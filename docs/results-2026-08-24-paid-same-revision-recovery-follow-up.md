# Result: same-revision reuse succeeded but typed context was not restored

**Date:** 2026-08-24
**Pre-registration commit:** `9c22fde`
**Production revision:** `f9e3b611779af1e3148cad1d5552758bd67ea274`
**Source run:** `20260824T073315Z-a214ab4947f0b78f7ff2bcf8d8b3dc4d`
**Child run:** `20260824T073632Z-6d42b05a6a46c605d8c7e16342395844`
**Result:** **NON-PASS — four nodes were reused, but the child failed at the
Writer guardrail**

## Decision

This follow-up closes one narrower question and exposes a new production seam.
The immutable child reused the exact same-revision retrieval, academic, patent,
and market checkpoints. Its usage record shows zero requests for all three
evidence agents, and the child began paid work at the Writer. That is direct
provider-backed evidence that contiguous-prefix reuse itself worked.

The end-to-end recovery still did not pass. The restored evidence
`TaskOutput` objects contained their validated raw JSON but not their typed
`EvidenceReport` values. The final-report guardrail reads only those typed
values when it builds the allowed-source registry, so it rejected both Writer
attempts with:

> No validated evidence sources are available in task context.

No retry, replacement source, alternate identity, BYOK bypass, or production
change was used. Do not describe this result as a completed paid recovery.

## Frozen relationship to the first canary

The [first canary](results-2026-08-24-paid-same-revision-recovery.md) remains a
separate non-pass: its only child admission was rejected by that owner's daily
wallet cap. The study owner later supplied another validated operator code.
Because code-owned runs cannot change owner identity at recovery, the
[follow-up protocol](prereg-2026-08-24-paid-same-revision-recovery-follow-up.md)
froze a new source and required the second code to own both source and child.
The code and its hash are absent from every retained artifact.

## Preconditions

Immediately before the new source:

- `/health` reported zero active runs and zero active paid operations;
- `/health/ready` returned HTTP 200 with `ready=true`, and LLM, search,
  outputs, and paid accounting were all `ok`;
- the second code passed a read-only authentication request and saw zero runs;
- Railway reported deployment
  `a65d414c-33ed-415b-a9f0-33786c9cdb92` as `SUCCESS`, instance
  `71e5ba8b-719a-4a4a-be2e-449e2d7923a5` as `RUNNING`, and the frozen
  `f9e3b61` commit;
- the mounted output volume was `/app/outputs`.

All seven CI jobs for the pushed pre-registration were green before source
admission.

## Observed sequence

1. The source was admitted between `07:33:15.2120472Z` and
   `07:33:15.6283163Z`.
2. Public polling first observed retrieval committed at
   `07:34:31.1880691Z`, patent at `07:34:40.5485204Z`, academic at
   `07:34:45.2109653Z`, and the exact four-node prefix at
   `07:34:49.8866464Z`. These are observation times, not claimed manifest
   commit times.
3. At the four-node observation the source was still running at
   `Agent 4 — Report Writing`, with 8 academic, 8 patent, and 7 market
   sources and no failed retrieval domain.
4. Railway accepted the immediate restart without rebuild and returned the
   same deployment id. Readiness was first recorded again at
   `07:35:37.9284618Z`; the deployment, instance, image, commit, and volume
   mount were unchanged.
5. The source was observed failed at `07:36:13.7034967Z`, still exposing the
   exact four-node prefix with no checkpoint errors.
6. The only child was admitted between `07:36:32.0864128Z` and
   `07:36:32.5946014Z`.
7. At `07:36:48.7250518Z`, both public status surfaces reported
   `recovery.state=reused`, the exact four reused nodes, and
   `next_node=writer`. The Writer checkpoint was correctly reported missing.
8. The child failed at `07:37:55.9955812Z` after two Writer requests. It
   committed no later node and produced no report.
9. After the audit, `/health` again reported zero active runs and zero active
   paid operations. The second code's scoped history contained exactly the
   failed source and failed child.

## Persisted and client evidence

