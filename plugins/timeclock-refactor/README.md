# timeclock-refactor

Conventions extracted from the WinTeam `TimeClockViewModel` refactor (MOB-13653, Iteration 1).

## What's in here

| Item | Purpose |
|---|---|
| `skills/vm-communication-channel` | Which of the six inter-component mechanisms to use — `RequestMessage`, `ValueChangedMessage`, notification record, C# event, `BusManager`, or a direct reference |
| `skills/extract-child-view-model` | The wiring a child view model needs: base class, construction site, `[Inject]`, activation, teardown |
| `skills/kiosk-variant-pairing` | Deciding whether a punch-flow change needs a kiosk variant, and which of the three substitution mechanisms to use |
| `skills/extracting-orchestrator-pipelines` | The Iteration 2 shape: pulling an *ordered pipeline* out, where the ordering becomes implicit in construction and nothing enforces it |
| `skills/moving-bound-properties` | The view layer was never touched — moving a bound member silently stops a control updating without failing the build |
| `skills/retiring-orphan-messages` | Working the seven responder-with-no-sender messages, where the live direct access is the actionable half |
| `commands/vm-message-audit.md` | Re-derives the messenger map from source and diffs it against `docs/architecture/timeclock/messages.md` |
| `commands/parity-check.md` | Drives the whole per-area parity loop — preflight, audit via `refactor-parity-auditor`, characterization tests, fixes via the six skills, re-audit. Takes a feature area *or* a free-form description. Reports and stops before writing anything |
| `commands/next-extraction.md` | Ranks the remaining candidates by coupling removed per unit of risk — explicitly *not* by line count |
| `agents/refactor-parity-auditor.md` | Deep behaviour-parity audit of an extraction against the merge base with `dev` — never `master`; report-only |

Everything is addressed with the plugin prefix, but only commands take the leading slash — skills as
`timeclock-refactor:vm-communication-channel`, commands as `/timeclock-refactor:vm-message-audit`. The bare
`/vm-message-audit` form does not resolve, and neither does a skill written with a slash.

**The six skills fire automatically; the three commands do not.** The skills carry no
`disable-model-invocation`, so their descriptions load into context and Claude invokes them when a task matches.
That is deliberate: a rule about activation wiring or a bound property is only worth anything *before* the code
is written, and nobody remembers to ask. The three commands keep the flag — they are sweeps, not guardrails —
and the agent is invoked on request in the same way.

**What keeps them off `master` is no longer the flag.** See *Why this is a plugin* below.

## Relationship to `winteam-standards`

`winteam-standards` is the sibling plugin in this marketplace: repo-wide, not branch-scoped, and mostly
**automatic**. It covers general standards — file and method size, layer boundaries, subscription teardown,
dependency injection, MVVM generators, naming and documentation.

The two agree where they overlap. This plugin's context-record pattern is the fix that plugin's 3-parameter
limit asks for, and `keeping-files-small` defers here for the wiring once an extraction becomes a view model.
Install them independently.

## Why this is a plugin and not plain project skills

Iteration 1 is **not on `master`**. `WTBaseObservableRecipient`, `IActivatableViewModel`,
`PunchInputState` and `RejectionContext` exist only on the refactor branch, and
`Messages/TimeLanding/` holds 55 types there against 10 on `master`.

`.claude/` is committed, so these files reach everyone who clones — including teammates working on `master`,
where this advice is actively wrong. Being a plugin is what makes that safe:

**It must be installed**, per machine, before it does anything at all. **This is the only guard, and it is
entirely load-bearing.** That is not possible for plain project skills in `.claude/skills/`, which load for
everyone automatically — which is why this repo no longer has that directory at all; `winteam-standards`
absorbed the last four of them when the skills were consolidated.

**Do not treat the descriptions as a second layer.** An earlier version of this file claimed they were, on the
theory that a description naming a nonexistent path cannot match. Checked against `master`, it does not hold:
`ViewModels/TimeLanding/Punches/TimeClock/` (6 files), `ViewModels/Kiosk/` (11) and `Messages/TimeLanding/` (10)
all exist there. So four of the six descriptions anchor on paths that resolve on `master` anyway, and the other
two — `extracting-orchestrator-pipelines` and `moving-bound-properties` — name types rather than paths, so they
anchor on nothing branch-specific at all. Every description can match on `master`.

What does help, once a skill has already loaded, is the branch-only *types* — `WTBaseObservableRecipient`,
`IActivatableViewModel`, `PunchInputState`, `RejectionContext`, zero hits on `master` — and the one-line branch
note each skill body opens with, which a reader sees at the moment they invoke it. Both are corrective, not
preventive. **So: uninstall when you leave the branch.**

Both plugins in this repo work the same way: the committed `.claude/settings.json` registers the marketplace so
`/plugin` lists them, and neither is enabled until someone installs it. Nobody is prompted for this one, and it
does nothing on `master` unless deliberately opted into — which, given the advice is wrong there, is the point.

