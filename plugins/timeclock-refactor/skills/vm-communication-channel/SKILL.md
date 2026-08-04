---
name: vm-communication-channel
description: >-
  Use when two components under ViewModels/TimeLanding/Punches/ or ViewModels/Kiosk/ need to talk, or when a
  TimeClock request message returns null or throws InvalidOperationException.
---

> Applies to the MOB-13653 refactor branch. On `master` the types below do not exist yet.

# Choosing how two components talk

Read `docs/architecture/timeclock/messages.md` for the live catalog of the 55 existing messages before
adding a new one — **the one you need may already exist.**

## When to use

Before writing the call, not after. Fires when you would otherwise write: `new XyzMessage(`,
`WeakReferenceMessenger.Default.Send/Register`, `StrongReferenceMessenger`, `public event EventHandler`,
`BusManager.Publish/Subscribe`, a new file under `WinTeam.Mobile.Core/Messages/`, or
`SomeOtherViewModel.SomeProperty` from inside a view model. Also fires when a request message you send
returns a default/null value for no obvious reason, or throws `InvalidOperationException` — that is almost
always a responder problem, see the hazards section.

This repo has six competing mechanisms for this and the compiler verifies none of them, so picking the
wrong one fails silently at runtime rather than at build time.

## When NOT to use

- View-to-viewmodel binding — that's `[ObservableProperty]`/`IRelayCommand`, not a channel.
- A parent calling a method on a child it constructed and holds a reference to — just call it.
- Manager→Proxy or Manager→DbProxy calls.
- Anything in `WinTeam.Mobile.iOS/` or `WinTeam.Mobile.Android/` view code, which talks to its ViewModel
  directly and uses `BusManager` for cross-screen signals.

## Pick the channel

| Your need | Use | Reference implementation |
|---|---|---|
| Caller needs a value from a component it does **not** hold a reference to | `RequestMessage<T>`, file in `Messages/<Feature>/Request/` | `LastStatusRequestMessage` → answered by `LastStatusViewModel` |
| Same, but the reply must be awaited | `AsyncRequestMessage<T>` | `SetupAndGetLatestPunchRequestRequestMessage` |
| One owner announces a state change to N listeners it doesn't know about | `ValueChangedMessage<T>`, file in `ValueChanged/` | `LastStatusChangedMessage` — 1 sender (`LastStatusViewModel.cs:93`), 5 recipients |
| Fire-and-forget command or reset, no reply needed | `sealed record`, file in `Notification/` | `ResetPunchInputDataMessage` |
| A component reports an outcome to its **one known owner** | C# `event EventHandler<T>` | `TeamTimeMessagesViewModel.OnCompleteDisplayMessages`; `CapturePunchPhotoViewModel`'s three events |
| A modal/sheet result the caller awaits | C# events on the sheet VM; the platform view converts them to `TaskCompletionSource<OptionalResult<T>>` | `JobSelectorViewModel` → `JobSelectorModalSheetController.cs:93,98,122` |
| App-wide or cross-screen lifecycle signal | `BusManager.Publish` / `Subscribe` | `ForceLogoutEvent`, `RefreshTimeClockDataEvent` |
| Caller already holds the reference and needs the whole object | **Direct property or constructor injection. Do not invent a message.** | `TimeClockBannerViewModel(lastStatus, pendingPunches)` |
| A helper needs a capability from its owner without a back-reference | `Func<>` / `Action<>` capability delegate | `JobInputViewModel`, `TimeMessageObservableQueue` |

The dividing line: **a C# event is for reporting upward to the single owner that holds you; a message is
for components that hold no reference to each other.** If you can name the receiver's type at compile
time and it owns you, use an event.

## Rules

1. **One responder per `RequestMessage`.** `Reply()` throws `InvalidOperationException` on a second call.
   If two instances could both be registered (see `timeclock-refactor:kiosk-variant-pairing`), guard with
   `if (!message.HasReceivedResponse)` — as `TimeClockViewModel.Messages.cs:144` does.
2. **Prefer `IRecipient<T>` over manual `Register`.** Implementing `IRecipient<T>` means
   `ObservableRecipient` registers and unregisters for you when `IsActive` flips. A manual
   `WeakReferenceMessenger.Default.Register` obliges you to add the matching `Unregister` in the same
   pair of methods — the one place that got this wrong is `KioskTimeClockViewModel.cs:90`, registered in
   the constructor and never released.
3. **Weak messenger by default.** `StrongReferenceMessenger` holds recipients alive and needs an explicit
   `UnregisterAll` on teardown. There is exactly one use — `CapturePunchPhotoViewModel.cs:79`, released by
   `TimeClockViewModel.cs:341`. Don't add a second without the matching teardown.
4. **Send with `.Send(new T()).Response`, not `Send<T>()`.** `RequestMessage<T>` defines an implicit
   conversion to `T` that returns `.Response`, so `Send<T>()` assigned to a variable *looks* like an
   assignment but throws when nobody replied (`PeriodicCheckViewModel.cs:153`).
5. **Don't add a message for a coupling you aren't actually going to cut.** Seven messages in this
   codebase have a responder and zero senders, because each was added next to a direct-property route
   that then stayed. Either replace the direct access in the same change, or don't add the message. See
   `docs/architecture/timeclock/messages.md#4-seven-orphans`.
6. **File placement and naming.** `Messages/<Feature>/Request/XyzRequestMessage.cs`,
   `ValueChanged/XyzMessage.cs`, `Notification/XyzMessage.cs`. Nine files still sit loose at the root of
   `Messages/TimeLanding/` — four of which aren't messages at all. Don't add to that pile.

## Choosing between the two messengers and the bus

`WeakReferenceMessenger` is **not** the repo-wide default — it arrived with the TimeClock refactor and is
concentrated in `ViewModels/TimeLanding/Punches/**` and `ViewModels/Kiosk/**`, which is exactly the scope of
this skill. `BusManager` (TinyMessenger, `MobileCore/src/Mobile.Core/Bus/BusManager.cs`) is still the house
idiom everywhere else, across ~15 feature folders.

**Two consequences.** Inside TimeClock, the messenger is the default and `BusManager` is for cross-screen
lifecycle signals only. **Outside TimeClock this skill does not fire and its table does not apply** — in a
feature already built on `BusManager`, keep using it rather than introducing the messenger because it is newer.

The two are already interleaved here: `PunchRejectionManager.NewPunchRejectionEvent` is a bus event type sent
through the messenger (`PunchRejectionParamBuilder.cs:125`).

## Verify

- New message type has **exactly one** sender and **at least one** recipient. Ask the user to run
  `/timeclock-refactor:vm-message-audit` — it cannot be invoked from inside a skill.
- Every manual `Register` has a matching `Unregister` in the paired method.
- `dotnet build WinTeam.Mobile.Core/WinTeam.Mobile.Core.csproj` — plus the iOS/Android csproj if a View
  sends or receives the message. A build cannot catch a missing responder; the audit command can.
