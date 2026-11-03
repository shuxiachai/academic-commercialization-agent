# Erratum: OpenAlex refused two batches' requests, unrecorded

**Date:** 2026-10-22.

**Affects:**
- [held-out TRL calibration v2](results-2026-10-19-heldout-trl-v2.md): the last five of its 30 runs;
- [hyperloop confirmation](results-2026-10-21-hyperloop-confirmation.md): both of its runs.

**Found by:** reading the saved audits of the October benchmark runs while
checking which retrieval lanes come back empty (#256).

## What happened

Both batches ran locally without `OPENALEX_API_KEY`. Anonymous OpenAlex calls
share a $0.10 daily budget per IP address, about 100 searches. A run issues
five to seven OpenAlex searches, so a 30-run batch outruns the budget. Once
the budget is spent, OpenAlex answers 429 until 00:00 UTC.

Before #252 (merged 2026-10-21 03:30 UTC), a refused request came back as an
empty result. Nothing in a run's audit, status or summary distinguished it
from a topic with no papers.

## Evidence

Every OpenAlex lane returned 0 results in the affected runs. In every earlier
run of the same batch, the cited lane returned the full 32 rows.

| Batch | Run | Collected (UTC) | OA-Recent / OA-Cited / OA-Syn | Academic sources | TRL (range) |
|---|---|---|---|---:|---|
| held-out v2 | V06 space-based solar power, rep 3 | 2026-10-19 06:43 | 0 / 0 / 0 | 6 | **2** (3–5) |
| held-out v2 | V07 hyperloop, rep 3 | 2026-10-19 06:50 | 0 / 0 / 0 | 8 | **2** (4–6) |
| held-out v2 | V08 量子密钥分发网络, rep 3 | 2026-10-19 06:55 | 0 / 0 / 0 | 8 | 7 (7–9) |
| held-out v2 | V09 特高压直流输电, rep 3 | 2026-10-19 07:01 | 0 / 0 / 0 | 7 | 9 (8–9) |
| held-out v2 | V10 vertical farming, rep 3 | 2026-10-19 07:07 | 0 / 0 / 0 | 5 | 8 (8–9) |
| hyperloop confirmation | V07, rep 1 | 2026-10-21 01:13 | 0 / 0 / 0 | 7 | 6 (4–6) |
| hyperloop confirmation | V07, rep 2 | 2026-10-21 01:20 | 0 / 0 / 0 | 7 | 5 (4–6) |

The academic sources these runs delivered came from arXiv, PubMed and
DOI-linked records found by the other lanes. The academic title gate v1 live
check (Part A) is not affected: OpenAlex returned results for all 20 of its
topics.

## Effect on the readings

**Held-out v2, headline.** The registered count, 25/30 in range, stands as
registered, because the protocol counts runs.

**Held-out v2, interpretation.**
- The result states that "all three misses that delivered a TRL fell below the
  floor". Two of those three, V06 rep 3 and V07 rep 3, are runs scored without
  any OpenAlex evidence.
- Without the five affected runs, 22 of 25 runs are in range. One of the 25 falls
  below its floor (V07 rep 2, TRL 3); the other two misses are the two failed runs.
- The registered "directional bias toward under-scoring" therefore rests mostly
  on degraded retrieval and should not be read as a property of the scorer.

**Hyperloop confirmation.**
- Both runs completed with seven on-topic academic sources and TRL 6 and 5.
  That is true, but it was reached with no OpenAlex results.
- Production has an OpenAlex key, so this is not the configuration production
  runs.
- What the result shows is that the corrected planner and gate reached the
  minimum from the other lanes. It does not show what production delivers for
  hyperloop.

No result or protocol document is edited. This erratum and the index carry
the correction.

## Prevention

- #252 records an OpenAlex refusal in the audit. #256 does the same for every
  academic client and counts refusals across runs in `/api/health/retrieval`.
- `benchmark.py` now:
  - stops a run before its paid crew stage when retrieval recorded an OpenAlex
    refusal or failure;
  - stops the batch there, so the remaining units can run later under
    `--resume-batch`;
  - refuses to freeze such a fixture;
  - requires `OPENALEX_API_KEY`, or an explicit `--allow-anonymous-openalex`, for
    live retrieval.
- Local batches need a free OpenAlex key in `.env`. The production key is set
  on Railway only.
