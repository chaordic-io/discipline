# Status (last updated <YYYY-MM-DD>)

## Continuation point (start here)

<!-- The next concrete step, precise enough that a fresh session can start on it without asking.
Update it after every step, before starting the next. -->

## Roadmap (in the user's order)

<!-- Numbered items, each with its state (done / in progress / next), a pointer to its proposal and
DECISIONS entries, and the user's words that ordered it, with the date. -->
1.

## Sessions and ownership

<!-- If several sessions work on the repo at once: which session owns which directories, and the
shared files that need a merge step. Delete if there is only one. -->

## State

- **Built and verified:** <!-- with the last gate, end-to-end and smoke results, as numbers -->
- **Uncommitted:** <!-- what the user still has to commit -->
- **Review:** `python3 scripts/review/review.py status` / `open`.

## Open questions for the user

<!-- Batched, each with options and a recommendation. Move answers to DECISIONS when given.
Include the review loop's open questions (`python3 scripts/review/review.py questions`). -->

## Follow-ups and known issues

<!-- Things found along the way that are not on the roadmap yet. -->

## How to resume

1. Read `.agents/README.md` and the files it lists.
2. Install the tools (see `ENVIRONMENT.md`), then run the gate to confirm the tree is green.
3. Check the review state, then continue from the continuation point.
