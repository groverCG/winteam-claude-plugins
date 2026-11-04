# winteam-device-testing

Runs WinTeam on a **phone and a tablet**, either iPhone and iPad simulators or Android phone and tablet emulators,
to check UI changes visually.

- It logs into the **Testing** environment.
- It opens the screens a change touched, using a screen map.
- It captures a screenshot and the page source of each, in portrait and landscape.
- It flags layout problems, most usefully **elements that stay at phone size on the tablet**.

Claude then compares the phone and tablet screenshots side by side and reports what it sees.

This covers the visual check `/winteam-standards:scale-for-tablets` ends with. When this plugin is installed,
that command hands its touched files here, iOS and Android, instead of leaving the check to you.

## Why this is a separate plugin

`winteam-standards` works with no setup. This plugin needs Node, pnpm, Appium, Xcode simulators, the Android
emulator and a test account, so it's opt-in. It depends on `winteam-standards` and never copies anything from it: sizing
rules stay in one place.

## Prerequisites

| What | How |
|---|---|
| Xcode with an **iPhone 17** and an **iPad Pro 13-inch (M5)** simulator on **iOS 26.5** | Xcode > Window > Devices and Simulators. The app crashes at launch on iOS 27.0 until it adopts the UIScene lifecycle. To use other simulators, change `data/devices.json` |
| The Android SDK with `platform-tools`, `emulator` and the `android-37.0` Google Play arm64 system image, plus Java 21 | Android Studio > SDK Manager. `ANDROID_HOME` defaults to `~/Library/Android/sdk`, and `JAVA_HOME` should be set in `~/.zshrc` |
| The **`Medium_Phone_API_37.0`** AVD | Android Studio > Device Manager. Setup creates the tablet AVD, `WinTeam_Tablet_API_37.0`, from it |
| Node and pnpm | `brew install node pnpm`. **Don't install pnpm through npm** |
| A Debug build of WinTeam.Mobile.iOS or WinTeam.Mobile.Android that compiles | The skill builds it and installs it on both devices |
| A test account in the **Testing** environment, without MFA | See *Test credentials* |

## Install

From your WinTeam-Mobile checkout:

```bash
claude plugin marketplace add groverCG/winteam-claude-plugins   # skip if /plugin already lists "winteam"
claude plugin install winteam-standards@winteam -s local         # required by this plugin
claude plugin install winteam-device-testing@winteam -s local
```

Then, in Claude Code, run `/winteam-device-testing:setup-devices` and **restart Claude Code** so the bundled
`appium-mcp` server starts. Run setup again after every update of this plugin, because an update can bring a new
lockfile.

Setup installs Appium into the plugin's data folder, `~/.claude/plugins/data/<plugin id>/appium`. That folder
survives plugin updates and is deleted when you uninstall the plugin. Nothing is installed globally.

Setup also creates the Android tablet AVD under `~/.android/avd` if it's missing. It copies the phone AVD's
settings with a 2560×1600, 320 dpi screen. Then it checks that the tablet resolves the `xlarge` size bucket,
the condition for the app to use `values-large`. Uninstalling the plugin leaves the AVD. Delete it in Android
Studio's Device Manager.

## Test credentials

The capture script logs in by itself and never shows the password to Claude. Store the account in your
login keychain, from any folder. The command prompts for the password, so it never appears in your shell
history:

```bash
security add-generic-password -U -s winteam-device-testing -a <test account email> -w
```

To check it's there without showing it: `security find-generic-password -s winteam-device-testing`.
To remove it: `security delete-generic-password -s winteam-device-testing`.

If you'd rather not use the keychain, `WT_TEST_USER` and `WT_TEST_PASSWORD` in your environment work too. They
are plain text, though, and every process you start can read them, including package install scripts.

**Use a Testing-only account.** Never put credentials in this repository, in `data/`, or in a chat.

If the account belongs to more than one tenant, the app shows "Choose an account" after sign-in. Set
`WT_TEST_TENANT` to the tenant's name as it appears there (or pass `--tenant`), and the script picks that row.
Without it, the script stops at the picker.

## Use

```
/winteam-device-testing:verify-screens schedule jobs
/winteam-device-testing:verify-screens WinTeam.Mobile.iOS/Views/Cells/Schedule/ScheduleViewCell.xib
/winteam-device-testing:verify-screens WinTeam.Mobile.Android/Resources/layout/fragment_time_clock.xml
/winteam-device-testing:verify-screens time-clock timekeeping --android
/winteam-device-testing:verify-screens --changed
```

`/winteam-standards:scale-for-tablets` calls the same skill, `verifying-screens-on-devices`, on its own at its
Step 8.

A run, per platform:

