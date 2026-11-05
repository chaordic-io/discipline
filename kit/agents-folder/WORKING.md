# How we work

How the agent sessions in this repository work with the user and with each other. It is generic:
project-specific facts belong in `CLAUDE.md` (rules and commands), `ENVIRONMENT.md` (machine) and
`USER.md` (the user). Add a section at the bottom whenever a new lesson is learned.

## Roles

- **The user** owns the product and makes the product decisions. They read reports and answer
  questions; they don't want to babysit.
- **The main session** orchestrates: it clarifies, writes proposals and specs, delegates sizeable work,
  runs the slow suites, reviews, and reports. It may also implement directly.
- **Subagents** do bounded work from a self-contained brief and report back. Reviewer agents are
  read-only.

## The loop for each request

1. **Clarify only what is genuinely the user's call.** Ask with concrete options and a recommendation
   (the recommended option first). Anything with a conventional default, or that the code and docs can
   answer, is decided without asking and mentioned in the report.
2. **Proposal for features.** A new feature starts as `docs/proposals/<NAME>.md` (template in
   `docs/proposals/TEMPLATE.md`): the request verbatim, the current state with file references,
   options with trade-offs, the open questions with a recommended answer each, and numbered build
   steps. Statements about laws, standards or third-party behaviour cite their source and are marked
   *(verify)* until checked against the primary source. Batch the questions; build only once they are
   answered.
3. **Spec first.** Read the relevant `docs/SPEC.md` section, change the behaviour, update the spec, and
   add a `docs/DECISIONS.md` entry: trigger, decision, alternatives turned down, spec reference.
4. **Implement with tests in the same change.** A regression test for every fix, checked to fail
   without the fix where that is possible.
5. **Verify** (next section). The gate must pass before anything is called done.
6. **Review.** Run the `review-loop` workflow after each phase or sizeable feature, then the full gate
   once more.
7. **Write it down as you go.** Record each user decision, design answer and backlog item the moment it
   is made, not at the end: product decisions in `docs/DECISIONS.md`; backlog, open questions and the
   continuation point in `.agents/STATUS.md`; build conventions in the proposal's "Built" list. A
   decision that exists only in chat is lost on a crash or a context reset.
8. **Report** (see Reporting) and continue with the next item unless a decision needs the user.

## Verification flow

Done means verified, not written. In order of cost:

