# winteam-claude-plugins

Claude Code plugin marketplace (`winteam`) for the WinTeam mobile app.

| Plugin | What it does |
|---|---|
| [`winteam-standards`](plugins/winteam-standards/README.md) | Code standards (size caps, layering, DI, MVVM, teardown, theming, `AppStrings`) as skills, advisory hooks and audit commands, a `scale-for-tablets` fixer, plus four report-only review agents |
| [`winteam-device-testing`](plugins/winteam-device-testing/README.md) | Optional. Captures the screens a UI change touched on a phone and a tablet (iPhone and iPad simulators, or Android phone and tablet emulators), and compares them for sizing and layout problems. Picks up `scale-for-tablets`' visual checks. **Needs setup**: Node, pnpm, Xcode simulators, the Android SDK and emulator, and a Testing account |
| [`winteam-pr-video`](plugins/winteam-pr-video/README.md) | Optional. Records a before/after video of a fix for its PR: builds the PR's base and the branch, runs a reviewed scenario on the Android emulator or iOS simulator, and makes a side-by-side video. Asks before pushing. **Needs** `winteam-device-testing` set up, plus ffmpeg, gh and .NET 10 |

## Install

From your WinTeam-Mobile checkout:

```bash
claude plugin marketplace add groverCG/winteam-claude-plugins   # skip if /plugin already lists "winteam"
claude plugin install winteam-standards@winteam -s local
claude plugin install winteam-device-testing@winteam -s local   # optional; requires winteam-standards
claude plugin install winteam-pr-video@winteam -s local         # optional; requires winteam-device-testing
```

Use `-s local`: the hooks are written for the WinTeam-Mobile layout, and the default `user` scope would turn
them on in every project on your machine.

`winteam-device-testing` needs a one-time setup before it works: the prerequisites and
`/winteam-device-testing:setup-devices` in [its README](plugins/winteam-device-testing/README.md).

## Update

```bash
claude plugin marketplace update winteam
claude plugin update winteam-standards@winteam -s local
claude plugin update winteam-device-testing@winteam -s local   # then run /winteam-device-testing:setup-devices again
claude plugin update winteam-pr-video@winteam -s local
```

## Uninstall

```bash
claude plugin uninstall winteam-pr-video@winteam -s local         # before winteam-device-testing, which it depends on; also deletes its runs
claude plugin uninstall winteam-device-testing@winteam -s local   # first: it depends on winteam-standards; also deletes its Appium install and runs
claude plugin uninstall winteam-standards@winteam -s local
```

## Layout

```
.claude-plugin/marketplace.json   marketplace manifest
plugins/<name>/                   one directory per plugin, each with its own .claude-plugin/plugin.json
```

Changing a plugin? Read its README's *Working on this plugin* section — in short: edit, bump `version` in its
`plugin.json`, run `claude plugin validate .`, push.
