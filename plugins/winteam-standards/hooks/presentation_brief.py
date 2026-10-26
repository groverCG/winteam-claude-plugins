#!/usr/bin/env python3
"""Pre-brief for winteam-standards' presentation-layer rules.

Runs as a PreToolUse hook before Edit/Write. Emits the rules for the markup file about to be
authored as additionalContext, so they land *before* the write rather than as a fix-up advisory
afterwards. Never blocks, always exits 0.

Why this exists: the four presentation skills — declarative-static-styling, checking-dark-mode,
sizing-for-tablets, appstrings — were not firing on the work that needed them, and the cause was
structural rather than a wording problem. All three of this plugin's original hooks return early
on anything that is not a `.cs` file, so the surface these four skills actually govern — 101 xibs
and storyboards, 117 layout XMLs, 185 drawables, the asset catalogue and AppStrings.resx — had no
deterministic coverage at all. A skill description only competes for attention at turn start; by
the time a screen is being restyled the model is mid-execution. This is the same argument, and the
same fix, that entity_pair_brief.py already applies to the entity/response pair.

Three scoping decisions are load-bearing, and they mirror its sibling deliberately:

  * Path match only, no file parsing. On a Write the target may not exist, and on an Edit the
    content on disk is the *pre*-edit state, so neither is worth reading here. Everything stateful
    belongs in check_presentation_edit.py, which runs after the write and can see the result.
  * One brief per write, first match wins. A xib and a drawable have almost nothing in common, and
    emitting every rule on every markup write is how a hook becomes wallpaper.
  * Each brief names the skill to invoke. A hook cannot invoke a skill itself — injected context is
    the whole lever — so the brief has to carry both the rule and the pointer.
"""
import json
import os
import re
import sys

IOS_MARKUP_RE = re.compile(r"\.(xib|storyboard)$", re.I)
LAYOUT_RE = re.compile(r"(^|/)WinTeam\.Mobile\.Android/Resources/layout[^/]*/.*\.xml$")
DRAWABLE_RE = re.compile(r"(^|/)WinTeam\.Mobile\.Android/Resources/drawable[^/]*/.*\.xml$")
VALUES_RE = re.compile(r"(^|/)WinTeam\.Mobile\.Android/Resources/values[^/]*/.*\.xml$")
ASSETS_RE = re.compile(r"(^|/)WinTeam\.Mobile\.iOS/Assets\.xcassets/")
APPSTRINGS_RE = re.compile(r"(^|/)AppStrings(\.[a-z]{2})?\.(resx|Designer\.cs)$", re.I)

IOS_MARKUP_BRIEF = """winteam-standards — iOS markup rules (invoke `declarative-static-styling`, `checking-dark-mode` and `sizing-for-tablets` before writing):
  - A value that is the same on every load — font, text colour, tint, border, corner radius, icon — belongs
    here, not in ViewDidLoad/AwakeFromNib. Markup loads first, so a surviving code assignment silently wins
    and the storyboard value never applies. Move it here and *delete* the code line; do not leave both.
  - Colours are named: `<color key="textColor" name="color_x"/>`, never `red=/green=/blue=`. If no colourset
    in Assets.xcassets carries the value you want, you have no dark variant either — flag it and stop rather
    than inventing a name or a dark hex.
  - An image goes on the element itself — `<imageView image="ic_name" .../>` — which is this repo's
    established pattern across the cell xibs.
  - A font that should differ on tablet needs a sibling
    `<variation key="heightClass=regular-widthClass=regular">` holding its own `<fontDescription>`. The
    tablet value is a lookup into WinTeam.Mobile.Android/Resources/values-large/dimens.xml, never a number
    you choose.
  - A `<variation>` on a *button's* font silently does nothing. Buttons use
    `SetupFontSizeForCustomButton(phoneValue, tabletValue)` in code — that is the one sanctioned exception.
  - Border width, corner radius and shadow have no inspector field: use User Defined Runtime Attributes in
    the Identity Inspector when the value is constant."""

LAYOUT_BRIEF = """winteam-standards — Android layout rules (invoke `declarative-static-styling`, `checking-dark-mode` and `sizing-for-tablets` before writing):
  - A value that is the same on every load belongs here, not in OnCreateView/OnViewCreated. Set it as an
    attribute and delete the `.SetTextColor(`/`.Typeface =`/`.SetImageResource(` line in code.
  - Colours are `@color/x`, never a hex literal. The full light/dark palette already exists in
    values/colors.xml and values-night/colors.xml, so referencing it is usually the whole fix.
  - Dimensions are `@dimen/x`, never a raw dp/sp literal. If values/dimens.xml has no name for the value,
    leave the literal alone — a speculative new dimen looks like coverage and is worse than the literal.
  - A selected/pressed appearance belongs in an XML state selector (`android:state_selected`), not in a code
    toggle. Fall back to `ImageViewCompat.SetImageTintList` only when the state is not expressible in XML.
  - Fonts come from `android:textAppearance`/`android:fontFamily` referencing an existing style, not from
    `Typeface` assigned in code.
  - `app:tint` only on genuinely tintable template icons. A pre-coloured or self-adapting icon must not be
    tinted at all."""