The source and child manifest pairs carry the same `git:f9e3b611...`
revision and exact matching output hashes:

| Node | Matching source/child output SHA-256 |
|---|---|
| retrieval | `f2ea292ef5b06e94e8bbaaefee3c107504e7208f6d2f2cf0d6470ddd569cee63` |
| academic | `60c2fe0c55dabd9251bd3b94755549648e1fdd4727c737dfcb737e5c2ce5dc5e` |
| patent | `67fc17f4f55a90d341e05cf4f7aa7c771b1852f54ac6a2e7e7c40e644af5fbda` |
| market | `9451e91df3a30e42f2163cff5bd355d8e077203418c9a84b816e74d82fb44a6e` |

The child progress stream represented the three evidence agents as
`Reused validated checkpoint` and then emitted a Writer action. Final usage
reported:

| Measure | Child observation |
|---|---|
| Total requests | 2 |
| Total tokens | 31,642 |
| Cached prompt tokens | 15,104 |
| Estimated cost | $0.014576 |
| Academic agent | 0 requests / 0 tokens |
| Patent agent | 0 requests / 0 tokens |
| Market agent | 0 requests / 0 tokens |
| Writer | 2 requests / 31,642 tokens |
| Reviewer / Scorer | 0 requests / 0 tokens |
| Usage completeness | `true` for the child |

The report endpoint returned HTTP 409 because the child failed. The sources and
steps endpoints remained readable at HTTP 200, with 61,060 and 334 UTF-8 bytes
respectively.

All four source and child checkpoint manifests recorded `usage=null`.
Consequently the interrupted source's provider usage cannot be reconstructed,
and total source-plus-child cost is `not_inspectable`. The child's
`$0.014576` is below the soft stop but is not the experiment total.

## Pre-registered criteria

| Criterion | Result |
|---|---|
| Eligible prefix visible while source was running | pass |
| Same revision and readiness after restart | pass |
| Source terminal and exactly one child admitted | pass |
| Child reports the exact reusable contiguous prefix | pass |
| Reused evidence nodes did not execute new child provider work | pass |
| Child completes report and all seven checkpoints | **fail** |
| Total source plus child cost is within the soft stop | not inspectable |

The aggregate result is non-pass because the frozen protocol has no
partial-pass threshold.

## Root cause

The failure is deterministic and sits between checkpoint hydration and the
existing report guardrail:

1. Evidence guardrails set `output.pydantic` to an `EvidenceReport` after
   validating each live evidence-agent response.
2. `CheckpointRuntime.restore_contiguous_prefix()` reconstructs each reused
   `TaskOutput` with `description`, `expected_output`, `raw`, and
   `agent`, but does not reconstruct `pydantic`.
3. `collect_context_sources()` and `collect_context_finding_sources()` read
   only `task.output.pydantic` values that are `EvidenceReport` instances;
   they deliberately do not trust unvalidated arbitrary raw text.
4. The Writer received the raw context and generated output, but its guardrail
   built an empty allowed-source registry from the restored tasks. Both allowed
   Writer attempts were therefore rejected before later stages could run.

The existing offline recovery tests assert that hydrated tasks are skipped,
republished, and visible through status seams. They do not feed a partially
restored production `EvidenceReport` prefix into the real final-report
guardrail. That missing seam assertion allowed 1,339 tests to pass while this
production-only path remained broken.

## What this establishes

- A real same-revision Railway restart preserved and reused an exact four-node
  prefix.
- The immutable child republished byte-identical checkpoint outputs.
- The three reused evidence agents made zero new child provider requests.
- Typed guardrail context is part of the recovery contract even when raw task
  context is sufficient for model generation.

## What remains open

End-to-end paid recovery remains unproven until typed evidence outputs are
reconstructed from already validated checkpoint JSON, a seam test reproduces
this exact failure, and a separately pre-registered post-fix canary completes
the remaining Writer, Reviewer, and Scorer suffix.

This result does not support general token, cost, or latency savings; a
production recovery rate or SLO; exactly-once execution; report correctness; or
six-stage necessity.
