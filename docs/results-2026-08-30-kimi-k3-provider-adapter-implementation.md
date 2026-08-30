# Kimi K3 provider adapter implementation result

**Date:** 2026-08-30
**Status:** implementation complete; zero-network verification complete; live
provider compatibility not evaluated

## Question

Can Kimi K3 be added as a first-class logical provider without weakening the
existing provider, BYOK, cost-accounting, or zero-network test boundaries?

This change answers only the implementation question. It does not claim that a
real Kimi request has completed, that report quality improved, or that Kimi
should replace the frozen DeepSeek contract used by the evidence-set v5 study.

## Frozen provider contract

| Concern | Implemented contract |
|---|---|
| Logical provider | `kimi` |
| CrewAI transport | pinned OpenAI-compatible transport in CrewAI 1.14.7 |
| Operator key | `MOONSHOT_API_KEY` |
| Model | `kimi-k3` by default |
| Base URL | `https://api.moonshot.ai/v1` by default |
| Reasoning | `low`, `high`, or `max`; project default `low` |
| Structured output | `response_format={"type": "json_object"}` |
| Temperature | omitted because the K3 chat contract does not expose it |
| Cached usage | top-level Kimi `usage.cached_tokens` is translated into CrewAI's shared cached-prompt field |
| BYOK override surface | visitor supplies only provider and key; endpoint, model, and reasoning remain code-owned |

Kimi K3 always reasons. The project deliberately chooses `low` rather than
the provider's `max` default to make the operator's cost and latency choice
explicit; `KIMI_REASONING_EFFORT` can opt into `high` or `max`. An invalid
value fails before client construction.

The implementation follows the official Kimi API overview, K3 model contract,
and pricing pages:

- <https://platform.kimi.ai/docs/api/overview>
- <https://platform.kimi.ai/docs/models>
- <https://platform.kimi.ai/docs/pricing/chat-k3>

## Credential boundary

Kimi is available through both operator-funded runs and the existing browser /
API BYOK route. The guest key maps to `MOONSHOT_API_KEY`; no key is written to
run artifacts, checkpoint identity, logs, or the immutable run specification.

The work also found an adjacent isolation defect. The child process previously
deleted operator-paid variables before adding guest values, but CrewAI's
import-time dotenv loading could repopulate a deleted name from the deployment's
real `.env`. The child now writes an explicit empty sentinel for every
operator-paid variable first and then injects only the selected guest values.
That distinction is required: a missing variable can be reloaded, while an
explicit empty value blocks dotenv replacement.

## Cost ledger

The built-in Kimi K3 table is dated 2026-08-30 and records USD per million
tokens:

| Input | Cache hit | Output |
|---:|---:|---:|
| 3.00 | 0.30 | 15.00 |

These rates produce an estimate, not a billing receipt. A live provider response
has not yet been observed, so realised Kimi token accounting and cost remain
unverified. As with every provider, an operator can override the built-in table
through the existing price configuration when the public price changes.

## Verification evidence

The starting point passed **1,751 tests plus 639 subtests** with Kimi variables
temporarily removed so the baseline represented the merged revision rather than
the new host configuration.

After implementation:

- the focused provider, BYOK, readiness, and cost suite passed **112 tests plus
  31 subtests**;
- the complete zero-network suite passed **1,771 tests plus 658 subtests** in
  26.37 seconds on the local Windows environment;
- latest Ruff reported no findings;
- the narrow Pylint `E0701` check scored 10.00/10;
- the opt-in Chromium seam passed with zero external requests, zero mutation
  attempts, zero paid-provider requests, and no console or page errors.

Two defects were re-injected rather than inferred:

1. restoring the faulty empty-string reasoning parser made the exact Kimi BYOK
   contract test fail;
2. restoring deletion instead of empty child-process sentinels made the dotenv
   isolation seam fail by reloading an operator search key.

Both failures disappeared only after the intended implementation was restored.

## Configuration

A minimal operator configuration is:

```dotenv
LLM_PROVIDER=kimi
MOONSHOT_API_KEY=
KIMI_MODEL=kimi-k3
KIMI_API_BASE=https://api.moonshot.ai/v1
KIMI_REASONING_EFFORT=low
```

The key value remains local or in the deployment secret store. Legacy
`OPENAI_API_KEY`, `OPENAI_API_BASE`, and `OPENAI_MODEL_NAME` values are
recognised for migration only; the explicit Kimi names are the documented
contract.

## Limits and next evidence

No paid Kimi request was authorized or executed during this implementation.
Therefore the following remain **not evaluated**:

- live authentication and returned-model identity;
- JSON-mode compatibility through the real CrewAI request path;
- report completion and guardrail behaviour;
- token-usage field shape, realised cost, and latency;
- report quality relative to DeepSeek.

A separately authorized one-run canary is the next honest compatibility check.
It should use a fixed public topic, one complete run, no retry or recovery, no
Planner or supplemental paid search, a small soft budget, and exact model /
usage / artifact inspection. Until that succeeds, documentation must say
"Kimi K3 implemented" rather than "Kimi K3 validated in production."

The evidence-gap Tool Calling candidates and evidence-set v5 runners remain
production-disconnected. This provider adapter does not authorize connecting
them, and it does not rewrite their frozen DeepSeek experimental contract.
