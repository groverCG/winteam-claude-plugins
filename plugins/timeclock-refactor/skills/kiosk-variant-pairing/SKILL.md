---
name: kiosk-variant-pairing
description: >-
  Use when changing punch-flow behaviour under ViewModels/TimeLanding/Punches/ or ViewModels/Kiosk/, or when a
  punch bug reproduces on phone but not kiosk (or vice versa).
---

> Applies to the MOB-13653 refactor branch. On `master` the types below do not exist yet.

# Pairing a change with its kiosk variant

Full map of what currently differs: `docs/architecture/timeclock/kiosk-overrides.md`.

`KioskTimeClockViewModel : TimeClockViewModel`, plus five child subclasses and one policy subclass. **No
code in the single-worker tree branches on kiosk *identity*** — the only kiosk conditionals there read a
capability flag (`TimeClockViewModel.cs:252` checks `IsKioskTeamTimeMessageEnabled`;
`CapturePunchPhotoViewModel.cs:77` passes `KioskModeManager.IsKioskModeEnabled` to a factory). That is the
sanctioned mechanism below. Keep it that way: no `is KioskTimeClockViewModel`, no type sniffing.

## When to use

Touching anything under `WinTeam.Mobile.Core/ViewModels/TimeLanding/Punches/**`,
`WinTeam.Mobile.Core/ViewModels/Kiosk/**`, or a punch-related Manager/Utility: adding a feature flag check,
a server call, a dialog, a permission prompt, a job/work-ticket rule, or a rejection path. Also when
extracting a new child view model in that area, and when a bug reproduces on phone but not on kiosk (or
vice versa) — that asymmetry is usually a missing or over-eager override.

Kiosk mode is implemented purely by subclassing. If a behaviour change needs to differ in kiosk and you
don't pair it, kiosk silently inherits the single-worker behaviour and nothing fails at build time.

## When NOT to use

- Features outside the punch/TimeClock flow — Pay, Resources, TaxForms, ProfileInfo and Timesheets have no
  kiosk variant.
- Changes that are provably presentation-only in a phone-only view.
- The kiosk login/session screens themselves — `BaseKioskLoginViewModel` and friends are already
  kiosk-only, so there is no pairing to do.

## Step 1: decide whether kiosk actually differs

Ask what the kiosk device changes about the behaviour. Kiosk has: fixed assigned geo-coordinates, no
logged-in contact record (worker identity comes from the session), its own server endpoints, an inactivity
timeout, offline punches always off, and its own profile config (`KioskProfileEntity`).

If none of those touch your change, **stop — no pairing needed.** Most changes need nothing. Nine of the
twelve TimeClock children have no kiosk subclass at all.

## Step 2: pick the cheapest mechanism that works

In order of preference:

| Mechanism | Use when | Reference |
|---|---|---|
| **Capability flag** | Kiosk just turns the feature off | `PeriodicCheckViewModel.IsFeatureSupported`, set false at `KioskTimeClockViewModel.cs:95` |
| **Policy object behind a `protected virtual` factory** | Only a decision *rule* differs | `PunchPhotoPolicy` + `CreatePolicy()` → `KioskPunchPhotoPolicy` |
| **Subclass with virtual overrides** | Behaviour, server calls, or UI flow genuinely differ | the five `Kiosk*ViewModel` classes |

A flag or a policy avoids a new class and keeps the variation visible in one place. Reach for a subclass
only when several members must change together.

## Step 3: if you need a subclass, do all four parts

Miss any one and kiosk silently inherits single-worker behaviour.

1. **Interface** in `WinTeam.Mobile.Core/Utilities/TimeClockUtilities/`, extending `IActivatableViewModel`
   — follow `IGeoLocationViewModel.cs`. Declare the orchestrator's property with the interface, not the
   concrete type. (`CapturePunchPhotoViewModel` is declared concretely and still substituted, since
   subclassing alone satisfies assignment — but the interface is the convention.)
2. **Make every divergence point `protected virtual` or wider** on the base, *and* anything the subclass
   needs to read. `GeoLocationViewModel` keeps `IsMapAllowedByProfile` and
   `HandleTeamTimeMessagesOnGPSPermission()` protected precisely for this.

   **Prefer a narrow virtual *value* over a virtual *method* the subclass corrects afterwards.**
   `IsMapAllowedByProfile` is a `bool` the base folds into its own computation, so the base acts on the
   final value. The shape it replaced — kiosk overriding `RefreshMapVisibility`, calling `base`, then
   forcing `ShouldShowMap = false` — meant the base had already logged a map-shown analytics event on
   kiosks that never show a map, and wrote the bound property twice per refresh. If your subclass finds
   itself undoing what `base` just did, the seam is in the wrong place.
3. **Construct it in `SetupAbstractViewModels()`** (`TimeClockViewModel.cs:202`) — **not**
   `SetupManualViewModels()`, which is not virtual and cannot be overridden.
4. **Add the `Kiosk*` class** in `ViewModels/Kiosk/` and override it in
   `KioskTimeClockViewModel.SetupAbstractViewModels()` (`:98-105`).

## Traps

**The constructor-ordering trap.** `SetupAbstractViewModels()` is called from the *base* constructor
(`TimeClockViewModel.cs:114` → `:182`), so your derived override runs **before**
`KioskTimeClockViewModel`'s own constructor body. Anything the kiosk constructor initialises is not yet
set while its children are being built. This is why `PeriodicCheckViewModel.IsFeatureSupported = false`
sits at the *end* of the kiosk constructor (`:95`) rather than in the setup method.

**Duplicate responders on a `RequestMessage`.** Because kiosk *replaces* child view models rather than
reconfiguring them, any window where a single-worker and a kiosk instance are both registered gives two
responders for the same request — and `Reply()` throws `InvalidOperationException` on the second. If your
new child answers a `RequestMessage`, guard with `HasReceivedResponse`. See
`docs/architecture/timeclock/messages.md#1-duplicate-responders-on-a-requestmessage-throw`.

**Don't downcast the manager without a fallback.** `TimeClockManager` is `KioskModeManager` in kiosk mode
and `TimeClockManager` otherwise, both behind `ITimeClockManager`.
`KioskPunchRejectionHandlerViewModel.cs:46` uses `(TimeClockManager as KioskModeManager)?.…`, which
yields `null` rather than throwing if the wrong manager was injected — copy the null-conditional form.

**Kiosk-only messages have no recipient on phone.** `InitInactivityMonitorMessage` is handled only by
`KioskTimeClockViewModel`. Sending it in single-worker mode is a silent no-op, which is fine — just don't
assume a recipient exists.

## Verify

- Both paths exercised: single-worker **and** kiosk. A build proves nothing here.
- For each member you overrode, confirm the base still behaves correctly for phone — check you didn't make
  a phone-only rule `virtual` and then change its meaning.
- If you added a child VM: it appears in `SetupAbstractViewModels()` on **both** classes, and in
  `ActivatableViewModels` if it has `IRecipient<T>` handlers.
- `dotnet build` for Core plus both platform csprojs if any View changed.
- Update `docs/architecture/timeclock/kiosk-overrides.md` with the new pairing.
