export const meta = {
  name: 'review-loop',
  description: 'Incremental review: stale units → multi-lens review → batched verify → fix → diff-only re-review → ledger',
  whenToUse: 'After a phase or sizeable feature, or as a periodic sweep. Each run reviews up to maxUnits stale units (never-reviewed first). Args: { maxUnits?: number (default 8), stopAt?: number (opt-in: weekly usage % at which to stop gracefully; no guard when omitted), units?: string[], lenses?: string[], maxDelta?: number (default 2), reviewModel?: string }. Progress: `python3 scripts/review/review.py status`.',
  phases: [
    { title: 'Plan', detail: 'pick stale (unit, lens) pairs from the ledger; snapshot the tree' },
    { title: 'Review', detail: 'one read-only agent per unit, applying every pending lens checklist' },
    { title: 'Verify', detail: 'one skeptic per unit refutes that unit’s findings in a batch' },
    { title: 'Fix', detail: 'one fixer for all confirmed findings; lint + the affected tests at the end (the full gate runs after the loop)' },
    { title: 'Delta', detail: 'review only the fixer’s diff; fix again if needed' },
    { title: 'Record', detail: 'append outcomes to history, mark reviewed pairs in the ledger' },
  ],
}

// Design notes (token economy):
// - The ledger (.claude/review/ledger.json) stores, per unit and lens, the content hash it was
//   last reviewed at. Unchanged code is never re-reviewed; the whole repo is covered over runs.
// - One reviewer per unit applies several lenses, so the unit's files are read once, not 5×.
// - Every previously reported finding in a unit (fixed or rejected) is shown to its reviewer via
//   `review.py show`, so nothing is re-reported and rejections stay rejected.
// - Verification is batched per unit; after fixing, only the diff is re-reviewed.

const A = args || {}
const maxUnits = A.maxUnits || 8
const maxDelta = A.maxDelta === undefined ? 2 : A.maxDelta
const stopAt = A.stopAt || null // opt-in per run; unset = no usage guard
const reviewOpts = A.reviewModel ? { model: A.reviewModel } : {}
const RP = 'python3 scripts/review/review.py'

// ---------------------------------------------------------------- Project configuration
// ADAPT: the only project-specific part of this workflow. Fill in every field for your repository;
// nothing below this block names a project, a stack or a command. Worked examples for two stacks are
// in the bootstrap kit's stacks/ folder (go-react-postgres.md, astro-cloudflare-pages.md).
const PROJECT = {
  name: '<PROJECT>',
  // Where reviewers, verifiers and fixers find the rules and the intended behaviour.
  docs: 'CLAUDE.md and docs/SPEC.md',
  // The full gate. The loop does not run it: whoever started the loop runs it once afterwards.
  gate: 'make check',
  // The fixer's gate: everything static, plus the tests affected by its changes. Much faster than
  // the full gate, which the caller still runs once after the loop.
  fixGate: '`make lint test-scripts`',
  // How the fixer finds and runs the tests affected by its changes.
  affectedTests: 'the test files covering the files you changed, and those of modules importing them',
  // House rules the fixer must follow, in one sentence.
  fixRules: 'Follow CLAUDE.md strictly (tests for every change, property/fuzz tests where applicable, real services instead of mocks for external systems, never weaken lint configs, no unexplained lint suppressions). Update docs/SPEC.md if behaviour changes.',
  // Cheap checks the fixer should prefer while iterating.
  targetedChecks: 'the single test files or packages you touched, and the linter for the touched part of the repo',
  // Files a reviewer may check by script instead of reading line by line ('' for none), e.g. translation catalogues.
  scriptCheckable: '',
  // What the diff-only review of the fixer's changes looks for, beyond the lens checklists.
  deltaFocus: 'bugs or regressions introduced, new code without tests (or tests that don\'t assert the behaviour), hard-coded user-visible strings or missing translations, new duplication, security problems, layering violations',
}

