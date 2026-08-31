---
name: shaping-manager-contracts
description: >-
  Use when creating a Manager in WinTeam.Mobile.Core, adding or changing a public method on one or on an
  I*Manager interface, or deciding what type a Manager hands back.
when_to_use: >-
  Applies even mid-execution of an already-approved plan that names the file, class or method shapes —
  an approved plan is not an exemption. Applies whichever tool writes the file: Write, Edit, a Bash
  heredoc, `sed -i`, or an MCP server's own file-creation call.
---

# Let a Manager return entities, and nothing that knows about a screen

The Manager is the only layer allowed to see both the wire and the database, which makes its signature the most
expensive thing in the project to get wrong: ViewModels, use cases and the kiosk variant all bind to it.

**The cost of returning a `*ItemViewModel` is that the business rule stops being reusable.** The kiosk screen,
the other platform and any future caller now have to construct a presentation object to ask a business
question — and changing how one screen displays a value forces a rebuild of the business layer. This is the
most-violated boundary in the repo — a double-digit number of Manager files already import a `ViewModels`
namespace, counted and listed under `## Known offenders` below. That is a reason to contain it, not permission
to add one more.

## When to use

Before writing the signature, not after — a return type is the hardest thing to change later, because every
caller encodes it. Fires when you are about to:

- create a class under `WinTeam.Mobile.Core/Managers/`,
- add or change a public method on a Manager or on an `I*Manager`,
- pick a return type, or add a `using` to a Manager file,
- decide whether a new Manager needs an interface at all.

## When NOT to use

- Private helpers inside a Manager. The size rules still apply; this one does not.
- Proxies — concrete by design, see `respecting-layer-boundaries` rule 3.
- `MobileCore`'s own `BaseManager`, which is a submodule and not ours to change.
- Classes named `*Manager` that are not business managers — the stateful lifecycle owners under `Utilities/`
  are helpers, and `reusing-existing-helpers` covers those.

## Rules

1. **Extend `WTBaseManager`.** It supplies `Logger`, `DbProxy`, a `BuildUp(this)` constructor, and the three
   synchronisation helpers. A Manager that reaches for its own database access re-implements sync slightly
   differently, which is how two screens end up disagreeing about what is cached.

2. **Declare an `I*Manager` when a ViewModel or use case will inject it. Skip it when the Manager is only
   another Manager's collaborator.** 9 of 26 Managers have no interface and not all of that is debt. Put the
   interface next to the implementation. The one sanctioned exception is a contract shared by two
   implementations, which lives with its factory — see below.

3. **Return `*Entity`, a `record`, a primitive, or a result enum. Never a `*ViewModel`, in either direction.**
   Accepting one is the same violation as returning one: the dependency exists either way.

   ```csharp
   // no — the business layer now depends on presentation
   Task<List<ThingItemViewModel>> GetThingsAsync();
   Task UpdateAsync(ThingItemViewModel item);

   // yes — hand back data; let the ViewModel build its own items
   Task<List<ThingEntity>> GetThingsAsync();
   Task UpdateAsync(ThingEntity thing);
   ```

4. **A `*Response` stops at the Manager, with one named carve-out.** Map it to its `*Entity` sibling and return
   that; see `response-entity-sibling`. The carve-out is `ErrorResponse`, which is already
   treated as a domain type and travels into use cases and platform views. **That is accepted debt with a
   boundary: do not add a new `*Response` to any public signature.**

5. **Formatting is not a business rule.** A Manager that builds `Balance = $"{value} {AppStrings.Hours}"` has
   picked a display format for every caller and made the business layer depend on localisation. Return the
   `decimal`; let the item view model format it.

