# Tablet sizing authoring mechanics

The step-by-step for `sizing-for-tablets`. Read this when you are about to edit a layout, storyboard or asset.
The decisions — the icon fork, and "flag the gap, don't invent a tablet value" — are in the skill.

`WinTeam.Mobile.Android/Resources/values/dimens.xml` and `values-large/dimens.xml` are the canonical size map
for **both** platforms; iOS has no dimens file of its own. There are only three `values*` directories —
`values`, `values-large`, `values-night` — so `values-large` is the only tablet axis that exists here.

## Android

For any hardcoded dimension in a layout XML or set in code (text size, padding/margin, icon width/height,
corner radius, stroke width):

1. Note the hardcoded value (`20sp`, `16dp`).
2. Search `values/dimens.xml` for a `<dimen>` with that exact value.
3. If found, replace the literal with `@dimen/name`, then check `values-large/dimens.xml` for an override of
   that same name:
   - **Present** → done. Android resolves the tablet override automatically on large-screen configs.
   - **Absent** → flag it as a gap. Do not invent a tablet value.
4. If no matching `@dimen` exists in `values/dimens.xml` at all, leave the value hardcoded — no speculative
   new dimens.

## iOS

Same matching process, cross-referenced against Android's `dimens.xml`.

1. Note the hardcoded value in the storyboard/xib/code (font point size, constraint constant).
2. Search `values/dimens.xml` for a `<dimen>` with that exact numeric value — ignore the unit (`sp`/`dp` vs
   iOS points).
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
2. Create resized SVG copies for the regular×regular size class, scaling `width`/`height`/`viewBox` by the
   `values-large/dimens.xml` icon-size counterpart (e.g. `icon_medium` 24dp phone → 34dp tablet). The
   `icon_*` scale — `icon_extra_small` through `icon_extra_large` — is overridden in `values-large` for
   every step, so the tablet counterpart always exists for these.
3. Register them in `Contents.json` with `width-class` **and** `height-class` both set to `"regular"` — that
   pair is the tablet trait combination. Mirror `ic_logout_filled.imageset/Contents.json` exactly, including
   combining with `appearances` if the icon also needs a dark variant (that half is `checking-dark-mode`).
4. **SF Symbols have no `.imageset` to duplicate.** If the icon is `UIImage.GetSystemImage(...)`, pass a
   trait-aware `UIImageSymbolConfiguration` point size in code instead — SF Symbols scale via point-size
   configuration, not asset variants. This mirrors the phone/tablet split `SetupFontSizeForCustomButton` uses
   for text.
