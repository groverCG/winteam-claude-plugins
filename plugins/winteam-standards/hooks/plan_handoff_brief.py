#!/usr/bin/env python3
"""Hand-off brief for winteam-standards, emitted as an approved plan leaves plan mode.

Runs as a PreToolUse hook on ExitPlanMode. Reads the plan out of `tool_input["plan"]`, reports the
files it names with no line budget stated, and appends the rule sets the plan's own text earns.
Also clears plan_budget_brief.py's per-episode stamp, so a second round of planning in the same
session gets the budget card again. Never blocks, always exits 0.

Why ExitPlanMode, when it adds no coverage: measured over 66 transcripts, *zero* sessions reach
ExitPlanMode without having written the plan file first, so this is not a delivery of last resort.
Its value is when the context lands. additionalContext from a PreToolUse hook on ExitPlanMode is
still in the window once the approved plan starts being executed — which is precisely the case the
README names as the one where skills were observed silently not firing, "executing an
already-approved plan that already named the file and method shapes." This is a hand-off note into
execution, not a late attempt to fix the plan.

Four scoping decisions are load-bearing:

  * **It informs, it never denies.** A `permissionDecision: "deny"` here would work — the CLI would
    hand back the reason and ask for a revised plan — and it is deliberately not used, for the same
    never-block invariant the other five hooks share plus one reason specific to this hook: a plan
    check can only grep prose. It can see that a plan names a file with no number beside it; it
    cannot see whether a stated number is honest. Blocking on that grades the phrasing, and the
    cheapest way to satisfy it is boilerplate budget lines that change no code. check_cs_edit.py
    counts real lines in a real file, and that is where enforcement belongs.
  * **Paths, not class names.** `PunchesManager` in prose is not evidence the plan will touch that
    file; `WinTeam.Mobile.Core/Managers/PunchesManager.cs` is. Matching bare identifiers would fire
    on every plan that mentions a type in passing.
  * **Not one-brief-per-write.** entity_pair_brief.py and presentation_brief.py both pick exactly
    one brief, because a xib and a drawable have nothing in common and emitting both is wallpaper.
    That argument does not transfer: one plan legitimately spans a Manager and two xibs, and
    suppressing an axis would silently drop it. What keeps this quiet instead is that every route
    is matched against the plan's *own* text, plus the advisory cap.
  * **Every route is anchored on a path or a code token, never on prose.** This was measured before
    it shipped, which is this plugin's rule, and the first cut failed it: routing `appstrings` on the
    words "label", "alert" and "placeholder" fired on 27 of 51 saved plans, and routing the entity
    axis on a bare `*Manager` mention fired on 30. Together they made the hook fire on 46 of 51 — a
    hook that speaks on nine plans in ten is wallpaper. Anchoring each route on
    `WinTeam.Mobile.Core/Entities/`, `…/UseCases/`, `AppStrings`, `Bootstrap.cs`, `[Inject]` and the
    real subscription tokens is what brought it back down. The dropped prose signals are not lost:
    `/winteam-standards:ui-audit` and the post-write hooks still cover that ground.
  * **Silence on a clean plan is the whole contract.** A hook that fires on a correct plan is a hook
    that gets muted. The budget scan below is deliberately generous about what counts as a stated
    budget for that reason: a false negative here costs one advisory that was not printed, a false
    positive costs the hook's credibility.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STAMP_SUFFIX = ".planbrief"

# Matches the cap in check_presentation_edit.py. A plan naming thirty files should get a readable
# list and a pointer, not thirty bullets.
MAX_FILES_LISTED = 12

PATH_RE = re.compile(r"WinTeam\.Mobile\.(?:Core|iOS|Android)/[\w./+-]*\w")

# A budget counts as stated if a plausible line count or one of the budget words appears near the
# mention. Deliberately generous — see the fourth scoping decision. The 80-600 range is bounded
# below to skip ticket numbers' trailing digits and small counts ("3 parameters", "2 files"), and
# above because nothing over 600 is being proposed as a target.
BUDGET_RE = re.compile(
    r"\b(?:[1-5]\d{2}|[89]\d)\b|\bcaps?\b|\bbudget\b|\bunder\s+\d+\b|\bsplit\b|\bseam\b",
    re.I,
)

# How far from a path mention to look. Plans put the path in a heading or a table row and the
# budget on the line under it, so the window leans forward.
LOOK_BACK = 1
LOOK_FORWARD = 3

CS_RE = re.compile(r"\.cs$", re.I)

MARKUP_ROUTE = re.compile(
    r"\.xib\b|\.storyboard\b|Resources/layout|Resources/drawable|Resources/values|Assets\.xcassets",
    re.I,
)
ENTITY_ROUTE = re.compile(
    r"WinTeam\.Mobile\.Core/Entities/|WinTeam\.Mobile\.Core/Managers/[\w/]*\w+Manager\.cs"
)
USECASE_ROUTE = re.compile(r"WinTeam\.Mobile\.Core/UseCases/")
TEARDOWN_ROUTE = re.compile(
    r"\+=\s*\w|WeakReferenceMessenger|BusManager\.Subscribe|new Timer\(|AddObserver\(|"
    r"NSNotificationCenter"
)
DI_ROUTE = re.compile(r"\[Inject\]|Bootstrap\.cs|TinyIoC|BuildUp\(")
STRINGS_ROUTE = re.compile(r"AppStrings")

MARKUP_RULES = """  - Markup is in scope, so the static/dark/tablet axes are too — invoke
    `declarative-static-styling`, `checking-dark-mode` and `sizing-for-tablets`. A value that is the
    same on every load belongs in the xib or layout XML, not in ViewDidLoad/OnCreateView; colours are
    `@color/x` or a named colourset, never a hex; dimensions are `@dimen/x`, never a raw dp/sp. Never
    invent a colour name, a dark hex or a tablet value — surface the gap instead."""

ENTITY_RULES = """  - An entity, a Response or a Manager is in scope — invoke `response-entity-sibling`
    and `shaping-manager-contracts`. An *Entity needs WinTeamBusinessEntityBase,
    [AutoMap(typeof(*Response))] and exactly one [PrimaryKey]; a Manager maps only through
    WTBaseManager's synchronizers and returns Entity types, never a *Response."""

