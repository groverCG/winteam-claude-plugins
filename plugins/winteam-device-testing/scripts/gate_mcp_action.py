"""Hooks for this plugin's Appium MCP server: navigation runs freely, protected buttons and other actions ask first.

  gate_mcp_action.py gate   --data D --state S   PreToolUse: no output lets the call through; otherwise "ask"
  gate_mcp_action.py record --state S            PostToolUse on appium_find_element(s): remember each element ID

A tap carries only an element ID or coordinates, and the MCP runs its drivers embedded, so the hook can't ask
Appium what an ID is. Instead the record hook remembers the strategy and selector each element was found with,
and the gate decides a tap from that:
  - a tap, double tap or long press on an element found through appium_find_element(s) runs freely, unless its
    selector or attributes name a protected button:
      - the blockedLabels (Clock in/out, breaks, Submit, Save, Delete, Log out…);
      - the Android blockedIds, the Time clock punch buttons (primary, secondary and More);
      - the punch buttons' inner views (button_text, material_button) and the label "More";
  - it also asks when the selector names nothing (class name, a positional or regex selector, a parent axis), when
    the ID was never recorded, and for every coordinate tap: the hook can't know what lies under a point.
The protected lists come from the plugin's app.json with the developer's local map on top, so a local addition
counts too.

Also free: reads, scrolls, swipes, the back gesture and the BACK key, rotation, and alert buttons on
alertDismissLabels. Everything else asks, including typing, accepting an alert, app and device control, and any
tool a future appium-mcp version adds. An input the hook can't read asks too.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import screen_map  # noqa: E402

READ_ONLY_TOOLS = {
    "select_device",
    "prepare_ios_simulator",
    "appium_session_management",
    "appium_find_element",
    "appium_find_elements",
    "appium_get_page_source",
    "appium_get_text",
    "appium_get_element_attribute",
    "appium_get_active_element",
    "appium_screenshot",
    "appium_get_window_size",
    "appium_mobile_device_info",
    "appium_orientation",
    "generate_locators",
}
FREE_ACTIONS = {
    "appium_context": {"list"},
    "appium_alert": {"get_text"},
    "appium_gesture": {"scroll", "scroll_to_element", "swipe", "back"},
    "appium_mobile_keyboard": {"is_shown"},
}
TAP_ACTIONS = {"tap", "double_tap", "long_press"}
FREE_KEYS = {"BACK"}
# The punch buttons keep their label in a child: these are the inner views a find could return instead.
PUNCH_INNER = ["button_text", "material_button", "More"]
# Locator strategies whose whole selector is one value: an id, an accessibility id or a name.
WHOLE_VALUE = {"id", "accessibility id", "name"}
# Attributes that identify an element, as they appear in predicates, class chains, XPath and UiSelector.
NAMING = re.compile(r"\b(label|name|value|text|resourceId|resource-id|description|content-desc|identifier)\b", re.I)
# Partial matches: a value matches every label that contains it.
PARTIAL = re.compile(r"\b(CONTAINS|BEGINSWITH|ENDSWITH|textContains|textStartsWith|descriptionContains|"
                     r"descriptionStartsWith|contains|starts-with)\b")
# Selectors the hook can't pin to one named element: regexes, wildcards, positions, and parent or sibling axes.
VAGUE = re.compile(r"\b(MATCHES|LIKE|textMatches|descriptionMatches|resourceIdMatches|classNameMatches|matches|"
                   r"instance|index|fromParent|childSelector|parent|ancestor|following|preceding)\b|\.\.|"
                   r"\[\s*-?\d+\s*\]")
QUOTED = re.compile(r"\"((?:[^\"\\]|\\.)*)\"|'((?:[^'\\]|\\.)*)'")
ELEMENT_ID_LINE = re.compile(r"elementId '([^'\n]+)'")
ID_PREFIX = re.compile(r"^[\w.]+:id/")
STATE_MAX_AGE = 24 * 3600
STATE_MAX_ENTRIES = 500
WARNING = ("Appium action `{}`: {} It could change data in the WinTeam app (Clock in/out, Submit, Log out). "
           "Approve only if you meant it.")


def norm(text):
    return ID_PREFIX.sub("", " ".join(str(text).split())).lower()


# What the app protects

def app_lists(data_dir, cwd):
    """(protected tokens, alert dismiss labels), with the developer's local map added when it can be read."""
    app = screen_map.read_json(os.path.join(data_dir, "app.json"))
    project = os.path.join(cwd, screen_map.DEFAULT_PROJECT) if cwd else None
    try:
        app, _, _ = screen_map.load(data_dir, project)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        try:  # an invalid local map still adds to the lists: they only ever grow
            app = screen_map.merge_app(app, (screen_map.read_local(project) or {}).get("app") or {})
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
    tokens = list(app.get("blockedLabels", [])) + list((app.get("android") or {}).get("blockedIds", []))
    tokens += PUNCH_INNER
    return {norm(t) for t in tokens if norm(t)}, {norm(label) for label in app.get("alertDismissLabels", [])}


# What a selector names

def selector_values(strategy, selector):
    """The values a selector matches on: the whole of an id or accessibility id, otherwise its quoted strings."""
    if strategy in WHOLE_VALUE:
        return [selector]
    return [a or b for a, b in QUOTED.findall(selector)]


