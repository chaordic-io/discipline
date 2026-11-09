# Changelog

Each release lists what changed and, under **Migration**, what a repository set up with the previous
version has to do (`/discipline:upgrade` walks through it). Versions follow semantic versioning:
a minor release adds without breaking, a major one needs migration steps.

## Unreleased

- **Lenses of the project's own.** The profile's new `customLenses` field declares lenses next to the
  built-in ones, {name: {checklist, why, secondOpinion?}}, each with a checklist kept in the repository.
  `discipline lenses new NAME --why R [--checklist PATH] [--second-opinion]` creates one: a checklist
  from the template (by default `.claude/agents/<name>-reviewer.md`, so it also works by hand as a
  project agent), the profile entry and a review-context section. A custom lens runs like a built-in
  one; it is on while declared, and `overrides.remove` turns it off. `discipline review checklist`
  prints a custom lens's checklist; `discipline check` fails when one is missing and warns when a
  custom lens has no review-context section. `secondOpinion` gives its refuted critical/high findings
  a second verifier: the review plan now lists those lenses, and the workflow takes them from it.
- **`discipline review requeue --lens L --reason R [--unit ID ...]`** makes reviewed (unit, lens) pairs
  due again, in full, although their code didn't change, e.g. after a checklist's rules changed. The
  earlier reviews stay in the history; the pairs show as `stale` until reviewed.
- The read-only guard also blocks `discipline review requeue` and `discipline lenses new` for reviewers.

### Migration (from 0.2.0)

None required. Optionally add `"customLenses": {}` to `.agents/profile.json`, so the field is there to
fill in.

## 0.2.0 (2026-11-05)

- **New lens, simplicity (always on).** Its rule: don't express a rule, a case or anything else in a
  new way when an existing, adequate composition, abstraction or configuration achieves the same with
  little or no compromise. It looks for superfluous structure, such as pass-through layers,
  interfaces with one implementation, options nobody sets, special cases the general mechanism
  covers, re-built machinery and defensive code for impossible states. It isn't against
  abstraction: each finding must name the existing machinery or composition that expresses the same
  behaviour, and seams the spec, a decision, the roadmap or the review context ask for are left
  alone. Checklist `discipline:simplicity-reviewer`; review-context section `simplicity`.
- **E1** now covers the code as well as the system: "Few moving parts, in the system and in the code".
- **Duplication lens:** prefers an existing helper and proposes a new abstraction only when it
  removes more than it adds.
- **Fix:** the architecture checklist had lost items 1–3 (structure against the spec, layer
  violations, violated invariants) when its placeholders moved to the review context in 0.1.0; they
  are back, and the review context's architecture section now has two fields to fill in: layers, and
  invariants. A test keeps checklist numbering free of gaps.
- **Gate:** `discipline check` warns about a lens that is on but used by no unit.
- **Adopting discipline on an existing project:** bootstrap surveys first (`discipline init
  --survey`: agent instructions, specs, decision records, roadmap notes, the gate and CI, uncommitted
  changes, the size of the code) and asks a batch of adoption questions before copying anything, so
  nothing the team wrote is merged or moved without their answer. `discipline review baseline`
  accepts existing code without reviewing it (shown as `baseline`, never `ok`; naming a unit in a run
  reviews it in full). `decisionsElsewhere` in the profile keeps an existing decision folder where it
  is, linked from the index and searched. Gate checks the existing code fails are ratcheted, fixed as
  planned work or left out, each by the user's choice; never fixed as part of setup.
- **Resuming after a crash:** the work file has an "In progress" section, written before a step that
  edits files and cleared when it is done. A `SessionStart` hook shows every new session the
  continuation point, an unfinished step and the changes newer than the work file; a `Stop` hook asks
  the agent once to update the work file when code changed after it (`DISCIPLINE_STOP_CHECK=0` turns
  it off); `discipline work` and `discipline check` warn about a stale work file.
- **Team preferences start empty:** the `.agents/USER.md` template no longer suggests the plugin
  author's own preferences; it lists the kinds worth asking about, and bootstrap records only what
  the team says.

### Migration (from 0.1.0)

1. `discipline lenses apply` (the gate fails until you do: the profile now turns `simplicity` on),
   then add `simplicity` to the units where code lives (usually every unit except dependency and
   contract-only units). `discipline check` warns until a unit uses it.
2. Add a `## simplicity` section to `.agents/review-context.md`: the seams the project keeps on
   purpose, and the shared machinery to use instead of re-building (see the template).
