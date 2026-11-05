---
name: bootstrap
description: Set a repository up with the discipline working method - copy the templates, ask the product, stack and working questions, choose the review lenses from the project profile, fill in CLAUDE.md, the handover folder and the review configuration, wire the gate, and record the decisions. Run once per repository, when the user asks to set it up.
disable-model-invocation: true
---
# Set up a repository

Work through these steps in order. Ask the user only in steps 3, 5 and 6, each time as **one batch**
of questions with concrete options and a recommendation for each (the recommended option first),
saying what each answer changes. Skip a question the repository already answers, and say what you
found instead. Decide everything else yourself, and record it.

Background, read when a step needs it: [`reference/setup.md`](reference/setup.md) (the reviewers and
when they run, designing review units, the gate, the usage guard) and
[`reference/review-loop.md`](reference/review-loop.md) (running the review loop).

1. **Check the prerequisites.** `discipline --version` must work (the plugin puts it on the PATH;
   it needs Python 3.10+, or uv to fetch one). The repository must be a git repository. If it is
   already set up and you are a new teammate, don't bootstrap: run `discipline work` on your branch and
   create your `.agents/USER.local.md` (`discipline init` adds it, and nothing else that exists).
2. **Copy the templates:** `discipline init --dry-run`, then `discipline init`. Existing files are kept
   and listed; merge them by hand with the templates (`discipline doc bootstrap` and the plugin's
   `skills/bootstrap/templates/`). It also enables the plugin for the repository in
   `.claude/settings.json`, so everyone who opens it gets the same reviewers and workflow.
3. **Ask the product questions** (batch 1 below). If code exists, look at it first and propose the
   answers it implies, for the user to confirm or correct.
4. **Choose the reviewers:** write the answers into `.agents/profile.json` and run
   `discipline lenses apply`. Show the user its output (each lens, on or off, and why) and change the
   profile until they agree.
5. **Ask the stack questions** (batch 2). Use /discipline:stack: its criteria S1–S7, shapes and
   capability checklist shape the recommendations.
6. **Ask the working questions** (batch 3).
7. **Fill in the texts:** every file `discipline init` listed as still to adapt.
   - `docs/SPEC.md` section 0 "Purpose": the problem, the users, the success measures and the
     non-goals from batch 1, in the user's terms.
   - `CLAUDE.md`: the product, the layout, the commands, the domain rules. Delete the rules that don't
     apply (the translation rule when localisation is off, the national-rules rule for one market,
     the AI rule when the product calls no models).
   - `.agents/USER.md`: the user and their preferences, in their words.
   - `.agents/ENVIRONMENT.md`: what you know about the machine.
   - `.agents/WORKING.md`: the git policy from batch 3.
8. **The review context:** fill the sections of `.agents/review-context.md` for the lenses that are on
   (layering, isolation model, test commands, expected sizes, package ecosystems, contracts,
   languages, AI features) and delete the sections of the lenses that are off. The checklists
   themselves are generic and live in the plugin.
9. **Review units:** replace the example units in `.claude/review/units.json` (see "Designing units"
   in `reference/setup.md`).
10. **The workflow's settings:** fill `.claude/review/project.json`: the gate, the fixer's gate, how to
    find affected tests, files to check by diff. The stack examples show a complete one.
11. **The gate:** create the gate command for the stack ("The gate" in `reference/setup.md`) and make
    it run `discipline check`, pinned to the plugin's version so local runs and CI agree:
    `uvx --from "git+https://github.com/chaordic-io/discipline@v<version>#subdirectory=plugins/discipline" discipline check`,
    where `<version>` is what `discipline --version` prints. Run the gate until it passes, then make CI
    run the same gate command on every push and pull request (the CI system from batch 2), so the
    gate holds whether or not an agent ran it.
12. **Optional usage guard:** `discipline init --statusline`, then the settings change in "The usage
    guard" (`reference/setup.md`).
13. **Record:** a first decision (`discipline decisions new "Working method set up with discipline <version>"`)
    with the profile, the lenses that are on and off and why, and the stack part by part with the
    selection criteria it rests on (S1–S7), the alternatives turned down, and any engineering
    principle (E1–E10) the stack makes hard; then the roadmap and the team in `.agents/STATUS.md`,
    and the continuation point in this branch's work file (`discipline work`).
14. **First review:** run `/discipline:review-loop` (with the user's go-ahead, which batch 3 may have
    given as a standing permission), then the gate. Tell the user which files are new, for them to commit unless
    batch 3 said agents may.

## Bootstrap questions

### Batch 1: the product (decides the reviewers)

