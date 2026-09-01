# Result: role-slot consensus v6 Y development run

**Executed:** 2026-09-01

**Authorized merged revision:**
`d23ffd54bb171d1030f5531a7d57bd6eedc5d853`

**Production connection authorized:** no

**Private labels opened:** none

**Unseen Z01-Z08 opened:** no

## Outcome

The bounded Y01-Y08 run stopped correctly at the Qwen soft-cost boundary. It
completed all eight anonymous OpenAlex requests and 21 of the possible 24
sequential `qwen3.5-plus` requests. The 21st in-flight request took the known
model estimate from below the USD 0.20 stop to USD 0.204363; the runner then
stopped before constructing the first Y08 model request. No retry, redirect,
repair, fallback, recovery, supplementary search or model substitution ran.

The serialized execution is therefore `partial / model_soft_stop`, and its
mechanical state correctly remains `not_evaluated`. This is not merely an
unfinished run that could become a pass by buying three more calls. Two frozen
gates are already mathematically unreachable:

- provisional disposition unanimity is 34/56 (60.714%) for Y01-Y07. Even if
  all eight Y08 candidates were unanimous, the maximum would be 42/64
  (65.625%), below the pre-registered 80% minimum; and
- four completed cases selected an evidence set. Even if Y08 selected one,
  the maximum would be 5/8, below the pre-registered 6/8 minimum.

The v6 development hypothesis therefore cannot pass. Y01-Y08 are consumed
development evidence, Z01-Z08 remain unopened, and v6 must not be rerun or
tuned into a pass. The production worker, report workflow and planner trigger
remain disconnected.

## Authorized and observed limits

| Boundary | Authorized | Observed |
|---|---:|---:|
| Anonymous OpenAlex requests | at most 8 | 8 completed |
| OpenAlex soft stop | USD 0.01 | USD 0.008 known |
| Sequential Qwen calls | at most 24 | 21 completed |
| Qwen soft stop | USD 0.20 | USD 0.204363 known |
| Requested / returned model | exact `qwen3.5-plus` | 21/21 exact |
| Retry, repair, fallback or recovery | forbidden | none |
| Production, report or planner connection | forbidden | false |

The small Qwen overage is within the explicitly authorized one-in-flight-call
allowance. The runner checked the stop before each later request and made no
22nd call.

## Mechanical observations

| Frozen observation | Result |
|---|---:|
| OpenAlex successful cases | 8/8 |
| Provider candidates / rejections | 64 / 0 |
| Completed case audits | 7/8 |
| Top-level valid model passes | 21/21 (100%) |
| Locally valid candidate-pass rows | 160/168 (95.238%) |
| Provisional unanimous dispositions | 34/56 (60.714%) |
| Cases with a selected evidence set | 4 completed cases |
| Prompt / completion / total tokens | 61,844 / 49,106 / 110,950 |
| Cached prompt tokens | 0 |

The top-level response-contract gate and the 95% local-row gate passed on the
attempted model calls. The 80% unanimity gate failed. Selected-set coverage
cannot reach 6/8. Because Y08 has no model audit, the complete audit boundary,
source-lock readiness and human-value gates remain unavailable rather than
being reported as passes.

### Per-case boundary

| Case | Provider rows | Model calls | Deterministic action | Selected sources | Unanimous candidates |
|---|---:|---:|---|---:|---:|
| Y01 | 8 | 3 | `ABSTAIN` | 0 | 4/8 |
| Y02 | 8 | 3 | `ABSTAIN` | 0 | 4/8 |
| Y03 | 8 | 3 | `SELECT` | 1 | 4/8 |
| Y04 | 8 | 3 | `SELECT` | 1 | 4/8 |
| Y05 | 8 | 3 | `SELECT` | 1 | 8/8 |
| Y06 | 8 | 3 | `SELECT` | 1 | 2/8 |
| Y07 | 8 | 3 | `ABSTAIN` | 0 | 8/8 |
| Y08 | 8 | 0 | not evaluated | not evaluated | not evaluated |

## Artifact and request audit

The final `execution.json` passed its committed Pydantic model. The artifact
index named 56 files; all 56 existed and every recorded SHA-256 matched. The
eight provider journals preserved the frozen Y01-Y08 order and each recorded
exactly one outbound attempt. The 21 model journals were all completed, had 21
unique trace identities, and requested and returned only `qwen3.5-plus`.

The provider calls accumulated 12.372 seconds of recorded latency. The model
calls accumulated 920.490 seconds; their median recorded latency was 45.101
seconds and the maximum was 53.952 seconds. These are one bounded run's
transport observations, not an SLO or latency distribution.

## Required follow-up

The original pre-registration requires every provider candidate to receive a
label-blind human source review even after a mechanical failure. A separate,
production-disconnected packet should therefore expose the 64 frozen titles
and abstracts plus the frozen baseline and role descriptions while hiding
model slots, consensus decisions and selected sets. That review may diagnose
retrieval and role-assignment failure surfaces; it cannot rescue v6, authorize
Z01-Z08 or connect Tool Calling to production.

Any successor semantic method must use a new identity and fresh challenge. It
must not tune on Y01-Y08 and retain the v6 name.

## Explicit non-claims

This run does not establish source truth, OpenAlex-wide precision or recall,
literature-wide novelty, human-confirmed role support, report improvement,
decision correctness, user utility, cost stability, an SLO, autonomous tool
choice or completed production Tool Calling.
