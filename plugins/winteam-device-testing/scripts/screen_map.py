"""The screen map a run uses: the plugin's data/screens.json and app.json, with the developer's local map on top.

The local map is <project>/screens.local.json, by default .claude/winteam-device-testing/ in the WinTeam-Mobile
checkout. It is per developer and gitignored. Claude writes to it after a route found through the MCP has been
verified by a capture, so a new or broken screen is fixed without a plugin release.

  {"screens": {"<id>": {"ios": {"files", "steps", "anchor"}, "android": {...}, "learned": "YYYY-MM-DD"}},
   "app": {"dismissLabels": [...], "alertDismissLabels": [...], "blockedLabels": [...],
           "ios": {"loadingLabels": [...]}, "android": {"loading": [...], "blockedIds": [...]}}}

Merge rules. The local map can't loosen a safety setting:
  - A screen id the plugin lacks is added. A screen id the plugin has is replaced per platform block, and keeps the
    plugin's "domain". A local entry can't declare a domain: run_capture.py detects the Time clock page on screen.
  - "app" only adds to the lists above. Accept labels, protected domains, the environment, the login locators and
    the retention can't be changed locally; a local file that tries is refused.
An invalid local file stops the run with its path and every problem found. It is never ignored.

  screen_map.py list     --data D [--project P]              every screen id, its platforms and where it comes from
  screen_map.py resolve  --data D [--project P] FILE...      the screens each file selects, and the unmapped UI files
  screen_map.py check    --data D [--project P]              validate the local map
  screen_map.py upstream --data D [--project P] [--prompt]   local entries the plugin lacks or differs on
"""

import argparse
import copy
import json
import os
import re
import sys

LOCAL_FILE = "screens.local.json"
DEFAULT_PROJECT = os.path.join(".claude", "winteam-device-testing")
PLATFORMS = ("ios", "android")
PLATFORM_ROOTS = {"ios": "WinTeam.Mobile.iOS/", "android": "WinTeam.Mobile.Android/"}
SCREEN_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SCREEN_KEYS = set(PLATFORMS) | {"learned"}
BLOCK_KEYS = {"files", "steps", "anchor"}
TAP_KEYS = {"action", "predicate", "locator", "settle", "timeout", "expect"}
SCROLL_KEYS = {"action", "target", "direction", "within", "maxSwipes", "timeout"}
ANDROID_LOCATOR_KEYS = {"id", "rawId", "class", "text", "label", "textMatches", "desc", "clickable", "selected", "in"}
APP_LISTS = {"dismissLabels", "alertDismissLabels", "blockedLabels"}
APP_PLATFORM_LISTS = {"ios": {"loadingLabels"}, "android": {"loading", "blockedIds"}}
# An edit to these selects every screen mapped for the platform.
SHARED_RESOURCES = {"android": re.compile(r"^WinTeam\.Mobile\.Android/Resources/values[^/]*/(dimens|styles)\.xml$")}
# Files that render UI: one of these that no screen matches is reported as unmapped.
UI_FILES = {
    "ios": re.compile(r"^WinTeam\.Mobile\.iOS/(.*\.(xib|storyboard)|Views/.*\.cs)$"),
    "android": re.compile(r"^WinTeam\.Mobile\.Android/(Resources/layout[^/]*/.*\.xml|Resources/values[^/]*/"
                          r"(dimens|styles)\.xml|Views/.*\.cs)$"),
}


class MapError(ValueError):
    """The local map is invalid; the message names the file and every problem."""


def read_json(path):
    with open(path) as handle:
        return json.load(handle)


def local_path(project_dir):
    return os.path.join(project_dir or DEFAULT_PROJECT, LOCAL_FILE)


def read_local(project_dir):
    """The local map, unvalidated, or None when there is none. A file that isn't JSON is an error, not an empty map."""
    path = local_path(project_dir)
    if not os.path.exists(path):
        return None
    try:
        local = read_json(path)
    except ValueError as error:
        raise MapError("{}: not valid JSON: {}".format(path, error))
    return local


# Validation

def validate(local, path, app=None):
    problems = []
    if not isinstance(local, dict):
        raise MapError("{}: the top level must be an object".format(path))
    for key in set(local) - {"screens", "app"}:
        problems.append("unknown top-level key '{}'".format(key))
    for screen_id, entry in (local.get("screens") or {}).items():
        problems += ["screens.{}: {}".format(screen_id, p) for p in screen_problems(screen_id, entry, app)]
    problems += ["app: {}".format(p) for p in app_problems(local.get("app") or {})]
    if problems:
        raise MapError("{} is invalid:\n  - {}".format(path, "\n  - ".join(problems)))


