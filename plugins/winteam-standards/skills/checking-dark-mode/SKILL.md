---
name: checking-dark-mode
description: >-
  Use when a hex literal, UIColor.FromRGB, new Color(...), a drawable, or an .imageset enters
  WinTeam.Mobile.Android or WinTeam.Mobile.iOS, or when asked to check dark mode for a screen or view.
---

# Dark mode is a resource axis, not a styling pass

Light and dark are two resolutions of the *same* reference. A screen is dark-mode-correct when every color it
shows comes from a semantic resource that has both values — `@color/x` resolved through
`values(-night)/colors.xml` on Android, `Colors.X` or an asset-catalog `appearances` entry on iOS.

**Nothing fails when this is wrong.** Resource resolution falls back rather than erroring, so a screen that is
unreadable in dark mode builds exactly as cleanly as a correct one. Only a missing `@color/` reference breaks
the Android compile. This is why the check has to be deliberate.

Sizing for tablets is the other axis and a separate skill: `sizing-for-tablets`. They intersect only in one
place — an iOS icon needing both variants — and the dark-mode runbook says so where it matters.

## When to use

Fires on the *literal*, not on the finished screen:

- a hex literal (`#1565C0`, `#8F091B2A`), `UIColor.FromRGB(...)`, or `new Color(...)` anywhere in a view,
  layout XML, storyboard or xib;
- a new or edited vector drawable under `WinTeam.Mobile.Android/Resources/drawable/`;
- a new or edited `.imageset` under `WinTeam.Mobile.iOS/Assets.xcassets/`;
- any request to "check dark mode", "add a dark variant", or "audit theming" for a screen.

## When NOT to use

- A component already fully wired: an Android drawable whose fill resolves through `@color/x` with a
  `drawable-night` counterpart present, or an iOS imageset whose `Contents.json` already carries a
  `luminosity: dark` appearance entry. Do not reprocess these.
- Non-visual code — managers, view model business logic, entities.
- Phone/tablet sizing, `dimens.xml`, `<variation>` blocks, `SetupFontSizeForCustomButton`: that is
  `sizing-for-tablets`.

## Rules

1. **A text-bearing view never carries a literal color.** `@color/x` on Android, `Colors.X` on iOS. The full
   light/dark palette already exists in both files, so referencing it is usually the whole fix.

2. **Flag, never invent.** If a hex has no match in `values/colors.xml`, you do not have a semantic name and
   you do not have a dark value. Say so and stop. Inventing a color name or a dark hex is a design decision
   wearing engineering clothes, and it will be wrong in a way nobody notices until a user is squinting at it.

3. **Prefer `@color/` over a `drawable-night` copy.** A fill that resolves through a color reference adapts
   with no second file. Duplicating a drawable is the fallback for literal fills, not the default move.

4. **Never stack two alphas.** An 8-digit ARGB color already encodes its alpha; an `android:fillAlpha` or SVG
   `fill-opacity` on top of it double-fades the result into unreadability. One alpha, from one source. This is
   the single most common defect in this area — see the runbook for which one to drop.

5. **On iOS, add an appearance variant — don't branch in code.** A `Contents.json` `appearances` entry is
   resolved by the system on every repaint. A color chosen in `ViewDidLoad` is resolved once and will not
   repaint when the user toggles appearance with the screen open.

**Mechanics** — reading a `fillColor`, the hex-to-name lookup, the ARGB split into `fill` + `fill-opacity`, the
`Contents.json` entry shapes: [`references/dark-mode-runbook.md`](references/dark-mode-runbook.md).

## Verify

**The build proves nothing here** — every failure is a resolution failure and resolution falls back silently.
Run the screen in both appearances and check:

- **Missing `-night` qualifier.** The default is used, so the screen renders plausibly and wrongly.
- **Appearance toggled while the screen is open.** Anything resolved once in code will not repaint.
- **A missing iOS `appearances` entry** silently reuses the light asset.
- **Double transparency.** `fillAlpha` over an already-alpha'd ARGB color renders too faint to read.
