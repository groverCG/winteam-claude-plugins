# Dark-mode authoring mechanics

The step-by-step for `checking-dark-mode`. Read this when you are about to edit an asset. The decisions —
which things need checking, and "flag it, don't invent it" — are in the skill.

## Text colors, both platforms

Every `TextView`/`UILabel` (or anything else with a `.Text`/`.Title`/attributed-string color) must resolve its
color through a semantic resource — `@color/x` on Android, `Colors.X` on iOS — never a literal hex or
`UIColor.FromRGB(...)`/`new Color(...)`. `colors.xml` (Android) and `Colors.cs` (iOS) already carry the full
light/dark palette, so referencing them is normally enough on its own. Replace a literal with the matching
entry from those files; if nothing matches, flag it.

## Android icons

1. Open the vector drawable in `WinTeam.Mobile.Android/Resources/drawable/`. Read each `<path>`'s
   `android:fillColor`.
   - **Already `@color/xxx`**: it auto-adapts via `values-night/colors.xml` — nothing to do, skip this icon.
   - **A literal hex** (e.g. `#1565C0`, or an 8-digit ARGB like `#8F091B2A`): continue.
2. Search `WinTeam.Mobile.Android/Resources/values/colors.xml` for a `<color>` whose value matches that hex
   exactly (case-insensitive). **If nothing matches, flag it** — do not guess a name or invent a color entry.

   **A hex often maps to more than one name, so the match is rarely unique.** `#1565C0` is both
   `primary_main` and `login_tidal_ocean_blue`; `#FFFFFF` carries five names. Pick between them by scope,
   not by file order:
   - Prefer the **role** name (`primary_main`, `error_main`, `text_secondary`) for anything general.
   - Take a **feature-scoped** name (`login_*`, `splash_*`, `animated_dialog_*`) only when the drawable
     belongs to that feature.
   - Then confirm the name you picked actually has a `values-night/` override (step 3). If it does not but
     a co-named alternative does, you picked the wrong one.
3. Look that same name up in `values-night/colors.xml` to get the dark-mode hex.
4. Copy the drawable into `WinTeam.Mobile.Android/Resources/drawable-night/` under the **same filename**,
   replacing the fill hex with the night hex from step 3. Android's qualifier system picks it automatically in
   dark mode — no code changes.
5. **Avoid double transparency.** If the original path has `android:fillAlpha="0.NN"`:
   - night hex is 8-digit ARGB (already encodes alpha) → **drop `fillAlpha`** in the night copy; stacking both
     double-fades it.
   - night hex is plain opaque 6-digit → **keep** the original `fillAlpha`.

## iOS icons

1. Open the `.svg` inside its `.imageset` (`WinTeam.Mobile.iOS/Assets.xcassets/<name>.imageset/`). Read the
   `<path>`'s `fill="#XXXXXX"` and, if present, `fill-opacity="0.NN"`.
2. Android's `colors.xml` is the canonical color map — iOS has no equivalent file, and `Colors.cs` carries the
   palette for *code* references but not the hex-to-name lookup. So cross-reference the hex against
   `values/colors.xml` for the name, then read the dark counterpart from `values-night/colors.xml`.
   - If the matched Android color is 8-digit ARGB, split it: the low 6 digits become the SVG `fill`, and the
     alpha byte (the first two, ARGB) becomes `fill-opacity` (`alpha / 255`, so `0x8F` ≈ `0.56`). This is how
     `ic_open_in_new.imageset` is authored (`fill="#091B2A" fill-opacity="0.56"`) — match that style.
3. Duplicate the SVG inside the same `.imageset` under a new filename (e.g. `<name>_dark.svg`), with the fill
   (and `fill-opacity`, per step 2) swapped to the dark variant.
4. Register it in the imageset's `Contents.json` alongside the existing entry, with an `appearances` array:
   ```json
   {
     "filename" : "<name>_dark.svg",
     "idiom" : "universal",
     "appearances" : [
       { "appearance" : "luminosity", "value" : "dark" }
     ]
   }
   ```
5. **Avoid double transparency** the same way: don't let a baked-in `fill-opacity` from the original SVG stack
   with the alpha you are applying via step 2's ARGB split. The dark variant's `fill-opacity` comes from the
   matched color, not from both.

## When the icon needs tablet variants too

The two axes multiply on iOS: an icon needing both a dark and a tablet variant needs up to 4 files
(light-phone / dark-phone / light-tablet / dark-tablet). The `appearances` key combines with
`width-class`/`height-class` keys on the same `Contents.json` entry.

**`ic_logout_filled.imageset` is the fully-worked reference** — all 8 combinations enumerated. Read its
`Contents.json` before touching any icon that needs both. The tablet half of the work is
`sizing-for-tablets`.
