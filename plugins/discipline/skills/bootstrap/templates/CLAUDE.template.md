# <PROJECT>

**Starting a new session?** Read `.agents/README.md` first. It covers the shared status, your branch's
work file (`discipline work`: its continuation point), the team's preferences, how we work and
environment quirks. Keep the work file's continuation point current after every step, and
`.agents/STATUS.md` current when something shared changes. Before starting a step that edits files,
write it and the files it touches under "In progress" in the work file; set it back to "nothing" when
the step is done. (The discipline plugin shows a new session the continuation point and any
unfinished step, and asks for the work file to be updated when code changed after it.)

<!-- ADAPT: one paragraph on what the product is and who it is for. -->
Why it exists (the problem, the users, what success looks like, the non-goals) is section 0 of
`docs/SPEC.md`; read it before any judgement call no rule settles. The specification is in `docs/SPEC.md`. Read the relevant section before you change behaviour, and
update the spec when behaviour changes. When a change comes from user feedback or a product decision,
also add a decision (`discipline decisions new "<title>"`, a file in `docs/decisions/`): what triggered
it, the decision, the alternatives turned down,
and where it is in the spec. New features start as a proposal in `docs/proposals/` (template:
`docs/proposals/TEMPLATE.md`) with the user's open questions.

## Layout
<!-- ADAPT: one line per top-level directory: what lives there, which files are generated and must
never be edited by hand, and which command regenerates them. -->
- `.claude/settings.json`: enables the discipline plugin (marketplace `chaordic`), which brings the
  reviewer agents, the review loop (`/discipline:review-loop`), the guides (`/discipline:working`,
  `/discipline:engineering`, `/discipline:stack`) and the `discipline` command.
- `.claude/review/`: the review loop's configuration (`units.json` splits the repo into review units; `project.json` holds this project's settings for the workflow) and its state. The bookkeeping and the gate checks are the `discipline` command (`discipline help`), from the discipline plugin; the gate runs it pinned.
- `.agents/`: the handover folder for new sessions; `.agents/profile.json` is the project profile that decides which lenses run.

## Commands
- `make check`: the full gate (lint + tests + coverage + duplication + vulnerability scan + review-unit
  coverage). It must pass before you declare any work done. <!-- ADAPT: your gate command -->
<!-- ADAPT: the other commands: single test suites, code generation, local development, and the slow
suites (browser end-to-end, production-image smoke test, the AI eval suite) with when to run them. -->

## Non-negotiable rules
The short, binding form of how we build. The reasoning, and the engineering principles these come from
(E1–E10), are in /discipline:engineering (or `discipline doc engineering`), and this project's own in
`.agents/ENGINEERING.md`; cite the E-number when a decision or finding rests on one. How we work (the
request loop, verification, delegation, handover) is /discipline:working.
- **Check, then ask; never assume silently.** Before asking the user, look for an existing answer
  (`discipline decisions search <words>`, the spec, the proposals, STATUS.md) and apply it, citing it.
  Agents decide only technical, reversible choices invisible to users, and record them. The user decides
  anything user-visible, money, permissions, data, legal, cost, external commitments, and anything hard
  to undo. Work that can't wait proceeds on the most conservative assumption, marked
  `(assumed <YYYY-MM-DD>, not confirmed)` in the spec, listed in the branch's work file and reported;
  never written into the spec as settled. `discipline assumptions` lists them.
- **Tests for everything.** Every new function or endpoint gets tests in the same change.
  - Use property-based tests or fuzz tests for parsers, conversions, arithmetic and anything with an
    invariant. <!-- ADAPT: libraries -->
  - Code that touches a database, mail server or other external system is tested against the real
    service (testcontainers or a container started by the test). Do not mock the database. (E5)
  - Every bug fix gets a regression test that fails without the fix.
  - Fix the code, not the tests: an existing test's expected value changes, or a test is loosened,
    skipped or deleted, only when the spec or a decision says the old expectation was wrong, cited in
    the test.
- **Every failure is ours.** A red gate, a flaky test, a stray error or warning is investigated to its
  root cause and fixed with a regression test, whether this change caused it or not. Re-running until
  green is not a fix; "unrelated" and "pre-existing" are not reasons.
- **Observable, with quiet logs.** Every server process and job emits traces and metrics, with the
  trace ID in every log line and error response. Log at error level only real failures (a broken
  invariant, a failed dependency, a bug), once, where they are handled; expected outcomes (validation
  failures, not found, access denied, a retry that succeeds) are never logged as errors. No secrets or
  personal data in logs, traces or metric labels. Tests fail on error logs they did not expect, and a
  test of a failure path asserts the one error log it expects. Client errors are reported through our
  own endpoint. (E9) <!-- ADAPT: the logging and tracing setup, the test helper that captures logs -->