// Lens → checklist. Keep in sync with "lenses" in scripts/review/units.json.
const LENS_FILE = {
  security: '.claude/agents/security-auditor.md',
  tests: '.claude/agents/test-coverage-reviewer.md',
  architecture: '.claude/agents/architecture-reviewer.md',
  duplication: '.claude/agents/duplication-reviewer.md',
  localisation: '.claude/agents/localisation-reviewer.md',
}
const LENSES = Object.keys(LENS_FILE)

const QUOTA = {
  type: 'object',
  properties: {
    ok: { type: 'boolean' },
    known: { type: 'boolean' },
    week: { type: ['number', 'null'] },
    ageSeconds: { type: 'number' },
  },
  required: ['ok', 'known'],
}

const PLAN = {
  type: 'object',
  properties: {
    quota: QUOTA,
    open: { type: 'array', items: { type: 'object' } },
    selected: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          unit: { type: 'string' },
          lenses: { type: 'array', items: { type: 'string', enum: LENSES } },
          reason: { type: 'string' },
          files: { type: 'number' },
          since: { type: 'string', description: 'git tree the unit was last fully reviewed at; present => diff-only review' },
          changed: { type: 'array', items: { type: 'string' }, description: 'with since: the unit files changed since then (copy verbatim)' },
        },
        required: ['unit', 'lenses', 'reason'],
      },
    },
    remainingUnits: { type: 'number' },
    uncovered: { type: 'array', items: { type: 'string' } },
  },
  required: ['quota', 'open', 'selected', 'remainingUnits', 'uncovered'],
}

const FINDING = {
  type: 'object',
  properties: {
    lens: { type: 'string', enum: LENSES },
    severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low'] },
    file: { type: 'string' },
    line: { type: 'number' },
    title: { type: 'string' },
    scenario: { type: 'string' },
    fix: { type: 'string' },
  },
  required: ['lens', 'severity', 'file', 'title', 'scenario', 'fix'],
}

const REVIEW = {
  type: 'object',
  properties: {
    findings: { type: 'array', items: FINDING },
    coverage: {
      type: 'array',
      items: {
        type: 'object',
        properties: { lens: { type: 'string', enum: LENSES }, summary: { type: 'string' } },
        required: ['lens', 'summary'],
      },
    },
    skipped: { type: 'array', items: { type: 'string' }, description: 'unit files you did not read in full' },
  },
  required: ['findings', 'coverage', 'skipped'],
}

const VERDICTS = {
  type: 'object',
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: { index: { type: 'number' }, real: { type: 'boolean' }, reason: { type: 'string' } },
        required: ['index', 'real', 'reason'],
      },
    },
  },
  required: ['verdicts'],
}

const FIXED = {
  type: 'object',
  properties: {
    fixed: { type: 'array', items: { type: 'string' } },
    rejected: {
      type: 'array',
      items: {
        type: 'object',
        properties: { id: { type: 'string' }, justification: { type: 'string' } },
        required: ['id', 'justification'],
      },
    },
    gatePassing: { type: 'boolean' },
    gateFailures: { type: 'array', items: { type: 'string' } },
  },
  required: ['fixed', 'rejected', 'gatePassing', 'gateFailures'],
}

const RECORDED = {
  type: 'object',
  properties: { ok: { type: 'boolean' }, status: { type: 'string', description: 'verbatim output of review.py status' } },
  required: ['ok', 'status'],
}

const describe = (f) =>
  `[${f.id}] (${f.lens}/${f.severity}) ${f.title} @ ${f.file}${f.line ? ':' + f.line : ''}\n  scenario: ${f.scenario}\n  fix: ${f.fix}` +
  (f.verdict ? `\n  verifier: ${f.verdict}` : '')

