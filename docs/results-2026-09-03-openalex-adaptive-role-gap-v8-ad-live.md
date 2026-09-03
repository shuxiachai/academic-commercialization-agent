# Adaptive role-gap v8: AD unseen live-provider result

**Date:** 2026-09-03 (Australia/Sydney)

**Executed revision:**
`b54fa22666805f8d0de0ff7e26c42af88b641615`

**Production connection authorized:** no

## Outcome

The separately authorized AD01-AD08 unseen run completed under the frozen
adaptive role-gap v8 contract. The runner made fifteen sequential anonymous
OpenAlex requests: eight anchor requests and seven selected role-closure
requests. AD03 found no mechanical role gap and explicitly abstained from a
second request. Every request completed on its first and only attempt.

This is a mechanical provider-execution pass and is eligible for an exact
source lock. It is not a source-value result and does not establish that v8
generalizes.

| Observation | Result |
|---|---:|
| Cases completed | 8 / 8 |
| Requests completed | 15 / 15 |
| Anchor requests | 8 |
| Closure requests | 7 |
| Explicit no-gap abstentions | 1 (`AD03`) |
| Provider rows | 90 |
| Abstract-bearing candidates | 73 |
| Provider-schema rejections | 17 |
| DOI/OpenAlex-deduplicated candidates | 67 |
| Provider-reported cost | USD 0.015 |
| Frozen soft stop | USD 0.02 |
| Recorded provider latency | 17,011.77 ms |
| Model calls | 0 |
| API key used | no |
| Retry, redirect, fallback, or recovery | none |

The request count stayed below the sixteen-request ceiling and the recorded
cost stayed below the separately authorized soft stop. The anonymous adapter's
daily-budget contract remained USD 0.10; the narrower run-level stop was USD
0.02 and governed whether a later request could start.

## Frozen identity

- challenge fixture SHA-256:
  `0be98f249bfd1eaf891cd3c20903b9d6ae4cd2d6431282ee32e82298a2d8ecc7`
- AD runner SHA-256:
  `1f188fbdef225e0f6407b24a2ddbf40b66f5425ff9013021b5e94e0f176ccffa`
- artifact-index SHA-256:
  `01b3193d60d7405388b6d624da543131e18e67d13910bdb42f74e42e21af6e8f`
- execution artifact SHA-256:
  `4197bace48cc305b4db71bd8943d68ef7b5691a9950a49ebb78b8724badf7f26`
- manifest SHA-256:
  `f16ba2eef97a46d3f10b04e6381ca1244b39a6876f7c01966c8231ddda0ab5d6`
- indexed source files: 38; all 38 recomputed hashes matched the index

The write-once source remains in the local, gitignored output directory
`outputs/20260903-openalex-role-gap-v8-ad-live-b54fa22/`. Raw titles and
abstracts are not added to the public repository by this result note.

## Route observations

| Case | Action | Selected missing role |
|---|---|---|
| AD01 | search | `polyol_reuse` |
| AD02 | search | `source_separated_urine` |
| AD03 | abstain | none |
| AD04 | search | `infection_reduction` |
| AD05 | search | `pulp_mill_lignin_waste` |
| AD06 | search | `agricultural_groundwater` |
| AD07 | search | `magnetic_guidance` |
| AD08 | search | `offshore_wind_steel` |

These are deterministic lexical route observations, not human judgments that
the route was correct. The exact unique-candidate denominators by case are 10,
4, 5, 11, 10, 9, 10, and 8 respectively.

## Boundary result

The aggregate reports:

- `overall_state=completed`;
- `review_packet_eligibility=eligible_for_source_lock`;
- `serialized_boundary_complete=true`;
- `source_lock_state=not_created`;
- `human_review_state=not_prepared`; and
- `source_value_state=not_evaluated`.

The manifest and artifact index both keep production, report-workflow,
planner-trigger, checkpoint-recovery, and model-call connections false. A
successful process exit therefore does not masquerade as a successful human
value evaluation.

## Next decision

Before seeing any AD human label, freeze an AD-specific source-lock and blind
review protocol. That boundary must bind the exact bytes above, expose all 67
candidate rows and eight frozen case contexts, hide route and lane provenance,
and join adaptive provenance only after every label and reviewer declaration
validate. The inherited six conjunctive gates must not change.

Even if all six AD gates pass, v8 remains production-disconnected. A pass would
permit only separately pre-registered disabled-path, planner-trigger, and
report-value studies.

## Non-claims

This run establishes one frozen cohort's anonymous OpenAlex compatibility,
bounded request accounting, durable route execution, and serialized lineage.
It does not establish candidate relevance, novelty, route correctness,
closure value, role coverability, recall, full-text truth, inter-rater
agreement, report improvement, user utility, latency reliability, autonomous
query generation, or production Tool Calling.
