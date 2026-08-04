---
description: Drive the TimeClock parity loop — audit, characterization tests, fixes, re-audit. Reports before changing anything
allowed-tools: Agent, Task, Skill, Read, Grep, Glob, Bash, Write, Edit
argument-hint: "[feature area, file, class, symptom, or free-form description — defaults to all]"
disable-model-invocation: true
---

Verify that the MOB-13653 refactor preserved behaviour for one area, and close the loop on what it did not.

Scope: `$ARGUMENTS` (default `all`).

This is the runner for the loop documented at `docs/architecture/timeclock/parity-and-testing.md:52-68`.
That file owns the loop's *rationale*; this file owns its *execution*. Where they disagree, fix one of them —
do not carry a second opinion.

## What this command owns, and what it must never restate

It owns **sequencing, gates and state**. It owns **no domain procedure**.

The seven parity checks, the baseline derivation and the verdict contract live in
`timeclock-refactor/agents/refactor-parity-auditor.md`. The extraction rules live in the six skills. This file
reaches both by dispatch and copies neither. That is not stylistic: this file used to carry a second copy of
the agent's checks, the same baseline commands and the same verdict contract, and **the two copies drifted**.
One copy now.

So: **do not work the checks yourself.** Dispatch, then act on what comes back.

> **If dispatching fails, check the tool name before anything else.** `allowed-tools` above names **both**
> `Agent` and `Task` — the subagent-dispatch tool and its previous name. Only one of them exists in any given
> Claude Code version, and granting a name that does not exist costs nothing, whereas granting only the wrong
> one costs this command its central capability. If the tool is renamed *again*, this file silently loses that
> capability and the failure looks like the agent being missing rather than the grant being wrong. Add the new
> name to `allowed-tools`; do not go looking at the agent.

## The argument is free-form — pass it through verbatim

`$ARGUMENTS` does **not** have to be one of the eight areas. A class name, a file path, a symptom
(*"the banner shows a stale punch type after clock-in"*), or nothing at all are all valid.

**Do not classify it yourself.** The agent owns the mapping from a symptom to a feature area, and it reports
which area it picked. A second classifier here is a second thing to drift, and it would silently narrow an
audit the user meant broadly. Pass the string through untouched and let the agent map it.

The eight areas, for reference only — not a validation list:
`punch-lifecycle` · `punch-input` · `punch-rejection` · `punch-photo` · `team-time-messages` ·
`geo-location` · `status-display` · `kiosk-overrides`

## Phase 0 — Preflight

Read-only. **Stop on any failure.** A wrong baseline does not fail loudly, it manufactures findings — and
sends someone re-reading 2000 lines of deleted code for a regression that never happened.

```bash
git fetch origin dev                                          # unconditional; a stale ref moves the merge base
BASE=$(git merge-base HEAD origin/dev)
REFACTOR=$(git log HEAD --grep="TimeclockVM improvements" --format=%h -1)
echo "BASE=$BASE  REFACTOR=$REFACTOR"

# The ref-selection test. It compares the repo against itself — no recorded figure participates.
git rev-parse --short "$REFACTOR^"                            # must equal $BASE: the refactor is the only commit
git show --numstat "$REFACTOR" | awk '$3 ~ /Punches\/TimeClockViewModel/ {printf "+%s -%s %s\n",$1,$2,$3}'

for P in WinTeam.Mobile.Core/ViewModels/TimeLanding/Punches/TimeClockViewModel.cs \
         WinTeam.Mobile.Core/ViewModels/TimeLanding/Punches/TimeClockViewModel.TeamTimeMessage.cs; do
  echo "$P  base=$(git show "$BASE":"$P" | awk 'END{print NR}')  master=$(git show master:"$P" | awk 'END{print NR}')"
done
```

**The test is an equality between two things you just derived, and it must hold on all three lines:**

> The refactor is the only commit on this branch, so `$BASE` is `HEAD`'s parent. Both files are **pure
> deletions** in `$REFACTOR` — `0` insertions — so the deletion counts *are* the baseline file lengths.
> `git show "$BASE":<path> | awk 'END{print NR}'` must reproduce them, and `master` must not.

So: `$REFACTOR^` equals `$BASE`; insertions are `0` for both files; and `base=` equals each file's deletion
count while `master=` does not. **If all three hold, your ref is right and you are done here** — there is
nothing to compare against and nothing to record.

**No expected figure is written down anywhere, deliberately.** One used to be recorded elsewhere in this
plugin, and it was wrong four times: corrected twice, once asserted to be a value it had never been, and stale
by 15 lines when last checked against a real derivation. The lengths move whenever
the branch is rebased onto a dev commit touching either file, so any recorded pair decays on a schedule nobody
controls — while the equality above re-establishes itself on every run and cannot go stale. A `shortstat`
check was retired for the same reason after drifting three passes running.

