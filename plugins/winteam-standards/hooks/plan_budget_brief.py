#!/usr/bin/env python3
"""Authoring-budget brief for winteam-standards, delivered while the plan is being written.

Runs as a PreToolUse hook with **no matcher**, gated on `permission_mode == "plan"` and standing down on
ExitPlanMode. Emits the size, parameter, documentation and layer budget once per plan-mode episode, as
additionalContext, so the numbers are in context while the plan is composed rather than after the code is
written. Never blocks, always exits 0.

One note on the output field, because the docs will make it look wrong: `hookSpecificOutput.additionalContext`
is published for SessionStart, UserPromptSubmit and PostToolUse, and the PreToolUse entry lists only
`permissionDecision`, `permissionDecisionReason`, `updatedInput` and `hookEventName`. It nonetheless works on
PreToolUse — verified by this card landing in a live plan-mode session, rendered as "PreToolUse hook additional
context". Do not migrate this to `updatedInput`; that would rewrite the tool call being made.

Why this exists: the README's own account of why the five existing hooks were needed names
"executing an already-approved plan that already named the file and method shapes" as one of the
two cases where nothing fired. The plan is where those shapes get decided, and every existing hook
sits at or after the write. Measured over the 51 saved plans in ~/.claude/plans, 43 name
WinTeam.Mobile.Core and only 11 state any budget at all; the other 32 hand execution a shape
nobody costed.

Four scoping decisions are load-bearing:

  * **No matcher.** The first tool call of a plan-mode episode is whatever gets reached for first —
    a Read, a Grep, an Agent launch — and enumerating those names is exactly the mistake
    sweep_tool_writes.py exists to avoid: a tool list is wrong the moment someone installs a new
    MCP server. Gating on permission_mode instead is stable across any future tool.
  * **The card is universal, not path-routed.** At the first tool call the plan does not exist yet,
    so there is nothing to route on. That is the price of firing early, and it is the right trade:
    the plan-file Write *could* be routed, but it lands after the plan content is composed, and
    27 of 57 measured sessions write the plan file exactly once — so in half of them a brief there
    influences nothing. Path-routed rules ride on plan_handoff_brief.py, which has the plan text.
  * **Once per episode, via a stamp.** Plans are rewritten up to seven times in one session. Without
    the stamp this card would be injected seven times, which is most of the token cost it exists to
    save. plan_handoff_brief.py clears the stamp on ExitPlanMode, so a second round of planning in
    the same session gets the card again — that pairing is why these are two hooks and not one.
  * **Numbers come from thresholds.json, never from a literal here.** load_thresholds() is imported
    from check_cs_edit so a cap change reaches this card for free. A second copy of the numbers
    would drift, and drifting numbers in the *planning* layer are worse than no card: the plan would
    then disagree with the hook that checks the result.

Cost, measured rather than estimated, because a matcher-less hook spawns python3 on every tool call
for the rest of the episode. On this machine: ~55ms once gate 1 has rejected a non-plan-mode call,
~80ms on the in-plan-mode path where the stamp already exists, against a ~43ms floor for
`python3 -c pass`. So the hook's own work is 12-37ms and the rest is interpreter startup, which no
amount of tuning here removes. Across a thirty-call plan-mode session that is roughly two seconds of
wall clock. Worth knowing before adding a second matcher-less hook: the floor is paid per hook, per
call, so the next one doubles it.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STAMP_SUFFIX = ".planbrief"


CORE = "WinTeam.Mobile.Core/"

# The Core cap carries ~50 lines of tolerance: keeping-files-small states 200 as the target and the
# thresholds.json value as the line not to cross. Deriving the target rather than hardcoding 200
# keeps the pair consistent if the cap is ever changed, and the arithmetic is documented here so it
# does not read as an invented number.
CORE_TOLERANCE = 50


def cap_for(prefix, file_caps, default):
    """The cap for a project prefix, out of check_cs_edit's FILE_CAPS tuple."""
    for path, value in file_caps:
        if path == prefix:
            return value
    return default


