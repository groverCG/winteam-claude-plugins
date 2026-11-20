# Scenario API

A scenario is a Python file (3.9, standard library) that starts from a fresh install and runs unchanged on the
before and after builds:

- `setup(s)` (optional) runs first and **isn't recorded**: signing in, creating a PIN, logging out, any state the
  repro needs. Keeping it out of the video makes the video short and keeps the login off screen.
- `run(s)` is recorded: the repro steps and the checks. Put the sign-in here only when the bug is in that flow.

`s` gives:

## Platform

`s.android`, `s.ios`, `s.platform` (`"android"` / `"ios"`), `s.mode` (`"before"` / `"after"`).

## Locators

winteam-device-testing's format: an iOS predicate string, or an Android dict (`id`, `rawId`, `text`, `label`,
`textMatches`, `desc`, `class`, `clickable`, `selected`, and `in` for an ancestor spec).

| Helper | Android | iOS |
|---|---|---|
| `s.id("numericPadLayout")` | resource id in the app package | `name == '…'` |
| `s.text("Log out")` | exact text | `label == '…' OR name == '…'` |
| `s.contains("PIN")` | text contains | `label CONTAINS '…'` |
| `s.key(5)` | PIN keypad key | PIN keypad key |
| `s.pick(android=…, ios=…)` | the Android one | the iOS one |

## Actions

- `s.tap(loc, timeout=15)`, `s.find(loc, timeout=15)` (raises when missing), `s.long_press(loc, seconds=2)`.
- `s.exists(loc, timeout=3)` / `s.gone(loc, timeout=5)`: booleans, for checks and optional steps.
- `s.type(loc, text)`: for ordinary fields only, never credentials.
- `s.back()` (Android), `s.swipe(x1, y1, x2, y2)`, `s.pause(seconds)`.
- `s.adb("shell", "cmd", "uimode", "night", "yes")` (Android), `s.simctl("ui", "appearance", "dark")` (iOS).
- `s.driver`: the raw `wt_driver.Session`, for anything else.

## App flows

- `s.sign_in(pin=None)`: from a fresh install to Home. Testing environment, password login, `set_up_pin(pin)` when
  a PIN is given, the tenant on "Choose an account" (`WT_TEST_TENANT`), the PIN offer (No thanks) and the
  notifications prompt.
- The pieces, for scenarios that need to stop in between: `s.select_environment()`, `s.log_in()` (Log In, then
  the B2C form), `s.set_up_pin(pin)`, `s.finish_sign_in()`.
- `s.enter_pin(pin)`, `s.log_out()` (side menu > Log out, waits for the login screen), `s.close_sign_in()` (leave
  the B2C page without signing in).

## Expected result

`s.check(name, condition)`: `condition()` returns true when the app behaves as expected. In `before` mode a failure
is only logged (it shows the bug); in `after` mode it stops the run with exit code 2. Use `lambda:` so the check
runs at that moment: `s.check("Keypad opens", lambda: s.exists(s.id("numericPadLayout"), 5))`.

## Example

`example_scenario.py`, next to this file (MO-8964, both platforms).
