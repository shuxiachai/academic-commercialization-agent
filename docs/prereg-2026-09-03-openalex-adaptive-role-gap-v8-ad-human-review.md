# Pre-analysis plan: adaptive role-gap v8 AD human review

**Date:** 2026-09-03 (Australia/Sydney)

**Status:** frozen after the completed AD01-AD08 provider run and before an
AD-specific review-boundary implementation, source-lock creation, packet
delivery, human labels, or source-value aggregate

**Production connection authorized:** no

## Question

The outcome-unseen AD01-AD08 run completed fifteen bounded anonymous OpenAlex
requests and preserved every provider, route, cost, and deduplication seam.
This review asks whether the resulting sixty-seven unique title-and-abstract
candidates satisfy the same six human routing-and-value gates that the AC
development cohort passed.

The review does not reopen retrieval, rerun AD, invoke a model, inspect a
different provider, estimate recall or full-text truth, evaluate a report, or
connect the planner or production workflow.

## Exact source identity

- authorized and executed revision:
  `b54fa22666805f8d0de0ff7e26c42af88b641615`
- challenge fixture SHA-256:
  `0be98f249bfd1eaf891cd3c20903b9d6ae4cd2d6431282ee32e82298a2d8ecc7`
- live-runner SHA-256:
  `1f188fbdef225e0f6407b24a2ddbf40b66f5425ff9013021b5e94e0f176ccffa`
- artifact-index SHA-256:
  `01b3193d60d7405388b6d624da543131e18e67d13910bdb42f74e42e21af6e8f`
- source boundary: thirty-eight indexed artifacts plus the index itself
- exact closure cases: `AD01`, `AD02`, `AD04`, `AD05`, `AD06`, `AD07`, and
  `AD08`; `AD03` is the only no-gap abstention
- unique candidates by case: AD01=10, AD02=4, AD03=5, AD04=11, AD05=10,
  AD06=9, AD07=10, AD08=8
- fixed totals: eight cases, fifteen requests, seven closure requests, ninety
  provider rows, seventy-three abstract-bearing provider candidates,
  seventeen provider-schema rejections, and sixty-seven deduplicated
  candidates
- provider-reported cost: USD 0.015

The source lock must verify the exact artifact-index bytes before parsing it,
recompute every indexed file hash, parse every Pydantic artifact, rebuild the
lane journals, route journals, case portfolios, and aggregate CSV rows, and
confirm that the two provider-created review CSVs remain blank. A different
valid AD execution is not an acceptable substitute.

The source lock is controller-only evidence. It must be stored separately from
the reviewer packet and must never be delivered to the reviewer.

## Blind reviewer projection

The Schema v2 packet exposes, for every candidate:

- case and candidate identity;
- topic;
- title, canonical OpenAlex URL, DOI, publisher, publication date, abstract,
  and citation count;
- the exact frozen baseline; and
- the five role IDs and descriptions.

It hides anchor/closure lane membership, provider rank, duplicate occurrence
count, mechanical signal observations, missing roles, selected closure role,
route action, computed coverability, aggregate results, and answer keys. Rows
may be reordered, but every read-only field must remain unchanged.

The reviewer labels only:

- `directly_relevant`;
- `baseline_novel` relative to the visible frozen baseline;
- `supported_role_ids`; and
- a source-grounded note.

Allowed relevance/novelty pairs are `YES/YES`, `YES/NO`, `NO/N/A`, and
`UNVERIFIABLE/UNVERIFIABLE`. Relevant rows require at least one visible role;
other rows require an empty role array. Every completed note must contain at
least twelve non-whitespace characters. External pages are optional because
this is a title-and-abstract study, but their use must be declared. Only
`NONE` or `LANGUAGE_ONLY` substantive generative-AI use is eligible.

The raw declaration strings and file hash must be retained alongside the
normalized declaration. Incomplete, substantively AI-generated, unconfirmed,
or unverifiable reviews are distinct states and cannot produce gate metrics.

## Post-label deterministic join

Hidden route and lane provenance may be joined only after all sixty-seven
labels and the reviewer declaration pass strict validation.

- A human source portfolio contains only `YES/YES` rows.
- A portfolio is coverable when no more than three rows jointly support every
  required role, at least one scope role, and at least one supporting role.
- A closure route is human-correct when its selected role is absent from every
  directly relevant anchor candidate. Novelty is not required for this
  absence check because routing asks whether the role was retrieved, not
  whether it was new to the baseline.
- The AD03 abstention is human-correct only when the anchor's `YES/YES` rows
  are already coverable.
- A closure earns selected-role value only when a closure-only `YES/YES` row
  supports the selected role. A cross-lane duplicate cannot earn incremental
  credit.

The strict result may reveal per-case route assessments only after this join.
The reviewer-visible packet must continue to report route and lane exposure as
false.

## Frozen conjunctive gates

1. At least 6/8 cases contain a `YES/YES` candidate.
2. Directly relevant candidates are at least 25% of all sixty-seven rows.
3. At least 6/8 routing decisions are human-correct.
4. At least four of the seven closure cases contain selected-role closure
   value.
5. At least 6/8 union portfolios are human-coverable.
6. The union makes at least two more cases coverable than the anchor alone.

All six must pass. A missing or unavailable denominator is `not_evaluated`,
never pass. Failure seals adaptive role-gap v8. Passing all six permits only
separately pre-registered disabled-path, planner-trigger, and report-value
studies; it does not authorize production.

## Required implementation evidence

Before packet delivery:

1. a synthetic fifteen-request AD source must be reconstructed at every seam;
2. the implementation must bind the exact non-positional closure-case set, so
   the AC assumption that the final case abstains cannot be reused;
3. every candidate must reach the packet while all hidden fields remain absent;
4. a blank packet must remain `incomplete / not_evaluated` with no route
   assessment;
5. a complete synthetic review must exercise all six gate calculations;
6. each frozen gate must independently veto the conjunctive decision;
7. source, packet, label, role, declaration, and production-import drift must
   fail closed;
8. the `CASE_IDS[:-1]` positional closure defect and a route-decision leak at
   the reviewer boundary must each be re-injected and make a seam test fail
   before restoration; and
9. the full zero-network suite, latest Ruff, narrow Pylint, browser smoke, and
   Docker checks must pass.

## Non-claims

This review can establish candidate value, human-grounded route accuracy,
incremental closure value, and bounded role coverability for one consumed AD
unseen run. One reviewer cannot establish inter-rater agreement. A title-and-
abstract review cannot establish full-text truth or recall. Neither a complete
packet nor a six-gate pass establishes report improvement, planner-trigger
precision, autonomous Tool Calling, user utility, or production readiness.