def card(file_caps, max_body, max_params):
    """The budget card, formatted from thresholds.json's live values.

    Takes the three numbers rather than the check_cs_edit module, so the text can be rendered and
    eyeballed without importing a hook or constructing a payload.
    """
    core = cap_for(CORE, file_caps, 250)
    ios = cap_for("WinTeam.Mobile.iOS/", file_caps, 350)
    android = cap_for("WinTeam.Mobile.Android/", file_caps, 450)

    return """winteam-standards — authoring budget for this plan (invoke `keeping-files-small`, \
`keeping-core-methods-small`, `naming-and-documenting-members` and `respecting-layer-boundaries` \
before writing):
  - **State a line budget beside every file this plan names.** A plan that names a file with no
    number is how an over-cap Manager gets approved and split afterwards, which is the expensive
    path: at the cap the seam is twenty minutes, at 600 lines it is a week.
  - File caps: WinTeam.Mobile.Core/ **%d** (aim at %d — the cap carries ~%d lines of tolerance),
    WinTeam.Mobile.iOS/ **%d**, WinTeam.Mobile.Android/ **%d**. Whole project, not only Views/.
    Generated files are exempt.
  - If a file in this plan cannot fit its cap, **name the seam in the plan**: a partial, a plain
    collaborator class, a child view model, or a record collapsing a wide parameter surface — in
    that order of cost. Do not leave it for execution to discover.
  - One exception to that order: for a **Manager or Proxy**, a new sibling class beats a partial —
    with its own `I*Manager` interface if a ViewModel injects it. A secondary partial leaves the
    `[Inject]` properties in the primary file, so the half doing the work has no declaration
    explaining where its collaborator came from. Follow `Managers/Punches/` or
    `Proxies/Biometrics/`. Partials in a ViewModel are still fine and idiomatic.
  - Method bodies **%d lines** (target 10) and **max %d parameters**, WinTeam.Mobile.Core/ only.
    Platform view methods are exempt from both by design.
  - The two parameter fixes are different, and getting them backwards is the common mistake:
    collaborators (managers, services, other view models) become `[Inject]` properties; data that
    travels together becomes a `record` or `readonly record struct`.
  - Every method gets a `///` block — summary, one `<param>` each, `<returns>` when non-void. A `//`
    comment never narrates the body: if a line needs explaining, the name is wrong or the block
    wants extracting. Budget for the doc comments when you budget the lines.
  - Layer order is View -> ViewModel -> Manager -> Proxy/DbProxy, no skipping and no reaching back.
    An operation coordinating more than one Manager belongs in UseCases/.
  - Planning a new helper — formatting, parsing, validating, converting? Plan the search first:
    MobileCore is a submodule that `git grep` from the repo root does not see.""" % (
        core, core - CORE_TOLERANCE, CORE_TOLERANCE, ios, android, max_body, max_params,
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    # Gate 1. Absent field, "auto", "default", "acceptEdits" — anything but plan mode is silence.
    # Verified against a live 2.1.259 payload: the key is snake_case `permission_mode`, and
    # `permissionMode` does not appear. Both are accepted anyway, because a hook whose whole
    # trigger is one field name should not go quiet on a rename.
    mode = payload.get("permission_mode") or payload.get("permissionMode")
    if mode != "plan":
        return 0

    # Gate 1b. ExitPlanMode is the one tool name worth naming, and it is not a walk-back of the
    # no-matcher decision above: this is the *boundary* of the episode the card is scoped to, not a
    # guess about which tools a plan reaches for, so it cannot go stale when a new MCP server appears.
    # Two reasons to stand down here. The card is advice for composing a plan, and at ExitPlanMode the
    # plan is already written, so it would arrive as pure tokens. More importantly plan_handoff_brief.py
    # matches this same call and removes the stamp read below; hooks for one event run in parallel, so
    # without this gate the two race. If the removal landed first this hook would re-emit the card at
    # hand-off *and* re-create the stamp, and the next planning episode in the session would get no card —
    # destroying exactly the pairing the fourth scoping decision in the module docstring relies on.
    if payload.get("tool_name") == "ExitPlanMode":
        return 0

    # Gate 2. One card per plan-mode episode. Imported here rather than at module scope: the
    # no-op path above runs on every tool call and has no business paying for it.
    import sweep_tool_writes

    stamp = sweep_tool_writes.stamp_path(payload.get("session_id"), suffix=STAMP_SUFFIX)
    if stamp is None or os.path.exists(stamp):
        return 0

    # load_thresholds() overlays thresholds.json onto check_cs_edit's module globals and returns
    # nothing, so the values are read off the module afterwards rather than from a return value.
    import check_cs_edit
    check_cs_edit.load_thresholds()

    # Rendered before the stamp is written, not after. The stamp's promise is "this episode has had its
    # card", so anything that can fail must fail before the promise is recorded — otherwise a raised
    # exception in card() leaves the stamp set and the episode silently loses the brief for good.
    context = card(check_cs_edit.FILE_CAPS, check_cs_edit.MAX_BODY_LINES, check_cs_edit.MAX_PARAMS)

    try:
        sweep_tool_writes.write_stamp(stamp, 1)
    except Exception:
        return 0

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": context,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
