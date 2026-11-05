# Environment

<!-- ADAPT: fill each section as you learn it; record every gotcha the moment it costs time. -->

## Where the agent runs

- **The container or VM:** <!-- what it is, where the repo is mounted, the host path -->
- **Docker:** <!-- local daemon, or the host's socket (then: bind mounts resolve against host paths,
  published ports may be unreachable from the agent; run test clients inside the stack's network) -->
- **Command sandbox:** <!-- network or filesystem limits seen, and the workaround (e.g. a runner
  container for tests that need the test databases) -->
- **Tool versions:** <!-- where they are pinned (e.g. mise.toml), and the install command after a fresh VM -->
- **What survives a restart:** only the repo (including `.claude/` and `.agents/`). The agent's memory
  directory and temporary files may not.

## Long-lived containers

<!-- Shared test services (names, how to reset them), the user's development database (never modify it
without asking), per-run stacks for end-to-end and smoke tests (naming, keep/reuse flags). -->

## Test infrastructure

<!-- How the test suites reach real services; template databases; how to run one package; how to narrow
the browser suite; where failure traces land. -->

## Deployment

<!-- Where each part runs, how it is deployed, which secrets it needs (names only, never values). -->

## Gotchas

<!-- One bullet per lesson: symptom, cause, fix. -->
