export const meta = {
  name: 'review-loop',
  description: 'Incremental review: stale units → multi-lens review → batched verify → fix → diff-only re-review → ledger',
  whenToUse: 'After a phase or sizeable feature, or as a periodic sweep. Each run reviews up to maxUnits stale units (never-reviewed first). Args: { maxUnits?: number (default 8), stopAt?: number (opt-in: weekly usage % at which to stop gracefully; no guard when omitted), stopAt5h?: number (opt-in: the same for the 5-hour limit), units?: string[], lenses?: string[], maxDelta?: number (default 2), reviewModel?: string }. The lenses and their checklists come from .claude/review/units.json (chosen by discipline lenses from .agents/profile.json). Progress: `discipline review status`.',
  phases: [
    { title: 'Plan', detail: 'pick stale (unit, lens) pairs from the ledger; snapshot the tree' },
    { title: 'Review', detail: 'one read-only agent per unit, applying every pending lens checklist' },
    { title: 'Verify', detail: 'one skeptic per unit refutes that unit’s findings in a batch; refuted critical/high security and supply-chain findings get a second, independent verifier; then a check that nothing was written' },
    { title: 'Fix', detail: 'one fixer for all confirmed findings; lint + the affected tests at the end (the full gate runs after the loop)' },
    { title: 'Delta', detail: 'review only the fixer’s diff; fix again if needed' },
    { title: 'Record', detail: 'append outcomes to history (questions for the user included), mark reviewed pairs in the ledger' },
  ],
}

// Design notes (token economy):
// - The ledger (.claude/review/ledger.jsonl) records, per unit and lens, the content hashes it was
//   last reviewed at. Unchanged code is never re-reviewed; the whole repo is covered over runs.
// - One reviewer per unit applies several lenses, so the unit's files are read once, not 5×.
// - Every previously reported finding in a unit (fixed or rejected) is shown to its reviewer via
//   `discipline review show`, so nothing is re-reported and rejections stay rejected.
// - Verification is batched per unit; after fixing, only the diff is re-reviewed.
// Safety notes:
// - Reviewers and verifiers run as the `review-reader` agent type, which has no file-editing tools;
//   `discipline review touched` then proves that the read-only phases changed nothing in the reviewed units.
// - A refuted critical/high finding in a SECOND_OPINION lens is rejected only if a second,
//   independent verifier also refutes it; if the two disagree, the fixer gets it.
// - A finding of kind `question` (the spec, decisions and proposals don't settle the behaviour) is
//   verified like any other, but never fixed: it is recorded for the user (`discipline review questions`).

const A = args || {}
const maxUnits = A.maxUnits || 8
const maxDelta = A.maxDelta === undefined ? 2 : A.maxDelta
const stopAt = A.stopAt || null // opt-in per run; unset = no usage guard
const stopAt5h = A.stopAt5h || null // opt-in per run: the same for the 5-hour limit
const guarded = !!(stopAt || stopAt5h)
const quotaArgs = [stopAt ? `--stop-at ${stopAt}` : '', stopAt5h ? `--stop-at-5h ${stopAt5h}` : ''].filter(Boolean).join(' ')
const reviewOpts = A.reviewModel ? { model: A.reviewModel } : {}
const RP = 'discipline review'
// The read-only agent type for reviewers and verifiers: the plugin's agents/review-reader.md, whose
// writes the plugin's PreToolUse hook (hooks/readonly_guard.py) blocks.
const READER = 'discipline:review-reader'
// Lenses whose refuted critical/high findings get a second, independent verifier: the plan's
// `secondOpinion` (the built-in ones plus custom lenses that ask for it), or these.
let SECOND_OPINION = ['security', 'supply-chain']

