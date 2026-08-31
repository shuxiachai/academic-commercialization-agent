# Result: Qwen evidence-set v5 bounded timeout amendment implementation

Date: 2026-08-31

## Outcome

The transport-only amendment is implemented and verified with zero provider
requests. New Qwen development artifacts use manifest/execution schema 4 and
persist a 120-second timeout in every request identity, the manifest and the
final execution. The default Qwen judge adapter receives the same value at the
actual transport seam.

This implementation does not authorize or execute another W01-W08 paid run. It
does not relabel the earlier schema-3 execution, which remains
`partial / not_evaluated`, and it does not connect the evidence-gap planner,
supplementary retrieval or report generation.

## Evidence used for the bound

Only one exact completed Qwen v5 request latency is available on disk:
41.404828 seconds for W01 pass 1. W01 pass 2 is right-censored by the historical
60-second timeout. A separate 306-second production workflow contains seven
provider calls plus retrieval, orchestration, validation and persistence, so it
cannot be converted into seven request latencies.

The 120-second value is therefore not a percentile, p95 or SLO. It is the
adapter's pre-existing hard maximum, frozen as a bounded development choice
before any later provider request.

## Implemented contract

- `QwenJudgeRequest.transport_timeout_seconds` is a durable, credential-free
  request field; it is deliberately excluded from the provider JSON body.
- Historical schema-3 Qwen requests continue to default to 60 seconds.
- New runner-created Qwen requests explicitly use 120 seconds and schema 4.
- The adapter rejects request/transport timeout drift before body construction
  or transport invocation.
- HTTP and transport failures retain safe monotonic elapsed time when available.
- Failed-call journals persist that elapsed time without semantic content or
  credentials.
- A potentially spending timeout without usage still makes aggregate cost
  `uninspectable` and stops the run without retry.
- DeepSeek schema 2 and historical Qwen schema 3 remain readable.
- No CLI timeout option was added; an operator cannot silently mutate the
  frozen experiment contract.

The Qwen behavior dependency is frozen at SHA-256
`1a4d20a0cfb2f39ffdb4ae4c878929b187f34e77e057ae98d4082fb6d64e67c0`.

## Seam verification

The focused adapter and runner suite passes 26/26 tests. It verifies:

1. historical 60 seconds still reaches the raw transport for schema 3;
2. amended 120 seconds reaches the raw transport for schema 4;
3. a 120-second request paired with a 60-second adapter is rejected with zero
   transport calls;
4. a simulated timeout makes one call, records 120,250 ms, performs no retry
   and leaves cost uninspectable;
5. manifest construction happens before the default paid-capable adapter;
6. all 16 manifest requests, call journals and the execution expose 120 seconds;
   and
7. historical schema-3 manifest and execution payloads validate without
   backfilling a schema-4 claim.

The required defect was re-injected by temporarily restoring the default live
adapter argument to 60 seconds while requests remained at 120. The client-seam
test failed with observed `[60.0]` versus expected `[120.0]`; after restoring
the implementation, the identical test passed.

## Zero-network protocol verification

The real W01-W08 dry-run completed with:

| Check | Result |
|---|---:|
| Frozen cases | 8/8 |
| Candidate identities | 64/64 |
| Prompt identities | 16/16 |
| Request timeout identities | 16/16 at 120 seconds |
| Schema | 4 |
| Network calls | 0 |
| Model calls | 0 |

The complete project verification then passed:

- `1787 passed, 657 subtests passed`;
- latest Ruff, all files; and
- narrow Pylint for exception ordering, unreachable code, use-before-assignment
  and undefined variables.

## Remaining boundary

A later paid execution still requires separate user authorization naming the
merged revision, exact `qwen3.5-plus` model, at most 16 sequential calls, a
soft USD stop, a fresh output directory and the prohibitions on retry, repair,
fallback, recovery and production connection. Both W01 passes must be fresh;
the earlier successful schema-3 pass is immutable history and cannot be reused.

Even a complete schema-4 run would establish only bounded transport
compatibility. The unchanged quote, two-pass agreement, set-cover and human
label gates must still pass before X01-X08 may be opened. Production Tool
Calling remains disabled.

Related records:

- `docs/prereg-2026-08-31-openalex-evidence-set-v5-qwen-timeout-amendment.md`;
- `docs/results-2026-08-31-openalex-evidence-set-v5-qwen-development-timeout.md`;
  and
- `docs/results-2026-08-31-openalex-evidence-set-v5-qwen-provider-implementation.md`.
