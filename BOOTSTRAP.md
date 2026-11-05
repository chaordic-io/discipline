# Bootstrap: our way of working with coding agents, for any repository

This folder is self-contained. Copy it into a new repository (as `.agents/bootstrap/` or anywhere) and
an agent can set up the whole working method from it, with no access to the repository it came from:

- **Instructions** for every session (`CLAUDE.md`) and a **handover folder** (`.agents/`) so a new or
  restarted session recovers the context: status, the user's preferences, how we work, the environment.
- **A project profile** (`.agents/profile.json`): what kind of product this is. It decides which
  reviewers run, so a one-language product gets no localisation review and a product without an
  interface to other parts gets no contract review.
- **A deterministic gate** (`make check` or the stack's equivalent): the only definition of done.
- **A verification flow** beyond the gate: slow suites, visual checks, claims tests, conformance
  evidence, independent reviewers, and the rule that every failure is investigated.
- **Read-only reviewer agents**, one checklist per lens: security, behaviour (does the code do what the
  spec and the recorded decisions say), tests, architecture, duplication, performance, supply chain,
  contracts (API drift) and localisation. Where the written intent doesn't settle a behaviour, the
  reviewers ask the user instead of guessing.
- **Spec rules pinned by tests** (optional): each business rule in the spec has an ID, and the gate
  fails on a rule that no test names.
- **An incremental review loop** (a Claude Code workflow): stale code is reviewed, skeptics verify the
  findings, one fixer fixes them, only the fix is re-reviewed, and a ledger records it all. Unchanged
  code is never reviewed twice, and rejected findings stay rejected.
- **A decision log, a spec and a proposal template**, so every change has a recorded reason.
- **An optional usage guard** that stops the review loop at a weekly or 5-hour usage percentage.

Requirements: Python 3.10+ and git. Everything else depends on the stack you choose.

## What is in the kit

| Path | Becomes | What it is |
|---|---|---|
| `kit/CLAUDE.template.md` | `CLAUDE.md` | Repo rules, commands, the review loop. Fill in the `ADAPT` parts. |
| `kit/agents-folder/` | `.agents/` | Handover folder: `README`, `STATUS`, `USER`, `WORKING`, `ENVIRONMENT`, `HISTORY`, `RESUME`, and `profile.json` (the project profile). `WORKING.md` is the full description of how we work. |
| `kit/claude/agents/` | `.claude/agents/` | The nine read-only reviewer checklists (see "The reviewers"), and `review-reader.md`, the tool-restricted agent type the review loop runs them in. |
| `kit/claude/workflows/review-loop.js` | `.claude/workflows/review-loop.js` | The review loop. Only its `PROJECT` block is project-specific. |
| `kit/scripts/review/` | `scripts/review/` | `review.py` (ledger, units, diffs, usage, questions), `lenses.py` (profile → lenses), `spec_rules.py` (spec rules ↔ tests), `test_review.py` (their tests, including "every file belongs to a unit", "the units follow the profile" and "every spec rule is pinned"), `units.json` (example units). |
| `kit/docs/` | `docs/` | `SPEC.md` skeleton, `DECISIONS.md` with the entry format, `proposals/TEMPLATE.md`. |
| `kit/home/statusline-usage.sh` | `~/.claude/statusline-usage.sh` | Optional, for the usage guard. |
| `stacks/` | (reference) | Our [default suggestion for web apps](stacks/recommended-webapp.md) (app and marketing site, library by purpose); worked examples ([Go + React + Postgres](stacks/go-react-postgres.md), [Astro on Cloudflare Pages](stacks/astro-cloudflare-pages.md)) and a capability table for other stacks ([stacks/README.md](stacks/README.md)). |
| `install.py` | (tool) | Copies the kit into place; never overwrites; lists what still needs adapting. |
| `selfcheck.py` | (tool) | Proves the kit works on its own (installs it into an empty git repository and runs its tests there). |

The kit stores `CLAUDE.md` and `.claude/` under neutral names so they don't act as instructions while
the kit itself is being edited; `install.py` puts them in place.

## The reviewers

| Lens | Checklist | Runs when |
|---|---|---|
| security | `kit/claude/agents/security-auditor.md` | always |
| behaviour | `kit/claude/agents/behaviour-reviewer.md` | always |
| tests | `kit/claude/agents/test-coverage-reviewer.md` | always |
| architecture | `kit/claude/agents/architecture-reviewer.md` | always |
| duplication | `kit/claude/agents/duplication-reviewer.md` | always |
| supply-chain | `kit/claude/agents/supply-chain-reviewer.md` | always (every project has dependencies, a build or CI) |
| performance | `kit/claude/agents/performance-reviewer.md` | performance is `critical` or `normal` |
| contracts | `kit/claude/agents/contract-reviewer.md` | the profile lists at least one interface |
| localisation | `kit/claude/agents/localisation-reviewer.md` | the product has a user interface and more than one language |

`scripts/review/lenses.py` applies these rules to `.agents/profile.json`. The profile's `overrides`
turn a lens on or off by hand, with the reason written next to it (for example, localisation ahead of
a launch in a second market). `lenses.py apply` writes the result into `scripts/review/units.json`,
and `test_review.py` fails while the two disagree, so the gate catches a profile change that was never
applied.

## Set up a repository

Give a new agent session this prompt in the target repository:

```
Read .agents/bootstrap/BOOTSTRAP.md and set up this repository with it, following "Set up a repository".
```

The agent works through these steps. It asks the user only in steps 3, 5 and 6, each time as one
batch of questions with a recommended answer for each, and it decides everything else itself.

1. **Check the kit:** `python3 .agents/bootstrap/selfcheck.py`. It must pass.
2. **Install:** `python3 .agents/bootstrap/install.py --dry-run`, then without `--dry-run`. Existing
   files are kept and listed; merge them by hand with the kit's versions.
3. **Ask the product questions** ("Bootstrap questions", batch 1). Look at the repository first: if
   code exists, propose the answers it implies and ask the user to confirm or correct them.
4. **Choose the reviewers:** write the answers into `.agents/profile.json`, run
   `python3 scripts/review/lenses.py apply`, and show the user its output (each lens, on or off, and
   why). Change the profile until the user agrees.
5. **Ask the stack questions** (batch 2). The recommendations depend on batch 1.
6. **Ask the working questions** (batch 3).
7. **Fill in the texts:** every file `install.py` listed as still to adapt. In `CLAUDE.md`: the
   product, the layout, the commands, the domain rules; delete the rules that don't apply (the
   translation rule when localisation is off, the national-rules rule for a product with one market).
   In `.agents/USER.md`: the user and their preferences, in their words. In `.agents/ENVIRONMENT.md`:
   what you know about the machine.
