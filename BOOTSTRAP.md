# Bootstrap: our way of working with coding agents, for any repository

This folder is self-contained. Copy it into a new repository (as `.agents/bootstrap/` or anywhere) and
an agent can set up the whole working method from it, with no access to the repository it came from:

- **Instructions** for every session (`CLAUDE.md`) and a **handover folder** (`.agents/`) so a new or
  restarted session recovers the context: status, the user's preferences, how we work, the environment.
- **A deterministic gate** (`make check` or the stack's equivalent): the only definition of done.
- **A verification flow** beyond the gate: slow suites, visual checks, claims tests, conformance
  evidence, independent reviewers, and the rule that every failure is investigated.
- **Read-only reviewer agents**, one checklist per lens: security, tests, architecture, duplication,
  localisation.
- **An incremental review loop** (a Claude Code workflow): stale code is reviewed, skeptics verify the
  findings, one fixer fixes them, only the fix is re-reviewed, and a ledger records it all. Unchanged
  code is never reviewed twice, and rejected findings stay rejected.
- **A decision log, a spec and a proposal template**, so every change has a recorded reason.
- **An optional usage guard** that stops the review loop at a weekly usage percentage.

Requirements: Python 3.10+ and git. Everything else depends on the stack you choose.

## What is in the kit

| Path | Becomes | What it is |
|---|---|---|
| `kit/CLAUDE.template.md` | `CLAUDE.md` | Repo rules, commands, the review loop. Fill in the `ADAPT` parts. |
| `kit/agents-folder/` | `.agents/` | Handover folder: `README`, `STATUS`, `USER`, `WORKING`, `ENVIRONMENT`, `HISTORY`, `RESUME`. `WORKING.md` is the full description of how we work. |
| `kit/claude/agents/` | `.claude/agents/` | The five read-only reviewer checklists. |
| `kit/claude/workflows/review-loop.js` | `.claude/workflows/review-loop.js` | The review loop. Only its `PROJECT` block is project-specific. |
| `kit/scripts/review/` | `scripts/review/` | `review.py` (ledger, units, diffs, usage), `test_review.py` (its tests, including "every file belongs to a unit"), `units.json` (example units). |
| `kit/docs/` | `docs/` | `SPEC.md` skeleton, `DECISIONS.md` with the entry format, `proposals/TEMPLATE.md`. |
| `kit/home/statusline-usage.sh` | `~/.claude/statusline-usage.sh` | Optional, for the usage guard. |
| `stacks/` | (reference) | Our [default suggestion for web apps](stacks/recommended-webapp.md) (app and marketing site, library by purpose); worked examples ([Go + React + Postgres](stacks/go-react-postgres.md), [Astro on Cloudflare Pages](stacks/astro-cloudflare-pages.md)) and a capability table for other stacks ([stacks/README.md](stacks/README.md)). |
| `install.py` | (tool) | Copies the kit into place; never overwrites; lists what still needs adapting. |
| `selfcheck.py` | (tool) | Proves the kit works on its own (installs it into an empty git repository and runs its tests there). |

The kit stores `CLAUDE.md` and `.claude/` under neutral names so they don't act as instructions while
the kit itself is being edited; `install.py` puts them in place.

## Set up a repository

Give a new agent session this prompt in the target repository:

```
Read .agents/bootstrap/BOOTSTRAP.md and set up this repository with it, following "Set up a repository".
```

The agent then works through these steps, asking the user only where marked.

1. **Check the kit:** `python3 .agents/bootstrap/selfcheck.py`. It must pass.
2. **Install:** `python3 .agents/bootstrap/install.py --dry-run`, then without `--dry-run`. Existing
   files are kept and listed; merge them by hand with the kit's versions.
3. **Ask the user** (in one batch, each with a recommendation):
   - what the product is, who it is for, which markets and languages;
   - the stack: if nothing exists yet and the product is a web app, suggest
     `stacks/recommended-webapp.md`; otherwise choose with the user, using the capability table in
     `stacks/README.md`;
   - whether agents may commit (the default in `USER.md` is: the user commits);
   - which standing preferences in `.agents/USER.md` apply (they come from earlier projects).
4. **Fill in the texts:** every file `install.py` listed as still to adapt. In `CLAUDE.md`: the
   product, the layout, the commands, the domain rules; delete the rules that don't apply (e.g.
   translations for a one-language product). In `.agents/USER.md`: the user and their preferences, in
   their words. In `.agents/ENVIRONMENT.md`: what you know about the machine.
