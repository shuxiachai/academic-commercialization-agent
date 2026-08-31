# Pre-registration amendment: evidence-set v5 Qwen provider contract

Date: 2026-08-31

Status: frozen before implementation and before any Qwen request for the v5
study. This amendment authorizes no paid call and does not reinterpret the
earlier DeepSeek provider-identity stop.

## Why this amendment exists

The production six-stage workflow now has a first-class Qwen3.5 Plus adapter
and one completed live canary, while the disconnected evidence-set v5 runner
still imports a provider-specific `deepseek-v4-flash` judge. Reusing the normal
CrewAI adapter would be the wrong boundary: production retries selected
transport failures, whereas one v5 judge invocation must equal exactly one
potentially billable request with no hidden repair or fallback.

This amendment adds a separate strict Qwen judge profile. It does not replace
or edit the historical DeepSeek contract. It changes only provider transport,
identity and accounting. The semantic prompt, two reversed-order passes,
quote verifier, deterministic set-cover selector, W01-W08 development inputs,
five development gates, X01-X08 unseen gates and production disconnection stay
unchanged.

## Frozen Qwen request contract

Every v5 Qwen judge request must:

1. use `POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`;
2. authenticate only with `DASHSCOPE_API_KEY` in the outbound bearer header;
3. request exactly `qwen3.5-plus` and accept only that exact returned model;
4. place `enable_thinking=false` at the top level of the raw HTTP body;
5. retain JSON Object mode, temperature 0, non-streaming behavior and the
   existing per-pass output-token limit;
6. contain the word `JSON` in the prompt, as already required by the frozen v5
   system and user instructions;
7. make exactly one HTTP request with no redirect, retry, repair, fallback,
   model substitution or second formatting call; and
8. keep credentials outside prompts, identities, errors and persisted
   artifacts.

The top-level thinking field is deliberate. Alibaba documents `extra_body` as
an OpenAI SDK mechanism and explicitly says direct HTTP callers must send the
provider field directly. Copying the production CrewAI configuration into a
raw JSON body would therefore serialize the wrong contract.

An alias, dated suffix, alternate region, operator endpoint override or prefix
match is terminal. Exact identity is needed because a transport-compatible
model is not automatically the frozen semantic judge.

## Frozen response and accounting contract

The adapter may admit semantic output only after it validates:

- one response choice with non-empty content and a finish reason;
- exact returned-model identity;
- non-negative `prompt_tokens`, `completion_tokens` and `total_tokens` with
  `total_tokens = prompt_tokens + completion_tokens`;
- optional cached input only from
  `usage.prompt_tokens_details.cached_tokens`, bounded by prompt input; and
- a locally reproducible cost using the repository's dated, conservative
  Qwen3.5 Plus peak-tier row with environment price overrides disabled.

The built-in row intentionally remains conservative for this fixed soft-stop
study. Changing a deployment's `LLM_PRICE_PER_MTOK` must not move an
experiment gate without changing committed bytes.

After a parseable provider envelope, a terminal identity failure may preserve
only safe returned-model and usage observations. Semantic content must not be
persisted. Any potentially spending call with missing or invalid usage makes
the aggregate cost `uninspectable`, never zero or a partial known total.

## Runner and artifact compatibility

- The existing DeepSeek profile remains the default for historical dry-run
  compatibility and retains manifest schema version 2.
- Qwen uses an explicit provider selection and manifest schema version 3.
- A live CLI execution must name its provider; provider auto-detection is not
  allowed at an experimental paid boundary.
- Provider, model, endpoint, request schema and the selected adapter hash must
  reach the pre-call manifest and every call journal.
- The complete manifest is written before credential resolution or adapter
  construction, and each response/usage journal is durable before a later
  call.
- `pipeline_worker.py` must import neither provider judge nor the v5 runner.

## Required zero-network evidence

Before a paid Qwen development authorization:

1. the exact raw body contains top-level `enable_thinking=false`, JSON Object
   mode and `qwen3.5-plus`, with no `extra_body` wrapper;
2. exact model drift is terminal after one request and preserves safe usage
   without semantic content;
3. redirect, missing usage, inconsistent totals and uninspectable cost remain
   terminal and never trigger a retry;
4. nested cached-token accounting and the frozen price basis are tested while
   an environment price override is present;
5. the Qwen provider/model/endpoint and every request identity reach the
   manifest and journal boundary;
6. the historical DeepSeek dry-run and its schema-2 manifest remain valid;
7. the top-level thinking field is temporarily removed and the outbound seam
   test fails before restoration;
8. the complete W01-W08 Qwen dry-run verifies 8 cases, 64 candidates, 16 prompt
   identities, all source hashes and all provider-specific implementation
   hashes with zero sockets and zero model calls; and
9. the full zero-network suite, latest Ruff and narrow Pylint pass.

## Later paid boundary

This amendment and its implementation authorize no provider request. A later
W01-W08 development execution requires fresh authorization naming the merged
Git revision, provider, exact model, maximum 16 sequential calls and a soft USD
stop. W01-W08 remain consumed development evidence and can never be described
as v5 validation. Failure of any frozen development gate seals v5; it cannot be
tuned and replayed into a pass.

Even a development pass would authorize only the separately frozen X01-X08
unseen study. It would not authorize planner triggering, report insertion or
production Tool Calling.

## Official contract references

- <https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-chat-completions>
- <https://docs.modelstudio.console.alibabacloud.com/en/model-studio/qwen-structured-output>
- <https://www.alibabacloud.com/help/en/model-studio/qwen3-5-plus>
- <https://www.alibabacloud.com/help/en/model-studio/model-pricing>
