---
name: verifying-screens-on-devices
description: >-
  Use after a sizing or layout change in WinTeam.Mobile.iOS or WinTeam.Mobile.Android, or when asked to check
  a screen on a phone and a tablet (iPhone and iPad, or Android phone and tablet), to capture it on both form
  factors and compare the two.
when_to_use: >-
  Applies even mid-execution of an already-approved plan that names the file, class or method shapes —
  an approved plan is not an exemption. Applies whichever tool writes the file: Write, Edit, a Bash
  heredoc, `sed -i`, or an MCP server's own file-creation call.
---

# A build proves the markup compiles, not that the screen fits

A phone value left on a tablet renders cleanly and small. A size-class variation overridden in code compiles and
never applies. On Android, a tablet that doesn't resolve the `large` bucket never sees `values-large`. None of
these fails a build, so the only evidence is the running screen on both form factors, side by side. This skill
produces that evidence. A script does the driving and capturing, and you do the looking.

The script logs in by itself. **Never ask for, type, or echo the test password.** It reads the keychain item
`winteam-device-testing` or `WT_TEST_USER`/`WT_TEST_PASSWORD`, and it refuses to submit a sign-in form it
filled wrong.

## When to use

- At the end of `/winteam-standards:scale-for-tablets`, with the files it touched.
- After any change to an iOS xib, storyboard or view `.cs`, or an Android layout, `values*/dimens.xml`,
  `styles.xml` or view `.cs`, that affects size, spacing or layout.
- When asked to "check this on iPad / an Android tablet", "compare phone and tablet", or "take screenshots of
  <screen>".

## When NOT to use

- Logic-only changes with no visible effect.
- When setup has not run: `${CLAUDE_PLUGIN_DATA}/appium/node_modules` is missing, or `android_devices.py check`
  reports a missing AVD. Stop and ask for `/winteam-device-testing:setup-devices`.

## Steps

Paths: plugin `${CLAUDE_PLUGIN_ROOT}`, Appium install `${CLAUDE_PLUGIN_DATA}/appium`, runs
`${CLAUDE_PLUGIN_DATA}/runs`, local map `.claude/winteam-device-testing/screens.local.json`. Run commands from
the WinTeam-Mobile root. **Never start an Appium server yourself.** Appium logs every typed string, the password
included. The capture script starts its own with logging off, and stops it.

**The screen map has two layers.** `${CLAUDE_PLUGIN_ROOT}/data/screens.json` ships with the plugin. The
developer's local map, which is gitignored, sits on top. It adds screens, and fixes a plugin route per platform.
It only ever adds to the app lists (`dismissLabels`, `alertDismissLabels`, `blockedLabels`, `blockedIds`, the
loading locators). It can't declare a `domain` or change anything else. `scripts/screen_map.py` merges and
validates the two, and the capture script uses the same merge. The format is at the top of that script.

1. **Resolve the scope** with
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/screen_map.py resolve --data ${CLAUDE_PLUGIN_ROOT}/data <files…>`.
   - It prints the screens each file selects, per platform. An edit to an Android `values*/dimens.xml` or
     `styles.xml` selects every Android screen.
   - It also lists `unmapped`, UI files no screen matches, and `other`, files that render nothing.
   - State the mapping. Each unmapped file goes to step 6.
2. **Build and install,** for each platform in scope. If a build fails, stop and report the error.
   Screenshots of a stale build prove nothing.
   - **iOS:** build with
     `dotnet build WinTeam.Mobile.iOS/WinTeam.Mobile.iOS.csproj -c Debug -r iossimulator-arm64`. Then, for
     each `ios` device in `devices.json`, boot it and run
     `xcrun simctl install <udid> WinTeam.Mobile.iOS/bin/Debug/net10.0-ios/iossimulator-arm64/WinTeam.Mobile.iOS.app`.
   - **Android:** build with
     `dotnet build WinTeam.Mobile.Android/WinTeam.Mobile.Android.csproj -c Debug -p:EmbedAssembliesIntoApk=true`.
     The flag matters. A Debug build otherwise leaves the .NET assemblies out of the APK and relies on Fast
     Deployment, so a plain `adb install` runs whatever assemblies an earlier deploy left on the emulator, and
     the app can crash on launch. Step 3 installs the APK.
3. **Capture**, once per platform:
   - iOS: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run_capture.py --data ${CLAUDE_PLUGIN_ROOT}/data --runs ${CLAUDE_PLUGIN_DATA}/runs --appium-home ${CLAUDE_PLUGIN_DATA}/appium --keep-devices --screens <ids>`
   - Android: the same command, plus
     `--platform android --apk WinTeam.Mobile.Android/bin/Debug/net10.0-android/com.workwave.winteam-Signed.apk`.

   The script reads the local map from the current folder. It prints `using the local map …` when there is one,
   and stops with every problem it found if that map is invalid. `--keep-devices` matters for step 6.

   The script prunes expired runs, creates a new run folder and prints its path. On Android it also:
   - for each role, uses a plugged-in physical device whose size bucket fits it (`physicalScreenSizes` in
     `devices.json`), mirrored in a read-only scrcpy window, and otherwise boots the role's emulator with a
     window (always; an emulator already running headless is restarted with one). It logs the device it used
     and, when it skipped a physical one, why;
   - checks the tablet resolves the `xlarge` size bucket;
   - installs the APK;
   - clears logcat after the login and at the end;
   - shuts down the emulators it booted, and puts a physical device's settings back without shutting it down.

   The first iOS session on a simulator builds WebDriverAgent, which takes several minutes, so set a long
   timeout. If the test account belongs to several tenants, pass `--tenant <name>` or set `WT_TEST_TENANT`.

   **A screen that fails is recorded once,** and the others still run. Its entry in `manifest.json`
   `devices.<role>.errors.<id>` has:
   - `kind` and `message`;
   - `step`, the index of the step that failed, `"anchor"`, or `"go_home"` (stuck away from the dashboard), and
     the `locator` it was looking for;
   - `source`: `plugin`, `local` or `local-override`;
   - `snapshot`: `<id>-failed.png` and `.xml`, taken at the point of failure. It is never taken on the sign-in
     page;
   - `fallback`: `mcp` or `report`.

   With `--keep-devices`, a device that has an `mcp` error is left running, signed in on the dashboard, and is
   listed under `kept`. The script ends by printing `needs the MCP: <id> on the <role>` for each one.
