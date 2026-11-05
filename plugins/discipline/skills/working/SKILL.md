---
name: working
description: The way of working with coding agents - the request loop (clarify, proposal, spec first, tests, verify, review, write it down, report), the verification flow, delegation, several sessions on one repository, review-loop practice, keeping the handover files small, reporting, and lessons learned. Use at the start of sizeable work, before delegating, when verifying or reporting, when running or acting on the review loop, and at the end of a phase or session.
---
# How we work

How the agent sessions in a repository work with the user and with each other. It is generic:
project-specific facts belong in `CLAUDE.md` (rules and commands), `.agents/ENVIRONMENT.md` (machine),
`.agents/USER.md` (the user) and `.agents/WORKING.md` (this project's git policy and its own lessons).
Commands are the `discipline` CLI from the plugin; `discipline help` lists them.

## Roles

- **The user** owns the product and makes the product decisions. They read reports and answer
  questions; they don't want to babysit.
- **The main session** orchestrates: it clarifies, writes proposals and specs, delegates sizeable work,
  runs the slow suites, reviews, and reports. It may also implement directly.
- **Subagents** do bounded work from a self-contained brief and report back. Reviewer agents are
  read-only.

## The loop for each request

1. **Clarify only what is genuinely the user's call** (see "Deciding, assuming, asking"). First check
   whether it was already decided (`discipline decisions search <words>`, the spec, the proposals,
   STATUS.md); if so, apply that and cite it. Otherwise ask with concrete options and a recommendation
   (the recommended option first). Technical, reversible choices invisible to users are decided without
   asking, recorded, and mentioned in the report.
2. **Proposal for features.** A new feature starts as `docs/proposals/<NAME>.md` (template in
   `docs/proposals/TEMPLATE.md`): the request verbatim, how it serves the purpose in `docs/SPEC.md`
   section 0 (a feature that crosses a non-goal makes that the first open question), the current state
   with file references,
   options with trade-offs, the open questions with a recommended answer each, and numbered build
   steps. Statements about laws, standards or third-party behaviour cite their source and are marked
   *(verify)* until checked against the primary source. Batch the questions; build only once they are
   answered.
3. **Spec first.** Read the relevant `docs/SPEC.md` section, change the behaviour, update the spec, and
   add a decision in `docs/decisions/`: trigger, decision, alternatives turned down, spec reference.
4. **Implement with tests in the same change.** A regression test for every fix, checked to fail
   without the fix where that is possible.
5. **Verify** (next section). The gate must pass before anything is called done.
6. **Review.** After each phase or sizeable feature, run `/discipline:review-loop`, then the full gate
   once more. On a branch, review before the pull request: the loop then reviews only that branch's
   changes, and a clean merge needs no second review. A workflow spends many agents' worth of tokens,
   so it runs only with the user's opt-in: when `CLAUDE.md` ("Review loop") records a standing
   permission (for everyone, or for this person in their `.agents/USER.local.md`), run it without
   asking, within the limits recorded there; otherwise propose the run and wait for the go-ahead.
7. **Write it down as you go.** Record each user decision, design answer and backlog item the moment it
   is made, not at the end: product decisions as files in `docs/decisions/` (`discipline decisions
   new "<title>"`); this branch's continuation point in its work file (`discipline work`); the shared
   roadmap and shared open questions in `.agents/STATUS.md`; build conventions in
   the proposal's "Built" list. A decision that exists only in chat is lost on a crash or a context
   reset.
8. **Report** (see Reporting) and continue with the next item unless a decision needs the user.

## Deciding, assuming, asking

Ambiguity filled with an unspoken assumption is how a product drifts away from what its users wanted.
The defence is to keep every assumption visible until the user has confirmed or rejected it.

- **Look before asking.** Before putting a question to the user, check whether it is already answered:
  `discipline decisions search <words>` (decisions and answered review questions), the spec, the
  proposals, the open questions in `STATUS.md` and `discipline review questions`. An answer that exists
  is applied and cited (the decision's file), never asked again. If the new request conflicts with an
  earlier decision, don't ask from scratch: ask "this would change <decision>: keep it, or replace it?",
  and a replacement gets a new decision that marks the old one `Superseded by`.
- **What an agent decides, and records:** technical choices that are reversible and invisible to users
  (a library within the chosen stack, an internal name, a file layout, an index). Record each as a
  convention: in the decision's "Conventions taken during the build", or *(convention)* in a proposal.
- **What the user decides, always:** anything that changes what a user sees or can do, money, permissions
  and roles, personal or tenant data, legal or contractual behaviour, cost, external commitments
  (APIs others depend on), and anything hard to undo (data migrations, deletions, published formats).
  Also anything that crosses a non-goal or a success measure in spec section 0.
- **When the work can't wait for the answer:** go ahead on the most conservative assumption (the
  most restrictive, the easiest to undo), but never silently:
  - in the spec, mark the assumed text `(assumed <YYYY-MM-DD>, not confirmed)`; never write an
    assumption as settled text;
  - list it under "Assumptions to confirm" in the branch's work file, with the question and the options;
  - name it in the report, and ask it in the next batch of questions.

  `discipline assumptions` lists every marker, and the gate warns about them, so none is forgotten.
  When the user answers, record a decision, update the spec text, and remove the marker.
- **Behaviour nobody wrote down is an assumption too.** A default, a state, a side effect or an error
  case the spec doesn't mention, added because the code "needed" it, gets the same treatment.
- **Agents you delegate to** report every assumption they made (see Delegation); the review loop's
  fixer hands product questions back instead of deciding them.

## Verification flow

Done means verified, not written. In order of cost:

1. **Targeted checks while iterating:** the single test file or package, the linter for the part touched.
2. **The gate** (`make check` or the project's equivalent): lint with no warnings, type checks, unit and
   integration tests with coverage thresholds, property and fuzz tests, real services through
   containers, a check that generated code is current, a duplication check, vulnerability scans, and
   the review-unit coverage test (`discipline check`). The gate is the only definition
   of done.
3. **Slow suites, run by the main session after the agents finish:** the browser end-to-end suite
   against the production build, and a smoke test of the production image or deployment through the
   critical path (sign-up → core action → document → email → public link → isolation). One at a time
   when they share Docker. When the product calls models: the eval suite, on every prompt or model
   change and before a release, compared with the last recorded scores per facet; a drop below the
   thresholds is a failure like a red test.
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
unhandled errors and error logs in test output, warnings. Since only real failures are logged as
errors, an error log in a test run is a failure. Find the root cause, fix it with a regression test, report it
plainly (what failed, why, what fixed it). Never call it "unrelated" or "pre-existing", and never re-run
until green as the fix. If a test expectation was wrong, say so and correct the test, with the reasoning.

## Delegation

- **One background agent per sizeable piece of work**, with a self-contained brief (it knows nothing
  else):
  - the user's request verbatim;
  - the decisions already made, and what has been ruled out;
  - the files to start from;
  - the rules: "do NOT commit", "the gate must pass", "don't run the slow suites (I will)";
  - what to report: files changed, tests and their numbers, decisions for the user, and every
    assumption made where the brief, the spec and the decisions were silent (none may be written into
    the spec as settled; see "Deciding, assuming, asking").
- **Never let two agents edit the same area.** When the review loop runs over some units, queue work
  that touches them. Unrelated areas can run in parallel.
- **Sequence-numbered files** (migrations): take the next number at the moment the file is created,
  and have a test that enforces contiguous numbering.
- **Agents' results are claims.** Check what matters: run the gate yourself, read the diff, look at
  the screenshots.

## Several people and sessions on one repository

Several people, each with their own sessions, work on branches; several sessions may also share one
checkout (separate terminals or panes, e.g. a terminal multiplexer for agents).

- **One work file per branch:** `.agents/work/<branch>.md` (`discipline work`) holds the branch's
  continuation point and state, and in its header who works on it, its roadmap item and the
  directories it owns, so branches never overwrite each other's. `discipline work --list` shows every
  branch in flight, read from git. `.agents/STATUS.md` holds only what everyone shares: the roadmap and
  the shared open questions. (Don't list branches in a shared file: two branches adding a row conflict
  on every merge.)
- **Split by ownership:** each branch or session owns directories and never edits another's. Write the
  directories into the work file's "Owns", and check `discipline work --list` before starting.
- **Files that merge by themselves:** decisions are one file each (`docs/decisions/`; regenerate the
  index with `discipline decisions index` after a merge), and the append-only files (the review
  ledger, history and trees, `.agents/HISTORY.md`) are merged by keeping both sides
  (`.gitattributes`). Spec rule IDs are the exception: two branches can both take "the next" ID, and
  the gate fails on the duplicate; renumber one on the second branch.
- **Shared files** (`CLAUDE.md`, the Makefile, CI config, `units.json`, `.agents/STATUS.md`,
  `docs/SPEC.md`): change them only in small, separate edits, or batch the changes as a merge step.
  Re-read before editing; someone else may have changed them.
- **Review on the branch, gate on the pull request:** run the review loop on the branch before its
  pull request, put `discipline review evidence --since <the branch's start date>` in the pull
  request's description, and let CI run the gate on every pull request. The review ledger is keyed by content,
  so what was reviewed on a branch stays reviewed after a clean merge; only units whose merged content
  differs from both sides are due again.
- **Merges can break what git doesn't see.** Two branches that each pass the gate can fail together
  (one changes a shared helper's signature, the other adds callers of the old one). Before merging
  the second of two parallel branches, merge the default branch into it and run the gate there, or
  have CI run the gate on the merged result. A gate that fails after a merge is fixed first, like any
  other failure.
- **When a branch merges:** move what it did to `HISTORY.md` (a dated entry at the end), anything still
  open to `STATUS.md`, and delete its work file. On the
  default branch, the gate warns about work files left behind.
- **Questions have an owner:** review questions and product decisions go to the person `CLAUDE.md`
  names ("Review loop"), not to whoever happened to run the loop.
- **Cross-session requests** (e.g. "the sign-up page needs a terms checkbox") go as a written brief in a
  proposal, then as a short message to the other session if a channel exists, never as an edit to its
  area.
- **Concurrent gates** share Docker and CPU: don't run two heavy suites at once.

## Review-loop practice

- Status: `discipline review status`; open findings: `discipline review open`; a unit's history:
  `discipline review show <unit>`; usage: `discipline review quota`.
- A finding is rejected only with a written reason; reviewers see the history, so nothing is repeated.
- Findings left `open` by the delta limit are fixed in a follow-up, with tests, and recorded as fixed.
- New directory or package: add it to a unit in `units.json`; the gate fails on uncovered files.
- The product changed shape (a second language, a mobile client, a public API, a published package):
  update `.agents/profile.json`, run `discipline lenses apply`, add the new lens to the
  units where it applies, and record it in `docs/decisions/`. The gate fails until units and profile
  agree.
- A run that reports `questions`: add them to "Open questions for the user" in `STATUS.md` and ask
  the person who answers them (`CLAUDE.md`, "Review loop") in the next batch, each with its options
  and the recommendation. When answered: update
  `docs/SPEC.md`, add a decision in `docs/decisions/`, change the code if the answer differs from the
  current behaviour (with a test that names the rule), then `discipline review answer N --reason "..."`.
- A run that reports `strayWrites` fixed and marked nothing: look at those files with `git diff`, keep
  or revert them, and run again. A run that reports `disputed` findings sent serious findings to the
  fixer although one verifier refuted them; read the fixer's reasoning for each.
- The review loop comes with the plugin; a plugin update takes effect after `/reload-plugins` or in a
  new session. Running it is described in the plugin's `skills/bootstrap/reference/review-loop.md`.

## Keeping the handover files small

Every session reads `CLAUDE.md`, `STATUS.md`, its branch's work file and the recent part of
`HISTORY.md`, and every behaviour
reviewer and verifier looks things up in `docs/decisions/`. What grows there is paid for in every
session and every review run, and a status page that has become a log is worse at saying where things
stand. So:

- **`STATUS.md` and the work files are snapshots.** Rewrite them in place. When a roadmap item is
  merged, move it to `HISTORY.md` that day; answered questions become decisions; a follow-up not taken
  up within a phase goes onto the roadmap or is dropped with a reason. A work file is deleted when its
  branch merges.
- **`HISTORY.md` is read from the end.** A few lines per entry, with pointers, added at the end. Older
  entries move to `docs/history.md` when it passes its budget.
- **Decisions are read by search.** One file per decision in `docs/decisions/`, each with `Area` and
  `Spec`, so readers find the ones that concern them (`grep -rln "Area: <area>" docs/decisions/`); a
  replaced decision gets `Superseded by` instead of being edited. `docs/DECISIONS.md` is the generated
  index.
- **`CLAUDE.md` holds rules, not explanations.** Reasoning goes to the engineering principles (the
  project's own in `.agents/ENGINEERING.md`), history to
  `HISTORY.md`, decisions to `docs/decisions/`.
- **When:** at the end of each phase, before stopping a session (`RESUME.md`), and whenever
  `discipline review status` or the gate warns that a file is over budget (`discipline handover`
  shows the sizes; budgets can be changed per project in `units.json`, `handoverBudgets`).
- **Moving, never deleting:** trimming moves text to its archive or its proper file. Only follow-ups
  are dropped, and each with its reason.

## Reporting

- Short: what changed, test results with numbers, decisions the user still has to make, next steps.
- "Status and ETA?": one status line plus a step-by-step table with realistic estimates, updated as
  you go.
- State failures and skipped steps plainly. When something is done and verified, say so without hedging.
- When you correct yourself (a wrong number, a wrong claim), say so explicitly.
- Name files as clickable `path:line` references.

## Writing

- Docs, specs and reports in plain, concrete language: the reason ("why") with each decision.
- Translations follow the market-voice rule in `CLAUDE.md`.

## Lessons learned (avoid)

Generic lessons from earlier projects. A project's own lessons go in its `.agents/WORKING.md`; a lesson
that would hold in any project belongs here, in the plugin.

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