1. **Targeted checks while iterating:** the single test file or package, the linter for the part touched.
2. **The gate** (`make check` or the project's equivalent): lint with no warnings, type checks, unit and
   integration tests with coverage thresholds, property and fuzz tests, real services through
   containers, a check that generated code is current, a duplication check, vulnerability scans, and
   the review-unit coverage test (`scripts/review/test_review.py`). The gate is the only definition
   of done.
3. **Slow suites, run by the main session after the agents finish:** the browser end-to-end suite
   against the production build, and a smoke test of the production image or deployment through the
   critical path (sign-up → core action → document → email → public link → isolation). One at a time
   when they share Docker.
4. **Visual check for UI work:** screenshots at phone, tablet and desktop widths (and dark mode),
   looked at, not just generated. Check that nothing scrolls sideways.
5. **Claims tests:** where copy makes statements about the product (marketing site, docs, legal texts),
   tests read the product's source and fail when a claim stops being true. Copy claimed ahead of a build
   is recorded as such and re-checked before launch.
6. **Conformance evidence for rules:** rule engines (compliance, tax, payment formats) get case files
   that cite the source of each expected result, run as tests, with generated evidence documents.
7. **The review loop** (below): independent read-only reviewers with a skeptic pass.
8. **Verify agents' claims** that matter (legal citations, standards, prices, external behaviour)
   against primary sources before relying on them.

**Every failure is investigated**, whether this change caused it or not: red gates, flaky tests,
unhandled errors in test output, warnings. Find the root cause, fix it with a regression test, report it
plainly (what failed, why, what fixed it). Never call it "unrelated" or "pre-existing", and never re-run
until green as the fix. If a test expectation was wrong, say so and correct the test, with the reasoning.

## Delegation

- **One background agent per sizeable piece of work**, with a self-contained brief (it knows nothing
  else):
  - the user's request verbatim;
  - the decisions already made, and what has been ruled out;
  - the files to start from;
  - the rules: "do NOT commit", "the gate must pass", "don't run the slow suites (I will)";
  - what to report: files changed, tests and their numbers, decisions for the user.
- **Never let two agents edit the same area.** When the review loop runs over some units, queue work
  that touches them. Unrelated areas can run in parallel.
- **Sequence-numbered files** (migrations): take the next number at the moment the file is created,
  and have a test that enforces contiguous numbering.
- **Agents' results are claims.** Check what matters: run the gate yourself, read the diff, look at
  the screenshots.

## Several sessions on one repository

When more than one interactive session works on the repo at once (separate terminals or panes, e.g. a
terminal multiplexer for agents):

- **Split by ownership:** each session owns directories (e.g. one the app, one the marketing site) and
  never edits the other's. Write the split into `STATUS.md`.
- **Shared files** (`CLAUDE.md`, the Makefile, CI config, `units.json`, `.agents/STATUS.md`,
  `docs/DECISIONS.md`): change them only in small, separate edits, or batch the changes as a merge step
  done when the other session is idle. Re-read before editing; the other session may have changed them.
- **Cross-session requests** (e.g. "the sign-up page needs a terms checkbox") go as a written brief in a
  proposal, then as a short message to the other session if a channel exists, never as an edit to its
  area.
- **Concurrent gates** share Docker and CPU: don't run two heavy suites at once.

## Review-loop practice

- Status: `python3 scripts/review/review.py status`; open findings: `review.py open`; a unit's history:
  `review.py show <unit>`; usage: `review.py quota`.
- A finding is rejected only with a written reason; reviewers see the history, so nothing is repeated.
- Findings left `open` by the delta limit are fixed in a follow-up, with tests, and recorded as fixed.
- New directory or package: add it to a unit in `units.json`; the gate fails on uncovered files.
- Saved workflows load at session start. After editing `.claude/workflows/review-loop.js`, run it by
  its script path until the next session, or the old version runs.

## Reporting

- Short: what changed, test results with numbers, decisions the user still has to make, next steps.
- "Status and ETA?": one status line plus a step-by-step table with realistic estimates, updated as
  you go.
- State failures and skipped steps plainly. When something is done and verified, say so without hedging.
- When you correct yourself (a wrong number, a wrong claim), say so explicitly.
- Name files as clickable `path:line` references.

## Git

- By default the user commits, branches and pushes; agents leave work uncommitted, gated and described
  in `STATUS.md`, and say when nothing is running so the user can commit. <!-- ADAPT: confirm with the
  user; delete if agents may commit -->

## Writing

- Docs, specs and reports in plain, concrete language: the reason ("why") with each decision.
- Translations follow the market-voice rule in `CLAUDE.md`.

## Lessons learned (avoid)

Generic lessons from earlier projects; add this project's own below them.

- Browser tests written against assumptions (an old default view, old columns) rather than the current
  UI. Read the component first.
- Timing-sensitive UI tests under coverage instrumentation: use a generous global wait timeout; a test
  that waits on purpose passes its own short timeout.
- Hand-patched generated code. Always regenerate.
- Two consumers deriving the same concept separately and drifting apart. Define it once (one SQL
  function, one helper) and reuse it.
- Tests that count rows globally while fixtures add rows of their own (e.g. a default project every
  member gets). Count within the scope the test controls.
- Property tests that fail once in thousands of runs are real bugs (range cutting, rounding, third-party
  decoders); keep the failing seed as a golden case.
- Hard-coded values in tests that duplicate configuration (old prices, limits): derive them from the
  configuration so the test cannot go stale.
- Agent sandboxes that cannot reach ports published by test containers: run the suite inside a runner
  container on the same Docker network instead of mocking.
