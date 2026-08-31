# Pre-registration amendment: evidence-set v5 Qwen transport timeout

Date: 2026-08-31

Status: frozen after the first Qwen development timeout and before any later
provider request. This amendment authorizes no paid call, does not relabel the
earlier partial execution, and does not change the evidence-set v5 semantic
method.

## Why another amendment is necessary

The first authorized Qwen development execution completed W01 pass 1 in
41.404828 seconds. The reversed pass then reached the transport boundary and
exceeded the frozen 60-second timeout. The runner stopped without retry, as
required, and the strict result remains `partial / not_evaluated`.

Only one completed per-request latency and one 60-second right-censored
observation exist on disk. The earlier production canary records 306 seconds
for an entire seven-request workflow, but that total includes retrieval,
orchestration, validation and persistence and cannot be divided into seven
provider latencies. These observations are insufficient for a percentile,
tail-latency distribution or SLO claim.

The next timeout is therefore not described as statistically calibrated. It
is a bounded development choice: 120 seconds, which was already the committed
Qwen adapter's hard maximum before this outcome. The purpose is to test whether
the exact frozen prompts can finish within that pre-existing bound, not to
claim that 120 seconds is optimal or production-ready.

## Frozen transport-only change

For a later Qwen development execution only:

1. each request has a 120-second client timeout;
2. one judge invocation still makes exactly one potentially billable HTTP
   request, with no redirect, retry, repair, fallback or recovery;
3. the exact endpoint, model, non-thinking JSON body, output-token limit,
   prompts, candidate order and semantic decision rules remain unchanged;
4. the timeout value must be part of the persisted request identity and reach
   the pre-call manifest, every call journal and the final execution artifact;
5. the adapter must reject a mismatch between the persisted timeout and the
   timeout actually supplied to the HTTP transport before making a request;
6. a failed call should retain a safe monotonic elapsed-time observation when
   available, without retaining semantic content or credentials; and
7. any potentially spending failure with missing usage keeps aggregate cost
   `uninspectable` and stops the run immediately.

Qwen uses manifest/execution schema version 4 for this amendment. Historical
DeepSeek schema 2 and Qwen schema 3 artifacts must remain valid and keep their
original 60-second behavior. The normal six-stage Qwen provider and its retry
policy are outside this experiment and are not changed.

## Treatment of the consumed W01 response

The successful W01 pass-1 response from the partial run remains an immutable
historical artifact but is excluded from every future gate calculation. A
later amended execution must use a fresh output directory and make both W01
passes under the same schema-4 transport contract. Resuming only pass 2 would
mix two post-outcome transport methods inside one agreement pair.

W01-W08 are already disclosed development evidence. Repeating them after this
transport-only amendment can at most evaluate development qualification; it
cannot convert them into unseen validation. X01-X08 remain untouched and may
be opened only if the complete amended development execution passes every
previously frozen gate.

## Frozen interpretation and stop rules

- A timeout, redirect, identity drift, malformed response, uninspectable
  spending event or other adapter failure stops the amended execution without
  retry and leaves it `partial / not_evaluated`.
- Completing fewer than 16 calls or fewer than eight two-pass cases is not a
  transport pass and does not run the five development gates.
- Completing all calls only establishes bounded transport compatibility. The
  unchanged quote, agreement, set-cover and human-label gates still decide the
  semantic development result.
- Failure of any semantic gate seals v5 on W01-W08. The timeout amendment may
  not be used to tune prompts, roles, selectors or thresholds.
- Neither transport success nor a development pass authorizes planner
  triggering, report insertion or production Tool Calling.

## Required zero-network evidence before authorization

1. schema-4 dry-run exposes 120 seconds at the top level and inside all 16
   persisted request identities;
2. the default live Qwen factory uses the same 120-second value at the actual
   HTTP transport seam;
3. a request/adapter timeout mismatch fails before the fake transport records
   a call;
4. a simulated timeout persists elapsed time, one failed journal,
   `request_may_have_spent=true`, uninspectable aggregate cost and no retry;
5. historical schema-2 and schema-3 artifacts still validate without a
   backfilled schema-4 claim;
6. the timeout passed to the fake transport is temporarily restored to 60
   while the request remains 120 and the seam test fails before restoration;
7. the complete W01-W08 dry-run verifies eight cases, 64 candidates, 16 prompt
   identities, source hashes and provider implementation hashes with zero
   sockets and zero model calls; and
8. the full zero-network suite, latest Ruff and narrow Pylint pass.

## Later paid boundary

This document and its implementation authorize zero provider requests. Any
later execution requires fresh user authorization naming the merged revision,
exact `qwen3.5-plus` model, maximum 16 sequential calls, soft USD stop, fresh
output directory and the prohibitions on retry, recovery and production
connection. A timed-out in-flight request may still cause a small soft-stop
overrun and must remain visibly uninspectable when usage is absent.

Related records:

- `docs/prereg-2026-08-31-openalex-evidence-set-v5-qwen-provider-amendment.md`;
- `docs/results-2026-08-31-openalex-evidence-set-v5-qwen-provider-implementation.md`;
  and
- `docs/results-2026-08-31-openalex-evidence-set-v5-qwen-development-timeout.md`.
