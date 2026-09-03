---
name: keeping-core-methods-small
description: >-
  Use when writing or extending a method, constructor, or interface declaration in WinTeam.Mobile.Core, or
  when a parameter list reaches four. Method bodies and parameters, not whole-file length.
when_to_use: >-
  Applies even mid-execution of an already-approved plan that names the file, class or method shapes —
  an approved plan is not an exemption. Applies whichever tool writes the file: Write, Edit, a Bash
  heredoc, `sed -i`, or an MCP server's own file-creation call.
---

# Keep a business-logic method to one job

Two limits, both **only for `WinTeam.Mobile.Core/`** — the business logic layer:

| Limit | Target | Flag at |
|---|---|---|
| Method body length | 10 lines | 15 |
| Parameter count | 3 | 4 |

The "flag at" numbers are the machine-readable source of truth and live in one place:
[`thresholds.json`](../../thresholds.json) at the root of this plugin (`maxBodyLines`, `maxParams`,
`lengthCarveOuts`). The edit
hook reads it and `/winteam-standards:code-style` applies it; the table above restates it for readability.
**If they disagree, the file is right** — and fix the table.

**Platform view methods are exempt from both.** Declaring and wiring UI elements in
`WinTeam.Mobile.iOS/` and `WinTeam.Mobile.Android/` legitimately needs the room, and a flat run of binding
statements is not improved by chopping it up.

A 10-line body is short. That is the point: it forces one job per method, which is what makes the code
readable without comments and reviewable without running it.

## When to use

Before writing the method, not after — retro-fitting is what produces the 40-line method with three
extracted helpers that each take seven parameters. Fires when you are about to:

- write or extend any method, constructor, local function, or command handler under
  `WinTeam.Mobile.Core/`,
- declare a method on an interface there,
- add a fourth parameter to anything.

## When NOT to use

- Any method in `WinTeam.Mobile.iOS/` or `WinTeam.Mobile.Android/`. Both limits are Core-only.
- `RegisterInjections` and other flat declaration lists whose entire body is one statement per line with no
  branching. Length is the content; splitting is pure churn.
- Generated files.
- Constructors that only assign parameters to fields.
- A `switch` expression mapping an enum to values — that is a table, and it should stay one piece.

## Rules

1. **Count the body, not the signature or braces.** A 12-line body is inside tolerance; a 20-line one is not.
2. **Guard clauses over nesting.** Early return is the single highest-yield fix and usually gets a method
   under the cap on its own.

   ```csharp
   // Before — nesting drives the length
   if (request is not null)
       if (request.IsValid)
           return await SubmitAsync(request);
   return Result.Skipped;

   // After
   if (request is null || !request.IsValid) return Result.Skipped;
   return await SubmitAsync(request);
   ```

3. **Extract to a named method, and let the name carry the explanation.** If you are reaching for a comment
   to label a block, that block is the method you should extract. See
   `naming-and-documenting-members`.
4. **A dictionary or `switch` expression beats a long `if`/`else if` chain** when the whole body is choosing
   a value by key.
5. **Extraction must not widen the parameter surface.** Four private helpers each taking six arguments is
   worse than the one long method you started with. If the pieces need that much shared context, the state
   belongs in an object — see rule 7.

## The parameter limit has two different fixes

Which one you need depends on what the extra parameters *are*. Getting this backwards is the common mistake.

**Collaborators — services, managers, other view models.** These do not become a record. They become
`[Inject]` properties, which is this repo's idiom; see `wiring-dependency-injection`.

```csharp
// Before
public MyThing(ISettingsManager settings, IDialog dialog, ILogger logger, IClock clock) { }

// After — property injection, so the constructor takes nothing
[Inject] public ISettingsManager Settings { get; set; }
[Inject] public IDialog Dialog { get; set; }
```

**Data — values that travel together.** These become a `record` or `readonly record struct`. Prefer an
immutable one, and build it in a single place so every caller gets a consistent snapshot.

```csharp
// Before
Task<Result> SubmitAsync(string reference, DateTime at, bool isRetry,
                         string note, GeoPoint location, int attempt);

// After
public readonly record struct SubmitContext(
    string Reference, DateTime At, bool IsRetry, string Note, GeoPoint Location, int Attempt);

Task<Result> SubmitAsync(SubmitContext context);
```

**A record carrying six fields is not cheating.** The win is that the fields now have one definition, one
construction site, and travel as a unit — not that the number six disappeared. But note the record is a
*snapshot*: if a caller mutates an object reachable through it, every holder sees the change. Prefer value
types and immutable members inside it.

## Known offenders

The worst over-parameterised declarations under `WinTeam.Mobile.Core/`, and why each is the shape it is: the
`WTPunchFlowPersistentClient` constructor and `WTTimePunchQueuableHttpMessage` constructor are pure collaborator
lists, so both are `[Inject]` cases; `ToPunchRequest` and `RunOfflineConnectivityWithGifAnimation` are data
that wants a record; `SubmitTimeMessagesAsync` is declared on an interface, so every implementor inherits its
signature. That list is short enough to work through; ask for `/winteam-standards:code-style`.

Method *length* is the larger problem — **several hundred** Core methods already exceed 15 lines.
`/winteam-standards:code-style` derives the live counts for both, parameters and length.
**That is not a backlog to work through — it is context.** Apply the limit to code you write or modify; do not open unrelated methods to
shorten them.

## Verify

- Body under 15 lines, four parameters or fewer, and no helper you extracted is worse on either count.
- Behaviour identical — extraction is a refactor, so no reordering and no added guards that change results.
- `dotnet build WinTeam.Mobile.Core/WinTeam.Mobile.Core.csproj`. If you changed an interface signature, build
  the platform projects too; implementors there will not fail until you do.
