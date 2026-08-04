---
description: Rank the remaining TimeClock extraction candidates by payoff and risk, and recommend the next one
allowed-tools: Bash, Read, Grep, Glob
argument-hint: "[optional: a candidate name to assess in depth instead of ranking all]"
disable-model-invocation: true
---

Decide what to extract next from the TimeClock feature, and say why that one rather than the largest one.

Argument: `$1` — empty to rank everything, or a candidate name for a deep assessment of just that one.

## Iteration 1 changed the question

The orchestrator went from roughly 2000 lines to around 700, and the regions are almost gone. **Size is no
longer the useful signal** — what remains is long methods and orchestrator-owned state that several siblings
reach into. Ranking by line count would now recommend the wrong work. (No count is recorded anywhere;
derive what you need, as below.)

Rank by **coupling removed per unit of risk**, not by lines moved.

## The candidates

**Refresh these before ranking — do not rank from the table.** Every line number below is a hint that was true
once; the branch is rebased and each extraction moves them. Derive the current shape first:

```bash
D=WinTeam.Mobile.Core/ViewModels/TimeLanding/Punches/TimeClock
K=WinTeam.Mobile.Core/ViewModels/Kiosk/KioskTimeClockViewModel.cs

# Sizes. awk, not `wc -l` — `wc -l` counts newlines and under-reports any file
# whose last line has none, which is most of Core.
for F in $D/TimeClockViewModel.cs $D/TimeClockViewModel.Messages.cs $K; do
  echo "$F $(awk 'END{print NR}' "$F")"
done

grep -l WTBaseObservableRecipient $D/*.cs | wc -l              # child view models
grep -c "WeakReferenceMessenger.Default.Register"   $D/TimeClockViewModel.Messages.cs
grep -c "WeakReferenceMessenger.Default.Unregister" $D/TimeClockViewModel.Messages.cs
```

Then re-anchor each candidate you are actually considering by grepping its member *names* — the names are
stable, the numbers are not:

```bash
grep -nE "SendTimePunchAsync|ResumePunchSendAsync|PreparePunchAsync" $D/TimeClockViewModel.cs
```

**Report the derived figures, not the ones in this table**, and say which candidates you re-anchored. A table
row that no longer matches source is a stale row, never a finding.

| Candidate | Where | Shape |
|---|---|---|
| **Punch-send pipeline** | `TimeClockViewModel.cs` 411-621, ~210 lines (622 is `RefreshButtonsTextsAndVisibility`, which belongs to the next row) | Ordered pipeline; 8 direct `LatestPunchRequest` accesses; shares the `CanUseUi` semaphore. See `timeclock-refactor:extracting-orchestrator-pipelines` |
| **Suggested-action / menu block** | `ShouldShowPlusMoreButton` 287, `GetCurrentPunchType` 344, `ShowPunchOptionsMenu` 352 (virtual), `RunPrimarySuggestedAction` 363, `RunSecondarySuggestedAction` 386, `RefreshButtonsTextsAndVisibility` 622, `ShowShiftCompleteAlertIfNeeded` 630, `ShowInformationActionSheetAsync` 701 | Reads 4 siblings; a feature extraction, not a pipeline |
| **Team-Time deferral** | `TeamTimeMessagesViewModelOnOnCompleteDisplayMessages` 216, `ResumeDeferredTeamTimeMessages` 235, `ProcessTeamTimeMessagesAsync` 244, `FetchTeamTimeMessagesUnlessLocationPendingAsync` 328 | Reaches into two siblings' flags |
| **Manual message handlers** | `TimeClockViewModel.Messages.cs`, registrations near the top of the file | Each exists because the orchestrator answers for state it still owns; retires one per extraction. **Count the `Register`/`Unregister` pair above** — it is symmetric today, and keeping it symmetric is the constraint |
| **Seven orphan messages** | `docs/architecture/timeclock/messages.md#4-seven-orphans` | Lowest risk, genuinely small. See `timeclock-refactor:retiring-orphan-messages` |
| **Kiosk timeout/session** | `KioskTimeClockViewModel.cs`: `PublishTimeoutEvent` 341, `RestartInactivityMonitor` 355, `DoKioskLogout` 361, `CompletePunchActionAsync` 375, `SendPendingCallLogs` 401, `AttachTimeoutCoordinator` 412, `BuildTimeoutConfirmationParameter` 430, `ResolveTimeoutSeconds` 451 | Grew during Iteration 1; separable concern |
| **Two un-collapsed use cases** | `UseCases/TimeClock/LoadTimeClockDataUseCase.cs` (6 params), `HandlePunchRejectionUseCase.cs` (6 params / 5 child VMs) | Both violate the 3-parameter limit; `BuildRejectionContextUseCase` shows the target shape |

## Assess each on

```bash
V=WinTeam.Mobile.Core/ViewModels/TimeLanding/Punches/TimeClock/TimeClockViewModel.cs
awk 'END{print FILENAME": "NR}' $V
awk 'END{print FILENAME": "NR}' WinTeam.Mobile.Core/ViewModels/Kiosk/KioskTimeClockViewModel.cs

# Does the candidate touch bound members? This dominates risk.
grep -rn "<MemberName>" WinTeam.Mobile.iOS WinTeam.Mobile.Android --include="*.cs"

# Is there a virtual the kiosk overrides? Also dominates risk.
grep -n "protected virtual\|public virtual" $V
grep -n "override" WinTeam.Mobile.Core/ViewModels/Kiosk/KioskTimeClockViewModel.cs
```

Four factors, in descending weight:

1. **Coupling removed.** How many cross-sibling reads and manual message handlers disappear. This is the payoff.
2. **Bound-property exposure.** Does any moved member appear in the four platform files? These bindings fail
   silently, so this is the largest risk multiplier. See `timeclock-refactor:moving-bound-properties`.
3. **Kiosk entanglement.** Does it cross a `protected virtual` the kiosk subclass overrides?
4. **Ordering sensitivity.** Is it a sequence whose order becomes implicit after extraction?

Explicitly **reject line count as a ranking factor** and say so in the output. The largest block is not
automatically the right next move.

## Report

1. **Ranked list**, best first. For each: coupling removed, risk factors present, rough size, and the skill to
   invoke.
2. **The recommendation**, with the reason it beats the runner-up. One recommendation, not three.
3. **What to do first if the goal is a safe win** rather than the biggest one — usually the orphan messages or a
   use-case parameter collapse, both of which touch no bound members.
4. **Blocked candidates** — anything that should wait, and what it is waiting on.

## Rules

- **Report only. Change no code.** This command recommends; it does not refactor.
- Verify line numbers against source before citing them. Stale anchors are worse than none.
- If two candidates are genuinely close, say so rather than manufacturing a distinction.
