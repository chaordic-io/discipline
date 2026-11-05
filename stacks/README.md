# Stacks

The kit is stack-neutral: what it needs from a stack is a set of capabilities, not particular tools.

**Starting a new web app?** [`recommended-webapp.md`](recommended-webapp.md) is our default suggestion:
the app (Go, Postgres, React) and the marketing site (Astro on Cloudflare Pages), with the key library
for each purpose and when to choose differently.

Two worked examples of how those stacks are gated and tested:

- [`go-react-postgres.md`](go-react-postgres.md): a multi-tenant SaaS (Go API, React SPA, Postgres with
  row-level security), with the full gate, real-service tests, smoke and browser suites.
- [`astro-cloudflare-pages.md`](astro-cloudflare-pages.md): a static marketing site with serverless
  functions, built-page tests, claims tests against the app, and browser tests in a container.

## What each stack must provide

| Capability | Go | TypeScript / Node | Python | Rust | JVM |
|---|---|---|---|---|---|
| Strict lint, no warnings | golangci-lint | ESLint strict-type-checked, `tsc --strict` | ruff + mypy --strict | clippy `-D warnings` | Error Prone, Checkstyle/Spotless |
| Unit tests + coverage threshold | `go test -cover` + a per-package gate | Vitest `--coverage` thresholds | pytest + coverage `fail_under` | cargo test + cargo-llvm-cov | JUnit + JaCoCo rules |
| Property / fuzz tests | rapid, `testing.F` | fast-check | hypothesis | proptest, cargo-fuzz | jqwik |
| Real services in tests | testcontainers-go | testcontainers-node | testcontainers-python | testcontainers-rs | Testcontainers |
| Generated code is current | `sqlc diff`, re-export and diff | regenerate and `git diff --exit-code` | same | same | same |
| Duplication | jscpd | jscpd | jscpd / pylint duplicate-code | jscpd | jscpd / PMD CPD |
| Vulnerabilities | govulncheck | `npm audit` | pip-audit | cargo-audit | OWASP dependency-check |
| Browser end-to-end | Playwright (any backend) | Playwright | Playwright | Playwright | Playwright |

Every row is one target of the gate, and the gate also runs `scripts/review/test_review.py` (Python 3.10+
and git are the kit's only own requirements).
