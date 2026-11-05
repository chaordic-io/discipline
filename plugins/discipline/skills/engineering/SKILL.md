---
name: engineering
description: The engineering principles E1–E10 (how we build, whatever the stack) - few moving parts, one source of truth per contract, invariants enforced by the platform, exact domain types, testing against real services, dependencies as liabilities, secure by default, built for the profile's users, observable with quiet logs, AI engineered like code. Use when designing or changing code, choosing how to implement something, writing a proposal or decision, or reviewing code, and whenever an E-number is cited.
---
# How we build: the engineering principles

The engineering principles that apply to every change, whatever the stack. The way of working
(/discipline:working) is how we work: the request loop, verification, delegation; this is how we
build. The short, binding form of the most important ones is in the project's `CLAUDE.md`; this gives
the reasoning. A project adds its own principles (E11 onwards) in `.agents/ENGINEERING.md`.

Each principle has an ID. Cite it where it decides something: in a decision in `docs/decisions/` ("the
job is enqueued in the same transaction: E3"), in a review finding's title, in a proposal. The stack
was chosen to make these easy (the stack-selection criteria S1–S7, /discipline:stack); when the
stack makes one hard, record how it is covered instead.

**E1. Few moving parts, in the system and in the code.** Every new language, runtime, service and data store must earn its place:
something the product needs that the existing parts can't do well at the expected size. Prefer one
deployable unit and one data store that does several jobs (storage, isolation, queue, search) until
scale or a real requirement says otherwise. Content that doesn't change per request is built
statically, so there is no runtime to operate. The same holds inside the code: don't express a rule,
a case or anything else in a new way when an existing, adequate composition, abstraction or
configuration achieves the same with little or no compromise. A new abstraction, layer, option or
special case earns its place with a second use, a stated need (the spec, a decision, the roadmap) or a
boundary the architecture requires.

**E2. One source of truth per contract, everything else generated.** Each contract (database schema
and queries, API, events, a library's exports) is defined once; types, clients and documentation are
generated from it, committed, and checked current by the gate. Hand-written copies of a contract are
where drift starts. The same holds for concepts: one rule, defined once, reused by every consumer.

**E3. Let the platform enforce the invariants.** Whatever the data store, the type system or the
framework can enforce, it should: constraints, foreign keys, tenant isolation at the data layer,
transactions around multi-step writes, background work enqueued in the same transaction as the
business change. A rule enforced only by application code is a rule one code path will skip.

**E4. Exact domain types.** Money as integer minor units with a currency; decimal arithmetic for rates;
explicit time zones and dates distinct from instants; identifiers that can't be guessed or enumerated.
Country- or customer-specific behaviour is configuration or a module chosen by data, never a branch in
general code.

**E5. Test against the real thing.** Every external dependency (database, queue, mail, object storage,
validators) runs as a container in tests; the real service, never a mock of it. Property-based and fuzz
tests for anything with an invariant. Outputs that matter (documents, exports, generated code) are
deterministic, so they can be tested by rendering and comparing. A dependency that can't run locally
(a third-party API, a hosted model) is tested on recorded real responses, and against the live service
in a separate, slower suite.

**E6. Dependencies are liabilities.** The standard library first; then a dependency only when it saves
real work, and only one that is maintained, widely used and narrow in scope. Every new dependency is a
decision with a reason. Lockfiles are committed and CI installs from them; every tool version is pinned
in one place that developers, CI and images all use; images and CI actions are pinned by digest.

**E7. Secure by default.** Current algorithms without configuration (password hashing, TLS), rate
limiting, authorization checked where the action happens, a front end that works under a strict
content security policy (no inline script or style), no third-party requests from users' browsers
(self-hosted fonts and assets, first-party analytics), minimal non-root runtime images. Data residency
and hosting follow the profile's sensitive data (`.agents/profile.json`).

**E8. Built for the profile's users from the start.** If the profile lists several languages: message
catalogues, a lint rule against hard-coded user-visible text, locale-aware formatting of dates, numbers
and money, and every language written for its market. For any UI: accessible components (keyboard,
screen reader) as the base layer, not an afterthought. Retrofitting either costs more than building it
in.

**E9. Observable, with quiet logs.** Every server process and background job emits traces, metrics
and structured logs, so any failure can be followed from the user's request to its cause.
- **Traces:** one trace per request or job, propagated across process boundaries and queues. Trace IDs
  appear in every log line and in error responses, so a user's report leads straight to its trace.
  Sample successful traces if volume demands it; keep every failed one. Use a vendor-neutral standard
  (OpenTelemetry) so the backend can change.
- **Metrics:** at least rate, errors and duration per endpoint and per job type, and the depth and age
  of every queue: enough to see a regression before a user reports it.
- **Logs record real failures only:** a broken invariant, a failed dependency, a bug. Expected outcomes
  (a validation failure, not found, access denied, a retry that succeeds) are not errors and are not
  logged as errors; they show in traces and metrics. Each failure is logged once, with its context,
  where it is handled, not at every layer it passes through. No warnings nobody acts on: a message is
  actionable or it is not logged.
- **Clients report their failures too:** when there is a UI, unhandled errors and failed requests in
  the browser or app are reported through the product's own endpoint (E7: no third-party requests),
  with the trace ID where there is one.
- **No secrets or personal data** in logs, traces or metric labels (E7); what counts as personal
  follows the profile's `data`.
- **The quiet is testable:** because an error log means a real failure, tests fail on error logs they
  did not expect, and tests of failure paths assert the one error log (or error span) they expect.

**E10. AI components are engineered like code: versioned, evaluated, constrained.** Applies when the
profile's `ai` lists a mode: `rag` (answers from retrieved documents), `assistive` (suggests or
drafts; a person decides) or `agentic` (acts through tools, in several steps). A product may have
several.
- **Prompts are code.** Prompts, system instructions, tool definitions and output schemas live in the
  repository, one file per prompt, reviewed and versioned like code. Every call records the prompt
  version it used.
- **Models are pinned dependencies (E6).** An exact model version, never a "latest" alias;
  generation parameters in code. A model upgrade is a change like a dependency upgrade: it goes through
  the evals and gets a decision in `docs/decisions/`, as does the choice of provider.
- **Evals are the tests for behaviour, one facet per stage.** Each prompt has an eval set:
  representative, edge and adversarial cases, and every failure seen in production (as a bug becomes a
  regression test). The facets follow the mode, so a failure can be traced to its stage:
  - `rag`: **query** (rewriting, filters, intent), **retrieval** (the right documents in the top
    results; nothing the user may not see), **answer** (grounded in what was retrieved, correct
    citations, says so when the documents don't answer);
  - `assistive`: **output** (correct, complete, in the required format and tone);
  - `agentic`: **task** (end-to-end success), **trajectory** (the right tools with the right
    arguments, within the step and cost budget), **safety** (no action without its permission or
    confirmation; sensible recovery from tool errors).

  Checks are deterministic where possible (schema, required facts, forbidden content); where judgement
  is needed, a model grades against a rubric, and the grader is checked against human labels. Results
  are recorded per prompt and model version, with thresholds; a change that scores below them doesn't
  ship.
- **The spec states the intended behaviour.** What the AI must and must never do is written as spec
  rules; eval cases cite them as tests do.
- **Plumbing tested without the model (E5).** Tests of the code around the model use recorded real
  responses (including refusals, malformed output, timeouts and rate limits): fast and deterministic.
  Live calls happen in the evals.
- **Structured, validated, untrusted output.** Output requested in a schema or through tools and
  validated on every call. Model output is untrusted input: escaped before rendering, never executed or
  used unchecked in queries, commands, URLs or paths.
- **Prompt injection is a given (E7).** Content that isn't ours (user text, documents, web pages, tool
  results) may carry instructions and is kept apart from ours; tools get the least privilege they need
  and check authorization themselves; irreversible or outward-facing actions need a confirmation
  outside the model; no secrets in prompts; no data leaks through links, images or tool arguments.
  Agents run with a step limit, a cost limit, and a sandbox for anything that executes.
- **Data sent to providers follows the profile's `data`:** what may be sent, the provider's retention,
  training and processing-location terms, and redaction of personal data in stored prompts and
  responses.
- **Budgets and failure handling.** Limits on tokens, latency and cost per request; timeouts; retries
  with backoff for retryable errors only; caching where the provider supports it; a defined behaviour
  when the model is down, refuses or returns something invalid. The product degrades; it doesn't break.
- **Observable (E9).** Each call is a span with the prompt version, model, token counts, latency, cost,
  tool calls and outcome; user feedback is linked to the trace, so production failures become eval
  cases.
- **Retrieval is versioned too.** The corpus, chunking and embedding model are versioned and
  re-indexing is reproducible; retrieval applies the product's access rules (tenant, role); deleted
  documents leave the index.