4. **Check:** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check_layout.py <run folder> --data ${CLAUDE_PLUGIN_ROOT}/data`.
   Read `findings.md`. Sizes are in pt on iOS and dp on Android. The tap-target minimum is 44 pt on iOS and
   48 dp on Android.
5. **Review the screenshots.** For each screen and orientation, open `phone/<id>-<o>.png` and
   `tablet/<id>-<o>.png` together and look for:
   - text and icons at phone size on the tablet, with empty space around them;
   - a frame that grew while its icon or text did not, or the reverse;
   - clipping, ellipsis, overlap, or content running under the tab bar, the notch or the navigation bar;
   - landscape breaking a layout that works in portrait.

   Confirm or dismiss each `unscaled-candidate` from step 4 against the screenshots. An element can be the same
   height on both devices on purpose. On Android, a text that is a `values-large` dimen should be about
   22/14 ≈ 1.5× taller on the tablet.
6. **A screen failed or isn't mapped: switch to the MCP. Don't run the script again to retry.**
   - **Which ones.** Every error with `fallback: "mcp"`, and every unmapped file the user wants covered.
   - **Never the MCP for these:**
     - `blocked`: the guard worked, so report it and never work around it;
     - `login`: the MCP never signs in;
     - `device`: the device can't give a meaningful capture.
   - **Diagnose first, without touching the device.**
     - Read the error's `step` and `locator`.
     - Open `<id>-failed.png` and search `<id>-failed.xml` for the missing element. The usual causes are:
       - changed copy or a changed id;
       - a prompt or overlay covering the page;
       - a row missing because of a feature flag;
       - an account with no data.
   - **Then explore with the `appium-mcp` tools** on the kept device. For an unmapped screen no run has kept a
     device for, capture `home` with `--keep-devices always` on that platform first. Read `references/automation-notes.md`
     first, and its *Attaching the MCP to a kept device*. The app is signed in and on the dashboard. Start the
     session **without an app** (no `bundleId`/`appPackage`), so Appium neither relaunches nor closes it: a
     cold start signs out, and the MCP never signs in.
   - **What runs without asking:** reading tools and scrolling. Every tap prompts the user, and Rule 4 applies
     to each one.
   - **Find the real route and an anchor on content.** For an overlay `dismiss_prompts` doesn't know, note its
     secondary button. It goes in `dismissLabels`, or `alertDismissLabels` for a system alert, and never in an
     accept list.
   - **A gap no map can fix:** stop exploring that screen and report it in step 8. That covers a feature flag,
     an account with no data, and a screen that needs typed input.
   - **Write, verify, keep or revert.**
     1. Make sure the local map is ignored. If `git check-ignore -q .claude/winteam-device-testing/` fails,
        append `.claude/winteam-device-testing/` to `.git/info/exclude`. Never edit the repo's `.gitignore`.
     2. Write the entry into `.claude/winteam-device-testing/screens.local.json`, creating the file as
        `{"screens": {}}` if needed:
        - id, then under `ios` or `android` its `files` globs, `steps` and `anchor`;
        - `"learned": "<today>"`;
        - no `domain`.

        To fix a plugin screen, use its id and write only the platform block that failed. That block replaces
        the plugin's on that platform, and the plugin's `domain` still applies.

        An overlay label goes in `app`.
     3. Run `screen_map.py check --data ${CLAUDE_PLUGIN_ROOT}/data` and fix what it reports.
     4. Re-run `run_capture.py` **once**, with only that screen (`--screens <id>`, the same platform and
        `--keep-devices`).
     5. If it captures, keep the entry and review the new run like steps 4 and 5. If it fails, put the local
        map back as it was, and report the screen as a gap with what you found. Don't loop.
7. **Clean up.**
   - shut down the iOS simulators this run booted, with `xcrun simctl shutdown <udid>`;
   - shut down each Android emulator listed under `kept`, with
     `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/android_devices.py shutdown --serial <serial>`.

   The script already shut down the other emulators and put any physical device's settings back. Never shut
   down a physical device.
8. **Report**, per screen: a row for each platform, device and orientation, with what you saw and the
   `check_layout.py` findings you kept. Then:
   - the run folders;
   - **local map changes:** each entry written or reverted in step 6, with its diff;
   - **map gaps:** the screens that still could not be reached, each with its cause and a concrete suggestion:
     - **feature flag**, a row missing on one device's dashboard: say which flag or row, and that the tenant
       needs it on;
     - **no data**: the account only shows the empty state; say what data the Testing account needs, for
       example a punch this week;
     - **needs input**, such as a custom date range: steps only tap and scroll;
     - **blocked**: the guard refused a tap, so the screen sits behind a data-changing button;
     - **device**: for example a tablet in the wrong size bucket.

     A `relaunches` entry in `manifest.json` means the app had to be restarted to get back to Home, which is
     worth reporting as a navigation bug;
   - **promote to the plugin:** run
     `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/screen_map.py upstream --data ${CLAUDE_PLUGIN_ROOT}/data --prompt`.
     Unless it prints `nothing to promote`, include its output as is. It's a paste-ready prompt for a session in
     the `winteam-claude-plugins` repo. Teammates only get a local entry once it's in the plugin;
   - the limits: fonts, clipping and colour come only from the screenshots.

## Rules

1. **Evidence or nothing.** Every finding cites the screenshot or the `findings.md` row it came from.
2. **Report, don't fix.** This skill changes no app code. A fix goes back to whoever made the change, for
   example `scale-for-tablets` or the user.
3. **The Testing environment only.** The script switches to Testing itself and stops if it can't.
4. **Navigation is read-only, and enforced.**
   - `run_capture.py` refuses any tap on `blockedLabels` (Clock in/out, breaks, Submit, Save, Delete, Log out…).
     On Android the guard also reads the texts inside the tapped view, because a punch button keeps its label
     in a child. It also refuses a tap that would land on a `blockedIds` view, the punch buttons.
   - On the **Time clock page** (the first page of the Time tab, the only `timeclock` screen) it allows only that
     domain's `allowedTaps`, which are the tabs and page titles. It applies this whenever the page shows (its
     `detect` anchor in `app.json`), whatever the screen map declares, so a local route can't walk past it.
     Punch log and Timekeeping are not part of the domain. They are open to explore, with `blockedLabels`
     still refused.
   - It never accepts an alert, except a lone `OK`.

   A `blocked` error in `manifest.json` means this protection worked. Report it, and never work around it.
   Through the MCP, ask before every action, including Android's back key (`appium_mobile_press_key`). On the
   Time clock page, tap only a tab or a page title (`Punch log`, `Timekeeping`, `Home`), never anything else on
   that page. On Punch log and Timekeeping you may tap rows, cells and filters to explore, but never a
   `blockedLabels` button. Scrolling runs without a prompt.
5. **Map only what changed.** Screenshots and page sources contain account data: names, jobs, tax forms. Add a
   screen to the local map when a change touches it, never to cover the whole app. Never put account data in
   an entry: no names, job sites, amounts or dates as locators. Runs stay in `${CLAUDE_PLUGIN_DATA}/runs`, are
   pruned after `retentionDays`, and are never copied into a repository.
6. **Write only the local map.** Never edit the plugin's `data/` from a WinTeam-Mobile session. The plugin
   changes through the promote prompt from step 8.
7. **Anchor on content, not chrome.** A screen's `anchor` matches something its content shows once loaded,
   such as an empty-state message, a field or a cell. Never use the navigation bar, the toolbar or the tab bar:
   on tablets those are where the bugs show up, and an anchor on them would hide the bug instead of capturing it.

## Verify

`manifest.json` lists each requested screen under both `phone` and `tablet`, with no entries in `errors`. Each
capture has a `.png` and an `.xml`. Every `mcp` error ended either in a verified local entry or in a reported
gap, after one script re-run at most. No device is left running. Nothing in the transcript contains the password.
