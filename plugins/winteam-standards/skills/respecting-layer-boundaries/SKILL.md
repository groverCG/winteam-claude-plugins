---
name: respecting-layer-boundaries
description: >-
  Use when adding a call from a ViewModel, use case, Manager, or Proxy in WinTeam.Mobile.Core, or when
  choosing which layer and which folder a new class in that project belongs to.
---

# Keep each layer talking only to the one below it

One direct call from the wrong layer is not a disaster on its own — the cost is that it establishes a
precedent, and the next person copies it. One of the boundaries below is genuinely unbroken and worth
defending as an invariant; another is already broken across a double-digit number of Manager files and needs
containing rather than defending. `shaping-manager-contracts` owns that count.

```
View (iOS ViewController / Android Fragment)
  → ViewModel                  binds; owns presentation state
    ├→ UseCase                 optional; orchestrates 2+ Managers for one named operation
    └→ Manager (via I*Manager) owns business rules, caching, sync
         → Proxy               owns HTTP
         → DbProxy             owns SQLite
```

A use case is a **peer of the ViewModel, not a fifth layer under it** — it sits beside the ViewModel and
calls downward into Managers. A ViewModel may call a Manager directly; it does not have to route through a
use case, and most should not. See `writing-use-cases`.

**A ViewModel that reaches a Proxy directly bypasses caching, offline handling, and entity mapping** — all of
which live in the Manager. It will appear to work on a good network and fail in exactly the conditions the
Manager exists to handle.

## When to use

Before adding the call, not after. Fires when you are about to:

- add a `[Inject]` property or a call to a type ending in `Proxy`, `Manager`, `UseCase`, or `Service`,
- write `DbProxy`, `RestClient`, or an HTTP call anywhere,
- create a new class under `WinTeam.Mobile.Core/` and need to pick a folder,
- return something from a Manager, or add a `using` to a Manager file.

## When NOT to use

- Choosing how two ViewModels talk to each other — that is a messaging question, not a layering one.
- Pure utilities, extension methods, and entity mapping, which any layer may call. Which folder one goes in is
  `reusing-existing-helpers`, not this skill.
- Building a whole new feature from nothing — the folder table below tells you where each piece lives, but the
  order to build them in is `building-vertical-slices`.
- Platform view code, which talks to its ViewModel directly and is not part of this chain.
- `Middlewares/` and `Localization/`, which are cross-cutting by design.

## Rules

1. **ViewModels never touch a Proxy or `DbProxy`.** No exceptions. This invariant currently holds across the
   entire project — a grep for `Proxy` under `ViewModels/` returns nothing. Keep it that way; it is far easier
   to defend an unbroken rule than to re-establish a broken one.

2. **ViewModels depend on manager *interfaces*.**

   ```csharp
   [Inject] public IThingManager ThingManager { get; set; }   // yes
   [Inject] public ThingManager  ThingManager { get; set; }   // no
   ```

3. **Managers may depend on concrete Proxies.** That is the established idiom here and does not need an
   interface.

4. **A Manager never returns, imports, or accepts a ViewModel type**, and **Managers return Entities, not
   Responses.** These two are the boundary most at risk and the one already most broken — see
   `shaping-manager-contracts`, which owns the Manager contract in full, including the one named
   `ErrorResponse` carve-out.

5. **Extend the base classes.** New Managers extend the base manager (which supplies `DbProxy`, `Logger`, and
   the fetch/map/save synchronisation helpers); new Proxies extend the base proxy (which supplies the REST
   client, configuration, and URI building). Bypassing them means re-implementing sync and URI construction
   slightly differently, which is how two endpoints end up disagreeing about a base path.

6. **A use case calls Managers, never a Proxy, a `DbProxy`, or a ViewModel.** It is a peer of the ViewModel,
   so the same downward-only rule applies to it. See `writing-use-cases`.

7. **Calls go downward only.** A Proxy never calls a Manager; a Manager never calls a ViewModel. If a lower
   layer needs to announce something upward, it publishes a message or raises an event — it does not hold a
   reference to its caller.

## Where a new class goes

| It... | Folder | Base |
|---|---|---|
| holds presentation state for a screen or part of one | `ViewModels/` | a `WTBase*ViewModel` |
| owns a business rule, caching, or sync for a domain area | `Managers/` | the base manager |
| makes HTTP calls to one backend module | `ServerAccess/Proxies/` | the base proxy |
| is a wire DTO | `Entities/Response/` or `Entities/Request/` | none |
| is a persisted or in-app model | `Entities/` | none |
| orchestrates two or more Managers for one named operation | `UseCases/<Domain>/` | none |
| is a payload passed between components | `Messages/<Feature>/` | none |
| is one behaviour with a different implementation per platform | interface in `Services/<Area>/`, impls in the platform projects | none |
| is a stateless helper encoding a WinTeam business rule | `Utilities/` | none |
| is stateless infrastructure with no domain knowledge | `Utils/` | none |
| extends a BCL or platform type | `Extensions/<Type>Extensions.cs` | none |
| is a custom exception | `Exceptions/` | an existing app exception |
| is a screen | iOS `Views/ViewControllers/`, Android `Views/Fragments/` | `BaseViewController<TVm>` / `WTBaseFragment<TVm>` |

The last four rows are the ones people get wrong, and `Utils/` versus `Utilities/` is the one people get wrong
most. That call belongs to `reusing-existing-helpers`, along with the search that has to precede adding any
file to `Extensions/`, `Utils/`, `Utilities/` or `Services/`. Go there before adding to one of them.

## Known offenders

**Two of the boundaries above hold; two do not.**

- Rule 1 is genuinely unbroken: `grep -rn "Proxy" WinTeam.Mobile.Core/ViewModels --include="*.cs"` returns
  nothing. Defend it.
- Rule 4 is broken across a double-digit number of Manager files, and `*Response` types appear above the
  Manager in several public signatures. This is not one stray file to fix in passing — it is an established
  pattern, so treat it as **contain, do not extend**. `shaping-manager-contracts` owns the count, the
  file-by-file list, the sanctioned carve-out, and the non-growth check.

A related trap: `Utilities/TimeClockUtilities/` holds five ViewModel *interfaces* so that a Manager contract
can reference them without importing `ViewModels`. **Moving a type does not fix an inversion** — do not copy
that as a workaround.

## Verify

- `grep -rn "Proxy" WinTeam.Mobile.Core/ViewModels --include="*.cs"` returns nothing. This is this skill's
  invariant and must stay at zero.
- For the Manager-side checks — the `using ...ViewModels` count and "no *new* `*Response` above the Manager" —
  run the Verify section of `shaping-manager-contracts` rather than a second copy of it here.
- `dotnet build WinTeam.Mobile.Core/WinTeam.Mobile.Core.csproj`. A layering violation compiles perfectly, so
  the build proves nothing here — the greps are the check.
