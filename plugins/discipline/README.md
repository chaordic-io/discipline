# discipline (the plugin)

The Claude Code plugin for the Chaordic working method. The repository's
[README](https://github.com/chaordic-io/discipline#readme) explains the method, the workflows and how
the parts fit together; this file covers the plugin's contents and its command-line tool.

Install it from the `chaordic` marketplace:

```
/plugin marketplace add chaordic-io/discipline
/plugin install discipline@chaordic
```

or, from a terminal: `claude plugin marketplace add chaordic-io/discipline`, then
`claude plugin install discipline@chaordic`. Then run `/discipline:bootstrap` in the repository to set
up.

## Contents

| Path | What it is |
|---|---|
| `skills/bootstrap/` | `/discipline:bootstrap`: set a repository up (templates, questions, reviewers, gate). |
| `skills/upgrade/` | `/discipline:upgrade`: move a repository to a newer version. |
| `skills/working/` | `/discipline:working`: the way of working. |
| `skills/engineering/` | `/discipline:engineering`: the engineering principles E1–E10. |
| `skills/stack/` | `/discipline:stack`: choosing a stack, criteria S1–S7, with examples. |
| `workflows/review-loop.js` | `/discipline:review-loop`: the incremental review → verify → fix loop. |
| `agents/` | The eleven reviewer checklists (`discipline:security-auditor`, …) and `discipline:review-reader`, the read-only agent the loop runs them in. |
| `hooks/` | A `PreToolUse` hook that blocks writes by `discipline:review-reader`; `SessionStart` and `Stop` hooks that show a new session where to resume and ask for the work file to be updated before stopping (`DISCIPLINE_STOP_CHECK=0` turns the stop check off). |
| `bin/discipline`, `src/discipline/` | The `discipline` command (below). |
| `tests/` | The plugin's tests. |

## The `discipline` command

Standard-library Python 3.10+. Inside Claude Code, `bin/discipline` runs it straight from the plugin
with no installation (it falls back to `uv run` when there is no suitable `python3`). Elsewhere, such
as CI, run it pinned with uv:

```sh
uvx --from "git+https://github.com/chaordic-io/discipline@v0.4.1#subdirectory=plugins/discipline" discipline check
```

`discipline help` lists the commands: `init`, `check`, `review …`, `lenses …`, `spec-rules`,
`ai-evals`, `handover`, `doc <guide>`.

## Development

```sh
python3 -m unittest discover -s tests        # or: uv run --no-project python -m unittest discover -s tests
uv build                                     # wheel and sdist; the agents and skills travel inside the wheel
claude plugin validate .                     # and from the repository root, for the marketplace
```