const fixPrompt = (items) => `You are fixing review findings in the ${PROJECT.name} repo. ${PROJECT.fixRules}

Findings:
${items.map(describe).join('\n')}

Fix each one. Reject a finding only with a concrete written justification (it contradicts the spec, it is already handled, or the fix would be harmful).
Keep tool output small to save tokens: while iterating run only targeted checks (e.g. ${PROJECT.targetedChecks}). When done, run your gate ONCE: ${PROJECT.fixGate} plus ${PROJECT.affectedTests}. Redirect output to a log file and inspect failures with grep/tail rather than printing whole logs; fix and re-run until it passes. Do NOT run the full \`${PROJECT.gate}\`: it runs once after the loop.
Report the ids fixed (each entry in \`fixed\` must be exactly an id such as \`api-orgs#3\`, nothing else), the ids rejected with justification, whether your gate passes (\`gatePassing\`, with the commands you ran listed in \`gateFailures\` only if they fail), and any remaining failures (concise). Tests you could not run because the environment blocks them (for example unreachable test containers) are not failures of your code: list them in \`gateFailures\` prefixed "not run:".`

// Skeptical batch verification. Confirmed findings are flagged `confirmed` so that, if their fix is
// deferred, a later run can fix them without verifying them again.
const verify = (findings, scope) =>
  agent(
    `You are a skeptical senior engineer verifying code-review findings (${scope}) of the ${PROJECT.name} repo (read-only; do not modify files).
For EACH finding below, try to REFUTE it by reading the actual code, ${PROJECT.docs}. real=true only if the problem genuinely exists in the current code and the fix is worthwhile for this project. If uncertain, a matter of taste, or already handled elsewhere, real=false. Give a short reason either way. Return one verdict per finding, using its index.

${findings.map((f, i) => `#${i} ${describe(f)}`).join('\n\n')}`,
    { label: `verify:${scope}`, phase: 'Verify', schema: VERDICTS },
  ).then((v) => {
    const byIdx = new Map(((v && v.verdicts) || []).map((x) => [x.index, x]))
    return findings.map((f, i) => {
      const x = byIdx.get(i)
      const real = x ? x.real : null
      return { ...f, real, confirmed: real === true, verdict: x ? x.reason : 'not verified' }
    })
  })

// Weekly usage guard (opt-in via args.stopAt): reads the status-line snapshot (review.py quota).
// Unknown usage never blocks.
const quotaOk = async (where) => {
  if (!stopAt) return true
  const q = await agent(
    `Run exactly \`${RP} quota --stop-at ${stopAt}\` from the repository root and return its JSON output unchanged. Do nothing else.`,
    { label: `quota:${where}`, phase: 'Fix', schema: QUOTA, effort: 'low' },
  )
  if (!q) return true
  if (q.known && q.ageSeconds > 1800) log(`usage snapshot is ${Math.round(q.ageSeconds / 60)} min old (week ${q.week}%) — proceeding`)
  if (!q.ok) log(`weekly usage ${q.week}% ≥ ${stopAt}% — stopping gracefully before ${where}`)
  return q.ok
}
let stoppedForQuota = false

// ---------------------------------------------------------------- Plan
phase('Plan')
const planArgs = [`--max-units ${maxUnits}`]
  .concat((A.units || []).map((u) => `--unit ${u}`))
  .concat((A.lenses || []).map((l) => `--lens ${l}`))
  .join(' ')
