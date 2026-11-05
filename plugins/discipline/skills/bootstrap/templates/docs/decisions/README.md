# Decisions: one file per decision

Why things are the way they are. One file per change that came from the user's feedback or a product
decision, written when the decision is made, not at the end of the session: `discipline decisions new
"<title>"` creates `<YYYY-MM-DD>-<slug>.md` here with the format below and updates the index,
`docs/DECISIONS.md`. One file each means branches never conflict over the log.

Read by search, not in full: find the decisions for your area or spec section
(`grep -rln "Area: invoicing" docs/decisions/`), and skip superseded ones. A decision that is replaced
stays, with a `Superseded by` line naming the file that replaced it.

```markdown
# <short title>

- **Date:** <YYYY-MM-DD>. **Kind:** <user decision | user feedback | agent, bug fix>
- **Area:** <one or two words from the spec's areas, e.g. invoicing, permissions>
- **Trigger:** <what prompted it, with the user's words quoted where they gave them>
- **Decision:** <what was decided, precisely enough to build and test from>
- **Alternatives turned down:** <each with the reason>
- **Conventions taken during the build** (optional): <choices made without asking, so they can be revisited>
- **Spec:** <the docs/SPEC.md section(s)>. **Tests:** <the tests that pin it>
- **Superseded by** (added later, when it happens): <the file of the decision that replaced it>
```
