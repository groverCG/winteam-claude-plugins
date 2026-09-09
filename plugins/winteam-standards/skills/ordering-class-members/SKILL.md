---
name: ordering-class-members
description: >-
  Use when adding a property, field, command or method to a class in WinTeam.Mobile.Core, .iOS or .Android, or
  when choosing where in the file a new member goes. Placement only, not size.
when_to_use: >-
  Applies even mid-execution of an already-approved plan that names the file, class or method shapes —
  an approved plan is not an exemption. Applies whichever tool writes the file: Write, Edit, a Bash
  heredoc, `sed -i`, or an MCP server's own file-creation call.
---

# Declare state above behaviour, and a helper below its caller

A reader answers two questions about a class, in this order: what does it hold, and what does it do. When a
property is parked between two methods, the first question no longer has an answer you can scan for — you have
to read the whole file to be sure you have found all the state. `LoginViewModel.cs` is the worked example:
sixteen `[Inject]` properties and nine commands sit at the top exactly as they should, and then `PrivacyText`,
`ErrorText` and `IsBannerShown` appear at lines 279, 291 and 297, below three methods.

The second half costs differently. A private helper called from exactly one place is part of that caller's
story, and when it sits fifty lines away — or worse, above the method that calls it — you read the helper with
no idea why it exists. `dotnet build` cannot see either problem, there is no `.editorconfig` in this repo and no
tracked ReSharper layout pattern, so nothing catches it but this rule.

**This governs members you are writing or adding.** It is not a licence to reorder a file you are only visiting.
`keeping-files-small`, `keeping-core-methods-small` and the `new-slice` command all forbid reordering during a
split, an extraction or a scaffold, and where they apply they win — a diff that moves twenty members is
unreviewable, and behaviour changes hide in it.

## When to use

Before writing the member, while you are choosing the line to put it on. Fires when you are about to:

- add a property, `[ObservableProperty]`, command, field or constant to an existing class
- add a method, and have to decide where it goes relative to the one that calls it
- write a new class from scratch, in any of the three projects

## When NOT to use

- Generated files — `*.Designer.cs`, `AppStrings.Designer.cs`, `obj/` and `bin/`.
- Interface bodies. The order of an `I*Manager`'s declarations is a contract's business, not this rule's.
- Reordering for its own sake, or as part of a split or extraction. See the boundary above.
- `enum` members, and records whose whole body is a positional parameter list.
- Deciding whether a member should exist at all, or how big it should be — that is
  `keeping-core-methods-small`, `keeping-files-small` and `shaping-manager-contracts`.

## The order

Within one type. A nested type is ordered independently, against its own members.

| # | Group | Note |
|---|---|---|
| 1 | Nested types, enums, delegates, events | |
| 2 | `const`, then `static readonly` | |
| 3 | `[Inject]` collaborator properties | Already the idiom — see `wiring-dependency-injection` |
| 4 | Remaining instance fields | Except a backing field; see rule 2 |
| 5 | Properties and commands | `public`, then `protected`, then `private` |
| 6 | Constructor(s) | |
| 7 | Lifecycle overrides | `InitializeAsync`, `OnActivated`, `OnDeactivated`, `Dispose`, `ViewDidLoad`, `OnCreateView` |
| 8 | Everything else: methods | Ordered by the call graph, not by accessibility — see rule 3 |

## Rules

1. **State goes above behaviour.** Groups 1-5 come before group 6. A property added below the constructor or
   below any method is the single most common form of this defect and the one the hook reports.

2. **A backing field rides immediately above its own property**, not down in group 4. This is deliberate and
   already the codebase idiom — `LoginViewModel.cs:170-183` pairs `_biometricTypeDescription` with
   `BiometricTypeDescription`. Do not "tidy" such a pair apart.

3. **Group 8 is ordered by the call graph, not by accessibility.** A public entry point comes first, then the
   private helpers it calls, as one contiguous block directly below it. Keep going down: a helper's own helpers
   follow it. This is why group 8 is not sorted `public` before `private` — doing that would separate every
   caller from everything it calls.

4. **A helper called from exactly one place goes below its caller, never above it.** This is the half the hook
   checks, because it is the half with no honest second reading. When a helper has two or more callers it cannot
   be adjacent to all of them; put it below the first one and stop worrying about it.

5. **Region-grouped static display strings stay where they are.** `declaring-properties-and-commands` blesses a
   region of `public string Title => AppStrings.Title;` computed properties. Those are group 5 members and the
   region is fine — this rule asks where the group sits, not whether it may be wrapped in a region.

6. **A new class gets the order right the first time.** Retrofitting it onto an existing class is a judgment
   call about diff size, and nothing here obliges you to make it.

## Known offenders

64 files declare a property or field below their type's first constructor or method, and 19 hold a single-caller
helper above its caller. Almost all of the first group are platform views that grew a field at the bottom
rather than in the block at the top — `Android/Views/Fragments/Home/HomeFragment.cs` (19),
`Android/Views/Fragments/Biometrics/BiometricsUploadPhotoFragment.cs` (15),
`iOS/CollectionView/BaseCollectionViewSource.cs` (6). `Core/Constants.cs` is the clearest single case: nine
`static readonly` constants appended below `GetBaseUrl`'s switch at line 358, when every other constant in the
file is at the top. On the second axis `Core/ViewModels/TimeLanding/Punches/TimeClockViewModel.cs` holds the
largest cluster, with three.

**That is not a backlog to work through — it is context.** 78 of the repo's 867 non-generated `.cs` files are
involved, so 91% already conform — which is why this is a keep-it-that-way rule rather than a migration.

## Verify

- **The build proves nothing here.** `dotnet build WinTeam.Mobile.Core/WinTeam.Mobile.Core.csproj` compiles a
  class whose members are in any order at all, and there is no analyzer or `.editorconfig` rule behind it.
- Read the class top to bottom and stop at the first method or constructor. Everything above it should be state;
  nothing below it should be.
- For each private method you added, find its callers in the file. One caller means it belongs directly below
  that caller.
- The member-order advisories are non-blocking and fire on the lines you changed. For the whole picture on a
  file or a folder, ask for `/winteam-standards:code-style`.
- A moved member must be a pure move. If the diff shows an edit inside a member you only relocated, split it.