6. **The canonical read is sync-then-read-from-db, gated by a flag.**

   ```csharp
   public async Task<List<ThingEntity>> GetThingsAsync(bool forceDownload = false)
   {
       if (forceDownload)
           await SynchronizeDbEntityList<ThingEntity, ThingResponse>(
               () => ThingProxy.GetThingsAsync(), ThingsDataFilter);

       return (await DbProxy.AllWithChildrenAsync<ThingEntity>()).ToList();
   }
   ```

   The read is a **separate statement on purpose**: `SynchronizeDbEntityList` catches its own exceptions and
   logs them, so a failed sync returns stale cached data rather than throwing. Callers cannot distinguish
   "synced" from "sync failed" — if that distinction matters to your screen, you need a return value, not a
   `void` sync.

7. **Mapping is by attribute, not by hand.** Put `[AutoMap(typeof(ThingResponse))]` on the entity;
   `MapperConfigSingleton` discovers it automatically across loaded assemblies. No manual projection loop, no
   profile registration.

8. **Not every Manager needs a cache.** An online-only screen may pass proxy results straight through — say so
   in the `///` doc rather than inventing an entity table nobody reads.

9. **A Manager holds no per-screen state, and never calls upward.** Every registration is `AsSingleton()`, so a
   field survives navigation, logout and user switch — a cached "current thing" is how one user sees another's
   data. And no ViewModel reference, no callback handed in from a screen: to announce something, publish a
   message.

## When two implementations share one contract

If two Managers implement the same interface, the container cannot disambiguate — the second registration
silently wins for every caller. The fix is a factory that decides which one applies, and the **interface then
belongs with the factory** (`Managers/ThingFactory/IThingManager.cs`), not with either implementation. This is
the only reason to file an interface away from its implementation.

## Known offenders

**13 Manager files import a `WinTeam.Mobile.Core.ViewModels.*` namespace**, across 17 public signatures:

- `IHourlyBenefitsManager.cs:14` and `HourlyBenefitsManager.cs:24` — returns `List<HourlyBenefitsItemViewModel>`,
  and `:31` also formats with `AppStrings`. Two rules in one method.
- `IPaycheckManager.cs:15,16,19,23` — four methods returning `List<PaycheckItemViewModel>`.
- `TimeClockManager.cs:33,76` — `Task<List<PunchGroupViewModel>>`.
- `TimekeepingManager.cs:19,51` — `List<TimekeepingItemViewModel>` and a single `TimekeepingItemViewModel`.
- `KioskModeManager.cs:245,266` — *accepts* a `KioskProfileItemViewModel`. Inbound counts.
- `PunchesManager.cs:482` — `static JobItemViewModel GetJobInformationFromPunchErrorResponse(List<ErrorResponse>)`,
  which breaks rules 3 and 4 at once.

`*Response` above the Manager: `IBiometricsManager.cs:13,15,19,21,23` (five methods), `IProfileInfoManager.cs:19,20`.

**Two laundering traps, neither of which is a fix.** `Utilities/TimeClockUtilities/` holds five ViewModel
interfaces so a Manager contract can reference them without a `ViewModels` using, and
`Managers/Resources/ISubmitAppFeedbackViewModel.cs` puts one inside `Managers/` itself. **Moving a type does
not undo the dependency** — rule 3 is about what the signature means, not which folder it is spelled in.

`AppStrings` appears 8 times under `Managers/`. Not all are violations — notification and support-email body
text is defensible. `HourlyBenefitsManager.cs:31` is the clear one.

## Verify

- `grep -rl "using WinTeam.Mobile.Core.ViewModels" WinTeam.Mobile.Core/Managers --include="*.cs" | wc -l`
  returns **13**. A non-growth check: 14 means you added an inversion.
- `grep -rn "AppStrings" WinTeam.Mobile.Core/Managers --include="*.cs"` — 8 hits, and yours is not a ninth that
  formats a value for display.
- Your new public signature names no `*ViewModel` and no `*Response`.
- `dotnet build WinTeam.Mobile.Core/WinTeam.Mobile.Core.csproj`. **Every rule above compiles perfectly** — that is
  the whole problem. A Manager that formats a string builds clean and surfaces as two screens rendering the
  same value differently; a singleton holding per-screen state builds clean and surfaces as stale data after a
  user switch. Only the greps and a second caller catch these.
