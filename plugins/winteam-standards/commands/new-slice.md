---
description: Scaffold a new vertical slice — Entity, Proxy, Manager, ViewModel, Bootstrap and platform route wiring
allowed-tools: Bash, Read, Grep, Glob, Write, Edit, Skill
argument-hint: "<DomainName> [--online-only] [--list|--detail] [--with-use-case] [--ios-only|--android-only]"
disable-model-invocation: true
---

Create the files a new feature slice needs, in dependency order, with every unknowable value left as a marked
`TODO` rather than guessed.

Scope: `$ARGUMENTS`

**This is one of two write-capable commands in the plugin**, with `scale-for-tablets`; the rest are audits. That difference is
deliberate and bounded by `## Rules` below — read them before writing anything.

## Scope

| Argument | Effect |
|---|---|
| `<DomainName>` | Required. Singular PascalCase, e.g. `Timesheet`. Names the entity, proxy, manager and folder |
| `--online-only` | No entity, no `[AutoMap]`, no DB cache; the manager passes proxy results through |
| `--list` | Generates `<Domain>ViewModel : WTBaseFeedViewModel<T>` plus a `<Domain>ItemViewModel` (default) |
| `--detail` | Generates a single `<Domain>ViewModel : WTBasePageViewModel`, no item view model |
| `--with-use-case` | Adds a use case. **Requires two Managers to be named**, or refuse |
| `--ios-only` / `--android-only` | Skip one platform. Must be stated in the PR body — see rule 5 |

```
/winteam-standards:new-slice Timesheet
/winteam-standards:new-slice Timesheet --detail --online-only
/winteam-standards:new-slice Timesheet --android-only
```

`building-vertical-slices` is the source of truth for what belongs *inside* each file. This command owns only
the order and the wiring. **Invoke it before you write anything, and if the two disagree, the skill wins.**

## Gather

Read-only. Do all of this before writing a single file, and stop if any check fails.

Substitute the domain name into `D` literally before running the block — the first token of the arguments
with the `--` flags stripped, PascalCase. `$1` is textually replaced in this file before any shell runs, so
a shell-side default or `D="$1"` cannot work here.

```bash
D="<DomainName>"

# 1. Refuse if the slice already exists — never scaffold over real work.
ls -d WinTeam.Mobile.Core/Managers/$D 2>/dev/null && echo "EXISTS: manager folder"
ls -d WinTeam.Mobile.Core/ServerAccess/Proxies/$D 2>/dev/null && echo "EXISTS: proxy folder"
grep -rn "class ${D}Entity\|class ${D}Proxy\|class ${D}Manager" WinTeam.Mobile.Core --include="*.cs"

# 2. Which backend module does this belong to? 11 members exist; there may be no fit.
grep -oE "^\s+[A-Za-z]+,?$" WinTeam.Mobile.Core/Utilities/WinTeamModuleEnum.cs

# 3. Insertion points.
grep -n "RegisterInjections" WinTeam.Mobile.Core/Bootstrap.cs          # block to append inside
tail -3 WinTeam.Mobile.Core/ViewModels/Navigation/NavigationRoutes.cs  # enum, trailing comma present
grep -n "NavigationMapping\|GetRoute" WinTeam.Mobile.iOS/Extensions/NavigationExtensions.cs
grep -n "switch (navRoute)\|case NavigationRoutes" WinTeam.Mobile.iOS/AppCoordinator.Navigation.cs | head -3

# 4. Android has NO single navigation site — 29 fragments carry a NavigationRoutes switch.
grep -rln "case NavigationRoutes\." WinTeam.Mobile.Android/Views/Fragments/ | wc -l
```

Two things you must **ask the user**, because there is no correct default:

1. **Which `WinTeamModuleEnum` member the endpoint lives under**, or whether a new member is needed. Guessing
   this produces a proxy that builds a wrong base URI and fails only at runtime.
2. **Which parent fragment owns the Android navigation `case`.** 29 fragments have one. `PayLandingPageFragment`
   is where `HourlyBenefits` lives, but that is one area among many — the answer depends on where the screen is
   reached from, which only the user knows.

Do not proceed on assumptions for either. Ask, then continue.

## Plan

Print the full plan and **stop for confirmation.** Two lists, no prose:

```
WILL CREATE
  WinTeam.Mobile.Core/Entities/Response/TimesheetResponse.cs        ~12 lines
  WinTeam.Mobile.Core/Entities/TimesheetEntity.cs                   ~18 lines
  ...

WILL APPEND TO  (append-only, no reordering)
  WinTeam.Mobile.Core/Bootstrap.cs                    after line 150, inside RegisterInjections()
  WinTeam.Mobile.Core/ViewModels/Navigation/NavigationRoutes.cs   +1 enum member
  WinTeam.Mobile.iOS/Extensions/NavigationExtensions.cs           +1 dictionary entry
  WinTeam.Mobile.iOS/AppCoordinator.Navigation.cs                 +1 case
  WinTeam.Mobile.Android/Views/Fragments/<ASKED>.cs               +1 case

TODO MARKERS  (5)
  TimesheetProxy.cs:14      endpoint route string — not guessable from the domain name
  TimesheetProxy.cs:18      WinTeamModuleEnum member — confirmed as Timekeeping
  TimesheetEntity.cs:9      [PrimaryKey] — which field is the server-side id?
  TimesheetViewModel.cs:22  screen title — must become an AppStrings key
  TimesheetItemViewModel.cs:15  displayed fields
```

Show the five existing-file edits as a unified diff preview. Then ask. Do not write on an unconfirmed plan.

## Write

Order matters — this is `building-vertical-slices`' manifest, mechanised:

1. `Entities/Response/<D>Response.cs` — plain DTO, no base class. *(skip if `--online-only`)*
2. `Entities/<D>Entity.cs` — `WinTeamBusinessEntityBase`, `[AutoMap(typeof(<D>Response))]`, one `[PrimaryKey]`
   as a `TODO`. *(skip if `--online-only`)*
   **Invoke `response-entity-sibling` before writing rows 1–2.** The scaffold gets the base class and the
   attribute right; that skill is what decides the `[PrimaryKey]`, whether nested properties need `TextBlob`
   companions, and whether this Response is a write-result that should get no Entity at all.
3. `ServerAccess/Proxies/<D>/<D>Proxy.cs` — `WTBaseProxy`, `BuildRequestUri(WinTeamModuleEnum.X, endpoint)`,
   `UriBuilderUtil`, `BuildRequestMessage`, `RestClient.RequestAsync`, `ParseToList<T>()`.
4. `Managers/<D>/I<D>Manager.cs` + `<D>Manager.cs` — `WTBaseManager`. Returns **entities**, not view models.
   Sync-then-read-from-db unless `--online-only`. See `shaping-manager-contracts`.
5. `UseCases/<D>/<Verb><D>UseCase.cs` — *only with `--with-use-case` and two named Managers.*
6. `ViewModels/<D>/<D>ViewModel.cs` (+ `<D>ItemViewModel.cs` for `--list`) — `[ObservableProperty]` and
   `[RelayCommand]`, per `declaring-properties-and-commands`.
7. `Bootstrap.cs` — proxy (concrete), manager (interface → impl), use case if any.
8. `NavigationRoutes.cs` — one member, appended before the closing brace.
9. iOS view + `NavigationExtensions` entry + `AppCoordinator.Navigation` case. *(skip if `--android-only`)*
10. Android fragment + the `case` in the parent fragment the user named. *(skip if `--ios-only`)*

Then build all three csproj files and report the result. **Do not fix a build failure by inventing a value that
should be a `TODO`** — report it instead.

## Rules

1. **Never overwrite. Refuse if any target path already exists**, and name which ones. A partial pre-existing
   slice is a signal to stop and ask, not to merge.

2. **The five edits to existing files are pure appends.** New enum member before the closing brace, new
   dictionary entry after the last one, new `case` before `default:`, new registration at the end of the
   `RegisterInjections()` body. **No reordering, no reformatting, no `using` cleanup, no touching adjacent
   lines.** These files are merge-conflict magnets; a diff that only adds lines is one a reviewer can trust.

3. **Placeholders are marked, never invented.** The endpoint route, the `WinTeamModuleEnum` member, the primary
   key, and every user-facing string are `// TODO:` with the reason. **Never guess a REST route** — a plausible
   wrong one is worse than an obvious blank, because it compiles and 404s at runtime.

4. **Create no `AppStrings` entries.** That is the `appstrings` skill's job and it fires on the edit.
   Emit `// TODO: AppStrings key` and let it handle the resx.

5. **Both platforms, or explicitly neither.** Without `--ios-only`/`--android-only`, generate both. A route in
   the enum handled on one platform only is a silent no-op or a crash on the other. If a flag was passed, print
   a line for the PR body saying which platform was skipped and why.

6. **No use case by default.** Only with `--with-use-case` *and* two Managers named. Three use cases exist in
   the whole repo and all three are debt — see `writing-use-cases`.

7. **The output compiles and renders an empty screen. It is not a feature.** State that in the closing summary,
   with the `TODO` count, so nobody reports the slice as done.

8. **Warn if the tree is dirty.** `git status --porcelain` — if it returns anything, say so before writing:
   mixing scaffold output into unrelated changes makes the diff unreviewable. Do not refuse; just say it.

9. **Never stage or commit.** No `git add`, no `git commit`. Leave everything as working-tree changes.

## Self-test

Read-only assertions against the repo. Run these if the command misbehaves — **if any drifts, assume this
command is stale, not the repo.**

- `HourlyBenefits` is the reference slice and accounts for manifest steps 3, 4, 6, 7, 8, 9, 10 — and
  legitimately **not** 1, 2, or 5: `HourlyBenefitsProxy.cs:28` deserializes straight into the entity, so there
  is no Response sibling and no cache.
- `NavigationRoutes.HourlyBenefits` appears in exactly three wiring sites:
  `WinTeam.Mobile.iOS/Extensions/NavigationExtensions.cs:38`,
  `WinTeam.Mobile.iOS/AppCoordinator.Navigation.cs:91`,
  `WinTeam.Mobile.Android/Views/Fragments/PayLandingPageFragment.cs:200`.
- `RegisterInjections()` spans `Bootstrap.cs:57-151` and its last block is `// TimeClock use cases` at `:147`.
- `WinTeamModuleEnum` has **11** members. `NavigationRoutes` ends with a trailing comma, so appending is clean.
- **29** files under `WinTeam.Mobile.Android/Views/Fragments/` contain `case NavigationRoutes.` — which is why
  the parent fragment is the second of the two things `## Gather` requires you to **ask the user**, rather than
  something to infer.

## How the slice gets finished

1. Fill the `TODO` markers, starting with the endpoint route — nothing downstream is testable until it is real.
2. The auto-firing skills police each file as you edit it: `shaping-manager-contracts` on the manager,
   `appstrings` on every string, `declarative-static-styling` on the views, `keeping-files-small` throughout.
3. `/winteam-standards:code-style --changed` once the files have real bodies.
4. `winteam-standards:senior-reviewer` on the diff before the PR.

One slice per change. If you find yourself running this twice before the first one renders, stop.