8. **Reviewer checklists:** fill the `ADAPT` comments in the checklists of the lenses that are on
   (layering, isolation model, test tools, expected sizes, package ecosystems, contracts, catalogues).
   Delete the checklists of the lenses that are off, or keep them for later; `lenses.py apply` lists
   them.
9. **Review units:** replace the example units in `scripts/review/units.json` (see "Designing units").
10. **The workflow:** fill the `PROJECT` block in `.claude/workflows/review-loop.js` (the stack
    examples show a complete one). The workflow takes its lenses from `units.json`; there is no lens
    list to keep in sync.
11. **The gate:** create the gate command for the stack (see "The gate") and make it run
    `python3 -m unittest discover -s scripts/review -q`. Run it until it passes.
12. **Optional usage guard:** `python3 .agents/bootstrap/install.py --statusline`, then the settings
    change in "The usage guard".
13. **Record:** a first `docs/DECISIONS.md` entry ("Working method set up from the bootstrap kit") with
    the profile, the lenses that are on and off and why, and the stack with the reasons for it; the
    continuation point and roadmap in `.agents/STATUS.md`.
14. **First review:** with the user's go-ahead, run the `review-loop` workflow (workflows run only when
    the user opts in), then the gate.

## Bootstrap questions

Ask each batch in one go. Give every question concrete options and a recommendation (the recommended
option first), and say what the answer will change. Skip a question the repository already answers,
and say what you found instead.

### Batch 1: the product (decides the reviewers)

| # | Question | Goes into | Recommendation |
|---|---|---|---|
| 1 | What is the product, and who is it for? | `profile.product`, `CLAUDE.md`, `docs/SPEC.md` | (free text) |
| 2 | What kind of product is it? Several may apply: `web-app`, `mobile-app`, `desktop-app`, `internal-tool`, `static-site`, `public-api`, `backend-service`, `library`, `cli`, `data-pipeline`. | `profile.kinds` | From the description and the code. |
| 3 | Which languages do its users read, at launch and within the next year? | `profile.languages` | One language unless a market needs another at launch. Adding one later is a profile change and one command. |
| 4 | Which interfaces does a separately built or released part depend on? Several may apply: `frontend-backend`, `mobile-backend`, `public-api`, `service-to-service`, `published-library`, or none. | `profile.interfaces` | From the kinds: a web app with its own API → `frontend-backend`; a mobile app → `mobile-backend`; an API for third parties → `public-api`; several services → `service-to-service`; a published package → `published-library`; a static site or a CLI → none. |
| 5 | How much does performance matter? `critical` (budgets are part of the product), `normal` (must stay fast at expected sizes), `minor` (small data, few users). | `profile.performance` | `normal` for apps, services and pipelines; `minor` for static sites, CLIs and small internal tools. |
| 6 | What sensitive data does it hold? Personal data, payments, health data, several tenants' data, or none. | `profile.data`, the security checklist, `CLAUDE.md` domain rules | (from the description) |
| 7 | Does the spec carry business rules worth pinning to tests by ID (calculations, permissions, lifecycles, legal rules)? If so, which files are tests? | `profile.specRules` | Yes for apps with business rules: `{"tests": [<the test file globs>]}`. No (`null`) for content sites, CLIs and thin wrappers. |
| 8 | Should any reviewer be on or off against the rules above, and why? | `profile.overrides` | No overrides. |

