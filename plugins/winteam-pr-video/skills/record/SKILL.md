---
name: record
description: >-
  Record a before/after video of a WinTeam Mobile fix for its pull request: build the PR's base and the branch,
  run a scenario that reproduces the ticket on the Android emulator and/or iOS simulator, and make a labelled
  side-by-side video. Asks before pushing and opening the PR. Use for "/winteam-pr-video:record MO-1234",
  "record a video of the fix", "PR video".
argument-hint: <TICKET> [--base <branch>] [--platform android|ios|both] [--pr] [--allow-dirty]
allowed-tools:
  - Bash(wt-pr-video *)
  - Bash(git status *)
  - Bash(git diff *)
  - Bash(git log *)
  - Bash(git rev-parse *)
  - Bash(git merge-base *)
  - Bash(git fetch *)
  - Bash(gh pr view *)
  - Read
---

# Record a before/after video of a fix

Every step runs `wt-pr-video`, which is on PATH while this plugin is enabled. Always pass the data folder first:
`wt-pr-video --data "${CLAUDE_PLUGIN_DATA}" <command> ...` (written `wt-pr-video …` below). Run from the
WinTeam-Mobile root (`$REPO`). Add `--avd "${user_config.android_avd}" --simulator "${user_config.ios_simulator}"`
to `inspect` and `record`.

Arguments: `TICKET` (required); `--base` (default: the open PR's base branch, else `dev`); `--platform` (default:
the ticket title tag, `[Android]` / `[iOS]`; `[iOS/Android]` or no tag means both); `--pr` (push and open the PR
without asking); `--allow-dirty`.

**Never ask for, type or echo the test password.** Only `s.log_in()` / `s.sign_in()` type credentials; they read
them from the Keychain item `winteam-device-testing`.

## 0. Preflight

- `wt-pr-video … doctor`. If it reports a problem, stop and show the fixes. If it notes the missing permission
  rule, ask the user once whether to add it (`wt-pr-video … doctor --add-permission`); without it every step after
  the scenario approval prompts.
- The current branch isn't `dev` or `master`.

## 1. Read the ticket and the change

1. Read the ticket with the Atlassian connector (`getJiraIssue`): summary, steps to reproduce, expected result,
   platform tag. If the connector isn't available, ask the user to paste the repro steps and expected result (and
   the platform, without `--platform`).
2. Base: `--base`, else `gh pr view --json baseRefName -q .baseRefName`, else `dev`.
3. `git fetch -q origin`, then `git diff --stat $(git merge-base HEAD origin/<base>)...HEAD`. Read only the
   changed files that tell you which screens and states the fix touches.

## 2. Run folder and builds (start early; each build takes minutes)

1. `wt-pr-video … new-run <TICKET>` prints the run folder (`$RUN` below). Run each `wt-pr-video` command on its
   own, without `$(...)` or pipes, so the permission rule matches it.
2. `git status --porcelain`: if dirty and no `--allow-dirty`, list the files and ask whether to build the "after"
   version with them. If yes, the after label gets `+local`.
3. `wt-pr-video … base $REPO <base> --copy "${user_config.worktree_files}"` prints `<worktree> <sha>`.
4. In the background, one chain per source tree (the two platforms of one tree share build folders, so never
   build them in parallel): `wt-pr-video build <platform> <worktree> $RUN/before-<platform>` and
   `wt-pr-video build <platform> $REPO $RUN/after-<platform>`. Each prints the `.apk` / `.app` path.

## 3. Write the scenario

1. Read `references/scenario-api.md` and the UI facts for each platform you record
   (`references/android.md`, `references/ios.md`).
2. Don't guess locators. Once an "after" build exists, explore the real screens:
   `wt-pr-video … inspect <platform> $RUN/ui/<step> [--app <app>] [--do '<python using s>']`. `--app`
   clean-installs and launches; without it, inspect attaches to the app as it is. It prints the visible elements;
   the screenshot is `<prefix>.png`, worth reading only when the list isn't enough. On the sign-in page it saves
   nothing, by design.
3. Write `$RUN/scenario.py`. It runs unchanged on both builds and both platforms, from a fresh install.
   `setup(s)` (not recorded) prepares the state: `s.sign_in(...)`, `s.log_out()`, … . `run(s)` (recorded) does the
   repro steps with short `s.pause()`s so the video is watchable, then `s.check(...)` for the expected result.
   Never change app code to make it easier.
4. `wt-pr-video … check $RUN/scenario.py` lists the data-changing buttons it names. Show the user the scenario
   and that list (with its warning, if any) and wait for approval.

## 4. Record (per platform: before, then after)

`wt-pr-video … record <platform> <app> $RUN/scenario.py <before|after> $RUN/<platform>-<before|after>.mp4`

- Exit 2 on `after`: the fix isn't proven. Show the user the video and `$RUN/<platform>-after.json`, and stop.
  Nothing gets pushed.
- Exit 1: scenario error. `wt-pr-video log $RUN` shows the Appium errors. Fix the scenario, tell the user what
  changed, and record again.
- Before a recording counts, look at a frame or two: `wt-pr-video frame <mp4> <seconds> $RUN/frame.png`.

## 5. Video, then ask

1. Per platform: `wt-pr-video sidebyside $RUN/<p>-before.mp4 $RUN/<p>-after.mp4 "BEFORE · <base>@<base sha7>"
   "AFTER · <branch>@<head sha7>[+local]" $RUN/<TICKET>-<p>.mp4`.
2. Report the video path(s) and the check results.
3. Unless `--pr`, ask: "Push and open the PR?" If yes: `git push -u origin HEAD` when there are unpushed commits;
   if `gh pr view` finds no PR, `gh pr create --base <base>` with the title `[<TICKET>] <ticket summary>` and a
   body of the ticket URL plus a 1–2 sentence summary of the fix.
4. `open -R <video>` and, when there is a PR, `open <PR URL>`. Tell the user to drag the video into the PR
   description (GitHub has no API for video uploads).

Runs are deleted after 7 days.
