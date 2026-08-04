---
description: Audit WeakReferenceMessenger message wiring in WinTeam.Mobile.Core and diff it against the architecture docs
allowed-tools: Bash, Read, Grep, Glob
argument-hint: "[feature folder under Messages/, defaults to TimeLanding]"
disable-model-invocation: true
---

Audit the messenger wiring that the compiler cannot check, and report drift against
`docs/architecture/timeclock/messages.md`.

Feature folder to audit: `$1` (default `TimeLanding` if empty).

## Why this exists

Messages are resolved by type at runtime. A message with no responder, two responders on the same
`RequestMessage`, or a recipient that never registers all compile cleanly and fail on device. There is no
test project over `WinTeam.Mobile.Core`, so this command is the only automated check.

## Gather

Run these from the repo root. **Quote `--include="*.cs"`** — zsh expands it otherwise and grep fails with
`no matches found`.

Substitute the folder name into `F` literally before running the block — `$1` above, or `TimeLanding` if it
was empty. `$1` is textually replaced in this file before any shell runs, so `${1:-TimeLanding}` would leave
a broken assignment and the audit would silently find nothing.

```bash
F="TimeLanding"   # ← replace with $1 when an argument was given
S=$(mktemp -d)
grep -rn "IRecipient<" WinTeam.Mobile.Core --include="*.cs" > "$S/recipients.txt"
grep -rn "WeakReferenceMessenger.Default.Register\|WeakReferenceMessenger.Default.Unregister" \
  WinTeam.Mobile.Core --include="*.cs" > "$S/register.txt"
grep -rn "WeakReferenceMessenger.Default.Send\|StrongReferenceMessenger.Default.Send\|Messenger.Send" \
  WinTeam.Mobile.Core --include="*.cs" > "$S/senders.txt"

# Per-message usage across every project that could reference it.
for f in $(find "WinTeam.Mobile.Core/Messages/$F" -name "*.cs" | sort); do
  n=$(basename "$f" .cs)
  echo "=== $n ($f)"
  grep -rn "\b$n\b" WinTeam.Mobile.Core WinTeam.Mobile.iOS WinTeam.Mobile.Android MobileCore \
    --include="*.cs" | grep -v "^$f:"
done > "$S/usage.txt"
echo "$S"
```

Senders must be counted across all four projects — messages are sent from platform view code
(`KioskTimeClockView.cs`, `TimeClockKioskFragment.cs`) and from Managers (`PunchesManager`), not only from
view models.

## Report

Produce these six sections. For each finding give the message type and the `path:line` of the live half.

1. **Orphans — responder but zero senders.** For each candidate confirm with
   `grep -rn "new <Name>(" ...` **and** `grep -rn "Send<<Name>>" ...` across all four projects; the
   generic-`Send<T>()` form has no `new`, so checking only one pattern produces false positives.
   For each orphan, also look for the **live direct-access route that replaced it** (a sibling property
   with the same name/meaning) — that is the actionable half.
2. **Dead letters — sender but zero recipients.** Distinguish genuinely dead from
   *conditionally* handled: `InitInactivityMonitorMessage` is handled only by `KioskTimeClockViewModel`,
   which is correct, not a defect.
3. **Register/Unregister asymmetry.** Diff each class's manual register list against its unregister list
   (for TimeLanding: `TimeClockViewModel.Messages.cs` `RegisterSubViewModelsCallbacks` vs
   `UnregisterSubViewModelsCallbacks`, and the same pair on `KioskTimeClockViewModel`). Also flag any
   `Register` call sitting in a **constructor** rather than inside the register method — those escape the
   pairing entirely.
4. **Multi-responder risk.** For every `RequestMessage<T>`/`AsyncRequestMessage<T>`, list all responders
   (`IRecipient<T>` implementors plus manual handlers that call `.Reply(`). More than one responder — or
   one responder on a class that has a `Kiosk*` subclass, since both instances can be alive — is a
   potential `InvalidOperationException`. Note whether the responder guards with `HasReceivedResponse`.
5. **Misfiled messages.** Files directly under `Messages/$F/` instead of `Request/`, `ValueChanged/`, or
   `Notification/`; and files in that tree that are **not** messenger messages at all (plain DTOs,
   `TinyMessageBase`/`GenericTinyMessage<T>` bus types) and belong elsewhere.
6. **Doc drift** against `docs/architecture/timeclock/messages.md` (only when auditing `TimeLanding`):
   message types in the tree but absent from the catalog; catalog entries whose type no longer exists;
   sender/responder attributions that no longer match.

   **Check the catalog exists before running this item, and skip it explicitly if it does not.** That file
   is not currently in the working tree or in git. A missing catalog is not drift and must never be reported
   as findings — say "catalog unavailable, item 6 not run" in the report, because a silently skipped section
   reads as a clean one.

   **Compare type names, not row counts.** A file count and a row count are not comparable here: the page
   holds several tables plus their header rows, and two files under this tree declare two types each
   (`TimePunchOfflineSuccessMessage.cs` and `TimePunchOfflineServerErrorMessage.cs`, each with its
   `*Content` DTO). Diff the **set of type names** instead — extract declared types from the tree,
   extract the catalog's first-column identifiers, and report only names present on one side and not the
   other.

   Known gap as of this writing: the catalog omits the two `SwitchTo*Message` bus types and the four
   `*Content` payload DTOs. Those are the same types item 5 flags as belonging outside this tree, so
   treat them as expected absences rather than new drift.

## Rules

- **Report only. Change no C# and delete nothing.** Deciding an orphan's fate needs feature history.
- Give every finding a `path:line` so it is clickable.
- If a section has no findings, say so in one line rather than omitting it — a silent section reads as
  "not checked".
