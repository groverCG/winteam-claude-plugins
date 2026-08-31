---
name: building-vertical-slices
description: >-
  Use when starting a feature, screen, or backend endpoint that has no files yet in WinTeam.Mobile.Core, or
  when asked which files a new domain area needs and in what order.
when_to_use: >-
  Applies even mid-execution of an already-approved plan that names the file, class or method shapes —
  an approved plan is not an exemption. Applies whichever tool writes the file: Write, Edit, a Bash
  heredoc, `sed -i`, or an MCP server's own file-creation call.
---

# Build a new feature bottom-up, one layer at a time

A slice touches around ten files across three projects. Four of them are shared wiring files that every other
feature also edits — `Bootstrap.cs`, `NavigationRoutes.cs`, `NavigationExtensions.cs` and
`AppCoordinator.Navigation.cs` — and a fifth append lands in whichever parent Android fragment owns the route.
Getting the order wrong is not a style problem.

**Top-down is how the layer inversions got here.** Write the ViewModel first and you write it against an
imagined Manager signature — then you bend the Manager to fit what the screen already asks for, and the Manager
ends up returning a `*ItemViewModel`. That is exactly the shape of every existing inversion — see
`shaping-manager-contracts`, which owns the count and the file-by-file list. Bottom-up costs
nothing extra, because each layer compiles and can be reasoned about on its own.

## When to use

Only when the feature has no files yet, or you are adding a new backend endpoint to an existing domain. Fires
on: "add a screen for X", "wire up the new /x endpoint", or a ticket that names an API and a screen together.

## When NOT to use

- Adding a property, command, or one method to a screen that already exists.
- A pure-UI change with no new data.
- `MobileCore` changes — it is a submodule.
- A kiosk variant of an existing slice. Those override an existing base; they do not scaffold.
- Anything where the endpoint does not exist yet. Confirm the route before writing a Proxy against it.

## The file manifest

Build in this order. Each row is verifiable before you start the next.

| # | File | Base / attribute | Governed by |
|---|---|---|---|
| 1 | `Entities/Response/ThingResponse.cs` | none | `response-entity-sibling` |
| 2 | `Entities/ThingEntity.cs` | `WinTeamBusinessEntityBase`, `[AutoMap(typeof(ThingResponse))]`, one `[PrimaryKey]` | `response-entity-sibling` |
| 3 | `ServerAccess/Proxies/Thing/ThingProxy.cs` | `WTBaseProxy` | this skill |
| 4 | `Managers/Thing/IThingManager.cs` + `ThingManager.cs` | `WTBaseManager` | `shaping-manager-contracts` |
| 5 | `UseCases/Thing/<Verb>ThingUseCase.cs` — **only if the flow spans two Managers** | none | `writing-use-cases` |
| 6 | `ViewModels/Thing/ThingViewModel.cs` (+ `ThingItemViewModel.cs` for a list) | a `WTBase*ViewModel` | `declaring-properties-and-commands` |
| 7 | `Bootstrap.cs` — proxy, manager, and use-case registrations | — | `wiring-dependency-injection` |
| 8 | `ViewModels/Navigation/NavigationRoutes.cs` — one enum member | — | this skill |
| 9 | iOS `Views/ViewControllers/Thing/ThingView.cs` + an entry in `Extensions/NavigationExtensions.cs` + a `case` in `AppCoordinator.Navigation.cs` | `BaseViewController<TVm>` | `declarative-static-styling` |
| 10 | Android `Views/Fragments/ThingFragment.cs` + a `case` in the **parent** fragment's navigation switch | `WTBaseFragment<TVm>` | `declarative-static-styling` |

**Invoke `response-entity-sibling` before you write row 1 or row 2.** Do not work the pair from this table
alone — the "Base / attribute" column is a reminder of what those two files need, not the rules for producing
them. `[AutoMap]`, picking the `[PrimaryKey]`, the `TextBlob` companion strings and the write-result carve-out
are all in that skill, and an Entity that misses any of them is silently never persisted.

Steps 8–10 are the ones that get forgotten, because **there are three separate iOS wiring sites and the Android
one lives in whichever parent fragment owns that area** — there is no single navigation file.

A Proxy is the one layer no other skill owns, so the shape is here:

