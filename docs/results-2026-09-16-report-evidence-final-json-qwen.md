# Final-only JSON canary: valid envelope, no saved-text read

Date: 2026-09-16 (Australia/Sydney). The single JQ batch failed its registered
positive-case gate. JSON formatting worked in the observed zero-hit branch;
the saved-evidence follow-up loop did not pass. Production remains disconnected.

## Identity and authority

The [protocol](prereg-2026-09-16-report-evidence-final-json-qwen.md) and fresh
JQ01/JQ02 synthetic fixture were committed first in
`20706803fdd7459ee9e9c008f178ceba467aa377`, before implementation or requests.
After offline regression and independent read-only review, the executed code
was frozen at `b35e98887eeabce224577e4a63057b91179ceff1`.

- Fixture SHA-256: `f0e8233a7b0e0d86783f069d96880ace941cd0ac16dbfa934e723d653febb5ca`.
- Configuration SHA-256: `a228c23d30df9b52a5076e28cac3168e07890b29e10e34b72dadace8948fb299`.
- Default CLI preflight verified 17 committed paths and installed dependency
  versions, before any key lookup, output creation or provider request.
- The user's standing same-scope authorization covered one new synthetic batch,
  at most six sequential exact `qwen3.5-plus` requests and USD 0.10 total soft
  stop, accepting a small in-flight excess. This did not reuse old SQ/FQ budget.

Only synthetic questions and records were in scope for the pinned official
Beijing endpoint. No customer report, retrieval request, retry, repair, fallback,
redirect, recovery or production route was used. The invocation started at
2026-09-15 14:38:03 UTC and finished at 14:38:17 UTC, exiting with code 1.
The output directory timestamp is not the actual request start time.

The parent loaded only the authorized dedicated environment-file assignment
into its invocation process; the runner itself still reads only process
`DASHSCOPE_API_KEY`. No key was printed and the environment file was not edited.
The shell's strict restoration comparison returned false. A separate synthetic
environment-variable probe reproduced absent/null becoming an empty string in
this runtime, and a fresh process inspection found no nonempty dedicated key.
This is not a claim that the strict restoration check passed. The invocation
has exited; no persistent environment or alternate credential was configured.

## What actually happened

| Case | Observed result | Interpretation |
|---|---|---|
| JQ01 | `case_gate_failed`; core state `abstained`, terminal `model_abstained` | Well-formed final JSON is not the required saved-text read and supported positive answer |
| JQ02 | Unrun | First-case failure closed the batch; no missing-text read/abstention observation was obtained |

The first response natively called `lookup_sources` with the query
`synthetic piezoelectric vibration sensor resonant frequency field deployment lifetime testing`.
The frozen tool casefolds the entire query and requires it to occur contiguously
in either the saved title or saved summary. It does not interpret the query as
an unordered list of search terms. This exact phrase occurs in neither field,
so the real local result was `total_count=0`, with an empty hit list.

The fixture nevertheless contains A9 and its 18 Hz laboratory result, explicitly
excluding field deployment and lifetime testing. The miss is therefore a query
contract mismatch, not an absent saved source, failed API, missing abstract or
provider outage. The stage policy then legitimately disabled tools after zero
hits. There was no `read_source` call, issued evidence ID or served excerpt.

The second actual HTTP request retained the paired lookup result and native
call ID. It omitted `tools`, kept `tool_choice=none`, and included
`response_format={"type":"json_object"}` before serialization and reservation.
The response was a whole JSON object, without explanatory prose or Markdown
fences. The unchanged strict parser accepted its abstention and empty evidence
list. It did not give the positive answer required by the registered case gate.

Both request bodies matched their journal hashes, both observed response-model
fields matched the authorized alias, and both requests retained complete reported
usage. This is not independent backend-model attestation. The ledger contains
two reserve/finish pairs and `batch_stopped`, no third request, no pending request
and no unknown-usage request. The persisted JQ01 and summary both say failed;
there is no JQ02 record or leftover candidate from this successful publication.

The narrow positive content control was not satisfied: no supported 18 Hz answer
was delivered. `semantic_support=not_assessed` and
`answer_verification=not_verified` remain. A syntactically valid abstention is
not a semantic-accuracy score, missing-text-case pass or successful closure.

## Usage and accounting

| Request | Input tokens | Output tokens | Total | Frozen estimate, USD |
|---|---:|---:|---:|---:|
| 1: lookup | 742 | 39 | 781 | 0.000559326 |
| 2: final-only abstention | 396 | 44 | 440 | 0.000378268 |
| Total | 1138 | 83 | 1221 | 0.000937594 |