3. If your review context's `## architecture` section still holds the template's placeholder text,
   which includes the lost checklist items, replace it with your layers and invariants.
4. Add the "In progress" section to each work file (see the template in `discipline work`'s source
   or a newly created work file), and the "In progress" sentence to `CLAUDE.md`'s opening paragraph.
5. Pin `v0.2.0` in the gate and set `"discipline": "0.2.0"` in `.agents/profile.json`.

## 0.1.0 (2026-11-05)

First release as a Claude Code plugin (`discipline@chaordic`), replacing the copy-in bootstrap kit.

- **Plugin:** skills `/discipline:bootstrap`, `/discipline:upgrade`, `/discipline:working`,
  `/discipline:engineering`, `/discipline:stack`; the workflow `/discipline:review-loop`; ten reviewer
  agents and the read-only `discipline:review-reader`; a `PreToolUse` hook that blocks the reviewer's
  writes.
- **The `discipline` command** (standard-library Python): `init`, `check`, `review …`, `lenses …`,
  `spec-rules`, `ai-evals`, `handover`, `doc`. Runs from the plugin with no installation; CI runs it
  pinned with `uvx`.
- **Reviewers chosen by the project profile:** security, behaviour, tests, architecture, duplication
  and supply chain always; performance, contracts (API drift), AI and localisation when the profile
  calls for them.
- **Review loop:** incremental by content hash per unit and lens, with lens context (a contract change
  re-queues the contract review of every unit that uses it); second opinion on refuted serious
  security and supply-chain findings; questions for the user instead of guesses; a check that the
  read-only phases wrote nothing; usage guard for the weekly and 5-hour limits;
  the fixer never decides product behaviour (it hands such findings back as questions) and fixes the
  code, not the tests; the tests reviewer and the diff-only re-review flag tests written to pass.
- **Evidence:** every review outcome keeps its scenario, fix, verifier's reasoning and the snapshot of
  the code that was reviewed; `discipline review evidence` reports coverage and findings as Markdown.
- **Gate checks:** review-unit coverage, units ↔ profile, spec rules pinned by tests, AI eval sets with
  their facets per mode, and size budgets for the handover files (warnings).
- **Guides:** engineering principles E1–E10 and stack-selection criteria S1–S7, kept apart.
- **Teams and branches:** each branch keeps its continuation point in `.agents/work/<branch>.md`
  (`discipline work`), with STATUS.md holding only what is shared; one file per decision in
  `docs/decisions/` with a generated index (`discipline decisions`); append-only review state (ledger,
  history, trees) and HISTORY.md merged with git's union driver; spec rule IDs defined twice fail the
  gate; team roles, who answers review questions, and personal preferences in an uncommitted
  `USER.local.md`. `discipline work --list` shows every branch in flight from its own work file (no
  shared table to conflict over); pinned review snapshots are only ever added, so branches sharing a
  clone keep each other's; the working guide covers merges that break what git doesn't see.
- **Check, then ask; never assume silently:** a rule for what agents decide (technical, reversible,
  invisible to users) and what the user decides; `discipline decisions search` before asking anything,
  so settled questions aren't asked again; assumptions marked `(assumed <date>, not confirmed)` in the
  spec, listed by `discipline assumptions` and warned about by the gate; the behaviour reviewer flags
  behaviour nobody wrote down; delegated agents and proposals list their assumptions.
- **Purpose:** the spec opens with section 0 (problem, users, success measures, non-goals); bootstrap asks
  for it, proposals state how they fit it, and the behaviour reviewer raises a question when code works
  against it.

### Migration (from the copy-in kit)

1. Run `discipline init` (the copy step of `/discipline:bootstrap`): it adds the new files
   (`.agents/review-context.md`, `.claude/review/project.json`, `.claude/settings.json` entries) and
   keeps everything that exists.
2. Move `scripts/review/units.json` to `.claude/review/units.json` and turn its `lenses` map into a
   list of lens names; delete `scripts/review/`.
3. Move the workflow's `PROJECT` block into `.claude/review/project.json`, and the `ADAPT` parts of
   `.claude/agents/*.md` into the matching sections of `.agents/review-context.md`; then delete
   `.claude/agents/` (the checklists come from the plugin) and `.claude/workflows/review-loop.js`.
4. Reduce `.agents/ENGINEERING.md` and `.agents/WORKING.md` to the project's own parts (the generic
   text is now `/discipline:engineering` and `/discipline:working`).
5. Replace `python3 -m unittest discover -s scripts/review` in the gate with the pinned
   `discipline check`, and add `"discipline": "0.1.0"` to `.agents/profile.json`.
