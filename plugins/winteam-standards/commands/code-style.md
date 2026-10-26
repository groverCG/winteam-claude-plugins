---
description: Audit file sizes, method lengths, parameter counts and documentation comments against the winteam-standards rules
allowed-tools: Bash, Read, Grep, Glob
argument-hint: "[paths/dirs to scope to, or --changed; default is repo-wide]"
disable-model-invocation: true
---

Report where the codebase breaks the code-style rules, and rank what is worth fixing.

Scope: `$ARGUMENTS`

## Scope

| Argument | Scope |
|---|---|
| *(empty)* | Repo-wide — all three projects |
| `--changed` | Files in the working diff |
| One or more paths | Each token as a file, directory, or glob |

```
/winteam-standards:code-style
/winteam-standards:code-style WinTeam.Mobile.Core/ViewModels/Login/LoginViewModel.cs
/winteam-standards:code-style WinTeam.Mobile.Core/ViewModels WinTeam.Mobile.Core/Managers
/winteam-standards:code-style --changed
```

Every axis honours the scope. Every figure in the report is derived from the run itself — there are no recorded
repo-wide figures to compare against, so the report states its own totals.

**Four axes have a volume problem, and aggregation solves it — not narrowing scope.** Method length,
documentation comments and in-body comments each run into the hundreds repo-wide, and member order into the
low hundreds. Several hundred individual findings is unreadable; grouped into file rows ranked worst-first, it
is a backlog. Never emit a flat list for those four.

## Gather

Run from the repo root. **Quote `--include="*.cs"`** if you add a grep — zsh expands it otherwise and grep
fails with `no matches found`.

**Resolve the scope to a concrete file list first, and count it.** Everything downstream reads that list, and
the count is what the report opens with.

```bash
S=$(mktemp -d); ARGS="$ARGUMENTS"

if [ -z "$ARGS" ]; then
  find WinTeam.Mobile.Core WinTeam.Mobile.iOS WinTeam.Mobile.Android -name "*.cs" \
    -not -path "*/obj/*" -not -path "*/bin/*" > "$S/files.txt"
elif [ "$ARGS" = "--changed" ]; then
  # Tracked modifications *and* untracked new files. `git diff HEAD` alone omits the
  # latter, and a brand-new file is the most likely thing in a change to be over cap —
  # so omitting it made `--changed` quietly clean on exactly the wrong input. The edit
  # hook already treats an untracked file as wholly changed; this keeps the two agreeing.
  { git diff HEAD --name-only -- "*.cs"
    git ls-files --others --exclude-standard -- "*.cs"; } \
    | sort -u | grep -vE "/obj/|/bin/" > "$S/files.txt"
else
  # Each token may be a file, a directory, or a glob.
  # NOTE: split via tr, not `for t in $ARGS`. This shell is zsh, where unquoted
  # parameter expansion does NOT word-split — that form silently iterates once
  # over the whole string and resolves to zero files for any multi-path scope.
  echo "$ARGS" | tr ' ' '\n' | while read -r t; do
    [ -z "$t" ] && continue
    if   [ -f "$t" ]; then echo "$t"
    elif [ -d "$t" ]; then find "$t" -name "*.cs" -not -path "*/obj/*" -not -path "*/bin/*"
    else ls -1 $t 2>/dev/null | grep "\.cs$"
    fi
  done | sort -u > "$S/files.txt"
fi

# Generated files are never findings — exclude before counting.
grep -vE "\.[Dd]esigner\.cs$" "$S/files.txt" > "$S/scoped.txt"
wc -l < "$S/scoped.txt"   # <-- the number the report must state
```

**If `scoped.txt` is empty, stop and report it as an error** — see the Report rules. Do not continue and emit a
clean-looking report.

Then run every check the hooks run, over that list:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scan_standards.py" \
  < "$S/scoped.txt" > "$S/findings.tsv" 2> "$S/errors.txt"