**If the equality fails, stop and say so.** That is a genuinely wrong ref, and it manufactures findings.

If `$REFACTOR` is empty or the grep matches more than one commit, **ask which commit is the refactor.** Do not
fall back to `master...HEAD` or `$BASE...HEAD` — a range against the branch tip mixes the refactor with
everything committed after it.

Then confirm the suite is green *before* you start, so a later red is attributable:

```bash
dotnet test WinTeam.Mobile.Core.Tests/WinTeam.Mobile.Core.Tests.csproj
```

## Phase 1 — Audit

Dispatch **`refactor-parity-auditor`**. Pass the scope and nothing it can derive on its own:

> Audit TimeClock behaviour parity for: `$ARGUMENTS` (default `all` if empty). Establish the baseline as your
> own instructions describe — the merge base against dev, and the refactor commit — both derived, neither
> hardcoded, and not from `master`. Report per-area verdicts, and for each Regression give the baseline
> `path:line` **range** at `$BASE` so the hunk can be pulled without reading the whole original.

### Dispatch mechanics — this is where the command silently produces nothing

- **Dispatch synchronously: pass `run_in_background: false`.** Subagents default to the background, and a
  backgrounded dispatch lets this turn end the moment the agent is launched — the agent then finishes into a
  notification and phases 2-4 never happen. The run looks successful and the user sees no findings at all.
- **Phases 1 → 4 are one turn.** Do not end the turn between them. The only stop in this command is the
  approval gate at the end of Phase 4.
- **The agent's report is never shown to the user — only your own output is.** Whatever you do not re-print
  under the Phase 4 template is lost, however complete the agent's report was. Writing "the auditor found
  three issues" and stopping is the exact failure this note exists to prevent.

**Never name a commit hash or a baseline branch here.** The agent derives both itself, and those derivations
are deliberately in one place: this branch is rebased, so a hash pinned in two files is a hash that goes stale
in one of them. **In particular, never tell it to read the original from `master`** — local `master` drifts
from the merge base in both directions, and the agent's baseline section carries the arithmetic showing how
that manufactures phantom regressions.

## Phase 2 — Triage

Bucket the report into the three verdicts the agent already emits: **Regression**, **Changed deliberately**,
**Preserved**. Do not re-derive them and do not re-judge them — if a verdict looks wrong, say so in the report
rather than silently reclassifying it.

## Phase 3 — Constructibility probe

**Read-only. Write nothing here.** For each type a finding touches, decide whether a test could construct it
today: read its `[Inject]` block and compare each type against the registrations in
`WinTeam.Mobile.Core.Tests/Infrastructure/TimeClockTestFixture.cs`.

```bash
grep -n "\[Inject\]" -A2 <the file the finding touches> | grep "public"
grep -n "container.Register" WinTeam.Mobile.Core.Tests/Infrastructure/TimeClockTestFixture.cs
```

**This is the safety rule that makes the loop trustworthy.** TinyIoC *rethrows* when an `[Inject]` type cannot
resolve, so an unregistered dependency means the constructor throws — and a test that dies in its constructor
is **red**, which is exactly this loop's signal that a regression reproduced. Without this probe the command
reports missing DI registrations as parity failures.

So: a subject that will not construct is a **fixture gap**, not a regression. Report it under `BLOCKED`, write
no test for it, and never let it reach `WILL FIX`.

**No list of known gaps is kept here.** One used to be, and every entry in it was registered by the time
anyone checked — a second copy of the fixture's contents that could only ever go stale, and that would have
sent an area to `BLOCKED` for a dependency that has a double. Read the fixture; it is the only truthful
source, and the grep above is the whole procedure.

**The `container.Register` grep is necessary but not sufficient, because the trap has changed shape.** Several
concrete types are registered through `RuntimeHelpers.GetUninitializedObject` — look for `Uninitialised<…>` in
the fixture. Those **construct**, so the old symptom is gone; but their constructors never ran, so **every
member throws `NullReferenceException`** the moment it is touched. A subject that resolves and then dies on
first use is still a fixture gap, and still belongs under `BLOCKED` — it just fails later and with a message
that points at the wrong thing. The fixture's own XML docs say which types these are and why, and
`docs/architecture/timeclock/parity-and-testing.md` records what would be needed to build them for real.

## Phase 4 — Report, and stop

Relay all four sections in full from the agent's report — **verbatim** wherever it already gave the required
shape — then **end the turn and wait.** This is the command's only user-visible output; a summary of it is a
lost report. At this point `git status` is clean.

