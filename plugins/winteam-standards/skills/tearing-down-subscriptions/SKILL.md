---
name: tearing-down-subscriptions
description: >-
  Use when +=, WeakReferenceMessenger.Register, BusManager.Subscribe, new Timer( or
  NSNotificationCenter.AddObserver enters a ViewModel or view in WinTeam.Mobile.Core, .iOS or .Android.
when_to_use: >-
  Applies even mid-execution of an already-approved plan that names the file, class or method shapes —
  an approved plan is not an exemption. Applies whichever tool writes the file: Write, Edit, a Bash
  heredoc, `sed -i`, or an MCP server's own file-creation call.
---

# Every subscription needs a matching teardown, and here you cannot rely on Dispose

**Read this first, because it inverts the usual advice: ViewModels in this app are not reliably disposed.** A
process-lifetime store deliberately holds ViewModels across Android fragment recreation so state survives
navigation. A ViewModel kept there outlives its fragment by design, so its `Dispose` — and any
`UnsubscribeAll` inside it — **never runs on navigation.** It is cleared only when the host activity tears
down.

The consequence: "the ViewModel gets disposed eventually" is not a teardown strategy here. A subscription
added and not explicitly removed keeps its target alive for the life of the process, and handlers fire
repeatedly on stale instances — which shows up as duplicated dialogs, double submissions, or a timer that
speeds up every time you revisit a screen.

## When to use

Before writing the subscription, not after. Fires on: `+=`, `WeakReferenceMessenger.Default.Register`,
`StrongReferenceMessenger`, `BusManager.Subscribe`, `new Timer(`, `.Elapsed +=`,
`NSNotificationCenter.AddObserver`, `Delegate = this`, and any `IDisposable` stored in a field.

## When NOT to use

- `IRecipient<T>` handlers on an `ObservableRecipient`. Registration and unregistration are automatic when
  `IsActive` flips — that is the safe path, and adding manual teardown on top is wrong.
- `[RelayCommand]`/`[ObservableProperty]` generated members.
- Binding a view to its ViewModel through the binding DSL.
- Locals that go out of scope within the method.

## Rules

1. **Never subscribe with a lambda.** A lambda cannot be unsubscribed — there is no reference to remove — so
   it is a permanent subscription by construction. Use a named method every time.

   ```csharp
   // no — unremovable, and it captures `this` into a delegate the source holds
   thing.Changed += (s, e) => Refresh();

   // yes
   thing.Changed += OnThingChanged;
   thing.Changed -= OnThingChanged;
   ```

   This is the most common leak shape in this codebase — dozens of lambda-form subscriptions exist, and not one
   of them can be undone. Ask for `/winteam-standards:leak-audit` for the live list.

2. **Subscribe and unsubscribe in a symmetric pair of methods**, called from paired lifecycle hooks —
   `OnActivated`/`OnDeactivated` for ViewModels, the platform's subscribe/unsubscribe overrides for views.
   Never subscribe in a constructor: there is no matching "unconstruct", so the pairing is impossible.

   ```csharp
   protected override void OnActivated()   { base.OnActivated();   Subscribe();   }
   protected override void OnDeactivated() { Unsubscribe();        base.OnDeactivated(); }

   private void Subscribe()   => _source.Changed += OnChanged;
   private void Unsubscribe() => _source.Changed -= OnChanged;
   ```

3. **Prefer `IRecipient<T>` over a manual `Register`.** Implementing the interface hands lifetime to the
   framework. A manual `Register` obliges you to add the matching `Unregister` yourself, in the paired method.

4. **`StrongReferenceMessenger` holds its recipients alive.** Weak is the default; if you use strong, the
   `UnregisterAll` on teardown is mandatory, not advisory.

5. **Timers need all three steps, in order:** `Elapsed -= handler`, `Stop()`, `Dispose()`, then null the
   field. Skipping the `-=` leaves the handler reachable from the timer even after `Dispose`.

6. **iOS: store observer tokens and remove them.** `NSNotificationCenter.AddObserver` returns a token; keep it
   in a field and pass it to `RemoveObserver`. Prefer `WeakDelegate` over `Delegate = this`, which creates a
   retain cycle the collector cannot break.

7. **A static field holding a view, activity, or ViewModel leaks for the process lifetime.** If you need
   process-wide access to something view-shaped, that is a design problem, not a caching opportunity.

8. **`BusManager` subscriptions are covered by the base page ViewModel's `Dispose`** — but re-read the top of
   this file: that `Dispose` may never run. If the subscription must stop when the screen goes away, unsubscribe
   explicitly in `OnDeactivated`.

## The sanctioned escape hatch nobody uses

MobileCore ships weak event subscription helpers — a generic weak `EventHandler` wrapper plus
`NotifyCollectionChanged` and `CanExecuteChanged` variants, with extension methods. **They have zero usages in
the app.** When you genuinely cannot pair a subscription with a teardown — a long-lived publisher and a
short-lived subscriber — that is the correct tool, and it is better than accepting the leak. Reach for it
before writing an unremovable subscription.

## Known offenders

Do not copy these: a messenger `Register` in a kiosk ViewModel's constructor that is never unregistered; two
`Register` calls on a singleton Manager with no teardown anywhere; a timer `Elapsed +=` in a kiosk
confirmation ViewModel with no `-=` and no `Dispose`, unlike its two sibling ViewModels which get it right;
a static `Instance` field holding an Android activity. Repo-wide the gap is real and one-directional:
`BusManager` subscribes far outnumber unsubscribes, and the same holds for `+=` against `-=` on every project.
**Do not trust a raw `+=` total, your own or anyone else's.** `+=` is also string and numeric concatenation, so
that aggregate swings with whatever regex filtered it. Pair per handler instead. Ask for
`/winteam-standards:leak-audit` to get the live list.

Worth knowing the good examples exist too: connectivity listeners split into paired
`ListenToNetworkChanges`/`RemoveNetworkChangesListener`, kiosk timers with a full three-step disposal, and
platform views using paired subscribe/unsubscribe overrides with named handlers.

## Verify

- Every `+=` you added has a `-=` on the same handler, in the paired method. Grep the file for both counts and
  compare.
- No lambda subscriptions added.
- Nothing subscribes in a constructor.
- Exercise it on device: navigate away and back **three times**, then confirm the handler fires once, not
  three times. A leak of this kind is invisible at build time and on a single pass.
