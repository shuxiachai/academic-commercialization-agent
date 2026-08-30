# Pre-registration amendment: evidence-set v5 DeepSeek V4 provider contract

Date: 2026-08-30

Status: frozen after the first provider-identity stop and before any later
model request. This document does not reopen or reinterpret that run.

## Reason for the amendment

The original v5 protocol froze `deepseek-chat` as a non-thinking judge. The
first authorized development request stopped because the returned model
identity did not equal that legacy alias. Official provider documentation now
names `deepseek-v4-flash` and `deepseek-v4-pro`, states that V4 thinking is
enabled by default, and documents retirement of the old alias.

This amendment changes only the provider transport contract needed to preserve
the original intended non-thinking Flash judge. It does not change the
semantic prompt, candidate order, quote verifier, deterministic selector,
W01-W08 inputs, development gates, X01-X08 unseen gates or production
disconnection.

## Frozen amended request contract

Every later v5 judge request must:

1. use `POST https://api.deepseek.com/chat/completions`;
2. request exactly `deepseek-v4-flash`;
3. include `thinking={"type":"disabled"}`;
4. retain JSON Object mode, temperature 0, non-streaming behavior and the
   existing per-pass token limit;
5. accept only the exact returned model identity `deepseek-v4-flash`;
6. make one HTTP request with no redirect, retry, repair, fallback or model
   substitution; and
7. keep credentials outside every request identity and persisted artifact.

An alias, dated suffix, provider fallback or prefix match is a terminal
identity failure. Exactness is intentional: billing compatibility is not
semantic-method compatibility.

## Accounting amendment

The local table uses DeepSeek's published **peak** V4 Flash rates as the
conservative fixed-budget basis:

- cache-miss input: USD 0.44 per million tokens;
- cache-hit input: USD 0.014 per million tokens; and
- output: USD 1.32 per million tokens.

The basis is dated 2026-08-30 independently of the older shared price census.
An environment override remains possible for normal application accounting,
but the frozen v5 adapter deliberately ignores it. This prevents an unrecorded
deployment variable from changing the pre-registered experiment budget.

After a parseable provider envelope, safe model and usage metadata must be
validated before semantic output is admitted. If identity then fails, the call
journal may retain only the returned model identity and validated token/cost
observation. It must not retain response content. Aggregate execution totals
must include that safe failed-call usage. If any potentially spending call has
no inspectable cost, the whole execution cost remains `uninspectable`, never
zero or a partial total.

## Historical and future-run boundaries

- The 2026-08-30 legacy-alias run remains `partial / not_evaluated`.
- Its unpersisted provider content and usage cannot be reconstructed.
- W01-W08 remain consumed development cases; this transport correction does
  not permit prompt or decision-rule tuning on them.
- No paid request is authorized by this amendment or by its implementation.
- A future run requires fresh authorization naming the merged Git revision,
  call ceiling, soft stop and credential/provider boundary.
- No automatic retry of the historical run is permitted.

## Required zero-network evidence before another authorization

1. outbound-body test proves the exact V4 model and disabled-thinking field;
2. exact identity mismatch remains terminal after one transport call;
3. a mismatch journal preserves safe usage through `execution.json` but no
   semantic response content;
4. missing usage or price stays visibly uninspectable;
5. the provider rates, date and OpenAI-shaped cache arithmetic are tested;
6. the disabled-thinking defect is temporarily re-injected and makes the
   outbound seam test fail;
7. the frozen source and implementation hashes pass the real dry-run; and
8. full zero-network tests, latest Ruff and narrow Pylint are green.

## Sources

- DeepSeek, [Change Log](https://api-docs.deepseek.com/updates/)
- DeepSeek, [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)
- DeepSeek, [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)
- DeepSeek, [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)
