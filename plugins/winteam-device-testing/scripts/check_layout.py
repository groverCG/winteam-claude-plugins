"""Size and layout checks on a capture run's XCUITest page sources.

Per capture: visible elements that extend past the screen, overlapping text or buttons, and tap targets
under 44 pt. Across devices: elements found on both phone and tablet whose height did not change, which
is what a phone value left in place on a tablet looks like.

The accessibility tree carries frames, not fonts. Clipped text, font size and colour are not visible to
these checks; the screenshots are the evidence for those.
"""

import argparse
import json
import os
import xml.etree.ElementTree as ET

MIN_TAP_TARGET = 44.0
TEXT_TYPES = {"XCUIElementTypeStaticText", "XCUIElementTypeTextView"}
TAPPABLE_TYPES = {"XCUIElementTypeButton", "XCUIElementTypeSwitch", "XCUIElementTypeLink",
                  "XCUIElementTypeTextField", "XCUIElementTypeSecureTextField"}
SIZED_TYPES = TEXT_TYPES | TAPPABLE_TYPES | {"XCUIElementTypeImage"}
UNSCALED_RATIO = (0.95, 1.05)
SYSTEM_CHROME = ("scroll bar", "Toolbar")
CHROME_CONTAINERS = {"XCUIElementTypeNavigationBar", "XCUIElementTypeTabBar", "XCUIElementTypeKeyboard"}
SCROLL_CONTAINERS = {"XCUIElementTypeScrollView", "XCUIElementTypeCollectionView", "XCUIElementTypeTable"}


def load_elements(path, chrome_labels):
    """Visible, sized elements outside system chrome; scrolling content is marked, duplicates dropped."""
    root = ET.parse(path).getroot()
    app = root if root.tag == "XCUIElementTypeApplication" else root.find(".//XCUIElementTypeApplication")
    screen = (float(app.get("width")), float(app.get("height")))
    elements, seen = [], set()

    def walk(node, ancestors):
        for child in node:
            visit(child, ancestors)
            walk(child, ancestors | {child.tag})

    def visit(node, ancestors):
        attrs = node.attrib
        if node.tag not in SIZED_TYPES or attrs.get("visible") != "true" or ancestors & CHROME_CONTAINERS:
            return
        width, height = float(attrs.get("width", 0)), float(attrs.get("height", 0))
        label = attrs.get("label") or attrs.get("name") or ""
        if width <= 1 or height <= 1 or any(chrome in label for chrome in SYSTEM_CHROME):
            return
        if node.tag == "XCUIElementTypeButton" and label in chrome_labels:
            return
        element = {"type": node.tag.replace("XCUIElementType", ""), "label": label,
                   "x": float(attrs.get("x", 0)), "y": float(attrs.get("y", 0)), "width": width, "height": height,
                   "scrolling": bool(ancestors & SCROLL_CONTAINERS)}
        key = (element["type"], label, element["x"], element["y"], width, height)
        if key not in seen:
            seen.add(key)
            elements.append(element)

    walk(root, set())
    return screen, elements


def describe(element):
    return "{} '{}' at {:.0f},{:.0f} {:.0f}x{:.0f}".format(element["type"], element["label"][:40], element["x"],
                                                         element["y"], element["width"], element["height"])


def contains(outer, inner):
    return (outer["x"] <= inner["x"] and outer["y"] <= inner["y"] and
            outer["x"] + outer["width"] >= inner["x"] + inner["width"] and
            outer["y"] + outer["height"] >= inner["y"] + inner["height"])


def overlap_area(a, b):
    width = min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"])
    height = min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"])
    return width * height if width > 0 and height > 0 else 0.0


def single_capture_findings(screen, elements):
    findings = []
    width, height = screen
    for element in elements:
        if not element["scrolling"] and (element["x"] < -1 or element["y"] < -1 or
                                         element["x"] + element["width"] > width + 1 or
                                         element["y"] + element["height"] > height + 1):
            findings.append({"check": "offscreen", "detail": describe(element)})
        if "XCUIElementType" + element["type"] in TAPPABLE_TYPES and min(element["width"], element["height"]) < MIN_TAP_TARGET:
            findings.append({"check": "small-tap-target", "detail": describe(element)})
    checked = [e for e in elements if "XCUIElementType" + e["type"] in TEXT_TYPES | TAPPABLE_TYPES]
    for i, first in enumerate(checked):
        for second in checked[i + 1:]:
            if contains(first, second) or contains(second, first):
                continue
            area = overlap_area(first, second)
            smaller = min(first["width"] * first["height"], second["width"] * second["height"])
            if smaller and area / smaller > 0.2:
                findings.append({"check": "overlap", "detail": "{}  overlaps  {}".format(describe(first),
                                                                                       describe(second))})
    return findings


def unscaled_candidates(phone_elements, tablet_elements):
    def index(elements):
        grouped = {}
        for element in elements:
            if element["label"]:
                grouped.setdefault((element["type"], element["label"]), []).append(element)
        return {key: group[0] for key, group in grouped.items() if len(group) == 1}

    phone, tablet = index(phone_elements), index(tablet_elements)
    findings = []
    for key in sorted(set(phone) & set(tablet)):
        ratio = tablet[key]["height"] / phone[key]["height"]
        if UNSCALED_RATIO[0] <= ratio <= UNSCALED_RATIO[1]:
            findings.append({"check": "unscaled-candidate",
                             "detail": "{} '{}' is {:.0f} pt tall on both".format(key[0], key[1][:40],
                                                                                 phone[key]["height"])})
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run", help="run folder written by run_capture.py")
    parser.add_argument("--data", help="folder with app.json, for the app's own chrome labels such as tab names")
    args = parser.parse_args()
    with open(os.path.join(args.run, "manifest.json")) as handle:
        manifest = json.load(handle)
    chrome_labels = set()
    if args.data:
        with open(os.path.join(args.data, "app.json")) as handle:
            chrome_labels = set(json.load(handle).get("chromeLabels", []))

    results = []
    loaded = {}
    for role, device in manifest["devices"].items():
        for screen_id, captures in device["screens"].items():
            for orientation, files in captures.items():
                screen, elements = load_elements(files["xml"], chrome_labels)
                loaded[(role, screen_id, orientation)] = elements
                for finding in single_capture_findings(screen, elements):
                    results.append(dict(finding, device=role, screen=screen_id, orientation=orientation))
    for screen_id in manifest["screens"]:
        for orientation in manifest["orientations"]:
            phone = loaded.get(("phone", screen_id, orientation))
            tablet = loaded.get(("tablet", screen_id, orientation))
            if phone is not None and tablet is not None:
                for finding in unscaled_candidates(phone, tablet):
                    results.append(dict(finding, device="phone+tablet", screen=screen_id, orientation=orientation))

    with open(os.path.join(args.run, "findings.json"), "w") as handle:
        json.dump(results, handle, indent=2)
    lines = ["| Screen | Orientation | Device | Check | Detail |", "|---|---|---|---|---|"]
    for item in results:
        lines.append("| {screen} | {orientation} | {device} | {check} | {detail} |".format(**item))
    if not results:
        lines.append("| — | — | — | none | no findings |")
    lines += ["", "Not covered by these checks: clipped text, font size, colour, and spacing that stays inside "
              "its frame. Compare the screenshots for those."]
    with open(os.path.join(args.run, "findings.md"), "w") as handle:
        handle.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