DRAWABLE_BRIEF = """winteam-standards — Android drawable rules (invoke `checking-dark-mode` before writing):
  - Never stack two alphas. An 8-digit ARGB `fillColor` already encodes its alpha; adding `android:fillAlpha`
    or an SVG `fill-opacity` on top double-fades the result into unreadability. One alpha, from one source.
  - Prefer a `@color/x` reference over a `drawable-night` duplicate. A fill that resolves through a colour
    reference adapts with no second file; duplicating the drawable is the fallback for literal fills, not the
    default move.
  - A hex with no match in values/colors.xml means you have neither a semantic name nor a dark value. Flag it
    and stop — inventing either is a design decision wearing engineering clothes."""

VALUES_BRIEF = """winteam-standards — Android resource-map rules (invoke `checking-dark-mode` and `sizing-for-tablets` before writing):
  - values-large is the only tablet axis. Do not reference or create a `sw600dp`- or landscape-qualified
    variant; none exists. values-h640dp is a short-screen height qualifier that outranks values-large, so a
    name it defines must never also be added to values-large.
  - values-night/colors.xml is the dark axis and values-large/dimens.xml is the tablet axis. A name needs a
    counterpart there only when its value actually *differs*; an intentionally identical value needs no entry.
  - Never invent a colour name, a dark hex or a tablet value. Both are design decisions, and a wrong one is
    invisible to everyone testing on a phone in light mode. Surface the gap and let the user decide.
  - dimens.xml is the size map for *both* platforms. iOS has no dimens file, so an iOS `<variation>` value is
    always a lookup into this file — a value invented independently will not match its Android counterpart."""

ASSETS_BRIEF = """winteam-standards — iOS asset-catalogue rules (invoke `checking-dark-mode` and `sizing-for-tablets` before writing):
  - Resolve the icon fork *before* creating any file. An SVG/PDF in a UIImageView sized by explicit
    constraints rescales losslessly, so it needs a `<variation>` on the constraint and **no new asset**. A
    UIButton icon is sized by the asset itself, so it needs real resized files. Backwards means either a pile
    of unnecessary assets or a variation that changes nothing.
  - A dark variant is an `appearances` entry with `"appearance": "luminosity", "value": "dark"` *and a
    filename*. Xcode writes empty appearance slots into every Contents.json, so a slot with no filename is
    not coverage. A template icon tinted through `@color`/`Colors.X` legitimately needs no dark asset at all.
  - Tablet variants are `width-class`/`height-class` entries, keyed off the same dimens map.
  - On iOS, add an appearance variant rather than branching in code: a Contents.json entry is re-resolved on
    every repaint, while a colour chosen in ViewDidLoad is resolved once and will not repaint when the user
    toggles appearance with the screen open."""

APPSTRINGS_BRIEF = """winteam-standards — AppStrings rules (invoke `appstrings` before writing):
  - `.resx` and `.Designer.cs` must be edited **together, by hand, in the same change**. The generator is a
    Visual Studio design-time tool: `dotnet build` never regenerates Designer.cs, so the two files drift
    silently and the new `AppStrings.*` member simply does not exist.
  - Grep the existing keys for the literal or a close variant before adding anything. This file already
    carries several hundred keys and duplicates are easy to introduce.
  - Key names are PascalCase and prefixed by screen/feature so related strings sort together.
  - Add the entry near the end, before `</root>` — this file is not alphabetised.
  - Never invent a translation. ResourceManager falls back to the neutral value for any culture missing a
    key, so leave AppStrings.es.resx / AppStrings.fr.resx alone and flag that translations are needed."""

# Longest-path-first is not needed here because the six patterns are mutually exclusive by
# directory, but the order is still meaningful: AppStrings.Designer.cs is a `.cs` file and would
# otherwise fall through to no brief at all.
ROUTES = (
    (APPSTRINGS_RE, APPSTRINGS_BRIEF),
    (IOS_MARKUP_RE, IOS_MARKUP_BRIEF),
    (LAYOUT_RE, LAYOUT_BRIEF),
    (DRAWABLE_RE, DRAWABLE_BRIEF),
    (VALUES_RE, VALUES_BRIEF),
    (ASSETS_RE, ASSETS_BRIEF),
)


def brief_for(path):
    """The brief this path earns, or None when it is not presentation markup.

    Split out from main() so the shape is testable without constructing a hook payload.
    """
    if not path:
        return None
    rel = path.replace(os.sep, "/")
    if "/obj/" in rel or "/bin/" in rel:
        return None
    for pattern, brief in ROUTES:
        if pattern.search(rel):
            return brief
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    brief = brief_for((payload.get("tool_input") or {}).get("file_path") or "")
    if not brief:
        return 0

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": brief,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