const plan = await agent(
  `Run exactly this command from the repository root and return its JSON output as the structured result, unchanged: \`${RP} plan ${planArgs} --stop-at ${stopAt || 101}\`. Do not run anything else and do not modify files.`,
  { label: 'plan', phase: 'Plan', schema: PLAN, effort: 'low' },
)
if (!plan) return { aborted: true, reason: 'plan agent failed' }
if (stopAt) log(`weekly usage: ${plan.quota.known ? plan.quota.week + '%' : 'unknown'} (stop at ${stopAt}%)`)
if (stopAt && !plan.quota.ok) return { stoppedForQuota: true, week: plan.quota.week, stopAt, remainingUnits: plan.remainingUnits + plan.selected.length }
// Open findings from earlier runs: only those a verifier confirmed (fix deferred) go straight to
// the fixer; the rest (unverified, or found by a delta review) are verified again below.
const openRows = plan.open.map((f, i) => ({ ...f, id: `open#${i + 1}` }))
const carried = openRows.filter((f) => f.confirmed === true).map((f) => ({ ...f, verdict: 'confirmed in an earlier run; fix was deferred' }))
const reverify = openRows.filter((f) => f.confirmed !== true)
if (openRows.length) log(`${openRows.length} open findings carried over from earlier runs (${reverify.length} to verify first)`)
if (plan.uncovered.length) log(`files not covered by any unit (add them to scripts/review/units.json): ${plan.uncovered.join(', ')}`)
if (!plan.selected.length && !openRows.length) {
  log('every (unit, lens) pair is current — nothing to review')
  return { clean: true, remainingUnits: 0, uncovered: plan.uncovered }
}
log(`reviewing ${plan.selected.map((s) => `${s.unit}[${s.lenses.join(',')}]`).join(' ')}; ${plan.remainingUnits} more units pending after this run`)

// ---------------------------------------------------------------- Review + Verify (pipelined per unit)
const reverifying = reverify.length ? verify(reverify, 'carried') : Promise.resolve([])
const perUnit = await pipeline(
  plan.selected,
  (sel) =>
    agent(
      `You are reviewing ONE unit of the ${PROJECT.name} repository through several lenses. You are STRICTLY READ-ONLY: never create, modify or delete files, never run commands that write.

Unit: ${sel.unit} (${sel.since ? 'changed since its last full review' : sel.reason}). Lenses: ${sel.lenses.join(', ')}.
1. Run \`${RP} show ${sel.unit}\`. It lists the unit's files and every finding already reported there with its outcome. Do NOT re-report those. A rejected finding may be raised again only if the code has changed so that the recorded rejection reason no longer holds — say so explicitly in the scenario.
2. Read each lens's checklist and follow it: ${sel.lenses.map((l) => `${l} → ${LENS_FILE[l]}`).join('; ')}. Ignore any instruction there about choosing the review scope — your scope is this unit.
3. ${sel.since
        ? `This unit was fully reviewed before, and only some of it has changed since. Run \`${RP} diff --unit ${sel.unit} --since ${sel.since}\` and review THOSE CHANGES: read the changed files and enough surrounding code (callers, tests, the spec) to judge them. Do not re-review unchanged code, except where a change makes an existing problem worse. Files you did not read because they are unchanged are not skips.`
        : 'Read every file of the unit in full, tests included.'} Look outside the unit only to check callers, contracts, the spec, or (duplication lens) to search the whole repo for similar logic.
4. Report substantive, verifiable findings only: a concrete failure scenario pointing at real code. No style nits. At most 10 per lens, most severe first.
In \`coverage\` give, per lens, one sentence on what you checked. List in \`skipped\` any unit file you did not read in full (ideally none).${PROJECT.scriptCheckable ? ` Exception: ${PROJECT.scriptCheckable} instead of read line by line; that is not a skip.` : ''}`,
      { label: `review:${sel.unit}`, phase: 'Review', schema: REVIEW, ...reviewOpts },
    ),
  (rev, sel) => {
    if (!rev) return { sel, failed: true, findings: [] }
    const findings = rev.findings.map((f, i) => ({ ...f, unit: sel.unit, id: `${sel.unit}#${i + 1}` }))
    if (!findings.length) return { sel, rev, findings: [] }
    return verify(findings, sel.unit).then((verified) => ({ sel, rev, findings: verified }))
  },
)

