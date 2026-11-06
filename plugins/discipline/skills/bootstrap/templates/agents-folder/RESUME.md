# Resuming a session

Start a new session, on your branch, with this prompt:

```
Read .agents/README.md, then follow the continuation point in this branch's work file (discipline work).
```

`CLAUDE.md` already tells every session to read `.agents/README.md` first, so "continue where we left
off" also works. With the discipline plugin enabled, a new session is shown the continuation point
anyway, with the step that was in progress if the last session stopped in the middle of one, and the
files changed after the work file was last written.

**After a crash:** if the work file shows a step "In progress", the last session stopped in the middle
of it. Check the files it names (`git status`, `git diff`) for half-done edits, finish or undo them, run
the gate, then update the work file before going on.

Before stopping a session, check that:

- the branch's work file (`discipline work`) has a current continuation point and is a snapshot,
  with its header (who, roadmap item, what it owns) filled in; shared changes (the roadmap, shared
  questions) are in `STATUS.md`;
- every decision of the session is a file in `docs/decisions/` with its `Area` and `Spec`, any decision
  it replaces is marked `Superseded by`, and the index is current (`discipline decisions index`);
- `discipline handover` shows nothing over budget, or the user has been told what needs trimming;
- the user knows what is uncommitted.

When a branch is merged: move what it did to `HISTORY.md` (a dated entry at the end), anything still
open to `STATUS.md`, and delete its work file.
