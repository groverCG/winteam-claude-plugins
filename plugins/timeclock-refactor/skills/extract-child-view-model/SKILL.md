---
name: extract-child-view-model
description: >-
  Use when splitting TimeClockViewModel or KioskTimeClockViewModel, or when adding a feature to a child view
  model under ViewModels/TimeLanding/Punches/TimeClock/ or ViewModels/Kiosk/.
---

> Applies to the MOB-13653 refactor branch. On `master` the types below do not exist yet.

# Extracting a child view model

Reference implementation: the 12 children under
`WinTeam.Mobile.Core/ViewModels/TimeLanding/Punches/TimeClock/`, mapped in
`docs/architecture/timeclock/README.md`. They are the only 12 users of `WTBaseObservableRecipient`.

## When to use

- You are adding to `TimeClockViewModel` or `KioskTimeClockViewModel` — both already well over the Core cap — or
  to a child under `ViewModels/TimeLanding/Punches/TimeClock/` or `ViewModels/Kiosk/`.
- You are asked to split, refactor, or decompose one of those.
- You are about to add a fourth-or-later responsibility to one.
- You catch yourself passing three or more view models as arguments to a single method.

**The wiring below is TimeClock-specific**, not general advice for any large ViewModel. All three of its moving
parts are used by nothing outside the TimeClock tree, but they do not cover the same set — do not assume one
count for all three:

- `WTBaseObservableRecipient` is derived by the 12 children — confirm with
  `grep -l WTBaseObservableRecipient ViewModels/TimeLanding/Punches/TimeClock/*.cs | wc -l` rather than trusting
  this number, which moves with every extraction.
- `IActivatableViewModel` is implemented by 7 of them directly, and by 3 more through their interfaces in
  `Utilities/TimeClockUtilities/` (`IPunchInputViewModel`, `IGeoLocationViewModel`,
  `IPunchRejectionHandlerViewModel`).
- `ActivatableViewModels` holds those 10 (`TimeClockViewModel.cs:185-197`) — the 12 children less
  `PeriodicCheckViewModel` and `TeamTimeMessagesViewModel`, which are the step-5 exceptions below.

The other long ViewModels in this repo — `LoginViewModel`, which is larger than the TimeClock orchestrator, and
`PreferencesViewModel` — are not built this way, so splitting one is
`winteam-standards:keeping-files-small`, not this skill.

Getting the activation wiring wrong is the common failure: the child compiles, constructs, and binds fine,
but silently never receives any of its messages.

## When NOT to use

- Creating a screen's top-level page ViewModel — that's `WTBasePageViewModel` plus a navigation route, not
  a child.
- Item/cell ViewModels for a list — follow `WTFeedItemViewModel`/`JobItemViewModel` instead.
- Pure data holders with no behaviour — make an Entity or a record.
- Managers, Proxies, or Services. Those aren't view models and are registered directly in `Bootstrap.cs`.
- A long ViewModel outside the TimeClock and Kiosk trees. That's `winteam-standards:keeping-files-small` —
  none of the activation wiring here applies to it.

## Steps

1. **Name the state it owns, first.** Write one sentence: "this class is the single source of truth for
   X." If you can't, the boundary is wrong — you'll end up with two classes mutating the same field.
   `LastStatusViewModel` owns `LastStatus`; `PendingPunchesViewModel` owns the pending-punch entities.

2. **Pick the base class.**
   - `WTBaseObservableRecipient` (`ViewModels/Abstract/WTBaseObservableRecipient.cs`) — anything with
     observable properties or message handlers. It marshals `OnPropertyChanged`/`OnPropertyChanging` to
     the main thread; deriving from `ObservableRecipient` directly instead updates bindings off the UI
     thread and produces iOS "UIKit Consistency error". The one class still doing that,
     `HomeTenantViewerViewModel`, predates the base class — don't copy it.
   - **A plain class with no base** — a helper collaborator that only manipulates state passed to it. See
     `PunchInput/JobInputViewModel.cs`. Prefer this; it's the cheapest thing that works.
   - `WTBasePageViewModel` — only if this is its own screen with a navigation route.

3. **Call `TinyIoCContainer.Current.BuildUp(this)` in the constructor** if you use `[Inject]` properties.
   Nothing injects for you when the object is `new`ed. Plain helper classes do this too
   (`JobInputViewModel.cs:42`).

