# Setup reference

Read from /discipline:bootstrap when a step needs it.

## The reviewers

| Lens | Checklist (plugin agent) | Runs when |
|---|---|---|
| security | `discipline:security-auditor` | always |
| behaviour | `discipline:behaviour-reviewer` | always |
| tests | `discipline:test-coverage-reviewer` | always |
| architecture | `discipline:architecture-reviewer` | always |
| duplication | `discipline:duplication-reviewer` | always |
| simplicity | `discipline:simplicity-reviewer` | always |
| supply-chain | `discipline:supply-chain-reviewer` | always (every project has dependencies, a build or CI) |
| performance | `discipline:performance-reviewer` | performance is `critical` or `normal` |
| contracts | `discipline:contract-reviewer` | the profile lists at least one interface |
| ai | `discipline:ai-reviewer` | the profile's `ai` lists a mode (`rag`, `assistive`, `agentic`) |
| localisation | `discipline:localisation-reviewer` | the product has a user interface and more than one language |

`discipline lenses` applies these rules to `.agents/profile.json`. The profile's `overrides`
turn a lens on or off by hand, with the reason written next to it (for example, localisation ahead of
a launch in a second market). `discipline lenses apply` writes the result into `.claude/review/units.json`,
and `discipline check` fails while the two disagree, so the gate catches a profile change that was never
applied.

The checklists are generic. Each one starts by reading its lens's section of the project's
`.agents/review-context.md`, which holds the project's specifics. In the review loop they run inside the
read-only `discipline:review-reader` agent (`discipline review checklist <lens>` prints one); they can
also be called by hand as agents, e.g. "use discipline:security-auditor on the auth package".

## Designing units

`.claude/review/units.json` has four parts:

- `lenses`: the lenses the profile turns on. `discipline lenses apply` writes it; don't edit it by
  hand.
- `globalExclude`: generated code, binaries and build output. Not lockfiles: they belong to the
  dependencies unit.
- `roots`: everything that must be covered. Files under a root that no unit claims are reported as
  uncovered, and `discipline check` fails on them.
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
- **An AI unit per feature** (when `ai` lists a mode): the code that calls the model, its prompts and
  its eval sets together, reviewed with `ai`, `security`, `behaviour` and `tests`, so a prompt change
  makes the feature's review stale.
- **A dependencies unit** with the manifests, lockfiles, CI configuration and Dockerfiles, reviewed
  with `supply-chain` and `security`. A lockfile change then makes it stale, so every dependency change
  is reviewed. Reviewers read lockfiles through diffs, not line by line (`scriptCheckable` in `project.json`).
- **Context for contracts:** a unit that implements or consumes a contract lists it as context, e.g.
  `"context": {"contracts": ["api/openapi.yaml"]}`. A change to the contract then makes the contracts
  lens stale for every such unit, and only that lens. The contract itself is its own unit.
- **Infrastructure gets its own unit:** the Makefile, scripts, CI helpers.
- When you add a directory, add it to a unit. The gate fails until you do, which is the point.

## The gate

The workflow runs `fixGate` (from `project.json`) after fixing and expects the caller to run `gate` after the
loop. The gate must fail on any problem. A good model:

- lint and type checks, with no warnings allowed;
- tests with coverage thresholds, including property and fuzz tests, and real services through
  containers (never a mocked database); tests fail on error logs they did not expect (E9);
- a check that generated code is current;
- a duplication check;
- vulnerability scans, and a licence check where the stack has one (supply chain);
- when contracts are on: the committed contract and generated clients are current, a breaking-change
  check against the main branch, and contract tests that run the real server against the contract;
- when performance is `critical`: benchmarks or budgets for the hot paths the spec names;
- `discipline check`, so every file belongs to a review unit, the units follow the profile, and (when
  `specRules` is on) every rule in the spec is named by a test and no test names a rule that is gone,
  and (when `ai` lists a mode) every prompt has its eval set with the facets its mode needs.

Keep slow suites (browser end-to-end against the production build, a smoke test of the production
image, load tests, and the AI eval suite with its live model calls) as separate targets that the main
session runs after the agents finish. The eval suite also runs on every prompt or model change and
before a release, and fails below its thresholds.
The capability checklist in /discipline:stack illustrates each item with tools for Go, TypeScript,
Python, Rust and the JVM.

## The usage guard (optional)

`discipline review quota` reads `~/.claude/usage/statusline.json`, which the status-line script writes:

1. `discipline init --statusline` (it copies the plugin's status-line script to
   `~/.claude/statusline-usage.sh`).
2. In `~/.claude/settings.json`, add
   `"statusLine": {"type": "command", "command": "~/.claude/statusline-usage.sh", "refreshInterval": 300}`.

Without the snapshot, usage counts as unknown and never blocks a run.
