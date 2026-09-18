# PCQ native canary: semantic insufficiency failure

Date: 2026-09-17. One closed synthetic development batch, not a production
release or a general accuracy estimate.

## Identity and admission

The [native protocol](prereg-2026-09-17-claim-proposition-contrast-qwen-canary.md)
was committed before implementation. Execution used
`996f0e284fdc2a776e2d4dfc1bdf2d610fe9d049` and the original PCQ fixture
`bfc9347b28a7d284b8d959c93a038a14f1c15c9adb0d3394c9c6463012141c78`.
Independent implementation review and all eight exact-SHA
[CI jobs](https://github.com/shuxiachai/academic-commercialization-agent/actions/runs/35171746647)
passed before dispatch. A fresh local full suite also passed:
5,139 tests / 1,434 subtests in 276.77 seconds; latest Ruff and narrow Pylint
passed. Those are engineering checks, not judgments of model answers.

The default identity-only invocation succeeded without creating the fixed
output. Under the standing equivalent synthetic-only low-cost authorization,
the parent executed the new batch once, from 02:56:45.589 to 02:56:59.976 UTC.
The ceiling was six sequential exact `qwen3.5-plus` requests and USD 0.10 soft
stop; this was not reuse of CLQ's allowance. Only the dedicated credential
entered the invocation process; it was restored afterward, never printed or
persisted. There was no private RS input, retry, redirect, repair, search,
fallback, recovery, extra project-provider judging call or production change.

## Observed failure and denominator

| Case | Native observation | Mechanical check | Frozen-label check |
|---|---|---|---|
| PCQ01 | Complete nonempty read, then declared refuted and cited its real receipt | Passed | Failed: reference is insufficient |
| PCQ02 | Unrun after first failure | Not assessed | Not assessed |
| PCQ03 | Unrun after first failure | Not assessed | Not assessed |

The actual read delivered all 228 codepoints of the saved synthetic text, with
one paired local tool result and the same evidence ID in the strict final JSON.
The original claim states a physical resistance value. The source says no
resistance measurement or result exists. The candidate correctly acknowledges
that the record cannot substantiate the value, but calls the physical-value
claim refuted. A readable source and a valid citation do not make that inference
correct.

There is **one per-case mechanical pass, zero of one checked label matches**,
not zero-of-three semantic accuracy or three attempted cases. Whole-batch
`mechanical_passed=False` reflects incomplete case coverage; it does not erase
PCQ01's mechanical pass. `batch_passed=False`,
`stop_reason=expected_relation_mismatch`; case and summary publication
succeeded, no request remained pending. The remaining four possible requests
were not made and are not a reusable allowance. The occupied output is closed.

Runtime flags remain `semantic_support=not_assessed`,
`answer_verification=not_verified` and
`assessment_origin=injected_transport_unverified`. Immutable native artifacts
still mark later review pending; the separate assessment below does not mutate
them into a runtime semantic pass.

## Usage, not invoice

| Request | Input tokens | Output tokens | Total tokens | Frozen estimated USD |
|---|---:|---:|---:|---:|
| 1 | 910 | 53 | 963 | 0.000703750 |
| 2 | 1,055 | 214 | 1,269 | 0.001340675 |
| Total | 1,965 | 267 | 2,232 | 0.002044425 |

Both reported usages were complete; unknown usage count is zero. Both responses
reported the authorized model identity, which is not backend attestation.
Reserved budget consumption was USD 0.022298624; reservation is not an
additional charge. The protocol's frozen conservative rates, rather than a
new current-price assertion, produce the estimate. No invoice was inspected.

## Separate label-blinded LLM assessment and context limitation

A separate `route_reviewer` context, requested as `gpt-6-astra/high`, received
the original claim, the receipt/text actually delivered in the second HTTP
request, the candidate output and the preregistered neutral rubric as task data.
No PCQ reference labels, test outcomes or fixture were supplied in that message,
and full parent conversation history was not forked. The reviewer made no file
reads, tests, external-source checks or project Qwen calls during its first pass.

However, the reviewer later confirmed that inherited project instructions
already contained the CLQ outcome and the older recording-versus-physical-value
diagnosis. No explicit history fork is not complete context isolation.
The preregistered fully blind ideal was therefore not fully achieved. Treat
this as context-limited diagnostic LLM review, not an independent blind accuracy
measurement. Retain the original judgment and provenance plus a separate
amendment; do not rerun or relabel the native batch to remove this limitation.

The reviewer inferred **insufficient** and judged the candidate **mixed**:
the narrower statement that the record does not substantiate a value is
supported, but the assertion that the physical-value claim is refuted overstates
what an unmeasured record can establish. Four exact quotations were located:
one from the claim, one from the source and two from the candidate. Literal
matching checks transcription, not entailment.

This is an AI-generated, fallible assessment, not human expert gold. Effective
backend metadata is unavailable; requested role/model settings and successful
inference do not attest the backend. Separate reviewer inference uses resources
outside the two-request project-provider ledger; it is not zero LLM resource.
The native batch already failed its frozen rule independently of this review.

Exact submitted prompt SHA-256:
`81b7586bfde8464e347d348b4de4e8932196d3d71a2208c3f5dfdcb9fd4a047f`.
Exact returned review text SHA-256:
`91879c7ac4fa8cae63a070205fa67902347c75d27a1031c3980cb9412f049445`.
Local file hashes differ because serialization adds a trailing newline; these
hashes identify the message text, not all inherited instructions or context.
Raw review text, original provenance and the amendment stay ignored locally,
not in the public repository.

## Immutable artifacts and interpretation

| Local synthetic artifact | SHA-256 |
|---|---|
| identity.json | 18070a8c385d01478f1510a51b724c8d2545d664e32d2b152c9a119dd3fc9f3c |
| events.jsonl | 82fc3a597619b6faa08e69fdb29aba07392df21a169677cda9d1e25ebc851d25 |
| PCQ01.json | 2454aca31a6ea2322ac25d0a17e405e2169da9749b290267172139d58321f241 |
| summary.json | f35a0a7094163a6c9f584f31c36c9947fc58a3eb97aa162c3345686fe7212d1e |

Full local records remain under the exclusive protocol output; public changes
contain only synthetic aggregates and method limits. CLQ and all earlier
consumed cohorts remain untouched. The PCQ pair shares a source and PCQ03 is a
positive control; even a complete batch would not be three independent samples.

The intended native nonempty-but-insufficient abstention lane is still
unproven. Engineering guardrails successfully stopped further expenditure; they
did not validate semantic correctness. This observation motivates a separately
preregistered contract that distinguishes evidence absence from contradiction
and preserves the exact proposition being judged. It does not identify a
uniquely proven prompt or model root cause.

Next work should start offline with new controls and an explicit three-way
decision rubric, before considering a new bounded native experiment. Do not
retune/relabel/rerun this batch or silently patch its frozen prompt. Do not infer
permission for real-report disclosure, another paid allowance, general claim
blocking, scoring changes, automatic merge/deployment or production admission.
