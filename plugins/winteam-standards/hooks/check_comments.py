#!/usr/bin/env python3
"""Advisory documentation-comment check for winteam-standards.

Runs as a PostToolUse hook after Edit/Write on a .cs file, and is imported by
sweep_tool_writes.py and enforce_session_standards.py so the same three checks cover a file
written by any tool and again at end of turn. Emits advisories as additionalContext; never
blocks, always exits 0 — the same contract as its three siblings.

A fourth peer module rather than 190 more lines in the already-769-line check_cs_edit.py. The
git helpers and the method parser are imported from that file, never copied: the README forbids
a second copy, and parse_methods()' constructor and interface handling is already measured
against these projects.

`naming-and-documenting-members` owns two rules that nothing measured before this file existed —
every method gets a `///` block, and a `//` never narrates a body — and both were counted against
the whole repo before shipping, which is the plugin's rule for adding a check. The counts are the
reason the gating below looks the way it does:

  * **912 of 948 public/protected members in Core carry no `///` block (96%).** The house style is
    currently the opposite of the rule, so this check is viable only on the narrowest possible
    gate. It fires when the *declaration line itself* changed — a new member or an edited
    signature — and deliberately NOT when a line deep inside an existing undocumented method's
    body changed. The wider gate the length check uses (any line in decl..end) would have turned
    every edit to an existing method into a documentation advisory, which is the exact shape of
    noise that gets a hook muted.
  * **226 in-body prose comments and 25 commented-out-code lines**, ~0.5 per file between them —
    lower density than the checks that shipped, so no extra gate was needed beyond changed lines.
    They are reported as two different advisories because they have two different fixes: prose
    means the name is wrong or the block wants extracting, dead code just gets deleted.

    Those two numbers were first estimated at 426 and 157 by an `awk` proxy that treated brace
    depth >= 2 as "inside a method". **The proxy over-counted by 258**, because a file-scoped
    namespace puts class-level members at depth 2, as do property accessors and object
    initializers. The figures above come from the real check, which is scoped to a method body
    parsed by parse_methods() — which is what the rule actually says. Worth knowing if anyone
    re-measures with a grep and gets a bigger number: the grep is wrong, not the check.
  * **In-body `//` separators: 0.** No carve-out was needed.

Findings collapse to a summary past COLLAPSE_AT per file. A new 40-member file would otherwise
emit 40 near-identical advisories, and the aggregation doctrine in the code-style command applies
just as much at the source as in the report.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_cs_edit

CORE_PREFIX = "WinTeam.Mobile.Core/"
SKILL = "see the naming-and-documenting-members skill"

# Defaults. thresholds.json overrides these; they stay here so a missing or malformed config
# degrades to the documented values instead of breaking a hook whose contract is "never blocks".
REQUIRE_DOC_COMMENTS = True
COMMENT_CARVE_OUT_PREFIXES = ("TODO", "HACK", "NOTE", "FIXME", "NOSONAR", "XXX")

# Past this many findings of one kind in one file, emit a count instead of a list.
COLLAPSE_AT = 6

_LOADED = False

# A line whose first non-space content is `//` but not `///`.
LEADING_COMMENT = re.compile(r"^\s*//(?!/)")
# Code, then a trailing `//` but not `///`.
TRAILING_COMMENT = re.compile(r"\S\s*//(?!/)")
# The return type sits immediately before the method name.
RETURN_TYPE = re.compile(r"([\w<>\[\],\.\?]+)\s+%s\s*[<(]")
# Lines that may sit between a `///` block and the declaration it documents.
SKIPPABLE_ABOVE = re.compile(r"^\s*(?:\[|#region\b|#if\b|#endif\b|#pragma\b|$)")
PUBLIC_OR_PROTECTED = re.compile(r"\b(?:public|protected)\b")
IS_OVERRIDE = re.compile(r"\boverride\b")
# Commented-out code, kept deliberately identical to the heuristic the 157 count was measured
# with. Changing it invalidates that number, so re-count before touching it.
LOOKS_LIKE_CODE = re.compile(
    r";\s*$|^\}|^(?:var|if|await|return|foreach|using)\b.*[;{]")
URL = re.compile(r"https?://")


def load_config():
    """Overlay thresholds.json onto the defaults above. Idempotent; safe to call per file.

    Unlike check_cs_edit.load_thresholds(), which its callers must remember to invoke, this is
    called from advisories_for() behind a module flag. Same "read the config once per process"
    result, minus a footgun: three separate callers now import this module, and a caller that
    forgot would silently get the defaults rather than the configured values.
    """
    global _LOADED, REQUIRE_DOC_COMMENTS, COMMENT_CARVE_OUT_PREFIXES
    if _LOADED:
        return
    _LOADED = True
    try:
        with open(check_cs_edit.CONFIG_PATH, encoding="utf-8") as handle:
            config = json.load(handle)
    except Exception:
        return
    if not isinstance(config, dict):
        return

    require = config.get("requireDocComments")
    if isinstance(require, bool):
        REQUIRE_DOC_COMMENTS = require

    # An explicit `[]` means "no carve-outs" and is honoured; only a non-list falls back to the
    # defaults. Same semantics as lengthCarveOuts, and thresholds.json documents it once.
    prefixes = config.get("commentCarveOutPrefixes")
    if isinstance(prefixes, list):
        COMMENT_CARVE_OUT_PREFIXES = tuple(p for p in prefixes if isinstance(p, str))


def _doc_block_above(lines, decl):
    """The `///` lines documenting the member declared at 1-based `decl`, or [].

    Walks upward past attributes, blanks and preprocessor directives, because all three
    legitimately sit between a doc block and the signature it belongs to.
    """
    index = decl - 2
    while (index >= 0 and SKIPPABLE_ABOVE.match(lines[index])
           and not lines[index].lstrip().startswith("///")):
        index -= 1
    block = []
    while index >= 0 and lines[index].lstrip().startswith("///"):
        block.append(lines[index].lstrip()[3:])
        index -= 1
    block.reverse()
    return block


def _is_documentable(lines, name, decl, kind):
    """Does this member owe a `///` block?

    Interface declarations always do — they carry no modifier and are implicitly public. Concrete
    members owe one when they are public or protected and not an `override`, where the base
    already carries the documentation.
    """
    if kind == "decl":
        return True
    line = lines[decl - 1]
    if not PUBLIC_OR_PROTECTED.search(line) or IS_OVERRIDE.search(line):
        return False
    return name not in check_cs_edit.LENGTH_CARVE_OUTS


def _returns_a_value(lines, decl, name):
    """Is the return type something a `<returns>` tag should describe?

    `void` and a bare `Task` return nothing. `Task<T>`, `ValueTask<T>` and every ordinary type do.
    """
    match = re.search(RETURN_TYPE.pattern % re.escape(name), lines[decl - 1])
    if not match:
        return False
    return match.group(1) not in ("void", "Task", "ValueTask")


def _doc_advisories(rel, lines, changed, collapse=True):
    """Missing and incomplete `///` blocks on members this edit declared or re-signed."""
    if not REQUIRE_DOC_COMMENTS:
        return []
    missing, incomplete = [], []
    for name, decl, _body, params, _end, kind in check_cs_edit.parse_methods(lines):
        # The declaration line, not the whole method. See the module docstring: the wider gate
        # would fire on all 912 pre-existing offenders the moment anyone edited a body.
        if changed is not None and decl not in changed:
            continue
        if not _is_documentable(lines, name, decl, kind):
            continue

        block = _doc_block_above(lines, decl)
        if not block:
            missing.append((decl, name))
            continue

        text = "\n".join(block)
        gaps = []
        if "<summary>" not in text:
            gaps.append("no <summary>")
        documented = text.count("<param ")
        if documented < params:
            gaps.append("%d of %d <param> tags" % (documented, params))
        if "<returns>" not in text and _returns_a_value(lines, decl, name):
            gaps.append("no <returns>")
        if gaps:
            incomplete.append((decl, name, ", ".join(gaps)))

    out = _collapse(rel, missing, collapse, "%s:%d %s() has no /// block",
                    "%s: %d members declared here have no /// block",
                    "Summary, one <param> each, <returns> when non-void — %s." % SKILL)
    out.extend(_collapse(rel, incomplete, collapse, "%s:%d %s()'s /// block is incomplete — %s",
                         "%s: %d /// blocks here are incomplete",
                         "Every parameter needs a <param> — %s." % SKILL))
    return out


def _comment_advisories(rel, lines, changed, collapse=True):
    """In-body `//` comments added by this edit, split by what the fix is."""
    spans = [(decl, end) for _n, decl, body, _p, end, kind in check_cs_edit.parse_methods(lines)
             if kind == "method" and body > 0]
    narrating, dead = [], []
    for index, line in enumerate(lines):
        line_number = index + 1
        if changed is not None and line_number not in changed:
            continue
        if not LEADING_COMMENT.match(line) and not TRAILING_COMMENT.search(line):
            continue
        if not any(decl < line_number < end for decl, end in spans):
            continue
        text = line.split("//", 1)[1].strip() if "//" in line else ""
        if not text or URL.search(line) or text.upper().startswith(COMMENT_CARVE_OUT_PREFIXES):
            continue
        (dead if LOOKS_LIKE_CODE.search(text) else narrating).append((line_number, text[:60]))

    out = _collapse(rel, narrating, collapse, "%s:%d // narrates the body: \"%s\"",
                    "%s: %d // comments here narrate the body",
                    "If a line needs explaining the name is wrong or the block wants "
                    "extracting — %s." % SKILL)
    out.extend(_collapse(rel, dead, collapse, "%s:%d commented-out code: \"%s\"",
                         "%s: %d lines of commented-out code here",
                         "Delete it; git remembers — %s." % SKILL))
    return out


def _collapse(rel, findings, collapse, one, many, advice):
    """One advisory per finding, or a single count past COLLAPSE_AT.

    A new file with forty undocumented members must not print forty near-identical lines in a hook
    advisory. The collapsed form still names the count, so it cannot read as fewer than it found.

    `collapse=False` for a report — /winteam-standards:code-style does its own grouping and has to
    state true totals, and collapsing here first made a 912-finding backlog scan report 645 rows.
    Aggregating twice, with the first pass invisible to the second, is how a report understates.
    """
    if not findings:
        return []
    if collapse and len(findings) > COLLAPSE_AT:
        first = ", ".join(str(item[0]) for item in findings[:5])
        return ["%s (first at lines %s, ...). %s" % (many % (rel, len(findings)), first, advice)]
    return ["%s. %s" % (one % ((rel,) + tuple(item)), advice) for item in findings]


def advisories_for(path, report_all=False):
    """Every comment advisory this file earns, or [] when it is out of scope.

    `report_all=True` drops the changed-lines gate, which is the only way a repo-wide scan can see
    the 912-member backlog the module docstring measures. Hooks always leave it False: on that
    gate the check is about the author's own work, off it, it is a report.

    Same contract as check_cs_edit.advisories_for(), so any caller can hand it a path straight
    from `git status` without pre-filtering. Core-only: the doc-comment and narration rules are
    WinTeam.Mobile.Core rules, and platform view code is exempt for the same reason it is exempt
    from the method-length cap.
    """
    load_config()
    if not path or not path.endswith(".cs") or not os.path.isfile(path):
        return []
    base = os.path.basename(path)
    if base.endswith(".Designer.cs") or base.endswith(".designer.cs"):
        return []

    rel, root = check_cs_edit.repo_relative(path)
    if "/obj/" in rel or "/bin/" in rel or not rel.startswith(CORE_PREFIX):
        return []

    try:
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            lines = handle.read().split("\n")
    except Exception:
        return []
    if lines and lines[-1] == "":
        lines.pop()

    changed = None if report_all else check_cs_edit.changed_line_numbers(rel, root)
    if changed is not None and not changed:
        return []

    out = []
    for check in (_doc_advisories, _comment_advisories):
        try:
            out.extend(check(rel, lines, changed, collapse=not report_all))
        except Exception:
            # One failing check must not cost the advisories from the other. Advisory-only means
            # a bug here degrades to silence, never to a broken edit.
            continue
    return out


MAX_ADVISORIES = 12


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    check_cs_edit.load_thresholds()
    advisories = advisories_for((payload.get("tool_input") or {}).get("file_path") or "")
    if not advisories:
        return 0

    shown = advisories[:MAX_ADVISORIES]
    body = "\n".join("  - %s" % item for item in shown)
    if len(advisories) > MAX_ADVISORIES:
        body += ("\n  - ...and %d more — ask for /winteam-standards:code-style --changed for the "
                 "full list." % (len(advisories) - MAX_ADVISORIES))

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext":
                "winteam-standards documentation advisories (non-blocking):\n" + body,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
