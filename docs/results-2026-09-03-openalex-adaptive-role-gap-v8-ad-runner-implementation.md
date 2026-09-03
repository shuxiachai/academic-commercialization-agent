# Implementation result: adaptive role-gap v8 AD unseen runner

**Date:** 2026-09-03 (Australia/Sydney)

**Status:** implementation and zero-network verification complete; live provider execution not authorized or performed

**Production connection authorized:** no

## Outcome

A separately named AD01-AD08 evaluation runner is now implemented without widening the consumed AC runner or importing an experimental v8 component into production. The runner accepts only the frozen `unseen` cohort, defaults to a zero-network dry run, and preserves the same routing, portfolio, provider, qualification, request, and cost contracts that qualified on AC01-AC08.

No OpenAlex request, model call, human review, recovery action, or production connection occurred during this implementation. AD remains outcome-unseen.

## Frozen lineage

- AD evaluation pre-registration: `docs/prereg-2026-09-03-openalex-adaptive-role-gap-v8-ad-evaluation.md`
- implementation base revision: `243d23f6f000523da96c8c37c58f75a9bf264a27`
- challenge fixture: `tests/fixtures/openalex_role_gap_v8_challenge.json`
- fixture SHA-256: `0be98f249bfd1eaf891cd3c20903b9d6ae4cd2d6431282ee32e82298a2d8ecc7`
- runner observed SHA-256 at zero-network verification: `1f188fbdef225e0f6407b24a2ddbf40b66f5425ff9013021b5e94e0f176ccffa`
- accepted case order: exactly `AD01` through `AD08`

The runner is a deliberate audit snapshot of the already-tested AC execution kernel. Several Pydantic contracts in the consumed AC runner encode AC identifiers at serialization seams. Generalising those models would mutate the implementation that produced the qualified AC artifacts and make later comparison harder to audit. The separate snapshot keeps the frozen behavior inspectable while adding only an AD-only entrypoint and AD-specific artifact identities.

## Implemented authority boundary

`openalex_role_gap_evaluation.py` now:

1. rejects any cohort other than `unseen` before output reservation or adapter construction;
2. verifies the raw fixture, AD order, all case/anchor/closure identities, frozen contracts, and committed behavior dependencies before spending authority can exist;
3. refuses a configured `OPENALEX_API_KEY`, requires an explicit anonymous-budget acknowledgement, and caps the soft stop at USD 0.02;
4. permits one anchor and at most one already-frozen role-closure request per case, for eight to sixteen sequential requests and at most ninety-six provider rows;
5. forbids retries, redirects, model-written queries, repair, fallback, recovery, parallel requests, and production imports through the inherited adapter and execution contracts; and
6. observes its own file hash without attempting a recursive predeclared self-hash.

The default CLI path is `protocol_dry_run()`. Its completed output reports eight unseen cases, forty-eight potential call identities, a sixteen-request maximum, zero model calls, `real_network_calls_performed=false`, and every production/report/planner/recovery connection as false.

## Persistence and client-boundary evidence

The execution path preserves the pre-registered write order:

1. validate immutable identity and authority;
2. reserve a fresh output directory;
3. persist the complete AD manifest before adapter construction;
4. persist the anchor request and every provider row or rejection before routing;
5. persist the full route decision before an optional closure request;
6. persist closure evidence before portfolio construction;
7. persist the case portfolio before the next case; and
8. emit content-addressed execution, provider-row, route, occurrence, deduplication, unique-candidate, blank-review, and artifact-index outputs.

The AD manifest, execution artifact, and artifact index use AD-specific modes. The artifact index also carries `cohort=unseen`; this prevents a correctly computed cohort value from disappearing at the final client boundary. Partial execution remains distinct from abstention or completion, and uninspectable provider accounting cannot become zero cost.

## Verification

- AD runner focused suite: **21/21 passed**.
- Complete zero-network suite: **1,964 tests and 657 subtests passed**.
- Latest Ruff on the new runner and tests: passed.
- Default runner dry run: passed with the frozen fixture and zero external calls.
- Existing AC implementation and historical frozen tests were not modified.
- `src/academic_agent/pipeline_worker.py` remains disconnected from the AD runner and every experimental v8 module.

Public cross-platform CI, browser smoke, and Docker checks are required on the eventual pull request before merge. This local result does not pre-announce those remote checks.

## Required defect reinjection

Two pre-registered defects were inserted one at a time and then removed:

| Injected defect | Expected seam | Observed result |
|---|---|---|
| Permit `development` at the AD entrypoint | Cohort authority before adapter/output | The focused test failed with `DID NOT RAISE`; restoring unseen-only validation returned the suite to green. |
| Drop the final route only when serializing aggregate CSV output | Internal-to-client route boundary | The focused test failed with `route decision disappeared before the aggregate boundary`; restoring the complete route sequence returned the suite to green. |

These failures demonstrate that the tests guard the authority and delivery seams rather than merely checking internal fields.

## Decision and non-claims

The implementation satisfies the zero-network prerequisite for asking the owner whether to run the frozen AD cohort. It does not authorize that run. A future authorization must name the exact merged implementation revision, the unchanged fixture SHA-256 above, no more than sixteen sequential anonymous OpenAlex requests, and a total soft stop no greater than USD 0.02.

This result does not establish provider compatibility, source quality, routing accuracy, closure value, unseen generalisation, report improvement, planner-trigger precision, user utility, cost stability, latency, autonomous Tool Calling, or production readiness. AD becomes consumed at its first provider request, even if that request produces a partial or failed run.
