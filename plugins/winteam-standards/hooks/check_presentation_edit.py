#!/usr/bin/env python3
"""Advisory presentation-layer check for winteam-standards.

Runs as a PostToolUse hook after Edit/Write, and is also imported by sweep_tool_writes.py so the
same checks reach a file written by a Bash heredoc or an MCP tool. Emits advisories as
additionalContext; never blocks, always exits 0 — the same contract as its three siblings.

It owns the presentation axis across *every* extension, which is why it is a separate module from
check_cs_edit.py rather than more branches inside it. That file owns size, parameters, teardown and
entity pairs and is already 769 lines; this one owns the four presentation skills, on markup and on
platform `.cs` alike. The git helpers and the method parser are imported from it, never copied —
the same rule sweep_tool_writes.py follows, and for the same reason.

EVERY CHECK BELOW WAS MEASURED AGAINST THE REPO BEFORE IT SHIPPED. This plugin's design premise is
that a hook flagging correct code gets muted, so the bar is the one is_handler_reference() set in
check_cs_edit.py: a pattern that fires on a legitimate site does not ship, and a false negative is
the right way for an advisory to fail. Backlog at time of writing:

    fillAlpha over an 8-digit ARGB fillColor      0 drawables      -> whenever the file is touched
    UI string literal on .Text/.Title             0 sites          -> per changed line
    hex literal in a layout XML                   1 of 117 files   -> per changed line
    a colour name with no values-night twin       2 of 120 names   -> per changed line
    UIColor.FromRGB / hex in a platform .cs       2 files          -> per changed line
    raw <color red= green= blue=> in a xib        8 of 101 files   -> per changed line
    static styling in a setup method              7 files/14 sites -> per changed line
    raw dp/sp in a layout XML                    83 of 117 files   -> per changed line, and that
                                                                      gate is the only thing making
                                                                      it usable

FIVE CHECKS WERE MEASURED AND DELIBERATELY DROPPED. They are the ones that read as obvious and turn
out to fire on the majority of a correct file, so they are recorded here to stop someone adding
them back. All five are still stated in presentation_brief.py, where a rule costs nothing, and all
five are swept by /winteam-standards:ui-audit, where the user has opted in:

  * "A hex literal in a *drawable*." 120 of 184 drawables carry one, so this is the house style for
    a vector asset, not a defect. The identical check on a *layout* fires on 1 of 117 and is kept —
    the difference between the two numbers is the entire argument, and it is why the hex check below
    is scoped to layout/ and not to Resources/ generally.
  * "A <fontDescription> with no sibling tablet <variation>." 365 of 605 font elements have none.
    A font only needs a variation when its tablet size actually differs, so the majority here is
    correct code.
  * "A @dimen with no values-large override." 65 of 106 names have none, and for the same reason.
  * "An imageset with no dark variant." 88 of 124 imagesets have none, because a template icon
    tinted through @color/Colors.X legitimately needs none. Worse, Xcode writes empty `appearances`
    slots into every Contents.json, so presence of the key proves nothing — only a slot carrying a
    `filename` is real coverage.
  * "An imageset with no width-class/height-class entry." 113 of 124. Same reasoning.

The colours pair is the one that survived the same test — only 2 of 120 names lack a night twin —
which is why values-night is checked and values-large is not. When adding a check here, measure it
against the whole repo first; three of the five above looked obviously right until counted.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_cs_edit

# A storyboard can run to tens of thousands of lines. The regex passes below are linear and cheap,
# but a runaway file must not eat the 35s timeout, and nothing legitimate in this repo is close.
MAX_BYTES = 2 * 1024 * 1024

STYLING = "see the declarative-static-styling skill"
DARK_MODE = "see the checking-dark-mode skill"
TABLETS = "see the sizing-for-tablets skill"
APPSTRINGS = "see the appstrings skill"

ANDROID_RES = "WinTeam.Mobile.Android/Resources/"
IOS_PREFIX = "WinTeam.Mobile.iOS/"
ANDROID_PREFIX = "WinTeam.Mobile.Android/"
PLATFORM_PREFIXES = (IOS_PREFIX, ANDROID_PREFIX)

LAYOUT_RE = re.compile(r"^WinTeam\.Mobile\.Android/Resources/layout[^/]*/.*\.xml$")
DRAWABLE_RE = re.compile(r"^WinTeam\.Mobile\.Android/Resources/drawable[^/]*/.*\.xml$")
IOS_MARKUP_RE = re.compile(r"\.(xib|storyboard)$", re.I)

# --- resource maps -----------------------------------------------------------------------------
#
# All four are built once per process and cached. A hook run reads at most a handful of small
# files; a sweep over 25 changed files would otherwise re-read colors.xml 25 times.

_CACHE = {}

HEX_LITERAL = re.compile(r'"(#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?)"')
ANDROID_COLOR_DECL = re.compile(
    r'<color\s+name="([^"]+)"[^>]*>\s*(#[0-9a-fA-F]{6,8})\s*</color>')
ANDROID_DIMEN_DECL = re.compile(r'<dimen\s+name="([^"]+)"[^>]*>\s*([0-9.]+(?:dp|sp))\s*</dimen>')
# A literal dp/sp value in an attribute. `0dp` is excluded outright: in a ConstraintLayout it is the
# idiomatic "match constraints" sentinel, not a dimension, and it is far and away the commonest
# literal in these files.
DP_LITERAL = re.compile(r'="((?!0dp")[0-9]+(?:\.[0-9]+)?(?:dp|sp))"')


def _read(path):
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            return handle.read()
    except Exception:
        return ""


def _rgb_key(value):
    """A `#RRGGBB` or `#AARRGGBB` string as an uppercase 6-digit RGB key, alpha discarded.

    Alpha is dropped on purpose. The advisory's job is to name the semantic colour that carries this
    hue; an 8-digit literal whose RGB matches `text_primary` should still be told about
    `@color/text_primary`, and the alpha difference is the author's business.
    """
    value = value.lstrip("#").upper()
    if len(value) == 8:
        value = value[2:]
    return value if len(value) == 6 else None


def android_colors(root):
    """`{RRGGBB: [name, ...]}` from values/colors.xml, plus the set of names with a night twin."""
    key = ("android_colors", root)
    if key in _CACHE:
        return _CACHE[key]
    by_rgb, names = {}, set()
    light = _read(os.path.join(root, ANDROID_RES, "values/colors.xml"))
    for name, value in ANDROID_COLOR_DECL.findall(light):
        names.add(name)
        rgb = _rgb_key(value)
        if rgb:
            by_rgb.setdefault(rgb, []).append(name)
    night = set()
    dark = _read(os.path.join(root, ANDROID_RES, "values-night/colors.xml"))
    for name, _value in ANDROID_COLOR_DECL.findall(dark):
        night.add(name)
    _CACHE[key] = (by_rgb, names, night)
    return _CACHE[key]


def android_dimens(root):
    """`{"16dp": [name, ...]}` from values/dimens.xml.

    Keyed by the literal as written, because that is what a layout attribute holds and what the
    advisory has to match. `16dp` and `16sp` are deliberately distinct keys — they are different
    units and swapping one for the other is a real bug.
    """
    key = ("android_dimens", root)
    if key in _CACHE:
        return _CACHE[key]
    by_value = {}
    text = _read(os.path.join(root, ANDROID_RES, "values/dimens.xml"))
    for name, value in ANDROID_DIMEN_DECL.findall(text):
        by_value.setdefault(value, []).append(name)
    _CACHE[key] = by_value
    return by_value


def _component(raw):
    """One asset-catalogue colour component as 0-255, or None.

    Xcode writes these three ways in the same repo: `"0x0E"`, `"0.850"` and `"14"`. Guessing wrong
    only costs a suppressed advisory, so anything unparseable returns None.
    """
    raw = (raw or "").strip().strip('"')
    try:
        if raw.lower().startswith("0x"):
            return int(raw, 16)
        value = float(raw)
    except Exception:
        return None
    if 0.0 <= value <= 1.0 and ("." in raw):
        return int(round(value * 255))
    return int(round(value))


def ios_colorsets(root):
    """`{RRGGBB: [color_name, ...]}` for every .colorset in Assets.xcassets.

    Only the entry with no `appearances` block is indexed — the light value. A xib author needs the
    name whose *light* appearance matches what they are looking at in Interface Builder, and
    indexing the dark values too would suggest a name for the wrong reason.
    """
    key = ("ios_colorsets", root)
    if key in _CACHE:
        return _CACHE[key]
    by_rgb = {}
    base = os.path.join(root, IOS_PREFIX, "Assets.xcassets")
    for dirpath, _dirnames, filenames in os.walk(base):
        if not dirpath.endswith(".colorset") or "Contents.json" not in filenames:
            continue
        name = os.path.basename(dirpath)[: -len(".colorset")]
        try:
            data = json.loads(_read(os.path.join(dirpath, "Contents.json")) or "{}")
        except Exception:
            continue
        for entry in data.get("colors") or []:
            if entry.get("appearances"):
                continue
            components = ((entry.get("color") or {}).get("components")) or {}
            parts = [_component(components.get(c)) for c in ("red", "green", "blue")]
            if any(p is None for p in parts):
                continue
            by_rgb.setdefault("%02X%02X%02X" % tuple(parts), []).append(name)
    _CACHE[key] = by_rgb
    return by_rgb


def _name_hint(names, prefix):
    """`use @color/x` when exactly one name matches, `one of ...` when several do."""
    if len(names) == 1:
        return "%s%s" % (prefix, names[0])
    return "one of %s" % ", ".join("%s%s" % (prefix, n) for n in sorted(names)[:4])


def _touched(changed, line_number):
    return changed is None or line_number in changed


# --- Android layout and drawable ----------------------------------------------------------------

FILL_ALPHA = re.compile(r'(?:android:)?fillAlpha\s*=\s*"([0-9.]+)"')
FILL_COLOR_ARGB = re.compile(r'(?:android:)?fillColor\s*=\s*"#([0-9a-fA-F]{8})"')


def _android_markup(rel, lines, root, changed):
    out = []
    is_layout = bool(LAYOUT_RE.match(rel))
    is_drawable = bool(DRAWABLE_RE.match(rel))
    if not (is_layout or is_drawable):
        return out

    by_rgb, _names, _night = android_colors(root)
    dimens = android_dimens(root)

    for number, line in enumerate(lines, start=1):
        if not _touched(changed, number):
            continue
        stripped = line.strip()
        if stripped.startswith("<!--"):
            continue

        # Layout only. A hex in a drawable is this repo's house style at 120 of 184 files — see
        # the module docstring. The double-alpha check below is the only one a drawable earns.
        for literal in (HEX_LITERAL.findall(line) if is_layout else ()):
            rgb = _rgb_key(literal)
            if not rgb:
                continue
            match = by_rgb.get(rgb)
            if match:
                out.append(
                    "%s:%d hardcodes %s. values/colors.xml already names it — use %s, which resolves "
                    "through values-night for dark mode — %s."
                    % (rel, number, literal, _name_hint(match, "@color/"), DARK_MODE))
            else:
                out.append(
                    "%s:%d hardcodes %s and no name in values/colors.xml carries that value, so there "
                    "is no dark value for it either. Flag the gap and stop — do not invent a colour "
                    "name or a dark hex — %s." % (rel, number, literal, DARK_MODE))

        if is_layout:
            for literal in DP_LITERAL.findall(line):
                match = dimens.get(literal)
                if match:
                    out.append(
                        "%s:%d hardcodes %s. values/dimens.xml already names it — use %s, which "
                        "resolves through values-large on tablet — %s."
                        % (rel, number, literal, _name_hint(match, "@dimen/"), TABLETS))
                else:
                    out.append(
                        "%s:%d hardcodes %s with no matching @dimen. Leave the literal alone unless "
                        "this dimension genuinely differs on tablet — a speculative new dimen looks "
                        "like coverage — %s." % (rel, number, literal, TABLETS))

    # Whole-file, because the two halves of a double-fade are usually on different lines and
    # either one alone is fine. Zero current instances, so this cannot be noise.
    if is_drawable and (changed is None or changed):
        text = "\n".join(lines)
        if FILL_ALPHA.search(text) and FILL_COLOR_ARGB.search(text):
            out.append(
                "%s sets fillAlpha on top of an 8-digit ARGB fillColor. The colour already encodes "
                "its alpha, so the two multiply and the result renders too faint to read. One alpha, "
                "from one source — %s." % (rel, DARK_MODE))
    return out


# --- iOS xib / storyboard -----------------------------------------------------------------------

RAW_COLOR = re.compile(
    r'<color\s+key="([^"]+)"[^>]*\bred="([^"]+)"[^>]*\bgreen="([^"]+)"[^>]*\bblue="([^"]+)"'
    r'(?:[^>]*\balpha="([^"]+)")?')

def _ios_markup(rel, lines, root, changed):
    if not IOS_MARKUP_RE.search(rel):
        return []
    out = []
    by_rgb = ios_colorsets(root)

    for number, line in enumerate(lines, start=1):
        if not _touched(changed, number):
            continue

        for match in RAW_COLOR.finditer(line):
            key = match.group(1)
            parts = [_component(match.group(i)) for i in (2, 3, 4)]
            if any(p is None for p in parts):
                continue
            # A fully transparent colour is `UIColor.clear` — "no background", not a hue. It has no
            # semantic name to reference and needs no dark variant, so advising one is wrong. Found
            # by running this check against a branch whose storyboards use the shape: 10 of its 21
            # raw colours are alpha="0.0", and all of them were correct code.
            if _component(match.group(5)) == 0 and (match.group(5) or "").strip('"') != "":
                continue
            rgb = "%02X%02X%02X" % tuple(parts)
            named = by_rgb.get(rgb)
            if named:
                out.append(
                    "%s:%d sets %s as a raw red/green/blue colour (#%s). Assets.xcassets already "
                    "names it — use <color key=\"%s\" name=\"%s\"/>, which carries the dark "
                    "appearance — %s."
                    % (rel, number, key, rgb, key, sorted(named)[0], DARK_MODE))
            else:
                out.append(
                    "%s:%d sets %s as a raw red/green/blue colour (#%s) and no colourset carries that "
                    "value, so it has no dark appearance. Flag the gap and stop — do not invent a "
                    "colour name or a dark value — %s." % (rel, number, key, rgb, DARK_MODE))

    return out


# --- values/*.xml -------------------------------------------------------------------------------


def _values(rel, lines, root, changed):
    """A colour name added to values/colors.xml with no values-night twin.

    Phrased as a question, not a defect, and that wording is load-bearing: a night entry is required
    only when the value actually *differs* in dark mode, so a name intentionally identical in both
    is correct with no twin. The assertive form would flag correct code.

    Only colors.xml is checked. The identical-looking dimens/values-large check was measured at 65
    of 106 names missing and dropped — see the module docstring.
    """
    if rel != ANDROID_RES + "values/colors.xml":
        return []
    _by_rgb, _names, night = android_colors(root)
    out = []
    for number, line in enumerate(lines, start=1):
        if not _touched(changed, number):
            continue
        for name, _value in ANDROID_COLOR_DECL.findall(line):
            if name not in night:
                out.append(
                    "%s:%d declares @color/%s with no entry in values-night/colors.xml. If it should "
                    "differ in dark mode, add the night value; if it is intentionally identical in "
                    "both, no entry is needed — but never invent the dark hex — %s."
                    % (rel, number, name, DARK_MODE))
    return out


# --- AppStrings ---------------------------------------------------------------------------------

RESX_DATA = re.compile(r'<data\s+name="([^"]+)"')
DESIGNER_PROP = re.compile(r"public\s+static\s+string\s+(\w+)\s*\{")
APPSTRINGS_RESX = re.compile(r"^(.*/)AppStrings\.resx$")
APPSTRINGS_DESIGNER = re.compile(r"^(.*/)AppStrings\.Designer\.cs$")


def _appstrings(rel, lines, root, changed):
    """Keys present in one of the twin files and absent from the other.

    This is the only `appstrings` failure that is mechanically detectable, and it is the one the
    skill names as its main hazard: PublicResXFileCodeGenerator is a Visual Studio design-time tool,
    so `dotnet build` never regenerates Designer.cs and the two files drift in silence. A key in the
    .resx with no property does not compile at the call site; a property with no .resx entry
    compiles and returns null, rendering an empty label.

    Whole-file rather than per-line: the drift is a property of the pair, and the author who added a
    key three edits ago is the one who needs telling.
    """
    resx = APPSTRINGS_RESX.match(rel)
    designer = APPSTRINGS_DESIGNER.match(rel)
    if not (resx or designer):
        return []
    if not (changed is None or changed):
        return []

    directory = (resx or designer).group(1)
    if resx:
        resx_text = "\n".join(lines)
        designer_text = _read(os.path.join(root, directory + "AppStrings.Designer.cs"))
    else:
        designer_text = "\n".join(lines)
        resx_text = _read(os.path.join(root, directory + "AppStrings.resx"))
    if not resx_text or not designer_text:
        return []

    keys = set(RESX_DATA.findall(resx_text))
    props = set(DESIGNER_PROP.findall(designer_text))
    out = []
    missing_props = sorted(keys - props)
    orphan_props = sorted(props - keys)
    if missing_props:
        out.append(
            "%s: %d key(s) in AppStrings.resx have no property in AppStrings.Designer.cs (%s). "
            "`dotnet build` never regenerates that file — hand-add each property in the generated "
            "style or AppStrings.<Key> will not compile — %s."
            % (rel, len(missing_props), ", ".join(missing_props[:5]), APPSTRINGS))
    if orphan_props:
        out.append(
            "%s: %d property(ies) in AppStrings.Designer.cs have no <data> entry in AppStrings.resx "
            "(%s). Each compiles and resolves to null at runtime, rendering an empty label — %s."
            % (rel, len(orphan_props), ", ".join(orphan_props[:5]), APPSTRINGS))
    return out


# --- platform .cs -------------------------------------------------------------------------------
#
# The three checks here have a near-zero backlog, which is what lets them fire on any changed line
# the way the entity-pair checks do rather than needing the method checks' narrowing.

# The one-time setup methods that actually exist in this repo, measured: InitView (46 files),
# InitStylesAndContent (31), ViewWillAppear (23), ViewDidLoad (21), SetupViews (11), OnCreate (10),
# OnViewCreated (9), AwakeFromNib (8), SetupView (2), SetupUI (1). ViewWillAppear is in because a
# static value re-applied on every appearance is the same defect, only louder.
#
# LayoutSubviews and OnSizeChanged are absent on purpose: `CornerRadius = Bounds.Height / 2` is the
# case the skill explicitly blesses, because markup cannot express "half my own runtime height".
SETUP_METHODS = {
    "InitView", "InitStylesAndContent", "ViewWillAppear", "ViewDidLoad", "SetupViews",
    "OnCreate", "OnViewCreated", "AwakeFromNib", "SetupView", "SetupUI",
}

# The Step 1 assignment shapes from declarative-static-styling, both platforms, matched together
# with the target that carries them. One regex rather than two because the target and the property
# have to be adjacent to mean anything: `NavigationItem.LeftBarButtonItem.TintColor` names a
# PascalCase outlet *and* a visual property, and is still not a styling violation — the styled
# object is a bar button a factory built one line earlier, which no markup owns. Matching the whole
# chain in one pass is what tells the two apart.
#
# Three groups of property, because they attach differently:
VISUAL_PROP = r"TextColor|TintColor|Font|BackgroundColor|Typeface|Image|CardElevation"
LAYER_PROP = r"CornerRadius|BorderWidth|BorderColor|ShadowColor|ShadowOpacity|ShadowRadius"
VISUAL_CALL = (r"SetTextColor|SetBackgroundColor|SetImageResource|SetTextSize|SetTypeface"
               r"|SetImageTintList")

# Two things this establishes, both derived from reading all 16 sites it fires on:
#
#   * The target is PascalCase. An outlet is a field or property and is PascalCase in this repo; a
#     control built in the same method is a camelCase local with no markup to move the value into.
#     That is what keeps KioskProfileViewHolder's `new TextView(...)` and WTSnackBar's `snackbar`
#     out, and it costs nothing real — an outlet is never camelCase here.
#   * The only thing allowed *between* target and property is a `FindViewById<...>(...)` call, plus
#     `.Layer` immediately before a layer property. Both reach a view markup owns:
#     `OptedChipView.Layer.BorderWidth` and
#     `StatusChipCardView.FindViewById<ImageView>(...).SetImageResource(...)` are both genuine. Any
#     other intermediate means the styled object came from another object's property.
STYLE_ASSIGN = re.compile(
    r"^\s*(?:if\s*\(.*?\)\s*)?"
    r"([A-Za-z_]\w*)"
    r"(?:\.FindViewById\s*<[^>]*>\s*\((?:[^()]|\([^()]*\))*\))*"
    r"(?:"
    r"\.Layer\.(?:" + LAYER_PROP + r")\s*="
    r"|\.(?:" + VISUAL_PROP + r")\s*="
    r"|\.(?:" + VISUAL_CALL + r")\s*\("
    r")")

# A design-time constant on the right-hand side. This is an allowlist rather than a blacklist of
# dynamic shapes, and that polarity is what makes the check precise enough to ship. Measured
# against all 16 existing assignment sites: it accepts the three real violations in LoginFragment,
# which read `new Color(ContextCompat.GetColor(RequireContext(), Resource.Color.x))` — a fixed
# resource reached through two calls, which any "no method calls" rule would have missed — and it
# rejects every state-driven site, none of which names a resource constant. It also rejects
# `Layer.CornerRadius = Layer.Frame.Height/2`, which is runtime geometry and the case the skill
# explicitly blesses.
CONSTANT_RHS = re.compile(
    r"=.*(?:\bResource\.(?:Color|Drawable|Dimension|Font)\b"
    r"|\bResourceConstant\.(?:Color|Drawable|Dimension)\b"
    r"|\bColors\.[A-Z]"
    r"|\bUIFont\.[A-Z]"
    r"|\bUIColor\.[A-Z])")
# The same shapes as an argument, for the `.SetTextColor(...)` / `SetImageResource(...)` call forms.
CONSTANT_ARG = re.compile(
    r"\((?:[^()]|\([^()]*\))*(?:\bResource\.(?:Color|Drawable|Dimension|Font)\b"
    r"|\bResourceConstant\.(?:Color|Drawable|Dimension)\b)")
# A runtime dependency anywhere on the line disqualifies it outright, whatever else it names.
DYNAMIC_RHS = re.compile(r"\bViewModel\b|\?\s*[^:=]*:|_is[A-Z]|\bIs[A-Z]\w*\b|\bsender\b")

COLOR_IN_CODE = re.compile(
    r"UIColor\.FromRGB\s*\(|Color\.ParseColor\s*\(|\bnew\s+Color\s*\(\s*\d|\"#[0-9a-fA-F]{6}")
# A multi-word literal on a UI-facing property. Two words minimum: a single word is far more often a
# key, a route or a resource name than a sentence, and the skill's own NOT-to-use list is mostly
# single tokens.
UI_TEXT_LITERAL = re.compile(
    r"\.(?:Text|Title|TitleText|Message|Hint|ContentDescription)\s*=\s*\"([^\"]*\s[^\"]*)\"|"
    r"\.Set(?:Title|Text)\s*\(\s*\"([^\"]*\s[^\"]*)\"")
# The skill's "When NOT to use" list, as line-level disqualifiers.
NOT_UI_TEXT = re.compile(
    r"Debug\.|Console\.|Logger|\bLog\b|throw new|nameof\(|Analytics|TrackEvent|"
    r"Resource\.|ResourceConstant\.|AppStrings\.|\{0\}|nameof")


def _has_backing_markup(path):
    """Does this iOS view have markup at all?

    A sibling `.xib` or `.designer.cs` is the test. `.designer.cs` is written only for a type
    Interface Builder owns, so it also catches a controller whose markup is a `.storyboard` under a
    different name. Measured against the sites this check fires on: it admits APIConfiguration,
    PhoneOptUiView, PhoneNumberUiView and RejectedPunchListView, and excludes CustomDateButton — a
    `UIButton` subclass built with `new`, which has no markup to move a font into, so advising the
    move would be wrong rather than merely unhelpful.

    Android needs no equivalent: a Fragment's layout is reached through `Resource.Layout.x` rather
    than a sibling file, and every one of them has one.
    """
    stem = path[: -len(".cs")]
    return os.path.isfile(stem + ".xib") or os.path.isfile(stem + ".designer.cs")


def _method_spans(lines):
    """`[(name, first_line, last_line), ...]` for every method in the file.

    Uses check_cs_edit.parse_methods() rather than a second parser — the README forbids a second
    copy, and its constructor/interface handling is already measured against these projects.
    """
    spans = []
    for name, decl, _body, _params, end, _kind in check_cs_edit.parse_methods(lines):
        spans.append((name, decl, end))
    return spans


def _enclosing_method(spans, line_number):
    """The innermost method containing `line_number`, or None.

    Innermost by widest-first replacement: parse_methods yields outer declarations before the
    members nested inside them, so the last match wins.
    """
    found = None
    for name, start, end in spans:
        if start <= line_number <= end:
            found = name
    return found


def _platform_cs(rel, lines, root, changed):
    if not rel.startswith(PLATFORM_PREFIXES) or not rel.endswith(".cs"):
        return []
    out = []
    spans = None
    styling_applies = (not rel.startswith(IOS_PREFIX)
                       or _has_backing_markup(os.path.join(root, rel)))

    for number, line in enumerate(lines, start=1):
        if not _touched(changed, number):
            continue
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("///"):
            continue

        if COLOR_IN_CODE.search(line):
            extra = ""
            if rel.startswith(IOS_PREFIX):
                extra = (", and on iOS it is resolved once — it will not repaint when the user "
                         "toggles appearance with the screen open, so this needs an asset-catalogue "
                         "appearance entry rather than a code branch")
            out.append(
                "%s:%d builds a colour from a literal in code, so it has no dark value%s. Reference "
                "a semantic colour — @color/x on Android, Colors.X on iOS — or flag the gap; never "
                "invent a dark hex — %s." % (rel, number, extra, DARK_MODE))

        literal = UI_TEXT_LITERAL.search(line)
        if literal and not NOT_UI_TEXT.search(line):
            text = literal.group(1) or literal.group(2)
            out.append(
                "%s:%d assigns the user-facing literal \"%s\" directly. It belongs in "
                "AppStrings.resx with a matching property hand-added to AppStrings.Designer.cs in "
                "the same change — %s." % (rel, number, text, APPSTRINGS))

        if not styling_applies:
            continue
        styled = STYLE_ASSIGN.match(line)
        if not styled or not styled.group(1)[:1].isupper():
            continue
        if DYNAMIC_RHS.search(line):
            continue
        if not (CONSTANT_RHS.search(line) or CONSTANT_ARG.search(line)):
            continue
        if spans is None:
            spans = _method_spans(lines)
        method = _enclosing_method(spans, number)
        if method not in SETUP_METHODS:
            continue
        # The target is deliberately not named. On a chained line it is the *container*
        # (`StatusChipCardView.FindViewById<ImageView>(...)`), not the styled view, and naming the
        # wrong control is worse than naming none — the line number is unambiguous.
        out.append(
            "%s:%d sets a static visual value inside %s(). A value that is the same on every load "
            "belongs in the %s — markup loads first, so this assignment silently overrides it and "
            "any tablet variation on it never applies. Move it there and delete this line — %s."
            % (rel, number, method,
               "storyboard/xib" if rel.startswith(IOS_PREFIX) else "layout XML", STYLING))
    return out


# --- entry point --------------------------------------------------------------------------------

CHECKS = (_android_markup, _ios_markup, _values, _appstrings, _platform_cs)

IN_SCOPE = re.compile(
    r"\.(xib|storyboard)$|"
    r"^WinTeam\.Mobile\.Android/Resources/(?:layout|drawable|values)[^/]*/.*\.xml$|"
    r"(?:^|/)AppStrings(?:\.Designer\.cs|\.resx)$|"
    r"^WinTeam\.Mobile\.(?:iOS|Android)/.*\.cs$")


def advisories_for(path, report_all=False):
    """Every presentation advisory this file earns, or [] when it is out of scope.

    Same contract as check_cs_edit.advisories_for(), so sweep_tool_writes.py can hand it any path
    from `git status` without pre-filtering — including `report_all`, which drops the HEAD
    baseline so /winteam-standards:code-style can report a backlog rather than a regression.
    """
    if not path or not os.path.isfile(path):
        return []
    rel, root = check_cs_edit.repo_relative(path)
    if not root or "/obj/" in rel or "/bin/" in rel:
        return []
    if not IN_SCOPE.search(rel):
        return []
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return []
    except Exception:
        return []

    text = _read(path)
    if not text:
        return []
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    changed = None if report_all else check_cs_edit.changed_line_numbers(rel, root)
    if changed is not None and not changed:
        return []

    out = []
    for check in CHECKS:
        try:
            out.extend(check(rel, lines, root, changed))
        except Exception:
            # One failing check must not cost the advisories from the others. Advisory-only means a
            # bug here degrades to silence, never to a broken edit.
            continue
    return out


# A single edit to a 117-attribute layout should not print thirty lines. Ranked by nothing in
# particular — they arrive in file order — so the cap keeps the earliest, which are the ones nearest
# the top of the file the author is looking at.
MAX_ADVISORIES = 12


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    check_cs_edit.load_thresholds()
    advisories = advisories_for((payload.get("tool_input") or {}).get("file_path") or "")
    if not advisories:
        return 0

    shown = advisories[:MAX_ADVISORIES]
    body = "\n".join("  - %s" % item for item in shown)
    if len(advisories) > MAX_ADVISORIES:
        body += ("\n  - ...and %d more — ask for /winteam-standards:ui-audit --changed for the full "
                 "list." % (len(advisories) - MAX_ADVISORIES))

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "winteam-standards presentation advisories (non-blocking):\n" + body,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
