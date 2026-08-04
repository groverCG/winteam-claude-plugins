---
name: extracting-orchestrator-pipelines
description: >-
  Use when moving the punch-send pipeline or another ordered flow out of TimeClockViewModel, where several
  TimeClock children read and write the same request state.
---

> Applies to the MOB-13653 refactor branch. On `master` the types below do not exist yet.

# Extracting a multi-step flow out of the orchestrator

Iteration 1 pulled out *features* — photo capture, punch input, rejection handling. What remains in
`TimeClockViewModel` is a **pipeline**: one ordered sequence that reads and writes several siblings as it goes.
That is a different extraction shape, and the feature recipe in `timeclock-refactor:extract-child-view-model`
does not cover the hard part.

The hard part is that **the ordering is currently implicit in one method body, and after extraction it becomes
implicit in construction and activation order instead** — where nothing enforces it and nothing fails at build
time.

## The remaining pipeline

`WinTeam.Mobile.Core/ViewModels/TimeLanding/Punches/TimeClock/TimeClockViewModel.cs`, roughly lines 411-621,
about 210 lines and the largest cohesive block left. Line 622 (`RefreshButtonsTextsAndVisibility`) belongs to
the suggested-action block, which is a separate candidate:

In call order — **line anchors deliberately omitted, because they move.** Grep the member names below for
their current positions; a number written here would be wrong within a commit or two:

| Member | Note |
|---|---|
| `SendTimePunchAsync` | `protected virtual` — the kiosk subclass overrides it |
| `ResumePunchSendAsync` | re-entry after a rejection or permission prompt |
| `PreparePunchAsync` | |
| `SendPunchRequestAsync` | ~45 lines |
| `HandlePunchRequestAndSendAsync` | ~44 lines |
| `SetupLatestPunchRequest` | |
| `SetupLatestPunchInformation` | |
| `GetNumericJobNumber` | |
| `HandleResponseAsync` | ~48 lines, longest in the file |

## When to use

Before moving any of the above, or any similarly ordered sequence. Also when you notice a method reading three
or more siblings to assemble one request.

## When NOT to use

- Extracting a self-contained feature with its own state — that is
  `timeclock-refactor:extract-child-view-model`.
- Moving a single method with no ordering relationship to its neighbours.
- The suggested-action/menu block or the Team-Time deferral logic, which are cohesive *feature* extractions
  rather than pipelines.
- Anything on `master`.

## The coupling to cut

Two things keep this block in the orchestrator. Both must be addressed, or the extraction just moves the
problem.

**1. Eight direct reads and writes of a sibling's mutable request object.** `PendingPunchesViewModel.LatestPunchRequest`
is touched at lines 448, 484, 506, 511, 531, 534, 535 and 545 — including in-place mutation of a nested
property. Two owners writing one object is the defect; extracting without fixing it produces three.

The fix is the `RejectionContext` pattern already proven here: build an immutable snapshot once, pass it
through, and give the pipeline **one** place that writes back.

```csharp
public readonly record struct PunchSendContext(
    TimeClockPunchRequest Request,
    PunchType PunchType,
    string JobNumber,
    GeoCoordinate Coordinate);
```

**Note the trap `RejectionContext` already has:** a record struct is a shallow snapshot. If a caller mutates an
object reachable *through* it — as the kiosk path does with `GeoCoordinate` — every holder sees the change and
the immutability is illusory. Either make the carried members value types, or state explicitly which member is
still shared.

**2. The `CanUseUi` semaphore.** Declared at line 102 and released via `SafeUseUiReleaseSemaphore` at 688,
waited on at **four** sites: 256, 682 and 715 via `WaitAsync()`, and 645 via the blocking `Wait()`. That
blocking one is its own hazard — check it before you move anything. A pipeline that acquires the semaphore must
release it on every path including exceptions.
**Do not give the new child its own semaphore** — two uncoordinated semaphores around one flow is exactly how
the punch screen deadlocks. Either leave the semaphore owned by the orchestrator and have it wrap the call, or
move it wholesale. Never both.

## Steps

1. **Write the current order down first**, as a numbered list from `SendTimePunchAsync` through
   `HandleResponseAsync`, including every early return and guard. This list is the specification for the
   extraction and the checklist for verifying it afterwards. Do not skip this.
2. **Define the context record** for what flows through, and decide where it is built. One construction site.
3. **Decide who owns the semaphore** — orchestrator or child, not both.
4. **Create the coordinator**, following `timeclock-refactor:extract-child-view-model` for base class,
   construction site, activation and teardown.
5. **Keep `SendTimePunchAsync` `protected virtual` on the orchestrator** as a thin delegating method, or move
   the virtual hook deliberately. The kiosk subclass overrides it; changing that signature silently changes
   which implementation runs. Check `timeclock-refactor:kiosk-variant-pairing`.
6. **Re-point the writes** so exactly one place assigns the request object.
7. **Check bound properties** before finishing — invoke `timeclock-refactor:moving-bound-properties`. Four
   platform files bind this ViewModel's flattened surface.
8. **Re-run the numbered list from step 1** against the new code, in order.

## Verify

- The step-1 ordering list is reproduced exactly: same sequence, same guards, same early returns.
- Exactly one place assigns `LatestPunchRequest`; the other seven accesses read a context or a property.
- One semaphore, released on every path including exceptions.
- Ask the user to run `/timeclock-refactor:vm-message-audit` (no new orphan or dead letter) and
  `/timeclock-refactor:parity-check punch-lifecycle`. Neither can be invoked from inside a skill.
- `dotnet build` on Core plus both platform csprojs, then **punch on device** — normal punch, rejected punch,
  and a resumed punch after a permission prompt. Ordering and activation defects do not appear at build time.
