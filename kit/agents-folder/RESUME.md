# Resuming a session

Start a new session with this prompt:

```
Read .agents/README.md and follow the continuation point in .agents/STATUS.md.
```

`CLAUDE.md` already tells every session to read `.agents/README.md` first, so "continue where we left
off" also works; the prompt above goes straight to the continuation point.

Before stopping a session, check that:

- `STATUS.md` has a current continuation point, and is a snapshot: the session's finished items have
  moved to `HISTORY.md`;
- every decision of the session is in `docs/DECISIONS.md`, with its `Area` and `Spec`, and any entry it
  replaces is marked `Superseded by`;
- `python3 scripts/review/handover.py` shows nothing over budget, or the user has been told what needs
  trimming;
- the user knows what is uncommitted.
