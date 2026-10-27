# winteam-device-testing

Runs WinTeam on an **iPhone and an iPad simulator** to check UI changes visually.

- It logs into the **Testing** environment.
- It opens the screens a change touched, using a screen map.
- It captures a screenshot and the page source of each, in portrait and landscape.
- It flags layout problems, most usefully **elements that stay at phone size on the tablet**.

Claude then compares the phone and tablet screenshots side by side and reports what it sees.

This covers the visual check `/winteam-standards:scale-for-tablets` ends with. When this plugin is installed,
that command hands its touched files here instead of leaving the check to you.

**iOS only for now.** Android screens stay a manual check.

## Why this is a separate plugin

`winteam-standards` works with no setup. This plugin needs Node, pnpm, Appium, Xcode simulators and a
test account, so it's opt-in. It depends on `winteam-standards` and never copies anything from it: sizing
rules stay in one place.

## Prerequisites

| What | How |
|---|---|
| Xcode with an **iPhone 17** and an **iPad Pro 13-inch (M5)** simulator on **iOS 27.0** | Xcode > Window > Devices and Simulators. To use others, change `data/devices.json` |
| Node and pnpm | `brew install node pnpm`. **Don't install pnpm through npm** |
| A Debug build of WinTeam.Mobile.iOS that compiles | The skill builds and installs it on both simulators |
| A test account in the **Testing** environment, without MFA | See *Test credentials* |

`JAVA_HOME` and `ANDROID_HOME` in `~/.zshrc` will be needed once Android is supported, not yet.

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

## Use

```
/winteam-device-testing:verify-screens schedule jobs
/winteam-device-testing:verify-screens WinTeam.Mobile.iOS/Views/Cells/Schedule/ScheduleViewCell.xib
/winteam-device-testing:verify-screens --changed
```

`/winteam-standards:scale-for-tablets` calls the same skill, `verifying-screens-on-devices`, on its own at its
Step 8.

A run:

1. builds the iOS app and installs it on both simulators;
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
  title or a 50 pt button on a 13" iPad;
- **overlap** between text and buttons;
- **off-screen** elements outside scrolling content;
- **tap targets** under 44 pt.

Navigation and tab bars are skipped, because they're system-managed.

The tree carries **no fonts, colours or clipping**. Those come from the screenshots, which Claude reviews. A
same-height element can be intentional, so each candidate is confirmed or dismissed against the screenshots.

## Data and safety

- **The password never reaches a log.**
  - Appium writes every typed string to its log. `run_capture.py` therefore starts its own Appium server with
    logging off and output discarded, and stops it at the end.
  - Nothing else runs an Appium server. The bundled MCP server is never used for logging in.
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
    Confirm, Continue, Log out…) are never tapped, whatever the screen map says.
  - **The TimeClock domain** (Time clock, Punch log, Timekeeping) is navigation-only. On those screens the script
    may only tap the tabs and page titles. It reads and captures everything else.
  - **Alerts** get a known-safe button pressed by name (Cancel, Not now, Don't Allow…), or OK when it's their
    only button. Any other alert stops that screen.
  - A refusal shows up as a `blocked` error in the run's `manifest.json`.
  - The only taps outside this check are the fixed login steps: the environment picker, Log In, and the email
    field.
- **The Appium MCP tools ask before acting.** A `PreToolUse` hook lets reading tools (page source, find
  element, screenshot, text, attributes) run freely. Every other tool, including any future one, shows an
  approval prompt warning that it can tap or type anywhere in the app, including Clock in/out and Submit. The
  prompt appears in auto mode too. The hook can't tell which button a tap targets, because it only sees an
  element ID or coordinates, so it asks for every action.
- **The Testing environment only.** The script switches each simulator to Testing and stops if it can't. It
  checks the sign-in form before submitting it.

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

`data/screens.json` maps a screen id to the source files that render it, the steps that reach it from the
dashboard, and an `anchor` that proves it loaded. `data/app.json` holds what every screen shares: the bundle
id, the login, the Home check, the back button, and the prompt labels to dismiss. The automation lessons
behind these are in `skills/verifying-screens-on-devices/references/ios-automation-notes.md`.

To add a screen, ask Claude to explore it. It proposes an entry, and you add it here. Anchor it on content
(an empty-state text, a field, a cell), never on the navigation bar.

## Known limitations

- **iOS only.** Android needs a tablet emulator and a tested login through the embedded web view.
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
