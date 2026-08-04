---
name: reusing-existing-helpers
description: >-
  Use before writing any helper — formatting, parsing, validating, converting, collection work — or
  before adding a file under an Extensions, Utils, Utilities or Services folder, and when asked whether
  something like it already exists in MobileCore.
---

# Search MobileCore before you write a helper

The cost of a duplicate helper is not the duplicate. It is the **divergence** — two implementations that agree
today, get bug-fixed separately, and quietly disagree six months later.

**The mechanical reason this keeps happening: `MobileCore/` is a git submodule, so `git grep` cannot see it.**

```
git grep MoveItemAtIndexToFront                      → 2 hits
git grep --recurse-submodules MoveItemAtIndexToFront → 3 hits
grep -rn MoveItemAtIndexToFront                      → 3 hits
```

The missing hit is the original, and `MobileCore/src` holds **85 `*Extensions.cs` files** — the fast search
reflex is blind precisely where the answers live.

**There is also a compile-time trap.** 12 files under `MobileCore/src` declare bare `namespace System`, including the
40-member `StringExtensions`. Their extension methods are in scope in every file with `using System;`, so adding
a same-signature method to `WinTeam.Mobile.Core.Extensions` is a **CS0121 ambiguity in only the files importing
both namespaces** — a break that looks random and per-file.

## When to use

Before writing the body, not after. Fires when you are about to:

- type `public static`, or `this ` as a first parameter,
- name a method as a verb plus a framework type — `FormatPhone`, `ParseX`, `IsValidY`, `ToZ`, `Truncate`,
- create a file under `Extensions/`, `Utils/`, `Utilities/`, or `Services/`,
- type the same three or more lines a second time in one session.

## When NOT to use

- A private one-liner with a single call site in one class. Leave it there.
- Anything whose signature names a WinTeam domain type — `PunchType`, `TimeMessage`, `PaycheckDetail`. It belongs
  with its feature; rule 2 explains why that test is reliable.
- View or ViewModel plumbing: bindings, command wiring, activation.
- Response→Entity mapping, which is `[AutoMap]` — see `response-entity-sibling`.

## Rules

1. **The extraction test is two questions, and both must be yes.** (a) Can you write its `///` summary without
   naming a WinTeam screen, module, or domain type? (b) Does it have **two call sites that exist right now?**
   One call site is a method, not a shared helper. A duplicated three-line block is cheaper than a wrong
   abstraction — the expensive failures here are copies drifting, not copies existing.

2. **"Reusable in the future" is a type check, not a prediction.** If every parameter and the return type is a
   BCL or platform type (`string`, `decimal`, `DateTime`, `List<T>`, `Enum`, `TextView`, `UIView`), assume it is
   reusable and search. If any one of them is a WinTeam type, assume it is not, and leave it with the feature.
   The repo backs this up exactly: **all 9 WinTeam extension class names that collide with MobileCore target a
   framework type; none of the domain-typed ones collide.**

3. **Three passes with a tool that can see the submodule, stopping at the first hit.** Name → target type →
   behaviour, as below; use `grep -rn` or the Grep tool, never `git grep`. **Budget: one grep, one find, at most
   one folder listing. Reaching for a fourth command means stop searching and write the method** — a rule that
   costs more than the duplicate it prevents will be ignored, correctly.

4. **Near match: extend, then overload, then wrap. Never copy-and-modify.** Add an optional parameter if the
   default preserves every existing caller exactly; otherwise overload in the same class; if the near match is
   in MobileCore you may not touch it (rule 6), so wrap it. **Tie-breaker: count the call sites you would
   break** — zero, extend it; non-zero, wrap it. Name a wrapper after the **delta**, not with a `WT` prefix:
   `AddWTLinkedText` earned its prefix from a name clash and tells a reader nothing, `AddLinkedTextWithThemeColor`
   does. (`WT*` stays right for a *type* specialising a MobileCore base — `WTBaseManager`, `WTSnackBar`.)

5. **Never add a member to a class name MobileCore already uses.** These 9 collide today: `StringExtensions`,
   `EnumExtensions`, `ListExtensions`, `UIViewExtensions`, `UITextViewExtensions`, `UILabelExtensions`,
   `TextViewExtensions`, `ImageViewExtensions`, `FragmentExtensions`. If the signature already exists there,
   delete yours and add the `using` — or just call it, if that class is in `namespace System`. **A duplicate
   under a *different* method name produces no compiler signal at all**, which is why pass 3 exists.

6. **Never edit anything under `MobileCore/`.** It is a submodule pointing at another repository; a change there
   is a separate PR and is lost on the next `submodule update`. Wrap instead. Corollary: a teammate on an older
   submodule pointer may not have the method you just found, so build all three csproj files, not just Core.

## How to search

```bash
# Pass 1 — by name. grep -rn, NOT git grep: MobileCore is a submodule.
grep -rn "FormatPhoneNumber" --include="*.cs" \
  WinTeam.Mobile.Core WinTeam.Mobile.iOS WinTeam.Mobile.Android MobileCore/src

# Pass 2 — by target type. One file per target type is 100% consistent here, so this is exhaustive.
# Use -iname: WinTeam has UiButtonExtensions.cs and MobileCore has UIButtonExtensions.cs.
find WinTeam.Mobile.Core WinTeam.Mobile.iOS WinTeam.Mobile.Android MobileCore/src \
  -iname "StringExtensions.cs" -not -path "*/obj/*" -not -path "*/bin/*"

# Pass 3 — by behaviour, when you cannot guess the name. ONE folder, from the table below.
grep -rn "public static" --include="*.cs" MobileCore/src/Mobile.Core/Utilities/Extensions
```

**Quote `--include="*.cs"`.** Unquoted, zsh expands it and grep fails with `no matches found`.