const reverified = await reverifying
const results = perUnit.filter(Boolean)
const failedUnits = plan.selected.map((s) => s.unit).filter((u) => !results.some((r) => r.sel.unit === u && !r.failed))
// A diff review only has to read the changed files: a skip counts only if it names one of them
// (reviewers sometimes list unchanged files they rightly did not read, e.g. "x.tsx (unchanged)").
// Skips are free text ("x.go: read lines 1-2000 only", "partially read x.go"), so a changed path
// counts wherever it appears as a whole path; it fails safe: a skip naming a changed file is never dropped.
// `changed` lists only files that still exist (review.py changed_files), so a deleted file is never a skip.
const realSkips = (r) => {
  const skipped = (r.rev && r.rev.skipped) || []
  if (!r.sel.since || !Array.isArray(r.sel.changed)) return skipped
  const names = (s, p) => new RegExp(`(^|[^\\w.-])${p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}($|[^\\w./-]|[.](?![\\w/-]))`).test(s)
  return skipped.filter((s) => r.sel.changed.some((p) => names(s, p)))
}
const partialUnits = results.filter((r) => r.rev && realSkips(r).length).map((r) => r.sel.unit)
if (failedUnits.length) log(`review failed for: ${failedUnits.join(', ')} — they stay unmarked`)
if (partialUnits.length) log(`partial review (files skipped) for: ${partialUnits.join(', ')} — they stay unmarked`)

const all = results.flatMap((r) => r.findings).concat(reverified)
const confirmed = all.filter((f) => f.real === true)
const rejectedByVerifier = all.filter((f) => f.real === false)
const unverified = all.filter((f) => f.real === null)
log(`${all.length} findings: ${confirmed.length} confirmed, ${rejectedByVerifier.length} refuted, ${unverified.length} unverified`)

// ---------------------------------------------------------------- Fix + delta review
const outcomes = []
const record = (f, status, reason) =>
  outcomes.push({
    unit: f.unit || null, lens: f.lens, severity: f.severity, file: f.file, line: f.line || null, title: f.title, status,
    reason: (reason || '').slice(0, 300),
    // Open findings keep their details so a later run can fix them without re-reviewing.
    // `confirmed` lets the next run skip re-verification only for verifier-confirmed findings.
    ...(status === 'open' ? { scenario: f.scenario, fix: f.fix, confirmed: f.confirmed === true } : {}),
  })
rejectedByVerifier.forEach((f) => record(f, 'rejected', f.verdict))
unverified.forEach((f) => record(f, 'open', 'verifier gave no verdict'))