// ---------------------------------------------------------------- Project configuration
// Generic defaults. Each project overrides them in .claude/review/project.json, which `discipline review plan`
// passes in as `plan.project`; this script is never edited per project.
const PROJECT_DEFAULTS = {
  name: 'project',
  // Where reviewers, verifiers and fixers find the rules and the intended behaviour.
  docs: 'CLAUDE.md and docs/SPEC.md',
  // The full gate. The loop does not run it: whoever started the loop runs it once afterwards.
  gate: 'make check',
  // The fixer's gate: everything static, plus the tests affected by its changes. Much faster than
  // the full gate, which the caller still runs once after the loop.
  fixGate: 'the project\'s lint and `discipline check`',
  // How the fixer finds and runs the tests affected by its changes.
  affectedTests: 'the test files covering the files you changed, and those of modules importing them',
  // House rules the fixer must follow, in one sentence.
  fixRules: 'Follow CLAUDE.md strictly (tests for every change, property/fuzz tests where applicable, real services instead of mocks for external systems, never weaken lint configs, no unexplained lint suppressions). Update docs/SPEC.md only to describe behaviour the spec, docs/decisions/ or a proposal already settles.',
  // Cheap checks the fixer should prefer while iterating.
  targetedChecks: 'the single test files or packages you touched, and the linter for the touched part of the repo',
  // Files a reviewer may check by script or diff instead of reading line by line ('' for none), e.g.
  // lockfiles and translation catalogues.
  scriptCheckable: 'lockfiles (check them through the manifest, `git diff` and targeted searches)',
  // What the diff-only review of the fixer's changes looks for, besides the checklists of the lenses
  // involved (those are added automatically).
  deltaFocus: 'bugs or regressions introduced, new code without tests (or tests that don\'t assert the behaviour), and tests weakened or re-pinned to match the code (an expected value edited, a tolerance widened, a comparison loosened, a test skipped or deleted) without a spec change or decision behind it',
}
let PROJECT = PROJECT_DEFAULTS

const QUOTA = {
  type: 'object',
  properties: {
    ok: { type: 'boolean' },
    known: { type: 'boolean' },
    week: { type: ['number', 'null'] },
    five_hour: { type: ['number', 'null'] },
    ageSeconds: { type: 'number' },
  },
  required: ['ok', 'known'],
}

