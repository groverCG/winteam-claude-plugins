---
description: Apply tablet sizes to a screen from the Android size map, port them to iOS markup, and ask wherever no tablet value exists
allowed-tools: Bash, Read, Grep, Glob, Write, Edit, Skill, AskUserQuestion
argument-hint: "[paths | --changed] [--ios-only | --android-only]"
disable-model-invocation: true
---

Make a screen built and tested on a phone size correctly on a tablet. Every value written traces to
`values-large/dimens.xml` or to an answer from the user. Nothing is guessed.

Scope: `$ARGUMENTS`

**This is one of two write-capable commands in the plugin**, with `new-slice`. It is bounded by `## Rules`
below — read them before writing anything.

## Scope

| Argument | Scope |
|---|---|
| One or more paths | Each token as a file, directory or glob — a layout XML, xib, storyboard, or the `.cs` view behind one |
| `--changed` | Layout XML, xibs and storyboards in the working diff, plus the markup behind any changed view `.cs` |
| `--ios-only` / `--android-only` | Skip the counterpart platform. Without it, **both platforms are in scope** |

```
/winteam-standards:scale-for-tablets WinTeam.Mobile.iOS/Views/Cells/Schedule
/winteam-standards:scale-for-tablets WinTeam.Mobile.Android/Resources/layout/fragment_my_schedule.xml
/winteam-standards:scale-for-tablets --changed
```

An empty argument is refused — a repo-wide fixer is a thousand questions. Ask for
`/winteam-standards:ui-audit` to find the screens worth fixing first.

## Step 1 — Load the rules

Invoke `winteam-standards:sizing-for-tablets` and `winteam-standards:declarative-static-styling`, then read
`sizing-for-tablets`' `references/tablet-sizing-runbook.md` in full. The runbook holds the mechanics this
command applies — the variation shapes, the porting procedure, the dimen-pair procedure. **If the skill and
this command disagree, the skill wins.**

## Step 2 — Gather (read-only)

1. **Resolve the scope to files and count them.** A `.cs` view expands to its `.xib`/storyboard scene or its
   layout XML; a markup file brings its `.cs` along, read-only for now.
2. **Pair each screen with its counterpart on the other platform**, by the runbook's *Porting from the
   counterpart layout*. State every pairing in the output. If a pairing is ambiguous, ask with
   `AskUserQuestion` before continuing. Unless `--ios-only`/`--android-only`, the counterpart is in scope too.
3. **Build the size map** from `WinTeam.Mobile.Android/Resources/values/dimens.xml`, `values-large/dimens.xml`
   and `values-h640dp/dimens.xml`: name → phone value, tablet value or *none*, family (text, icon, corner,
   offset, screen-specific).

## Step 3 — Inventory

List every size-bearing value in scope — **fonts and spacing alike**. Spacing is not optional; it is where the
size map has the most gaps.

- **Android:** `textSize`, padding/margin (all sides), `layout_width`/`layout_height`, `cornerRadius`,
  `strokeWidth`, icon sizes. Skip `0dp`, `match_parent`, `wrap_content`.
- **iOS:** `fontDescription pointSize`, constraint `constant` (margins, spacing, fixed widths and heights),
  icon image-view sizes, button fonts, corner radius (`layer.cornerRadius` runtime attribute or
  `Layer.CornerRadius =` in code). Skip a constraint with no `constant` and one whose `constant` is `0`.
