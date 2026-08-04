---
name: sizing-for-tablets
description: >-
  Use when a hardcoded dp/sp/point size, font size or constraint constant enters a layout, storyboard or xib
  in WinTeam.Mobile.Android or .iOS, or when asked to check tablet sizing.
---

# A tablet is a size class, not a second layout

Phone and tablet are two resolutions of the *same* named dimension. A screen sizes correctly on tablet when
every dimension it uses comes from a name that has both values — `@dimen/x` resolved through
`values(-large)/dimens.xml` on Android, and on iOS a `<variation key="heightClass=regular-widthClass=regular">`,
a `SetupFontSizeForCustomButton` call, or a `width-class`/`height-class` asset entry keyed off the same map.

**Android's `dimens.xml` is the size map for both platforms.** iOS has no dimens file, so the iOS work is
always a lookup into the Android one. That is unintuitive and it is load-bearing: an iOS value invented
independently will not match its Android counterpart.

**Nothing fails when this is wrong.** The phone value resolves and the screen renders plausibly and small.
Dark mode is the other axis and a separate skill: `checking-dark-mode`.

## When to use

Fires on the *literal*, not on the finished screen:

- a hardcoded `dp`/`sp` value in an Android layout XML, or set in code;
- a font point size or constraint constant in a storyboard, xib, or view code;
- a new `.imageset` or a new icon on a `UIButton`;
- any request to "check tablet sizing", "add tablet variations", or "check this on iPad".

## When NOT to use

- A dimension already referencing a named `@dimen`, or already covered by a `<variation>` or a
  `SetupFontSizeForCustomButton` call. Do not reprocess these.
- Non-visual code — managers, view model business logic, entities.
- Colors, hex literals, `drawable-night`, `appearances` entries: that is `checking-dark-mode`.

## Rules

1. **Never invent a tablet value.** If `values/dimens.xml` has the name but `values-large/dimens.xml` has no
   override, that is a **gap to flag**, not a number to choose. Picking one is a design decision, and a wrong
   one is invisible to everyone who tests on a phone.

2. **No matching `@dimen` at all means leave the literal alone.** Do not create speculative new dimens to have
   something to reference. An unreferenced name is worse than a literal — it looks like coverage.

3. **Resolve the icon fork before creating any asset.** Ask how the icon reaches its displayed size. An SVG in
   a `UIImageView` sized by explicit constraints rescales losslessly, so it needs a `<variation>` on the
   constraint and **no new asset**. A `UIButton` icon is sized by the asset itself, so it needs real resized
   files. Getting this backwards means either a pile of unnecessary assets or a variation that changes nothing.

4. **Buttons do not take storyboard variations for font size.** Use
   `SetupFontSizeForCustomButton(phoneValue, tabletValue)`. A `<variation>` on a button's font is the trap here
   — it looks configured and does nothing.

5. **`values-large` is the only tablet axis in this repo.** There are exactly three `values*` directories:
   `values`, `values-large`, `values-night`. Do not reference or create a `sw600dp`- or landscape-qualified
   variant; none exists.

**Mechanics** — the dimens lookup, the `<variation>` block shapes, the resized-asset steps, SF Symbols:
[`references/tablet-sizing-runbook.md`](references/tablet-sizing-runbook.md).

## Verify

**The build proves nothing here** — the phone value resolves and renders. Run the screen on both a phone and a
tablet and check:

- **Missing `-large` qualifier.** The phone value is used, so the screen renders plausibly and small.
- **A `<variation>` on a button font**, which silently does nothing — should be
  `SetupFontSizeForCustomButton`.
- **A missing iOS `width-class`/`height-class` entry** silently reuses the phone asset.
- **An icon that grew its frame but not its image** — case B treated as case A.
