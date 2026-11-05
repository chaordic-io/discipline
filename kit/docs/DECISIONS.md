# Decisions

Why things are the way they are. Newest first. One entry per change that came from the user's feedback
or a product decision, written when the decision is made, not at the end of the session.

**Read by search, not in full.** Reviewers and sessions look up the entries for the area or spec
section they work on (`grep -n "Area: invoicing" docs/DECISIONS.md`, or the spec section number), not
the whole file. That only works if every entry carries its `Area` and `Spec`.

**Never edited away.** A decision that is replaced stays, with a `Superseded by` line pointing to the
entry that replaced it; readers skip superseded entries. Past 100 entries (the budget in
`scripts/review/handover.py`), move the entries of past years to `docs/decisions/<year>.md` and keep
here an index of one line per moved entry (date, title, area, file) above the current year's entries.

<!-- Entry format:

## <YYYY-MM-DD>: <short title> (user decision | user feedback | agent, bug fix)
- **Area:** one or two words from the spec's areas (e.g. invoicing, permissions, onboarding).
- **Trigger:** what prompted it, with the user's words quoted where they gave them.
- **Decision:** what was decided, precisely enough to build and test from.
- **Alternatives turned down:** each with the reason.
- **Conventions taken during the build** (optional): choices made without asking, so they can be revisited.
- **Spec:** the SPEC.md section(s). **Tests:** the tests that pin it.
- **Superseded by** (added later, when it happens): the date and title of the entry that replaced it.
-->
