---
name: retiring-orphan-messages
description: >-
  Use when retiring one of the seven orphan messages under Messages/TimeLanding/, or when a message type there
  has a registered responder and no sender.
---

> Applies to the MOB-13653 refactor branch. On `master` the types below do not exist yet.

# Retiring a message that has a responder and no sender

Seven message types in `WinTeam.Mobile.Core/Messages/TimeLanding/` have a registered responder and **zero
senders**. Each exists because someone added a message to decouple two components, next to the direct property
access it was meant to replace — and then the direct access stayed. The result is two routes for one fact, one
of them dead.

**The dead half is not the problem. The live direct access is.** Deleting the message alone tidies the file tree
and changes nothing about the coupling. That is why this skill exists as a pair of choices rather than a delete
instruction.

The catalog with the full table is `docs/architecture/timeclock/messages.md#4-seven-orphans`.

## The current orphans

Named here because the names are what you act on. **The list, not the count, is what this heading is for** —
run `/timeclock-refactor:vm-message-audit` for the live set, and treat a name below that no longer comes back
as already retired rather than as a discrepancy.

- `GpsPermissionsRequestMessage`
- `LatestPunchRequestRequestMessage`
- `OldestPendingPunchRequestMessage`
- `RefreshPendingPunchesSectionRequestMessage`
- `CurrentRejectedPunchTypeMessage`
- `PrevRejectedPunchMessage`
- `PrevRejectedMessageMessage`

## When to use

When working any of the seven, or when `/timeclock-refactor:vm-message-audit` reports a new orphan.

## When NOT to use

- **Dead letters** — a sender with no recipient. That is the opposite defect and usually means a missing
  registration, not a deletable message. Do not delete a message because nothing handles it; find out why
  nothing handles it.
- Messages handled only under a condition. `InitInactivityMonitorMessage` is handled only by
  `KioskTimeClockViewModel`, which is correct, not an orphan.
- Adding a new message — that is `timeclock-refactor:vm-communication-channel`, whose rule 5 is what prevents
  creating an eighth orphan.

## Confirm it is actually an orphan first

A file count is not evidence. Every one of the seven appears in **two to five files** — its own definition, its
responder, and often a partial-class registration list. None of that is a sender.

```bash
# Both send forms — the generic form has no `new`, so checking one pattern gives false positives
grep -rn "new <Name>(" WinTeam.Mobile.Core WinTeam.Mobile.iOS WinTeam.Mobile.Android MobileCore --include="*.cs"
grep -rn "Send<<Name>>" WinTeam.Mobile.Core WinTeam.Mobile.iOS WinTeam.Mobile.Android MobileCore --include="*.cs"
```

Search **all four projects.** Messages are sent from platform view code and from Managers, not only from view
models. A "confirmed orphan" that a fragment actually sends is a regression waiting to happen.

## Then find the live route

For each orphan, locate the direct access that replaced it — usually a sibling property with the same meaning
as the message's payload. That direct access is the actionable half, and it is what you are deciding about.

## Pick one, and do it in a single change

**Option A — cut the direct access, keep the message.** Correct when the two components genuinely should not
hold references to each other. The responder already exists, so the work is replacing the direct read with a
`Send`.

Watch the two hazards `vm-communication-channel` documents: send with `.Send(new T()).Response` rather than
`Send<T>()`, and confirm there is exactly **one** responder — a class with a `Kiosk*` subclass can have two live
instances, and a second `Reply()` throws `InvalidOperationException`.

**Option B — delete the message and its responder, keep the direct access.** Correct when the owner legitimately
holds the reference. Most of the seven fall here: the parent orchestrator constructs and holds every child, so a
message to read a child's property is pure indirection.

Delete the message record **and** the responder registration and handler. Leaving the handler behind creates a
dead letter — the opposite defect.

**Never do neither, and never do both.** Deleting the message while leaving the direct access untouched is the
change that created these seven in the first place.

## Rules

1. **One message per change.** Seven messages is seven reviewable changes, not one sweep.
2. **Confirm zero senders across all four projects** before deleting anything.
3. **If deleting, remove the handler and the registration too**, not just the record.
4. **Update the catalog** at `docs/architecture/timeclock/messages.md` too, since it *describes* the
   message you retired. **No count needs updating anywhere** — nothing records one, and
   `/timeclock-refactor:vm-message-audit` re-derives the orphan set on every run.

## Verify

- Ask the user to run `/timeclock-refactor:vm-message-audit` and confirm one fewer orphan and **no new dead
  letter**. It cannot be invoked from inside a skill.
- The catalog no longer describes the retired message.
- For option A: exactly one responder, and the send uses `.Response`.
- For option B: no reference anywhere to the deleted type — `grep` all four projects.
- `dotnet build` on Core and both platform csprojs, then exercise the feature. A missing responder compiles
  cleanly and returns a default value, so the build proves nothing here.
