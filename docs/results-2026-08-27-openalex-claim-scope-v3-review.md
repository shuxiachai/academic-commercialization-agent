# Result: claim-scope v3 human source-value review

**Reviewed:** 2026-08-27

**Source execution:** `ad70d72120e86dad5d04f99cce319a61a623508e`

**Decision:** `complete / fail`

**Authority:** one source-locked human review over the 13 candidates from the
single frozen V01-V08 execution. This result does not authorize production Tool
Calling or a planner-trigger study.

## Intake

The strict zero-network summarizer revalidated the exact execution manifest,
four aggregate files, artifact index, eight case journals, source lock, packet
manifest and every candidate identity before reading labels.

The returned review contained:

- 13/13 completed rows and no missing or uninspectable rows;
- `reviewed_all=YES`;
- `generative_ai_use=NONE`;
- `external_sources_checked=ALL_ATTEMPTED`;
- 30 minutes of declared review time; and
- one cross-disciplinary reviewer with no specialist adjudication or
  independent replication.

The reviewer entered `2026/8/27` for the completion date. Strict intake
requires ISO `YYYY-MM-DD`, so the private working packet normalizes only that
field to `2026-08-27` after preserving the returned declaration byte for
byte. No label, note, identity or method declaration changed.

Summarization made zero provider, search or model calls.

## Frozen gates

| Gate | Observed | Required | Result |
|---|---:|---:|---|
| Cases with an accepted candidate | 7/8 | at least 6/8 | pass |
| Cases with novel relevant evidence | 7/8 | at least 6/8 | pass |
| Directly irrelevant accepted candidates | 1/13 (7.69%) | at most 5% | **fail** |

Observed labels were 12 `YES/YES` and one `NO/N/A`. The failed row was V08
provider result 6: the inspected work used a graphene/cellulose-nanocrystal
coating on a porous melamine-film structure, not the declared
biomass-derived-aerogel material scope.

The all-gates rule therefore returns:

- `protocol_status=complete`;
- `decision=fail`;
- `planner_trigger_study_eligible=false`;
- `production_connection_authorized=false`; and
- `production_connected=false`.

## Interpretation

Claim-scope v3 materially improved the earlier anonymous OpenAlex experiment:
the previous eligible review found 4/9 directly irrelevant candidates, while
this unseen challenge found 1/13. That comparison is descriptive because the
case sets differ. It does not relax the pre-registered precision-first gate.
With only 13 accepted rows, one wrong source already exceeds the 5% ceiling.

This is a useful negative result. The request, accounting, abstention,
source-lock and human-review seams worked, and relevant baseline-novel evidence
reached seven cases. The retrieval decision still did not meet the precision
required before a downstream model may use tool results.

Do not tune on or rerun V01-V08 and describe the revision as an unseen
validation. Any next candidate must be specified before seeing labels and face
a new byte-frozen challenge.

## Limits

This study measures candidate relevance and baseline-relative novelty for one
frozen eight-case OpenAlex execution. It does not measure:

- planner-trigger precision;
- OpenAlex-wide precision or recall;
- literature-wide novelty;
- source-claim truth beyond the reviewer's inspection;
- report improvement or decision correctness;
- production reliability, adoption, ROI or commercial value; or
- inter-rater agreement.

The executor, adapter, live runner and review module remain disconnected from
`pipeline_worker.py`.
