# Driving WinTeam on the iOS simulator: what works

These notes come from running the app through Appium on an iPhone 17 and an iPad Pro 13" (M5), iOS 27.
`run_capture.py` already follows them. They matter when you explore a screen with the `appium-mcp` tools,
or when you change the script.

## Locating elements

- **iOS views have almost no accessibility identifiers.** Find elements by `-ios predicate string` on `type` and
  `label`, for example `type == 'XCUIElementTypeButton' AND label == 'Home'`. Add `AND visible == 1` when a
  hidden copy of the same label exists. The iPad lists every tab button twice.
- A label is user-facing text. It changes with copy edits and with the device language, so keep the simulators
  in English.
- **Taps are W3C pointer actions at the center of the element's rect.** Element clicks are ignored on the B2C
  page and on the keyboard toolbar. Coordinate taps work everywhere.

## Environment switch

- `ta_dev_tools` is a **1×1 pt button marked not visible**, on the right edge of the login screen. A long-press
  on the element does nothing. A long-press at its exact center coordinates (about 1.5 s) opens the picker.
- The picker shows a text field with the current environment. Tapping it opens a **picker wheel**. Sending
  `Testing` as the wheel's value selects that row. Then tap `Done`, then `Submit`. The choice persists across
  launches, but **each simulator keeps its own**, and a fresh one starts on Production.

## B2C sign-in page

- It opens in **SFSafariViewController**. Its fields are in the native tree: a `TextField` labelled
  `Email Address` and a `SecureTextField` labelled `Password`.
- **Fill it through the keyboard only.** Tap the email field near its right edge, so the cursor lands at the
  end. Type, press **Tab** to move to the password field, type, then press **Enter** to submit.
  - Don't tap the password field: on a phone the keyboard toolbar covers it, and the tap lands on the toolbar.
  - The toolbar's `Next` and `Done` buttons are not in the element tree in a script session.
  - Tapping the page's heading does not close the keyboard.
- **The page keeps earlier input across app launches.** Clear a field before typing, with Delete (`\b`) key
  presses after placing the cursor at its end. An empty field reports its label as its value.
- Afterwards, check that the email field's value is the email and the secure field holds as many bullets as the
  password has characters. Never submit otherwise.

## After sign-in

- Possible full-screen prompts: Enable notifications (`Not right now`), Enable your location (`Not now`), the
  biometrics opt-in. There are also informational alerts such as the tenant's test message (`OK`). Prompts
  can appear after any navigation step, not only after login. Their secondary buttons are `dismissLabels` in
  `data/app.json`.
- **Home** is the menu button (`ic menu`) together with at least one dashboard row subtitle. The menu button
  alone is not enough (see the iPad bug below).
- **Dashboard rows depend on feature flags and the build.** The iPad had no Schedule row while the iPhone did.
  A missing row means the screen is unreachable on that device. That's a finding, not a script failure.

## Navigation

- Pushed screens (Schedule, Tax Forms, Jobs) **hide the tab bar**. Go back with `ic back`, and use the Home tab
  only when it is visible.
- The dashboard's **Timekeeping row switches to the Time tab**. The Time tab has three pages, `Time clock`,
  `Punch log` and `Timekeeping`, selected by tapping their titles.
- The iPad tab bar floats at the top (iPadOS 18+), with no `TabBar` element above it.
- **iPad navigation-bar bug, observed on the build tested:** after leaving a pushed screen, the navigation bar can
  show the wrong items. A pushed screen shows Home's menu and title, or Home shows a back arrow that does
  nothing. `run_capture.py` recovers by relaunching and logging in again, and records it under `relaunches`.

## Session and app state

- **The app logs out on every cold start**, so every run (and every relaunch) logs in again.
- If the app is already running, a session with `noReset` attaches without bringing it to the front. Use
  `forceAppLaunch: true`.
- The first session on each simulator builds WebDriverAgent, which takes several minutes.

## Screenshots and page sources

- Use `xcrun simctl io <udid> screenshot <file>`. The MCP screenshot tool returns the image inline, and it is
  too large to read.
- `xcrun simctl status_bar <udid> override --time 9:41` keeps the status bar the same across captures.
- Check an anchor **once, in portrait**. Rotating can scroll it out of view; on the iPhone, `Clock in` falls
  below the fold in landscape. That's a finding for the screenshots, not a reason to skip the capture.
