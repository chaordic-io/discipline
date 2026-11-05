# .agents: handover for a new agent session

This folder lets an agent session recover its context after a restart. Everything an agent needs
that isn't already in the code, `CLAUDE.md` or `docs/` is here. The agent's own memory directory
(e.g. `~/.claude/...`) lives outside the repo and may not survive a VM or container rebuild, so
anything worth keeping is written here.

**Resuming?** [`RESUME.md`](RESUME.md) has the prompt to start with.

Read in this order:

1. [`STATUS.md`](STATUS.md): where the project stands, the continuation point, what is open.
2. [`USER.md`](USER.md): who the user is, how they like to work, standing preferences in their words.
3. [`WORKING.md`](WORKING.md): how we work: the request loop, verification, delegation, parallel
   sessions, the review loop, reporting.
4. [`ENGINEERING.md`](ENGINEERING.md): how we build: the engineering principles E1–E10, with the
   reasoning behind the rules in `CLAUDE.md`.
5. [`ENVIRONMENT.md`](ENVIRONMENT.md): the machine, containers, tool versions, gotchas.
6. [`HISTORY.md`](HISTORY.md): what was built in what order, with pointers into `docs/DECISIONS.md`.
   Read the last three phases; the older ones are reference.
7. [`profile.json`](profile.json): what kind of product this is; it decides which review lenses run
   (`python3 scripts/review/lenses.py show`).

The documents these files point to instead of repeating:

- `CLAUDE.md`: the repo rules, commands and review-loop description (always loaded).
- `docs/SPEC.md`: the behaviour; it is the source of truth.
- `docs/DECISIONS.md`: why each change exists (trigger, decision, alternatives turned down).
- `docs/proposals/`: designs, including phases not yet built.
- `python3 scripts/review/review.py status`: review coverage per unit and lens.

Keep these files current: update `STATUS.md` at the end of every sizeable piece of work, and the
continuation point after every step. Keep them small, too: see "Keeping the handover files small" in
`WORKING.md`.