def screen_problems(screen_id, entry, app):
    if not SCREEN_ID.match(screen_id):
        return ["the id must be lower-case letters, digits and dashes"]
    if not isinstance(entry, dict):
        return ["must be an object"]
    problems = []
    if "domain" in entry:
        problems.append("'domain' can't be set locally; protected pages are detected on screen")
    for key in set(entry) - SCREEN_KEYS - {"domain"}:
        problems.append("unknown key '{}'".format(key))
    if not any(platform in entry for platform in PLATFORMS):
        problems.append("needs an 'ios' or 'android' block")
    for platform in PLATFORMS:
        if platform in entry:
            problems += ["{}: {}".format(platform, p) for p in block_problems(platform, entry[platform], app)]
    return problems


def block_problems(platform, block, app):
    if not isinstance(block, dict):
        return ["must be an object"]
    problems = ["unknown key '{}'".format(key) for key in set(block) - BLOCK_KEYS]
    files = block.get("files")
    if not isinstance(files, list) or not files or not all(isinstance(f, str) for f in files):
        problems.append("'files' must be a non-empty list of globs")
    else:
        for glob in files:
            if not glob.startswith(PLATFORM_ROOTS[platform]) or ".." in glob.split("/"):
                problems.append("file glob '{}' must sit under {}".format(glob, PLATFORM_ROOTS[platform]))
    steps = block.get("steps")
    if not isinstance(steps, list):
        problems.append("'steps' must be a list (empty for the dashboard)")
    else:
        for index, step in enumerate(steps):
            problems += ["step {}: {}".format(index, p) for p in step_problems(platform, step)]
    if "anchor" not in block:
        problems.append("needs an 'anchor'")
    else:
        problems += ["anchor: {}".format(p) for p in anchor_problems(platform, block["anchor"], app)]
    return problems


def step_problems(platform, step):
    if not isinstance(step, dict):
        return ["must be an object"]
    action = step.get("action")
    if action == "tap":
        key = "predicate" if platform == "ios" else "locator"
        problems = ["unknown key '{}'".format(k) for k in set(step) - TAP_KEYS]
        if key not in step:
            problems.append("a tap needs a '{}'".format(key))
        else:
            problems += locator_problems(platform, step[key])
        if "expect" in step:
            problems += ["expect: {}".format(p) for p in locator_problems(platform, step["expect"])]
        return problems
    if action == "scroll_to":
        problems = ["unknown key '{}'".format(k) for k in set(step) - SCROLL_KEYS]
        if step.get("direction", "vertical") not in ("vertical", "horizontal"):
            problems.append("'direction' must be 'vertical' or 'horizontal'")
        if "target" not in step:
            problems.append("a scroll_to needs a 'target'")
        else:
            problems += locator_problems(platform, step["target"])
        if "within" in step:
            problems += ["within: {}".format(p) for p in locator_problems(platform, step["within"])]
        return problems
    return ["'action' must be 'tap' or 'scroll_to', not {}".format(json.dumps(action))]


def locator_problems(platform, spec):
    if platform == "ios":
        return [] if isinstance(spec, str) and spec.strip() else ["an iOS locator is a predicate string"]
    if not isinstance(spec, dict) or not spec:
        return ["an Android locator is a non-empty object"]
    problems = ["unknown locator key '{}'".format(k) for k in set(spec) - ANDROID_LOCATOR_KEYS]
    if "in" in spec:
        problems += locator_problems(platform, spec["in"])
    return problems


def anchor_locators(anchor):
    if isinstance(anchor, dict) and ("all" in anchor or "any" in anchor):
        return list(anchor.get("all", [])) + list(anchor.get("any", []))
    return [anchor]


def is_chrome(platform, spec, app):
    """Whether a locator names the app's chrome (tab bar, toolbar, back button), which can't prove a screen."""
    if platform == "ios":
        labels = (app or {}).get("ios", {}).get("chromeLabels", [])
        return isinstance(spec, str) and any(re.search(r"\b(label|name) == '{}'".format(re.escape(label)), spec)
                                             for label in labels)
    android = (app or {}).get("android", {})
    if not isinstance(spec, dict):
        return False
    return (spec.get("id") in android.get("chromeIds", []) or spec == android.get("backButton") or
            spec == android.get("homeTab"))