5. **Reviewer checklists:** fill the `ADAPT` comments in `.claude/agents/*.md` (layering, isolation
   model, test tools, catalogues). Drop a lens that can't apply (e.g. localisation) from the checklists,
   `units.json` and `LENS_FILE` in the workflow.
6. **Review units:** replace the example units in `scripts/review/units.json` (see "Designing units").
7. **The workflow:** fill the `PROJECT` block in `.claude/workflows/review-loop.js` (the stack examples
   show a complete one). Keep `LENS_FILE` equal to `lenses` in `units.json`.
8. **The gate:** create the gate command for the stack (see "The gate") and make it run
   `python3 -m unittest discover -s scripts/review -q`. Run it until it passes.
9. **Optional usage guard:** `python3 .agents/bootstrap/install.py --statusline`, then the settings
   change in "The usage guard".
10. **Record:** a first `docs/DECISIONS.md` entry ("Working method set up from the bootstrap kit"), and
    the continuation point and roadmap in `.agents/STATUS.md`.
11. **First review:** with the user's go-ahead, run the `review-loop` workflow (workflows run only when
    the user opts in), then the gate.

## Designing units

`scripts/review/units.json` has four parts:

- `lenses`: maps each lens name to its checklist file.
- `globalExclude`: generated code, lockfiles, binaries and build output.
- `roots`: everything that must be covered. Files under a root that no unit claims are reported as
  uncovered, and `test_review.py` fails on them.
- `units`: each has an `id`, `include` and optional `exclude` globs, and `lenses`.

Guidelines:

- **One unit per feature or package**, small enough (roughly 10–40 files) that one reviewer can read
  all of it, tests included.
- **Order is priority:** never-reviewed units go first, in file order. Put the security-sensitive
  ones (authentication, tenancy, the data layer) at the top.
- **Lenses only where they apply:** no localisation on pure domain code; no security on pure UI
  components without input handling.
- **Infrastructure gets its own unit:** CI, Dockerfiles, the Makefile, scripts and the workflow.
- When you add a directory, add it to a unit. The gate fails until you do, which is the point.

## The gate

The workflow runs `PROJECT.fixGate` after fixing and expects the caller to run `PROJECT.gate` after the
loop. The gate must fail on any problem. A good model:

- lint and type checks, with no warnings allowed;
- tests with coverage thresholds, including property and fuzz tests, and real services through
  containers (never a mocked database);
- a check that generated code is current;
- a duplication check;
- vulnerability scans;
- `test_review.py`, so every file belongs to a review unit.

Keep slow suites (browser end-to-end against the production build, a smoke test of the production
image) as separate targets that the main session runs after the agents finish.
`stacks/README.md` maps each item to tools for Go, TypeScript, Python, Rust and the JVM.

## Running the review loop

- **In Claude Code,** ask for the saved workflow `review-loop`, with arguments such as
  `{ "maxUnits": 4 }`, `{ "units": ["auth"] }` or `{ "maxUnits": 26, "stopAt": 80 }`. Say "run the
  review-loop workflow"; workflows only run when the user opts in.
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

The kit's `review.py`, `test_review.py` and the workflow (outside its `PROJECT` block) are copies of the
live files in the repository the kit lives in. After changing the live files, copy them back into
`kit/` and run `python3 selfcheck.py`: inside such a repository it fails while the copies differ. When
a lesson is learned that applies beyond one project, add it to `kit/agents-folder/WORKING.md`, and new
reviewer rules to `kit/claude/agents/`.
