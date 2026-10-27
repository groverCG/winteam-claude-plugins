---
description: Install the pinned Appium setup into this plugin's data folder and check simulators and test credentials
allowed-tools: Bash, Read
disable-model-invocation: true
---

Prepare this machine for `winteam-device-testing`. Run this once, and again after every plugin update, since an
update can bring a new lockfile. It writes nothing outside `${CLAUDE_PLUGIN_DATA}`.

## Step 1 — Tools

Check that `node`, `pnpm` and `xcrun` are on `PATH`, and print their versions. If one is missing, stop and point
to the README's *Prerequisites*. Install `node` and `pnpm` with Homebrew. **Do not install pnpm through npm.**

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
"$APPIUM_HOME/node_modules/.bin/appium" driver list --installed
"$APPIUM_HOME/node_modules/.bin/appium" driver doctor xcuitest
```

`xcuitest` must be listed, and the doctor must report 0 required fixes. Optional fixes are informational only.

## Step 4 — Simulators

Read `${CLAUDE_PLUGIN_ROOT}/data/devices.json`. Match each `ios` entry by `name` and `runtime` in
`xcrun simctl list devices available -j`, where runtime `iOS 27.0` is the key ending in `SimRuntime.iOS-27-0`.
Report each one as found, with its UDID, or missing. **Never create or delete a simulator.** Point to Xcode >
Window > Devices and Simulators instead.

## Step 5 — Credentials

Check that the credentials exist, without ever printing the password:

```bash
security find-generic-password -s winteam-device-testing >/dev/null 2>&1 && echo "keychain: found" || echo "keychain: missing"
[ -n "$WT_TEST_USER" ] && [ -n "$WT_TEST_PASSWORD" ] && echo "env: set" || echo "env: not set"
```

Never run `security find-generic-password` with `-w` or `-g` here. If neither source is present, show the
README's *Test credentials* command for the user to run themselves.

## Report

A short table with Tools, Appium install, XCUITest driver, each simulator and Credentials, each ok or with the
problem. Then:

- **after the first successful setup:** restart Claude Code so the bundled `appium-mcp` server starts;
- **otherwise:** the one thing to fix next.