- **A drawable behind an in-scope layout** (a shape's padding or radius) is inventoried but **report-only**,
  because drawables are usually shared. Grep its usage and list the other screens it would change.
- Name an element by its id and outlet / `@+id`; an element with no id is named by line number and tag.
- **Already scaling — skip:** an `@dimen` with a `values-large` override, an element that already has a
  `heightClass=regular-widthClass=regular` variation, a button already given `SetupFontSizeForCustomButton`.
- **Coupled sizes.** Some sizes only make sense together. They form one unit, and nothing in a unit is applied
  until every part of it is resolved. Never mark any of them "out of scope":
  - a font and a fixed `height`/`width` on the same label or `TextView` — a 24pt font in a 25pt frame clips;
  - a fixed-height row or container and everything inside it — text, buttons, icons;
  - a button's size, its padding, and the icon inside it. On Android the icon renders at
    size − 2 × padding;
  - a square's width and height.
- **Code that will defeat markup.** Grep the paired `.cs` setup methods for size assignments (`.Font =`,
  `UIFont.*SystemFontOfSize`, `.SetTextSize(`, `.Constant =`, `Layer.CornerRadius =`,
  `UIUserInterfaceIdiom.Pad ?`). A code line that
  sets a value markup also sets wins at runtime, and the variation you add will never apply.

## Step 4 — Resolve

For each item, take the first rule that answers, and **record which one did**. Android's `dimens.xml` is the
size map, so the two platforms resolve differently. iOS markup is never a source for Android.

**Android item:**

| # | Source | Result |
|---|---|---|
| A1 | It already references an `@dimen` with a `values-large` override | Already scaling — skipped in Step 3 |
| A2 | A literal, and exactly one tablet value holds across every same-family dimen with this phone value | Replace it with that `@dimen` |
| A3 | Anything else | **Unresolved → Step 5** |

**iOS item:**

| # | Source | Result |
|---|---|---|
| I1 | The counterpart element uses an `@dimen` with a `values-large` override, **and its phone value equals this one** | Use it. This is the "port Android → iOS" path. Resolve the Android side first, so an A2 result counts here |
| I2 | **No counterpart element exists**, and exactly one tablet value holds across every same-family dimen with this phone value | Use it |
| I3 | Anything else | **Unresolved → Step 5** |

Rules A3 and I3 cover these cases:
- the counterpart uses a literal, or a dimen with no override (the runbook: "the iOS element is a gap too");
- the counterpart's phone value differs from this one (13pt here, `body_2` 14sp there);
- same-family candidates disagree;
- there is no dimen at all;
- a dependent size.

A phone-value mismatch is also a cross-platform inconsistency. Report it whatever the user answers.

**What is not a source**, even when it looks like one:

- **Another iOS file.** A look-alike cell's variations are someone's earlier choice, not the size map. It may
  appear as a *suggestion* in a question; it is never applied as an answer.
- **A step or a ratio.** "+8pt like the others", "×1.5", "the next step up" are inventions with arithmetic.
  13pt has no dimen; it does not become 21pt because 14 became 22.
- **What the text needs.** "~29pt tall at 24pt, so ~32" is a design decision. Ask.

## Step 5 — Ask

Use `AskUserQuestion`, at most four questions per call. Ask **one question per answer unit**, not per element.
An answer unit is everything that one number will land in: a phone value on one screen that maps to the same
Android counterpart, across both platforms. For example, three iOS constraints and one Android `paddingVertical`
can all be `offset_8`. Each question names:

- every file and line in the unit, and each element — id plus outlet / `@+id`, or line and tag;
- the property and its phone value;
- why it is unresolved, in one clause — "offset_8 has no values-large override".

Ask a coupled unit's parts in the same call, back to back, and state what they produce together. For example:
"with 54 and 20, the Android icon renders at 54 − 2×20 = 14dp, smaller than the phone's 20dp". A square's
width and height are one question.

**Options**, in this order (`AskUserQuestion` needs at least two):

1. **Keep phone value** — no tablet change. This is a legitimate answer, not a fallback.
2. **Up to two suggestions**, each labelled with where it came from:
   - the counterpart's tablet value when only the phone values differed (`body_2 → 22`);
   - a same-family override whose *phone* value is between half and double this one, inclusive, and whose
     *tablet* value is larger than this phone value (`offset_16 → 27` for a 12; never for a 3; never
     `offset_40 → 46` for a 48);
   - a look-alike screen's variation (`TimekeepingRecordViewCell uses 21`).
   For a dependent height, **"change to greaterThanOrEqual"** is a suggestion too.
3. If there is no suggestion that qualifies, the second option is **"Leave for design"**. That leaves the
   value unchanged and lists it under the report's design decisions.
4. *Other* is added automatically for a custom value.

After an answer, if other unresolved items in scope share the same family and phone value, ask once whether
to reuse it for all of them. **Never write a value the user did not choose.**

**A case-B icon** (a button icon, sized by its asset) gets its own question here, before the preview. The
question names the imageset, the files it would add, and the icon size the other platform ends up at. The
answer decides whether its row in the preview says "assets" or "unchanged".

Family, for suggestions: a button's or row's own size is `offset_*`, and an icon's size is `icon_*`.

## Step 6 — Preview

Before writing anything, print one table per file:

| Element | Property | Phone | Tablet | Source | Lands in |
|---|---|---|---|---|---|

`Source` is the counterpart `@dimen`, the dimens name, or "user". `Lands in` is the markup file, or `.cs` with
the reason markup cannot hold it. Show a font and its dependent size on adjacent rows; they are applied
together or not at all. Then `AskUserQuestion`: apply all / choose items / cancel.

## Step 7 — Apply, markup first

- **Android:** replace the literal with the `@dimen`. For a user-supplied value, follow the runbook's *Adding
  a user-supplied tablet dimen pair*. Check the existing name's usage first. If any other screen uses it,
  create a screen-scoped pair in `values/` and `values-large/` instead of overriding the shared name. A name
  `values-h640dp` defines never gets a `values-large` entry.
- **iOS:** a `fontDescription` variation on labels, a `constant` variation on constraints — the runbook's
  shapes, exactly. A dependent height constraint gets its own `constant` variation, or is replaced by a
  `greaterThanOrEqual` relation if the user chose that.
- **Any other markup property** (stack-view `spacing`, insets): there is no in-repo variation to mirror. Do not
  hand-author one. Ask whether to express it as a constraint, or leave it and report it.
- **Code, only where markup cannot hold the value:**
  - a button font → `SetupFontSizeForCustomButton(phone, tablet)` in `InitStylesAndContent()`;
  - an SF Symbol → a trait-aware `UIImageSymbolConfiguration` point size;
  - a view built in code with `new`, which has no markup;
  - a corner radius set in code, because a runtime attribute takes no variation. Branch it on the size class,
    as `SetupFontSizeForCustomButton` does;
  - a size that genuinely changes with runtime state.
- **A code line overriding markup** found in Step 3: move its value into markup and delete the line, per
  `declarative-static-styling`. If it is state-driven, leave it and ask. A `UIUserInterfaceIdiom.Pad ? a : b`
  in a view that has a xib is migrated to a variation only if the user picks it in the preview.
- **A case-B icon:** create the resized assets only if its Step 5 question was answered yes. "Apply all" in
  the preview is not that yes. Follow the runbook.

## Step 8 — Verify

```bash
xmllint --noout <every touched .xml / .xib / .storyboard>
dotnet build WinTeam.Mobile.Android/WinTeam.Mobile.Android.csproj
dotnet build WinTeam.Mobile.iOS/WinTeam.Mobile.iOS.csproj
```

The Android build catches a missing `@dimen`, and the iOS build compiles the xibs. **Neither proves the
sizing.** A phone value resolves and renders on a tablet with no error, and a variation that is overridden in
code compiles cleanly. Re-grep the touched `.cs` for the Step 3 patterns, then name every screen to check on
an iPad simulator and an Android tablet emulator, in both orientations.

**If `winteam-device-testing:verifying-screens-on-devices` is among your available skills**, invoke it with the
touched iOS files once the builds pass, and fold its report into yours. It runs the iOS checks on a phone and a
tablet simulator. The Android screens stay on the manual list.

**Otherwise**, keep the manual list as it is, and add one line: the optional `winteam-device-testing` plugin can
run the iOS checks automatically (see its README).

## Report

1. Files in scope, and the pairings used.
2. The changes, grouped by source: counterpart `@dimen`, dimens lookup, the user's answer.
3. Each value the user decided, so the PR reviewer can see which numbers are design decisions.
4. Anything left unchanged, with the reason:
   - "kept phone value" by choice;
   - "left for design";
   - a property with no variation precedent;
   - a declined case-B asset;
   - a shared drawable.
5. Cross-platform inconsistencies noticed along the way, such as a phone-value mismatch or a bold label on one
   side only, and the same clipping pattern on a look-alike screen. Report these only; don't fix them.
6. The build results, and the visual checks: those run by `winteam-device-testing`, with its findings, and
   those still owed.

## Rules

1. **Never invent a value.** Every tablet number traces to `values-large/dimens.xml` or to an answer. A
   sibling screen, a step, a ratio and a text-height estimate are not sources.
2. **Markup first.** Code only for the cases listed in Step 7, each stated in the preview.
3. **Write only in scope:**
   - the in-scope markup;
   - the paired `.cs`, for Step 7's code cases;
   - the `values*/dimens.xml` files;
   - an `.imageset`, after its own yes.

   Nothing else — not drawables, not look-alike screens.
4. **Preview before writing.** Nothing is written until the user picks *apply* in Step 6.
5. **`values-large` is the only tablet axis.** No `sw600dp`, no landscape qualifiers, no `layout-large`
   copies.
6. **Never stage or commit.**
