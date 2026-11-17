# Decisions: one file per decision

Why things are the way they are, and what was turned down. One file per decision, product or
technical, written when the decision is made, not at the end of the session:

```sh
discipline decisions new "<title>" --kind <product|technical> --by <agent|together|people> [--people <names>] [--area <area>]
```

creates `<YYYY-MM-DD>-<slug>.md` here and updates the index, `docs/DECISIONS.md`. One file each means
branches never conflict over the log. The title is in the front matter only; the slug is made from it
once and never changes, so links and `superseded-by` survive a reworded title.

**Which decisions get a file.** Every product decision (what users see or can do; the user's call).
Every technical decision someone could reasonably revisit or get wrong again: a dependency, a data
store, a module boundary or layering rule, a protocol or format, a pattern the code is to follow, a
performance or security trade-off, and every approach that was tried and abandoned. Small reversible
choices (a name, a file layout) stay as conventions in the decision or proposal they belong to.

**Who decided** (`decided-by`): `agent` when an agent decided alone, within what it may decide
(`/discipline:working`, "Deciding, assuming, asking"); `together` when agents and people decided it
in conversation; `people` when people decided it without an agent, recorded by them or by an agent
they told. `people` names who, so a question about it goes to the right person. A product decision is
never `agent`: an agent that has to go ahead without an answer works on a marked assumption instead.

**Read by `list` and `search`, not in full:** `discipline decisions list --area <area>` (or
`--kind technical`, `--spec <section>`, `--by agent`) lists the decisions in force;
`discipline decisions search <words>` also finds proposals and answered review questions. Check both
before proposing a design: an alternative turned down or an approach abandoned is not proposed again
unless the reason no longer holds, and then the new decision says why. A decision that is replaced
stays, with `superseded-by` naming the file that replaced it.

```markdown
---
title: <what was decided, in a few words>
date: <YYYY-MM-DD>
kind: technical              # product | technical
decided-by: together         # agent | together | people
people: [<names or roles>]   # empty when an agent decided alone
area: [<one or two of the spec's areas>]
spec: [<the docs/SPEC.md sections>]
tests: [<the tests that pin it>]
superseded-by:               # set later: the file of the decision that replaced it
---

## Trigger
What prompted it, with the user's or developer's words quoted where they gave them.

## Decision
What was decided, precisely enough to build and test from.

## Alternatives turned down
- **<option>:** why it was turned down.

## Tried and abandoned
(Optional.) What was tried, how far it got, and why it failed.

## Conventions taken during the build
(Optional.) Small choices made without asking, so they can be revisited.
```
