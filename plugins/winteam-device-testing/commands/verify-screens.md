---
description: Capture WinTeam screens on the iOS phone and tablet simulators and compare them for sizing and layout problems
allowed-tools: Bash, Read, Glob, Grep, Skill
argument-hint: "<screen ids | file paths | --changed | all>"
disable-model-invocation: true
---

Scope: `$ARGUMENTS`

| Argument | Screens |
|---|---|
| Screen ids from `data/screens.json`, such as `home schedule` | Those screens |
| File paths | The screens whose `ios.files` globs match them |
| `--changed` | The screens matching the iOS xibs, storyboards and view `.cs` files in the working diff |
| `all` | Every screen in the map |

An empty argument is refused. List the screen ids in `${CLAUDE_PLUGIN_ROOT}/data/screens.json` and ask which.

Invoke `winteam-device-testing:verifying-screens-on-devices` and follow it with this scope. It builds, installs,
captures, checks and reports. It changes no app code.
