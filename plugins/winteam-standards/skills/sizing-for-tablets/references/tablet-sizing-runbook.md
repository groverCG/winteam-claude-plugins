# Tablet sizing authoring mechanics

The step-by-step for `sizing-for-tablets`. Read this when you are about to edit a layout, storyboard or asset.
The decisions — the icon fork, and "flag the gap, don't invent a tablet value" — are in the skill.

`WinTeam.Mobile.Android/Resources/values/dimens.xml` and `values-large/dimens.xml` are the canonical size map
for **both** platforms; iOS has no dimens file of its own. `values-large` is the only tablet axis that exists
here. `values-h640dp` also exists, but it is a short-screen height qualifier for kiosk login, and Android ranks
it *above* `values-large`: a name defined in both resolves to the `h640dp` value on a tablet. Never add a name
to `values-large` that `values-h640dp` already defines.

## Android

For any hardcoded dimension in a layout XML or set in code (text size, padding/margin, icon width/height,
corner radius, stroke width):

1. Note the hardcoded value (`20sp`, `16dp`).
2. Search `values/dimens.xml` for a `<dimen>` with that exact value **in the same family** — a text size
   matches typography names (`headline_*`, `subtitle_*`, `body_*`, `button`, `caption`, `overline`,
   `*_text_size`), an icon width/height matches `icon_*`, a corner `corner_*`, spacing `offset_*`. The value
   alone is ambiguous: `14sp` is `body_2` (tablet 22) and also `kiosk_login_disable_text_size` (tablet 24).
3. If found, replace the literal with `@dimen/name`, then check `values-large/dimens.xml` for an override of
   that same name:
   - **Present** → done. Android resolves the tablet override automatically on large-screen configs.
   - **Absent** → flag it as a gap. Do not invent a tablet value.
4. If no matching `@dimen` exists in `values/dimens.xml` at all, leave the value hardcoded — no speculative
   new dimens.

## iOS

Same matching process, cross-referenced against Android's `dimens.xml`.

1. Note the hardcoded value in the storyboard/xib/code (font point size, constraint constant).
2. **Look at the Android counterpart of the same screen first** (see *Porting from the counterpart layout*
   below). The `@dimen` the matching Android element uses is the strongest answer there is. Only when there is
   no counterpart element, search `values/dimens.xml` for a `<dimen>` with that exact numeric value in the
   same family — ignore the unit (`sp`/`dp` vs iOS points).
3. If found, look up the tablet counterpart in `values-large/dimens.xml`, then apply it per element type:

   **Labels and constraint constants** — add a `<variation key="heightClass=regular-widthClass=regular">`
   block wrapping just the changed property. Example from `TaxFormHeader.xib` (`subtitle_2`, 14 → 22):

   ```xml
   <label ...>
       <fontDescription key="fontDescription" type="system" weight="semibold" pointSize="14"/>
       <color key="textColor" name="color_text_secondary"/>
       <variation key="heightClass=regular-widthClass=regular">
           <fontDescription key="fontDescription" type="system" weight="semibold" pointSize="22"/>
       </variation>
   </label>
   ```

   A constraint takes the one-line form, `<variation key="heightClass=regular-widthClass=regular" constant="20"/>`,
   as a child of the `<constraint>` (see Case A below). **Those two — `fontDescription` and constraint
   `constant` — are the only variation shapes this repo's markup uses.** For any other property (stack-view
   `spacing`, insets, content-hugging), there is no in-repo example to mirror; do not hand-author the XML.
   Express the size through a constraint instead, or surface it to the user.

   **Buttons** — do *not* use storyboard variations. Call
   `SetupFontSizeForCustomButton(compactSize, regularSize)`
   (`WinTeam.Mobile.iOS/Extensions/UiButtonExtensions.cs:17`) in `InitStylesAndContent()`, phone value first,
   the `values-large` counterpart second. Reference: `ProfileInfoView.cs`'s `InitStylesAndContent()`, e.g.
   `EnrollNowButton.SetupFontSizeForCustomButton(14f, 22f);`.

4. If no matching `@dimen` exists in Android's `values/dimens.xml`, leave the hardcoded value as-is.

## Icons — resolve the fork first

**Check how the icon reaches its displayed size before creating any asset.**

### Case A — `UIImageView` sized by explicit width/height constraints

The common case for row and cell icons. The source is an SVG, so it rescales losslessly to whatever frame the
constraint produces: **no new asset is needed.** Add a `<variation>` to the constraints, the same as any other
constraint constant, and skip the resized-copies steps entirely.

