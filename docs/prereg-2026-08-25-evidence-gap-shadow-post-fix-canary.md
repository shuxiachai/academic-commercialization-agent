# Evidence-gap shadow post-fix production canary — pre-registration

**Frozen:** 2026-08-25T02:47:40Z, before the production `POST /api/runs`
**Authorized production revision:** `8d5ef489391cfa72905a8201d3bb55e76a236e14`
**Authorized paid scope:** one operator-funded source run, no retry or resume
**Soft cost stop:** `$0.05`; one already-admitted run may finish above it
**Planner or supplementary search calls authorized:** no

## Question

Does the narrow correction prompted by the first paid phase-1 canary reach the
production boundary on the same topic, without enabling a planner, executing a
supplementary search, or mutating the accepted evidence collection?

This is a post-fix observation of one previously seen topic. It is not a
held-out trigger-precision study, a phase-2 planner evaluation, or evidence of
a production success rate.

## Frozen input and preflight

The request topic is exactly:

> Wearable continuous blood pressure monitoring using photoplethysmography for
> clinical deployment

No language or weight-profile override will be supplied. Before this document
was frozen:

- GitHub deployment `6075343589` identified the authorized revision and
  Railway reported it as `success`;
- `/health/ready` returned HTTP 200 with `llm`, `search`, `outputs`, and
  `paid_accounting` all `ok`; and
- the existing operator code reached `/api/access/check` with HTTP 200. The
  code itself is not recorded in this repository.

## Frozen execution protocol

1. Submit exactly one `POST /api/runs` containing only the topic.
2. Record the returned run id before any polling.
3. Poll only that run to a terminal state. Do not retry, resume, or substitute
   another topic if it fails.
4. Inspect the public status, source collection, shadow artifact, usage, and
   checkpoint identity after termination.
5. Report every criterion as pass, fail, not inspectable, or not observed. A
   missing field is not a pass.

The `$0.05` threshold is soft because this API exposes aggregate usage only
after provider work has started. No second run is allowed even if the first
fails below the threshold.

## Acceptance criteria

1. The observed pipeline revision is the authorized revision.
2. The single source run reaches `completed` without a child resume.
3. Automatic profile selection records `biomedical`, not `industrial`.
4. Authority coverage requires `regulatory` and must not be
   `not_applicable`. If no validated regulator source is accepted, coverage
   must be `incomplete`, `regulatory` must be missing, and the shadow gate must
   expose `authority_category_missing/regulatory`. If a validated official
   regulator source is accepted, `complete` plus `no_gap` is allowed instead.
5. The shadow artifact is persisted, records zero executed calls and zero
   additional search cost, and shows identical source-collection hashes before
   and after evaluation.
6. If *American Journal of Preventive Cardiology* is retrieved again, it is
   not assigned a low/predatory credibility label. Absence of that venue is
   `not_observed`, not a pass.
7. Total provider cost is inspectable and no greater than the `$0.05` soft
   threshold.
8. No second run, resume, planner request, or supplementary search request is
   created by this protocol.

Any industrial profile, non-applicable authority result, unauthorized outbound
call, evidence mutation, terminal failure, or over-threshold inspectable cost
fails the canary. Passing this canary closes only the exact production defect;
it does not satisfy the separately frozen phase-2 thresholds.
