---
description: Install the pinned Appium setup into this plugin's data folder, and check the iOS simulators, the Android emulators (creating the tablet AVD) and the test credentials
allowed-tools: Bash, Read
disable-model-invocation: true
---

Prepare this machine for `winteam-device-testing`. Run this once, and again after every plugin update, since an
update can bring a new lockfile.

It writes only to:
- `${CLAUDE_PLUGIN_DATA}`;
- the Android tablet AVD named in `devices.json`, if that AVD is missing. It goes under `~/.android/avd`.

It never modifies or deletes an existing simulator or AVD.

## Step 1 — Tools

Check that these are available, and print their versions:
- `node`, `pnpm` and `xcrun` on `PATH`;
- `java` (`java -version`);
- `adb` and `emulator` from the Android SDK, at `$ANDROID_HOME`, or `~/Library/Android/sdk` when that is unset:
  `"$SDK/platform-tools/adb" version` and `"$SDK/emulator/emulator" -version`.

If one is missing, stop and point to the README's *Prerequisites*. Install `node` and `pnpm` with Homebrew.
**Do not install pnpm through npm.** A missing Android SDK, emulator or Java is installed through Android
Studio. Without them, only iOS works; report this and go on with the iOS checks.

## Step 2 — Install Appium

```bash
mkdir -p "${CLAUDE_PLUGIN_DATA}/appium"
cp "${CLAUDE_PLUGIN_ROOT}/appium/package.json" "${CLAUDE_PLUGIN_ROOT}/appium/pnpm-workspace.yaml" \
   "${CLAUDE_PLUGIN_ROOT}/appium/pnpm-lock.yaml" "${CLAUDE_PLUGIN_DATA}/appium/"
cd "${CLAUDE_PLUGIN_DATA}/appium" && pnpm install --frozen-lockfile
```

`--frozen-lockfile` installs exactly what the lockfile pins, or fails. **If it fails, report the error and
stop.** Do not retry without the flag, do not edit `pnpm-workspace.yaml` to get past a blocked build script or
a trust-policy error, and do not switch to npm. Those failures are the safety settings working. Explain them
from the README's *Why pnpm, and what the settings do*.

## Step 3 — Driver check

```bash
export APPIUM_HOME="${CLAUDE_PLUGIN_DATA}/appium"
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
export JAVA_HOME="${JAVA_HOME:-$(/usr/libexec/java_home)}"
"$APPIUM_HOME/node_modules/.bin/appium" driver list --installed
"$APPIUM_HOME/node_modules/.bin/appium" driver doctor xcuitest
"$APPIUM_HOME/node_modules/.bin/appium" driver doctor uiautomator2
```

- `xcuitest` and `uiautomator2` must both be listed.
- Each doctor must report 0 required fixes. Optional fixes are informational only.
- The lockfile pins both drivers. **If `uiautomator2` is missing, run Step 2 again.** Never use
  `appium driver install`: it fetches a driver outside the lockfile and its safety settings.

## Step 4 — iOS simulators

Read `${CLAUDE_PLUGIN_ROOT}/data/devices.json`. Match each `ios` entry by `name` and `runtime` in
`xcrun simctl list devices available -j`, where runtime `iOS 26.5` is the key ending in `SimRuntime.iOS-26-5`.
Report each one as found, with its UDID, or missing. **Never create or delete a simulator.** Point to Xcode >
Window > Devices and Simulators instead.

## Step 5 — Android emulators

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/android_devices.py" check --data "${CLAUDE_PLUGIN_ROOT}/data"
```

1. **Phone AVD missing:** report it and point to Android Studio > Device Manager. Don't create it.
2. **Tablet AVD missing:** create it from its `create` entry in `devices.json`. The script copies the source
   AVD's `config.ini` with a 2560×1600, 320 dpi screen, and refuses to overwrite an existing AVD:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/android_devices.py" create-avd --data "${CLAUDE_PLUGIN_ROOT}/data" --role tablet
   ```
3. **Confirm each AVD's size bucket.** This boots the AVD headless (the first boot of a new AVD takes a
   minute or two), prints its bucket, and shuts down an emulator it started:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/android_devices.py" bucket --data "${CLAUDE_PLUGIN_ROOT}/data" --role phone
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/android_devices.py" bucket --data "${CLAUDE_PLUGIN_ROOT}/data" --role tablet
   ```
   The phone must read `normal` and the tablet `xlarge`. A tablet in any other bucket doesn't get
   `values-large`, so its captures would prove nothing. Report it as a failure.

## Step 6 — Credentials

Check that the credentials exist, without ever printing the password:

```bash
security find-generic-password -s winteam-device-testing >/dev/null 2>&1 && echo "keychain: found" || echo "keychain: missing"
[ -n "$WT_TEST_USER" ] && [ -n "$WT_TEST_PASSWORD" ] && echo "env: set" || echo "env: not set"
```

Never run `security find-generic-password` with `-w` or `-g` here. If neither source is present, show the
README's *Test credentials* command for the user to run themselves.

## Report

A short table with one row per check, each ok or with the problem: Tools, Appium install, XCUITest driver,
UiAutomator2 driver, each simulator, each AVD (with its bucket, and "created" if this run created it) and
Credentials. Then:

- **after the first successful setup:** restart Claude Code so the bundled `appium-mcp` server starts;
- **otherwise:** the one thing to fix next.