let gate = { gatePassing: null, gateFailures: [] }
let toFix = carried.concat(confirmed)
const deltaHistory = []
// True while the latest fixer pass has not been followed by a successful delta review.
let unreviewedFix = false
for (let d = 0; toFix.length; d++) {
  phase('Fix')
  if (!(await quotaOk(d === 0 ? 'fix' : `fix:delta${d}`))) {
    stoppedForQuota = true
    toFix.forEach((f) => record(f, 'open', `deferred: weekly usage guard (${stopAt}%)`))
    break
  }
  const fix = await agent(fixPrompt(toFix), { label: d === 0 ? 'fix' : `fix:delta${d}`, phase: 'Fix', schema: FIXED })
  if (!fix) {
    toFix.forEach((f) => record(f, 'open', 'fixer failed'))
    log('fixer failed — findings recorded as open')
    break
  }
  gate = fix
  unreviewedFix = true
  // Fixers sometimes report "id: what I did" instead of the bare id; match on the leading id.
  const idOf = (x) => { const m = /^\s*\[?([\w.-]+#\d+)/.exec(String(x)); return m ? m[1] : String(x).trim() }
  const fixedIds = new Set(fix.fixed.map(idOf))
  const rej = new Map(fix.rejected.map((r) => [idOf(r.id), r.justification]))
  toFix.forEach((f) => (rej.has(f.id) ? record(f, 'rejected', `fixer: ${rej.get(f.id)}`) : record(f, fixedIds.has(f.id) ? 'fixed' : 'open', fixedIds.has(f.id) ? '' : 'fixer did not report it')))
  const unreported = toFix.filter((f) => !fixedIds.has(f.id) && !rej.has(f.id)).length
  if (unreported) log(`fixer did not report ${unreported} of ${toFix.length} findings — recorded as open for the next run`)

  phase('Delta')
  if (!(await quotaOk(`delta${d + 1}`))) {
    stoppedForQuota = true
    log('fixer changes not delta-reviewed — reviewed units stay unmarked so they are re-checked later')
    failedUnits.push(...plan.selected.map((s) => s.unit))
    break
  }
  const delta = await agent(
    `You are reviewing ONLY the changes a fixer just made to the ${PROJECT.name} repo. You are STRICTLY READ-ONLY.
Run \`${RP} diff\` to see every change since the review snapshot. Review those changes through every lens (checklists: ${Object.values(LENS_FILE).join(', ')}): ${PROJECT.deltaFocus}.
Ignore pre-existing issues outside the changed lines unless the change makes them worse. Already raised in earlier delta passes (do not repeat): ${JSON.stringify(deltaHistory)}
High bar: report only problems you have confirmed by reading the code, with a concrete failure scenario.`,
    { label: `delta:${d + 1}`, phase: 'Delta', schema: REVIEW, ...reviewOpts },
  )
  if (!delta) {
    log('delta review failed — fixer changes are not re-reviewed; units stay unmarked for safety')
    failedUnits.push(...plan.selected.map((s) => s.unit))
    break
  }
  unreviewedFix = false
  toFix = delta.findings.map((f, i) => ({ ...f, id: `delta${d + 1}#${i + 1}` }))
  deltaHistory.push(...toFix.map((f) => `${f.file}: ${f.title}`))
  log(`delta ${d + 1}: ${toFix.length} findings in the fixer's changes`)
  if (toFix.length && d + 1 >= maxDelta) {
    toFix.forEach((f) => record(f, 'open', 'found in delta review after the last fix pass'))
    log(`delta limit reached — ${toFix.length} findings recorded as open`)
    break
  }
}

// ---------------------------------------------------------------- Record
phase('Record')
// Never advance ledger pairs over fixer edits that no delta review has seen.
const noAdvance = unreviewedFix
const markPairs = results
  .filter((r) => !r.failed && r.rev && !realSkips(r).length && !failedUnits.includes(r.sel.unit))
  .flatMap((r) => r.sel.lenses.map((l) => `${r.sel.unit}:${l}`))
const rec = await agent(
  `From the repository root, do exactly these steps and nothing else:
1. Write this JSON verbatim to .claude/review/outcomes.tmp.json (use a quoted heredoc so nothing is interpolated):
${JSON.stringify(outcomes)}
2. Run \`${RP} record .claude/review/outcomes.tmp.json && rm .claude/review/outcomes.tmp.json\`
3. Run \`${RP} mark ${noAdvance ? '--no-advance ' : ''}${markPairs.join(' ')}\`
4. Run \`${RP} status\` and return its output verbatim as \`status\`. ok=true only if every command succeeded.`,
  { label: 'record', phase: 'Record', schema: RECORDED, effort: 'low' },
)

return {
  stoppedForQuota,
  reviewed: plan.selected.map((s) => s.unit),
  marked: markPairs.length,
  failedUnits,
  partialUnits,
  remainingUnits: plan.remainingUnits,
  // The fixer's gate (lint + affected tests); the full gate still has to run once afterwards.
  gate: { scope: 'lint + affected tests', passing: gate.gatePassing, failures: gate.gateFailures, next: `run ${PROJECT.gate}` },
  counts: {
    found: all.length,
    fixed: outcomes.filter((o) => o.status === 'fixed').length,
    rejected: outcomes.filter((o) => o.status === 'rejected').length,
    open: outcomes.filter((o) => o.status === 'open').length,
  },
  outcomes,
  recordOk: !!(rec && rec.ok),
  status: rec ? rec.status : 'record step failed — run review.py status',
}
