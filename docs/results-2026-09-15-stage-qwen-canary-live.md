# Stage-aware Qwen canary: read delivered, final envelope rejected

Date: 2026-09-15. This is a failed, production-disconnected synthetic batch,
not a successful follow-up feature or a reinterpretation of the old FQ run.

## Frozen identity and authority

The [preregistered protocol](prereg-2026-09-15-report-evidence-stage-qwen-canary.md)
was executed once at commit `99c04f20af42ae98186a793013eff06e4793ac11`.
The fixture SHA-256 was
`93d3872b7789a1ff99fbe236274a0ec7a52ce987ece9d53f63e4080fba27ffa6`;
the fixed configuration SHA-256 was
`88b4b81c67b155b3229788b87945a740e5c4af6b7b981e1be3ead096ada04b34`.
Identity checking covered 16 committed paths before execution. No frozen source,
fixture, preregistration, scoring rule or earlier result was changed for this run.

The user authorized SQ01/SQ02, exact `qwen3.5-plus`, at most six sequential
requests and a USD 0.10 total soft stop, accepting a small in-flight overshoot.
Only synthetic questions and synthetic records were sent to the official
Beijing compatible endpoint. There was no real report, external retrieval,
retry, repair, fallback, redirect, recovery or production enablement.

A preceding default identity check returned before credential lookup or network
execution, regardless of whether a key existed. A separate operator inspection
found the dedicated process credential absent. The user then authorized reading only
the project's dedicated `DASHSCOPE_API_KEY` assignment and temporarily injecting
it into the invocation's process. The operator restored the prior process value
afterwards, without printing it or editing the environment file. The runner's
process-only key lookup and no-fallback behavior remain unchanged. This is an
explicit credential-loading action, not a new automatic dotenv feature.

The single paid invocation started at 13:26:34 UTC and exited with code 1.
The reserved output directory name predates actual launch; it is not a start-time
measurement. The persisted batch is stopped, not resumable or awaiting retry.

## Observed sequence and primary result

| Case | Observed disposition | Interpretation |
|---|---|---|
| SQ01 | `policy_core_failed`, core `invalid_final_envelope` | Lookup and saved-text read executed, but the strict final contract failed |
| SQ02 | Unrun | First-case failure stopped dispatch; neither a pass nor a failed executed case |

The three received requests used these advertised tool sets:

1. `lookup_sources` and `read_source`: Qwen performed one literal lookup for the
   synthetic ceramic strain gauge, returning source A7.
2. `read_source` only, restricted to A7: Qwen natively requested the saved text.
3. Final-only: the actual HTTP body omitted `tools` and retained
   `tool_choice="none"`. It included the correctly paired tool-call result,
   all 123 code points of stored text and its issued evidence ID.

The final response requested no additional tool. It instead contained explanatory
prose followed by a Markdown-fenced JSON object. Parsing the entire content as
the required independent JSON object therefore failed. No `response_format`
was present in the frozen final request. The core accepted no final answer;
the case result's answer is null. Reaching the final transport and having a
plausible object inside the response do not satisfy the final-envelope gate.

A narrow agent-only inspection found that the raw response accurately repeated
the synthetic 32-microstrain bench result, its absence of outdoor durability
testing and the issued evidence ID. This is not an accepted answer, independent
human review, general citation entailment or a measured model success rate.
`semantic_support=not_assessed` and `answer_verification=not_verified` remain.

The ledger contains three reserve/finish pairs followed by `batch_stopped`.
There is no fourth request, no SQ02 request, no pending reservation and no unknown
usage request. Two local tool attempts executed without tool errors. The final
read result reached the actual third HTTP request, not merely a callback flag.
All three replies passed the adapter's response-model equality check; this is
not independent attestation of the provider's backend model implementation.

## Usage, not an invoice

