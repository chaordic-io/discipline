# Changelog

Each release lists what changed and, under **Migration**, what a repository set up with the previous
version has to do (`/discipline:upgrade` walks through it). Versions follow semantic versioning:
a minor release adds without breaking, a major one needs migration steps.

## 1.0.0 (2026-11-05)

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
  `USER.local.md`.
- **Check, then ask; never assume silently:** a rule for what agents decide (technical, reversible,
  invisible to users) and what the user decides; `discipline decisions search` before asking anything,
  so settled questions aren't asked again; assumptions marked `(assumed <date>, not confirmed)` in the
  spec, listed by `discipline assumptions` and warned about by the gate; the behaviour reviewer flags
  behaviour nobody wrote down; delegated agents and proposals list their assumptions.
- **Purpose:** the spec opens with section 0 (problem, users, success measures, non-goals); bootstrap asks
  for it, proposals state how they fit it, and the behaviour reviewer raises a question when code works
  against it.

### Migration (from the copy-in kit)

1. Run `/discipline:bootstrap`'s step 2 (`discipline init`): it adds the new files
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
   `discipline check`, and add `"discipline": "1.0.0"` to `.agents/profile.json`.
