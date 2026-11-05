# Resuming a session

Start a new session, on your branch, with this prompt:

```
Read .agents/README.md, then follow the continuation point in this branch's work file (discipline work).
```

`CLAUDE.md` already tells every session to read `.agents/README.md` first, so "continue where we left
off" also works.

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
