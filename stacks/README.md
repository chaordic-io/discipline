# Choosing a stack

The kit does not prescribe languages, frameworks or libraries. This page is about choosing them: the
criteria we compare options by, how to apply them, the usual shapes by product kind, and the
capabilities the stack must provide. How we build once the stack is chosen is a separate matter: the
engineering principles E1–E10 in [`kit/agents-folder/ENGINEERING.md`](../kit/agents-folder/ENGINEERING.md),
installed as `.agents/ENGINEERING.md`. The two connect through S7: a stack is only a candidate if it
makes every engineering principle easy. The [examples](examples/) show how one project chose; they
illustrate, they don't recommend.

## Selection criteria

Each criterion has an ID, so a `docs/DECISIONS.md` entry can cite the ones a stack choice rests on
("Postgres for storage and the job queue: S2, S7 for E3").

**S1. Fit the product, then the team.** Start from the project profile (`.agents/profile.json`):
what kind of product it is, its interfaces, its languages, how much performance matters, what data it
holds, whether it calls models. Among the options that fit, the one the team knows well beats a
better-on-paper one it doesn't. A stack that fights the product shape (a request/response framework
for realtime collaboration, a heavy runtime for a static site) costs more than any familiarity saves.

**S2. Few moving parts.** Count the languages, runtimes, services and data stores each option needs
for the whole product, and prefer the option with fewer, as long as each part does its job well at
the expected size: one deployable unit, one data store that can do several jobs, static output for
content. (E1 keeps it that way afterwards.)

**S3. Static types end to end, and strict.** A type checker and linter that run with zero warnings
allowed, across the boundaries between parts (server types → contract → client types). Prefer
languages and configurations where the strict mode is the normal mode.

**S4. A healthy dependency ecosystem.** Lockfiles with integrity hashes, locked installs in CI,
vulnerability and licence scanners, and a standard library that covers the common needs, so that E6
costs little. Every tool considered is maintained (recent releases, more than one maintainer), widely
used, and under a licence compatible with the product.

**S5. Operable by the people who will run it.** One deployment path, the same commands locally and
in CI (the gate is one command), health and readiness checks, and a hosting model the team can operate
and debug where the profile's data may live. A managed service is a dependency too: weigh lock-in and
data residency.

