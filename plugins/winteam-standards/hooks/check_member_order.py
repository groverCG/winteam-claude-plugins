#!/usr/bin/env python3
"""Member declaration order for winteam-standards, checked after the write.

Two axes, both deterministic, both advisory. Runs as a PostToolUse hook on Edit|Write, and is also
called by sweep_tool_writes.py and scan_standards.py through the shared advisories_for() contract.

  * **A — state above behaviour.** A property or field declared below the first method body. This is
    the axis that prompted the skill: a bindable property parked between two methods is invisible to
    anyone scanning the top of the class for the type's state.
  * **B — a helper below its caller.** A `private` method with exactly one caller in the same file,
    declared *above* that caller. The stepdown rule: you read a method, then the things it calls.

Deliberately **absent from enforce_session_standards.CHECKERS**, so it can never hand the turn back.
That is a scoping decision, not an oversight. Reordering members of an existing class is not the
keystroke that a missing `///` block or a rename is, and three other rules in this plugin —
keeping-files-small, keeping-core-methods-small and new-slice — forbid reordering during a split or a
scaffold. A Stop hook that demanded a reorder would be pushing against them. Advisory-only keeps the
rule where it belongs: on members being written, read by the author who is writing them.

Why axis B is narrowed to single-caller helpers, measured before shipping as this plugin requires.
The natural reading of "keep the call chain together" is that nothing unrelated sits between a caller
and its helpers. Counted across WinTeam.Mobile.Core that fires on 44 of 150 files with three or more
methods — 98 findings, 29% of files — and inspecting them shows why: a shared helper cannot be
adjacent to all of its callers, and a method that fans out to seven helpers reads perfectly while
failing a contiguity test on every helper but the first (ProfileInfoViewModel.cs:264-294 is the
clearest example). A hook firing on three files in ten gets muted, so the contiguity half is taught
by the skill and swept by /winteam-standards:code-style, and only the unambiguous case is checked
here.

Measured noise for what *is* checked, across all three projects, over the 634 files containing a
method: axis A is 46 files and 212 findings, axis B is 19 files and 27 findings. With the changed-line
gate that hooks use, an edit elsewhere in an existing offender stays silent.

Scope is all three projects, unlike the method-length and doc-comment checks. Ordering is a
readability rule with no platform dimension: a ViewController's outlets belong above its actions for
exactly the reason a ViewModel's commands belong above its handlers.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_cs_edit

SKILL = "see the ordering-class-members skill"

# Defaults. thresholds.json overrides these; they stay here so a missing or malformed config
# degrades to the documented values instead of breaking a hook whose contract is "never blocks".
REQUIRE_MEMBER_ORDER = True

# Past this many findings of one kind in one file, emit a count instead of a list. Matches
# check_comments.py: LastStatusEntity.cs alone earns 22 on axis A, and 22 near-identical bullets is
# wallpaper.
COLLAPSE_AT = 6

_LOADED = False

MODIFIER = r"public|private|protected|internal|static|virtual|override|async|sealed|partial|new|readonly|const|abstract|extern|required"

# A property with its accessor on the same line: modifiers, a type, a name, then `{` or `=>`. The
# `(` check in state_members is what separates it from a method or an expression-bodied method —
# `Foo => 1` is a property, `Foo() => 1` is not.
PROPERTY = re.compile(r"^\s+(?:(?:%s)\s+)+[\w<>,\[\]\.\?\s]*?\b(\w+)\s*(\{|=>)" % MODIFIER)

# A property whose brace is on the *next* line, which is the dominant style in this repo — Allman,
# as ReSharper's default for C# leaves it. Missing this was worth 96 findings on the first cut of
# this checker: LoginViewModel.cs:279-301, the three properties that prompted the whole skill, are
# all written this way and every one of them was invisible. The line must end after the name, so no
# `(`, `{`, `=`, `;` or `,`, which is what keeps a wrapped method signature out.
PROPERTY_HEAD = re.compile(
    r"^\s+(?:(?:%s)\s+)+[\w<>,\[\]\.\?]+\s+(\w+)\s*(?://.*)?$" % MODIFIER)

# What may follow a PROPERTY_HEAD line and still make it a property.
ACCESSOR_BELOW = re.compile(r"^\s*(?:\{|=>)")

# A field: modifiers, a type, a name, then an initialiser or a semicolon. `=[^>]` rather than `=`
# so `=>` falls through to PROPERTY.
FIELD = re.compile(r"^\s+(?:(?:%s)\s+)+[\w<>,\[\]\.\?]+\s+(\w+)\s*(?:=[^>]|;)" % MODIFIER)

PRIVATE = re.compile(r"\bprivate\b")

# A type opening a new member scope. `enum` is included so its members are never mistaken for the
# enclosing type's fields.
TYPE_OPEN = re.compile(r"^[^/]*\b(?:class|record|struct|interface|enum)\s+(\w+)")


def type_owner(lines):
    """The innermost type enclosing each line, as a list indexed 1-based (index 0 is unused).

    Axis A has to be answered per type, not per file, and this is what makes that possible. Without
    it a nested type's first property is compared against the *outer* type's first method, and every
    correctly-ordered `ViewHolder` in the Android adapters reports — `KioskActionRowAdapter.cs:61`
    declares `ActionLabel` directly above its own constructor, which is exactly right, and was a
    finding on the first cut. Sibling types in one file have the same problem in the other direction.

    Brace counting is naive about braces inside strings, the same tolerance check_cs_edit's own
    parsers accept. A miscount costs a mislabelled owner and therefore a missed or spurious
    advisory, which is the failure mode this whole module is allowed to have.
    """
    owner = [None] * (len(lines) + 1)
    stack = []
    depth = 0
    pending = None
    for index, line in enumerate(lines, start=1):
        owner[index] = stack[-1][0] if stack else None
        match = TYPE_OPEN.match(line)
        if match:
            pending = match.group(1)
        for char in line:
            if char == "{":
                depth += 1
                if pending is not None:
                    stack.append((pending, depth))
                    pending = None
            elif char == "}":
                if stack and stack[-1][1] == depth:
                    stack.pop()
                depth -= 1
    return owner

# `Name(` not preceded by a word character or a dot, so `this.Foo(` and `other.Foo(` do not count as
# a local call and `GetFoo(` does not count as a call to `Foo`.
def _call_re(name):
    return re.compile(r"(?<![\w.])%s\s*\(" % re.escape(name))


def load_config():
    """Overlay thresholds.json onto the defaults above. Idempotent; safe to call per file.

    Called from advisories_for() behind a module flag, like check_comments.load_config(), so a
    caller that forgets cannot silently get the defaults.
    """
    global _LOADED, REQUIRE_MEMBER_ORDER
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
    require = config.get("requireMemberOrder")
    if isinstance(require, bool):
        REQUIRE_MEMBER_ORDER = require


def _is_backing_field(field_name, property_name):
    """Whether `_errorText` is the backing field for `ErrorText`.

    The skill puts a backing field immediately above its own property rather than up in the field
    block, which is already the idiom here. Without this the pair earns two findings where the
    author made one placement decision, and the field's finding is the misleading one.
    """
    stripped = field_name.lstrip("_")
    return bool(stripped) and stripped.lower() == property_name.lower()


def state_members(lines, method_spans, interface_lines):
    """Yield (kind, name, line_1based) for every field and property declared at type level.

    `method_spans` excludes locals: a `const` or a `var` inside a body is not a member, and matching
    on indentation instead would break on a nested type. `interface_lines` excludes interface bodies,
    where ordering is a contract's business and the property/method split does not apply.
    """
    for index, line in enumerate(lines, start=1):
        if index in interface_lines or any(start <= index <= end for start, end in method_spans):
            continue
        match = PROPERTY.match(line)
        if match:
            # Guard the method case the regex cannot see: `void Foo(int a) => Bar(a);` reaches
            # PROPERTY through the type-and-name group when the parameter list holds no `{`.
            if "(" not in line.split(match.group(2))[0]:
                yield "property", match.group(1), index
            continue
        match = PROPERTY_HEAD.match(line)
        if match:
            following = next((lines[ahead] for ahead in range(index, len(lines))
                              if lines[ahead].strip()), "")
            if ACCESSOR_BELOW.match(following):
                yield "property", match.group(1), index
            continue
        match = FIELD.match(line)
        if match:
            if "(" in line.split("=")[0].split(";")[0]:
                continue
            yield "field", match.group(1), index


def order_advisories(rel, lines, changed):
    """Axis A: properties and fields declared below the first method of their own type."""
    methods = [(name, decl, end, kind) for name, decl, _body, _params, end, kind
               in check_cs_edit.parse_methods(lines)]
    owner = type_owner(lines)

    # The first constructor *or* method of each type, so a nested type is measured against its own
    # members. Constructors count as the boundary because the order the skill prescribes puts
    # properties in group 5 and constructors in group 6 — a property below the constructor is out of
    # place for the same reason a property below a method is. Taking both kinds also makes this
    # independent of parse_methods' constructor detection, which reports `kind == "method"` for a
    # constructor carrying two modifiers (`protected internal WTBaseTabBarViewController(...)`) and
    # would otherwise move this boundary depending on how the constructor happens to be written.
    first_body = {}
    for _n, decl, _e, kind in methods:
        if kind == "decl":
            continue
        held = owner[decl]
        if held not in first_body:
            first_body[held] = decl
    if not first_body:
        return []

    spans = [(decl, end) for _n, decl, end, _k in methods]
    interface_lines = check_cs_edit.interface_body_lines(lines)

    found = [(kind, name, line) for kind, name, line
             in state_members(lines, spans, interface_lines)
             if line > first_body.get(owner[line], line)]

    # Drop a backing field whose own property is the very next member found. One placement, one
    # finding, and the property is the half worth naming.
    kept = []
    for position, (kind, name, line) in enumerate(found):
        following = found[position + 1] if position + 1 < len(found) else None
        if (kind == "field" and following and following[0] == "property"
                and _is_backing_field(name, following[1])):
            continue
        kept.append((kind, name, line))

    if changed is not None:
        kept = [item for item in kept if item[2] in changed]
    if not kept:
        return []

    if len(kept) > COLLAPSE_AT:
        return ["%s declares %d properties or fields below its type's first constructor or method "
                "(%s:%d onward). State belongs above behaviour — %s."
                % (rel, len(kept), rel, kept[0][2], SKILL)]
    return ["%s:%d %s %s is declared below the first constructor or method of %s. Move it up with "
            "the other %s — %s." % (rel, line, kind, name, owner[line] or "the type",
                                    "properties" if kind == "property" else "fields", SKILL)
            for kind, name, line in kept]


def adjacency_advisories(rel, lines, changed):
    """Axis B: a private single-caller helper declared above its only caller."""
    methods = [(name, decl, end) for name, decl, _body, _params, end, kind
               in check_cs_edit.parse_methods(lines) if kind == "method"]
    if len(methods) < 2:
        return []

    bodies = ["\n".join(lines[decl:end]) for _n, decl, end in methods]
    names = {name: position for position, (name, _d, _e) in enumerate(methods)}

    out = []
    for position, (name, decl, _end) in enumerate(methods):
        if not PRIVATE.search(lines[decl - 1]):
            continue
        pattern = _call_re(name)
        callers = [other for other in range(len(methods))
                   if other != position and pattern.search(bodies[other])]
        # Exactly one caller is the whole scope of this check: a helper with two callers cannot sit
        # below both, and one with none is either an event handler or dead, neither of which this
        # axis has an opinion about.
        if len(callers) != 1 or position > callers[0]:
            continue
        caller_name, caller_decl, _e = methods[callers[0]]
        if changed is not None and decl not in changed and caller_decl not in changed:
            continue
        out.append("%s:%d %s() is only called by %s() at line %d, but is declared above it. A helper "
                   "reads below its caller — %s." % (rel, decl, name, caller_name, caller_decl, SKILL))
    return out


def advisories_for(path, report_all=False):
    """Every member-order advisory this file earns, or [] when it is out of scope.

    Same contract as check_cs_edit.advisories_for(), so any caller can hand it a path straight from
    `git status`. `report_all=True` drops the changed-lines gate, which is the only way
    /winteam-standards:code-style can see the existing backlog.
    """
    load_config()
    if not REQUIRE_MEMBER_ORDER:
        return []
    if not path or not path.endswith(".cs") or not os.path.isfile(path):
        return []
    base = os.path.basename(path)
    if base.endswith(".Designer.cs") or base.endswith(".designer.cs"):
        return []

    rel, root = check_cs_edit.repo_relative(path)
    if "/obj/" in rel or "/bin/" in rel:
        return []
    if not any(rel.startswith(prefix) for prefix, _cap in check_cs_edit.FILE_CAPS):
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
    for check in (order_advisories, adjacency_advisories):
        try:
            out.extend(check(rel, lines, changed))
        except Exception:
            # One failing axis must not cost the other's advisories. Advisory-only means a bug here
            # degrades to silence, never to a broken edit.
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
                "winteam-standards member-order advisories (non-blocking):\n" + body,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