```
FINDINGS  —  <area the agent picked>

  REGRESSION  F1  <one line>
    on dev      <path>:<line range>  (at $BASE)   <how the flow behaves there>
    on branch   <path>:<line>                     <how the flow behaves now>
    difference  <the structural cause>
    symptom     <what a user would see — per platform if they differ>

  CHANGED DELIBERATELY  F2  <one line>
    on dev      <path>:<line range>  (at $BASE)   <how the flow behaves there>
    on branch   <path>:<line>                     <how the flow behaves now>
    difference  <the structural cause>
    confirm?    intended, or an accident of the extraction?

  PRESERVED   <named, one line>

WILL WRITE                                                          covers
  WinTeam.Mobile.Core.Tests/ViewModels/TimeLanding/Punches/
    TimeClock/<Type>Tests.cs                          (new, ~N ln)   F1

WILL FIX
  <production path>            <owning skill>          <what changes>   F1

BLOCKED
  <finding>   <why no test is possible yet>

Nothing above has been created. Approve, or tell me what to drop.
```

Rules for the report:

- The template above is **layout only.** What belongs in `on dev` / `on branch` / `difference`, and the rule
  that findings touching activation or messaging must state behaviour per platform, are defined once in the
  agent's `## Output` section. **Do not restate them here** — that is the drift this file exists to avoid.
- Every **Regression** in full, with **both** the dev and the current `path:line`. Every **Changed
  deliberately** — these need the user's confirmation and cannot be dropped. **Preserved** collapses to one
  line naming the areas.
- Every `WILL WRITE` / `WILL FIX` row maps to a finding ID. **A row covering no finding, or a finding with no
  row, is itself worth flagging** — that is the point of the mapping.
- Relay the agent's closing note on what could not be determined by reading, and what needs a device.
- State plainly how much automated coverage the area actually has. Until an area shows tests in
  `docs/architecture/timeclock/parity-and-testing.md`, the honest answer is none, and device verification
  remains the only real proof. **Do not let a clean parity report read as more than a careful reading.**

**The gate is conversational.** Phases 5-6 resume on the user's reply, so approval is per-finding — they may
approve F1, defer F2, and you proceed with only what was approved.

## Phase 5 — Change (only after approval)

**The only phase that writes.** Create exactly the files listed under `WILL WRITE`; apply exactly the approved
`WILL FIX` rows. **If you find you need a file the report did not name, stop and re-report** rather than
widening scope silently.

Fixes go through the owning skill — invoke it, do not reimplement it:

| Finding shape | Skill |
|---|---|
| Child view model wiring, activation, teardown | `timeclock-refactor:extract-child-view-model` |
| A bound property or command that moved | `timeclock-refactor:moving-bound-properties` |
| Behaviour that needs a kiosk counterpart | `timeclock-refactor:kiosk-variant-pairing` |
| Two components need to talk; a request message returns null or throws | `timeclock-refactor:vm-communication-channel` |
| A message with a responder and no sender | `timeclock-refactor:retiring-orphan-messages` |
| An ordered pipeline moving out of the orchestrator | `timeclock-refactor:extracting-orchestrator-pipelines` |

**Where a skill and this file disagree, the skill wins.**

Writing the tests:

- **Assert against the baseline, not against current behaviour.** Derive expected values with
  `git show "$BASE":<path>`. A test written from the current code documents the bug.
- **Never `git show` a whole baseline file.** The baseline orchestrator alone is ~2200 lines. Pull only the
  hunk the agent cited: `git show "$BASE":<path> | sed -n 'A,Bp'`.
- Mirror the production folder under `WinTeam.Mobile.Core.Tests/`, named `<Type>Tests.cs`, namespace mirroring
  the folder. Every file inherits `TimeClockTestFixture`.
- Set **`IsActive = true`** on any `IRecipient<T>` subject and register the responders the code under test
  sends to. The fixture resets both messengers, so an inactive child receives nothing and a request message
  returns `default` — the test then passes having proven nothing.
- Conventions: `Given<Condition>_<Expected>`, literal `// Arrange` / `// Act` / `// Assert`, Moq with the
  lambda parameter named `a`, FluentAssertions only.

## Phase 6 — Re-verify

1. `dotnet test …` — each test written for a regression must go **red → green**. Show the real output. A test
   that was green before the fix did not test the regression.
2. Re-dispatch `refactor-parity-auditor` for the same scope.
3. **The run-2 diff rule.** Findings in run 2 that were absent in run 1 are **new backlog items, not
   fix-induced regressions** — unless they touch a file phase 5 modified, in which case treat them as caused
   by the fix and say so. Two passes over a prose correspondence task do not produce identical sets, and the
   agent is told to assume it missed where behaviour moved, which makes false negatives likely by design.
   **Without this rule the loop does not terminate.**
4. Update the status table in `docs/architecture/timeclock/parity-and-testing.md`: the verdict, the test
   files, every deliberate change with its rationale, and anything only a device can confirm.

## What this command cannot do

**It cannot run `/timeclock-refactor:vm-message-audit`** — a command cannot invoke another command, the same
limit the agent has. So for message-wiring findings, either fold in a run the user has already done, or derive
it inline with the grep block in the agent's own message-wiring section. **Do not imply the full sweep ran
when it did not.**