```csharp
public class ThingProxy : WTBaseProxy
{
    private const string ThingEndpoint = "things";

    public async Task<List<ThingResponse>> GetThingsAsync(DateTime from)
    {
        var requestUri = BuildRequestUri(WinTeamModuleEnum.Thing, ThingEndpoint);
        var util = new UriBuilderUtil(requestUri.ToString());
        util.WithQueryParam("StartDate", from.ToString("yyyy-M-d"));

        using var httpRequest = BuildRequestMessage(util.Build(), null, HttpMethod.Get);
        var result = await RestClient.RequestAsync(httpRequest);
        return result.Content.ParseToList<ThingResponse>();
    }
}
```

## Rules

1. **Bottom-up: proxy → manager → view model → views.** Build after each layer; do not move up on a red build.

2. **Choose the ViewModel base before writing the ViewModel.** A list screen is `WTBaseFeedViewModel<TItem>`
   with `LoadDataAsync` overridden. **A child view model that raises property change must derive from
   `WTBaseObservableRecipient`** — deriving from `ObservableRecipient` directly means bindings update off the UI
   thread and iOS raises a "UIKit Consistency error" at runtime, not at compile time.

3. **Response and Entity are separate types even when they look identical.** The Response is the wire shape and
   is allowed to change when the backend changes; the Entity is what you persist and bind against.

4. **Register only what needs registering.** Interfaces and non-parameterless constructors go in `Bootstrap.cs`;
   a concrete parameterless item ViewModel resolves without a line, and adding one is noise.

5. **Both platforms, or explicitly neither.** A route added to the enum and handled on iOS but not Android is a
   silent no-op or a crash on Android. If you deliberately skip one, say which in the PR body.

6. **Do not create a use case up front.** Skip step 5 unless the flow already spans two Managers. Three exist in
   the whole repo and all three are debt — see `writing-use-cases`.

7. **Every new file is under the caps.** Target 200 lines in Core, and never cross the flag values in
   [`thresholds.json`](../../thresholds.json) — that file is the source of truth, not this line. See
   `keeping-files-small` for the target-versus-flag distinction.

8. **Stop at the smallest slice that renders.** One endpoint, one screen, one entity. A slice with three
   endpoints and two screens cannot be reviewed as one change.

## The exemplar, and where it is wrong

`HourlyBenefits` is the slice worth reading end-to-end, because its **file layout and navigation wiring are
correct and complete**:

- `Core/ViewModels/HourlyBenefits/HourlyBenefitsViewModel.cs`, `Core/Managers/HourlyBenefits/`,
  `Core/ServerAccess/Proxies/HourlyBenefits/HourlyBenefitsProxy.cs`, `Core/Entities/HourlyBenefit.cs`
- iOS `Views/ViewControllers/HourlyBenefits/HourlyBenefitsView.cs`, wired at `NavigationExtensions.cs:38` and
  `AppCoordinator.Navigation.cs:91`
- Android `Views/Fragments/HourlyBenefitListFragment.cs`, wired at `PayLandingPageFragment.cs:200`

**Its contracts are wrong in three ways. Do not copy these:**

- `IHourlyBenefitsManager.cs:14` returns `Task<List<HourlyBenefitsItemViewModel>>` — a Manager returning a
  presentation type.
- `HourlyBenefitsManager.cs:31` formats with `AppStrings` — presentation in the business layer.
- `HourlyBenefitsProxy.cs:28` does `JsonConvert.DeserializeObject<List<HourlyBenefit>>` **straight into the
  entity**, so there is no `HourlyBenefitsResponse` on disk, no `[AutoMap]`, no `SynchronizeDbEntityList`, and
  no cache in that slice at all. It skips manifest steps 1 and 2 entirely.

Read it for the wiring. Take the contracts from `shaping-manager-contracts`.

## Known offenders

**No slice in the repo satisfies the whole manifest**, so there is no file to copy wholesale — the manifest is
the target, not a description of existing code. Of the layer invariants, only ViewModel → Proxy is unbroken
(zero hits). Managers importing `ViewModels` and Managers with no interface are both common; the counts and the
file lists live in `shaping-manager-contracts`, which owns them.

## Verify

- Build all three, in order, because an interface change only fails in the platform projects:
  `dotnet build WinTeam.Mobile.Core/WinTeam.Mobile.Core.csproj`, then the iOS and Android csproj.
- **What the build cannot catch, and this is most of the risk:** an enum member with no `case` compiles; a
  `NavigationExtensions` entry pointing at a view you never wrote compiles; a missing `Bootstrap` line compiles
  and throws `NullReferenceException` on first use. The only real check is to **navigate to the screen on both
  platforms, then navigate away and back once.**
