---
description: Audit the presentation layer against the winteam-standards theming, sizing, styling and AppStrings rules
allowed-tools: Bash, Read, Grep, Glob
argument-hint: "[paths/dirs to scope to, or --changed; default is repo-wide]"
disable-model-invocation: true
---

Report where the presentation layer breaks the four axes a screen has to satisfy, and rank what is worth
fixing.

Scope: `$ARGUMENTS`

## Scope

| Argument | Scope |
|---|---|
| *(empty)* | Repo-wide — both platform projects plus `AppStrings.resx` |
| `--changed` | Files in the working diff |
| One or more paths | Each token as a file, directory, or glob |

```
/winteam-standards:ui-audit
/winteam-standards:ui-audit WinTeam.Mobile.iOS/Views/ViewControllers/Paychecks
/winteam-standards:ui-audit WinTeam.Mobile.Android/Resources/layout --changed
/winteam-standards:ui-audit --changed
```

**Resolve the scope to a concrete file list first, and count it.** Every figure in the report is derived
from the run itself; there are no recorded repo-wide totals to compare against, so the report states its
own. All four passes honour the scope.

Unlike the other audits in this plugin, the file list here is not just `*.cs`. Each pass names the
extensions it reads, and three of the four read markup.

## The one hard rule

**Report only. Never invent a value.** Three of the four skills behind this command say so explicitly: a
colour name, a dark hex and a tablet dimension are all design decisions, and a wrong one is invisible to
everyone who tests on a phone in light mode. Where a value is missing, say *what* is missing and let the
user decide. Suggesting a plausible number here is how a wrong one gets committed.

This command also holds no `Write` or `Edit`. It is an audit, not a fixer.

## Pass 1 — static values living in code

**Reads:** `WinTeam.Mobile.iOS/**/*.cs`, `WinTeam.Mobile.Android/**/*.cs`.

Find visual properties assigned in a one-time setup method — `InitView`, `InitStylesAndContent`,
`ViewDidLoad`, `ViewWillAppear`, `SetupViews`, `OnCreate`, `OnViewCreated`, `AwakeFromNib` — where the value
is a design-time constant:

```bash
grep -rnE '\.(TextColor|TintColor|Font|BackgroundColor|Typeface|Image)\s*=|Layer\.(CornerRadius|BorderWidth|BorderColor|Shadow[A-Za-z]*)\s*=|\.Set(TextColor|BackgroundColor|ImageResource|TextSize|Typeface)\s*\(|ImageViewCompat\.SetImageTintList\s*\(' \
  --include="*.cs" WinTeam.Mobile.iOS WinTeam.Mobile.Android
```

Then classify each hit, because the raw grep over-reports and the classification is the whole value of this
pass:

- **Report it** when the value is a fixed constant (`Colors.X`, `UIFont.X`, `Resource.Color.x`,
  `ResourceConstant.Drawable.x`, a literal) *and* the target is a markup-backed outlet.
- **Skip it** when the value is state-driven (reads `ViewModel`, a ternary, an `Is*`/`_is*` flag, a
  `Setup(item)` parameter), when it is computed from runtime geometry (`Bounds.Height / 2` in
  `LayoutSubviews`), when the control was built in the same method with `new` (no markup exists to move it
  into), or when the iOS type has no backing `.xib`/`.designer.cs` at all.

**Then look for the expensive case, which grep alone will not show you:** a code assignment that survives
next to markup already setting the same property. Markup loads first, so the code silently wins and any
`<variation>` on the markup value never applies. For each reported hit, open the matching layout XML or
xib and check whether the property is already declared there. A hit that is *also* in markup is the
highest-severity finding this command produces — rank those first and say why.

## Pass 2 — dark mode

**Reads:** layout and drawable XML, xib/storyboard, platform `*.cs`.

1. Hex literals in a **layout** XML, and raw `<color key="..." red=... green=... blue=...>` in a
   xib/storyboard. For each, look the value up in `WinTeam.Mobile.Android/Resources/values/colors.xml` and
   in the `.colorset`s under `WinTeam.Mobile.iOS/Assets.xcassets`. Report the semantic name when one carries
   that value; report the gap when none does.