cut -f1 "$S/findings.tsv" | sort | uniq -c | sort -rn   # per-axis totals
cut -f1,2 "$S/findings.tsv" | sort | uniq -c | sort -rn | head -40   # worst files per axis
```

`findings.tsv` is `axis <TAB> path <TAB> line <TAB> text`. The axes are `file-size`, `parameters`,
`method-length`, `doc-comment`, `comment`, `member-order`, `teardown`, `entity-pair`, `presentation` and
`other`.

Four things to know about that script, all of which have bitten a previous version of this command:

- **It is the same code the hooks run**, importing `check_cs_edit.py`, `check_presentation_edit.py`,
  `check_comments.py` and `check_member_order.py`. This command no longer re-derives the caps in `awk`, and no longer writes a throwaway
  parser to the scratchpad. Two counters for one rule disagree eventually; one cannot.
- **The thresholds are not yours to choose.** The script reads them from
  [`thresholds.json`](../thresholds.json) — `fileCaps`, `maxBodyLines`, `maxParams`, `lengthCarveOuts`,
  `requireDocComments`, `commentCarveOutPrefixes`, `requireMemberOrder`. If a value here disagreed with that file, the file wins.
  The skills own the *rules*: **if a skill and this command disagree, the skill wins.**
- **It runs in `report_all` mode**, so it reports every violation present rather than only the ones the working
  diff introduced. That is the opposite of the hooks' gate, and it is why a repo-wide run is not silent on a
  clean tree.
- **Read `$S/errors.txt` and report anything in it.** A file the parser choked on is a gap in the scan, and a
  scan with a silent gap reads as a clean bill of health.

**Method, parameter and comment findings are `WinTeam.Mobile.Core`-only** by the rules' own scope, so a scope
naming only a platform folder yields file-size, presentation and member-order findings and nothing else. The
report must say so rather than appear to have checked. `member-order` is the one C# axis that does cover all
three projects — ordering has no platform dimension.

## Report

**Open with the resolved scope and the file count actually examined**, before any findings:

```
Scope: WinTeam.Mobile.Core/ViewModels (312 .cs files examined)
```

Three rules about scope, all of which exist to stop the report lying about being clean:

1. **Zero files matched → report it as an error and stop.** Name the argument that matched nothing and suggest
   the likely correction. An empty report is indistinguishable from a clean one, and a mistyped path is the most
   likely cause of both.
2. **When scoped, say so and name the scope in the report itself.** Every figure below it is then a figure
   *for those files only*. A scoped total read as a whole-repo one is how a partial sweep gets mistaken for a
   clean bill of health.
3. **If the scope contains no `WinTeam.Mobile.Core/` files, say the Core-only axes did not run.**

Then eight sections. Give every finding a `path:line` so it is clickable. If a section is empty, say so in one
line — an omitted section reads as unchecked.

**Every section states how many it found alongside how many it shows** — `31 found — showing top 5`. The caps
below exist to keep the report readable, not to make the backlog look smaller than it is: a section that found
31 and displayed 5 must not read like a section that found 5.

1. **Files over cap**, worst first, with the cap each is measured against. For each of the top few, name the
   responsibility that could come out — not just the number. A list of line counts is not actionable.
2. **Parameter violations in Core**, worst first, grouped by whether the extra parameters are **collaborators**
   (fix: `[Inject]` properties) or **data** (fix: a record). That classification is the useful part; the count
   is not. Label each finding as a method, a **constructor**, or an **interface declaration** — the fix differs
   per kind, and the two worst offenders in the repo are constructors.
3. **Method lengths — grouped by file, never a flat list.** One row per file, worst first:

   ```
   TimeClockViewModel.cs        12 over cap   worst: HandleResponseAsync :574 (48 lines)
   WTPunchFlowPersistentClient  9 over cap    worst: FlushMessagesAsync :79 (101 lines)
   ```

   Then expand **only the top 5 files** into individual methods with `path:line`. Below that, the file row plus
   its count is enough — anyone working a file can re-run scoped to it. Close the section with the totals
   (bodies over 15, over 20, over 30 lines) and the `lengthCarveOuts` exclusions listed separately, so the
   exclusion is visible rather than silent.
4. **Interface declarations over 3 parameters**, called out separately from concrete methods — each one commits
   every implementor, so it is worth more than a single finding.
5. **Missing and incomplete `///` blocks — grouped by file, never a flat list.** This is the largest axis in the
   repo by a wide margin and the one most likely to swamp everything else. One row per file with a count, worst
   first, top 10 files only, and **state the repo-wide total explicitly** so the row list cannot be mistaken for
   the whole of it. Split "no block at all" from "block present but incomplete": the second is a smaller, much
   cheaper fix and belongs at the top of anyone's list.