Search `MobileCore/src/Mobile.Core/Utilities/Extensions/` **first** — 17 files, the most-missed folder, holding
`StringExtensions` (40 members), `DateTimeExtensions`, `TimeSpanExtensions`, `CurrencyExtensions`,
`DictionaryExtensions`, `IEnumerableExtensions`, `ObjectExtensions`, `ExceptionExtensions`, `HttpExtensions`.
Then as needed: `Mobile.Core.Common.{iOS,Android}/` and `Mobile.Core.Mvvm.{Common,iOS,Droid}/Extensions/`, plus
the ten WinTeam folders — `Core/{Extensions,Utils,Utilities,Services}`, `Android/{Extensions,Utilities,Services}`,
`iOS/{Extensions,Utilities,Services}`.

## Where a new helper goes

| What you wrote | Folder | Name | Registered? |
|---|---|---|---|
| extension on a BCL or platform type | `<Project>/Extensions/<Type>Extensions.cs`, one file per target type | `<Type>Extensions` | no — `public static class` |
| stateless, **no** WinTeam domain knowledge | `Core/Utils/` | `XxxUtil` | no |
| stateless, encodes a WinTeam business rule | `Core/Utilities/` | `XxxUtility` | no |
| needs injected collaborators or user preferences | `Core/Utilities/` | `IXxxUtility` + impl | yes |
| holds state, owns a lifecycle (timer, session, queue) | `Core/Utilities/` | `IXxxManager` + impl | yes, `AsSingleton()` |
| one behaviour, different implementation per platform | interface `Core/Services/<Area>/`, impls `<Platform>/Services/<Area>/` | `IXxx` → `DroidXxx` / `IosXxx` | yes, in **both** platform Bootstraps |
| platform-only, no Core contract | `<Platform>/Utilities/` | `XxxUtil` | only if stateful |

**`Utils` versus `Utilities` is infrastructure versus domain, not legacy versus current** — both received new
files within the last month. `Utils/` holds what would work in any app (`AzureB2C/`, `FeatureFlag/`, `Result.cs`,
`Debouncer.cs`); `Utilities/` holds WinTeam rules and stateful lifecycle owners (`TimeClockUtilities/`, session
inactivity, call log, `JwtUtility`). **Pick the folder first and the suffix follows from it**, which makes the
`Util`/`Utility` coexistence harmless rather than a coin flip. Don't add a fifth `XxxHelper`.

**`static` versus DI is one test: does the output depend only on the arguments?** Yes → `public static class`, no
registration. No — it needs a preference, a token, a connection, or a clock you'd want to fake → instance class,
`[Inject]` properties, Bootstrap registration; see `wiring-dependency-injection`. `HelperFormatUtility` (static,
culture-blind) versus `WinTeamHelperFormatUtility` (injected, preference-aware) is that split done **right** —
but both spell one method name, so a call site doesn't reveal which ran. Name yours for the delta.

## Known offenders

Ranked by how likely you are to hit them:

1. **`Core/Extensions/StringExtensions.cs` (6 members) shadows the MobileCore `StringExtensions` (40 members,
   `namespace System`).** Its `FormatZipCode` blindly inserts a dash at index 5; MobileCore already has
   `IsValidZipCode`, `IsValidUSZipCode` and `ShouldPostalCodeBeFormatted(out string)`, which validate first.
2. **`Core/Extensions/ResponseDataExtensions.cs` clones `ParseToEntity<T>` and `ParseToList<T>` from
   `Core/Extensions/StringExtensions.cs` — in the same folder**, identical apart from `obj.Content` versus
   `obj`. The right shape is one pair on `string` plus `response.Content.ParseToEntity<T>()` at the call site.
3. `MoveItemAtIndexToFront<T>` — `iOS/Extensions/ListExtensions.cs:7` versus MobileCore's
   `Utilities/Extensions/ListExtensions.cs:8`. Identical signatures, different bodies, one caller.
4. **`EnumExtensions.GetEnumMemberValue<T>` versus MobileCore's `GetStringValue(this Enum)`** — same job, same
   class name, different method name, **zero compiler signal.** Only pass 3 catches this class of duplicate.

Four smaller traps: `iOS/Extensions/UiButtonExtensions.cs` has a lowercase `i`, so an exact-name `find` misses
the **two** `UIButtonExtensions.cs` in MobileCore; `Android/Extensions/ResourceExtensions.cs` is a
`public static class` whose whole body is commented out (delete, don't revive); the three
`Core/Utils/CoreLocalization/*.cs` files declare a `WinTeam.Mobile.Core.Utilities` namespace while sitting in
`Utils/`, so folder and namespace disagree; and separately, 12 files under `Core/Utils/` spell the root
`Winteam` with a lowercase `t` (23 across all of `WinTeam.Mobile.Core/`), so a namespace search for the
correct spelling silently misses them. **Don't copy any of them.**

## Verify

- `grep -rn "<yourMethodName>" --include="*.cs" WinTeam.Mobile.Core WinTeam.Mobile.iOS WinTeam.Mobile.Android MobileCore/src`
  returns exactly one definition, and `find … -iname "<Type>Extensions.cs"` shows you didn't add a second file
  for a type MobileCore already covers.
- `dotnet build` on **all three** csproj files. **Unusually for this plugin the build does real work here:** a
  same-signature collision surfaces as CS0121, so a clean build is genuine evidence for rule 6 — but a Core-only
  build proves nothing about the iOS and Android collisions.
- What the build still cannot catch: a duplicate under a different name (offender 4); one in namespaces no single
  file imports together; a stale submodule pointer hiding the method you found; and the case this skill mostly
  exists for — **a helper you wrote inline in a ViewModel and never considered extracting.**
