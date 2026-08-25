# Evidence-gap shadow planner — phase 1 result

**Run date:** 2026-08-25
**Protocol:** [phase-1 pre-registration](prereg-2026-08-25-evidence-gap-shadow-planner.md)
**Network, LLM, and search calls:** 0

## Result

The zero-network replay loaded exactly 30 stored benchmark source collections
and passed every phase-1 mechanics check:

| Measure | Observed |
|---|---:|
| Collections checked | 30/30 |
| Eligible | 9 |
| No explicit gap | 21 |
| Deterministic second pass | 30/30 identical |
| Tool calls executed | 0 |
| Input or evidence mutations | 0 |
| Failed checks | 0 |

The nine eligible collections contained 18
`authority_category_missing` signals: the three older biomedical benchmark
topics, each repeated three times, lacked both regulator and
clinical-registry records. No component or failed-domain signal occurred in
this development set.

Command:

```bash
uv run python evidence_gap_audit.py outputs/benchmark \
  outputs/evidence-gap-shadow-phase1-20260825 --expected-count 30
```

The generated `result.json` retains every fixture SHA-256 and `cases.csv`
retains every decision. The directory is intentionally under ignored
`outputs/`: it contains a local replay artifact, while this result record and
the executable checker travel with the repository.

## Verification

- Full zero-network suite: **1,370 passed and 592 subtests passed**.
- CI-equivalent coverage: **86.92%**, above the frozen 85% threshold.
- Latest Ruff and the CI-specific Pylint exception-order checks passed.
- A deliberate change from the two-intent ceiling to three made the targeted
  contract test fail; restoring the ceiling made it pass again. This confirms
  that the test detects the original boundary rather than merely exercising
  the happy path.
- The CI-caught Sydney/UTC fixture defect was reintroduced; the dedicated
  regression test failed under a simulated UTC date and passed after the
  historical fixture date was restored.

## What this establishes

- The feature can distinguish disabled, checked-with-no-gap, eligible, and
  failed states.
- The runtime observation path adds no planner or search request.
- Strict proposals cannot exceed two intents or reference invented and
  unauthorized triggers.
- The eligibility value reaches both HTTP status boundaries and a downloadable
  per-run artifact.

## What this does not establish

This is the same stored evidence that informed gate development. It is not a
held-out trigger-precision result, not evidence that supplementary search adds
useful sources, and not evidence that Tool Calling improves a report. Current
retrieval already sends FDA, EMA, and ClinicalTrials.gov queries for applicable
new runs, so repeating those queries later would not count as novel evidence.

Production planner-model invocation and tool execution remain disabled. Phase
2 requires a separately frozen challenge set and must meet the precision,
source-validity, evidence-increment, cost, latency, and tracing thresholds in
the pre-registration before any production adapter is connected.

## Production canary and follow-up correction

An operator-selected production canary ran on 2026-08-25 after the shadow flag
was enabled. It was a runtime check, not a held-out trigger-accuracy study:

- Run: [20260825T014903Z-07c05a15f0afebb64471a7433121a4e1](https://academic-commercialization-agent.up.railway.app/run/20260825T014903Z-07c05a15f0afebb64471a7433121a4e1)
- Topic: wearable continuous blood-pressure monitoring via photoplethysmography
- Completion: 162 seconds, 8 academic + 8 patent + 7 market sources
- Provider use: 6 requests, 78,254 tokens, `$0.032152`
- Shadow artifact: `checked=true`, `persistence_state=written`, zero executed
  calls, zero added search cost, and no evidence mutation

The runtime and public artifact seams passed. The `no_gap` decision did not:
the run exposed a deterministic false negative and a separate credibility
false positive.

1. The normalized clinical-monitoring topic fell through to the `industrial`
   weight profile.
2. Authority coverage consequently reported `not_applicable`, despite the
   finished report acknowledging that its regulatory pathway was not mapped.
3. The generic `American Journal of` publisher fragment downgraded the official
   ASPC/Elsevier *American Journal of Preventive Cardiology* as predatory,
   contrary to the [NLM Catalog record](https://www.ncbi.nlm.nih.gov/nlmcatalog/101769122).

The follow-up correction remains deliberately narrow:

- `blood pressure` selects the biomedical profile;
- `blood pressure monitor` requires regulator evidence, but does not invent
  a universal clinical-trial-registry requirement for medical devices;
- a generic journal-title prefix no longer establishes publisher identity;
- classification, regulator-query, authority-coverage, shadow-gate, and
  production-journal regressions assert the full seams.

The proposed phrases change zero of the ten topics and zero of the 30 runs in
the frozen calibration benchmark. No second paid run was used during the code
fix, so production post-fix behavior remains to be observed after deployment.

Post-fix local gates passed: 1,374 zero-network tests and 594 subtests, Ruff,
the CI exception-order Pylint checks, and 86.91% measured coverage against the
85% floor.
