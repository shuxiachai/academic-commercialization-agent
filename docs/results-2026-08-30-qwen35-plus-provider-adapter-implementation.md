# Qwen3.5 Plus provider adapter — implementation result

Date: 2026-08-30
Status: `implementation_only / live_not_evaluated`

## Decision

The project now treats Alibaba Qwen3.5 Plus as a first-class logical provider
without changing CrewAI 1.14.7 or the six-stage workflow. The adapter is built
over CrewAI's native OpenAI-compatible transport because Model Studio exposes
the Chat Completions contract that the existing synchronous pipeline needs.

This branch starts from public `main`. It does not carry the earlier, unmerged
Kimi candidate. Replacing that candidate rather than stacking two new providers
keeps the production-facing choice intentional and the review diff auditable.

## Frozen implementation contract

- Logical provider name: `qwen`.
- Official credential name: `DASHSCOPE_API_KEY`.
- Default model: `qwen3.5-plus`.
- Default BYOK endpoint:
  `https://dashscope.aliyuncs.com/compatible-mode/v1`.
- Operator overrides: `QWEN_MODEL` and `QWEN_API_BASE`.
- Legacy OpenAI-compatible detection remains available when
  `OPENAI_API_BASE` identifies DashScope or a `.maas.aliyuncs.com` workspace,
  or when `OPENAI_MODEL_NAME` identifies Qwen.
- JSON nodes send `response_format={"type":"json_object"}` and always place
  `enable_thinking=false` inside OpenAI SDK `extra_body`.
- The caller's requested temperature is retained; Qwen accepts `0 <= x < 2`,
  so the pipeline's existing deterministic `0.0` remains valid.

The non-thinking choice is deliberate. Qwen3.5 Plus enables hybrid thinking by
default, while the project's synchronous report stages require JSON Object
responses and CrewAI's pinned path uses Chat Completions. Exposing a global
thinking toggle would allow configuration to invalidate five structured-output
nodes before a guardrail could inspect their content.

CrewAI 1.14.7 expands `additional_params` into keyword arguments passed to
`OpenAI.chat.completions.create`. Alibaba's `enable_thinking` is not an OpenAI
SDK keyword, so this would be wrong:

```python
additional_params={"enable_thinking": False}
```

The implemented boundary is:

```python
additional_params={"extra_body": {"enable_thinking": False}}
```

An offline test instantiates the real CrewAI `OpenAICompletion`, asks it to
prepare the final Chat Completions request, and asserts on that final body.

## BYOK and accounting boundaries

The API accepts `qwen` wherever an LLM BYOK provider is accepted, including
full runs, resume credentials and inline PDF extraction. A Qwen BYOK request
is fixed to the official model and endpoint; operator model/base overrides are
not allowed to redirect the visitor's key or alter what the visitor pays for.

The child-process scrub now leaves explicit empty values for every operator
paid credential before adding the visitor's values. This is stronger than
deleting names: CrewAI imports dotenv in the child, and a deleted variable
could otherwise be restored from the operator's local `.env` after the API
boundary had reported it removed. Qwen uses an explicit provider-to-key map so
the child receives `DASHSCOPE_API_KEY`, never an invented `QWEN_API_KEY`.

DashScope reports cache reads in the OpenAI-compatible nested
`prompt_tokens_details.cached_tokens` shape. No provider-specific monkey patch
is needed; the existing ledger already treats cached tokens as a subset of
prompt input. The built-in Qwen estimate uses USD 0.573 input, USD 0.115 cached
input, and USD 3.44 output per million tokens: the highest published
China/global standard context tier as of 2026-08-30. This intentionally
overestimates shorter-context runs. `LLM_PRICE_PER_MTOK` remains the operator
override for a different region, contract or later price.

## Verification

All verification was zero-network and used a fake Qwen key.

- Provider/BYOK/readiness/accounting focus: **109 tests plus 30 subtests**.
- Complete repository: **1,768 tests plus 657 subtests** in 23.45 seconds.
- Latest Ruff: passed.
- CI's narrow Pylint gate: passed.
- Chromium browser smoke: passed with zero external requests, zero mutation
  attempts, zero provider requests, zero console errors and zero page errors.
- `git diff --check`: passed.

The request-body defect was re-injected by moving `enable_thinking` out of
`extra_body`. The new CrewAI seam test failed with a missing `extra_body`, then
passed again after the correct implementation was restored. This demonstrates
that the test guards the SDK boundary rather than merely restating the adapter
configuration.

## What this does not prove

No paid Qwen request was authorized or made. This work therefore does not
establish:

- live endpoint or returned-model compatibility;
- report quality or guardrail pass rate under Qwen;
- latency, retry behaviour, actual token usage or realised cost;
- equivalence to the frozen DeepSeek benchmark or evidence-set v5 contract.

A live Qwen canary, if wanted, needs a separately authorized merged revision,
a frozen topic and success criteria, a strict request limit, and a cost stop.
Until then the accurate claim is “Qwen3.5 Plus adapter implemented and verified
offline,” not “Qwen validated in production.”

## Official contract references

- [Qwen3.5 Plus model documentation](https://www.alibabacloud.com/help/en/model-studio/qwen3-5-plus)
- [OpenAI-compatible Chat Completions](https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-chat-completions)
- [Thinking-mode controls](https://www.alibabacloud.com/help/en/model-studio/deep-thinking)
- [Structured output](https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output)
- [Context cache and cached-token usage](https://www.alibabacloud.com/help/en/model-studio/context-cache)