| Request | Input tokens | Output tokens | Total tokens | Frozen estimate, USD |
|---|---:|---:|---:|---:|
| 1: lookup | 734 | 63 | 797 | 0.000637302 |
| 2: read | 817 | 96 | 913 | 0.000798381 |
| 3: final-only | 978 | 242 | 1220 | 0.001392874 |
| Total | 2529 | 401 | 2930 | 0.002828557 |

Coverage is `complete_for_reported_requests`, limited to these three recorded
requests. The USD 0.033447936 reservation consumption is conservative admission
accounting, not spend. The USD 0.002828557 known-usage estimate uses the frozen
USD 0.573/3.44 per-million input/output rates, not a provider invoice or a claim
about free credits. The [official pricing page](https://www.alibabacloud.com/help/en/model-studio/model-pricing)
was checked on the execution date; the frozen rates remained conservative for
the bounded input range. Unused budget does not authorize continuing this batch.

## Artifact integrity and verification

Raw synthetic transcripts remain in the ignored local directory
`outputs/report-evidence-stage-qwen-live-20260915T132424Z-7253fa8c/`.
The public record contains qualified aggregates and hashes, not credentials,
customer reports or raw reviewer material.

| Artifact | SHA-256 |
|---|---|
| authorization.json | `0de6e73e582a1a531bfa7e5971e4093e2292a6cf981e32f72048d294b7c62d90` |
| events.jsonl | `9f4a4732c1189ead5ca6742c914d1d84ec8fbb926c39c080203ad60dc5a78a82` |
| identity.json | `879e24f83e9469be6601ebcac55bf96b1b16fc78d51707bfe48c9fc526b68063` |
| manifest.json | `f6b6bb1bb2d3fdbf46063e31dac4115fd9dc278e8ee0fd24c4d366efbc5b5694` |
| SQ01.json | `31023ea92f8b1f94dd0fcee502348e0204a687303edf98d9eb500c0f43bbfb6b` |
| summary.json | `8233f26246c89ab89b8751130e8cf6af3ceb6194746c11c50eeadf9b1c70d4e4` |

Before this batch, the unchanged merged tree passed the full zero-provider
suite: **3613 passed / 1332 subtests, 122.03 seconds**. This result is distinct
from the earlier [runner-preparation tests and mutation](results-2026-09-15-stage-qwen-canary-preparation.md).
No new implementation or defect reinjection is claimed for this result-only
change. Independent read-only AI review inspected the persisted request bodies,
paired evidence, strict parser, stop path and token arithmetic. It did not run
the suite, read credentials or act as a human effectiveness evaluator.

The result-documentation regression completed with **3613 passed / 1338
subtests, 107.84 seconds**. Latest Ruff, narrow Pylint and the offline lock check
passed. A separate pre/post comparison found no changes in this round's 50
protected files: the 16 identity paths, 30 local benchmark source snapshots and
four original FQ artifacts. All six new SQ artifact hashes also stayed intact.
This 50-file set is not the earlier preparation's differently scoped 60-file set.
Private history comparison retained all 154 prior numbered stories unchanged.

Review caught two prose errors, which were corrected: default identity-only
mode does not inspect credentials at all, and the current guide must distinguish
the earlier absence of live evidence from this later failed live batch. These
were documentation defects, not additional model attempts or code failures.

## Next gate and unchanged limits

The stage policy prevented lookup from consuming the read opportunity in this
one observation. The remaining failure is final serialization, not evidence
delivery. The next bounded candidate is an offline final-only JSON-output
transport contract, while preserving strict whole-response parsing and current
tool/turn limits. Its provider compatibility and live closure are unestablished.
Do not strip fences, repair this response, change this frozen protocol or rerun
SQ01 until it passes. Any new live batch needs new frozen identity and a clearly
applicable bounded authorization; this batch's allowance is closed.

The old FQ failure, failed/sealed v8 evaluation, missing SQ02 observation and
production zero-call shadow policy remain unchanged. Publishing this result or
deploying its documentation exposes no follow-up route and establishes neither
user benefit nor production paid-admission readiness.
