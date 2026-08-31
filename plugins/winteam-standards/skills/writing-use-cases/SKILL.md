---
name: writing-use-cases
description: >-
  Use when a ViewModel method starts coordinating more than one Manager, or when creating or changing anything
  under WinTeam.Mobile.Core/UseCases/.
when_to_use: >-
  Applies even mid-execution of an already-approved plan that names the file, class or method shapes —
  an approved plan is not an exemption. Applies whichever tool writes the file: Write, Edit, a Bash
  heredoc, `sed -i`, or an MCP server's own file-creation call.
---

# Inject a use case's collaborators and pass it data, never a ViewModel

A use case here is a named business operation lifted out of a ViewModel that grew too big, or out of two
ViewModels that duplicated the same flow. It is **not** a mediator and not a CQRS handler — there are none of
those in this repo and none should be introduced.

**A use case that takes child ViewModels as parameters is the original method with `this` deleted.** It reduces
no coupling: it moves the coupling into a file the size cap no longer measures, makes the flow harder to
navigate, and inverts the layer graph, because a class in `UseCases/` now imports `ViewModels/`.

> **None of the three use cases in this repo is a template.** Two take five or six child ViewModels as
> parameters and one imports `Microsoft.Maui` to reach `MainThread`. The existing shape is agreed debt and
> the context record is the agreed fix — `BuildRejectionContextUseCase` is the one that already collapses
> four view models into a `readonly record struct`, and it is the closest thing here to the target.
> **Use the generic snippets here, not the nearest real file.**

## When to use

Before extracting, not after. Fires when you are about to:

- write a ViewModel method that calls two or more Managers in sequence with a decision between them,
- duplicate a multi-step flow that already exists in a sibling or kiosk ViewModel,
- create or edit anything under `WinTeam.Mobile.Core/UseCases/`.

## When NOT to use

- One Manager call and no branching. That is a line in a ViewModel, not a class.
- Deriving or formatting state that is already loaded — that is a computed property or an extension method.
- Sequencing sibling child ViewModels' own methods. That is not a use case; see the section below.
- Anywhere outside `WinTeam.Mobile.Core/`.
- Editing one of the three existing use cases for an unrelated reason. Do not rewrite them as a side effect.

## Rules

1. **One public entry point, `ExecuteAsync` — or `Execute` if genuinely synchronous.** A second public method
   means the type is a Manager or a helper, not a use case.

2. **Name it `<Verb><Noun>UseCase`, file it at `UseCases/<Domain>/`, and give it no interface and no base
   class.** The concrete type is the contract. An `IThingUseCase` with one implementation buys nothing here:
   the container resolves concrete types anyway, and Moq can double a concrete class where a test needs to.

3. **Collaborators are `[Inject]` properties and the constructor calls `BuildUp(this)`** — not constructor
   parameters, because nothing populates `[Inject]` on a manually constructed object. See
   `wiring-dependency-injection`.

   ```csharp
   [Inject] public IThingManager ThingManager { get; set; }
   public SubmitThingUseCase() => TinyIoCContainer.Current.BuildUp(this);
   ```

4. **Inputs are data: a `record`, a `readonly record struct`, an Entity, or three or fewer scalars. Never a
   ViewModel.**

   ```csharp
   // no — imports ViewModels, and binds one operation to five screen objects
   public Task ExecuteAsync(ThingConfigurationViewModel configuration,
                            PendingItemsViewModel pending,
                            ILastStatusViewModel lastStatus, ...)

   // yes — a context built once, at the call site
   public readonly record struct SubmitContext(string Reference, DateTime At, bool IsRetry);
   public Task<SubmitResult> ExecuteAsync(SubmitContext context);
   ```

5. **Return a value; do not mutate your caller.** If the only effect is assigning properties on objects it was
   handed, it is a method on those objects. When the caller must branch three ways, a result enum with an
   extension method beats a `bool`.

6. **A use case may call Managers. It may not touch a Proxy, `DbProxy`, or a ViewModel.** It is a peer of the
   ViewModel, not a fifth layer beneath it. See `respecting-layer-boundaries`.

7. **No UI concerns.** No `MainThread`, no `Microsoft.Maui.*`, no dialog, no navigation, no `AppStrings`.
   Thread marshalling belongs to the ViewModel, and `WTBaseObservableRecipient` already handles it for property
   change notifications.