There is deliberately no `SessionStart` hook — see *The `branch-check.sh` question, reopened*.

## Installing it

**Nothing here is published anywhere, and nothing installs it for you.** If you don't opt in, this plugin has
no effect on your sessions whatsoever.

Two commands, once per machine:

```bash
claude plugin marketplace add ./.claude/plugins
claude plugin install timeclock-refactor@winteam-local -s local
```

**`-s local` matters.** The default scope is `user`, which would enable branch-specific advice in every project
on your machine. `local` records it in the gitignored `.claude/settings.local.json`. **Uninstall when you leave
this branch:**

```bash
claude plugin uninstall timeclock-refactor@winteam-local -s local
```

## Working on this plugin

**Edit the files here, then bump `version` in `.claude-plugin/plugin.json`.** The bump is mandatory — this
plugin is served from a version-keyed cache, so without it your edits reach nobody. **This plugin is the
cautionary tale that produced the rule:** it sat pinned at a cached `1.0.0` against a `1.1.0` manifest, three
skills cached where the repo had six, and every edit silently did nothing while `marketplace update` reported
success.

If a change doesn't apply, check `~/.claude/plugins/installed_plugins.json` — a `version` behind the manifest
means you are pinned:

```bash
claude plugin marketplace update winteam-local
claude plugin update timeclock-refactor@winteam-local -s local
# still stale? force it:
claude plugin uninstall timeclock-refactor@winteam-local -s local
claude plugin install   timeclock-refactor@winteam-local -s local
```

Iterate against this directory directly, with no cache in the way:

```bash
claude --plugin-dir .claude/plugins/timeclock-refactor
```

Validate both halves after changes:

```bash
claude plugin validate .claude/plugins
claude plugin validate .claude/plugins/timeclock-refactor --strict
```

## Retiring it

**When Iteration 1 merges to `master`,** the architecture these skills describe becomes the repo's reality and
the branch caveats become noise. At that point pick one:

- **Promote:** fold the six skill directories and the commands into **`winteam-standards`**, then delete this
  folder. The skills already fire automatically, so promotion is just the fold-in plus widening each description
  past its branch-only path anchor. Simplest if the team wants them permanently. Do **not** promote them to
  `.claude/skills/` — that directory was deliberately emptied during the skills consolidation so that every
  auto-firing skill in the repo lives in one unit; recreating it would reopen the split that change closed.
- **Keep the plugin:** strip the branch notes and widen the descriptions. Worth it only if you want the
  install-to-opt-in behaviour for its own sake.

**One split is already decided for that point.** `vm-communication-channel` covers two things: the
`WeakReferenceMessenger` conventions, which are genuinely branch-scoped, and a channel-selection decision table
whose `BusManager` half is repo-wide advice this branch scoping currently hides. On promotion, divide it — the
messenger half stays with TimeClock, the table moves to `winteam-standards`.

### The `branch-check.sh` question, reopened

`hooks/branch-check.sh` was deleted with the reasoning that it existed to catch skills auto-firing on the wrong
branch, and once nothing auto-fired there was nothing left to guard. **The skills now auto-fire again, so that
reasoning no longer holds.** It was not reinstated, deliberately, on these grounds:

- The install is per-machine and opt-in, so only someone who asked for this plugin is exposed at all.
- A `SessionStart` hook fires on every session to cover a case that only arises if someone installs the plugin
  and then switches branch without uninstalling.

A third bullet used to sit between those two — "four of the six descriptions name paths that do not exist on
`master`, so they cannot match there." **It was wrong**, and it was doing real work in this argument. Every
path any description names exists on `master`. See *Why this is a plugin* above.

**So the residual risk is larger than this section previously recorded.** It is not two skills; it is all six.
Any of them can match on `master` and give advice about types that do not exist there, and the opt-in install
is the only thing standing in the way. That leaves the case for `branch-check.sh` resting on the single first
bullet. It is still not reinstated — the exposure needs someone to install this plugin and then change branch
without uninstalling — but if that ever bites anyone, reinstating the guard is the fix, and this is the note
that says so rather than leaving a stale justification standing.

## Companion docs

The skills reference `docs/architecture/timeclock/` (10 files: the `messages.md` contract catalog, 8
feature-area docs, and a composition README). They are no longer gitignored and are intended to be committed
alongside this plugin — the audit command diffs message *descriptions* against `messages.md`, so it degrades if
they are missing. They are branch-specific in the same way these skills are; if you retire this plugin, decide
their fate at the same time.

**No counts are recorded anywhere in this plugin, deliberately.** Every command, skill and the agent derives
what it needs from the repo on the run that needs it. A recorded figure here decayed on a schedule nobody
controlled — the branch is rebased, and every extraction moves a line count — so the figures went stale faster
than anyone checked them. `messages.md` describes each message; how many there are is a `grep`.
