---
description: Audit manual SetProperty, RelayCommand and notification-chain declarations in Core and rank them for migration
allowed-tools: Bash, Read, Grep, Glob
argument-hint: "[paths/dirs to scope to, or --changed; default is all of WinTeam.Mobile.Core]"
disable-model-invocation: true
---

Find hand-written MVVM boilerplate worth migrating to the CommunityToolkit source generators, and rank it by
payoff rather than by count.

Scope: `$ARGUMENTS`

This is the backward-looking counterpart to `declaring-properties-and-commands`, which governs *new* members.
That one fires automatically as you write; this one is a sweep you ask for, because **migrating a bound member
changes a name the platform views depend on** — that belongs in a session where it is the work, not fired while
you are trying to ship something else.

| Argument | Scope |
|---|---|
| *(empty)* | All of `WinTeam.Mobile.Core/` |
| `--changed` | Files in the working diff |
| One or more paths | Each token as a file, directory, or glob |

```
/winteam-standards:mvvm-audit
/winteam-standards:mvvm-audit --changed
/winteam-standards:mvvm-audit WinTeam.Mobile.Core/ViewModels/Kiosk
/winteam-standards:mvvm-audit WinTeam.Mobile.Core/ViewModels/Login/LoginViewModel.cs
```

The codebase is mid-transition and **manual is still the majority** on both properties and commands, so this is
a real backlog rather than a few stragglers. Every figure in the report is derived from the run itself —
there is no recorded split to compare against, so the report must state its own totals.

## Gather

**Resolve the scope to a concrete file list first, and count it** — the report opens with that count.

```bash
S=$(mktemp -d); ARGS="$ARGUMENTS"

if [ -z "$ARGS" ]; then
  find WinTeam.Mobile.Core -name "*.cs" \
    -not -path "*/obj/*" -not -path "*/bin/*" > "$S/files.txt"
elif [ "$ARGS" = "--changed" ]; then
  # Tracked modifications *and* untracked new files — `git diff HEAD` alone omits the
  # latter, so a newly added ViewModel escaped the audit entirely.
  { git diff HEAD --name-only -- "*.cs"
    git ls-files --others --exclude-standard -- "*.cs"; } \
    | sort -u | grep -vE "/obj/|/bin/" | grep "^WinTeam.Mobile.Core/" > "$S/files.txt"
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

# Generated files are never findings — exclude before counting.
grep -vE "\.[Dd]esigner\.cs$" "$S/files.txt" > "$S/scoped.txt"
wc -l < "$S/scoped.txt"   # <-- the number the report must state
```

**If `scoped.txt` is empty, stop and report it as an error.** Do not continue and emit a clean-looking report.

Then sweep that exact list. Searching the resolved files rather than directories means every pattern shares one
scope and no `--include` filter is needed:

```bash
# -H keeps filenames when xargs splits the list across several grep invocations.
X() { xargs grep -nH "$@" < "$S/scoped.txt" ; }

X -e "SetProperty(ref"                                  > "$S/manual_props.txt"
X -e "new RelayCommand" -e "new AsyncRelayCommand"      > "$S/manual_cmds.txt"
X -e "OnPropertyChanged(nameof"                         > "$S/chains.txt"
X -e "NotifyCanExecuteChanged()"                        > "$S/canexec.txt"
# -F is load-bearing: an attribute name is wrapped in brackets, and without -F `[...]` is a
# regex character class matching any file containing any one of those letters. Measured
# without it: 400 of 400 Core files "matched" against 17 with it, so every manual-SetProperty
# file then read as a mixed class and the top-priority band became the whole codebase.
# No closing bracket, because both attributes take an optional argument —
# `[RelayCommand(CanExecute = nameof(X))]` must count, and today one file has only that form.
X -lF -e "[ObservableProperty" -e "[RelayCommand"       > "$S/generator_based.txt"
echo "$S"
```

Mixed classes — the top priority band — are the intersection of the last file with the first:

```bash
comm -12 <(cut -d: -f1 "$S/manual_props.txt" | sort -u) <(sort -u "$S/generator_based.txt")
```

For each candidate type, establish three things before recommending anything:

1. **Is the class `partial`?** If not, that is part of the migration, and it is a trivial edit.
2. **Does a view bind the member?** Grep both platform projects for the member name. A bound member's migration
   is a coordinated change; an unbound one is safe and local.
3. **Does the setter do more than `SetProperty`?** Side effects move to the generated `OnXChanged` partial hook,
   which is a genuine behaviour-equivalence question, not a mechanical rename.

## Rank findings by payoff, not by count

In order of value:

1. **Mixed classes** — a type already using `[ObservableProperty]` *and* hand-written `SetProperty`. Highest
   priority: the inconsistency actively misleads readers about which style the class uses.
2. **Hand-written notification chains** — a `SetProperty` followed by `OnPropertyChanged(nameof(Other))`. The
   `[NotifyPropertyChangedFor]` attribute is compile-time checked against a real member; the string in the
   manual call is not, so every one of these is a latent silently-broken binding.
3. **Manual `NotifyCanExecuteChanged()` calls** — replaceable with `[NotifyCanExecuteChangedFor]`, same
   argument.
4. **Unbound properties and commands** — safe, local, low risk, low reward.
5. **Bound commands** — lowest priority despite being the largest group. Renaming one touches the platform
   views and the payoff is only boilerplate reduction.

## Migration target shapes

Bands 2 and 3 are migrations in their own right, not footnotes on a property migration — **report them as
first-class targets with the destination named.** Both are already gathered above, into `chains.txt` and
`canexec.txt`.