4. **Pick the construction site — this is load-bearing.**
   - `[Inject]` property on the parent — only when the child's constructor takes no arguments. TinyIoC
     auto-resolves concrete types, so **no `Bootstrap.cs` entry is needed** (`TimerViewModel`,
     `PeriodicCheckViewModel`).
   - Parent's manual setup method — when it needs a manager or a sibling passed in
     (`TimeClockViewModel.SetupManualViewModels():177`).
   - A `protected virtual` setup method — when a variant subclass must substitute it. For TimeClock that's
     `SetupAbstractViewModels():202`; invoke `timeclock-refactor:kiosk-variant-pairing` before choosing this.

   **Construction order is a constraint, not style.** Children taking siblings as constructor arguments
   must be built after those siblings, or you get a `NullReferenceException` during construction with no
   compile error.

5. **If it implements `IRecipient<T>`, it must also implement `IActivatableViewModel` and be added to the
   parent's `ActivatableViewModels` list.** The parent's `OnActivated`/`OnDeactivated` flips `IsActive`,
   and `IsActive` is what registers the handlers. **Miss this and the class works perfectly except that no
   message ever arrives** — no error, no warning. Two deliberate exceptions exist:
   `PeriodicCheckViewModel` sets `IsActive = true` in its own constructor (`:58`) and is never
   deactivated; `TeamTimeMessagesViewModel` implements no `IRecipient<T>` so activation would be a no-op.

6. **Wire teardown if it holds anything the messenger won't collect** — a `BusManager` subscription, a
   `StrongReferenceMessenger` registration, an `IDisposable`, a timer, or a `CancellationTokenSource`.
   Expose `Dispose()`/`Cleanup()` and call it from the parent's `Dispose` (`TimeClockViewModel.cs:336-342`
   disposes `PunchInputViewModel`, cleans up `CapturePunchPhotoViewModel`, and does its own
   `StrongReferenceMessenger.Default.UnregisterAll(this)`).

7. **Choose how it talks to its siblings** → invoke `timeclock-refactor:vm-communication-channel`. Do not default to a new
   message; if the parent already holds both objects, a direct call is correct.

8. **Prefer these four shapes over another view model where they fit.** Each already exists here:
   - **Shared mutable state object + capability delegates** — `PunchInput/PunchInputState.cs`. Two helpers
     share one state object and receive `Func<>`/`Action<>` for the capabilities they need, so neither
     holds a reference back to the owner. Best for splitting a multi-step flow.
   - **Immutable context record** — `Utilities/TimeClockUtilities/RejectionContext.cs`, built by
     `BuildRejectionContextUseCase`. Collapses "this method needs four view models" into one
     `readonly record struct`. Best for the trigger case of 3+ view model arguments.
   - **Policy object behind a `protected virtual` factory method** — `PunchPhotoPolicy` +
     `CapturePunchPhotoViewModel.CreatePolicy()`. Best when only a decision rule varies.
   - **Result enum with a predicate extension** — `PunchPhotoCaptureResult` + `CanSendPunch()`. Best
     when a bool currently conflates "failed" with "not applicable".

9. **Build.** `dotnet build WinTeam.Mobile.Core/WinTeam.Mobile.Core.csproj`, plus
   `WinTeam.Mobile.iOS`/`WinTeam.Mobile.Android` csproj if a View binds to the new child.

## Threading

`WTBaseObservableRecipient` handles property-change marshalling, but not your own async work. Anything
touching UI from a background task still needs `MainThread.InvokeOnMainThreadAsync`
(`LoadTimeClockDataUseCase` wraps geolocation init in it). If you add a `SemaphoreSlim`, release it in a
`finally` and be aware `TimeClockViewModel` already holds a separate `CanUseUi` semaphore — two
uncoordinated semaphores around one flow is how the punch screen deadlocks.

## Verify

- The new child appears in `ActivatableViewModels` if and only if it has `IRecipient<T>` handlers.
- Its messages actually arrive. Ask the user to run `/timeclock-refactor:vm-message-audit` and confirm no new
  zero-recipient message — a slash command cannot be invoked from inside a skill.
- Parent line count actually went down, and the child has one stateable responsibility.
- Build clean, and exercise the feature on device — activation bugs do not show up at build time.
