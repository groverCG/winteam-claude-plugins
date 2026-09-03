#!/usr/bin/env python3
"""End-of-turn standards enforcement for winteam-standards.

Runs as a `Stop` hook with no matcher, so it fires once per turn after the work is done. It
re-checks every file this session created, modified or renamed and, unlike the other seven
hooks, it can hand the turn back.

**This is the one hook here that blocks, and the exception is deliberate.** The others share a
contract stated in the README — advisory only, exit 0, never block — and the reasoning behind it
still holds for all of them. Two facts make this one different:

  * The other hooks fire *mid-turn* and their advisories are suggestions. `sweep_tool_writes.py`'s
    mtime stamp, which is what keeps it quiet, also guarantees an ignored advisory is never raised
    a second time. Nothing verified that a session ended with its own files clean.
  * The README's own dividing line is "enforce where you can measure; inform where you cannot" —
    the reason `plan_handoff_brief.py` declines to block an `ExitPlanMode`, since a plan check can
    only grep prose and blocking on it would grade the phrasing. Everything reported here is a
    counted line in a real file.

Every finding is HEAD-relative, because the checkers already only fire when an edit made a file
worse. That is what makes blocking safe rather than hostile: 294 Core methods are over the length
cap and 912 public members carry no `///` block already, and a hook that blocked on those would be
unsatisfiable and disabled within a day.

Three guards bound the blocking, and all three are required:

  * `stop_hook_active` — already a continuation this hook caused, so report and let the turn end.
  * A per-session ledger. A file that has blocked once is reported but never blocks again. Some
    findings are a judgment call rather than a fix (a file over cap needs a responsibility taken
    out, which needs the feature's context), and a hook with no escape from those is a hook that
    gets deleted rather than satisfied.
  * A cap on how many findings go into the block reason, with a pointer to the command for the
    rest. One turn must not paste a wall of text into the next.

The relent path reports through `systemMessage` rather than `additionalContext`. A `Stop` hook that
does not block has no channel to the model — the turn is over — so the outstanding findings go to
the user, who is the one who can decide they are acceptable.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_cs_edit
import check_comments
import check_presentation_edit
import sweep_tool_writes as sweep

CHECKERS = (check_cs_edit, check_presentation_edit, check_comments)

# Past this, the reason names the count and points at the command. Deliberately smaller than the
# sweep's 20: this text is the next turn's instructions, not a report.
MAX_BLOCK_FINDINGS = 15

# Files inspected per turn. Matches the sweep's cap for the same reason — a branch switch or a
# repo-wide `sed -i` must not turn one Stop into a 40-second stall.
MAX_FILES = 25

# A finding whose fix is a judgment call, not a keystroke. Matched on the advisory text, which is
# fragile by nature; a miss costs a mislabelled heading and nothing else, so the checkers are not
# reshaped to carry a severity field for it.
JUDGMENT_MARKERS = ("-line cap for this project",)

SESSION_SUFFIX = ".session"
LEDGER_SUFFIX = ".raised"


def session_floor(session_id):
    """The epoch this session started, or None when there is no usable mark.

    Its own stamp rather than the sweep's: that one is a high-water mark that advances on every
    tool batch, and this hook needs a floor that does not move, or "changed this session" would
    decay into "changed since the last batch" and miss everything fixed earlier in the turn.

    None means "do not report". A session that began before this hook was installed has no mark,
    and treating that as zero would block the first turn over every dirty file in the tree.
    """
    return sweep.read_stamp(sweep.stamp_path(session_id, SESSION_SUFFIX))


def read_ledger(session_id):
    path = sweep.stamp_path(session_id, LEDGER_SUFFIX)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_ledger(session_id, ledger):
    path = sweep.stamp_path(session_id, LEDGER_SUFFIX)
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(ledger, handle)
    except Exception:
        pass


def session_files(cwd, floor):
    """Absolute paths of in-scope files this session created, modified or renamed.

    `sweep.dirty_files()` already asks git the right question — `--porcelain -uall`, so a new file
    inside a new folder is visible, with renames resolved to the destination that exists on disk —
    and applies the same in-scope filter. Imported rather than re-asked.
    """
    root = sweep.repo_root(cwd)
    if not root:
        return []
    found = []
    for path in sweep.dirty_files(root):
        try:
            if os.path.getmtime(path) > floor:
                found.append((os.path.getmtime(path), path))
        except Exception:
            continue
    found.sort(reverse=True)
    return [path for _mtime, path in found[:MAX_FILES]]


def findings_for(paths):
    """`{repo_relative_path: [advisory, ...]}` across all three checkers."""
    check_cs_edit.load_thresholds()
    out = {}
    for path in paths:
        advisories = []
        for checker in CHECKERS:
            try:
                advisories.extend(checker.advisories_for(path))
            except Exception:
                # One unparseable file, or one failing checker, must not cost the findings from
                # the others — the same tolerance the sweep applies.
                continue
        if advisories:
            rel, _root = check_cs_edit.repo_relative(path)
            out[rel] = advisories
    return out


def split_by_fix(findings, only):
    """Partition the advisories of the files in `only` into (mechanical, judgment).

    The block reason states them separately because they ask for different things: one is a
    keystroke, the other is a decision about where a responsibility belongs.

    `only` is the set of files that have not blocked yet. Restricting to it is what makes the
    ledger's promise true: a file whose finding was raised and left standing — an over-cap file
    with no seam the author could see — does not come back every time some *other* file earns a
    block. Without that, one unsplittable file would reappear in every block for the rest of the
    session, which is the nagging the ledger exists to prevent.
    """
    mechanical, judgment = [], []
    for rel in only:
        for item in findings.get(rel, ()):
            (judgment if any(m in item for m in JUDGMENT_MARKERS) else mechanical).append(item)
    return mechanical, judgment


def build_reason(mechanical, judgment, standing):
    """The text handed back to the model as the next turn's instructions.

    `standing` counts findings in files already raised once. They are stated as a number and not
    re-listed — see split_by_fix() — so the turn knows the backlog exists without being asked to
    revisit a decision that was already made.
    """
    parts = ["winteam-standards: files this session touched still violate the standards. "
             "Fix them before finishing, or say why a finding should stand."]

    budget = MAX_BLOCK_FINDINGS
    for label, group, note in (
        ("Fix these now", mechanical,
         "Each is a local edit — a /// block, a rename, deleting a commented-out line, or moving "
         "a collaborator to an [Inject] property."),
        ("Judgment call", judgment,
         "A split needs the feature's context. Take a responsibility out if you can see the seam; "
         "otherwise say so and move on — this will not be raised again."),
    ):
        if not group:
            continue
        shown = group[:budget]
        budget -= len(shown)
        parts.append("\n%s (%d):\n%s" % (label, len(group),
                                         "\n".join("  - %s" % item for item in shown)))
        if len(group) > len(shown):
            parts.append("  ...and %d more." % (len(group) - len(shown)))
        parts.append("  %s" % note)
        if budget <= 0:
            break

    if standing:
        parts.append("\n%d further finding(s) were raised earlier and left standing; they are not "
                     "repeated here." % standing)
    parts.append("\nFull list: /winteam-standards:code-style --changed")
    return "\n".join(parts)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    session_id = payload.get("session_id")

    # SessionStart lays the floor down. Without it the first turn has nothing to measure against.
    if "--init" in sys.argv[1:]:
        import time
        sweep.write_stamp(sweep.stamp_path(session_id, SESSION_SUFFIX), time.time())
        write_ledger(session_id, {})
        return 0

    floor = session_floor(session_id)
    if floor is None:
        return 0

    findings = findings_for(session_files(payload.get("cwd") or os.getcwd(), floor))
    if not findings:
        return 0

    ledger = read_ledger(session_id)
    unraised = [rel for rel in findings if not ledger.get(rel)]

    # Either this hook already handed the turn back once, or every offending file has had its
    # turn. Tell the user and stop — the model cannot be reached from here anyway.
    if payload.get("stop_hook_active") or not unraised:
        total = sum(len(items) for items in findings.values())
        print(json.dumps({"systemMessage":
                          "winteam-standards: %d finding(s) outstanding across %d file(s). "
                          "Run /winteam-standards:code-style --changed to see them."
                          % (total, len(findings))}))
        return 0

    standing = sum(len(items) for rel, items in findings.items() if rel not in unraised)
    for rel in findings:
        ledger[rel] = ledger.get(rel, 0) + 1
    write_ledger(session_id, ledger)

    mechanical, judgment = split_by_fix(findings, unraised)
    print(json.dumps({"decision": "block",
                      "reason": build_reason(mechanical, judgment, standing)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