| Manual form | Migrates to |
|---|---|
| `SetProperty(...)` then `OnPropertyChanged(nameof(Other))` | `[NotifyPropertyChangedFor(nameof(Other))]` |
| `SomeCommand.NotifyCanExecuteChanged()` | `[NotifyCanExecuteChangedFor(nameof(SomeCommand))]` |

**Cite the in-repo precedent rather than describing a shape.** `ViewModels/Kiosk/KioskWorkerLoginViewModel.cs:28-31`
stacks both attributes on one `[ObservableProperty]` and is the exact target — note the notified member at `:33`
is a computed expression-bodied property, which is the case these attributes exist for:

```csharp
[ObservableProperty]
[NotifyPropertyChangedFor(nameof(IsWorkerIdInputEmpty))]
[NotifyCanExecuteChangedFor(nameof(ConfirmCommand))]
private string _workerIdInput = "";
```

Also `ViewModels/ProfileInfo/ProfileInfoViewModel.cs:92-95`, which stacks two `NotifyPropertyChangedFor` on one
property, and `ViewModels/Biometrics/BiometricsConsentViewModel.cs:83,87`. Those are the only files in the repo
using either attribute, so they are the whole precedent — say so when recommending one.

**Both attributes require the source to already be an `[ObservableProperty]`.** A manual `SetProperty` member
with a notification chain is therefore a *two-part* migration: the property first, then the chain. Report it as
one target with both parts named, never as two independent findings — half of it applied is a property that no
longer notifies what it used to.

The two constraints below still bind here, and they bite harder on these bands than on a plain property, because
a notification chain only exists where something else depends on the value:

- A setter doing more than `SetProperty` is not mechanical — the side effect moves to the generated `OnXChanged`
  hook, which runs *after* assignment and notification.
- Never recommend renaming a member to fit the generator.

## Report

**Open with the resolved scope and the file count actually examined**, before any findings:

```
Scope: WinTeam.Mobile.Core/ViewModels/Kiosk (14 .cs files examined)
```

Two scope rules, both there to stop the report lying about being clean:

1. **Zero files matched → report it as an error and stop.** Name the argument that matched nothing and suggest a
   correction. An empty report is indistinguishable from a clean one, and a mistyped path causes both.
2. **When scoped, say so and name the scope in the report itself.** Every figure below it is then a figure
   *for those files only*. A scoped total read as a whole-project one is how a partial sweep gets mistaken for
   a clean bill of health.

Then a table: type, member, current style, what it would become, risk (bound / unbound / has side effects), and
priority band. Give every finding a `path:line` so it is clickable. If a band is empty, say so in one line — an
omitted band reads as unchecked.

**Every band states how many it found alongside how many it shows** — `31 found — showing 8`. The caps below are
there to keep the report readable, not to make it look shorter than the work is: a band that found 31 and
displayed 8 must not read like a band that found 8. Close the table with the run's own totals per style, so the
scale is visible without reading every row.

Close with a recommended first batch of **no more than three types** — naming how many candidates it was chosen
from — each with the reason it ranks there and the literal request to make:

```
1. KioskProfileViewModel — mixed: 2 [ObservableProperty] alongside 3 manual SetProperty
   → ask: "migrate KioskProfileViewModel's manual SetProperty members to [ObservableProperty]"
     (declaring-properties-and-commands fires automatically on the edit)

2. SomeViewModel.SelectedJob — SetProperty + 2 OnPropertyChanged(nameof) chains, both to computed properties
   → ask: "migrate SelectedJob to [ObservableProperty] with [NotifyPropertyChangedFor] for its two chains"
     (two-part: property then chain — see KioskWorkerLoginViewModel.cs:28-31 for the target shape)
```

Say plainly what the audit cannot tell you: **whether a binding still resolves is not visible at build time.**

## Rules

- **Report only. Change no C# files.** Enforced by `allowed-tools`, not just stated: this command has no `Write`
  or `Edit`. Migration is a separate, reviewed change — see the handoff below.
- **One type per change.** A batch conversion across files cannot be reviewed meaningfully, and a broken binding
  will not surface until someone opens that screen.
- **Never recommend renaming a member to fit the generator.** The generated name must match what views already
  bind: backing field `_displayName` produces `DisplayName`, method `SubmitAsync` produces `SubmitCommand`. If
  the existing public name does not match what the generator would produce, **recommend leaving it manual** —
  renaming the binding is a bigger change than the boilerplate saves.
- **Flag setter side effects rather than waving them through.** They move to the `OnXChanged` hook, which runs
  *after* the value is assigned and the notification fires — whereas hand-written code before a `SetProperty`
  call ran before both. If the side effect depended on running first, the migration is not mechanical.
- **Note the two `IRelayCommand` types.** CommunityToolkit and MobileCore both define one, both extending
  `ICommand`. Bindings accept either, but the names collide, so a converted file may need a `using` alias. See
  `declaring-properties-and-commands`.
- Never report a finding in platform view code, entities, DTOs, records or messages — none of them bind.

## How findings get fixed

This command does not fix anything. The path is:

1. Run it, pick **one** type from the recommended batch.
2. Ask for it in plain language. `declaring-properties-and-commands` fires automatically on the edit and carries
   the target shape.
3. Build Core **and both platform csprojs** — a generated member name that no longer matches what a view binds
   only fails in the platform projects.
4. **Open the screen.** A binding to a missing member compiles cleanly and fails silently at runtime. That is
   the entire risk of this work, so a clean build is not evidence of success.

**One type per change**, even when the list is long. The failure here is silent, so a review covering a dozen
migrations at once is how one slips through.