| # | Question | Goes into | Recommendation |
|---|---|---|---|
| 1 | What is the product, and who is it for? What problem does it solve, how will you know it works (two to four success measures), and what is it deliberately not (non-goals)? | `profile.product`, `CLAUDE.md`, `docs/SPEC.md` section 0 "Purpose" | (free text; propose success measures and non-goals from the description for the user to confirm) |
| 2 | What kind of product is it? Several may apply: `web-app`, `mobile-app`, `desktop-app`, `internal-tool`, `static-site`, `public-api`, `backend-service`, `library`, `cli`, `data-pipeline`. | `profile.kinds` | From the description and the code. |
| 3 | Which languages do its users read, at launch and within the next year? | `profile.languages` | One language unless a market needs another at launch. Adding one later is a profile change and one command. |
| 4 | Which interfaces does a separately built or released part depend on? Several may apply: `frontend-backend`, `mobile-backend`, `public-api`, `service-to-service`, `published-library`, or none. | `profile.interfaces` | From the kinds: a web app with its own API → `frontend-backend`; a mobile app → `mobile-backend`; an API for third parties → `public-api`; several services → `service-to-service`; a published package → `published-library`; a static site or a CLI → none. |
| 5 | How much does performance matter? `critical` (budgets are part of the product), `normal` (must stay fast at expected sizes), `minor` (small data, few users). | `profile.performance` | `normal` for apps, services and pipelines; `minor` for static sites, CLIs and small internal tools. |
| 6 | What sensitive data does it hold? Personal data, payments, health data, several tenants' data, or none. | `profile.data`, the security section of the review context, `CLAUDE.md` domain rules | (from the description) |
| 7 | Does the spec carry business rules worth pinning to tests by ID (calculations, permissions, lifecycles, legal rules)? If so, which files are tests? | `profile.specRules` | Yes for apps with business rules: `{"tests": [<the test file globs>]}`. No (`null`) for content sites, CLIs and thin wrappers. |
| 8 | Does the product call AI models, and how? Any of `rag` (answers from retrieved documents), `assistive` (suggests or drafts; a person decides), `agentic` (acts through tools in several steps), or none. | `profile.ai` | From the description. An agent that searches documents is `rag` and `agentic`. |
| 9 | Should any reviewer be on or off against the rules above, and why? | `profile.overrides` | No overrides. |

### Batch 2: the stack (decides the gate and the tools)

| # | Question | Goes into | Recommendation |
|---|---|---|---|
| 1 | Is there code already? If so, the stack is what is there: confirm it, and ask only about the gaps. | `CLAUDE.md` layout | (from the repository) |
| 2 | Which languages, frameworks and data stores, part by part? | `CLAUDE.md`, the gate, `project.json`, `docs/decisions/` | Apply /discipline:stack: the shape for the profile's kinds, then one or two options per part, each with the criteria it rests on and checked against the capability checklist. What the team knows well comes first unless a criterion rules it out (S1). |
| 3 | Which data stores and external services (database, queue, mail, object storage, third-party APIs)? | real-service tests, `ENVIRONMENT.md` | Each one runs as a container in tests (testcontainers or the stack's equivalent), never mocked (E5). |
| 4 | Only if contracts are on: how is each contract written (OpenAPI, protobuf, GraphQL, JSON Schema, a library's exports), which way does generation go, and which consumers stay on old versions? | the contracts section of the review context, `units.json` context, the gate | Generate the contract from the code and the clients from the contract, and commit both; a breaking-change check against the main branch in the gate (E2). |
| 5 | Which package ecosystems, which CI system, and how is it shipped (container images, app stores, a package registry, static hosting)? | the supply-chain section of the review context, the dependencies unit, the gate | Lockfiles committed; CI installs from them; CI actions and base images pinned by digest (E6). |
| 6 | Where are tool versions pinned, and what is the gate command called? | `ENVIRONMENT.md`, `CLAUDE.md`, `project.json` (`gate`) | One version file for every tool (e.g. `mise.toml`), used by CI too; `make check`. |
| 7 | Where do traces, metrics, logs and client error reports go, and who looks at them? | `ENVIRONMENT.md` "Deployment", `CLAUDE.md` | OpenTelemetry from every server process and job to one backend the team already runs or can host where the data may live; client errors through the product's own endpoint (E9). |
| 8 | Only if `ai` lists a mode: which models and providers, under which data terms (retention, training, processing location), where prompts and eval sets live, which eval runner, and which thresholds block a change? | `profile.aiEvals`, the ai section of the review context, `docs/decisions/`, `CLAUDE.md` | Prompts in `prompts/`, one file each; eval sets in `evals/<prompt>/` with the facets of the mode (E10); models pinned to exact versions behind one client interface; a provider whose terms fit the profile's `data`. |

### Batch 3: how we work

| # | Question | Goes into | Recommendation |
|---|---|---|---|
| 1 | May agents commit, branch or push? | `.agents/USER.md`, `.agents/WORKING.md` "Git" | No: the user commits. |
| 2 | Which standing preferences in `.agents/USER.md` apply? They come from earlier projects. | `.agents/USER.md` | Read them out and keep the ones the user confirms, in their words. |
| 3 | May agents run the review loop on their own, at the end of each phase or sizeable feature, without asking each time? For everyone, or per person (each grants it in their own `.agents/USER.local.md`)? Any limits (units per run; a usage stop if capacity must be kept for other work)? | `CLAUDE.md` "Review loop" (the standing permission, with the date and any limits) | Yes, for everyone, with the default 8 units per run and no usage stop: the loop is incremental, so runs are cheap when little changed. Per person when people pay for their own usage. |
| 4 | Who works in this repository, and who answers review questions and product decisions? | `.agents/USER.md` (people and roles), `CLAUDE.md` "Review loop", `.agents/STATUS.md` | One named product owner answers product questions; with several areas, the owner of each area. Each person keeps their own preferences in `.agents/USER.local.md`, which is not committed. |

## When the product changes

A second language, a mobile client, a public API, a first AI feature: edit `.agents/profile.json`, run
`discipline lenses apply`, add the newly enabled lens to the units where it applies, fill its section
of `.agents/review-context.md`, and add a decision in `docs/decisions/`. Until then the gate fails, which
is the point.