- **AI features are engineered like code (E10).** <!-- ADAPT: delete if the product calls no models -->
  Prompts live in `prompts/` (one file each) and models are pinned to exact versions; a change to
  either runs the eval suite, which must stay above its thresholds, and a model or provider change gets
  a decision in `docs/decisions/`. Every prompt has an eval set with the facets of its mode (`rag`: query,
  retrieval, answer; `assistive`: output; `agentic`: task, trajectory, safety); production failures
  become eval cases. Tests of the code around the model use recorded responses, never the live model.
  Model output is validated and treated as untrusted; content that isn't ours never widens what the
  model may do; irreversible actions need a confirmation outside the model.
- **Strict lint.** Don't add lint suppressions without a specific reason in a trailing comment. Never
  weaken the lint configs to make code pass.
- **Generated code** is never edited by hand; regenerate it (E2). <!-- ADAPT: the command -->
- **Claims match the code.** User-facing copy (marketing pages, docs, help texts) claims only what is
  built, and tests pin the claims to the code where they can.
- **Translations are written for the market, not translated.** Every non-English text reads as if a
  native copywriter for that market wrote it: idiomatic sentences, no calques of the English, no English
  list rhythm or headline structure. Keep the meaning, and every claim, exactly as in the English. Keep
  the established register and the product's terminology. <!-- ADAPT: languages, register per language,
  catalogue paths; delete this rule if the product has one language -->
- **National or customer-specific rules are never hard-coded.** Country- or customer-specific behaviour
  is configuration on a generic engine, or a module behind an interface, chosen by data, so one
  country's rules never reach another's users (E4). <!-- ADAPT: delete if irrelevant -->
<!-- ADAPT: domain rules. Examples from earlier projects:
- Tenancy: all tenant data access goes through one helper; every tenant table has row-level security and
  a test proving cross-tenant isolation.
- Money is integer minor units plus a currency code; rates are decimals. Never floats for money.
- Settings that feed calculations over time are versioned with a valid-from date; past periods are
  always calculated with the version in force then. Never mutate a version that has applied.
- Errors are wrapped with context; HTTP errors use one shape (e.g. problem+json).
-->

## Review loop
Run `/discipline:review-loop` at the end of each phase or sizeable feature, or as a periodic
sweep. It is incremental and cheap when little has changed:
- **Standing permission:** agents run the review loop on their own, without asking, at the end of each
  phase or sizeable feature, and run the full gate after it. Given by the user on <YYYY-MM-DD>.
  <!-- ADAPT: from bootstrap batch 3, question 3: for everyone, with the date and any limits (maxUnits;
  a usage stop only if asked for); or per person: "Agents run it on their own for people whose
  .agents/USER.local.md grants it; otherwise they propose a run and wait"; or "Agents propose a review
  run and wait for a go-ahead." -->
- **Who answers review questions:** <!-- ADAPT: from batch 3, question 4: e.g. "Ann (product owner)",
  or "the owner of the area, per STATUS.md". -->
- **Branches:** review on the branch before its pull request; CI runs the gate on every pull request.
  The ledger, history and trees in `.claude/review/` are committed and merge by keeping both sides.
- **Units and lenses:** `.claude/review/units.json` splits the repo into units, each with the lenses
  that apply to it. Which lenses exist at all follows from `.agents/profile.json`
  (`discipline lenses show`); after changing the profile, run `discipline lenses apply` and add
  any new lens to the units where it applies. A unit's `context` lists files outside it that also make
  a lens stale (the API contract for the contracts lens).
- **Ledger:** `.claude/review/ledger.jsonl` records the content hashes each (unit, lens) pair was
  reviewed at, so only stale pairs are reviewed, never-reviewed ones first, up to `maxUnits` per run
  (default 8).
- **Diff reviews:** a changed unit is reviewed as a diff against the tree it was last marked at
  (pinned under `refs/review/trees/`, recovered from a matching commit if lost).
- **Questions, not guesses:** where the spec, `docs/decisions/` and the proposals don't settle a
  behaviour, reviewers raise a question for the user; it is never fixed by an agent. Open ones:
  `discipline review questions`. Once answered and recorded in the spec and DECISIONS,
  close it with `discipline review answer N --reason "..."`.
- **Each run:** one read-only reviewer per unit applies every pending lens; one skeptic per unit
  verifies its findings (a refuted critical or high security or supply-chain finding gets a second,
  independent verifier); a check confirms the read-only phases changed nothing; one fixer handles all
  confirmed findings and runs lint plus the affected tests; a reviewer then checks only the fixer's
  diff. Outcomes go to `.claude/review/history.jsonl`.
- **Run the full gate yourself after the loop.**
- **No repeats:** reviewers see every earlier finding in their unit (`discipline review show <unit>`); a
  finding is rejected only with a written reason.
- **Usage guard (opt-in):** `stopAt: <weekly %>` and/or `stopAt5h: <5-hour %>` stop gracefully at
  that usage.
- **Progress:** `discipline review status`. When you add a directory, add it to a unit;
  the gate fails on uncovered files, and on units that disagree with the profile.
