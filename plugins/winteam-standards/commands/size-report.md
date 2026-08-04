---
description: Audit file sizes, method lengths and parameter counts against the winteam-standards caps
allowed-tools: Bash, Read, Grep, Glob, Write
argument-hint: "[paths/dirs to scope to, or --changed; default is repo-wide]"
disable-model-invocation: true
---

Report where the codebase exceeds the size caps, and rank what is worth fixing.

Scope: `$ARGUMENTS`

## Scope

| Argument | Scope |
|---|---|
| *(empty)* | Repo-wide — all three projects |
| `--changed` | Files in the working diff |
| One or more paths | Each token as a file, directory, or glob |

```
/winteam-standards:size-report
/winteam-standards:size-report WinTeam.Mobile.Core/ViewModels/Login/LoginViewModel.cs
/winteam-standards:size-report WinTeam.Mobile.Core/ViewModels WinTeam.Mobile.Core/Managers
/winteam-standards:size-report --changed
```

All three checks honour the scope. Every figure in the report is derived from the run itself — there are no
recorded repo-wide figures to compare against, so the report states its own totals.

**Method length is the only check with a volume problem, and aggregation solves it — not narrowing scope.**
Several hundred individual findings is unreadable; grouped into file rows ranked worst-first, it is a backlog.
Never emit a flat list for that section.

## Gather

Run from the repo root. **Quote `--include="*.cs"`** — zsh expands it otherwise and grep fails with
`no matches found`.

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

Then apply the caps against that list. **The thresholds are not yours to choose** — read them from
[`thresholds.json`](../thresholds.json) at the root of this plugin (`fileCaps`, `maxBodyLines`, `maxParams`,
`lengthCarveOuts`), the same file the edit hook reads, and substitute those values below. The numbers shown
here are the current contents, not an independent copy; if they differ from the file, the file wins. The
`keeping-files-small` and `keeping-core-methods-small` skills own the *rules* — **if a skill and this command
disagree, the skill wins.**

```bash
while read -r f; do
  # awk, not `wc -l`. `wc -l` counts newline characters, so it under-reports by one for a
  # file whose last line has no trailing newline — 395 of 534 Core files. The edit hook
  # counts real lines, so `wc -l` here made the two disagree on the number they print for
  # the same file. It never changed *which* files are findings (no file crosses a cap only
  # under one counter), but a report and an advisory citing different lengths reads as a bug.
  n=$(awk 'END{print NR}' "$f")
  case "$f" in
    WinTeam.Mobile.Core/*)    cap=250 ;;   # fileCaps["WinTeam.Mobile.Core/"]
    WinTeam.Mobile.iOS/*)     cap=350 ;;   # fileCaps["WinTeam.Mobile.iOS/"]
    WinTeam.Mobile.Android/*) cap=450 ;;   # fileCaps["WinTeam.Mobile.Android/"]
    *) continue ;;
  esac
  [ "$n" -ge "$cap" ] && echo "$n $cap $f"
done < "$S/scoped.txt" | sort -rn
```

Method bodies and parameter counts need real parsing, not grep — a signature can span lines and a `(` appears
in plenty of non-signatures. Write a throwaway script to the scratchpad that, for each method in the scoped
list **that lies under `WinTeam.Mobile.Core/`** (method limits are Core-only; a scope naming a platform folder
yields file-size findings and nothing else, and the report should say so rather than appear to have checked):

- counts body lines between the opening and matching closing brace, excluding the brace lines;
- counts parameters by splitting the signature's top-level commas at paren/angle-bracket depth zero, so
  `Dictionary<string, int> x` counts as one;
- skips expression-bodied members, abstract/interface declarations for the *length* check but **keeps them for
  the parameter check** (an 8-parameter interface method propagates to every implementor);
- **counts constructors for the parameter check too, and only that check.** A constructor that merely assigns
  its parameters is exempt from length by the skill's own carve-out, but four-plus collaborators in a
  constructor is the exact case `wiring-dependency-injection` exists to redirect into `[Inject]` properties.
  The edit hook parses these the same way, so the two agree;
- skips `*.Designer.cs`.

**Exclude these from the length check by name** — the `lengthCarveOuts` array in `thresholds.json`, currently
`DoBind`, `RegisterInjections`, `FinishedLaunching`, `BuckleUp`. They are flat declaration lists where length
is the content. Report them in a separate line as
"excluded by carve-out" so the exclusion is visible rather than silent.

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
3. **If the scope contains no `WinTeam.Mobile.Core/` files, say the method and parameter checks did not run.**
   Both are Core-only, so a platform-only scope legitimately produces no such findings — and that must not read
   as "none found".

Then five sections. Give every finding a `path:line` so it is clickable. If a section is empty, say so in one
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
   its count is enough — anyone working a file can re-run scoped to it. Close the
   section with the totals (bodies over 15, over 20, over 30 lines) and the carve-out exclusions listed
   separately, so the exclusion is visible rather than silent.
4. **Interface declarations over 3 parameters**, called out separately from concrete methods — each one commits
   every implementor, so it is worth more than a single finding.
5. **Next actions — at most five, each one directly actionable, and name how many candidates they were ranked
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

## Rules

- **Report only. Change no C# files.** Splitting a file or reshaping a signature is a judgment call that needs
  the feature's context, and the fixes are reviewed one at a time — see the handoff note below.
- **`Write` is granted for the scratchpad parser and nothing else.** The method and parameter checks need real
  parsing rather than grep, so this command writes a throwaway script — which is why it holds `Write` while the
  other two audits do not. It is not a licence to edit a repo file: the rule above still binds, and every
  finding is a report.
- **Expect one approval prompt to run that script, and do not try to remove it.** No interpreter is in
  `permissions.allow`, deliberately — `Bash(python3:*)` would allow `python3 -c "<anything>"`, which is the same
  objection that keeps `xargs` off that list, only stronger. One prompt for the parser is the correct price.
- **Never emit a flat list of every over-cap method.** Group by file. A report nobody reads enforces nothing.
- Distinguish **pre-existing** from **newly introduced**. Only the latter belongs to whoever is working now, and
  conflating them makes the report feel like blame for someone else's code.
- Never recommend splitting a file whose length is a flat list of one-line members. Say why it is exempt.

## How findings get fixed

This command does not fix anything, and neither does a flag on it. The path is:

1. Run this command, pick **one** target from *Next actions*.
2. Ask for it in plain language. The relevant skill fires automatically on any `WinTeam.Mobile.Core` edit, so
   there is nothing to invoke by hand.
3. The advisory hook re-checks the file on write.
4. For anything non-trivial, run `senior-reviewer` on the diff afterwards.

**One target per change.** The failures this codebase produces are silent — a moved bound property or broken
activation wiring compiles cleanly and fails on device — so a review covering a dozen fixes at once is how one
slips through. Resist batching even when the list is long.
