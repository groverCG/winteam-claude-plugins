---
name: naming-and-documenting-members
description: >-
  Use when adding or renaming a public method, class or parameter in WinTeam.Mobile.Core, when writing
  or reviewing /// doc comments, when about to write a // comment explaining what a line does, or when
  adding a method with no /// block.
---

# Name the code so it explains itself, document the contract so callers don't have to read it

Two halves that look contradictory until you see the line between them:

- **`///` doc comments describe the contract.** What the member does, what each parameter means, what it
  returns, what it throws. Required on every method.
- **`//` comments never narrate the body.** If a line needs explaining, the name is wrong or the block wants
  extracting.

A `//` comment that restates the code is a defect, not documentation: it doubles the edit surface, and it goes
stale silently the first time someone changes the line without changing the comment. Then it actively lies.

## When to use

Before writing the member, not in a cleanup pass. Fires when you are about to:

- name a method, parameter, local, field, or property under `WinTeam.Mobile.Core/`,
- write any `//` comment,
- add a method without a `///` block.

## When NOT to use

- Generated files, and `*.Designer.cs`.
- Overrides and interface implementations that add nothing to the base contract — `<inheritdoc/>` is correct
  and sufficient there.
- Trivial auto-properties and `[ObservableProperty]` backing fields.
- Platform view code, where the required-documentation half is relaxed. The naming rules still apply.

## Documentation

Every method gets a `///` block. These are triple-slash comments in the `.cs` file — **nothing generates or
maintains a separate `.xml` file.**

```csharp
/// <summary>
/// Submits the pending entry and clears it from the local queue on success.
/// </summary>
/// <param name="context">Immutable snapshot of the entry being submitted.</param>
/// <param name="cancellationToken">Cancels the network call; the queue is left untouched.</param>
/// <returns><c>true</c> when the server accepted the entry.</returns>
/// <exception cref="InvalidOperationException">No entry is pending.</exception>
public async Task<bool> SubmitAsync(SubmitContext context, CancellationToken cancellationToken)
```

- `<summary>` — what it does, in one sentence, in terms of the caller's intent. Not a restatement of the name.
- `<param>` — one per parameter, always. State the *meaning*, including anything the type does not convey:
  units, whether null is allowed, what happens on the edge.
- `<returns>` — whenever non-void. Say what the value means, not its type.
- `<exception>` — for anything a caller should reasonably catch.
- `<remarks>` — where a non-obvious reason lives. See the relocation rule below.
- `<see cref="..."/>` — to point at related types, as the repo already does.

## Comments in the body: exactly one exception

**The only permitted `//` comment inside a method body is one stating a formula or mathematical
calculation** — the formula itself, or the business rule or spec it comes from, where the correctness of the
arithmetic cannot be judged from the identifiers alone.

```csharp
// Overtime = hours beyond 40 in the week, paid at 1.5x base. Company policy HR-114.
var overtimePay = Math.Max(0, weeklyHours - 40) * baseRate * 1.5m;
```

That is the entire list. It has one item.

**Everything else: rename or extract instead.** If you are about to comment a block to say what it does, that
block is a method and the comment is its name.

```csharp
// Before
// check if the punch is inside the geofence and not stale
if (distance <= radius && age < TimeSpan.FromMinutes(5)) { }

// After — the comment became the name
if (IsWithinGeofenceAndRecent(distance, radius, age)) { }
```

The test to apply, so the rule holds without memorising the exception: **a permitted comment states a
formula. A comment answering "what does this line do" is a defect.** Difficulty is not the criterion — "this
code is hard" is arguable about anything, and would reopen the question the rule just closed.

### Non-obvious code that is not a formula

This is where the rule is most likely to be misread, so it is explicit: something genuinely non-obvious that
is **not** a formula still gets documented — it just goes in the member's `///` block, in `<summary>` or
`<remarks>`, rather than beside the line.

That covers a platform-bug workaround, a load-bearing call ordering, a framework quirk, why a rare null
occurs — anything a reader might otherwise think is redundant and delete.

```csharp
/// <summary>Applies the pending selection to the input state.</summary>
/// <remarks>
/// Must run before the queue is started. Reversing the two leaves the first entry
/// unvalidated, which surfaces later as a rejected submission with no local record.
/// </remarks>
public void ApplyPendingSelection()
```

**"No comments except formulas" never means "leave it undocumented."** The information moves to the
contract; it does not disappear. A crash-avoiding workaround with no explanation anywhere is a worse outcome
than the noisy comment this rule exists to remove.

`TODO`/ticket references are outside this rule entirely — they track work rather than explain code.

## Naming

1. **State intent, not type or mechanism.** `pendingSubmission`, not `entityList` or `strJson`.
2. **No abbreviations** beyond established domain terms already in the codebase. Spell out `request`,
   `configuration`, `response`.
3. **Booleans read as predicates** — `isActive`, `hasPendingWork`, `canSubmit`, `shouldRetry`. A boolean named
   `flag`, `status`, or `check` is always wrong.
4. **Async methods end in `Async`.** No exceptions; the suffix is how callers know to await.
5. **Banned as names, always:** `tmp`, `temp`, `data`, `result`, `obj`, `item`, `value`, `flag`, `list`,
   `str`, `x`. `result` is the most common offender and the least excusable — name what it is a result *of*.
   Loop variables in a two-line loop are the one place a single letter is acceptable.
6. **Methods are verb phrases**, properties and fields are noun phrases. `CalculateTotal()`, not `Total()`
   for a method that does work.
7. **Match the domain vocabulary already in use.** If the codebase says "punch", a new method does not say
   "clock event". Consistency beats your preferred word.

## Verify

- Every new method has a `///` block with `<summary>` and one `<param>` per parameter.
- Zero `//` comments in bodies except formula statements. Read each one and ask: is this stating a formula?
  If not, delete it and fix the name.
- Anything non-obvious and non-formula is captured in `<summary>`/`<remarks>` — not simply dropped.
- No banned names, no unexplained abbreviations, `Async` suffixes present.
- `dotnet build WinTeam.Mobile.Core/WinTeam.Mobile.Core.csproj`. Note the build will not catch a malformed
  `///` block or a `<param>` naming a parameter that no longer exists, so check those by eye.
