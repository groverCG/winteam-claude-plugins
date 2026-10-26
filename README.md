# winteam-claude-plugins

Claude Code plugin marketplace (`winteam`) for the WinTeam mobile app.

| Plugin | What it does |
|---|---|
| [`winteam-standards`](plugins/winteam-standards/README.md) | Code standards (size caps, layering, DI, MVVM, teardown, theming, `AppStrings`) as skills, advisory hooks and audit commands, a `scale-for-tablets` fixer, plus four report-only review agents |

## Install

From your WinTeam-Mobile checkout:

```bash
claude plugin marketplace add groverCG/winteam-claude-plugins   # skip if /plugin already lists "winteam"
claude plugin install winteam-standards@winteam -s local
```

Use `-s local`: the hooks are written for the WinTeam-Mobile layout, and the default `user` scope would turn
them on in every project on your machine.

## Update

```bash
claude plugin marketplace update winteam
claude plugin update winteam-standards@winteam -s local
```

## Uninstall

```bash
claude plugin uninstall winteam-standards@winteam -s local
```

## Layout

```
.claude-plugin/marketplace.json   marketplace manifest
plugins/<name>/                   one directory per plugin, each with its own .claude-plugin/plugin.json
```

Changing a plugin? Read its README's *Working on this plugin* section — in short: edit, bump `version` in its
`plugin.json`, run `claude plugin validate .`, push.
