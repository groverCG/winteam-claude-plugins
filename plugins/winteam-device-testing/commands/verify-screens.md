---
description: Capture WinTeam screens on a phone and a tablet (iOS simulators; Android emulators, or physical devices over USB) and compare them for sizing and layout problems
allowed-tools: Bash, Read, Glob, Grep, Skill
argument-hint: "<screen ids | file paths | --changed | all> [--ios | --android]"
disable-model-invocation: true
---

Scope: `$ARGUMENTS`

| Argument | Screens |
|---|---|
| Screen ids from `data/screens.json`, such as `home schedule` | Those screens, on each platform they are mapped for |
| File paths | The screens whose `ios.files` or `android.files` globs match them, on that file's platform |
| `--changed` | The screens matching the iOS xibs, storyboards and view `.cs` files, and the Android layouts, `values*/dimens.xml`, `styles.xml` and view `.cs` files, in the working diff |
| `all` | Every screen in the map, on both platforms |

Add `--ios` or `--android` to limit the run to one platform. An empty argument is refused. List the screen ids
in `${CLAUDE_PLUGIN_ROOT}/data/screens.json` and ask which.

Invoke `winteam-device-testing:verifying-screens-on-devices` and follow it with this scope. It builds, installs,
captures, checks and reports. It changes no app code.
