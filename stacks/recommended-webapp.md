# Our default stack for web apps (a suggestion)

What we reach for when a new project is a **business web app** (multi-user, data in a database,
documents and emails, several languages) with a **marketing site** next to it. It is the stack of the
project this kit was extracted from, proven there with the full gate and review loop. It is a starting
point, not a rule: another kind of problem (data pipelines, mobile, realtime, ML, embedded) calls for
another stack, and the kit works the same with any of them (see [README.md](README.md)).

Why this shape: one statically typed backend binary, one database that also isolates tenants and runs
the job queue, a typed SPA whose API client is generated from the backend, and a static site with no
runtime to operate. Few moving parts, all testable against real services.

## The app

### Backend: Go

| Purpose | Choice | Why |
|---|---|---|
| Language | **Go** (1.27) | One static binary, fast tests with the race detector, strong tooling, easy to review. |
| HTTP router | **chi** (`go-chi/chi/v5`) | Small, standard `net/http` middleware. |
| API and OpenAPI | **huma** (`danielgtaylor/huma/v2`) | Typed handlers; the OpenAPI spec comes from the code, the TS client from the spec; problem+json errors. |
| Database | **PostgreSQL** (17) | Row-level security for tenant isolation, constraints, JSONB, and the job queue in the same database. |
| Driver | **pgx** (`jackc/pgx/v5`) | The native Postgres driver; pools, COPY, typed errors. |
| Queries | **sqlc** | SQL in `.sql` files, type-safe Go generated from them; `sqlc diff` in the gate. |
| Migrations | **goose** (`pressly/goose/v3`) | Plain SQL migrations, embedded in the binary. |
| Background jobs | **River** (`riverqueue/river`) | A Postgres-backed queue: jobs are enqueued in the business transaction, so nothing is lost or sent twice. |
| Money and rates | **shopspring/decimal** (+ `pgx-shopspring-decimal`) | Exact decimals for rates; money itself as integer minor units plus a currency code. |
| IDs | **google/uuid** | UUIDs everywhere, never sequential IDs in URLs. |
| Password hashing | **argon2id** (`golang.org/x/crypto/argon2`) | The current recommendation for password storage. |
| Rate limiting | **`golang.org/x/time/rate`** | In-memory, bounded limiters per IP, address and key. |
| Localisation helpers | **`golang.org/x/text`** (language, collate, norm) | Language matching, locale-aware sorting, Unicode normalisation. |
| Logging | **`log/slog`** (standard library) | Structured logs, no dependency. |
| Email | **go-mail** (`wneessen/go-mail`) | SMTP with STARTTLS and proper MIME. |
| PDFs | **Typst** (CLI, pinned, embedded fonts) | Typeset documents from templates; fast, deterministic, testable by rendering. |
| QR codes | **boombuler/barcode** to generate; **gozxing** and **goqr** to decode in tests | Codes drawn as SVG; round-trip tests with two independent decoders. |
| Configuration data | **YAML** (`go.yaml.in/yaml/v3`) | Versioned presets (rules per country, payment formats) as data, not code. |
| Property tests | **rapid** (`pgregory.net/rapid`) + `testing.F` fuzzing | Invariants of parsers, arithmetic and rules. |
| Real services in tests | **testcontainers-go** (+ postgres module), **Mailpit** for email | One shared container per service; a template database per schema hash, cloned per test. |
| Lint | **golangci-lint** (strict config) | One linter run in the gate, no warnings allowed. |
| Vulnerabilities | **govulncheck** | Reports only vulnerabilities in code paths actually used. |

### Frontend: React SPA