The USD 0.022298624 reservation consumption is conservative admission accounting,
not spend. The USD 0.000937594 estimate uses frozen USD 0.573/3.44 per-million
input/output rates, not an invoice or free-credit assertion. The
[official pricing page](https://www.alibabacloud.com/help/en/model-studio/model-pricing)
was checked before dispatch; these rates cover the bounded input range
conservatively. `complete_for_reported_requests` covers these two requests only.
The remaining allowance is not authorization to retry this failed batch.

## Implementation and verification

The separate transport adds JSON Object mode only at final-only, leaving native
tool stages and the strict core untouched. The existing system/user JSON
instruction is required before reservation; tool/assistant text cannot supply
it. The [official JSON Object contract](https://help.aliyun.com/zh/model-studio/qwen-structured-output)
does not guarantee a schema. This run observed compatibility after an empty
lookup, not after a successful saved-text read.

The unchanged baseline passed **3613 tests / 1338 subtests, 117.23 seconds**.
Initial implementation regression passed 3824 / 1345, 162.96 seconds, but
independent AI review found a persistence gap: a final success-shaped file could
exist after `fsync` failed. That green run did not cover the missing seam.

Only the new runner was repaired. Case and summary candidates are written,
flushed, fsynced and closed before atomic no-clobber hard-link publication.
Dot-prefixed `.pending` files are never authoritative. A cleanup failure after
publication does not reverse the already committed result. Unsupported hard
links fail closed. Frozen ledger reserve/finish semantics stay unchanged;
directory durability after power loss and hostile concurrent writers are not
claimed.

The 230 focused controls passed after repair. Removing the final JSON wire
member produced one expected red test; reintroducing direct final-name writing
made three actual fsync seam controls fail. Restored source hashes returned all
230 controls to green in 41.02 seconds. Final pre-live regression passed
**3843 tests / 1345 subtests, 210.33 seconds**. Latest Ruff 0.16.7, narrow Pylint
and the offline lock check passed. An initial default pytest temporary-directory
permission failure was handled with a new checked workspace temporary path,
without changing ACLs, assertions, skips or warning rules. Independent static
re-review closed the P2; it did not replace execution evidence or human review.

After result documentation, the full zero-provider regression passed
**3843 tests / 1350 subtests, 214.22 seconds**. Independent read-only AI artifact
review recomputed the two-request accounting, checked actual paired history and
the absent read, and retained the failed gate. Documentation review narrowed an
English README sentence: source discovery was the observed blocker, not proof
that it is the only remaining issue. Successful-read/final-JSON compatibility
is still unobserved; no further provider call was made to fill that gap.

## Artifact integrity

Raw synthetic artifacts remain locally ignored under
`outputs/report-evidence-final-json-qwen-live-20260915T143723Z-64e689f2/`.
Only qualified aggregates and hashes are public.

| Artifact | SHA-256 |
|---|---|
| authorization.json | `8632b4e461202b8efff42e1b8209b889d3159d000254a1cd7a2f213366eba067` |
| events.jsonl | `2f9d36655f68c193beaba4571e65c86d9db8e1953009f52337953787d94f77ae` |
| identity.json | `49835e8512003a12dda478945a1e6d0286a4411099152f53fbc1de5a42a6f9b0` |
| JQ01.json | `901dd8f3ca62acab3417791630ff165186328d6a59ea6c554bb8fb15c908909d` |
| manifest.json | `97633ef8b4bceef18641967cb83833f4ba862a219cb3cd7a53eb42492fd2ee55` |
| summary.json | `d1f95810440f7c9ed6634ebaabb5cb5ef1b8b7044dd7f361569ac92185abf30a` |

The 73-file pre-change protection set remained unchanged before dispatch:
33 old source/test/protocol/configuration records, 30 local benchmark source
snapshots and ten earlier FQ/SQ artifacts. This is not a newly validated 30-run
benchmark or the differently scoped earlier protection set.

## Next gate, not another paid retry

First study the saved-source lookup interface offline: multi-concept query
composition can miss evidence that is already present, and zero hits cannot
justify a literature-absence conclusion. Compare bounded metadata discovery or
an explicitly specified query contract using fresh positive, distractor and
negative controls, while preserving read-before-cite and abstention boundaries.
Do not silently replace literal matching, reveal answer labels, increase tool
budgets or rerun JQ until it passes. Any changed method needs its own frozen
protocol and separate applicable authorization before another live batch.

The old SQ/FQ failures, sealed v8 result and production zero-call shadow policy
remain binding. Package deployment does not enable a web follow-up route.
