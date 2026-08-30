# Result: evidence-set v5 development run stopped on provider model drift

Date: 2026-08-30

## Strict outcome

The first authorized W01-W08 development execution is **partial / not_evaluated**.
It is not a failed relevance result and it is not evidence for or against the
v5 semantic hypothesis. The first and only potentially billable request was
rejected by the adapter because the provider-returned model identity did not
exactly equal the frozen requested identity, `deepseek-chat`.

The process then stopped without retrying. It made zero OpenAlex requests,
completed zero model calls, completed zero cases, persisted zero candidate
decisions, did not parse the private human labels, and remained disconnected
from production, the report workflow and the planner trigger.

## Authorized boundary actually used

- merged revision: `5f6526b40731a005c5c0c397c8813264c0a9c908`;
- frozen public W01-W08 packet and existing private-artifact hashes;
- DeepSeek only, at most 16 sequential calls;
- local soft stop: USD 0.10;
- no retry, recovery, OpenAlex request or supplementary retrieval; and
- production/report/planner connection: false.

The output directory was
`outputs/openalex-evidence-set-v5-development-5f6526b-20260830`. It remains a
local ignored run artifact rather than a source-controlled fixture. The four
indexed artifact hashes were independently recomputed after the stop:

| Artifact | SHA-256 |
|---|---|
| `manifest.json` | `5ba62876abf90049fdc4638290e77723868b4c09be775cd37d09d8fca25799aa` |
| `execution.json` | `99917697e021e453724389411a18673057aa3818b5a6ff8281f7b07f9b946214` |
| `candidate-decisions.json` | `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570` |
| `judge-calls/W01-pass-1.json` | `65d3e252d73a4ccf9f937c3c4e307ad6a408c3e6258d13b21d6a46d840b94e76` |

## Why the cost is not zero

The request reached the provider and may have spent money. The historical
adapter checked model identity before converting the returned usage counters
to the durable journal. It also lacked a price row for the returned V4 family.
Consequently the artifact correctly reports `cost_state=uninspectable` and
`cost_usd=null`; zero would be an unsupported claim.

No raw semantic response was persisted or inspected after the identity
failure. This matters because a partial output from a consumed development
case must not become an informal tuning signal.

## Root cause and disposition

The frozen protocol named a legacy provider alias. DeepSeek's official V4
change log announced that `deepseek-chat` would be discontinued after
2026-07-24 and that callers should explicitly request `deepseek-v4-flash` or
`deepseek-v4-pro`. Current Chat Completions documentation also defaults V4 to
thinking mode unless the request explicitly disables it.

The strict identity check therefore did its job: it prevented a provider-side
model change from silently altering a pre-registered judge. Loosening the
check, accepting a prefix, or immediately retrying would have changed the
method after seeing an outcome. The original run remains sealed as
`not_evaluated`.

Any future request requires the separate provider-contract amendment, a merged
implementation revision, and fresh explicit paid-run authorization.

## Sources

- DeepSeek, [Change Log](https://api-docs.deepseek.com/updates/)
- DeepSeek, [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)
- DeepSeek, [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)
- DeepSeek, [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)