USECASE_RULES = """  - UseCases/ is in scope — invoke `writing-use-cases`. Note that zero of the
    existing use cases conform to the documented shape, so pattern-matching on the nearest file is
    the wrong move here; read the skill."""

TEARDOWN_RULES = """  - A subscription, message registration or timer is in scope — invoke
    `tearing-down-subscriptions`. Every subscribe needs its paired unsubscribe with a named method,
    not a lambda, and Dispose cannot be relied on here. Plan where the teardown goes now; it is the
    half that gets forgotten."""

DI_RULES = """  - Dependency injection is in scope — invoke `wiring-dependency-injection`. Collaborators
    are [Inject] properties resolved via BuildUp, registered in Bootstrap; no service location from
    TinyIoCContainer.Current."""

STRINGS_RULES = """  - User-facing text is in scope — invoke `appstrings`. The string goes in
    AppStrings.resx, and .resx and .Designer.cs must be edited together by hand in the same change:
    `dotnet build` never regenerates the Designer, so the two drift silently and the new member does
    not exist. Never invent a translation."""

ROUTES = (
    (MARKUP_ROUTE, MARKUP_RULES),
    (ENTITY_ROUTE, ENTITY_RULES),
    (USECASE_ROUTE, USECASE_RULES),
    (TEARDOWN_ROUTE, TEARDOWN_RULES),
    (DI_ROUTE, DI_RULES),
    (STRINGS_ROUTE, STRINGS_RULES),
)


def unbudgeted_paths(plan):
    """The .cs paths this plan names with no budget stated near them, in first-mention order.

    Split out from main() so it can be driven over the saved plans without a hook payload — which
    is how the noise level was measured before this shipped.
    """
    lines = plan.splitlines()
    windows = {}
    order = []
    for index, line in enumerate(lines):
        for match in PATH_RE.finditer(line):
            path = match.group(0).rstrip(".,;:`)")
            if not CS_RE.search(path):
                continue
            if path not in windows:
                windows[path] = []
                order.append(path)
            windows[path].append(index)

    unbudgeted = []
    for path in order:
        for index in windows[path]:
            start = max(0, index - LOOK_BACK)
            window = "\n".join(lines[start:index + LOOK_FORWARD + 1])
            # The path itself contains no digits worth matching, but a sibling path on the same
            # line might, so the paths are stripped before the budget scan.
            window = PATH_RE.sub(" ", window)
            if BUDGET_RE.search(window):
                break
        else:
            unbudgeted.append(path)
    return unbudgeted


def routed_rules(plan):
    """Every rule set this plan's text earns, in ROUTES order."""
    return [rules for pattern, rules in ROUTES if pattern.search(plan)]


def brief_for(plan):
    """The whole brief, or None when the plan earns nothing."""
    if not plan:
        return None

    sections = []
    unbudgeted = unbudgeted_paths(plan)
    if unbudgeted:
        shown = unbudgeted[:MAX_FILES_LISTED]
        listed = ", ".join("`%s`" % path for path in shown)
        more = ""
        if len(unbudgeted) > len(shown):
            more = " …and %d more." % (len(unbudgeted) - len(shown))
        sections.append(
            "  - **No line budget stated for:** %s.%s\n"
            "    Check each against its cap before writing it, and name the seam if it will not fit —\n"
            "    see `keeping-files-small`. Method bodies and parameter counts still apply per method:\n"
            "    `keeping-core-methods-small`." % (listed, more)
        )

    sections.extend(routed_rules(plan))
    if not sections:
        return None

    return ("winteam-standards — carrying the standards into execution (non-blocking):\n"
            + "\n".join(sections))


def clear_episode_stamp(session_id):
    """Drop the budget card's per-episode mark so the next plan-mode episode gets it again.

    Failure is silent on purpose: a stamp that cannot be removed costs one card that will not be
    re-emitted, and this hook's contract is that it never interferes with the turn.
    """
    try:
        import sweep_tool_writes

        stamp = sweep_tool_writes.stamp_path(session_id, suffix=STAMP_SUFFIX)
        if stamp and os.path.exists(stamp):
            os.remove(stamp)
    except Exception:
        pass


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    clear_episode_stamp(payload.get("session_id"))

    plan = (payload.get("tool_input") or {}).get("plan") or ""
    brief = brief_for(plan)
    if not brief:
        return 0

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": brief,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
