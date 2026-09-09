#!/usr/bin/env python3
"""Catch-all standards check for files written outside Edit/Write.

Runs as a PostToolBatch hook, so it fires after every batch of tool calls with no matcher.
That is deliberate: `check_cs_edit.py` and `entity_pair_brief.py` both match `Edit|Write`, so
a file written by a Bash heredoc, `sed -i`, `tee`, `cp`, `dotnet new` or an MCP server's own
file-creation call used to land completely unchecked — no brief before, no advisory after, and
no skill invoked. Enumerating the tools that can write was rejected because the list is open:
the next MCP server is invisible until someone remembers to add its name. Watching the
filesystem instead covers every writer, including ones that do not exist yet.

Emits advisories as additionalContext. Never blocks, always exits 0 — the same contract as its
two siblings, and the reason all three can stay enabled.

Four scoping decisions are load-bearing:

  * The checks are imported from check_cs_edit.py, check_presentation_edit.py and
    check_comments.py, never reimplemented. A second copy of the parser would drift from the
    first, and the thresholds it enforces are the whole point.
  * A stamp file per session holds the epoch of the last sweep, and only files whose mtime has
    passed it are considered. Without that gate every batch would re-report every dirty file
    for the rest of the session, which is precisely how a hook gets muted.
  * Files this batch wrote through Edit/Write are excluded by path. check_cs_edit.py already
    reported them on PostToolUse in the same batch, and two copies of one advisory reads as a
    bug. What survives the exclusion is, by construction, exactly the gap this hook exists for.
  * A hard cap on files inspected and advisories emitted. A `sed -i` across the repo, or a
    branch switch, must not turn one tool batch into a wall of text or a 30-second stall.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Tools whose writes another hook already reported. Anything not in here that touched a file is
# what this sweep is for.
ALREADY_REPORTED_BY = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

# What the three checkers between them can say something about. `.cs` was the original list, and
# widening it is the whole reason this file changed: all three of the plugin's first hooks returned
# early on anything else, so a xib, a layout XML or AppStrings.resx written by any tool at all —
# Edit included — was never looked at. The non-`.cs` extensions are confined to the two platform
# projects and Core's Resources folder by is_in_scope() below, because `.xml` and `.resx` are far
# too common to accept repo-wide.
WATCHED_SUFFIXES = (".cs", ".xml", ".xib", ".storyboard", ".resx", "Contents.json")

# Prefixes the non-`.cs` suffixes are allowed under. A stray `.xml` in a build script or a NuGet
# config has no presentation rules to break and must not cost a `git` call.
MARKUP_ROOTS = (
    "WinTeam.Mobile.Android/Resources/",
    "WinTeam.Mobile.iOS/",
    "WinTeam.Mobile.Core/Resources/",
)

# Tools that cannot write a file. A batch made up entirely of these skips the `git status`
# below, which is what keeps a Read/Grep turn from paying for this hook at all. The polarity
# matters: an *unknown* tool name — a new MCP server, a tool added next release — is not on this
# list and therefore still triggers a sweep. Task is deliberately absent; a subagent writes real
# files, and its result arriving here is the last chance to notice if the subagent's own hooks
# did not fire.
READ_ONLY_TOOLS = {
    "Read", "Grep", "Glob", "NotebookRead", "TodoWrite", "WebFetch", "WebSearch",
    "ListAgents", "ToolSearch", "BashOutput", "ExitPlanMode", "Skill", "AskUserQuestion",
}

# Most recently touched files win. 25 is well clear of any real hand edit and still leaves the
# whole sweep inside its 30s timeout, since each file costs three short `git` calls.
MAX_FILES = 25
MAX_ADVISORIES = 20

SAFE_SESSION = re.compile(r"[^A-Za-z0-9_-]")


def stamp_path(session_id, suffix=".stamp"):
    """Where this session's high-water mark lives.

    Under the system temp dir rather than the plugin, because the plugin is served read-only
    from a version-keyed cache and per-session state has no business in a source tree.

    `suffix` exists so a second hook can keep its own per-session mark in the same directory
    without colliding with this one — plan_budget_brief.py uses ".planbrief" for the
    once-per-plan-mode-episode gate. A parameter here rather than a second copy of the
    sanitise-and-mkdir logic, for the same reason the checks are imported and never duplicated.
    """
    name = SAFE_SESSION.sub("_", session_id or "default")[:128]
    directory = os.path.join(tempfile.gettempdir(), "winteam-standards")
    try:
        os.makedirs(directory, exist_ok=True)
    except Exception:
        return None
    return os.path.join(directory, name + suffix)


def read_stamp(path):
    """The last sweep's epoch, or None when there is no usable stamp.

    None means "do not report this pass". A missing stamp happens on the first batch of a
    session that started before this plugin was enabled, and the alternative — treating it as
    zero — would dump an advisory for every dirty file in the working tree at once.
    """
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return float(handle.read().strip())
    except Exception:
        return None


def write_stamp(path, value):
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(repr(value))
    except Exception:
        pass


def repo_root(cwd):
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except Exception:
        pass
    return None


def is_in_scope(rel):
    """Is this repo-relative path one of the three checkers can say anything about?

    Deliberately generous — every checker self-scopes and returns [] on a path it does not own, so a
    false positive here costs three `git` calls and nothing else. A false negative costs an advisory,
    which is the expensive direction.
    """
    if rel.endswith(".cs"):
        return True
    return rel.endswith(WATCHED_SUFFIXES) and rel.startswith(MARKUP_ROOTS)


def dirty_files(root):
    """Absolute paths of in-scope files git sees as modified or new.

    `-uall` is load-bearing: the default collapses an untracked directory to a single entry, so
    a brand-new file inside a brand-new folder would be invisible — and a brand-new file is the
    most likely thing in a change to be over cap — and, since this hook widened past `.cs`, a
    brand-new xib or layout is the most likely thing to carry a hardcoded colour.
    `core.quotePath=false` keeps non-ASCII paths from arriving escaped and unopenable.

    Deleted paths are left in; advisories_for() drops them on its os.path.isfile check.
    """
    try:
        out = subprocess.run(
            ["git", "-c", "core.quotePath=false", "status", "--porcelain", "-uall"],
            cwd=root, capture_output=True, text=True, timeout=15,
        ).stdout
    except Exception:
        return []

    found = []
    for line in out.split("\n"):
        if len(line) < 4:
            continue
        rel = line[3:]
        # A rename reports `old -> new`; only the destination exists on disk.
        if " -> " in rel:
            rel = rel.split(" -> ")[-1]
        if not is_in_scope(rel):
            continue
        found.append(os.path.join(root, rel))
    return found


def could_have_written(payload):
    """Could anything in this batch have changed a file?

    An empty or absent tool_calls list counts as "yes". It is what the manual test command in the
    README sends, and more importantly absence of evidence is not evidence here — the cost of
    guessing wrong is a missed advisory, and the cost of guessing right is one `git status`.
    """
    calls = payload.get("tool_calls")
    if not calls:
        return True
    return any(
        not isinstance(call, dict) or call.get("tool_name") not in READ_ONLY_TOOLS
        for call in calls
    )


def written_by_other_tools(payload, floor):
    """Candidate files, newest first, minus anything Edit/Write already accounted for."""
    cwd = payload.get("cwd") or os.getcwd()
    root = repo_root(cwd)
    if not root:
        return []

    excluded = set()
    for call in payload.get("tool_calls") or []:
        if not isinstance(call, dict) or call.get("tool_name") not in ALREADY_REPORTED_BY:
            continue
        path = (call.get("tool_input") or {}).get("file_path")
        if path:
            excluded.add(os.path.realpath(path))

    candidates = []
    for path in dirty_files(root):
        if os.path.realpath(path) in excluded:
            continue
        try:
            mtime = os.path.getmtime(path)
        except Exception:
            continue
        if mtime > floor:
            candidates.append((mtime, path))

    candidates.sort(reverse=True)
    return [path for _mtime, path in candidates[:MAX_FILES]]


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    stamp = stamp_path(payload.get("session_id"))

    # SessionStart lays the mark down so the very first tool batch of a session already has a
    # floor to measure against. Without it the first non-Edit write of a session escapes.
    if "--init" in sys.argv[1:]:
        write_stamp(stamp, time.time())
        return 0

    floor = read_stamp(stamp)
    now = time.time()
    if floor is None:
        write_stamp(stamp, now)
        return 0

    if not could_have_written(payload):
        # Return without advancing the stamp. A backgrounded Bash process can land a file during
        # a run of read-only batches, and moving the floor past that window would lose it for
        # good. Leaving the mark where it is costs one extra file to stat on the next real batch.
        return 0

    paths = written_by_other_tools(payload, floor)

    # Taken before the scan, not after: a file written while this hook was running has an mtime
    # past `now` and is therefore caught on the next batch instead of being skipped forever.
    write_stamp(stamp, now)

    if not paths:
        return 0

    # Imported here, not at module scope. Nothing above this line needs them, and the no-op path
    # runs far more often than this one.
    import check_cs_edit
    import check_comments
    import check_member_order
    import check_presentation_edit

    check_cs_edit.load_thresholds()
    advisories = []
    for path in paths:
        for checker in (check_cs_edit, check_presentation_edit, check_comments, check_member_order):
            try:
                advisories.extend(checker.advisories_for(path))
            except Exception:
                # One unparseable file, or one failing checker, must not cost the advisories from
                # the others.
                continue

    if not advisories:
        return 0

    shown = advisories[:MAX_ADVISORIES]
    body = "\n".join(f"  - {item}" for item in shown)
    if len(advisories) > MAX_ADVISORIES:
        body += ("\n  - ...and %d more — run /winteam-standards:code-style --changed for the full list."
                 % (len(advisories) - MAX_ADVISORIES))

    context = ("winteam-standards advisories — written outside Edit/Write, so the usual pre-write "
               "brief never ran (non-blocking):\n" + body)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolBatch",
            "additionalContext": context,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
