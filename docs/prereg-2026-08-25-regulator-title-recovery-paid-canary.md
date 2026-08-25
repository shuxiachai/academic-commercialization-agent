# Regulator-title recovery post-integration production canary — pre-registration

**Frozen:** 2026-08-25T06:32:45Z, before the production `POST /api/runs`
**Authorized production revision:** `8c592fcb35c4e89ce62764d1cd13bfb39f282bb0`
**Authorized paid scope:** one operator-funded source run, no retry or resume
**Soft cost stop:** `$0.05`; one already-admitted run may finish above it
**Planner or supplementary search calls authorized:** no

## Question

Does the precision-first regulator-title recovery reach the deployed
search-result-to-`EvidenceSource` seam when the previously observed title defect
recurs, without guessing a semantic title or changing any clean official title?

This is one repeated-topic production observation. It is not a held-out title
quality study, a real-world precision/recall estimate, or evidence that the
report itself is more accurate.

## Frozen input and preflight

The request topic is exactly:

> Wearable continuous blood pressure monitoring using photoplethysmography for
> clinical deployment

No language, weight-profile, paper, BYOK credential, planner option, or recovery
request will be supplied. Before this document was frozen:

- GitHub deployment `6077280941` identified the authorized revision and
  Railway reported it as `success`;
- `/health/ready` returned HTTP 200 with `llm`, `search`, `outputs`, and
  `paid_accounting` all `ok`;
- the selected operator code reached `/api/access/check` with HTTP 200; the
  code itself is not recorded in this repository; and
- that owner's run history reported `total=4`, with
  `20260825T024919Z-d8c43b0ba3479dc46227b4bfaa82f0a4` as the latest run.

## Frozen execution protocol

1. Submit exactly one `POST /api/runs` containing only the frozen topic.
2. Persist the returned run id before any polling or inspection.
3. Poll only that run to a terminal state. Do not retry, resume, cancel,
   substitute another topic, or submit a second run.
4. Inspect the public status, progress, validated source collection, report,
   usage, checkpoint identity, authority coverage, and evidence-gap artifact.
5. Re-read the owner history. Exactly one new root run and no child run may
   exist after the frozen baseline.
6. Classify each criterion as `pass`, `fail`, `not_inspectable`, or
   `not_observed`. Silence and absence are never a pass.

The `$0.05` threshold is soft because aggregate provider usage is exposed only
after work has started. No second run is allowed even if the first fails below
the threshold or does not retrieve a structurally broken official title.

## Acceptance criteria

1. The observed `pipeline_revision` is the full authorized revision.
2. The single root run reaches `completed`, creates no recovery child, and
   commits the ordinary seven-node checkpoint sequence without an error.
3. Total provider cost is inspectable and no greater than `$0.05`.
4. The evidence-gap artifact records zero executed planner/tool calls, zero
   supplementary-search cost, and identical source hashes before and after its
   evaluation. A disabled or failed check is not a pass.
5. If K222658 or another supported official URL arrives with a structural title
   defect, the final `EvidenceSource.title` contains only its neutral URL-derived
   identifier label, the malformed title is absent, and `credibility_reason`
   discloses the recovery. If no such defect recurs, this criterion is
   `not_observed`, not a pass.
6. Every accepted clean FDA or ClinicalTrials.gov title remains unchanged by
   the recovery seam. This can pass only for titles observable in the persisted
   collection; unobserved source classes remain `not_observed`.
7. Any recovered neutral label that reaches the persisted source collection
   also reaches the delivered report reference. A source absent from the report
   is `fail`; an untriggered recovery is `not_observed`.
8. The owner history increases from four to exactly five root runs, and this
   protocol creates no second run, resume, planner request, or supplementary
   search request.

Any unauthorized paid operation, child recovery, evidence mutation, terminal
failure, semantic title invention, unsupported-host recovery, or inspectable
over-threshold cost fails the canary. A completed run with no recurrent broken
official title is a valid production observation but does not pass the primary
title-recovery criterion.
