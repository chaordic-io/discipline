# Running the review loop

- **In Claude Code,** run `/discipline:review-loop`, with arguments such as `{ "maxUnits": 4 }`,
  `{ "units": ["auth"] }` or `{ "maxUnits": 26 }`. To keep capacity for other work, add a usage stop for
  that run: `{ "stopAt": <weekly %> }` and/or `{ "stopAt5h": <5-hour %> }` (needs the usage guard). Workflows only run
  when the user opts in.
- **What a run does:** reviewers and verifiers run as the `discipline:review-reader` agent type, which has
  no editing tools, and the plugin's hook blocks any write it attempts, through Bash included. Before fixing, `discipline review touched` checks that they changed nothing in the reviewed
  units; if they did, the run fixes and marks nothing and lists the files. A critical or high security
  or supply-chain finding that the verifier refutes goes to a second, independent verifier; if the two
  disagree, the fixer gets it. The run's result lists these as `disputed`.
- **Questions:** where `docs/SPEC.md`, `docs/decisions/` and the proposals don't settle a behaviour
  (or contradict each other), reviewers report a question with options and a recommendation instead
  of a defect. A verifier checks that the documents really don't answer it; the fixer never sees it.
  The run's result lists them as `questions`, and `discipline review questions` lists every open one. Ask the
  user (in one batch), write the answer into the spec and `docs/decisions/`, then close it with
  `discipline review answer N --reason "<the answer; where it is recorded>"`. Reviewers see answered questions,
  so they are not asked again.
- **Progress:** `discipline review status`, a units × lenses matrix of ok, stale and never.
- **Evidence:** `discipline review evidence [--since <date>]`: coverage with dates, and every finding
  with its scenario, fix, verifier's reasoning and the snapshot it was reviewed at, as Markdown for a
  pull request or an audit.
- **Open findings:** `discipline review open`. The next run fixes the confirmed ones first and verifies the
  others again.
- **A unit's history:** `discipline review show <unit>`.
- **State:** `.claude/review/`: commit `ledger.jsonl`, `history.jsonl` and `trees.jsonl` so the review
  state is shared (they are append-only and merge across branches by keeping both sides); `run.json`, `snapshot.index` and `outcomes.tmp.json` are per-run scratch files, kept
  out of git by the `.gitignore` lines `discipline init` adds. Reviewed trees are pinned locally under
  `refs/review/trees/`; another clone recovers its diff bases from the commits.
