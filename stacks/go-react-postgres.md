# Example stack: Go API + React SPA + Postgres

A worked example from the project this kit was extracted from (Hourmark: multi-tenant time tracking
and invoicing). Use it as a model: copy the parts that fit, adapt the names.

## The stack

- **API:** Go, chi + huma (OpenAPI from code), pgx + sqlc (queries in SQL, generated Go), goose
  migrations, River for background jobs, Typst for PDFs. One binary with the SPA embedded, one Docker image.
- **Web:** React + Vite + TypeScript (strict), the API client generated from the OpenAPI spec, i18next.
- **Database:** Postgres with row-level security per tenant (`org_id` on every tenant table, RLS
  `ENABLE` + `FORCE`, a standard policy, all access through one `WithTenant(ctx, orgID, userID, fn)` helper).
- **Tools:** versions pinned in `mise.toml` (`mise install` after a fresh machine).

## The gate (`make check`)

```make
check: lint test dup vuln
lint: lint-api lint-web lint-e2e
lint-api:            # golangci-lint (strict) + generated code is current
	cd api && golangci-lint run ./...
	cd api && sqlc diff
	./scripts/check-generated-api.sh spec      # exported OpenAPI equals the committed one
lint-web:            # tsc --strict, eslint strict-type-checked, knip; generated TS types current
	cd web && npm run lint
	./scripts/check-generated-api.sh types
test: test-api test-web test-scripts
test-api:            # race detector, real services, per-package coverage gate
	cd api && go test -race -count=1 -coverprofile=coverage.out ./... | tee test-output.txt
	./scripts/coverage-gate.sh api/test-output.txt
test-web:            # Vitest with coverage thresholds
	cd web && npm run test:coverage
test-scripts:        # the review loop's bookkeeping, incl. "every file belongs to a unit"
	python3 -m unittest discover -s scripts/review -q
dup:                 # copy/paste detection over Go and TypeScript
	npx --yes jscpd@4.3.0 --config .jscpd.json
vuln:
	cd api && govulncheck ./...
	cd web && npm audit --omit=dev --audit-level=high
```

- **Coverage gate** (`scripts/coverage-gate.sh`): per package, ≥ 90 % for pure domain packages and ≥ 70 %
  for the rest; a package with no tests fails; a failing package fails even if exempt from the minimum.
- **Generated code:** `make gen` runs sqlc, exports the OpenAPI spec and regenerates the TS types; the
  lint step fails when they are stale. Generated files are never edited by hand.
- **Property and fuzz tests:** `pgregory.net/rapid` and `testing.F` in Go, `fast-check` on the web;
  `make fuzz` runs each Go fuzz target for 30 s.

## Real services in tests

- **One shared Postgres and one Mailpit** container for all Go test packages (testcontainers, reused by
  name). Each schema version gets a template database named after the migrations' hash; every test
  clones its own database from it, so tests are isolated and fast.
- **Every tenant table has a cross-tenant isolation test**, and a store test enforces migration numbers
  1..n without gaps.
- **Agent sandbox:** when the agent's sandbox cannot reach ports published by the test containers,
  `make test-api-docker` runs the Go suite in a runner container on the same Docker daemon (source in by
  `docker exec` + tar, no bind mounts; module and build caches in named volumes; `PKGS=...` narrows it).
  `make check-docker` is the whole gate that way.
- **External validators** (e.g. an e-invoice validator) run as pinned containers in tests, built by
  content hash, required by the gate instead of skipped when missing.

## Slow suites (run by the main session)

- `make smoke`: builds the production image and runs a scripted end-to-end check against real Postgres
  and Mailpit: sign-up → verify → project → time → invoice → PDF → email → public link → tenant isolation.
- `make e2e`: builds the production image and runs the Playwright suite inside the stack's Docker
  network (key user journeys, a phone-width project); `E2E_KEEP=1` keeps the stack, failure traces land
  in `e2e/test-results`.

## Conformance evidence

Rule presets (e.g. working-time law per country) are YAML; each has a case file citing the law for every
expected result, with full coverage required; `make compliance-evidence` regenerates evidence documents
from the cases. Adding a preset without its cases fails the tests.

## Review units (`scripts/review/units.json`)

About 30 units: one per Go feature package (`api-auth`, `api-orgs`, `api-invoices`, …), the store and
migrations, the domain packages, web feature folders, the e2e suite, and one infrastructure unit (CI,
Dockerfile, Makefile, scripts). Security-sensitive units first. Lenses: no localisation on pure domain
code; translation catalogues may be checked by script.

## The workflow's PROJECT block

```js
const PROJECT = {
  name: 'Hourmark',
  docs: 'CLAUDE.md and docs/SPEC.md',
  gate: 'make check',
  fixGate: '`make lint test-scripts`',
  affectedTests: 'the Go packages you changed and those importing them (`PKGS="./internal/<pkg>/..." make test-api-docker`), and the web test files covering changed web files (`cd web && npx vitest run <paths>`)',
  fixRules: 'Follow CLAUDE.md strictly (tests for every change, property/fuzz tests where applicable, testcontainers for DB code, never weaken lint configs, no unexplained nolint/eslint-disable). Update docs/SPEC.md if behaviour changes.',
  targetedChecks: '`PKGS=./internal/<pkg>/... make test-api-docker` (database tests) or `cd api && go test ./internal/domain/...` (pure packages), `cd web && npx vitest run <path>`, `make lint-api`, `make lint-web`',
  scriptCheckable: 'non-English translation catalogues (web/src/i18n/locales/<lang>/*.json, api/internal/i18n/locales/<lang>.json) may be checked by script (key and placeholder parity, untranslated copies)',
  deltaFocus: 'bugs or regressions introduced, new code without tests, hard-coded user-visible strings or missing translations in any of the six locales, new duplication, security problems, layering violations',
}
```

## CI

GitLab CI stages `lint → test → build → publish`: golangci-lint, generated-code check, govulncheck,
web lint, duplication, the review scripts' tests, the Go suite with services, the web suite, the image
build, and a release job. CI runs the same Makefile targets as developers.
