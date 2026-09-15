# Saved-evidence follow-up: offline stage-control result

Date: 2026-09-15. Scope: offline engineering checks, not a provider experiment.
The [protocol](prereg-2026-09-15-report-evidence-stage-policy.md) was committed
as `22cb2a4` before implementation, against baseline
`40752a6e321c23d3eb22ed87c938b3d7f8659c1d`.

## Why another layer, not a larger budget

The first native Qwen canary made two lookups and then requested a read after
the two-tool allowance was exhausted. Its FQ01 closure failure and unrun FQ02
remain unchanged. The consumed trace is development evidence, not a fresh
evaluation. A second lookup may help literal retrieval, but increasing the
allowance would test a different paid protocol and hide the observed failure.

The separate `report_evidence_guarded_followup.py` wraps the frozen loop. It
restricts both the tools advertised to the injected callback and the returned
calls admitted to local execution:

| Observed stage | Allowed next actions |
|---|---|
| Initial | One literal lookup or a direct read of an existing snapshot ID |
| Lookup with hits | Read one returned hit ID, or finalize |
| Zero hits or any completed read | Finalize/abstain only |
| Last allowed turn | Finalize/abstain only, regardless of unused tool slots |

The original two-tool/three-turn ceilings remain. Finalization uses no tools
and `tool_choice=none`; the old auto-only Qwen adapter is not connected or
silently adapted. Wrong actions fail before dispatch, without a repair turn.
Tool results, not instructions in source text or model prose, advance state.

## Delivery is a separate seam

The old core records a read before entering its callback. That event alone is
not forwarding to the wrapper's outer transport. The new audit retains the
legacy ledger under `audit.core` and separately records downstream call counts,
advertised actions, local observations and `forwarded_read_ids`. Tests capture
the actual callback arguments; the audit does not persist argument snapshots.
Rejection before forwarding cannot claim delivery; rejection after a response
cannot erase text already supplied to that callback. Callback forwarding is
still not proof of provider receipt, correct reasoning or semantic support.

## Observed validation

- Before changes: **3,396 passed / 1,303 subtests**, 130.80 seconds.
- New policy tests: **43**. Combined old/new focused suites: **249 passed**,
  3.99 seconds. The old focused tests and frozen implementation were retained.
- Full post-implementation suite: **3,439 passed / 1,310 subtests**,
  116.19 seconds. Subtest counts are separate observations, not model cases.
- After adding this dated result, the documentation contract was rerun:
  **6 passed / 619 subtests**, 1.91 seconds. Keep this later link-check count
  separate from the preceding full-suite observation.
- Final full-tree recheck including the dated documentation: **3,439 passed /
  1,313 subtests**, 109.97 seconds. This is a separate execution, not a sum of
  the full-suite and focused subtest denominators above.
- Latest Ruff 0.16.7, the project's narrow Pylint command, offline lock check
  and diff whitespace check passed. No assertion weakening or skip was added.
- The scripted CLI executes the real local lookup/read functions, forwards an
  exact invented orchard excerpt, and produces `answered_with_evidence` with
  action sequence `[lookup, read] -> [read] -> []`. A subprocess test blocks
  network/provider use. This is a scripted positive control, not Qwen success.
- Temporarily admitting repeated lookup caused
  `test_repeated_lookup_cannot_execute_or_get_a_repair_turn` to fail at its
  actual tool-dispatch assertion: two lookups instead of one (**1 failed**,
  1.96 seconds). Restoring the implementation restored its exact hash and the
  249-test green result. This expected mutation failure is not a flaky test.

Additional controls cover zero literal hits, missing text, direct read,
unreturned/unknown IDs, duplicate call IDs, malformed arguments, source-text
instructions, downstream failures, and pre-/post-forwarding refusal.
`semantic_support=not_assessed` and `answer_verification=not_verified` remain
explicit, including when the answer references an actual saved excerpt.

Implementation SHA-256:
`c1b02a07808f737cf4bc89e7088c985aad56adca05ee9b7f72eb74852c398e0b`.
Tests SHA-256:
`48c7a90cc82d87719b5e70218b96ae887f38f292345fc63ed982832ac847817c`.
Scripted CLI SHA-256:
`58ce71bb04f25bcd23aa05ca097a0bbc3ce38cf13508eb6062f0cd2e38ce2af5`.

All 44 protected files retained their pre-change SHA-256 values: the old
implementation/protocol set, 30 benchmark source snapshots and four artifacts
from the previous paid batch. Nothing was rewritten as a new paid result.

An independent read-only AI review found no blocking code issue. Its final
documentation check corrected an overstatement about persisting callback
arguments: the tests observe them, while the audit keeps bounded observations.
The reviewer inspected code and declarations, but did not independently rerun
the tests or hash measurement. This is not an independent human/model evaluation.

## What this does not establish

No model/search requests, credentials, new real reports or production routes
were used. Direct-read membership does not prove the model did not guess an
ID: the catalog contains bounds and a count, not IDs. Zero substring hits do
not prove absent evidence. These controls do not establish model compliance,
answer correctness, reader utility or autonomous supplementation. The original
FQ01 and v8 failures stay failures. A future stage-aware live adapter and new
frozen protocol are separate work; unused slots from the old paid authorization
are not permission to rerun it. Deploying this code package does not activate
the offline follow-up on the website.
