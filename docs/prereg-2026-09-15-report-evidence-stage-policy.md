# Saved-evidence follow-up: offline stage-aware action controls

Registered: 2026-09-15, before implementing this policy.
Baseline: `40752a6e321c23d3eb22ed87c938b3d7f8659c1d` (public PR #144).
Scope: offline implementation and regression only; **no live authorization**.

## Observed problem, not a new success claim

The [first native canary](results-2026-09-15-report-evidence-followup-qwen-canary.md)
made two lookups before asking to read. Both local tool attempts were already
consumed, so read did not execute and no final answer was delivered. FQ01 failed;
FQ02 was not run. The three replies and their usage are transport observations,
not successful evidence-to-answer closure. The original batch stays unchanged.

The first long query was not a contiguous substring in the synthetic source.
The next shorter query matched. Assuming the model intended keyword search is
an inference. The snapshot catalog contains bounds and a count, not source IDs
or a second route to source text.

## Hypothesis and immutable boundaries

Expose only stage-appropriate actions and enforce the same permissions before
local dispatch, reserving an opportunity for reading and finalization. Keep the
existing maximum of two tool attempts and three transport turns. A restriction
in tool descriptions alone is not enforcement.

- Preserve the snapshot matcher, old loop, Qwen adapter, paid runner, fixture,
  preregistrations and recorded failures. Add separate modules; do not copy or
  relax a paid protocol to obtain an apparent pass.
- Preserve strict arguments, call IDs, snapshot-bound evidence receipts and
  `semantic_support=not_assessed` / `answer_verification=not_verified`.
- No provider calls, credentials, HTTP routes, external retrieval, additional
  sources, production activation, scoring changes or v8 reclassification.
- Never treat a zero literal hit as proof of absent literature. Earlier
  abstention may improve the control boundary without solving the positive task.
- A malicious source or model-generated state declaration must not grant a
  new action, source scope, tool attempt or model turn.

## Offline acceptance and falsification

Tests must observe the arguments that reach the actual injected callback and
the actual lookup/read functions, not merely inspect a policy field or source
string. Include these positive and negative controls:

1. Matching lookup, exact saved-text read, and final answer preserve original
   call IDs, excerpt hashes and delivered evidence IDs within the old ceilings.
2. A permitted direct read can proceed to finalization without a spare lookup.
3. Missing text remains explicit and can produce abstention without evidence.
4. Repeated lookup cannot consume the read opportunity. A response requesting
   an unadvertised action cannot reach the tool function or cause a repair turn.
5. The final allowed turn has no tool opportunity. Lack of executed/forwarded
   evidence must never become a successful read or complete verification.
6. Long noncontiguous queries still have literal matching semantics. A zero-hit
   path may terminate/abstain, but must not pass the prior positive case.
7. Unknown IDs, malformed arguments, duplicate IDs, transport failure and
   source-text instructions do not expand scope or conceal failed checks.
8. The synthetic CLI exercises real local tools and is covered by a subprocess
   test blocking network/provider use. Scripted responses are labelled scripted.

Re-inject at least the repeated-lookup admission defect and verify a dispatch-
level assertion fails, then restore and rerun. Keep the old focused suites and
the complete zero-provider suite, latest Ruff, narrow Pylint and independent
read-only review. Report the baseline and final test denominators separately.

The consumed FQ01 trace is regression/development evidence only. New synthetic
controls are engineering checks, not fresh model observations or human labels.
No outcome of this offline work permits spending the old canary's unused slots.
A later live design requires its own frozen protocol and authorization.
