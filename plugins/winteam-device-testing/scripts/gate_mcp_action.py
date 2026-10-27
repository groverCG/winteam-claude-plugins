"""PreToolUse gate for this plugin's Appium MCP server: reads run freely, every action asks first.

A tap or a typed key cannot be tied to a screen or a button from the hook's input (it carries an element
ID or coordinates), so any tool that can change the app's state needs the user's approval. Unknown tools,
including ones a future appium-mcp version adds, are treated as actions.
"""

import json
import sys

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
    "generate_locators",
}
READ_ONLY_ACTIONS = {
    "appium_context": {"list"},
    "appium_alert": {"get_text"},
}
WARNING = ("Appium action `{}`: it can tap or type anywhere in the WinTeam app, including Clock in/out and "
           "Submit. Approve only if you meant it.")


def decision(payload):
    """Return None to let a read through, or the reason to ask the user."""
    tool = payload["tool_name"].split("__")[-1]
    if tool in READ_ONLY_TOOLS:
        return None
    action = (payload.get("tool_input") or {}).get("action")
    if action in READ_ONLY_ACTIONS.get(tool, set()):
        return None
    return WARNING.format(tool)


def main():
    try:
        reason = decision(json.load(sys.stdin))
    except (ValueError, KeyError, TypeError, AttributeError):
        reason = WARNING.format("unknown")
    if reason is None:
        return
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                             "permissionDecisionReason": reason}}))


if __name__ == "__main__":
    main()
