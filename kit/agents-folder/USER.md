# The user

<!-- ADAPT: who the user is (role, expertise, market), in a few lines. Keep their standing preferences
below in their own words, with the date each was given. The preferences listed are the ones the kit's
author gave in earlier projects; confirm them with the user, then keep, change or delete each. -->

- **Who they are:** <!-- e.g. product owner and developer -->
- **Expertise:** <!-- e.g. experienced engineer; wants the reasoning ("why"), concise status, and
  decisions surfaced, not hidden -->
- **Market:** <!-- who the product is for; which countries, languages and regulations matter -->

## Standing preferences (from their own words)

- **Completeness:** "No rush, I care about completeness and thoroughness."
- **Tests:** "Write tests for each fix, so we don't get regressions." Tests for everything: property and
  fuzz tests, real services through containers; never mock the database.
- **Every failure is ours:** "Any failure, whether we caused it now or not, should be investigated, we
  are the only ones building this." Root-cause it, fix it with a regression test, report it; re-running
  until green is not a fix.
- **Write decisions down immediately:** "We should work this way so that we survive session
  crashes/restarts." Decisions, backlog items and the continuation point go into the repo as they happen.
- **Keep iterating:** "Don't stop, keep iterating until [done], only pause if needing my judgement." Work
  through the roadmap item after item; stop only for real product decisions.
- **Commits:** "i do the committing from now on, not you". Agents never commit, branch or push.
- **Translations:** "written in a tone, way, and voice that is appropriate for the market, not just a
  straight translation", for every surface (app and site).
- **Claims:** marketing and docs make no claims the code doesn't support.
- **Parallel sessions:** "Ensure you do not stomp on what the other agent pane is doing."
- **Lint and review:** strict lint, and read-only reviewer agents iterated until clean; rely on the gate
  and the review loop rather than hooks.
- **Token economy:** the incremental, ledger-based review loop, never repeated whole-repo sweeps. A usage
  stop (`stopAt`) applies only when the user sets it for a run.
- **Status updates:** asks "status and ETA?"; answer with a status line and a step-by-step ETA table.
- **Documentation:** every change from feedback goes into `docs/DECISIONS.md` ("so we have a track of
  why they exist"), and the spec stays current.
- **Tools:** <!-- e.g. mise, with versions pinned in mise.toml -->
- **Language of docs:** <!-- e.g. British English -->
