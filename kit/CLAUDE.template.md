# <PROJECT>

**Starting a new session?** Read `.agents/README.md` first. It covers the current status, the user's
preferences, how we work and environment quirks. Update `.agents/STATUS.md` at the end of sizeable work.

<!-- ADAPT: one paragraph on what the product is and who it is for. -->
The specification is in `docs/SPEC.md`. Read the relevant section before you change behaviour, and
update the spec when behaviour changes. When a change comes from user feedback or a product decision,
also add an entry to `docs/DECISIONS.md`: what triggered it, the decision, the alternatives turned down,
and where it is in the spec. New features start as a proposal in `docs/proposals/` (template:
`docs/proposals/TEMPLATE.md`) with the user's open questions.

## Layout
<!-- ADAPT: one line per top-level directory: what lives there, which files are generated and must
never be edited by hand, and which command regenerates them. -->
- `.claude/agents/`: read-only reviewer checklists, one per lens, and `review-reader.md`, the agent type the review loop runs them in.
- `.claude/workflows/review-loop.js`: the review → verify → fix loop.
- `scripts/review/`: the review loop's bookkeeping (`review.py`), the lens selection (`lenses.py`), the spec-rule check (`spec_rules.py`) and their tests; `units.json` splits the repo into review units.
- `.agents/`: the handover folder for new sessions; `.agents/profile.json` is the project profile that decides which lenses run.

## Commands
- `make check`: the full gate (lint + tests + coverage + duplication + vulnerability scan + review-unit
  coverage). It must pass before you declare any work done. <!-- ADAPT: your gate command -->
<!-- ADAPT: the other commands: single test suites, code generation, local development, and the slow
suites (browser end-to-end, production-image smoke test) with when to run them. -->

## Non-negotiable rules
- **Tests for everything.** Every new function or endpoint gets tests in the same change.
  - Use property-based tests or fuzz tests for parsers, conversions, arithmetic and anything with an
    invariant. <!-- ADAPT: libraries -->
  - Code that touches a database, mail server or other external system is tested against the real
    service (testcontainers or a container started by the test). Do not mock the database.
  - Every bug fix gets a regression test that fails without the fix.
- **Every failure is ours.** A red gate, a flaky test, a stray error or warning is investigated to its
  root cause and fixed with a regression test, whether this change caused it or not. Re-running until
  green is not a fix; "unrelated" and "pre-existing" are not reasons.
- **Strict lint.** Don't add lint suppressions without a specific reason in a trailing comment. Never
  weaken the lint configs to make code pass.
- **Generated code** is never edited by hand; regenerate it. <!-- ADAPT: the command -->
- **Claims match the code.** User-facing copy (marketing pages, docs, help texts) claims only what is
  built, and tests pin the claims to the code where they can.
- **Translations are written for the market, not translated.** Every non-English text reads as if a
  native copywriter for that market wrote it: idiomatic sentences, no calques of the English, no English
  list rhythm or headline structure. Keep the meaning, and every claim, exactly as in the English. Keep
  the established register and the product's terminology. <!-- ADAPT: languages, register per language,
  catalogue paths; delete this rule if the product has one language -->
- **National or customer-specific rules are never hard-coded.** Country- or customer-specific behaviour
  is configuration on a generic engine, or a module behind an interface, chosen by data, so one
  country's rules never reach another's users. <!-- ADAPT: delete if irrelevant -->
<!-- ADAPT: domain rules. Examples from earlier projects:
- Tenancy: all tenant data access goes through one helper; every tenant table has row-level security and
  a test proving cross-tenant isolation.
- Money is integer minor units plus a currency code; rates are decimals. Never floats for money.
- Settings that feed calculations over time are versioned with a valid-from date; past periods are
  always calculated with the version in force then. Never mutate a version that has applied.
- Errors are wrapped with context; HTTP errors use one shape (e.g. problem+json).
-->

## Review loop
Run the saved `review-loop` workflow at the end of each phase or sizeable feature, or as a periodic
sweep. It is incremental and cheap when little has changed:
- **Units and lenses:** `scripts/review/units.json` splits the repo into units, each with the lenses
  that apply to it. Which lenses exist at all follows from `.agents/profile.json`
  (`python3 scripts/review/lenses.py show`); after changing the profile, run `lenses.py apply` and add
  any new lens to the units where it applies. A unit's `context` lists files outside it that also make
  a lens stale (the API contract for the contracts lens).
- **Ledger:** `.claude/review/ledger.json` stores the content hash each (unit, lens) pair was last
  reviewed at, so only stale pairs are reviewed, never-reviewed ones first, up to `maxUnits` per run
  (default 8).
- **Diff reviews:** a changed unit is reviewed as a diff against the tree it was last marked at
  (pinned under `refs/review/trees/`, recovered from a matching commit if lost).
- **Questions, not guesses:** where the spec, `docs/DECISIONS.md` and the proposals don't settle a
  behaviour, reviewers raise a question for the user; it is never fixed by an agent. Open ones:
  `python3 scripts/review/review.py questions`. Once answered and recorded in the spec and DECISIONS,
  close it with `review.py answer N --reason "..."`.
- **Each run:** one read-only reviewer per unit applies every pending lens; one skeptic per unit
  verifies its findings (a refuted critical or high security or supply-chain finding gets a second,
  independent verifier); a check confirms the read-only phases changed nothing; one fixer handles all
  confirmed findings and runs lint plus the affected tests; a reviewer then checks only the fixer's
  diff. Outcomes go to `.claude/review/history.jsonl`.
- **Run the full gate yourself after the loop.**
- **No repeats:** reviewers see every earlier finding in their unit (`review.py show <unit>`); a
  finding is rejected only with a written reason.
- **Usage guard (opt-in):** `stopAt: <weekly %>` and/or `stopAt5h: <5-hour %>` stop gracefully at
  that usage.
- **Progress:** `python3 scripts/review/review.py status`. When you add a directory, add it to a unit;
  the gate fails on uncovered files, and on units that disagree with the profile.
