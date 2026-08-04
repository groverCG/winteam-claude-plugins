---
name: wiring-dependency-injection
description: >-
  Use when a class in WinTeam.Mobile.Core needs a manager or service, when writing [Inject], BuildUp( or
  TinyIoCContainer.Current, or when adding a registration to Bootstrap.
---

# Inject dependencies as properties, and resolve nothing yourself

This project uses TinyIoC, **vendored as source inside MobileCore rather than referenced as a NuGet package**,
so its behaviour is whatever that file says — not what the upstream docs say. Two consequences shape
everything below:

- **`[Inject]` is TinyIoC's own attribute and applies to properties only.** It does nothing on a constructor
  parameter, a field, or a value type. No error, no warning — the dependency is simply null at runtime.
- The container is a **global static**. Reaching into it directly works, which is exactly why it needs a rule.

## When to use

Before adding the dependency, not after. Fires when you are about to:

- give a class a manager, service, dialog, logger, or feature-flag client,
- write `[Inject]`, `BuildUp(`, or `Container.Current`,
- add a line to `Bootstrap.cs`,
- write a constructor that takes collaborators.

## When NOT to use

- Passing plain data or state objects — those are ordinary parameters.
- Platform bootstrap files, which register platform implementations and legitimately touch the container.
- A child collaborator that its owner constructs and hands everything it needs.
- Test-only wiring. Out of scope here.

## Rules

1. **Declare dependencies as public settable properties with `[Inject]`, typed as interfaces.**

   ```csharp
   [Inject] public IThingManager ThingManager { get; set; }
   [Inject] public IDialog Dialog { get; set; }
   ```

   Public and settable is required — TinyIoC populates these by reflection and skips anything it cannot set.

2. **Call `BuildUp(this)` in the constructor if you use `[Inject]` and no base class already does it.** The
   base page ViewModel and base manager do it for you. **A plain class that you `new` yourself does not** —
   nothing injects into a manually constructed object, and every `[Inject]` property stays null.

   ```csharp
   public MyHelper()
   {
       TinyIoCContainer.Current.BuildUp(this);
   }
   ```

3. **Never call `Resolve<T>()` in a constructor or a method body.** That is service location: it hides the
   dependency from the signature, makes the class impossible to construct without a fully configured global
   container, and turns a missing registration into a runtime failure far from its cause.

   ```csharp
   // no
   public MyThing() { _settings = TinyIoCContainer.Current.Resolve<ISettingsManager>(); }

   // yes
   [Inject] public ISettingsManager Settings { get; set; }
   ```

4. **Register interface-to-implementation in `Bootstrap.cs`, as a singleton unless you have a reason.**

   ```csharp
   container.Register<IThingManager, ThingManager>().AsSingleton();
   ```

5. **Concrete types with a parameterless constructor need no registration.** TinyIoC auto-resolves them. Don't
   add a `Bootstrap` line for a concrete child ViewModel that takes no arguments — it already works.

6. **A singleton must not hold per-screen state.** Most registrations here are singletons, so a field on a
   Manager persists for the whole process and across users. Screen state belongs on the ViewModel.

7. **Property injection is why primary constructors don't work on ViewModels and Managers.** The container
   needs a parameterless constructor to instantiate and then populate. Use primary constructors on records,
   messages, and small immutable helpers — not on injected types.

8. **When a constructor's parameter list grows past three collaborators, convert them to `[Inject]`
   properties** rather than introducing a record. A record is for data travelling together; collaborators are
   not data. See `keeping-core-methods-small`.

## What injection does not fix

`[Inject]` gives you the instance. It does not give you lifetime management — if the injected thing exposes
events or a messenger registration, teardown is still yours to write, and a singleton dependency outliving
your object is exactly the shape that leaks. See `tearing-down-subscriptions`.

## Known offenders

19 files under `WinTeam.Mobile.Core/` call the container directly rather than declaring an `[Inject]`
property, several inside constructors — including one use case whose entire constructor body is a `BuildUp`
call. 72 of the 116 `*ViewModel.cs` files under `WinTeam.Mobile.Core/ViewModels/` use `[Inject]` properly; the
rule is well established, the exceptions are the outliers. Don't add to them.

## Verify

- Every dependency is an `[Inject]` public settable interface-typed property, or an ordinary parameter — never
  a `Resolve<T>()`.
- If the class uses `[Inject]` and is `new`ed anywhere, its constructor calls `BuildUp(this)`.
- New interfaces are registered in `Bootstrap.cs`; new concrete parameterless types are not.
- `dotnet build WinTeam.Mobile.Core/WinTeam.Mobile.Core.csproj`, then **launch the screen**. A missing
  registration or a forgotten `BuildUp` compiles cleanly and fails as a `NullReferenceException` at runtime,
  so the build cannot confirm this one.
