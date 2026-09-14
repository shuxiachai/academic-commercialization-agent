# Native Qwen follow-up: transport observed, closure gate failed

Recorded: 2026-09-15 Australia/Sydney (execution 2026-09-14 14:01 UTC).
Implementation: `80fe47d844c8d125402b2886a56d07d3458183ef`.
Preregistration: `ab6ad59e56af135fedd9947313d933b4ef6b9633`,
[two-control protocol](prereg-2026-09-14-report-evidence-followup-qwen.md).
Result: **FAIL**. FQ01 failed; FQ02 was not run. No retry or second batch.

## What was implemented and checked before payment

The isolated native HTTP adapter pins `qwen3.5-plus` and the official Beijing
endpoint, accepts only the dedicated DashScope key, and does not inherit global
provider/model/base selection. It has no production route. It disables retries,
redirects and environment proxies, checks byte/output limits, and owns a bounded
asynchronous HTTP operation rather than leaving an unowned background thread.

An exclusive experiment ledger writes/fsyncs intent before every request,
retains conservative reservations for unknown usage and stops later cases on
uncertainty. It records returned-model matching separately from what was sent.
Thirteen installed transport/Pydantic/key-parser dependencies must match the
lock. The only dependency change declares already-locked httpx 0.28.1 directly;
there is no version upgrade. Phase-1 core, scoring and old experiments are unchanged.

Independent static review found and closed four issues before live execution:
JSON-escaped secret echoes, a paid repair turn after local tool argument errors,
rejection of valid native tool `index: 0` metadata, and recording installed
versions without comparing them with the lock. Final review found no remaining
actionable findings in this isolated scope. It did not claim model correctness.

- Before edits: **3317 passed / 1292 subtests**, 112.09 seconds.
- After edits: **3396 passed / 1298 subtests**, 137.53 seconds.
- New modules: **79 collected tests**; the four-module follow-up focus, including
  127 earlier tests, passed **206 tests**. These are not 206 newly added tests.
- Latest Ruff 0.16.7, narrow Pylint, offline lock check and diff check passed.
- Redirect re-injection caused one assertion failure; replacing unknown usage
  with zero caused eight. Both mutations were restored before the final checks.
- Initial focus was 205 passed / 1 failed: a test read UTF-8 pyproject text with
  Windows' default GBK. Explicit UTF-8 fixed the test, not its assertions.
  Initial Ruff also found four F401 imports; unused imports were removed and
  intentional fixture re-exports made explicit. No new skip or warning ignore.

The 30 existing source snapshots retained aggregate SHA-256
`be4d8673989d5e586103624e305460dbb47af370043e14e783c0e8b2ea654cee`.
None of their text was sent to Qwen. Live input was the synthetic fixture only.

## Observed native conversation

| Request | Model action | Local result / boundary |
|---|---|---|
| 1 | `lookup_sources` with a long multiword query | Literal phrase not present: zero hits. |
| 2 | `lookup_sources` with `synthetic sensor` | One hit, A1; both allowed tool executions now used. |
| 3 | `read_source` for A1, offset 0, length 1500 | Native request received but **not executed**: `tool_budget_exhausted`. No fourth request. |

All three HTTP replies matched the exact authorized model, had valid native
protocol shapes and complete reported usage. The actual tool results carried
their original call IDs in subsequent requests. However, no read receipt or
final answer was produced. Native tool-request transport is observed; the
read-to-cited-answer closure is **not** established. FQ02's missing-text
abstention branch remains unobserved, not passed or failed by an actual run.

## Usage and cost scope

| Fact | Observation |
|---|---:|
| Actual provider requests | 3 of at most 6 |
| Reported prompt tokens | 2498 |
| Reported completion tokens | 111 |
| Unknown-usage requests | 0 |
| Conservative known-usage estimate | USD 0.001813194 |
| Reservations retained for budget admission | USD 0.033447936 |
| Authorized total soft stop | USD 0.10 |
| Local CLI process wall time | 15.551 seconds |

The reservation total is **not money spent**. The token-derived estimate uses
the preregistered maximum-tier prices without cache discounts and is **not an
invoice**. Wall time includes local startup, identity and journal work; it is
not a per-request latency measure or SLO. No actual bill was queried.

## Root cause and limits

The scripted demonstration used a short matching literal query. Real Qwen
first requested a long phrase with no literal match, then a shorter matching
phrase. Interpreting the first request as keyword-search behavior is an
inference, not evidence of the model's internal reasoning. The two lookups
consumed the fixed two-tool allowance before the required read. The strict
budget correctly blocked further work; the tool interface and conversational
planning did not produce the required closure under that budget.

Do not relabel the failure as a pass, increase limits retrospectively, change
the fixture or spend unused authorization repeating it. A next offline design
should reserve a read/finalization opportunity and expose remaining actions,
rather than assuming a prompt alone coordinates the budget. This trace is now
development/regression evidence, not fresh independent validation.

`semantic_support=not_assessed` and `answer_verification=not_verified` remain.
No final prose existed for the FQ01 content check. This is not user utility,
source truth, supplementary retrieval v9 or production Tool Calling approval.

## Local artifact identities

Original artifacts remain unchanged in a gitignored local batch. Only this
aggregate and synthetic fixture are published; credentials and error bodies
are not artifacts.

| Artifact | SHA-256 |
|---|---|
| manifest.json | `ca6789618b865c6b7f12d4e956e6ddabb07124ada9b3ad33e6eb834ddba77cab` |
| events.jsonl | `efffa2c1d04cade2174bba20396b986d8601312ccc9ec727d13ac8916e0aab18` |
| FQ01.json | `5410240f0fca248afb5ed40071c7f5c8eb941209f0b0a1916d3fcd42bb445220` |
| summary.json | `2998940794003b8aed10b47d197ec7f6e21b80052483c30014b141b53c0e417b` |

Fixture SHA-256:
`4e026d9cf051a264b65f7b5f3e6d75cf501cc2acc2f4d5dcceb513cc37d37435`.
Implementation source hashes are in the manifest and reviewed commit. A source
hash or valid returned-model label is not independent backend-model attestation.
