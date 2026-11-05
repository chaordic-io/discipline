---
name: upgrade
description: Move a repository that was set up with an older discipline version to the current one - read the changelog, apply its migration notes, add new template files, update the gate's pinned version and the profile's version stamp, and verify. Use when the user asks to upgrade, or when `discipline check` warns that the project was set up with an older version.
disable-model-invocation: true
---
# Upgrade a repository to the current discipline version

1. **Versions.** `discipline --version` is the plugin's version. The project's is `discipline` in
   `.agents/profile.json` (missing means it was set up before versions were stamped: treat it as the
   oldest). If they are equal, say so and stop.
2. **Read the changelog** between the two versions: `CHANGELOG.md` at the root of the plugin's
   repository (https://github.com/chaordic-io/discipline). Each release lists its migration notes:
   renamed or moved files, new profile fields, changed `units.json` or `project.json` formats, new
   lenses.
3. **New files:** `discipline init --dry-run` lists templates the project doesn't have yet; run
   `discipline init` to add them (it never overwrites). For each existing file that a migration note
   says changed in the templates, compare it with the plugin's
   `skills/bootstrap/templates/` version and merge the change by hand, keeping the project's own text.
4. **Apply the migration notes** in order, one release at a time. Show the user any note that needs a
   decision (a new lens, a new profile question) as one batch, with a recommendation each.
5. **Profile and lenses:** answer any new profile fields, then `discipline lenses apply`; add newly
   enabled lenses to the units where they apply and fill their sections of
   `.agents/review-context.md`.
6. **Pin the new version** in the gate (the `uvx --from "git+…@v<version>…"` line) and set
   `discipline` in `.agents/profile.json` to the new version.
7. **Verify:** `discipline check`, then the full gate. Fix what fails.
8. **Record** a decision in `docs/decisions/` ("Upgraded discipline from <old> to <new>") with what changed
   for this project and the decisions taken; update this branch's work file and, if the roadmap
   changed, `.agents/STATUS.md`. Tell the user which files
   changed, for them to commit.