6. **In-body comments — grouped by file, and split by fix.** Two different findings live on this axis and they
   are not equally interesting: **commented-out code** is dead weight that just gets deleted, and it goes first
   because it is unambiguous. **Narrating comments** are a signal that a name is wrong or a block wants
   extracting, so treat each one as a candidate extraction rather than a candidate deletion, and never
   recommend deleting a comment without saying what should replace it.
7. **Member order — grouped by file, and by which of the two axes each finding is on.** State declared below
   behaviour comes first; a single-caller helper above its caller second. Two things to say every time. This
   axis is **advisory-only and never reaches the `Stop` hook**, deliberately, so nothing here is blocking
   anything. And a fix here is a **move**, which means the risk is the diff: recommend a reorder only where it
   is a handful of members, say so plainly when a file would need twenty moved, and never recommend one as part
   of a split or an extraction — `keeping-files-small` forbids reordering there and wins. `Entities/` files
   dominate this axis by count and are the least worth touching; say that rather than ranking them.

   The third half of the rule — a caller's helpers as one contiguous block — is **not checked** and will not
   appear in `findings.tsv`. If it matters for a file under discussion, read it by eye against
   `ordering-class-members` and say you did.
8. **Next actions — at most five, each one directly actionable, and name how many candidates they were ranked
   from.** This is the section that makes the report usable, so do not skip or pad it.

   For each: the target, why it ranks here, and the literal request to make. Nothing in this plugin fixes code,
   but the skills fire automatically on a `WinTeam.Mobile.Core` edit, so naming the target is the whole handoff:

   ```
   1. PunchPhotoPolicy.IsPunchPhotoNeeded — 6 params, all collaborators
      → ask: "convert IsPunchPhotoNeeded's collaborators to [Inject] properties"
        (keeping-core-methods-small + wiring-dependency-injection will fire)

   2. LoadTimeClockDataUseCase.ExecuteAsync — 6 params, mixed
      → ask: "collapse ExecuteAsync's parameters into a context record"
        (also an Iteration 2 candidate — see /timeclock-refactor:next-extraction)
   ```

   Rank by **payoff over risk**, not by magnitude. Prefer a target with no bound members and no kiosk override
   over the largest one. Explicitly flag any target that touches a property the platform views bind, because
   that needs `timeclock-refactor:moving-bound-properties` and is not a quick win.

   **Do not put "add the missing `///` blocks" here as a bulk item.** 929 of them exist; as one line it is not
   an action, it is a wish. If a documentation target earns a slot, name a single file.

## Rules

- **Report only. Change no C# files.** Splitting a file or reshaping a signature is a judgment call that needs
  the feature's context, and the fixes are reviewed one at a time — see the handoff note below.
- **This command holds no `Write`, deliberately.** The previous version did, solely to write a parser to the
  scratchpad; `scan_standards.py` is committed, so there is nothing left to write and the grant was dropped
  rather than left lying around.
- **Never emit a flat list for the method-length, `///`, comment or member-order axes.** Group by file. A report nobody reads
  enforces nothing.
- Distinguish **pre-existing** from **newly introduced**. Only the latter belongs to whoever is working now, and
  conflating them makes the report feel like blame for someone else's code. `--changed` is the scope that
  answers this directly; on a repo-wide run, say plainly that most of it predates the reader.
- Never recommend splitting a file whose length is a flat list of one-line members. Say why it is exempt.
- **The `///` and comment axes are 96%-and-rising pre-existing.** 929 documentation findings and 251 comment
  findings exist across Core. Treat the repo-wide figures as a backlog to draw from, never as a defect list to
  work through, and never as something the reader introduced.

## How findings get fixed

This command does not fix anything, and neither does a flag on it. The path is:

1. Run this command, pick **one** target from *Next actions*.
2. Ask for it in plain language. The relevant skill fires automatically on any `WinTeam.Mobile.Core` edit, so
   there is nothing to invoke by hand.
3. The advisory hooks re-check the file on write, and `enforce_session_standards.py` re-checks it at the end of
   the turn.
4. For anything non-trivial, run `winteam-standards:senior-reviewer` on the diff afterwards.

**One target per change.** The failures this codebase produces are silent — a moved bound property or broken
activation wiring compiles cleanly and fails on device — so a review covering a dozen fixes at once is how one
slips through. Resist batching even when the list is long.
