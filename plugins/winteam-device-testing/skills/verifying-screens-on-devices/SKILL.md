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
`${CLAUDE_PLUGIN_DATA}/runs`. Run commands from the WinTeam-Mobile root. **Never start an Appium server
yourself.** Appium logs every typed string, the password included. The capture script starts its own with
logging off, and stops it.

1. **Resolve the scope.** Read `${CLAUDE_PLUGIN_ROOT}/data/screens.json`.
   - Map each touched file to the screens whose `ios.files` or `android.files` globs match it. An iOS file
     selects that screen on iOS, an Android file on Android.
   - An edit to `WinTeam.Mobile.Android/Resources/values*/dimens.xml` or `styles.xml` selects every screen that
     has an `android` block.
   - State the mapping. A file no screen matches goes to step 7.
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
   - iOS: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run_capture.py --data ${CLAUDE_PLUGIN_ROOT}/data --runs ${CLAUDE_PLUGIN_DATA}/runs --appium-home ${CLAUDE_PLUGIN_DATA}/appium --screens <ids>`
   - Android: the same command, plus
     `--platform android --apk WinTeam.Mobile.Android/bin/Debug/net10.0-android/com.workwave.winteam-Signed.apk`.

   The script prunes expired runs, creates a new run folder and prints its path. On Android it also:
   - boots the emulators headless;
   - checks the tablet resolves the `xlarge` size bucket;
   - installs the APK;
   - clears logcat after the login and at the end;
   - shuts down the emulators it booted.

   The first iOS session on a simulator builds WebDriverAgent, which takes several minutes, so set a long
   timeout. A screen that fails is recorded in `manifest.json` and the others still run. If the test account
   belongs to several tenants, pass `--tenant <name>` or set `WT_TEST_TENANT`.
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
6. **Clean up.** Shut down the iOS simulators this run booted, with `xcrun simctl shutdown <udid>`. The Android
   script already shut down its emulators.
7. **Unmapped screens.** If the user wants one covered, explore it with the `appium-mcp` tools. Read
   `references/automation-notes.md` first. Reading tools run freely; every action prompts the user for
   approval. Then **propose** a `screens.json` entry in the report: id, `files` globs, `steps` and an `anchor`,
   under `ios` or `android`. Add `"domain": "timeclock"` only if the screen is the Time clock page or something
   reached from it. Do not write it into the plugin from this session.
8. **Report**, per screen: a row for each platform, device and orientation, with what you saw and the
   `check_layout.py` findings you kept. Then:
   - the run folders;
   - the screens that could not be reached, and why. A row missing on one device's dashboard is usually a
     feature flag; a `relaunches` entry in `manifest.json` means the app had to be restarted to get back to
     Home, which is worth reporting as a navigation bug. A `device` error means that device couldn't give a
     meaningful capture, for example a tablet in the wrong size bucket;
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
     domain's `allowedTaps`, which are the tabs and page titles. Punch log and Timekeeping are not part of the
     domain. They are open to explore, with `blockedLabels` still refused.
   - It never accepts an alert, except a lone `OK`.

   A `blocked` error in `manifest.json` means this protection worked. Report it, and never work around it.
   Through the MCP, ask before every action, including Android's back key (`appium_mobile_press_key`). On the
   Time clock page, tap only a tab or a page title (`Punch log`, `Timekeeping`, `Home`), never anything else on
   that page. On Punch log and Timekeeping you may tap rows, cells and filters to explore, but never a
   `blockedLabels` button. Scrolling runs without a prompt.
5. **Map only what changed.** Screenshots and page sources contain account data: names, jobs, tax forms. Add a
   screen to the map when a change touches it, never to cover the whole app. Runs stay in
   `${CLAUDE_PLUGIN_DATA}/runs`, are pruned after `retentionDays`, and are never copied into a repository.
6. **Anchor on content, not chrome.** A screen's `anchor` matches something its content shows once loaded,
   such as an empty-state message, a field or a cell. Never use the navigation bar, the toolbar or the tab bar:
   on tablets those are where the bugs show up, and an anchor on them would hide the bug instead of capturing it.

## Verify

`manifest.json` lists each requested screen under both `phone` and `tablet`, with no entries in `errors`. Each
capture has a `.png` and an `.xml`. Nothing in the transcript contains the password.
