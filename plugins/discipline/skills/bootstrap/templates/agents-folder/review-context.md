# Review context

This project's specifics for each review lens. The checklists (the discipline plugin's reviewer agents) are generic; each
reviewer reads its lens's section here first. Fill in the sections of the lenses that are on
(`discipline lenses show`) and delete the others. Keep each section short: facts a
reviewer needs (paths, commands, sizes, rules), not explanations.

**Project:** <!-- ADAPT: one line on what it is, e.g. "a multi-tenant SaaS (Go API + Postgres row-level security + React SPA)" -->


## security

- <!-- ADAPT: path, e.g. docs/SPEC.md "Multi-tenancy & security" -->
- <!-- ADAPT: how tenants or users are kept apart. Example (multi-tenant Postgres): every tenant table has org_id, RLS ENABLE + FORCE and the standard policy; every data access goes through the tenant transaction helper; no global-access helper touches tenant tables; composite (org_id, id) foreign keys; IDs from one tenant are never accepted for another; each tenant table has a cross-tenant test. -->
- <!-- ADAPT: name your authorization helpers -->

## behaviour

- <!-- ADAPT: the domain areas where mistakes cost most, e.g. money and rounding, permissions per role, versioned settings applied to past periods, country-specific rules, document numbering. -->

## tests

- <!-- ADAPT: e.g. `go test -cover ./...` and `go tool cover -func`, `npm run test:coverage` -->
- <!-- ADAPT: libraries, e.g. pgregory.net/rapid and testing.F (Go), fast-check (TypeScript), hypothesis (Python) -->
- <!-- ADAPT: e.g. testcontainers through a shared test helper package -->
- <!-- ADAPT: isolation rule, e.g. every tenant table has a cross-tenant isolation test -->

## architecture

- **Layers and what each may import:** <!-- ADAPT. Example (Go API + React SPA): `domain/*` pure logic,
  no IO; `authz` pure permission decisions; `store` migrations, generated queries, transaction
  helpers; feature packages with a Service (business rules, authorization, typed errors) and thin
  Handlers (no business rules or SQL); `app` composes everything; frontend reaches the API only
  through the generated client. Example (static site): pure logic in src/lib with unit tests;
  components only render; serverless functions thin, their logic in src/lib. -->
- **Invariants:** <!-- ADAPT: e.g. money as integer minor units, never float; quantities only through
  the units package; rounding in one place. -->

## duplication

- <!-- ADAPT: e.g. `npx --yes jscpd@4 --config .jscpd.json --reporters console` (the console reporter writes nothing) -->
- <!-- ADAPT: list your shared helper packages -->
- <!-- ADAPT: paths -->

## simplicity

- **Seams kept on purpose:** <!-- ADAPT: interfaces, extension points and indirection the project wants, with the reason (e.g. "payment providers behind `Provider`: a second one is on the roadmap") -->
- **Shared machinery to use instead of re-building:** <!-- ADAPT: the shared helper packages, the framework features relied on (validation, retries, caching) -->

## performance

- <!-- ADAPT: e.g. `go test -run=^$ -bench=. ./internal/<pkg>/`, `npx vitest bench` -->
- <!-- ADAPT: where they are, e.g. docs/SPEC.md "Limits and scale" -->
- <!-- ADAPT: the expected sizes, e.g. 1,000 tenants, 50,000 rows per tenant per year, 20 requests/s at peak, responses under 300 ms at p95; mobile clients on 3G. -->
- <!-- ADAPT: delete for projects without a client -->
- <!-- ADAPT: e.g. Go benchmarks, k6, Lighthouse budgets -->

## supply-chain

- <!-- ADAPT: e.g. `govulncheck ./...`, `npm audit --omit=dev`, `pip-audit`, `cargo audit`, `osv-scanner -r .` -->
- <!-- ADAPT: e.g. Go modules (api/go.mod, go.sum); npm (web/package.json, package-lock.json) -->
- <!-- ADAPT: e.g. npm `ignore-scripts`, pnpm `onlyBuiltDependencies` -->
- <!-- ADAPT: e.g. a proprietary SaaS: flag AGPL, SSPL and unlicensed packages -->
- <!-- ADAPT: delete if nothing is published -->

## contracts

- <!-- ADAPT: e.g. `oasdiff breaking main.yaml api/openapi.yaml`, `buf breaking --against '.git#branch=main'`, `graphql-inspector diff`, `cargo semver-checks`, `api-extractor run` -->
- <!-- ADAPT: one line each: the contract (a file, or how it is produced), who implements it, who consumes it, how consumers get it. Examples: - api/openapi.yaml: exported from the Go handlers; consumed by the web app through a generated client (web/src/api/) and by the mobile app, whose old versions stay in use for months. - proto/events/*.proto: events from the API to the worker. - The public exports of src/index.ts, published to npm under semver. -->
- <!-- ADAPT: who they are, e.g. mobile app versions in the field, third-party integrators -->

## ai

- <!-- ADAPT: the AI features, one line each: what it does, its mode, its prompt files, its eval set, the model and provider, the tools it may call, the data it may send. -->
- <!-- ADAPT: delete without rag -->

## localisation

- <!-- ADAPT: e.g. en (default), de, fr, it, es, sv -->
- <!-- ADAPT: catalogue paths for UI, backend and any site -->
- <!-- ADAPT: e.g. formal German and French; informal Italian, Spanish and Swedish for staff; formal for client-facing documents -->
- <!-- ADAPT: e.g. whether API error details may stay English -->