### Batch 2: the stack (decides the gate and the tools)

| # | Question | Goes into | Recommendation |
|---|---|---|---|
| 1 | Is there code already? If so, the stack is what is there: confirm it, and ask only about the gaps. | `CLAUDE.md` layout | (from the repository) |
| 2 | Which languages and frameworks? | `CLAUDE.md`, the gate, `PROJECT` | A new business web app: [`stacks/recommended-webapp.md`](stacks/recommended-webapp.md). Otherwise what the team knows best, checked against the capability table in [`stacks/README.md`](stacks/README.md). |
| 3 | Which data stores and external services (database, queue, mail, object storage, third-party APIs)? | real-service tests, `ENVIRONMENT.md` | Each one runs as a container in tests (testcontainers or the stack's equivalent), never mocked. |
| 4 | Only if contracts are on: how is each contract written (OpenAPI, protobuf, GraphQL, JSON Schema, a library's exports), which way does generation go (contract from code, or code from contract), and which consumers stay on old versions? | the contract checklist, `units.json` context, the gate | Generate the contract from the code and the clients from the contract, and commit both; a breaking-change check against the main branch in the gate. |
| 5 | Which package ecosystems, which CI system, and how is it shipped (container images, app stores, a package registry, static hosting)? | the supply-chain checklist, the dependencies unit, the gate | Lockfiles committed; CI installs from them; CI actions and base images pinned by digest. |
| 6 | Where are tool versions pinned, and what is the gate command called? | `ENVIRONMENT.md`, `CLAUDE.md`, `PROJECT.gate` | One version file for every tool (e.g. `mise.toml`), used by CI too; `make check`. |

### Batch 3: how we work

| # | Question | Goes into | Recommendation |
|---|---|---|---|
| 1 | May agents commit, branch or push? | `.agents/USER.md`, `.agents/WORKING.md` "Git" | No: the user commits (the kit's default). |
| 2 | Which standing preferences in `.agents/USER.md` apply? They come from earlier projects. | `.agents/USER.md` | Read them out and keep the ones the user confirms, in their words. |

### When the product changes

A second language, a mobile client, a public API: edit `.agents/profile.json`, run
`python3 scripts/review/lenses.py apply`, add the newly enabled lens to the units where it applies,
fill that checklist's `ADAPT` comments (copy the checklist from the kit if it was deleted), and add a
`docs/DECISIONS.md` entry. Until then the gate fails, which is the point.

## Designing units

`scripts/review/units.json` has four parts:

- `lenses`: maps each lens name to its checklist file. `lenses.py apply` writes it; don't edit it by
  hand.
- `globalExclude`: generated code, binaries and build output. Not lockfiles: they belong to the
  dependencies unit.
- `roots`: everything that must be covered. Files under a root that no unit claims are reported as
  uncovered, and `test_review.py` fails on them.
- `units`: each has an `id`, `include` and optional `exclude` globs, `lenses`, and an optional
  `context`.

Guidelines:

- **One unit per feature or package**, small enough (roughly 10–40 files) that one reviewer can read
  all of it, tests included.
- **Order is priority:** never-reviewed units go first, in file order. Put the security-sensitive
  ones (authentication, tenancy, the data layer) at the top.
- **Lenses only where they apply:** behaviour on every unit with business logic (domain, services,
  handlers, UI that applies rules), not on pure infrastructure; no localisation on pure domain code; no security on pure UI
  components without input handling; performance where there are queries, hot paths or a client to
  load; contracts on the units that implement or consume an interface, and on the contract itself.
- **A dependencies unit** with the manifests, lockfiles, CI configuration and Dockerfiles, reviewed
  with `supply-chain` and `security`. A lockfile change then makes it stale, so every dependency change
  is reviewed. Reviewers read lockfiles through diffs, not line by line (`PROJECT.scriptCheckable`).
- **Context for contracts:** a unit that implements or consumes a contract lists it as context, e.g.
  `"context": {"contracts": ["api/openapi.yaml"]}`. A change to the contract then makes the contracts
  lens stale for every such unit, and only that lens. The contract itself is its own unit.
- **Infrastructure gets its own unit:** the Makefile, scripts and the workflow.
- When you add a directory, add it to a unit. The gate fails until you do, which is the point.

## The gate

The workflow runs `PROJECT.fixGate` after fixing and expects the caller to run `PROJECT.gate` after the
loop. The gate must fail on any problem. A good model:

- lint and type checks, with no warnings allowed;
- tests with coverage thresholds, including property and fuzz tests, and real services through
  containers (never a mocked database);
- a check that generated code is current;
- a duplication check;
- vulnerability scans, and a licence check where the stack has one (supply chain);
- when contracts are on: the committed contract and generated clients are current, a breaking-change
  check against the main branch, and contract tests that run the real server against the contract;
- when performance is `critical`: benchmarks or budgets for the hot paths the spec names;
- `test_review.py`, so every file belongs to a review unit, the units follow the profile, and (when
  `specRules` is on) every rule in the spec is named by a test and no test names a rule that is gone.

Keep slow suites (browser end-to-end against the production build, a smoke test of the production
image, load tests) as separate targets that the main session runs after the agents finish.
`stacks/README.md` maps each item to tools for Go, TypeScript, Python, Rust and the JVM.

## Running the review loop

- **In Claude Code,** ask for the saved workflow `review-loop`, with arguments such as
  `{ "maxUnits": 4 }`, `{ "units": ["auth"] }` or `{ "maxUnits": 26, "stopAt": 80, "stopAt5h": 90 }`.
  Say "run the review-loop workflow"; workflows only run when the user opts in.
- **What a run does:** reviewers and verifiers run as the `review-reader` agent type, which cannot
  edit files. Before fixing, `review.py touched` checks that they changed nothing in the reviewed
  units; if they did, the run fixes and marks nothing and lists the files. A critical or high security
  or supply-chain finding that the verifier refutes goes to a second, independent verifier; if the two
  disagree, the fixer gets it. The run's result lists these as `disputed`.
- **Questions:** where `docs/SPEC.md`, `docs/DECISIONS.md` and the proposals don't settle a behaviour
  (or contradict each other), reviewers report a question with options and a recommendation instead
  of a defect. A verifier checks that the documents really don't answer it; the fixer never sees it.
  The run's result lists them as `questions`, and `review.py questions` lists every open one. Ask the
  user (in one batch), write the answer into the spec and `docs/DECISIONS.md`, then close it with
  `review.py answer N --reason "<the answer; where it is recorded>"`. Reviewers see answered questions,
  so they are not asked again.
- **Progress:** `python3 scripts/review/review.py status`, a units × lenses matrix of ok, stale and never.
- **Open findings:** `review.py open`. The next run fixes the confirmed ones first and verifies the
  others again.
- **A unit's history:** `review.py show <unit>`.
- **State:** `.claude/review/` (`ledger.json`, `history.jsonl`, `trees.json`, `run.json`). Commit it so
  the review state is shared; reviewed trees are pinned under `refs/review/trees/`.

## The usage guard (optional)

`review.py quota` reads `~/.claude/usage/statusline.json`, which the status-line script writes:

1. `python3 .agents/bootstrap/install.py --statusline` (or copy `kit/home/statusline-usage.sh` to
   `~/.claude/statusline-usage.sh` and make it executable).
2. In `~/.claude/settings.json`, add
   `"statusLine": {"type": "command", "command": "~/.claude/statusline-usage.sh", "refreshInterval": 300}`.

Without the snapshot, usage counts as unknown and never blocks a run.

## How we work (summary)

The full text is `kit/agents-folder/WORKING.md` (installed as `.agents/WORKING.md`):

1. Clarify only real product decisions, with options and a recommendation; features start as a proposal.
2. Spec first; implement with tests in the same change; record the decision when it is made.
3. Verify: targeted checks, the gate, slow suites, screenshots, claims tests, conformance evidence,
   the review loop. Every failure is investigated to its root cause.
4. Delegate sizeable work with a self-contained brief; never let two agents edit the same area; split
   ownership and batch shared-file edits when several sessions share the repository.
5. Report briefly with numbers, decisions needed and next steps; keep `.agents/STATUS.md` current.

## Maintaining the kit

The kit is the master copy of `review.py`, `lenses.py`, `test_review.py` and the workflow (outside its
`PROJECT` block). Change them here, run `python3 selfcheck.py`, then copy them into the repositories
that use the kit. Inside such a repository (the kit at `.agents/bootstrap/`), `selfcheck.py` fails
while the installed copies differ from the kit's. When a project improves its copy, bring the change
back here first. When a lesson is learned that applies beyond one project, add it to
`kit/agents-folder/WORKING.md`, and new reviewer rules to `kit/claude/agents/`. A new lens needs a
checklist, an entry in `CATALOGUE` and a rule in `decide` (both in `kit/scripts/review/lenses.py`),
tests for the rule, and a row in "The reviewers".
