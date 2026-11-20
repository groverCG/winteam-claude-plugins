# winteam-pr-video

Records a **before/after video of a fix** for its pull request:

- It reads the Jira ticket and the diff against the PR's base branch.
- It writes a short Python scenario that reproduces the bug, and shows it to you for approval.
- It builds the base version (in a reusable git worktree) and your branch.
- It clean-installs each on the Android emulator or iOS simulator, and records the scenario on both.
- It joins the two recordings into one labelled side-by-side video.
- Only then does it ask whether to push and open the PR.

```
/winteam-pr-video:record MO-1234
/winteam-pr-video:record MO-1234 --platform ios --base MO-8950
/winteam-pr-video:record MO-1234 --pr          # push and open the PR without asking
```

## Why it depends on winteam-device-testing

Driving WinTeam on a simulator needs the same things in both plugins:
- a vetted Appium install;
- a WebDriver client;
- a login routine that never leaks the password;
- a test account and a device list.

This plugin reuses all of them from `winteam-device-testing` and doesn't copy any. It adds the recording, the
builds, and scenario helpers that may tap any button. `winteam-device-testing` only navigates, read-only.

It imports the dependency's Python modules from wherever Claude Code installed it (`claude plugin list --json`),
and checks its version at startup (0.5.1 or later).

## Prerequisites

- **An Apple Silicon Mac.**
- **`winteam-device-testing`, set up.** Its README covers the simulators, the emulator, the pinned Appium install
  and the Testing account (`winteam-device-testing` in the Keychain, plus `WT_TEST_TENANT` if the account has
  several tenants).
- **`ffmpeg`, `gh` and .NET:**
  - `brew install ffmpeg gh`.
  - `gh auth login`, with access to the MobileCore submodule.
  - The .NET 10 SDK with the `android` and `ios` workloads.
- **Optional: the claude.ai Atlassian connector**, to read the ticket. Without it you paste the repro steps.

## Install

From your WinTeam-Mobile checkout:

```bash
claude plugin marketplace add groverCG/winteam-claude-plugins   # skip if /plugin already lists "winteam"
claude plugin install winteam-pr-video@winteam -s local          # also installs winteam-device-testing
```

Then, in Claude Code:
1. Run `/winteam-device-testing:setup-devices`, if you haven't.
2. Run `/winteam-pr-video:record` once. Its first step is `wt-pr-video doctor`, which checks everything above and
   prints the fix for anything missing. It installs nothing.

### Settings

Change them with `/plugin configure winteam-pr-video@winteam`. All are optional.

| Option | What it's for |
|---|---|
| `worktree_files` | Local files a clean checkout needs to build, comma-separated, e.g. `WinTeam.Mobile.iOS/Directory.Build.props` when your Xcode needs `ValidateXcodeVersion=false` |
| `android_avd` | Record on this AVD instead of the phone AVD in winteam-device-testing's `devices.json` |
| `ios_simulator` | Record on this simulator (name) instead of the phone in `devices.json`; the runtime stays `devices.json`'s |

### Permissions

A plugin can't ship permission rules.
- **Before you approve the scenario:** the skill's own `allowed-tools` cover its steps.
- **After that:** you would be asked before every step, so `doctor --add-permission` (the skill offers it once)
  adds `Bash(wt-pr-video *)` to `~/.claude/settings.json`, after a backup.

Every step runs through that one command, `wt-pr-video`, which this plugin puts on PATH. Its name doesn't change
between plugin versions, so the rule keeps working after updates.

Pushing and creating the PR are not covered by the rule, so they still ask.

## How a run goes

1. **Preflight**: `doctor`.
2. **Read**: the ticket (summary, repro steps, expected result, platform tag) and the diff against the base branch.
   The base is the open PR's base, or `dev`, or `--base`.
3. **Build**, in the background:
   - the base: the merge-base of your branch and the base, in `${CLAUDE_PLUGIN_DATA}/worktrees/before`. Your
     working copy is never touched;
   - your branch, from your checkout. Uncommitted changes are included only if you say so, and the label then
     gets `+local`.
