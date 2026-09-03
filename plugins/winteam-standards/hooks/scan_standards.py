#!/usr/bin/env python3
"""The engine behind /winteam-standards:code-style. Not a hook — nothing in hooks.json runs it.

It lives beside the checkers because it imports them. Given a list of paths on stdin, it runs
every check the hooks run and prints one tab-separated record per finding:

    axis <TAB> path <TAB> line <TAB> text

Two reasons this is a committed script rather than a snippet the command writes to the scratchpad:

  * The command used to re-derive the caps in `awk` and a throwaway parser, and its own comments
    apologised for the drift twice — `wc -l` under-reporting against the hook's line count, and a
    `python3` approval prompt on every run. One file, imported by both, cannot drift.
  * A scratchpad script is unreviewed and unversioned. This one is neither.

It runs the checkers with `report_all=True`, which drops the HEAD baseline the hooks use. That is
the whole difference between the two callers: a hook asks "did this edit make it worse", a report
asks "what is here". See check_cs_edit.advisories_for().

`axis` is derived by matching the advisory text against MARKERS. Classifying a string is fragile
by nature, and it was chosen anyway: the alternative is a severity/axis field threaded through
four checkers and every advisory they build, and a miss here costs one row filed under `other` —
visible, harmless, and easy to fix by adding a marker.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_cs_edit
import check_comments
import check_presentation_edit

CHECKERS = (check_cs_edit, check_presentation_edit, check_comments)

# First match wins, so order matters: the narrower patterns come first.
MARKERS = (
    ("file-size", re.compile(r"-line cap for this project")),
    ("parameters", re.compile(r"takes \d+ parameters")),
    ("method-length", re.compile(r"body is \d+ lines")),
    ("teardown", re.compile(r"tearing-down-subscriptions")),
    ("entity-pair", re.compile(r"response-entity-sibling")),
    ("doc-comment", re.compile(r"/// block")),
    ("comment", re.compile(r"narrates the body|commented-out code")),
    ("presentation", re.compile(
        r"declarative-static-styling|checking-dark-mode|sizing-for-tablets|appstrings")),
)

LINE_REF = re.compile(r"^\S+?:(\d+)\s")


def axis_of(text):
    for name, pattern in MARKERS:
        if pattern.search(text):
            return name
    return "other"


def line_of(text):
    match = LINE_REF.match(text)
    return match.group(1) if match else "-"


def main():
    paths = [line.strip() for line in sys.stdin if line.strip()]
    if not paths:
        print("scan_standards: no paths on stdin", file=sys.stderr)
        return 1

    check_cs_edit.load_thresholds()
    check_comments.load_config()

    root = None
    for path in paths:
        if not os.path.isfile(path):
            continue
        absolute = os.path.abspath(path)
        for checker in CHECKERS:
            try:
                found = checker.advisories_for(absolute, report_all=True)
            except Exception as error:
                print("scan_standards: %s failed on %s: %s"
                      % (checker.__name__, path, error), file=sys.stderr)
                continue
            for text in found:
                rel = text.split(":")[0].split(" ")[0]
                print("%s\t%s\t%s\t%s" % (axis_of(text), rel, line_of(text), text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