1. builds the app and installs it on the phone and the tablet. On Android, the script boots both emulators
   headless, installs the APK, and shuts down the emulators it booted at the end;
2. logs in;
3. captures each screen;
4. runs `check_layout.py`;
5. reports, per screen and orientation, what differs between phone and tablet.

It changes no app code. Runs are kept in `~/.claude/plugins/data/<plugin id>/runs/` for 3 days (see *Data and
safety*). To delete them sooner:

```
/winteam-device-testing:purge-runs                  # every run
/winteam-device-testing:purge-runs --older-than 1   # only runs older than a day
```

## What the checks catch, and what they don't

`check_layout.py` reads frames from the accessibility tree and flags:

- **unscaled candidates**: an element found on both devices with the same height, for example a 16 pt
  title or a 50 pt button on a 13" iPad, or the punch-button label that stays 19 dp on an Android tablet;
- **overlap** between text and buttons;
- **off-screen** elements outside scrolling content;
- **tap targets** under 44 pt on iOS, and under 48 dp on Android (Material's minimum).

Android bounds come in pixels, and are converted to dp with each device's density before any check. Navigation
and tab bars are skipped, because they're system-managed. On Android, so are the toolbar and the bottom
navigation (`chromeIds` in `data/app.json`).

The tree carries **no fonts, colours or clipping**. Those come from the screenshots, which Claude reviews. A
same-height element can be intentional, so each candidate is confirmed or dismissed against the screenshots.

## Data and safety

- **The password never reaches a log.**
  - Appium writes every typed string to its log. `run_capture.py` therefore starts its own Appium server with
    logging off and output discarded, and stops it at the end.
  - Nothing else runs an Appium server. The bundled MCP server is never used for logging in.
  - On Android, the UiAutomator2 server on the emulator logs its requests to logcat. The script clears logcat
    right after the sign-in is submitted and again at the end, and the Appium session doesn't collect logcat
    (`skipLogcatCapture`). Emulators the run booted are shut down, which drops their log buffers.
  - The Android sign-in page reports the typed password as plain text in its page source. The script reads only
    its length, and never saves that page.
- **Screenshots contain account data, and expire.**
  - Runs stay in the plugin's data folder for `retentionDays` (3) in `data/app.json`.
  - Expired runs are deleted **at every Claude Code session start** (a `SessionStart` hook, silent unless it
    deletes something) and at the start of every capture.
  - `/winteam-device-testing:purge-runs` deletes them on demand.
  - Uninstalling the plugin deletes the whole data folder.
  - Screenshots Claude reviewed are also in Claude Code's local session history (`~/.claude/projects/`), which
    the `cleanupPeriodDays` setting prunes, 30 days by default.
  - The map grows only with screens a change actually touches. It is never meant to cover the whole app.
- **Navigation is read-only, and the scripts enforce it.** Every tap after login goes through one check:
  - **`blockedLabels`** (Clock in, Clock out, Start/End break, meal and lunch, Submit, Save, Send, Delete,
    Confirm, Continue, Log out…) are never tapped, whatever the screen map says. On Android the check also
    reads the texts inside the tapped view, because a punch button keeps its label in a child view.
  - **`blockedIds`** (Android: the punch buttons) are never tapped either. A tap whose point lands inside one of
    those views is refused, even when the tapped element is an unlabelled inner view.
  - **The Time clock page** (the first page of the Time tab, the `timeclock` domain) is navigation-only. On it the
    script may only tap the tabs and page titles. It reads and captures everything else. The Time tab's other
    pages, Punch log and Timekeeping, are open to explore, with `blockedLabels` still off-limits.
  - **Alerts** get a known-safe button pressed by name (Cancel, Not now, Don't Allow…), or OK when it's their
    only button. Any other alert stops that screen.
  - A refusal shows up as a `blocked` error in the run's `manifest.json`.
  - The only taps outside this check are the fixed login steps:
    - the environment picker;
    - Log In;
    - the email field;
    - the row for the configured tenant on "Choose an account". That row is tapped only while the picker shows,
      never once the dashboard's menu button is visible.

    On a phone, the login may also scroll the sign-in page to bring the email field into view above the
    keyboard.
  - `scroll_to` steps only swipe, leftward or upward, so they can't tap or pull to refresh.
- **The Appium MCP tools ask before acting.**
  - A `PreToolUse` hook lets these run freely: the reading tools (page source, find element, screenshot,
    text, attributes, `select_device`), scrolling (`appium_gesture` `scroll` and `scroll_to_element`) and the
    keyboard check (`appium_mobile_keyboard` `is_shown`).
  - Every other tool, including any future one, shows an approval prompt warning that it can tap or type
    anywhere in the app, including Clock in/out and Submit. On Android that includes the back and home keys
    (`appium_mobile_press_key`) and switching contexts. The prompt appears in auto mode too.
  - The hook can't tell which button a tap targets, because it only sees an element ID or coordinates, so it
    asks for every action.
- **The Testing environment only.** The script switches each simulator and emulator to Testing and stops if it
  can't. It checks the sign-in form before submitting it.
- **The Android tablet must be a tablet to the app.** The script reads each emulator's size bucket and refuses
  to capture on a tablet that doesn't resolve `xlarge`. Such a device would show phone resources, and the
  comparison would prove nothing.

## Why pnpm, and what the settings do

Appium is only distributed through npm, and npm packages were repeatedly hijacked during 2026. `appium/`
pins a vetted install that setup reproduces exactly with `pnpm install --frozen-lockfile`. Its
`pnpm-workspace.yaml`:

| Setting | What it does |
|---|---|
| `minimumReleaseAge: 4320` | Nothing published in the last 3 days gets installed. Most hijacked releases are caught within that window |
| `trustPolicy: no-downgrade` | Refuses a version published with weaker provenance than earlier ones, the shape of an account takeover. `undici-types@6.21.0` is exempted: it predates the project's provenance signing and is published by the same maintainer |
| `allowBuilds` | Only `@appium/coresim` (native iOS simulator helper) and `appium-ios-tuntap` may run install scripts. `appium`'s own auto-install, the Edge and Firefox driver downloads, and two harmless scripts are denied. Any new script fails the install |
| `ignoredOptionalDependencies: [applesign]` | It pulls two packages straight from personal GitHub repos, and it's only used to sign WebDriverAgent for physical iPhones |
| `nodeLinker: hoisted` | A flat `node_modules`, which is how Appium expects to find its drivers |

If setup fails on one of these, that's the protection working. Don't loosen the setting to get past it; read
the error and decide on purpose.

## The screen map

For each platform, `data/screens.json` maps a screen id to three things, in its `ios` and `android` blocks:
- the source files that render it;
- the steps that reach it from the dashboard: `tap`, optionally with an `expect`, and `scroll_to`;
- an `anchor` that proves it loaded.

iOS locators are predicate strings. Android locators are resource ids or texts (see the top of
`scripts/platforms.py`).

`data/app.json` holds what every screen shares:
- **at the top level, the labels shared by both platforms:** blocked, dismiss and alert labels, plus the
  protected domains;
- **in `ios` and `android`, the platform's locators:** the login, the Home check, the back button, and loading
  indicators.

The automation lessons behind these are in `skills/verifying-screens-on-devices/references/automation-notes.md`.

To add a screen, ask Claude to explore it. It proposes an entry, and you add it here. Anchor it on content
(an empty-state text, a field, a cell), never on the navigation bar.

## Known limitations

- **iOS 26.5, not 27.0.** The app crashes at launch on iOS 27.0 until it adopts the UIScene lifecycle. Change
  the runtime in `data/devices.json` back once it does.
- **Android Debug builds need `-p:EmbedAssembliesIntoApk=true`.** Without it the APK has no assemblies and runs
  stale ones from an earlier Fast Deployment. The skill builds with the flag.
- **Screens that need input**, such as a custom date range, can't be prepared: steps only tap and scroll.
- **Feature flags change the dashboard.** A screen whose row is missing on one device is reported as
  unreachable there.
- **An iPad navigation-bar bug** in the build tested sometimes shows the wrong bar items after going back. The
  script recovers by relaunching and logging in again, and records it under `relaunches`.

## Working on this plugin

Same loop as `winteam-standards`: **edit → bump `version` in `.claude-plugin/plugin.json` → validate → push.**
Bump the minor version for a new or removed skill, command or screen, and the patch for wording.

```bash
claude plugin validate .
claude plugin validate plugins/winteam-device-testing --strict
python3 -m py_compile plugins/winteam-device-testing/scripts/*.py   # macOS system Python 3.9: no 3.10+ syntax
```

To iterate without the plugin cache, run from the WinTeam-Mobile root:

```bash
claude --plugin-dir ../winteam-claude-plugins/plugins/winteam-standards \
       --plugin-dir ../winteam-claude-plugins/plugins/winteam-device-testing
```

**Updating Appium:**
1. Change the ranges in `appium/package.json`.
2. Run `pnpm install` in a copy of `appium/`, with the same `pnpm-workspace.yaml`.
3. Read anything it blocks before allowing it.
4. Copy the new `pnpm-lock.yaml` back.
5. Bump the version.

The scripts use only the Python standard library, so never add a pip dependency.