const PLAN = {
  type: 'object',
  properties: {
    lenses: { type: 'array', items: { type: 'string' }, description: 'the lenses configured in units.json' },
    secondOpinion: { type: 'array', items: { type: 'string' }, description: 'lenses whose refuted critical/high findings get a second verifier' },
    project: { type: 'object', description: 'this project\'s settings from .claude/review/project.json' },
    quota: QUOTA,
    open: { type: 'array', items: { type: 'object' } },
    selected: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          unit: { type: 'string' },
          lenses: { type: 'array', items: { type: 'string' } },
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
  required: ['lenses', 'quota', 'open', 'selected', 'remainingUnits', 'uncovered'],
}

// FINDING and REVIEW depend on the lenses, which the plan reads from units.json.
const findingSchema = (lenses) => ({
  type: 'object',
  properties: {
    lens: { type: 'string', enum: lenses },
    severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low'] },
    file: { type: 'string' },
    line: { type: 'number' },
    title: { type: 'string' },
    kind: { type: 'string', enum: ['defect', 'question'], description: 'question: the written intent does not settle the behaviour; the user decides' },
    scenario: { type: 'string', description: 'defect: the failure scenario; question: what is unclear and why it matters' },
    fix: { type: 'string', description: 'defect: the fix; question: the recommended option' },
    options: { type: 'array', items: { type: 'string' }, description: 'question only: the options, the current behaviour among them' },
  },
  required: ['lens', 'severity', 'file', 'title', 'scenario', 'fix'],
})

const reviewSchema = (lenses) => ({
  type: 'object',
  properties: {
    findings: { type: 'array', items: findingSchema(lenses) },
    coverage: {
      type: 'array',
      items: {
        type: 'object',
        properties: { lens: { type: 'string', enum: lenses }, summary: { type: 'string' } },
        required: ['lens', 'summary'],
      },
    },
    skipped: { type: 'array', items: { type: 'string' }, description: 'unit files you did not read in full' },
  },
  required: ['findings', 'coverage', 'skipped'],
})

const TOUCHED = {
  type: 'object',
  properties: { files: { type: 'array', items: { type: 'string' } } },
  required: ['files'],
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
        properties: {
          id: { type: 'string' },
          justification: { type: 'string' },
          question: {
            type: 'object',
            description: 'only when the fix needs a product decision: the question for the user',
            properties: {
              unclear: { type: 'string', description: 'what is not settled and why it matters' },
              options: { type: 'array', items: { type: 'string' }, description: 'at least two, the current behaviour among them' },
              recommended: { type: 'string' },
            },
            required: ['unclear', 'options', 'recommended'],
          },
        },
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
  properties: {
    ok: { type: 'boolean' },
    recorded: { type: 'number', description: 'N from the "recorded N" line of discipline review record' },
    status: { type: 'string', description: 'verbatim output of discipline review status' },
  },
  required: ['ok', 'recorded', 'status'],
}

const isQuestion = (f) => f.kind === 'question'
const describe = (f) =>
  isQuestion(f)
    ? `[${f.id}] QUESTION (${f.lens}/${f.severity}) ${f.title} @ ${f.file}${f.line ? ':' + f.line : ''}\n  unclear: ${f.scenario}\n  options: ${(f.options || []).join(' | ')}\n  recommended: ${f.fix}` +
      (f.verdict ? `\n  verifier: ${f.verdict}` : '')
    : `[${f.id}] (${f.lens}/${f.severity}) ${f.title} @ ${f.file}${f.line ? ':' + f.line : ''}\n  scenario: ${f.scenario}\n  fix: ${f.fix}` +
      (f.verdict ? `\n  verifier: ${f.verdict}` : '')

const fixPrompt = (items, openQuestions) => `You are fixing review findings in the ${PROJECT.name} repo. ${PROJECT.fixRules}

Findings:
${items.map(describe).join('\n')}
${openQuestions.length ? `
Open questions for the user (product behaviour nobody has decided yet). Do not settle them: don't build anything that presumes an answer, and don't write an answer into docs/SPEC.md or anywhere else:
${openQuestions.map((q) => `- ${q.title} (${q.file}): ${q.scenario}`).join('\n')}
` : ''}
Fix each one. Reject a finding only with a concrete written justification (it contradicts the spec, it is already handled, or the fix would be harmful).
Fix the code, not the tests. Never change an existing test's expected value, loosen or skip a test, or delete one, unless docs/SPEC.md or a decision in docs/decisions/ says the old expectation was wrong; then cite it in the test (the spec section or rule ID) and in your report. If a test seems wrong but nothing written says so, don't touch it: reject the finding with \`question\` set.
You implement decisions; you never make product decisions. Where a fix would require deciding behaviour that docs/SPEC.md, docs/decisions/ and docs/proposals/ leave open (who may do something, whether a feature should exist, what an edge case should produce), don't decide it: reject that finding with \`question\` set (what is unclear, the options with the current behaviour among them, your recommendation). It goes to the user. One exception: a real security risk (data of another tenant or user exposed, an action without its permission) may get the most restrictive interim fix, with a test, but say in the justification that the rule is provisional, and still set \`question\`; never write a provisional rule into docs/SPEC.md as settled: if the spec must mention it, mark it \`(assumed <YYYY-MM-DD>, not confirmed)\`.
Keep tool output small to save tokens: while iterating run only targeted checks (e.g. ${PROJECT.targetedChecks}). When done, run your gate ONCE: ${PROJECT.fixGate} plus ${PROJECT.affectedTests}. Redirect output to a log file and inspect failures with grep/tail rather than printing whole logs; fix and re-run until it passes. Do NOT run the full \`${PROJECT.gate}\`: it runs once after the loop.
Report the ids fixed (each entry in \`fixed\` must be exactly an id such as \`api-orgs#3\`, nothing else), the ids rejected with justification, whether your gate passes (\`gatePassing\`, with the commands you ran listed in \`gateFailures\` only if they fail), and any remaining failures (concise). Tests you could not run because the environment blocks them (for example unreachable test containers) are not failures of your code: list them in \`gateFailures\` prefixed "not run:".`

// Skeptical batch verification. Confirmed findings are flagged `confirmed` so that, if their fix is
// deferred, a later run can fix them without verifying them again.
const verdictsByIndex = (v) => new Map(((v && v.verdicts) || []).map((x) => [x.index, x]))
const verifyOnce = (findings, scope) =>
  agent(
    `You are a skeptical senior engineer verifying code-review findings (${scope}) of the ${PROJECT.name} repo (read-only; do not modify files).
For EACH finding below, try to REFUTE it by reading the actual code, ${PROJECT.docs}, the decisions in docs/decisions/ for its area or spec section (search by \`Area:\` or \`Spec:\`; skip entries marked \`Superseded by\`) and docs/proposals/. real=true only if the problem genuinely exists in the current code and the fix is worthwhile for this project. If uncertain, a matter of taste, or already handled elsewhere, real=false. A QUESTION is real=true only if those documents genuinely don't settle the behaviour (or contradict each other) and the answer matters; real=false if they answer it, or if the user already answered it (\`discipline decisions search <words>\` searches decisions and answered review questions; say where). Give a short reason either way. Return one verdict per finding, using its index.

${findings.map((f, i) => `#${i} ${describe(f)}`).join('\n\n')}`,
    { label: `verify:${scope}`, phase: 'Verify', schema: VERDICTS, agentType: READER },
  ).then((v) => {
    const byIdx = verdictsByIndex(v)
    return findings.map((f, i) => {
      const x = byIdx.get(i)
      const real = x ? x.real : null
      return { ...f, real, confirmed: real === true, verdict: x ? x.reason : 'not verified' }
    })
  })

// A single skeptic's rejection is final, so the costliest misses get a second look: a refuted
// critical/high finding in a SECOND_OPINION lens goes to an independent verifier, who does not see
// the first verdict. Rejected only if both refute; if they disagree, the fixer gets it (and may still
// reject it with a written justification).
const needsSecondOpinion = (f) =>
  !isQuestion(f) && f.real === false && SECOND_OPINION.includes(f.lens) && (f.severity === 'critical' || f.severity === 'high')
const secondOpinion = (findings, scope) => {
  const doubtful = findings.filter(needsSecondOpinion)
  if (!doubtful.length) return Promise.resolve(findings)
  return agent(
    `You are an independent senior engineer checking ${doubtful.length} serious code-review finding(s) (${scope}) of the ${PROJECT.name} repo (read-only; do not modify files).
For EACH finding, decide from the actual code, ${PROJECT.docs}, whether the failure scenario can really happen: trace the inputs, the callers and the existing defences (middleware, constraints, configuration) that would stop it. real=true if it can happen and is worth fixing; real=false if a specific defence or fact rules it out — name it. Return one verdict per finding, using its index.

${doubtful.map((f, i) => `#${i} ${describe({ ...f, verdict: undefined })}`).join('\n\n')}`,
    { label: `verify2:${scope}`, phase: 'Verify', schema: VERDICTS, agentType: READER },
  ).then((v) => {
    const byIdx = verdictsByIndex(v)
    const upheld = new Map()
    doubtful.forEach((f, i) => {
      const x = byIdx.get(i)
      if (x && x.real) upheld.set(f.id, x.reason)
    })
    return findings.map((f) =>
      upheld.has(f.id)
        ? { ...f, real: true, confirmed: true, disputed: true, verdict: `verifiers disagree; first: ${f.verdict}; second (upheld): ${upheld.get(f.id)}` }
        : f,
    )
  })
}
const verify = (findings, scope) => verifyOnce(findings, scope).then((v) => secondOpinion(v, scope))

// Weekly usage guard (opt-in via args.stopAt): reads the status-line snapshot (discipline review quota).
// Unknown usage never blocks.
const usage = (q) => `week ${q.week === null || q.week === undefined ? '?' : q.week + '%'}${stopAt5h ? `, 5h ${q.five_hour === null || q.five_hour === undefined ? '?' : q.five_hour + '%'}` : ''}`
const limits = `${stopAt ? `week ${stopAt}%` : ''}${stopAt && stopAt5h ? ', ' : ''}${stopAt5h ? `5h ${stopAt5h}%` : ''}`
const quotaOk = async (where) => {
  if (!guarded) return true
  const q = await agent(
    `Run exactly \`${RP} quota ${quotaArgs}\` from the repository root and return its JSON output unchanged. Do nothing else.`,
    { label: `quota:${where}`, phase: 'Fix', schema: QUOTA, effort: 'low' },
  )
  if (!q) return true
  if (q.known && q.ageSeconds > 1800) log(`usage snapshot is ${Math.round(q.ageSeconds / 60)} min old (${usage(q)}) — proceeding`)
  if (!q.ok) log(`usage ${usage(q)} reached the limit (${limits}) — stopping gracefully before ${where}`)
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
  `Run exactly this command from the repository root and return its JSON output as the structured result, unchanged: \`${RP} plan ${planArgs} ${quotaArgs}\`. Do not run anything else and do not modify files.`,
  { label: 'plan', phase: 'Plan', schema: PLAN, effort: 'low' },
)
if (!plan) return { aborted: true, reason: 'plan agent failed' }
PROJECT = { ...PROJECT_DEFAULTS, ...(plan.project || {}) }
if (Array.isArray(plan.secondOpinion) && plan.secondOpinion.length) SECOND_OPINION = plan.secondOpinion
// units.json lists lens names (older files mapped them to paths; only the names matter now).
const LENSES = Array.isArray(plan.lenses) ? plan.lenses : Object.keys(plan.lenses || {})
const checklist = (l) => `${l} → \`${RP} checklist ${l}\``
if (!LENSES.length) return { aborted: true, reason: 'no lenses in .claude/review/units.json (run discipline lenses apply)' }
const REVIEW = reviewSchema(LENSES)
if (guarded) log(`usage: ${plan.quota.known ? usage(plan.quota) : 'unknown'} (stop at ${limits})`)
if (guarded && !plan.quota.ok) return { stoppedForQuota: true, week: plan.quota.week, fiveHour: plan.quota.five_hour, stopAt, stopAt5h, remainingUnits: plan.remainingUnits + plan.selected.length }
// Open findings from earlier runs: only those a verifier confirmed (fix deferred) go straight to
// the fixer; the rest (unverified, or found by a delta review) are verified again below.
const openRows = plan.open.map((f, i) => ({ ...f, id: `open#${i + 1}` }))
const carried = openRows.filter((f) => f.confirmed === true).map((f) => ({ ...f, verdict: 'confirmed in an earlier run; fix was deferred' }))
const reverify = openRows.filter((f) => f.confirmed !== true)
if (openRows.length) log(`${openRows.length} open findings carried over from earlier runs (${reverify.length} to verify first)`)
if (plan.uncovered.length) log(`files not covered by any unit (add them to .claude/review/units.json): ${plan.uncovered.join(', ')}`)
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
2. Read the sections for your lenses in .agents/review-context.md (this project's specifics), then read each lens's checklist and follow it: ${sel.lenses.map(checklist).join('; ')}. Ignore any instruction there about choosing the review scope — your scope is this unit.${sel.lenses.includes('contracts') ? ' For the contracts lens, the unit\'s contract files are part of the diff when they changed, even though they live outside the unit.' : ''}
3. ${sel.since
        ? `This unit was fully reviewed before, and only some of it has changed since. Run \`${RP} diff --unit ${sel.unit} --since ${sel.since}\` and review THOSE CHANGES: read the changed files and enough surrounding code (callers, tests, the spec) to judge them. Do not re-review unchanged code, except where a change makes an existing problem worse. Files you did not read because they are unchanged are not skips.`
        : 'Read every file of the unit in full, tests included.'} Look outside the unit only to check callers, contracts, the spec, or (duplication and simplicity lenses) to search the whole repo for similar logic or for existing machinery that already does the job.
4. Report substantive, verifiable findings only: a concrete failure scenario pointing at real code. No style nits. At most 10 per lens, most severe first. Where a finding breaks an engineering principle (E1–E10: \`discipline doc engineering\`; this project's own: .agents/ENGINEERING.md), put its ID in the title (e.g. "E9: validation failure logged as error").
5. Where docs/SPEC.md, docs/decisions/ and docs/proposals/ don't settle what the behaviour should be (or contradict each other), and the user hasn't answered it before (\`discipline decisions search <words>\`; answered questions are also in step 1's output), don't guess and don't report a defect: report kind="question" with what is unclear and why it matters in \`scenario\`, the options in \`options\` (the current behaviour among them) and your recommended option in \`fix\`. The user answers questions; the fixer never sees them.
In \`coverage\` give, per lens, one sentence on what you checked. List in \`skipped\` any unit file you did not read in full (ideally none).${PROJECT.scriptCheckable ? ` Exception: ${PROJECT.scriptCheckable} instead of read line by line; that is not a skip.` : ''}`,
      { label: `review:${sel.unit}`, phase: 'Review', schema: REVIEW, agentType: READER, ...reviewOpts },
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
// `changed` lists only files that still exist (discipline review changed_files), so a deleted file is never a skip.
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
const confirmed = all.filter((f) => f.real === true && !isQuestion(f))
// Questions a verifier confirmed, or could not judge, go to the user; refuted ones are rejected below.
const questions = all.filter((f) => isQuestion(f) && f.real !== false)
const rejectedByVerifier = all.filter((f) => f.real === false)
const unverified = all.filter((f) => f.real === null && !isQuestion(f))
const disputed = all.filter((f) => f.disputed)
log(`${all.length} findings: ${confirmed.length} confirmed, ${rejectedByVerifier.length} refuted, ${unverified.length} unverified, ${questions.length} questions for the user`)
if (disputed.length) log(`${disputed.length} serious findings refuted by one verifier but upheld by a second — sent to the fixer: ${disputed.map((f) => f.id).join(', ')}`)

// The read-only phases must have changed nothing in the reviewed units. If they did, nothing is fixed
// or marked in this run: the findings stay open (verified ones keep their flag) and the units are
// reviewed again later. The stray changes are left in place for the user to inspect.
const touchedUnits = plan.selected.map((s) => s.unit)
let strayWrites = []
if (touchedUnits.length) {
  const t = await agent(
    `Run exactly \`${RP} touched ${touchedUnits.map((u) => `--unit ${u}`).join(' ')}\` from the repository root and return its JSON list as \`files\`, unchanged. Do nothing else.`,
    { label: 'touched', phase: 'Verify', schema: TOUCHED, effort: 'low' },
  )
  strayWrites = t ? t.files : null
}
const readOnlyHeld = Array.isArray(strayWrites) && strayWrites.length === 0
if (!readOnlyHeld) {
  log(strayWrites === null
    ? 'could not check that the reviewers wrote nothing — not fixing or marking anything this run'
    : `files changed during the read-only phases: ${strayWrites.join(', ')} — not fixing or marking anything this run; inspect them with git diff`)
  failedUnits.push(...touchedUnits)
}

// ---------------------------------------------------------------- Fix + delta review
const outcomes = []
// Every outcome keeps its evidence: the failure scenario, the proposed fix and the verifier's reasoning
// (the history is the review's audit trail, `discipline review evidence` reports it). `review.py record`
// adds the snapshot of the code this run reviewed.
const clip = (t, n) => (t ? String(t).slice(0, n) : null)
const record = (f, status, reason) =>
  outcomes.push({
    unit: f.unit || null, lens: f.lens, severity: f.severity, file: f.file, line: f.line || null, title: f.title, status,
    reason: (reason || '').slice(0, 300),
    scenario: clip(f.scenario, 600), fix: clip(f.fix, 400), verdict: clip(f.verdict, 400),
    // Open findings keep their details so a later run can fix them without re-reviewing.
    // `confirmed` lets the next run skip re-verification only for verifier-confirmed findings.
    ...(status === 'open' ? { scenario: f.scenario, fix: f.fix, confirmed: f.confirmed === true } : {}),
    // Questions keep what the user needs to decide.
    ...(status === 'question' ? { scenario: f.scenario, fix: f.fix, options: f.options || [] } : {}),
  })
rejectedByVerifier.forEach((f) => record(f, 'rejected', f.verdict))
questions.forEach((f) => record(f, 'question', f.verdict))
unverified.forEach((f) => record(f, 'open', 'verifier gave no verdict'))

let gate = { gatePassing: null, gateFailures: [] }
let toFix = carried.concat(confirmed)
if (!readOnlyHeld) {
  toFix.forEach((f) => record(f, 'open', 'not fixed: files changed during the read-only phases'))
  toFix = []
}
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
  const fix = await agent(fixPrompt(toFix, questions), { label: d === 0 ? 'fix' : `fix:delta${d}`, phase: 'Fix', schema: FIXED })
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
  // A finding whose fix needs a product decision becomes a question for the user, not a rejection.
  const asked = new Map(fix.rejected.filter((r) => r.question).map((r) => [idOf(r.id), r]))
  toFix.forEach((f) => {
    const q = asked.get(f.id)
    if (q) {
      const question = { ...f, kind: 'question', scenario: q.question.unclear, options: q.question.options, fix: q.question.recommended }
      questions.push(question)
      // An interim security fix may have been applied anyway; the question still goes to the user.
      record(question, 'question', `fixer: ${q.justification}`)
    } else if (rej.has(f.id)) record(f, 'rejected', `fixer: ${rej.get(f.id)}`)
    else record(f, fixedIds.has(f.id) ? 'fixed' : 'open', fixedIds.has(f.id) ? '' : 'fixer did not report it')
  })
  const unreported = toFix.filter((f) => !fixedIds.has(f.id) && !rej.has(f.id)).length
  if (unreported) log(`fixer did not report ${unreported} of ${toFix.length} findings — recorded as open for the next run`)
  if (asked.size) log(`fixer handed ${asked.size} finding(s) back as questions for the user (they need a product decision)`)

  phase('Delta')
  if (!(await quotaOk(`delta${d + 1}`))) {
    stoppedForQuota = true
    log('fixer changes not delta-reviewed — reviewed units stay unmarked so they are re-checked later')
    failedUnits.push(...plan.selected.map((s) => s.unit))
    break
  }
  const deltaLenses = LENSES.filter((l) => toFix.some((f) => f.lens === l) || plan.selected.some((s) => s.lenses.includes(l)))
  const delta = await agent(
    `You are reviewing ONLY the changes a fixer just made to the ${PROJECT.name} repo. You are STRICTLY READ-ONLY.
Run \`${RP} diff\` to see every change since the review snapshot. Read .agents/review-context.md for this project's specifics. Review those changes for ${PROJECT.deltaFocus}, and through the checklists of the lenses involved: ${deltaLenses.map(checklist).join('; ')}.
Ignore pre-existing issues outside the changed lines unless the change makes them worse. A change that settles product behaviour the spec, decisions and proposals left open (in code or in docs/SPEC.md) is a finding of kind "question". Already raised in earlier delta passes (do not repeat): ${JSON.stringify(deltaHistory)}
High bar: report only problems you have confirmed by reading the code, with a concrete failure scenario.`,
    { label: `delta:${d + 1}`, phase: 'Delta', schema: REVIEW, agentType: READER, ...reviewOpts },
  )
  if (!delta) {
    log('delta review failed — fixer changes are not re-reviewed; units stay unmarked for safety')
    failedUnits.push(...plan.selected.map((s) => s.unit))
    break
  }
  unreviewedFix = false
  const deltaFindings = delta.findings.map((f, i) => ({ ...f, id: `delta${d + 1}#${i + 1}` }))
  deltaFindings.filter(isQuestion).forEach((f) => { questions.push(f); record(f, 'question', 'raised by the delta review') })
  toFix = deltaFindings.filter((f) => !isQuestion(f))
  deltaHistory.push(...deltaFindings.map((f) => `${f.file}: ${f.title}`))
  log(`delta ${d + 1}: ${toFix.length} findings in the fixer's changes`)
  if (toFix.length && d + 1 >= maxDelta) {
    toFix.forEach((f) => record(f, 'open', 'found in delta review after the last fix pass'))
    log(`delta limit reached — ${toFix.length} findings recorded as open`)
    break
  }
}

// ---------------------------------------------------------------- Record
phase('Record')
// Never advance ledger pairs over fixer edits that no delta review has seen, or over files changed
// during the read-only phases.
const noAdvance = unreviewedFix || !readOnlyHeld
const markPairs = results
  .filter((r) => !r.failed && r.rev && !realSkips(r).length && !failedUnits.includes(r.sel.unit))
  .flatMap((r) => r.sel.lenses.map((l) => `${r.sel.unit}:${l}`))
const rec = await agent(
  `From the repository root, do exactly these steps and nothing else:
1. Write this JSON verbatim to .claude/review/outcomes.tmp.json (use a quoted heredoc so nothing is interpolated):
${JSON.stringify(outcomes)}
2. Run \`${RP} record .claude/review/outcomes.tmp.json && rm .claude/review/outcomes.tmp.json\` and return the N it prints ("recorded N") as \`recorded\`.
3. Run \`${RP} mark ${noAdvance ? '--no-advance ' : ''}${markPairs.join(' ')}\`
4. Run \`${RP} status\` and return its output verbatim as \`status\`. ok=true only if every command succeeded.`,
  { label: 'record', phase: 'Record', schema: RECORDED, effort: 'low' },
)

// The outcomes pass through an agent's heredoc; a count mismatch means rows were lost or invented.
const recordOk = !!(rec && rec.ok && rec.recorded === outcomes.length)
if (rec && rec.recorded !== outcomes.length) log(`record step wrote ${rec.recorded} rows, expected ${outcomes.length} — check .claude/review/history.jsonl`)

return {
  stoppedForQuota,
  readOnlyHeld,
  strayWrites: strayWrites || [],
  // Behaviour the written intent doesn't settle: ask the user (batched, with the recommendation),
  // record the answer in docs/SPEC.md and docs/decisions/, then `discipline review answer N --reason ...`.
  questions: questions.map((f) => ({ id: f.id, unit: f.unit || null, file: f.file, title: f.title, unclear: f.scenario, options: f.options || [], recommended: f.fix })),
  disputed: disputed.map((f) => ({ id: f.id, lens: f.lens, severity: f.severity, file: f.file, title: f.title, verdict: f.verdict })),
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
    questions: outcomes.filter((o) => o.status === 'question').length,
  },
  outcomes,
  recordOk,
  status: rec ? rec.status : 'record step failed — run discipline review status',
}
