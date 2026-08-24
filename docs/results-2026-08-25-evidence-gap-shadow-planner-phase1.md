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

- Full zero-network suite: **1,369 passed and 592 subtests passed**.
- CI-equivalent coverage: **86.92%**, above the frozen 85% threshold.
- Latest Ruff and the CI-specific Pylint exception-order checks passed.
- A deliberate change from the two-intent ceiling to three made the targeted
  contract test fail; restoring the ceiling made it pass again. This confirms
  that the test detects the original boundary rather than merely exercising
  the happy path.

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
