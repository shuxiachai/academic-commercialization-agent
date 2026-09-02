# Pre-analysis plan: adaptive role-gap v8 AC human review

**Date:** 2026-09-03 (Australia/Sydney)

**Status:** frozen after the completed AC provider run and review-boundary
implementation, but before source-lock creation, packet delivery, human labels,
or any source-value aggregate

**Production connection authorized:** no

## Question

The completed AC01-AC08 run established only that a deterministic role-gap
router could execute fifteen bounded anonymous OpenAlex requests and preserve
all provider, route, cost, and deduplication lineage. This review asks whether
the resulting sixty-four unique title-and-abstract candidates support the six
human routing-and-value gates frozen in the parent v8 protocol.

The review does not reopen AC retrieval, inspect AD01-AD08, invoke a model,
measure source recall or full-text truth, evaluate a report, or connect the
planner or production workflow.

## Exact source identity

- authorized execution revision:
  `59b5870614d23c0d9c61e7e398fa363026b6a528`
- challenge fixture SHA-256:
  `0be98f249bfd1eaf891cd3c20903b9d6ae4cd2d6431282ee32e82298a2d8ecc7`
- live-runner SHA-256:
  `4c9be921531bc632a836271ccb46ef37043e45f6a280214e034c8f48a6bf3076`
- artifact-index SHA-256:
  `ddef615d202da90a23b89345616ce97bbfffd4e8f4718569761e8b9dd19faaf6`
- source boundary: thirty-eight indexed artifacts plus the index itself
- fixed denominators: eight cases, fifteen requests, seven closure requests,
  ninety provider rows, seventy-two abstract-bearing provider candidates,
  eighteen provider-schema rejections, and sixty-four deduplicated candidates

The source lock must verify the exact index bytes before parsing it, recompute
all thirty-eight indexed file hashes, parse every Pydantic artifact, rebuild
all request journals, routes, portfolios, and aggregate CSV rows, and confirm
that both original review CSVs remain blank. A different valid v8 run is not an
acceptable substitute.

## Blind reviewer projection

The Schema v2 packet exposes, for every candidate:

- case and candidate identity;
- topic;
- title, OpenAlex URL, DOI, publisher, publication date, abstract and citation
  count;
- the exact frozen baseline; and
- the five role IDs and descriptions.

It hides anchor/closure lane membership, provider rank, duplicate occurrence
count, mechanical signal observations, missing roles, selected closure role,
route action, computed coverability, aggregate results, and answer keys.
Rows may be reordered, but every read-only field must remain identical.

The reviewer labels only:

- `directly_relevant`;
- `baseline_novel` relative to the visible frozen baseline;
- `supported_role_ids`; and
- a source-grounded note.

Allowed relevance/novelty pairs are `YES/YES`, `YES/NO`, `NO/N/A`, and
`UNVERIFIABLE/UNVERIFIABLE`. Relevant rows require at least one visible role;
other rows require an empty role array. Every completed note must contain at
least twelve non-whitespace characters. External pages are optional because
this is explicitly a title-and-abstract study; their use must still be
declared. Only `NONE` or `LANGUAGE_ONLY` generative-AI use is eligible.

The raw reviewer declaration and its file hash must be retained alongside the
normalized declaration. Incomplete, substantively AI-generated, unconfirmed,
or unverifiable reviews are distinct states and cannot produce gate metrics.

## Post-label deterministic join

Hidden route and lane provenance may be joined only after all sixty-four
labels and the declaration pass validation.

- A human source portfolio contains only `YES/YES` rows.
- A portfolio is coverable when no more than three rows jointly support every
  required role, at least one scope role, and at least one supporting role.
- A closure route is human-correct when its selected role is absent from every
  directly relevant anchor candidate. Novelty is not required for this
  absence check because the frozen routing rule asks whether the anchor
  retrieved the role, not whether the role was new to the baseline.
- An abstention is human-correct only when the anchor's `YES/YES` rows are
  already coverable.
- A closure earns selected-role value only when a closure-only `YES/YES` row
  supports the selected role. A source already observed in the anchor cannot
  earn incremental credit merely by being returned again.

The strict result may reveal per-case route assessments only after this join.
The reviewer-visible packet itself must continue to report both route and lane
exposure as false.

## Frozen conjunctive gates

1. At least 6/8 cases contain a `YES/YES` candidate.
2. Directly relevant candidates are at least 25% of all sixty-four rows.
3. At least 6/8 routing decisions are human-correct under the definitions
   above.
4. At least four of the seven closure cases contain selected-role closure
   value.
5. At least 6/8 union portfolios are human-coverable.
6. The union makes at least two more cases coverable than the anchor alone.

All six must pass. A missing or unavailable denominator is `not_evaluated`,
never pass. AC failure seals v8. AC success permits only a separately
pre-registered AD01-AD08 evaluation; it does not authorize production.

## Required implementation evidence

Before packet delivery:

1. a synthetic fifteen-request source must be reconstructed at every seam;
2. every candidate must reach the packet while all hidden fields remain absent;
3. a blank packet must remain `incomplete / not_evaluated` with no route
   assessment;
4. a complete synthetic review must exercise all six gate calculations;
5. each frozen gate must be able to veto the conjunctive decision;
6. source, packet, label, role, declaration, and production-import drift must
   fail closed;
7. the route-leak defect must be re-injected and make its seam test fail before
   restoration; and
8. the full zero-network suite, latest Ruff, and narrow Pylint must pass.

## Non-claims

This review can establish only candidate value, human-grounded route accuracy,
incremental closure value, and bounded role coverability for one consumed AC
development run. It cannot establish recall, inter-rater agreement, provider
quality in general, AD performance, report improvement, user utility, or
completed production Tool Calling.
