# Result: anonymous OpenAlex evidence-gap live study

**Date:** 2026-08-27

**Executed revision:**
`7bfe4eadbf2ead7549125e59d0156c9fa3c1bf94`

**Protocol:**
[`prereg-2026-08-27-evidence-gap-anonymous-openalex.md`](prereg-2026-08-27-evidence-gap-anonymous-openalex.md)

**Production connection authorized:** no

## Outcome

The separately authorized anonymous OpenAlex study completed all four frozen
academic cases. It made exactly four sequential requests, used no API key,
performed no retry or source-page fetch, and retained
`production_connected=false` and `report_workflow_connected=false` through the
final artifact boundary.

OpenAlex reported USD 0.001 of anonymous-budget usage for each request, USD
0.004 in total, below the frozen USD 0.01 soft stop. This is a provider-reported
budget value, not evidence that a payment was charged. All request identities
were client-generated because the response did not expose a provider request
id.

This establishes one exact live compatibility and accounting observation. A
later eligible human review completed all nine rows after a copied declaration
error was corrected with disclosure. It passed both case-coverage gates but
failed the frozen wrong-source ceiling, so the source-value decision is fail.

## Execution and disposition audit

| Case | Request latency | Provider rows | Provider rejected | Local rejected | Quarantine accepted |
|---|---:|---:|---:|---:|---:|
| D01 | 1,954.07 ms | 5 | 2 | 2 | 1 |
| D02 | 1,254.00 ms | 5 | 2 | 1 | 2 |
| D03 | 1,470.37 ms | 5 | 1 | 1 | 3 |
| D04 | 1,448.35 ms | 5 | 2 | 0 | 3 |
| **Total** | **6,126.79 ms** | **20** | **7** | **4** | **9** |

The provider parser accepted 13/20 rows for local inspection. Seven rows were
rejected because the OpenAlex record had no reconstructable abstract. The
frozen relevance quarantine then rejected four of the thirteen parsed
candidates and retained nine sources for human review.

Every case retained at least one candidate, so the first mechanical frozen gate
passed at 4/4. The corrected human review made the other two gates evaluable:
five candidates were directly relevant and baseline-absent across all four
cases, so novel-relevant coverage passed at 4/4; four candidates were directly
irrelevant, so the `4/9 = 44.4%` wrong-source rate failed the frozen 5% maximum.

The blank review artifact contained exactly nine rows, one for every retained
source. The returned labels preserve that denominator unchanged.

## Persistence and integrity

The runner committed the manifest before the first request and four case
journals before final aggregation. The finalized output contains 20 candidate
rows, nine blank review rows and four case journals. All aggregate files match
the write-once artifact index:

| File | SHA-256 |
|---|---|
| `manifest.json` | `a53e05dc31b41a047307f393670f2983cf3ca3d6dab8c92f7bc58f8e9ecd7de0` |
| `execution.json` | `44298f78a0006eeb61f544620ce693dc1510cad015f43b0b1e94d6c6b1c7ffec` |
| `candidates.csv` | `91d148f97320582fe29987ff2ef139f7e3cb3d53ab2473ef1ac4ad3119805006` |
| `review.csv` | `c3fc1f61c9cd07257bff9ea95e77a9a07f674ec2a92b75ab21713a675579e191` |

The raw execution remains in the gitignored local directory
`outputs/evidence-gap-openalex-anonymous-20260827-7bfe4ead/`. The public result
records its identities and aggregates without claiming that an uncommitted raw
directory is independently available.

## Decision

Anonymous OpenAlex compatibility passed for this exact four-case execution, but
the corrected human source-value decision failed. The first declaration row was
copied from an unrelated AI-assisted review; the original excluded intake and
the owner-relayed correction are both retained in the
[`declaration erratum`](errata-2026-08-27-anonymous-openalex-review-declaration.md).

The eligible result is `complete / fail`: accepted-case coverage is 4/4,
novel-relevant coverage is 4/4, and wrong-source rate is 4/9 (44.4%). No repeat
provider run is needed. The current adapter does not advance to planner-trigger
measurement and production Tool Calling remains disconnected. See the
[`review-boundary result`](results-2026-08-27-evidence-gap-anonymous-openalex-review-implementation.md)
and [`returned-review result`](results-2026-08-27-evidence-gap-anonymous-openalex-review.md).

## Explicit non-claims

This single execution does not establish provider-wide reliability, source
truth, wrong-source rate, novel-evidence yield, planner precision, report
improvement, user utility, cost savings, latency performance, an SLO, or
production Tool Calling readiness.

## Supported claim

> On one frozen four-case study, the no-key OpenAlex adapter completed four
> single-attempt requests, retained nine candidates from twenty provider rows,
> reported USD 0.004 of anonymous-budget usage, and preserved write-once
> accounting with no production connection. After a copied declaration error
> was corrected with disclosure, one eligible human review found five relevant
> and four irrelevant candidates; the 44.4% wrong-source rate failed the frozen
> 5% source-value gate, so the adapter remains disconnected.
