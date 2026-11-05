# Status (last updated <YYYY-MM-DD>)

<!-- What everyone shares: the roadmap and the shared open questions. A snapshot of
now, not a log: rewrite sections in place, never append history. Each branch's own continuation point
is in .agents/work/<branch>.md (`discipline work`), with who works on it and what it owns. Done roadmap items move to HISTORY.md the day
they are merged; answered questions become decisions in docs/decisions/; a follow-up not taken up
within a phase goes onto the roadmap or is dropped with a one-line reason. Budget: 150 lines
(`discipline handover`). -->

## Roadmap (in the user's order)

<!-- Numbered items, each with its state (done / in progress on <branch> / next), a pointer to its
proposal and decisions, and the user's words that ordered it, with the date. -->
1.

## Branches in flight

Not kept here: each branch's work file says who works on it, its roadmap item and what it owns, and
`discipline work --list` gathers them from git. (A table here would conflict on every merge.)

## State of the default branch

- **Built and verified:** <!-- with the last gate, end-to-end and smoke results, as numbers -->
- **Review:** `discipline review status` / `open`.

## Open questions for the user

<!-- Shared and batched, each with options and a recommendation, and who answers it (CLAUDE.md, "Review
loop", names who answers review questions). Include the review loop's open questions (`discipline
review questions`). Answers become decisions in docs/decisions/. -->

## Follow-ups and known issues

<!-- Things found along the way that are not on the roadmap yet. -->

## How to resume

1. Read `.agents/README.md` and the files it lists.
2. Check out your branch; `discipline work` prints (or creates) its work file. Continue from its
   continuation point.
3. Install the tools (see `ENVIRONMENT.md`), run the gate to confirm the tree is green, and check the
   review state.