def protected_hit(values, tokens, partial):
    """The protected token one of the values would match, or None. Same rule as run_capture.is_blocked."""
    for value in values:
        value = norm(value)
        if not value:
            continue
        for token in sorted(tokens):
            if value == token or value.startswith(token + " ") or (partial and value in token):
                return token
    return None


def element_problem(entry, tokens):
    """Why a tap on this recorded element needs approval, or None."""
    strategy, selector = entry.get("strategy") or "", entry.get("selector") or ""
    attributes = [v for v in (entry.get("attributes") or {}).values() if isinstance(v, str)]
    bare = QUOTED.sub('""', selector)  # the operators and attributes, without the label text
    hit = protected_hit(selector_values(strategy, selector) + attributes, tokens,
                        partial=strategy not in WHOLE_VALUE and bool(PARTIAL.search(bare)))
    if hit:
        return "it taps an element found by `{}`, which matches the protected `{}`.".format(selector, hit)
    if strategy in WHOLE_VALUE:
        return None if selector.strip() else "it taps an element found by an empty selector."
    if strategy == "class name" or VAGUE.search(bare) or not (QUOTED.search(selector) and NAMING.search(bare)):
        return ("it taps an element found by `{}`, which doesn't name one element (no id, label or text, or a "
                "position, pattern or parent).".format(selector))
    return None


# The record of found elements

def read_state(path):
    try:
        with open(path) as handle:
            state = json.load(handle)
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(path, state):
    now = time.time()
    fresh = {k: v for k, v in state.items() if isinstance(v, dict) and now - v.get("at", 0) < STATE_MAX_AGE}
    kept = dict(sorted(fresh.items(), key=lambda item: item[1].get("at", 0))[-STATE_MAX_ENTRIES:])
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=folder, prefix=".mcp-elements-")
    with os.fdopen(handle, "w") as out:
        json.dump(kept, out)
    os.replace(temp, path)


def strings_in(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings_in(item)


def found_elements(response, depth=0):
    """{element id: attributes} from an appium_find_element(s) result, whether it arrives parsed or as JSON text."""
    found = {}
    for text in strings_in(response):
        for element_id in ELEMENT_ID_LINE.findall(text):
            found.setdefault(element_id, {})
        try:
            data = json.loads(text)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("elements"), list):
            items = data["elements"]
        elif isinstance(data, dict) and "elementId" in data:
            items = [data]
        else:
            items = []
            if depth < 2 and isinstance(data, (dict, list)):
                found.update(found_elements(data, depth + 1))
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("elementId"), str):
                attributes = item.get("attributes")
                found[item["elementId"]] = attributes if isinstance(attributes, dict) else {}
    return found


def record(payload, state_path):
    tool_input = payload.get("tool_input") or {}
    found = found_elements(payload.get("tool_response"))
    if not found:
        return
    state = read_state(state_path)
    now = time.time()
    for element_id, attributes in found.items():
        state[element_id] = {"strategy": tool_input.get("strategy"), "selector": tool_input.get("selector"),
                             "attributes": attributes, "at": now}
    write_state(state_path, state)


# The decision

def decision(payload, data_dir, state_path):
    """Return None to let the call through, or the reason to ask the user."""
    tool = payload["tool_name"].split("__")[-1]
    tool_input = payload.get("tool_input") or {}
    action = tool_input.get("action")
    if tool in READ_ONLY_TOOLS or action in FREE_ACTIONS.get(tool, set()):
        return None
    if tool == "appium_mobile_press_key" and tool_input.get("key") in FREE_KEYS:
        return None
    if tool == "appium_alert" and action in ("accept", "dismiss"):
        tokens, dismiss = app_lists(data_dir, payload.get("cwd"))
        label = norm(tool_input.get("buttonLabel") or "")
        if (label in dismiss or (action == "dismiss" and not label)) and not protected_hit([label], tokens, False):
            return None
        return WARNING.format(tool, "it presses an alert button that isn't on alertDismissLabels.")
    if tool == "appium_gesture" and action in TAP_ACTIONS:
        element_id = tool_input.get("elementUUID")
        if not element_id or str(element_id).startswith("ai-element:"):
            return WARNING.format(tool, "a coordinate tap, which the hook can't trace to a button. Find the "
                                        "element first and tap its elementUUID.")
        entry = read_state(state_path).get(element_id)
        if not isinstance(entry, dict):
            return WARNING.format(tool, "it taps an element that wasn't found through appium_find_element(s) "
                                        "first, so the hook can't tell what it is.")
        tokens, _ = app_lists(data_dir, payload.get("cwd"))
        problem = element_problem(entry, tokens)
        return WARNING.format(tool, problem) if problem else None
    return WARNING.format(tool, "it isn't a read, a scroll or a navigation tap.")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", nargs="?", default="gate", choices=["gate", "record"])
    parser.add_argument("--data", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))
    parser.add_argument("--state", required=True)
    args = parser.parse_args(argv)
    if args.mode == "record":
        try:
            record(json.load(sys.stdin), args.state)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass  # an unrecorded element only means its tap asks
        return
    try:
        reason = decision(json.load(sys.stdin), args.data, args.state)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        reason = WARNING.format("unknown", "the hook couldn't read the call.")
    if reason is None:
        return
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                             "permissionDecisionReason": reason}}))


if __name__ == "__main__":
    main()