**S6. Reversible where it is cheap to be.** Prefer tools behind standard interfaces (SQL, HTTP,
OpenAPI or protobuf, SMTP, OCI images, the common object-storage API, OpenTelemetry), so a component
can be replaced without rewriting its callers. Where a choice is hard to reverse (the primary language,
the data store, a model provider's proprietary features), spend the time to get it right and record why.

**S7. The stack supports every engineering principle.** For each of E1–E10 that applies to the
profile, the stack offers a ready way to follow it: generators for its contracts (E2), a data store
that enforces constraints and isolation (E3), exact decimal and date types (E4), containers and test
tooling for its services (E5), safe defaults (E7), localisation and accessible UI components (E8),
tracing and log capture (E9), model clients, response recording and eval runners (E10). The capability
checklist below is how to check it.

## How to choose

1. **Read the profile** (batch 1 of the bootstrap questions) and write down the constraints it implies:
   the parts the product needs (see "Shapes by product kind"), the interfaces between them, the
   expected sizes, the sensitive data, the languages.
2. **Existing code decides most of it.** If the repository has code, its stack is the stack: check it
   against the capability checklist and fill only the gaps.
3. **For each part, propose one or two options** that meet the criteria and the checklist, with
   the trade-off between them. Say which criteria each choice rests on. Put the option the team knows
   first unless a criterion rules it out (S1).
4. **Check every tool before adopting it:** maintained (recent releases, more than one maintainer),
   widely used, licence compatible with the product, supported by the scanners (S4). The tool names in
   this folder are illustrations and may be out of date.
5. **Record the result** in `docs/DECISIONS.md`: each part, the choice, the criteria it rests on,
   the alternatives turned down and why, and any engineering principle the stack makes hard, with how
   it is covered instead. Then fill the gate, `CLAUDE.md` and the workflow's `PROJECT`
   block from it.

## Shapes by product kind

The parts a product of each kind usually needs, and the engineering principles the stack must support
best for it (S7). These are shapes, not stacks: any language that meets the checklist can fill them.

| Kind | Usual parts | Watch especially |
|---|---|---|
| `web-app`, `internal-tool` | One backend, one data store, a browser client typed from the API contract; static marketing pages kept apart | E2 (generated client), E3 (isolation and constraints in the data store), E8, E9 (server and client errors) |
| `mobile-app` | A native or cross-platform client, the backend and contract it shares with the web | E2, and versioning: old app versions stay in use, so the contract changes compatibly; E9 (crash and error reports from devices) |
| `public-api`, `backend-service` | A service, its data store, a published contract, rate limiting | E2, E3, E7, E9; a breaking-change check in the gate |
| `library` | The package, its public exports as the contract, the test suite | E6 (few dependencies of its own), semver checked by tooling |
| `cli`, `desktop-app` | One binary or package, configuration, update path | E1, E6, signed releases |
| `static-site` | A static site generator, a few serverless functions at most | E1 (no runtime), E7 (strict CSP, no third-party requests), E8 |
| `data-pipeline` | Jobs, a scheduler or stream, storage, data contracts between stages | E2 (schemas between stages), E5 (deterministic runs on fixtures), E9 (a trace per run, metrics on lag and failures) |
| any kind, with `ai` | Prompt files, a model client behind one interface, eval sets per prompt and an eval runner; for `rag` an index with its ingestion; for `agentic` tools with their own authorization and a sandbox | E10, E6 (models and providers as dependencies), E7 (injection, data to providers), E9; S6 (avoid depending on one provider's proprietary features) |

When the product grows a new shape (realtime collaboration, heavy data or ML work, a mobile client),
add the part that shape needs next to the existing ones rather than replacing what works, and record
the decision.

## Capability checklist

What the gate and the review loop need from the stack, and how to check S7. Rows name the
engineering principle or criterion they serve where there is one. Each row is one gate target unless
marked as applying only when a lens is on in the profile. The tools named are **illustrations** of what fills each
row in common ecosystems, not recommendations: check each against step 4 of "How to choose".

| Capability | Go | TypeScript / Node | Python | Rust | JVM |
|---|---|---|---|---|---|
| Strict lint, no warnings (S3) | golangci-lint | ESLint strict-type-checked, `tsc --strict` | ruff + mypy --strict | clippy `-D warnings` | Error Prone, Checkstyle/Spotless |
| Unit tests + coverage threshold | `go test -cover` + a per-package gate | Vitest `--coverage` thresholds | pytest + coverage `fail_under` | cargo test + cargo-llvm-cov | JUnit + JaCoCo rules |
| Property / fuzz tests (E5) | rapid, `testing.F` | fast-check | hypothesis | proptest, cargo-fuzz | jqwik |
| Real services in tests (E5) | testcontainers-go | testcontainers-node | testcontainers-python | testcontainers-rs | Testcontainers |
| Generated code is current (E2) | `sqlc diff`, re-export and diff | regenerate and `git diff --exit-code` | same | same | same |
| Duplication | jscpd | jscpd | jscpd / pylint duplicate-code | jscpd | jscpd / PMD CPD |
| Vulnerabilities (E6) | govulncheck | `npm audit` | pip-audit | cargo-audit | OWASP dependency-check |
| Licences (E6) | go-licenses | license-checker | pip-licenses | cargo-deny | license-maven-plugin |
| Locked installs (E6) | go.sum (`-mod=readonly`) | `npm ci` | `pip install --require-hashes`, `uv sync --locked` | `cargo --locked` | Gradle lockfiles / dependency verification |
| Breaking-change check (E2; contracts) | `oasdiff breaking`, `buf breaking`, `apidiff` | `oasdiff`, `graphql-inspector`, api-extractor | `oasdiff`, griffe | `cargo semver-checks` | japicmp, `oasdiff` |
| Contract tests (E2; contracts) | Schemathesis (any server) | Schemathesis, Pact | Schemathesis | Schemathesis | Schemathesis, Pact |
| Benchmarks and load (performance) | `testing.B`, k6 | Vitest bench, k6, Lighthouse CI | pytest-benchmark, k6 | criterion, k6 | JMH, k6 |
| Browser end-to-end | Playwright (any backend) | Playwright | Playwright | Playwright | Playwright |
| Traces and metrics (E9) | OpenTelemetry Go | OpenTelemetry JS (`@opentelemetry/sdk-node`; `sdk-trace-web` in browsers) | OpenTelemetry Python | `tracing` + `opentelemetry` crates | OpenTelemetry Java (agent or SDK) |
| Structured logs with trace IDs (E9) | `log/slog` + an OTel bridge | pino + OTel instrumentation | `logging` with a JSON formatter, or structlog | `tracing-subscriber` (JSON) | SLF4J + Logback JSON encoder |
| Error logs captured in tests (E9) | a test `slog.Handler` | a pino test destination, or a spy on the logger | pytest `caplog` | `tracing-test` | Logback `ListAppender` |
| Recorded model responses (E10; ai) | go-vcr | Polly.js, nock recordings | vcrpy, pytest-recording | wiremock with saved fixtures | WireMock record and playback |
| Eval runner (E10; ai) | promptfoo, Inspect, or the test runner with a project harness | promptfoo, or Vitest with a project harness | Inspect, Ragas (rag facets), DeepEval, or pytest with a project harness | promptfoo, or the test runner with a project harness | promptfoo, or JUnit with a project harness |

Every stack also needs: tool versions pinned in one file (E6), CI actions and base images pinned by
digest (E6), and `scripts/review/test_review.py` in the gate (Python 3.10+ and git are the kit's only
own requirements). A capability the chosen stack can't provide is a gap to record in
`docs/DECISIONS.md` with how it is covered instead, not a row to drop silently.

## Examples

How one project chose. Copy the reasoning, not the list.

- [`examples/webapp-libraries.md`](examples/webapp-libraries.md): the libraries a multi-tenant business
  web app chose for each purpose, each with the criterion or principle behind it.
- [`examples/go-react-postgres.md`](examples/go-react-postgres.md): that app's gate, real-service tests,
  smoke and browser suites, review units and workflow configuration.
- [`examples/astro-cloudflare-pages.md`](examples/astro-cloudflare-pages.md): its static marketing site
  with serverless functions, built-page tests and claims tests against the app.
