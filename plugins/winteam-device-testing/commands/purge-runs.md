---
description: Delete saved capture runs (screenshots and page sources hold test-account data)
allowed-tools: Bash
argument-hint: "[--older-than <days>]"
disable-model-invocation: true
---

Delete the capture runs this plugin keeps under `${CLAUDE_PLUGIN_DATA}/runs`. Expired runs, older than
`retentionDays` in `data/app.json`, are already pruned at every session start and every capture. This command
is for deleting them now.

Scope: `$ARGUMENTS`

- **Empty:** delete every run.
- **`--older-than <days>`:** delete only the runs older than that.

Run exactly one of these:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/prune_runs.py" --runs "${CLAUDE_PLUGIN_DATA}/runs" --all
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/prune_runs.py" --runs "${CLAUDE_PLUGIN_DATA}/runs" --older-than <days>
```

Report the count it prints. Never list, open or copy the runs before deleting them, and delete nothing outside
that folder.

Screenshots that were shown in a conversation also stay in Claude Code's local session history, which
`cleanupPeriodDays` prunes. This command doesn't reach them.