2. `UIColor.FromRGB`, `Color.ParseColor`, `new Color(<digits>` or a `"#RRGGBB"` literal in `*.cs`. On iOS add
   that a colour resolved in a setup method is resolved once and will not repaint when the user toggles
   appearance with the screen open.
3. `fillAlpha`, or an SVG `fill-opacity`, on a drawable whose `fillColor` is already 8-digit ARGB. The two
   alphas multiply and the result renders too faint to read.
4. Names in `values/colors.xml` with no entry in `values-night/colors.xml`. Present these as questions, not
   defects — a night entry is needed only when the value actually differs.
5. `.imageset`s with no `appearances` entry carrying a **filename**. Xcode writes empty appearance slots into
   every `Contents.json`, so the key's presence proves nothing. Note that a template icon tinted through
   `@color`/`Colors.X` legitimately needs no dark asset, so this list is a set of candidates to confirm, not
   a defect list.

**Hex literals in drawables are the house style here and are not a finding on their own.** Report one only
when it also breaks rule 3, or when the drawable is text-bearing.

## Pass 3 — tablet sizing

**Reads:** layout XML, xib/storyboard, platform `*.cs`.

1. Raw `dp`/`sp` literals in layout XML. Ignore `0dp` — in a `ConstraintLayout` it means "match
   constraints", not a dimension. Look each value up in `values/dimens.xml`: report the `@dimen` name when
   one exists; when none does, say so and **leave the literal alone** — a speculative new dimen looks like
   coverage and is worse than the literal it replaced.
2. `<fontDescription>` elements with no sibling `<variation key="heightClass=regular-widthClass=regular">`.
   Most fonts in this repo have none and that is often correct, so present these as candidates and rank by
   whether the screen is text-heavy.
3. `<variation>` on a **button's** font, which silently does nothing — it needs
   `SetupFontSizeForCustomButton(phoneValue, tabletValue)`.
4. Names in `values/dimens.xml` with no `values-large` override, for any dimension the scope actually uses.
   Same framing as the colours question: a gap only matters if the value should differ.
5. `values-large` is the only tablet axis in this repo. Flag any reference to a `sw600dp`- or
   landscape-qualified variant as broken, because no such directory exists.

**Aggregate this pass per file, worst-first — never emit a flat list.** Most layouts in this project carry a
raw `dp` literal, so several hundred individual findings is unreadable, while file rows ranked by count are a
backlog. This is the same treatment `/winteam-standards:code-style` gives method length, and for the same
reason.

## Pass 4 — AppStrings

**Reads:** platform and Core `*.cs`, `WinTeam.Mobile.Core/Resources/AppStrings*.resx`.

1. Multi-word string literals assigned to `.Text`, `.Title`, `.TitleText`, `.Message`, `.Hint`,
   `.ContentDescription`, or passed to `SetTitle(`/`SetText(`. Exclude the skill's own non-UI list: logging,
   exception messages, `nameof`, analytics and event names, resource and drawable names, route and dictionary
   keys, format specifiers, and anything under a test project.
2. Drift between `AppStrings.resx` and `AppStrings.Designer.cs`: a `<data name="X">` with no
   `public static string X`, or a property with no `<data>` entry. The first does not compile at the call
   site; the second compiles and returns `null` at runtime, rendering an empty label. `dotnet build` never
   regenerates that file, so this drift is silent and permanent until someone looks.
3. Keys present in `AppStrings.resx` and missing from `AppStrings.es.resx` / `AppStrings.fr.resx`. Report the
   count and the keys. Do **not** propose translations — `ResourceManager` falls back to the neutral value,
   and an invented translation is worse than visible English.

## Report

Open with the resolved file count and one line per pass giving its total. Then the findings, most severe
first:

1. A code assignment overriding a value markup already sets (Pass 1) — silent, and the failure the styling
   skill exists to prevent.
2. A double-faded drawable, and a colour or dimension literal for which a semantic name already exists —
   these have a known correct fix.
3. Gaps where no semantic name or tablet value exists. State the gap; propose no value.
4. Candidates to confirm — imagesets and fonts with no variant, which are frequently correct.

Close with what the audit could not determine: **the build proves nothing for any of these four axes.**
Resource resolution falls back silently, so a screen that is unreadable in dark mode or tiny on a tablet
compiles exactly as cleanly as a correct one. Name the screens that need a visual check in both appearances
and on both device classes.
