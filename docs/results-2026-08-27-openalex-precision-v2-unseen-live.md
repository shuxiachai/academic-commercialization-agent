# Result: OpenAlex precision-v2 unseen live study

**Date:** 2026-08-27

**Executed revision:**
`9f84a9faf57f558c242ab3ab44f41b7b4bccb70f`

**Protocol:**
[`prereg-2026-08-27-openalex-precision-v2.md`](prereg-2026-08-27-openalex-precision-v2.md)

**Harness implementation:**
[`results-2026-08-27-openalex-precision-v2-unseen-implementation.md`](results-2026-08-27-openalex-precision-v2-unseen-implementation.md)

**Production connection authorized:** no

## Outcome

The separately authorized U01-U08 study completed all eight frozen cases. It
made exactly eight sequential anonymous OpenAlex requests, used no API key,
performed no retry, redirect, source-page fetch or model call, and retained
`production_connected=false` and `report_workflow_connected=false` through the
final artifact boundary.

OpenAlex reported USD 0.001 of anonymous-budget usage per request, USD 0.008 in
total, below the frozen USD 0.01 soft stop. This is a provider-reported budget
value, not evidence that a payment was charged. All eight request identities
were client-generated because the responses exposed no provider request id.

The provider returned 40 rows. Nine were rejected because the record had no
reconstructable abstract, the unchanged legacy quarantine rejected eight, and
23 reached the precision-v2 seam. The conjunctive gate accepted five candidates
across only three cases and abstained the other 18 candidates.

The frozen first value gate requires an accepted candidate in at least 6/8
cases. The observed 3/8 cannot be changed by any later relevance or novelty
label, so this exact method cannot satisfy the all-gates rule. The study stopped
before asking a reviewer to inspect five rows that could not rescue the failed
coverage gate. Accordingly, the persisted state remains
`human_review_state=not_prepared` and `source_value_state=not_evaluated`; this is
a deterministic coverage non-qualification, not a measured wrong-source rate
or source-truth result.

## Execution and disposition audit

| Case | Request latency | Provider rows | Provider rejected | Legacy rejected | Precision ACCEPT | Precision ABSTAIN |
|---|---:|---:|---:|---:|---:|---:|
| U01 | 1,732.44 ms | 5 | 2 | 2 | 1 | 0 |
| U02 | 1,373.29 ms | 5 | 1 | 2 | 2 | 0 |
| U03 | 1,397.58 ms | 5 | 0 | 0 | 2 | 3 |
| U04 | 1,186.24 ms | 5 | 1 | 0 | 0 | 4 |
| U05 | 741.30 ms | 5 | 1 | 1 | 0 | 3 |
| U06 | 1,340.71 ms | 5 | 1 | 0 | 0 | 4 |
| U07 | 1,498.60 ms | 5 | 2 | 0 | 0 | 3 |
| U08 | 1,440.45 ms | 5 | 1 | 3 | 0 | 1 |
| **Total** | **10,710.61 ms** | **40** | **9** | **8** | **5** | **18** |

The five accepted rows occur only in U01-U03. U04-U08 contain no accepted
candidate, even though their request and accounting seams all completed. An
abstention is not an assertion that a paper is irrelevant; it records that the
frozen exact-phrase conjunction lacked enough support to admit the row.

## Persistence and integrity

The runner committed the manifest before adapter construction and one
write-once journal after each attempted case. The final output contains all
eight journals, 40 candidate rows and five blank review rows. Every aggregate
file matches the artifact index:

| File | SHA-256 |
|---|---|
| `manifest.json` | `f07aa04d4943129120ae7f0c269a6401e1955d5cf9f13add73e4b5134ea5d5f5` |
| `execution.json` | `4a3b39d7cbb571143a08c758bf20f5873598d66ee4fdcb049c0d13fdae08d5f3` |
| `candidates.csv` | `815c42bcae0c59d917aa760108908e689757e4fab53eee648176c0c68e75ef7c` |
| `review.csv` | `168accff2a5c10c4bbc5eeed05240092b7d218655acaa95720a18cf182ad6595` |

The raw execution remains in the gitignored local directory
`outputs/2026-08-27-openalex-precision-v2-unseen-live-9f84a9f/`. The public
result records aggregate identities without claiming that the uncommitted raw
directory is independently available.

## Decision

Do not connect precision v2 to the planner or production workflow. Do not tune
the frozen profiles on U01-U08 and then report the same cases as validation,
and do not repeat these provider requests: the exact unseen observation is
already complete. If another retrieval or precision method is attempted, these
rows become development evidence and the next evaluation must freeze a
different unseen challenge first.

The useful engineering result is narrower: the identity, request-budget,
accounting, abstention and write-once boundaries worked under one live
eight-case execution. The source-value hypothesis did not qualify because the
precision rule was too selective to meet the pre-registered coverage floor.

## Explicit non-claims

This execution does not establish source truth, a wrong-source rate, retrieval
recall, OpenAlex-wide precision, planner-trigger precision, report improvement,
user utility, cost savings, latency performance, an SLO, autonomous tool choice
or production Tool Calling readiness.

## Supported claim

> On one frozen eight-case unseen study, the production-disconnected
> precision-v2 harness completed eight single-attempt anonymous OpenAlex
> requests for USD 0.008 of provider-reported budget usage and preserved every
> row and artifact identity. It accepted five candidates across 3/8 cases, below
> the frozen 6/8 coverage floor, so the method did not qualify for a human
> source-value review or production connection.