def anchor_problems(platform, anchor, app):
    if isinstance(anchor, dict) and ("all" in anchor or "any" in anchor):
        if set(anchor) - {"all", "any"}:
            return ["an all/any anchor has only 'all' and 'any'"]
    locators = anchor_locators(anchor)
    if not locators:
        return ["has no locator"]
    problems = []
    for spec in locators:
        problems += locator_problems(platform, spec)
    if not problems and all(is_chrome(platform, spec, app) for spec in locators):
        problems.append("anchors only on chrome (tab bar, toolbar, back button); anchor on the screen's content")
    return problems


def app_problems(local_app):
    if not isinstance(local_app, dict):
        return ["must be an object"]
    problems = []
    for key, value in local_app.items():
        if key in PLATFORMS:
            if not isinstance(value, dict):
                problems.append("{} must be an object".format(key))
                continue
            for sub, items in value.items():
                if sub not in APP_PLATFORM_LISTS[key]:
                    problems.append("{}.{} can't be set locally (only {})".format(
                        key, sub, ", ".join(sorted(APP_PLATFORM_LISTS[key]))))
                elif not isinstance(items, list):
                    problems.append("{}.{} must be a list".format(key, sub))
        elif key in APP_LISTS:
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                problems.append("{} must be a list of labels".format(key))
        else:
            problems.append("'{}' can't be set locally (only {}, and the ios/android loading and blockedIds "
                            "lists)".format(key, ", ".join(sorted(APP_LISTS))))
    return problems


# Merging

def add_unique(target, items):
    for item in items:
        if item not in target:
            target.append(copy.deepcopy(item))


def merge_app(app, local_app):
    merged = copy.deepcopy(app)
    for key in APP_LISTS:
        add_unique(merged.setdefault(key, []), local_app.get(key, []))
    for platform in PLATFORMS:
        for key, items in (local_app.get(platform) or {}).items():
            add_unique(merged[platform].setdefault(key, []), items)
    return merged


def merge_screens(bundled, local_screens):
    screens = {}
    for screen_id, spec in bundled.items():
        screens[screen_id] = dict(copy.deepcopy(spec), source="plugin")
    for screen_id, entry in local_screens.items():
        blocks = {platform: copy.deepcopy(entry[platform]) for platform in PLATFORMS if platform in entry}
        if screen_id in screens:
            screens[screen_id].update(blocks)
            screens[screen_id]["source"] = "local-override"
        else:
            screens[screen_id] = dict(blocks, source="local")
        if "learned" in entry:
            screens[screen_id]["learned"] = entry["learned"]
    return screens


def load(data_dir, project_dir=None):
    """(app, screens, local path or None). Each screen carries "source": plugin, local or local-override."""
    app = read_json(os.path.join(data_dir, "app.json"))
    bundled = read_json(os.path.join(data_dir, "screens.json"))["screens"]
    path = local_path(project_dir)
    local = read_local(project_dir)
    if local is None:
        return app, merge_screens(bundled, {}), None
    validate(local, path, app)
    return merge_app(app, local.get("app") or {}), merge_screens(bundled, local.get("screens") or {}), path


# Resolving files to screens

def glob_regex(glob):
    """A repo-relative glob: '**/' spans folders (or none), '*' and '?' stay inside one path segment."""
    out, index = "", 0
    while index < len(glob):
        if glob.startswith("**/", index):
            out, index = out + "(?:.*/)?", index + 3
        elif glob.startswith("**", index):
            out, index = out + ".*", index + 2
        elif glob[index] == "*":
            out, index = out + "[^/]*", index + 1
        elif glob[index] == "?":
            out, index = out + "[^/]", index + 1
        else:
            out, index = out + re.escape(glob[index]), index + 1
    return re.compile("^{}$".format(out))


def platform_of(path):
    return next((platform for platform, root in PLATFORM_ROOTS.items() if path.startswith(root)), None)


