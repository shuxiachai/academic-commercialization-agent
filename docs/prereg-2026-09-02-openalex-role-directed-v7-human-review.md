# Pre-registration amendment: role-directed retrieval v7 human review

**Frozen:** 2026-09-02 (Australia/Sydney), after the authorized AA01-AA08
provider run completed and before source locking, packet generation, human
labels, metric inspection, or access to AB01-AA08.

**Parent protocol:**
[`prereg-2026-09-01-openalex-role-directed-retrieval-v7.md`](prereg-2026-09-01-openalex-role-directed-retrieval-v7.md)

**Live-run result:**
[`results-2026-09-02-openalex-role-directed-retrieval-v7-development-live.md`](results-2026-09-02-openalex-role-directed-retrieval-v7-development-live.md)

**Executed revision:**
`2a61c32d4693f4f9a44965312c378dc8f14fb308`

**Fixture SHA-256:**
`9a91746d0a77fee6d57bfc91ae4329ab78a89109fca6f35171d56c0f3ee95761`

**Artifact-index SHA-256:**
`7ff4d2a86d19caac5e2a73177870f77540ec19a431bc42e3f321324830bf56bc`

**Frozen review denominator:** 79 DOI/OpenAlex-deduplicated candidates across
AA01-AA08, distributed 11, 10, 7, 9, 10, 12, 10, and 10 respectively.

**Production connection authorized:** no

## Question

Does the exact two-lane AA portfolio pass every human candidate-value gate
registered by the parent protocol without exposing retrieval-lane provenance
to the reviewer or changing the frozen evidence?

This review measures title-and-abstract relevance, novelty relative to the
visible frozen baseline, role coverability, and lane-level incremental value.
It does not verify source truth against full text, estimate recall, evaluate a
semantic judge, measure report improvement, or authorize production Tool
Calling.

## Source-lock boundary

The lock must bind the exact manifest, execution, three CSV boundaries,
sixteen lane journals, eight case portfolios, and artifact index from
`outputs/openalex-role-directed-v7-aa-live-2026-09-02/`. Every file hash must
match the completed run before a packet can be created. The lock is a separate
study-owner attestation and must never modify or live inside the write-once
provider directory.

Before locking, validation must independently reconstruct and compare:

1. all sixteen completed one-attempt lane journals and their provider cost;
2. all eight portfolios and every occurrence-to-unique-candidate link;
3. all 96 provider rows, including twelve provider rejections;
4. all 79 unique candidates and 79 blank review rows;
5. the artifact index and every indexed file hash; and
6. the zero-model, zero-key, production/report/Planner/recovery disconnection
   states.

Any byte, identity, row, order, accounting, or lineage drift stops before
packet creation. A reconstructed approximation is not an acceptable source.

## Reviewer blinding and visible context

The packet exposes, for every candidate:

- case and immutable candidate identity;
- topic, title, OpenAlex URL, DOI and bibliographic metadata;
- the frozen OpenAlex abstract;
- the exact frozen baseline sources; and
- the complete frozen role catalogue with role IDs and descriptions.

The reviewer-facing rows do **not** expose retrieval-lane membership, provider
rank, duplicate-occurrence count, evidence-lane incremental status, computed
coverability, any model judgment, or any answer key. Those fields remain in
the source-locked execution and are joined only after human labels have been
validated. Row order may change, but identities and read-only context may not.

The review is deliberately title-and-abstract based. Opening external pages is
optional and must be declared as `ALL_ATTEMPTED`, `SOME`, or `NONE`; it is not
an eligibility gate because the parent protocol defines role support from the
frozen title and abstract. This limitation must remain visible in the result.

## Human labels

Every row requires one of these relevance/novelty pairs:

- `YES/YES`: directly relevant and materially absent from the frozen baseline;
- `YES/NO`: directly relevant but already represented by the baseline;
- `NO/N/A`: adjacent, generic, or not directly relevant; or
- `UNVERIFIABLE/UNVERIFIABLE`: the frozen title and abstract are insufficient
  for a defensible judgment.

`supported_role_ids` is a JSON array containing only role IDs from the visible
case catalogue. Relevant rows require at least one supported role. `NO/N/A`
and `UNVERIFIABLE/UNVERIFIABLE` require `[]`. Every completed row also requires
a source-grounded note of at least twelve non-whitespace characters.

The declaration records reviewer identity, completion, generative-AI use,
external-source access, elapsed minutes, expertise, date, and limitations.
Only `NONE` and `LANGUAGE_ONLY` AI use are eligible. Substantive generated
judgments remain inspectable but are excluded from gate evaluation. Missing
rows, partial rows, an incomplete declaration, `reviewed_all=NO`, or any
`UNVERIFIABLE` row must remain visibly not evaluated rather than become zero
errors.

## Deterministic role-coverability calculation

Only `YES/YES` candidates may contribute to coverability. A candidate's
supported roles are exactly the human-entered, validated role IDs. A case is
coverable when a deterministic search finds a set of at most three candidates
whose union contains:

- every required role;
- at least one scope role; and
- at least one supporting role.

The search considers set sizes one through three and records the first
lexicographically stable minimal cover for audit. `technology_scope`-only
coverability uses candidates returned by that lane, including a deduplicated
candidate that appeared in both lanes. Union coverability uses every candidate.
Lane membership is joined from the source lock after labels are complete; the
reviewer never supplies it.

## Frozen gates

All five parent gates remain conjunctive and unchanged:

1. at least 6/8 cases contain a `YES/YES` candidate;
2. at least 6/8 cases are union-coverable under the three-source ceiling;
3. `YES/*` candidates are at least 25% of all 79 reviewable candidates;
4. at least 4/8 cases contain a directly relevant candidate returned by
   `technology_evidence` but not by `technology_scope`; and
5. union coverability exceeds scope-lane coverability by at least two cases.

No unavailable denominator or ineligible review can pass. The output must
report the observed numerator, denominator, case IDs, selected cover row IDs,
each threshold result, and one conjunctive decision.

## Required zero-network verification

Tests must prove that source and packet drift fail closed; all 79 identities
reach the reviewer and result seams; lane memberships are absent from every
reviewer-visible row; blank and partial reviews remain `not_evaluated`; unknown
roles and relevance/role contradictions are rejected; each of the five gates
can fail independently; substantive AI use is excluded; and neither the
production worker nor a provider/model adapter imports this review path.

At least two defects must be re-injected and observed red before restoration:

1. leaking lane membership into the reviewer-visible packet; and
2. calculating scope-only coverability from the full two-lane union.

Existing assertions may not be weakened or skipped.

## Stop rules and non-claims

AA01-AA08 are consumed after the existing provider run and may not be rerun or
tuned on. A failed human gate seals v7. A pass permits only a separately
pre-registered AB evaluation; it does not authorize opening AB automatically,
adding a semantic judge, running a Planner-trigger study, or connecting any
Tool Calling path to production.
