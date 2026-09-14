# Saved-evidence follow-up: bounded Qwen compatibility canary

Registered: 2026-09-14, before any request in this protocol.
Baseline: `f98f80a9041e5dde50b2595d0979ee5efd8f8a3a` (phase-1 PR #143).

## Question and authorization

Does the isolated loop accept native Qwen tool requests, return the matching
local result, and produce an evidence-linked answer or explicit abstention?
Scripted phase-1 success cannot answer this.

The user authorized **USD 0.10 total soft stop, at most six sequential requests**,
exact `qwen3.5-plus`, synthetic questions/evidence only. One in-flight request
may exceed the soft stop slightly. No real reports, benchmark source text,
retry, repair, fallback, retrieval, recovery or production enablement. Unused
allowance does not authorize extra cases or repeats. This is not supplementary
retrieval v9; sealed v8 and all consumed/reserved cohorts remain unchanged.

## Frozen cases

Exactly these cases, in order, with separate immutable snapshots; at most
three model turns and two local tool attempts per case. Tool choice is `auto`.

| ID | Synthetic saved material | Question | Required outcome |
|---|---|---|---|
| FQ01 | A1; title `Synthetic sensor laboratory record`; origin `abstract`; summary `The synthetic sensor was tested only in a laboratory fixture at 25 degrees Celsius. No field deployment was evaluated.` | `What temperature was used to test the synthetic sensor, and was field deployment evaluated? Read the saved evidence before answering and cite its evidence ID.` | `answered_with_evidence`; native `read_source`, exact frozen A1 excerpt and matching evidence ID delivered in a subsequent provider request and used in the final answer. |
| FQ02 | M1; title `Synthetic market record`; origin `unknown`; summary absent | `Does the saved synthetic market record establish annual revenue? Inspect the saved record; if its text is unavailable, explicitly abstain rather than invent a revenue figure.` | `abstained`; observed native `read_source` result `missing_text`, no final evidence IDs or successful read receipts. |

Both snapshots: publisher `Synthetic example`, accessed date `2026-09-14`, no
URL/DOI, case ID as report reference. These are invented controls, not literature
or human labels. Inspecting FQ01 for 25 degrees and no field evaluation is a
narrow control check, not general semantic-support validation.

## Transport and accounting gate

- Read only `DASHSCOPE_API_KEY`; explicitly pin the official Beijing compatible
  endpoint and exact model, ignoring global model/base selection and legacy keys.
- Non-streaming, non-thinking native tools, one tool per turn; no forced tool,
  JSON repair, retries, redirects or environment proxies. Bound request/response
  bytes, output tokens and request waiting; socket timeout is not hard process
  preemption.
- Reserve each request in a durable event ledger **before dispatch**. Uncertain
  dispatch, absent/malformed usage, unexpected returned model, persistence or
  protocol failure stops all remaining cases. Interrupted requests are not free.
- Freeze a conservative USD estimate of **0.573 input / 3.44 output per million
  tokens**, without cache discounts: official China maximum-context rates checked
  on 2026-09-14, not the actual invoice or this short prompt's tariff. Record
  reported tokens separately. Check a conservative next-request reservation
  against remaining allowance before dispatch; share the six-call ceiling.

Official [pricing](https://www.alibabacloud.com/help/en/model-studio/qwen3-5-plus)
lists lower short-input prices. Official [Function Calling](https://help.aliyun.com/en/model-studio/qwen-function-calling)
documents native `tool_calls`, matching `tool_call_id` and subsequent requests.
Documentation does not establish observed provider behavior.

## Identity, artifacts and decision

Commit implementation and fixture before the first request. Verify expected
exact commit, clean relevant files, fixture hash, source/dependency identities,
model, endpoint and limits. Create an exclusive new output directory and manifest
before network. Preserve per-request append-only events, safe usage metadata,
synthetic transcripts, case results and a batch summary. Do not log keys,
authorization headers or exception bodies. Never overwrite or resume an occupied
batch; a crash remains unresolved. No real user source content may be loaded.

Pass only if **both outcomes** are observed, every dispatch has accounted usage,
returned model matches, and identity/count/budget restrictions hold. Unrun cases
do not pass. Preserve failures; do not tune or repeat within the allowance.

Before live execution: complete zero-provider regression, latest Ruff, narrow
Pylint, independent review, mock HTTP round trips and defect reinjection. Assert
native ID pairing, redirects, timeouts, absent usage, wrong model, exhausted budget,
occupied output and durable pre-dispatch refusal at the actual seams.

Even a pass is only a tiny synthetic compatibility observation.
`semantic_support=not_assessed` and `answer_verification=not_verified` stay.
Web routes, payer authorization, admission, receipts, cancellation, customer-data
consent, useful answers and production rollout remain separate work.