| Purpose | Choice | Why |
|---|---|---|
| Language | **TypeScript** (strict) | Types end to end with the generated API types. |
| UI library | **React** (19) | The ecosystem and the testing tools. |
| Build | **Vite** | Fast dev server and build; the build is embedded in the Go binary. |
| Routing | **TanStack Router** | Type-safe routes and search params. |
| Server state | **TanStack Query** | Caching, refetching, mutations with invalidation. |
| API client | **openapi-fetch** + **openapi-typescript** | A typed client generated from the backend's OpenAPI spec; never hand-written types. |
| Forms and validation | **react-hook-form** + **zod** (via `@hookform/resolvers`) | Typed forms, one schema for validation. |
| Styling | **Tailwind CSS** (4) + **class-variance-authority**, **clsx**, **tailwind-merge** | Design tokens as CSS variables; variants without CSS sprawl. |
| Accessible primitives | **Radix UI** (dialog, dropdown menu, popover, tabs, label, slot) | Keyboard and screen-reader behaviour done right. |
| Icons | **lucide-react** | One consistent line icon set. |
| Font | **Inter** (`@fontsource-variable/inter`) | Self-hosted, no third-party font requests. |
| Localisation | **i18next** + **react-i18next**, **eslint-plugin-i18next** | Catalogues per language; lint fails on hard-coded UI text. |
| Unit and component tests | **Vitest** (+ coverage-v8), **Testing Library**, **jsdom**, **MSW** | Real routes rendered with the network mocked at the HTTP level. |
| Property tests | **fast-check** | Parsing and formatting invariants. |
| Lint | **ESLint** strict-type-checked (`typescript-eslint`), react-hooks, **knip** | No unused files, exports or dependencies. |

### Browser and smoke tests

| Purpose | Choice |
|---|---|
| End-to-end journeys | **Playwright** (own package, ESLint + `eslint-plugin-playwright`), run inside the stack's Docker network against the production image, with Mailpit for emails |
| Smoke test | A Python script against the production image with real Postgres and Mailpit (sign-up → core action → document → email → public link → tenant isolation) |

### Delivery and operations

| Purpose | Choice |
|---|---|
| Image | Multi-stage Docker build; runtime on **distroless** (static, non-root), Typst copied in with a pinned checksum |
| Reverse proxy and TLS | **Caddy** (automatic certificates) |
| Hosting | An EU host (Hetzner) with Docker Compose: app, Postgres, Caddy |
| Transactional email | An EU provider over SMTP (Brevo), on a delegated sending subdomain with DKIM and DMARC |
| CI | GitLab CI running the same Makefile targets as developers: lint → test → build → publish |
| Tool versions | **mise** (`mise.toml`), the same versions pinned in CI and the Dockerfile |
| Duplication | **jscpd** over Go and TypeScript |

## The marketing site

| Purpose | Choice | Why |
|---|---|---|
| Framework | **Astro** (static output) | Pages are HTML at build time: fast, nothing to operate, no client framework needed. |
| Hosting | **Cloudflare Pages** | Global CDN, free TLS, the visitor's country for market selection. |
| Server logic | **Pages Functions** (`functions/`) | The `/` redirect by language and country; a first-party analytics proxy. |
| Deploy | **wrangler** (pinned), API token | `wrangler pages deploy` after a placeholder check. |
| Analytics | **Plausible** (`@plausible-analytics/tracker`, bundled, events proxied through the site's own domain) | Cookieless, no consent banner, no third-party requests. |
| Font | **Inter**, self-hosted | Same as the app. |
| Language | **TypeScript** strictest, `astro check` | Typed dictionaries per language. |
| Tests | **Vitest** + **fast-check** (logic, dictionaries, built pages, claims against the app's code), **Playwright** in a container against `wrangler pages dev` | Every variant at phone, tablet and desktop widths. |
| Lint | **ESLint** strict-type-checked + **eslint-plugin-astro** | |
| Security | `public/_headers`: strict CSP (`'self'` only, no inline script or style), HSTS | |

Details of how the site is built and tested: [astro-cloudflare-pages.md](astro-cloudflare-pages.md).
Details of the app's gate: [go-react-postgres.md](go-react-postgres.md).

## When to choose differently

- **Mostly content, little app:** the Astro site alone, maybe with a few functions.
- **Realtime collaboration:** add a websocket layer or a sync engine; reconsider the SPA's data layer.
- **Heavy data or ML work:** Python for that part (with the Python row of the capability table), next
  to or instead of the Go backend.
- **Mobile first:** a native or cross-platform client; the Go API and its OpenAPI spec still fit.
- **A team that knows another stack well:** that usually beats this list. Keep the method (gate,
  real-service tests, review loop), change the tools.