```xml
<imageView contentMode="scaleAspectFit" image="ic_example_icon"
           translatesAutoresizingMaskIntoConstraints="NO" id="xxx-iv-icon">
    <constraints>
        <constraint firstAttribute="height" constant="12" id="xxx-cn-h">
            <variation key="heightClass=regular-widthClass=regular" constant="20"/>
        </constraint>
        <constraint firstAttribute="width" constant="12" id="xxx-cn-w">
            <variation key="heightClass=regular-widthClass=regular" constant="20"/>
        </constraint>
    </constraints>
</imageView>
```

### Case B — `UIButton` icons, or anything sized by the image's own intrinsic/asset size

A button does not stretch its image to fill its bounds the way a constrained `scaleAspectFit` `UIImageView`
does, so growing the button's frame via `<variation>` alone will not grow the icon. Here you do need
differently-sized assets:

1. Locate the `.imageset` in `WinTeam.Mobile.iOS/Assets.xcassets/`.
2. Create resized SVG copies (`<name>_larger.svg`) for the regular×regular size class. Change only the root
   `width`/`height` to the `values-large/dimens.xml` icon-size counterpart (e.g. `icon_medium` 24dp phone →
   34dp tablet), and **keep the `viewBox`**. The `viewBox` is the drawing's coordinate space, so scaling it
   too leaves the icon the same size. The
   `icon_*` scale — `icon_extra_small` through `icon_extra_large` — is overridden in `values-large` for
   every step, so the tablet counterpart always exists for these.
3. Register them in `Contents.json` with `width-class` **and** `height-class` both set to `"regular"` — that
   pair is the tablet trait combination. Mirror the regular×regular entries in
   `ic_logout_filled.imageset/Contents.json`, combining them with `appearances` when the icon has a dark
   variant (that half is `checking-dark-mode`). That file also holds height-only and width-only entries
   (` 1.svg`/` 2.svg`). Those are phone-size copies Xcode generates for its single-regular slots, and they are
   not required.
4. **SF Symbols have no `.imageset` to duplicate.** If the icon is `UIImage.GetSystemImage(...)`, pass a
   trait-aware `UIImageSymbolConfiguration` point size in code instead — SF Symbols scale via point-size
   configuration, not asset variants. This mirrors the phone/tablet split `SetupFontSizeForCustomButton` uses
   for text.

## Porting from the counterpart layout

The same screen almost always exists on both platforms, and the Android one usually already references
`@dimen` names. Matching element-to-element beats matching by number, because it carries the *intent*.

1. **Pair the files by name.** Strip the platform suffixes and compare stems: `ScheduleViewCell.xib` ↔
   `item_my_schedule.xml`, `FooViewController` ↔ `fragment_foo.xml`, `FooCell`/`FooRowView` ↔ `item_foo*.xml`.
   If more than one candidate fits, ask which one — a wrong pair ports wrong numbers with full confidence.
2. **Pair the elements by role, then order.** Match a label to the `TextView` showing the same bound value or
   `AppStrings` key (the `.cs`/fragment binding tells you which), a container's padding to the same
   container's padding, an icon to the `ImageView` with the same drawable name. Fall back to visual order only
   when roles agree.
3. **Take the Android element's `@dimen`.** If it has a `values-large` override *and the same phone value*,
   that is the tablet value for the iOS element. If the phone values differ (13pt on iOS, `body_2` 14sp on
   Android), the platforms already disagree. That makes it a gap: offer the counterpart's tablet value as a
   suggestion, and report the mismatch. If the Android element uses a literal, or a dimen with no override,
   the iOS element is a gap too.

## Adding a user-supplied tablet dimen pair

When the user supplies a tablet value — never otherwise — record it on **both** platforms so they stay
aligned:

1. **Check usage of the existing name before overriding it.** `grep -rn "@dimen/offset_12"` across
   `Resources/layout`, `Resources/drawable` and `Resources/values*`. If anything outside the screen being
   fixed uses it, do not add it to `values-large` — that resizes every one of those screens on tablet.
2. **Otherwise create a screen-scoped pair.** Name it `<screen>_<element>_<property>` in snake_case
   (`my_schedule_badge_padding_vertical`), using the screen/layout stem. Put the phone value in
   `values/dimens.xml` and the user's tablet value in `values-large/dimens.xml`, each under a
   `<!-- My Schedule -->` group comment matching the existing groups. The phone value may itself reference
   an existing name (`@dimen/offset_8`) so the phone side does not drift.
3. **Never add to `values-large` a name `values-h640dp` defines** — it would be shadowed.
4. **iOS takes the same number** as a `<variation>` on the counterpart element. Android's `dimens.xml` is
   still the record; the iOS variation is a lookup into it. Sometimes there is no Android property to record
   the value under: the phone values already differ, or Android has no such property (an icon sized
   implicitly by a button's padding). Then the iOS variation stands alone, and it is listed in the report as an
   iOS-only design decision. Do not create an unreferenced dimen to hold it.
