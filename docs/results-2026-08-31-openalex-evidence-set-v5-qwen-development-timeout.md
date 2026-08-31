# Result: Qwen evidence-set v5 development run stopped on transport timeout

Date: 2026-08-31

## Strict outcome

The authorized W01-W08 Qwen development execution is **partial / not_evaluated**.
It is not a failed relevance result and it is not evidence for or against the
evidence-set v5 semantic hypothesis. The first W01 pass completed, but the
second reversed-order pass reached the provider and then exceeded the frozen
60-second transport timeout. The runner stopped without retry or recovery.

The execution attempted two potentially billable requests, completed one
request, completed zero cases, persisted zero deterministic candidate
decisions and evaluated none of the five development gates. It made zero
OpenAlex requests, did not parse the private human labels, and remained
disconnected from production, report generation and planner triggering.

## Authorized boundary actually used

- merged revision: `d9adfa4501bb294add25302bee4b59cbd314450b`;
- frozen public W01-W08 packet containing 64 titles and abstracts;
- exact provider/model: Qwen / `qwen3.5-plus`;
- at most 16 sequential calls under a USD 0.20 soft stop;
- no redirect, retry, repair, fallback, recovery or supplementary retrieval;
  and
- production/report/planner connection: false.

Before credentials were read, the real zero-network preflight verified 8/8
cases, 64/64 candidate identities, 16/16 prompt identities, all source hashes
and all Qwen implementation hashes. The output directory was
`outputs/2026-08-31-openalex-evidence-set-v5-qwen-development`. It remains a
local ignored run artifact rather than a source-controlled fixture.

## What the two calls established

The first W01 pass returned the exact requested model and an inspectable usage
record after 41.405 seconds:

| Metric | Observed value |
|---|---:|
| Prompt tokens | 3,099 |
| Completion tokens | 1,332 |
| Total tokens | 4,431 |
| Cached prompt tokens | 0 |
| Locally reconstructed cost | USD 0.006358 |

The response passed the provider, request-identity, JSON and usage-accounting
contracts and was durably committed before the next call. Its individual
KEEP/ABSTAIN content is not a quality result: the required reversed-order pass
never completed, so no agreement or deterministic set decision exists.

The second W01 pass failed with `provider_transport / TimeoutError`. It has
`request_may_have_spent=true`, no response and no usage record. The frozen
adapter made no retry. The runner then wrote the failed call journal, final
execution and artifact index and stopped before W02.

## Why aggregate cost is uninspectable

The completed first call has an inspectable local cost estimate, but the second
request reached the transport boundary and may have been processed or billed
without returning usage. Therefore the execution correctly reports:

- `cost_state=uninspectable`;
- `cost_usd=null`; and
- no claim that total experiment cost was USD 0.006358 or zero.

The known first-call estimate is only an inspectable component, not an upper
bound or invoice total. A soft stop can prevent a later request only when all
earlier spending is inspectable; it cannot reconstruct a timed-out in-flight
request.

## Artifact audit

The artifact index listed five durable files. Their SHA-256 values were
independently recomputed after the process exited and all five matched:

| Artifact | SHA-256 |
|---|---|
| `manifest.json` | `28382e63aa7ec2aade3481a7166b175fca80178586a4f1c8fff753340fe1c09d` |
| `execution.json` | `4dac0e5f44c63dccc57392885c31f123db355d8baee1cbe45f63b16ba23fcc95` |
| `candidate-decisions.json` | `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570` |
| `judge-calls/W01-pass-1.json` | `12f0376bafe94e738d2f26fc23810a66016a14c5609b75addde197e9735db112` |
| `judge-calls/W01-pass-2.json` | `7503c451f55adb3aebb677ba19ad4ef2d283c8163cf503e00e3b1d9f74a0b4fa` |

The project models then revalidated the schema-3 manifest, both call journals
and the final execution. The validated states were `completed, failed`,
`partial`, `adapter_failed`, `uninspectable` and `not_evaluated`, with zero
case decisions and every production connection false.

## Disposition and next boundary

The implementation behaved as pre-registered. Raising the timeout, retrying
the failed pass, replaying W01, or resuming from the successful first pass
would change the frozen transport method after observing an outcome. None is
authorized by this run.

If work continues, it needs a separate pre-registered transport-only decision
that explicitly addresses the consumed first-pass response and the timeout
boundary. That decision must not relabel this run as complete, reuse X01-X08
for transport tuning, or authorize production Tool Calling. Until a later
eligible development execution completes both passes for every case and meets
all five frozen gates, evidence-set v5 remains not evaluated.