def resolve(screens, files):
    """{"screens": {platform: [ids]}, "matches": {file: [ids]}, "unmapped": [UI files], "other": [files]}."""
    result = {"screens": {platform: [] for platform in PLATFORMS}, "matches": {}, "unmapped": [], "other": []}
    for raw in files:
        path = raw.replace(os.sep, "/")
        path = path[2:] if path.startswith("./") else path
        platform = platform_of(path)
        if platform is None:
            result["other"].append(raw)
            continue
        shared = SHARED_RESOURCES.get(platform)
        if shared and shared.match(path):
            ids = [s for s in screens if platform in screens[s]]
        else:
            ids = [s for s in screens if platform in screens[s] and
                   any(glob_regex(g).match(path) for g in screens[s][platform].get("files", []))]
        if ids:
            result["matches"][raw] = ids
            for screen_id in ids:
                if screen_id not in result["screens"][platform]:
                    result["screens"][platform].append(screen_id)
        elif UI_FILES[platform].match(path):
            result["unmapped"].append(raw)
        else:
            result["other"].append(raw)
    return result


# Promoting local entries to the plugin

def upstream(data_dir, project_dir):
    """The local entries that are new to the plugin or differ from it, in the plugin's own format."""
    app = read_json(os.path.join(data_dir, "app.json"))
    bundled = read_json(os.path.join(data_dir, "screens.json"))["screens"]
    local = read_local(project_dir) or {}
    validate(local, local_path(project_dir), app)
    out = {"screens": {}, "app": {}}
    for screen_id, entry in (local.get("screens") or {}).items():
        blocks = {p: entry[p] for p in PLATFORMS if p in entry and entry[p] != bundled.get(screen_id, {}).get(p)}
        if blocks:
            out["screens"][screen_id] = blocks
    local_app = local.get("app") or {}
    for key in APP_LISTS:
        extra = [v for v in local_app.get(key, []) if v not in app.get(key, [])]
        if extra:
            out["app"][key] = extra
    for platform in PLATFORMS:
        for key, items in (local_app.get(platform) or {}).items():
            extra = [v for v in items if v not in app[platform].get(key, [])]
            if extra:
                out["app"].setdefault(platform, {})[key] = extra
    return {key: value for key, value in out.items() if value}


PROMPT = """In the winteam-claude-plugins repo, promote these locally learned entries into the \
winteam-device-testing plugin. Each one was found through the Appium MCP and verified by a capture run in \
WinTeam-Mobile.

1. For each screen below: add it to plugins/winteam-device-testing/data/screens.json, or replace the platform \
blocks shown for a screen the map already has. Keep any existing "domain". Add "domain": "timeclock" only if \
the screen is the Time clock page or is reached from it.
2. Append each "app" list item to the matching list in plugins/winteam-device-testing/data/app.json, without \
duplicates. The ios/android sub-objects go into app.json's "ios"/"android" blocks.
3. Bump the minor version in plugins/winteam-device-testing/.claude-plugin/plugin.json. If the change only fixes \
existing screens, bump the patch instead.
4. Run `claude plugin validate plugins/winteam-device-testing --strict` and \
`python3 -m py_compile plugins/winteam-device-testing/scripts/*.py`.

```json
{}
```
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["list", "resolve", "check", "upstream"])
    parser.add_argument("files", nargs="*", help="resolve: repo-relative paths of the touched files")
    parser.add_argument("--data", required=True, help="the plugin's data folder")
    parser.add_argument("--project", default=DEFAULT_PROJECT,
                        help="the folder holding screens.local.json (default: %(default)s)")
    parser.add_argument("--prompt", action="store_true", help="upstream: print a paste-ready prompt")
    args = parser.parse_intermixed_args()
    try:
        if args.command == "upstream":
            entries = upstream(args.data, args.project)
            if not entries:
                print("nothing to promote")
            elif args.prompt:
                print(PROMPT.format(json.dumps(entries, indent=2)))
            else:
                print(json.dumps(entries, indent=2))
            return
        app, screens, path = load(args.data, args.project)
    except MapError as error:
        raise SystemExit(str(error))
    if args.command == "check":
        print("{}: ok, {} local screen(s)".format(path, sum(s["source"] != "plugin" for s in screens.values()))
              if path else "no local map at {}".format(local_path(args.project)))
    elif args.command == "list":
        for screen_id, spec in screens.items():
            print("{}: {} ({})".format(screen_id, ", ".join(p for p in PLATFORMS if p in spec), spec["source"]))
    else:
        print(json.dumps(resolve(screens, args.files), indent=2))


if __name__ == "__main__":
    sys.exit(main())
