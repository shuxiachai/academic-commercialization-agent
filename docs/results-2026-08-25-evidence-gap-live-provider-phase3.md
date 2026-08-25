# Result: Phase 3 live-provider compatibility pilot

**Date:** 2026-08-25

**Authorized revision:** `adde83dfd7d40c7fdd425b6f665eb121bb300e33`

**Status:** **AUTOMATED PROVIDER-COMPATIBILITY PASS; HUMAN VALUE REVIEW NOT
INSPECTED; WINDOWS CLI PRESENTATION DEFECT FOUND**

## Scope and authorization

The study owner explicitly authorized the frozen five-case Tavily pilot on the
exact deployed revision above, with at most five requests, a USD 0.04 soft
stop, permission for one in-flight request to cause a small overrun, and no
connection to the production report workflow.

The run used:

- the canonical manifest SHA-256
  `4f216d5a7ad0f44db0b973a10087fc6075ac1a2dddddde0430faf62595ca377f`;
- the five collection and validated-plan identities frozen in the Phase 3
  protocol;
- one Tavily basic-search attempt per case;
- the conservative accounting rate of USD 0.008 per observed credit; and
- the local write-once directory
  `outputs/evidence-gap-phase3-live-20260825-adde83d/`.

The preflight confirmed a clean worktree at the authorized revision, a new
output path, key availability without reading or printing the secret, all ten
semantic identities, and the corrected raw fixture identity. The dry-run
reported `production_connected=false` and
`real_network_calls_performed=false` before live execution began.

## Automated result

The provider and executor work completed all five cases. The write-once
artifact is internally consistent:

| Measure | Observed |
|---|---:|
| Completed cases | 5/5 |
| Outbound attempts | 5 |
| Successful responses with request identity | 5/5 |
| Observed Tavily credits | 5 |
| Conservative incremental cost | USD 0.040 |
| Provider-returned rows | 25 |
| Adapter-rejected rows | 0 |
| Locally quarantine-rejected rows | 0 |
| Quarantined accepted rows | 25 |
| Unique accepted URLs | 25 |
| Empty titles / URLs | 0 / 0 |
| Review rows with completed human labels | 0/25 |
| Production connected | false |
| Report workflow connected | false |

Each provider response returned five rows and one inspectable credit. There
were no transport, schema, usage-accounting, or quarantine failures.

| Case | Tool | Provider request ID | Latency (ms) | Accepted |
|---|---|---|---:|---:|
| L01 | `academic_search` | `4112b268-bb86-4bef-9976-505d2e765949` | 3,743.716 | 5 |
| L02 | `patent_search` | `c3e8b533-bee1-4357-80e9-c116e061333a` | 4,989.810 | 5 |
| L03 | `market_search` | `f9a7e1ac-c6c1-4160-b2fc-786540d1ca55` | 3,775.543 | 5 |
| L04 | `authority_search` | `ed9d9673-9911-42bf-a4e2-68797b94ab70` | 2,885.986 | 5 |
| L05 | `authority_search` | `ea4b43a6-54f7-41fc-8ec8-3fde6891c476` | 3,809.252 | 5 |

The sum of recorded provider latency was 19,204.307 ms; median case latency
was 3,775.543 ms. This is a five-request compatibility observation, not a
latency distribution or SLO.

## Frozen criteria

| Pre-registered compatibility criterion | Observation | Result |
|---|---|---|
| All identities validate before the first request | Raw fixture plus five collection and five plan hashes matched | pass |
| No more than five requests and credits | 5 requests; 5 credits | pass |
| Conservative cost no greater than USD 0.04 | USD 0.040 | pass |
| Every successful response exposes request ID and usage | 5/5 | pass |
| No invalid row enters accepted evidence | 0 adapter/schema rejections and 0 quarantine rejections were misregistered | pass |
| Failure and uninspectable states remain distinct | No failure occurred; all five costs and usages were inspectable | pass |
| At least one accepted candidate reaches human review | 25 rows reached `review.csv` | pass |

This supports an **automated provider-compatibility pass** only. It does not
complete the separately registered exploratory value criteria.

## Human review remains open

All 25 accepted rows have blank `relevant`, `novel`, and `review_note` fields.
The artifact therefore correctly reports `review_state=not_inspected`.

Until a human labels every row, the following remain unknown:

- wrong-source rate;
- case-level novel relevant evidence yield; and
- whether at least three of five cases gained useful evidence.

The domain census is descriptive only: five Google Patents URLs, five FDA
URLs, five ClinicalTrials.gov/CDN URLs, four PubMed/NCBI URLs, one Semantic
Scholar URL, and five market/news URLs. Domain validity is not semantic
relevance.

## CLI presentation defect

The paid work and all four files completed before the process tried to print
the final artifact. One L01 evidence summary contained U+2005 FOUR-PER-EM SPACE
in `91\u2005mg`. The Windows process stdout used strict GBK, so the final
`print(artifact.model_dump_json(...))` raised `UnicodeEncodeError` and returned
exit code 1 after artifact persistence.

The pilot was not rerun: doing so would duplicate paid requests and the
existing output path correctly prevents reuse. The defect is classified as a
CLI presentation failure, not a provider or artifact failure.

The follow-up changes only the console projection to ASCII-safe, reversible
JSON escapes. Authoritative files remain original UTF-8. A strict GBK seam test
restores the observed U+2005, proves the rendered JSON round-trips, and fails
with the same `UnicodeEncodeError` when the old print call is re-injected.

## Artifact identities

The raw provider artifacts remain local and ignored by Git because they
contain provider-returned text. Their identities are fixed here for audit:

| File | SHA-256 |
|---|---|
| `manifest.json` | `8989acda104e55066b91f42c7f3f78ec33141f440a9f91c6e2b322e315f6c84b` |
| `execution.json` | `2625c20b40d216fb067cbda307880342843ec22d38b76c1ea39e6762ce77b133` |
| `candidates.csv` | `0ba0c36518deff990dd36bf3c9a212aa1e61860c54bd0dd4ad273f5f50b762a5` |
| `review.csv` | `3eaee269f838c4d5b36a4dc16d1c797a713c9c95f2635c572686e8312020d52d` |

No API key appears in the command, result summary, or public artifacts.

## Decision

The single-request Tavily boundary is compatible with the frozen executor and
accounting contract. Production remains phase-1 zero-call shadow mode.

Production connection is still blocked by:

1. incomplete human relevance and novelty review;
2. no measured wrong-source or novel-evidence result; and
3. the earlier 90% planner-trigger-precision requirement, which this injected-
   intent pilot cannot test.

## Explicit non-claims

This result does not establish autonomous tool choice, planner precision,
report improvement, source-truth accuracy, production reliability, invoice
cost, latency SLO, user adoption, or permission to merge supplementary sources
into `validated_sources.json`.

The supported claim is:

> One production-disconnected five-case Tavily compatibility pilot completed
> five single-attempt requests with complete request and credit accounting at a
> conservative USD 0.04; evidence value remains not inspected.

## Zero-network human-review follow-up

A separate provenance-locked packet and strict label intake were prepared
without modifying this result or making another provider request. Its initial
state is `incomplete / not_evaluated`, not a human-value pass. See the
[frozen protocol](prereg-2026-08-25-evidence-gap-human-review-phase3.md) and
[packet-readiness result](results-2026-08-25-evidence-gap-human-review-packet-phase3.md).