8. **Register it in `Bootstrap.cs` under a `// <Domain> use cases` comment.** `AsSingleton()` is safe *only*
   because rule 5 keeps it stateless. If it ever holds a field, it must not be a singleton.

9. **Target a body of 10 lines**, like any Core method — 15 is where the edit hook flags it, per
   [`thresholds.json`](../../thresholds.json). If `ExecuteAsync` needs more than that, it is doing two
   operations — split it, or leave the sequencing with the caller. See `keeping-core-methods-small`, which
   owns this rule.

## When a context record is the wrong answer

A record cannot express *"call these five things, in this order."* Some flows are genuinely a call sequence
over sibling ViewModels, and no amount of record-shaping turns them into a computation.

**A class whose job is sequencing sibling ViewModels' own methods is a step sequencer, not a use case.** It
belongs to the orchestrator ViewModel that owns those siblings. If the orchestrator is over the file cap and it
has to move out, the extraction that works takes **a shared state object plus `Func<Task>` capability
delegates** — never a ViewModel type, and never a reference back to its owner:

```csharp
// receives capabilities, not collaborators
public ThingInputStep(ThingInputState state, Func<Task> refreshAsync) { ... }
```

The repo precedent is `PunchInput/PunchInputState.cs` with `JobInputViewModel` and `WorkTicketInputViewModel` —
plain classes, no base class, no messaging, listed under "Patterns worth copying" in the architecture doc. See
also `keeping-files-small` for where the seam goes.

## Testing a use case

This used to say there was no way to test one. There is now: `WinTeam.Mobile.Core.Tests/` at the repo root, in
`WinTeam-MobileDotNet.sln`, xunit + Moq + FluentAssertions. Inherit
`Infrastructure/TimeClockTestFixture` — it registers the `[Inject]` doubles the global static container needs and
neutralises the MAUI `MainThread` call that otherwise throws in a test host. See
`docs/architecture/timeclock/parity-and-testing.md`.

Two caveats before you lean on it. Coverage is still essentially zero, so **do not describe a use case as
"tested" because the project exists.** And `MobileCore/src/Mobile.Core.Tests/` is a different project belonging
to the `MobileCore` sub-repo — it cannot see `WinTeam.Mobile.Core` and is not where this code goes.

**These rules are still justified by coupling first.** A use case with six parameters and four child view models
is bad design whether or not anyone tests it; testability is a consequence, not the argument.

## Known offenders

Three use cases exist, all under `UseCases/TimeClock/`, all registered `AsSingleton()` at `Bootstrap.cs:147-150`,
all consumed only by `TimeClockViewModel`. Each breaks something different:

- `LoadTimeClockDataUseCase.ExecuteAsync` — 6 parameters, 4 of them child ViewModels; imports
  `Microsoft.Maui.ApplicationModel` at line 2 for `MainThread.InvokeOnMainThreadAsync` at line 31. Its body is
  a pure call sequence, so it is the **step sequencer** case above, not a use case at all.
- `HandlePunchRejectionUseCase.ExecuteAsync` — 6 parameters, 5 child ViewModels, and `List<ErrorResponse>`
  inbound. Gets rule 3 right (`[Inject]` + `BuildUp`) and rule 4 wrong.
- `BuildRejectionContextUseCase.Execute` — 4 child ViewModels in, one `RejectionContext` out. **Output right,
  input wrong**, and it is the closest thing here to the target shape.

Zero use cases outside TimeClock. Zero `Interactor` types. No mediator.

## Verify

- `grep -n "ViewModel" <your new file>` returns nothing.
- **A stated false positive:** `RejectionContext.cs:11` carries a `JobItemViewModel`, so the *sanctioned*
  context record trips a naive ViewModel grep. That is existing debt, not a licence for a new one — your record
  should carry Entities and scalars.
- Three parameters or fewer; body at the 10-line target, and under the 15-line flag either way.
- `dotnet build WinTeam.Mobile.Core/WinTeam.Mobile.Core.csproj`. **A missing `Bootstrap` registration or a
  forgotten `BuildUp(this)` compiles perfectly and throws `NullReferenceException` on the first call** — so
  launch the screen and run the operation once. The build cannot tell you the use case was never wired.
