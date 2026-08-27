# Result: OpenAlex scope-link candidate v4 implementation

**Date:** 2026-08-27

**Protocol:**
`docs/prereg-2026-08-27-openalex-scope-link-v4.md`

**Frozen fixture:**
`tests/fixtures/openalex_scope_link_v4_challenge.json`

**Raw fixture SHA-256:**
`f4267c6a79c0bb8a685664de5086e4cfff59ebac1b352cbb56c2277957a55cc3`

**Live provider requests made:** 0

**Provider cost:** USD 0

**Production connection:** false

## Outcome

The role-structured v4 candidate and its zero-network W01-W08 preflight are
implemented. The preflight expanded eight distinct collection, plan, profile
and idempotency identities while reporting both
`real_network_calls_performed=false` and
`live_provider_requests_authorized=false`.

This is an implementation result, not a source-value result. No OpenAlex row
has been requested for W01-W08, no candidate has received a relevance or
novelty label, and the frozen source-value gates remain unmeasured.

## What changed

`src/academic_agent/openalex_scope_link.py` separates each profile into three
roles:

- required groups for the central technology and result;
- source-text-only scope groups for the defining material, route, platform or
  operating context; and
- source-text-only supporting groups for measurements and secondary context.

A source can be `ACCEPT` only when an exact required concept and an exact scope
concept occur in the same title or the same abstract sentence. OpenAlex topics
or keywords with a score of at least `0.55` may bridge at most one required
group, but they cannot satisfy scope, support or relation evidence. Every
accepted relation serializes its field, sentence index, group IDs and exact
phrases. The only negative action is `ABSTAIN`; there is no production drop,
profile relaxation, model fallback or source-page fetch.

`openalex_scope_link_unseen.py` validates the fixture's raw bytes before JSON
parsing or case expansion. It then derives deterministic source collections,
explicit academic gap signals, one-call validated plans, profile hashes and
idempotency keys without importing an adapter, transport or execution kernel.

## Verification

The focused v4 subset passed **15/15** tests. It covers:

- same-title relation evidence reaching the serialized decision boundary;
- cross-sentence co-occurrence producing `ABSTAIN` rather than a false link;
- one bounded provider bridge for a required group;
- provider metadata being unable to satisfy a scope group;
- provider-score, missing-scope and impossible-threshold failures;
- candidate and profile identity sensitivity;
- raw fixture, case-order, request-contract and role drift; and
- continued absence from `pipeline_worker.py`.

On a clean detached worktree, the exact project command passed **1,678 tests,
one skipped test and 609 subtests**. Latest Ruff passed, and the project's
narrow Pylint configuration reported 10.00/10. The test process used a
worktree-local `TEMP`/`TMP` directory because this Windows host denies fixture
creation under its global pytest temp root; no test was ignored or relaxed.

## Defect re-injection

The abstract relation scan was temporarily changed from sentence-level
segments to one whole-abstract segment. The focused seam then failed because
`agricultural_waste` was incorrectly reported as linked even though the hard-
carbon statement and waste statement occurred in different sentences. After
restoring sentence segmentation, the focused subset returned to 15/15.

This demonstrates that the new test detects the original representation risk;
it is not merely asserting that a link-shaped field exists.

## Decision

Implementation and zero-network preflight: **pass**.

Source value and production eligibility: **not evaluated**.

W01-W08 may proceed only through a separately authorized live runner that
locks the merged revision and implementation bytes before any request. The
unchanged gates remain at least 6/8 accepted cases, at least 6/8 cases with a
relevant baseline-novel source, no more than 5% directly irrelevant accepted
sources, complete attempted-source review, and no substantive generative AI
producing the judgments.

## Non-claims

This result does not establish provider compatibility for v4, source truth,
precision, recall, novel-evidence yield, planner-trigger precision, report
improvement, decision correctness, adoption, ROI, latency, an SLO, autonomous
tool choice or production Tool Calling. The v4 gate and preflight remain
disconnected from `pipeline_worker.py`.
