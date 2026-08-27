# Result: OpenAlex precision-v2 unseen harness implementation

**Date:** 2026-08-27
**Protocol:**
[`prereg-2026-08-27-openalex-precision-v2.md`](prereg-2026-08-27-openalex-precision-v2.md)
**Fixture erratum:**
[`errata-2026-08-27-openalex-precision-v2-unseen-fixture.md`](errata-2026-08-27-openalex-precision-v2-unseen-fixture.md)

## Outcome

The production-disconnected U01-U08 harness is implemented and its default
command completes an eight-case zero-network dry-run. It verifies the original
challenge bytes, the separately locked pre-provider correction, every
collection/plan/profile identity, all implementation hashes, the eight-request
ceiling, and the frozen source-value gates before any adapter could be
constructed.

The formal status is `ready_for_separate_live_authorization`. It is not a live
source-value result. No OpenAlex request, model call, output reservation, cost,
candidate, precision decision, or human review was produced by this result.
Production and report connections remain false.

## Frozen identities

| Artifact | SHA-256 |
|---|---|
| Original U01-U08 fixture | `355782bbe40278f44cb76f650d57fbb13be6b9097bfecb6e101815a24c47ea8b` |
| Pre-provider correction lock | `ac4a0cdfdbd18c688cba2e7edf340b0089f1402a5c549d56804dcab0231bfd84` |
| Anonymous OpenAlex adapter | `bcaa201622fe5241115661cd9d5a6f7616761eddfedb9acf364b3693e7a044c9` |
| Domain adapter boundary | `ae79c38378321f6ce4481e682787ee49f930ec4c34b696d404fcf78d97b2eeab` |
| Bounded execution kernel | `5b1b94ebd8130834603567f25336dcf106d58653e6bdd2b862509d396639e8fe` |
| Precision-v2 gate | `7c6e0f2999aae68a9caa042584c886bc5273037a2eaf2e95d80c553b7a503029` |
| U01-U08 preflight | `7dbe457aca2185d6daa4f51602e3683f60ca59a1c8dda01dec9204c3093332e7` |

The dry-run emits deterministic collection, plan, profile, and idempotency
hashes for all eight cases. `openalex_precision_live.py` is not imported by
`pipeline_worker.py`; its CLI defaults to dry-run and requires an explicit
authorization token for live mode.

## Live boundary implemented but not exercised

If separately authorized later, the runner preserves the pre-registered
constraints:

- anonymous OpenAlex only and refusal when `OPENALEX_API_KEY` is configured;
- one request per attempted case, with no redirect or internal retry;
- at most eight requests and a maximum USD 0.01 provider-reported soft stop;
- a write-once manifest before adapter construction, followed by one committed
  journal per attempted case;
- complete provider-row, legacy-quarantine, precision decision, cost, latency,
  request-identity, and trace accounting;
- `ACCEPT` rows alone enter the blank review packet, while `ABSTAIN` remains a
  recorded non-truth disposition; and
- `production_connected=false` and `report_workflow_connected=false` at every
  artifact seam.

The live path does not evaluate the frozen gates. Source truth and novelty can
only be calculated later by a source-locked Schema-v2 human review that exposes
the frozen baseline and satisfies the declared review-method constraints.

## Verification and defect re-injection

The focused preflight/live-runner suite passes **19/19** zero-network tests.
It covers fixture and correction drift, correction retargeting, case order,
provider construction timing, authorization, configured-key refusal,
implementation identity, request and cost limits, provider failures,
credential-safe tracebacks, per-row accounting, write-once artifacts, and the
production-worker disconnect.

The broad false-acceptance defect was re-injected by temporarily promoting
every precision decision to `ACCEPT` after legacy quarantine. The output seam
test failed immediately: the blank review packet grew from the expected eight
accepted rows to sixteen. Reversing that temporary patch restored all 19
focused tests. The complete suite then passed **1,614 tests, 1 skipped, and 609
subtests**; latest Ruff and CI-scope narrow Pylint passed, and measured coverage
remained **87.31%** above the unchanged 85% floor.

## Decision and next gate

No live request is authorized by this commit. After this implementation is
merged and CI is green, a separate authorization must name the exact merged
revision, permit no more than eight anonymous OpenAlex requests, and set the
USD 0.01 soft stop. A run may create evidence for human review only; it cannot
modify production evidence or reports.

Only an eligible, complete review meeting all frozen gates could justify a
later planner-trigger experiment. It would still not authorize production Tool
Calling.

## Supported claim

> A production-disconnected, identity-locked U01-U08 harness now validates the
> precision-v2 unseen protocol before provider construction and can account for
> at most eight one-attempt anonymous OpenAlex requests. Its zero-network seams
> pass; unseen source value and production suitability remain unobserved.
