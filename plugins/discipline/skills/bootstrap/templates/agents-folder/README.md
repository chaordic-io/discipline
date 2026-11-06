# .agents: handover for a new agent session

This folder lets an agent session recover its context after a restart. Everything an agent needs
that isn't already in the code, `CLAUDE.md` or `docs/` is here. The agent's own memory directory
(e.g. `~/.claude/...`) lives outside the repo and may not survive a VM or container rebuild, so
anything worth keeping is written here.

**Resuming?** [`RESUME.md`](RESUME.md) has the prompt to start with.

Read in this order:

1. [`STATUS.md`](STATUS.md): what everyone shares: the roadmap and the shared open questions.
   `discipline work --list` shows the branches in flight and who works on them.
2. Your branch's work file, `.agents/work/<branch>.md` (`discipline work` prints or creates it): this
   branch's continuation point and state.
3. [`USER.md`](USER.md): the team, its roles and standing preferences; then your own
   `USER.local.md` if you have one (not committed).
4. How we work: /discipline:working (the request loop, verification, delegation, parallel sessions,
   the review loop, handover, reporting), and [`WORKING.md`](WORKING.md) for this project's git policy
   and its own lessons.
5. How we build: /discipline:engineering (the engineering principles E1–E10, the reasoning behind the
   rules in `CLAUDE.md`), and [`ENGINEERING.md`](ENGINEERING.md) for this project's own principles.
6. [`ENVIRONMENT.md`](ENVIRONMENT.md): the machine, containers, tool versions, gotchas.
7. [`HISTORY.md`](HISTORY.md): what was built in what order, with pointers to decisions. Read the
   last three entries; the older ones are reference.
8. [`profile.json`](profile.json): what kind of product this is; it decides which review lenses run
   (`discipline lenses show`).

The documents these files point to instead of repeating:

- `CLAUDE.md`: the repo rules, commands and review-loop description (always loaded).
- `docs/SPEC.md`: the behaviour; it is the source of truth.
- `docs/decisions/`: why each change exists (trigger, decision, alternatives turned down), one file
  per decision; `docs/DECISIONS.md` is its generated index. Read by search.
- `docs/proposals/`: designs, including phases not yet built.
- `discipline review status`: review coverage per unit and lens.

Keep these files current: the work file's continuation point after every step, and its "In progress"
section before and after each step that edits files (so a crash in the middle of a step leaves a
trace), `STATUS.md` when
something shared changes (a roadmap item, a shared question). Keep them small, too: see "Keeping the handover files small" in
/discipline:working.
