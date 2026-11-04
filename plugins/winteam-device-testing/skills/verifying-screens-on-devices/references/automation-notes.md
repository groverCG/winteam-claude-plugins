# Driving WinTeam on the simulator and the emulator: what works

`run_capture.py` already follows these notes. They matter when you explore a screen with the `appium-mcp`
tools, or when you change the script.

Contents: [iOS](#ios) · [Android](#android)

# iOS

These notes come from running the app through Appium on an iPhone 17 and an iPad Pro 13" (M5), on iOS 27 and
then on iOS 26.5.

## Runtime

- **Use iOS 26.5.** On iOS 27.0 the app crashes at launch: it doesn't adopt the UIScene lifecycle yet.
  `devices.json` targets 26.5 until the app is fixed. Then switch the runtime back to 27.0.

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
- **On a phone the page scrolls, and the email field can sit below the fold or under the keyboard.** A tap
  on a field outside the visible area lands on nothing, or on the keyboard, and the field never takes focus.
  - Bring the field into view first: try `mobile: scroll` with `elementId` and `toVisible: true`.
  - If that fails, swipe vertically on the page, above the keyboard.
  - Through the MCP, use `appium_gesture` with `scroll` or `scroll_to_element`; these run without an approval
    prompt.
- **Don't wait for the keyboard.** `mobile: isKeyboardShown` (and `appium_mobile_keyboard` `is_shown`) never
  sees the keyboard on this page, even when the field has focus. Confirm focus by typing the email and reading
  the field's value back.
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

- **"Choose an account"** shows when the test user belongs to several tenants.
  - Its rows are `StaticText` labels with a tap gesture, not buttons, so `dismissLabels` never matches them.
  - The script taps the row whose label equals `--tenant` or `WT_TEST_TENANT`, and stops if neither is set.
  - It does this only while the picker title shows and the Home menu button (`ic menu`) doesn't. The dashboard
    header shows the same tenant name, and tapping it opens "Switch account".
- Possible full-screen prompts: Enable notifications (`Not right now`), Enable your location (`Not now`), the
  biometrics opt-in. There are also informational alerts such as the tenant's test message (`OK`). Prompts
  can appear after any navigation step, not only after login. Their secondary buttons are `dismissLabels` in
  `data/app.json`.
- **An alert can close by itself** between being read and a button being pressed. That raises "no such alert",
  and the script treats it as already handled.
- **Home** is the menu button (`ic menu`) together with at least one dashboard row subtitle. The menu button
  alone is not enough (see the iPad bug below).
- **Dashboard rows depend on feature flags and the build.** The iPad had no Schedule row while the iPhone did.
  A missing row means the screen is unreachable on that device. That's a finding, not a script failure.

## Navigation

- Pushed screens (Schedule, Tax Forms, Jobs) **hide the tab bar**. Go back with `ic back`, and use the Home tab
  only when it is visible.
- The dashboard's **Timekeeping row switches to the Time tab**. The Time tab has three pages, `Time clock`,
  `Punch log` and `Timekeeping`, selected by tapping their titles. It opens on `Time clock`.
- **Only the Time clock page is locked** (the `timeclock` domain). You are on it when the `Time clock` title is
  selected and a `Clock in` or `Clock out` button shows. There, tap nothing but a tab or a page title. Punch log
  and Timekeeping are open to explore, except for `blockedLabels`.
- **Horizontally scrolled content**, such as Timekeeping's chips on a phone, is reached with a `scroll_to` step.
  It swipes inside the `within` element until the `target` is fully visible.
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

# Android

These notes come from running the app through Appium's UiAutomator2 driver on two emulators with Android 17
(API 37). The phone is `Medium_Phone_API_37.0`: 1080×2400 px at 420 dpi, 411×914 dp, bucket `normal`. The
tablet is `WinTeam_Tablet_API_37.0`: 2560×1600 px at 320 dpi, 1280×800 dp, bucket `xlarge`.

## Emulators and the size bucket

- **Tablet resources come from `values-large` only.** A device gets them only when it resolves to the `large` or
  `xlarge` bucket. `values-h640dp` holds four kiosk-login dimens, and none of them is also in `values-large`.
- **Check the bucket.** `adb shell am get-config` carries it as a token: `…-normal-…` or `…-xlarge-…`.
  `run_capture.py` refuses to capture on a device whose bucket differs from its `screenSize` in `devices.json`.
- **Creating the tablet AVD.** There are no `cmdline-tools`. `android_devices.py create-avd` therefore copies
  the phone AVD's `config.ini` and changes the screen. It never copies disk images, and the emulator builds
  fresh userdata on the first boot.
- **Booting.** Start the emulator headless with
  `emulator -avd <name> -port <even port> -no-snapshot-save -no-window -no-audio -no-boot-anim`, then wait for
  `getprop sys.boot_completed` to read 1. An emulator that is already running is reused and left running.
- **Status bar.** SystemUI demo mode (`com.android.systemui.demo`) freezes the clock at 09:41 and shows a full
  battery and full Wi-Fi.

## Building and installing

- **Build with `-p:EmbedAssembliesIntoApk=true`.** The Debug configuration sets `EmbedAssembliesIntoApk=false`
  and relies on Fast Deployment. The plain `-Signed.apk` then carries no .NET assemblies, and the app loads
  whatever an earlier deploy left in `files/.__override__`. That folder may hold a different branch's
  assemblies: one such build crashed at launch with `No view found for id … appSettingsTextView for fragment
  LoginFragment`.
- **After `adb install -r`**, `run_capture.py --apk` deletes `files/.__override__` with `run-as`.
- **The launcher activity** has a generated name (`crc64….SplashScreenActivity`). The script resolves it with
  `cmd package resolve-activity --brief com.workwave.winteam`. The splash has `NoHistory` and hands over to
  `MainActivity`, so the session uses `appWaitActivity: "*"`.

## Locating elements

- **Android views have resource ids.** Prefer them: `{"id": "time"}` becomes
  `resourceId("com.workwave.winteam:id/time")`. Fall back to text through `-android uiautomator`. The keys a
  locator can use are listed at the top of `scripts/platforms.py`.
- **UiAutomator2 reports a missing attribute as the string `"null"`.** The scripts treat it as empty.
- Button text is shown in **upper case** (`SUBMIT`, `CANCEL`), so the label lists are matched case-insensitively.
- **A punch button keeps its label in a child.** `primary_suggested_punch_action_MaterialButton` is a clickable
  FrameLayout with no text. The `Clock in` text is the child `button_text`, and the inner `material_button` has
  no label at all.
  - The guard therefore also reads every text inside the tapped view.
  - It also refuses any tap whose point lands inside a `blockedIds` view.
  - XPath from an element only searches that element's subtree, so an element's ancestors can't be looked up.
    That is why the `blockedIds` check uses where the tap lands rather than the tapped element's own id.

## Environment switch

- `ta_dev_tools` is a 1×1 dp transparent `Button` at the top right of the login screen. A long-press at its
  centre opens `EnvironmentFragment`.
- The page has a `Spinner` `environmentSpinner`, whose selected TextView holds the current environment. Tap
  it, and the dropdown lists `Development`, `Testing`, `Staging` and `Production` as clickable TextViews with no
  id. Tap `Testing`, check the spinner reads `Testing`, then tap `btnSave` by id. Its text is `SUBMIT`, which
  is on `blockedLabels`, and the login routine is exempt from the guard.

## B2C sign-in page

- **MSAL uses its embedded WebView** (`UseEmbedded = true`). It runs in `AuthenticationAgentActivity`, not in
  Chrome Custom Tabs. WebView debugging is off, so there is no `WEBVIEW` context, but the native tree exposes
  the form: `EditText` with resource id `email`, `EditText` `password` (`password="true"`) and `Button` `next`
  (`Sign in`). The ids have no package prefix, so the locators use `rawId`.
- The page takes up to about 20 s to fill in its tree after the WebView appears.
- **Typing:** W3C key actions type into the focused field, and Tab moves to the password field. Use W3C codes for
  special keys:
  - Backspace is ``. UiAutomator2 refuses `\b`.
  - Enter is ``.
  - Element clear works only on the focused field, so clear with Backspaces from the end, as on iOS.
- **The password field's `text` attribute is the plain password**, not bullets. The script compares only its
  length, and never prints it or saves this page's source. Don't read that attribute through the MCP.
- The UiAutomator2 server on the device logs requests to logcat, typed text included. `run_capture.py` runs
  `adb logcat -c` right after the sign-in is submitted and again at the end. The Appium session uses
  `skipLogcatCapture`.

## After sign-in

- The prompts share one layout. `title_TextView` is "Enable notifications", "Enable your location" or "Enable
  biometric login", and `secondary_action_button` reads "Not right now", "Not now" or "No thanks". The
  location prompt's main button reads `Continue`, which is on `blockedLabels`.
- **Alerts** are AlertDialogs with `android:id/message` and buttons `android:id/button1`, `button2` and
  `button3`. The tenant's test message ("This is a test message - Global Test", one `OK`) can open late, even
  in the middle of a step. Permission dialogs use `com.android.permissioncontroller:id/permission_*_button`.
- **"Choose an account"** (`SelectTenantFragment`) has the title `title_TextView` and one
  `account_name_TextView` per row. The dashboard header `company_name_TextView` opens "Switch account" instead.
- **Home:**
  - The menu is an `ImageButton` with content-desc `WinTeam`.
  - The rows are matched on `moduleTitleTextView` / `moduleCaptionTextView`, because they have no ids.
  - The bottom tabs are FrameLayouts `#home` and `#time`, with content-desc "Home" and "Time".

## Navigation

- Pushed screens (Schedule, Tax Forms, Jobs) hide the bottom bar and show an `ImageButton` "Navigate up".
  `go_home` tries that first, then the `#home` tab, then the system back key.
- **Tax Forms opens the Pay landing page first.** Then tap the card `taxesCardView`.
- **Time tab:** the pages are tabs, `LinearLayout`s with content-desc "Time clock", "Punch log" and
  "Timekeeping". The selected one has `selected="true"`.
  - A tab tapped while the pager is still loading snaps back to Time clock. Each tab step carries an `expect`
    on the tab being selected, and is tapped again once if it isn't.
- **Timekeeping's chips** are `chipContainer` Buttons in the horizontal RecyclerView
  `expandedChipsRecyclerView`. On the phone "Custom dates" is off screen until a `scroll_to` step swipes the
  row. The RecyclerView recycles views while it scrolls, so stale elements are retried.

## Rotation

- `MainActivity` uses `ScreenOrientation.FullSensor`, and auto-rotate is off on the emulators. UiAutomator2's
  `/orientation` fails ("Screen rotation cannot be changed…"). The script turns the emulated device with
  `adb emu rotate` until the display is wider than tall, or the reverse, and never leaves it upside down.

## Screenshots and page sources

- Use `adb -s <serial> exec-out screencap -p > file.png`. It works on a headless emulator.
- Page-source bounds are pixels, `[x1,y1][x2,y2]`. `check_layout.py` divides them by `dpi / 160` from the
  manifest, so phone and tablet compare in dp.

## Observed on the build tested

- **The punch-button labels are a fixed 14sp on every device.** `loading_button.xml:44` hard-codes
  `android:textSize="14sp"` on `button_text`, so `Clock in` and `More` stay at phone size on the tablet, while
  `body_2` text on the same page grows to 22sp: `recent_punches_title_TextView` measures 19.4 dp on the phone
  and 29.5 dp on the tablet. `check_layout.py` flags the labels as `unscaled-candidate`. This is an app issue to
  report, not a script problem.