4. **Scenario**: Claude explores the real screens with `wt-pr-video inspect`. That prints a short list of the
   visible elements, which is cheaper to read than a screenshot. Then it writes `scenario.py`:
   - `setup(s)` prepares the state and **isn't recorded**: sign-in, PIN, logout…
   - `run(s)` is recorded: the repro steps and `s.check(...)` for the expected result.

   `wt-pr-video check` lists the data-changing buttons the scenario names (from winteam-device-testing's
   `blockedLabels`). There's an extra warning for punches, since they create real time records on the shared
   account. You approve the scenario before anything is recorded.
5. **Record**: per platform, before then after. In `before`, a failed check is only logged, since it shows the
   bug. In `after`, a failed check stops the run, and nothing gets pushed.
6. **Video**: `BEFORE · <base>@<sha>` and `AFTER · <branch>@<sha>` side by side. Then the question: push and open
   the PR? You drag the video into the PR description, because GitHub has no API for video uploads.

The scenario API is in `skills/record/references/scenario-api.md`, with an example
(`example_scenario.py`, MO-8964 on both platforms). The UI facts per platform are in `android.md` and `ios.md`.

## Data and safety

- **The password never reaches a log or a video:**
  - The login is winteam-device-testing's keyboard-only routine, and it refuses to submit a form it filled
    wrong. If it fails during a recorded `run()`, the recording is deleted, since a frame could show the password
    in the email field.
  - Appium runs on its own port, never shared with winteam-device-testing, and is stopped after every run. It
    logs to the run folder at info level, so response bodies stay out: the login reads the Android password field
    back to check its length. `runner/appium-log-filters.json` redacts typed text, single keys included, and any
    response body that still gets through.
  - Android: logcat is cleared after sign-in and after every run, and the last typed character isn't shown.
  - `inspect` saves nothing while the sign-in page is showing: on Android its element tree holds the typed
    password.
- **What stays visible:** the test account's email shows on the app's own screens (the PIN screen, for one).
  Signing in inside `setup()` keeps the sign-in page out of the video.
- **Where things are kept:**
  - Runs are stored in `${CLAUDE_PLUGIN_DATA}/runs/` and deleted after **7 days**, at every session start (a
    `SessionStart` hook) and whenever a run starts. `wt-pr-video prune --all` deletes them all.
  - The base worktree, `${CLAUDE_PLUGIN_DATA}/worktrees/before`, is reused between runs.
  - Uninstalling the plugin deletes the data folder. `git worktree prune` in WinTeam-Mobile then drops the stale
    entry.
- **Nothing secret is in this repository.** The account, tenant and Jira access all live on your machine.

## Known limitations

- **iOS recordings stay portrait.** After `setOrientation('LANDSCAPE')`, that part of the video shows the screen
  turned 90°.
- **Android biometrics** need a fingerprint enrolled on the emulator (see `references/android.md`). The emulator
  runs with `-no-snapshot-save`, so the enrollment is lost when it restarts.
- **Testing environment only**, like winteam-device-testing.
- **A notifications prompt or tenant picker can take 30–90 s** after sign-in. That wait is in `setup()`, not in
  the video.

## Working on this plugin

Edit, bump `version` in `.claude-plugin/plugin.json`, validate, push.

```bash
claude plugin validate plugins/winteam-pr-video --strict
python3 -m py_compile plugins/winteam-pr-video/runner/*.py   # macOS system Python 3.9: no 3.10+ syntax
```

To run it from a checkout, set these:
- `WT_DEVICE_TESTING_ROOT`: a winteam-device-testing checkout, instead of the installed plugin.
- `WT_DEVICE_TESTING_DATA`: its data folder.
- `WT_PR_VIDEO_APPIUM`: another `appium` binary.
- `WT_TEST_USER` / `WT_TEST_PASSWORD`: credentials, instead of the Keychain.

Then call `bin/wt-pr-video --data <folder> …` directly.

### Alternative considered

This could be a skill inside `winteam-device-testing` instead of a separate plugin:
- It would share `${CLAUDE_PLUGIN_DATA}` (the Appium install) without looking the dependency up.
- It would widen a read-only plugin to one that taps data-changing buttons and pushes branches.

It's a separate plugin for now. Merging them later is straightforward: `runner/` and `skills/record/` would move
over.
