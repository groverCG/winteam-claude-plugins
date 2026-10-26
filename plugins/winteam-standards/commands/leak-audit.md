---
description: Audit event handler, messenger, bus, timer and platform observer teardown across the app
allowed-tools: Bash, Read, Grep, Glob, Skill
argument-hint: "[paths/dirs to scope to, or --changed; default is all three projects]"
disable-model-invocation: true
---

Find subscriptions that are never undone. Nothing in this repo checks this — subscriptions resolve at runtime,
so every defect here compiles cleanly and shows up as a duplicated dialog, a double submission, or a timer that
speeds up on every revisit.

Scope: `$ARGUMENTS`

| Argument | Scope |
|---|---|
| *(empty)* | All three projects |
| `--changed` | Files in the working diff |
| One or more paths | Each token as a file, directory, or glob |

```
/winteam-standards:leak-audit
/winteam-standards:leak-audit WinTeam.Mobile.Core/ViewModels/Kiosk
/winteam-standards:leak-audit WinTeam.Mobile.Core/ViewModels WinTeam.Mobile.iOS/Views
/winteam-standards:leak-audit --changed
```

## Read this before judging anything

**`tearing-down-subscriptions` owns the rules. Invoke it now, and judge every finding against it** — it ships
in this same plugin, so it is always available to this command. Do not work from a second copy of the rules;
there isn't one here on purpose.

The two facts that decide most calls, so you have them before the sweep:

- **ViewModels in this app are not reliably disposed** — a process-lifetime store holds them across Android
  fragment recreation, so `Dispose` does not run on navigation. **"It's unsubscribed in `Dispose`" is therefore
  not sufficient evidence of safety.** Getting this wrong in either direction ruins the report: miss it and you
  clear real leaks, over-apply it and you flag correct code.
- **`IRecipient<T>` on an `ObservableRecipient` is the safe path** — register/unregister are automatic as
  `IsActive` flips. Never report those.

Everything else — the eight rules, the ordered timer teardown, the sanctioned escape hatch — comes from the
skill. **If the skill and this command disagree, the skill wins.**

## Gather

Two shell traps here, both of which silently corrupt counts rather than erroring:

- **A pattern starting with `-` needs `-e`.** `grep "-="` is parsed as options. Use `grep -e "-="`. Do **not**
  reach for the `--` end-of-options marker together with `--include`: `--` stops option parsing, so a following
  `--include="*.cs"` becomes a *filename* and every file type gets searched — that inflated the iOS `-=` count
  from 27 to 55 and looked exactly like real drift. Searching an explicit file list, as below, avoids the whole
  class of problem.
- **If you do fall back to `-r` over directories, quote `--include="*.cs"`** — zsh expands it otherwise and grep
  fails with `no matches found`.

**Resolve the scope to a concrete file list first, and count it** — the report opens with that count.

```bash
S=$(mktemp -d); ARGS="$ARGUMENTS"

if [ -z "$ARGS" ]; then
  find WinTeam.Mobile.Core WinTeam.Mobile.iOS WinTeam.Mobile.Android -name "*.cs" \
    -not -path "*/obj/*" -not -path "*/bin/*" > "$S/files.txt"
elif [ "$ARGS" = "--changed" ]; then
  # Tracked modifications *and* untracked new files. `git diff HEAD` alone omits the
  # latter, and a new ViewModel or view is where an unpaired subscription is most likely
  # to be introduced — so omitting it made `--changed` report clean on the worst input.
  { git diff HEAD --name-only -- "*.cs"
    git ls-files --others --exclude-standard -- "*.cs"; } \
    | sort -u | grep -vE "/obj/|/bin/" > "$S/files.txt"
else
  # Split via tr, not `for t in $ARGS`. This shell is zsh, where unquoted parameter
  # expansion does NOT word-split — that form silently resolves a multi-path scope
  # to zero files.
  echo "$ARGS" | tr ' ' '\n' | while read -r t; do
    [ -z "$t" ] && continue
    if   [ -f "$t" ]; then echo "$t"
    elif [ -d "$t" ]; then find "$t" -name "*.cs" -not -path "*/obj/*" -not -path "*/bin/*"
    else ls -1 $t 2>/dev/null | grep "\.cs$"
    fi
  done | sort -u > "$S/files.txt"
fi
wc -l < "$S/files.txt"   # <-- the number the report must state
```

**If that count is zero, stop and report it as an error.** Do not emit a clean-looking report.

Then sweep that exact list. Searching the resolved files rather than directories means every pattern shares one
scope, and no `--include` filter is needed:

```bash
# Search only the scoped files. Feed the list on stdin — `xargs -a FILE` is a GNU
# extension that BSD xargs on macOS rejects with "invalid option -- a".
# -H keeps filenames when xargs splits the list across several grep invocations.
X() { xargs grep -nH "$@" < "$S/files.txt" ; }

# Lambda subscriptions — unremovable by construction, the highest-value finding
X -E "\+=\s*(async\s*)?(\(|[A-Za-z_]+\s*=>)" > "$S/lambdas.txt"

# Handler pairing
X -e "+=" > "$S/add.txt"
X -e "-=" > "$S/remove.txt"

# Messenger and bus
X -e "WeakReferenceMessenger.Default.Register" -e "StrongReferenceMessenger.Default.Register" > "$S/register.txt"
X -e "Unregister" > "$S/unregister.txt"
X -e "BusManager.Subscribe" > "$S/bus_sub.txt"
X -e "BusManager.Unsubscribe" -e "UnsubscribeAll" > "$S/bus_unsub.txt"

# Timers, platform observers, retain cycles, statics
X -e "new Timer" -e ".Elapsed +=" > "$S/timers.txt"
X -e "AddObserver" -e "RemoveObserver" -e "Delegate = this" > "$S/ios.txt"
X -E "static\s+[A-Za-z_]*(Activity|Fragment|ViewModel|Controller|View)\b" > "$S/statics.txt"
echo "$S"
```

**Pair per handler name, not by count.** Two `+=` and two `-=` in one file can still be wrong if they are for
different events. For each `+=`, extract the handler identifier and grep for a `-=` on that same identifier.

Then read the **whole** file for every candidate. The unsubscribe half is usually outside any diff hunk and
often in a differently named method, so a hunk-level judgment produces false positives.

## Report

**Open with the resolved scope and the file count actually examined**, before any findings:

```
Scope: WinTeam.Mobile.Core/ViewModels/Kiosk (14 .cs files examined)
```

Two scope rules, both there to stop the report lying about being clean:

1. **Zero files matched → report it as an error and stop.** Name the argument that matched nothing and suggest a
   correction. An empty report is indistinguishable from a clean one, and a mistyped path causes both.
2. **When scoped, say so and name the scope in the report itself.** Every figure below it is then a figure
   *for those files only*. A scoped total read as a whole-repo one is how a partial sweep gets mistaken for a
   clean bill of health.

Then seven sections, each finding with `path:line`. Say "none" explicitly for an empty section, and **state
how many each section found alongside how many it shows** — `14 found — showing 6`. Grouping and ranking exist
to keep the report readable, not to make the backlog look smaller than it is: a section that found 14 and
displayed 6 must not read like a section that found 6.

1. **Lambda subscriptions.** Always a defect — no reference exists to remove. Group by file.
2. **Unpaired handlers**, matched per handler name.
3. **Subscriptions in constructors.** No matching "unconstruct", so the pairing cannot exist. Flag separately
   from unpaired handlers; the fix is different — move it to the activate/deactivate pair.
4. **Messenger asymmetry.** Manual `Register` with no matching `Unregister`. Note `StrongReferenceMessenger`
   uses separately: those hold recipients alive, so a missing `UnregisterAll` is more severe.
5. **Timers** missing any of `Elapsed -=`, `Stop()`, `Dispose()`.
6. **Platform-specific.** iOS: `AddObserver` tokens not stored/removed, `Delegate = this` where `WeakDelegate`
   exists. Android: statics holding an activity, fragment, or ViewModel.
7. **Next actions — at most five, each directly actionable, and name how many candidates they were ranked
   from.** Rank by lifetime impact: process-lifetime holds first, then per-navigation accumulation, then latent
   asymmetries that are correct today only by coincidence of lifetimes.

   For each: the target, what stays alive, and the literal request to make. `tearing-down-subscriptions` fires
   automatically on the edit, so naming the target is the whole handoff:

   ```
   1. KioskTimeoutConfirmationViewModel — timer Elapsed += with no -= and no Dispose
      → ask: "add paired teardown for the timer in KioskTimeoutConfirmationViewModel"
        (its two sibling kiosk VMs already do this correctly — copy that shape)

   2. JobPromptModalSheet — 5 lambda subscriptions, unremovable
      → ask: "convert the lambda handlers in JobPromptModalSheet to named methods with paired -="
   ```

For every finding, state **what stays alive** and **the symptom a user would see**. "Missing `-=`" alone is not
actionable; "the confirmation dialog appears twice after visiting the screen twice" is.

## Rules

- **Report only. Change no C# files.** Removing a subscription can change behaviour; each fix needs its own
  review.
- Never report `IRecipient<T>` registrations, or bus subscriptions on a type that genuinely gets disposed.
- Say what you checked and found clean. A silent section reads as unchecked.
- Close with the runtime check, because none of this is visible at build time: navigate away and back **three
  times**, then confirm the handler fires once rather than three times.

## How findings get fixed

This command does not fix anything. The path is:

1. Run it, pick **one** target from *Next actions*.
2. Ask for it in plain language — `tearing-down-subscriptions` fires automatically on the edit.
3. The advisory hook re-checks pairing on write.
4. Run `winteam-standards:memory-leak-hunter` on the diff afterwards to confirm the fix, since it applies the same rules with the
   ViewModel-store caveat in mind.

**One target per change, and never bulk-convert lambda subscriptions.** Converting a lambda to a named handler
changes *when* the handler can be removed, which is a behaviour change — the whole point — so each one needs the
navigate-three-times check on device. A batch of twelve gets one careless check instead of twelve real ones.
