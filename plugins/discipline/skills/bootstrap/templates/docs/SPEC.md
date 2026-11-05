# <PROJECT>: product and technical specification

The source of truth for behaviour. Read the relevant section before changing behaviour; update it in
the same change. `docs/decisions/` records why each rule exists.

## 0. Purpose

Why the product exists, above the level of features. It guides the judgement calls no rule settles, and
every proposal is checked against it. Keep it to a few lines; change it only with the user, and record
the change in `docs/decisions/`.

- **Problem:** <!-- ADAPT: the problem it solves, for whom, in one or two sentences. -->
- **Users:** <!-- ADAPT: who uses it, and who pays for it if that differs. -->
- **Success looks like:** <!-- ADAPT: two to four observable measures, e.g. "an invoice is sent within
  two minutes of finishing the work", "no support request about rounding". -->
- **Non-goals:** <!-- ADAPT: what it deliberately is not and will not do, each with the reason, e.g.
  "not an accounting system: exports to one instead". A feature that crosses a non-goal needs the
  user's decision first. -->

## 1. Glossary

<!-- Every domain term, defined once. Code, UI and docs use these words. -->

## 2. Roles and permissions

<!-- A table: action × role. -->

## 3. Domain rules

<!-- One numbered subsection per area (e.g. 3.1 Money, 3.2 Currency, 3.3 Time units, …). For each:
the rules, the validation (with error codes), the API endpoints, the edge cases, and the tests that pin
them. Mark country- or customer-specific behaviour as configuration or a module, never a branch.
Write each rule so that a reviewer can check the code against it: the condition, the result, the
boundaries, and a worked example with numbers where there is arithmetic. When `specRules` is on in
.agents/profile.json, start each rule with its ID in bold (R-<section>.<number>, e.g. the second rule
of 3.2 gets the ID R- followed by 3.2.2), never reuse an ID, and name the ID in every test that pins
the rule; the gate fails on a rule no test names. -->

## 4. Architecture

<!-- Layers and what each may import; data stores; jobs; deployment. -->

## 5. Conventions

<!-- UI patterns, formats, localisation, error shapes. -->

## 6. Quality workflow

The gate, the slow suites and the review loop (see CLAUDE.md and /discipline:working).

## 7. Phases

<!-- What is built, what is next, what is deliberately out of scope. -->
