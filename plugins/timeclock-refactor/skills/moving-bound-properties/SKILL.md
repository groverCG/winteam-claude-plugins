---
name: moving-bound-properties
description: >-
  Use when about to move, rename or remove a property or command on TimeClockViewModel or
  KioskTimeClockViewModel that the iOS or Android view binds to.
---

> Applies to the MOB-13653 refactor branch. On `master` the types below do not exist yet.

# Moving a property the views bind to

**Iteration 1 never touched the view layer.** The orchestrator was split into 12 children, but the four platform
files still bind against its flattened surface. Every property they read is still expected to be on
`TimeClockViewModel` itself.

**The binding DSL resolves member names through expression parsing, not compile-time member access on a
concrete type.** So moving a bound property to a child does not fail to build — the binding simply stops
updating, and the control silently shows a stale or empty value. This is the single most likely way an otherwise
correct extraction ships a visible bug.

## The four files that bind this ViewModel

| File | Lines |
|---|---|
| `WinTeam.Mobile.Android/Views/Fragments/Dashboard/TimeClockKioskFragment.cs` | 434 |
| `WinTeam.Mobile.Android/Views/Fragments/TimeLanding/Punches/TimeClockFragment.cs` | 430 |
| `WinTeam.Mobile.iOS/Views/ViewControllers/TimeLanding/Punches/TimeClockView.cs` | 361 |
| `WinTeam.Mobile.iOS/Views/ViewControllers/Dashboard/KioskTimeClockView.cs` | 354 |

Both platforms must be handled together. Fixing only one is worse than fixing neither, because the divergence
then hides behind "it works on my device".

## When to use

Before the move, not after. Fires when you are about to move, rename, or delete a **public** property, command,
or observable member on `TimeClockViewModel` or `KioskTimeClockViewModel` — including as a side effect of an
extraction.

## When NOT to use

- Private or protected members, which no view can bind.
- Adding a new member. Nothing binds it yet.
- Members on child view models that no view has ever bound.
- Non-TimeClock screens, though the same hazard applies wherever a bound member moves.

## Steps

1. **Establish whether it is bound at all.** Search both platform projects for the member name before assuming.

   ```bash
   grep -rn "MemberName" WinTeam.Mobile.iOS WinTeam.Mobile.Android --include="*.cs"
   ```

   Search the plain name, not `vm.MemberName` — bindings reference it inside a lambda and the receiver may be
   named anything. If there are no hits in either project, this skill does not apply and you can move freely.

2. **Choose re-expose or re-point.**

   - **Re-expose** — keep a pass-through on the orchestrator delegating to the child. Views are untouched.
     Cheapest and lowest risk, and correct when the orchestrator legitimately remains the view's single
     binding surface.

     ```csharp
     public string DisplayValue => _childViewModel.DisplayValue;
     ```

     **A pass-through computed property does not raise its own change notification.** The child raising
     `PropertyChanged` for its own member does not notify anything watching the parent's. Forward it, or the
     binding resolves once at bind time and never updates again — which looks exactly like the bug you were
     avoiding.

   - **Re-point** — change the binding to reach the child. Correct when the child is genuinely the owner and
     you want the coupling visible. Requires editing all four files and exposing the child as a public
     property.

3. **If re-exposing, forward the notification.** Subscribe to the child's `PropertyChanged` and re-raise for the
   parent's member name — and pair that subscription with a teardown, per
   `winteam-standards:tearing-down-subscriptions`.

4. **Handle the kiosk pair.** Kiosk views bind `KioskTimeClockViewModel`, which inherits from the orchestrator.
   A member moved off the base disappears from the kiosk surface too. See
   `timeclock-refactor:kiosk-variant-pairing`.

5. **Grep for the old name across both platform projects** and confirm zero remaining references to something
   that no longer resolves.

## Commands are the same hazard

A command bound to a control follows identical rules. An unresolvable command binding produces a control that
does nothing when tapped — no exception, no log. Worse than a stale label, because it looks like the feature is
merely slow.

## Verify

- `grep` for the old member name in both platform projects returns nothing, or only intended references.
- Every re-exposed pass-through forwards change notification, and the forwarding subscription has a teardown.
- `dotnet build` on Core and **both** platform csprojs.
- **Open the screen on both platforms and change the value.** A build cannot detect an unresolved binding — the
  only proof is watching the control update. For a command, tap it and confirm it fires.
