# Stage-aware saved-evidence Qwen canary

Registered: 2026-09-15, before runner implementation or any new provider call.
Baseline: `0b62b1dca44f6324f84e4bbf15c86bd3c67513dd` (PR #146).
Protocol identity: `report_evidence_stage_qwen_canary_v1`.

## Question and permission

Can the stage policy and separate HTTP adapter complete a native saved-text
read followed by citation, or an observed missing-text read followed by abstention?
Prior FQ01 stays failed, FQ02 unrun; neither is repeated. This tiny synthetic
control is not unseen retrieval evaluation, semantic accuracy or reader utility.

This change authorizes **offline preparation only**. The proposed future ceiling
is six sequential `qwen3.5-plus` requests and USD 0.10 total soft stop, at most two
local tool attempts and three model turns per case. Fresh user authorization
must bind the final commit and fixture hash before execution, accepting possible
small in-flight overshoot. Prior budget, unused calls, a CLI acknowledgement and
this protocol do not provide it. No real reports, benchmark snippets, external
retrieval, reserved cohorts, retry, repair, fallback, redirects, recovery or
production enablement. v8 and earlier evaluation decisions remain sealed.

## Fixed synthetic cases

The flat-list fixture `tests/fixtures/report_evidence_stage_qwen_canary.json`
has SHA-256 `93d3872b7789a1ff99fbe236274a0ec7a52ce987ece9d53f63e4080fba27ffa6`.
Order is SQ01 then SQ02, each with publisher `Synthetic example`, date
`2026-09-15`, no URL/DOI and its case ID as report reference. Exact questions and
text are in those frozen bytes. No expected-answer label is sent to the model.

| Case | Saved material | Required observation |
|---|---|---|
| SQ01 | A7, academic abstract, `Synthetic ceramic strain gauge record`; 32 microstrain in a bench fixture, no outdoor durability testing | Native A7 read, complete frozen text and issued evidence ID delivered to a subsequent accepted request; final `answered_with_evidence` using that ID. |
| SQ02 | M4, market, `Synthetic coastal filter business record`; absent text, unknown origin | Native M4 read, its `missing_text` result delivered to a subsequent accepted request; final `abstained`, no evidence IDs or successful read receipts. |

Direct reads are permitted and must not be mislabeled as lookup execution.
No-tool answers, lookup-only responses and early abstention fail the positive
gate. Missing-text abstention without inspecting the record fails SQ02. Checking
32 microstrain/no outdoor test is a separate narrow content observation, not
an automatic general entailment verdict or phrase-matching scoring policy.

## Identity and side-effect boundaries

Keep old runner/core/policy/adapters/fixtures/results unchanged. Compose the real
policy and stage-aware adapter in a separate runner/CLI. Default mode checks
identity only: no key access, output creation or provider request. Bind exact
commit, executing source dependencies, fixture, tests/protocol, configuration
and installed transport/schema dependencies. Refuse altered/untracked files,
fixture or commit mismatch and unavailable checks before side effects. A file
hidden from ordinary Git status must not silently pass. Normalize line endings
only for Git comparison; also record actual disk hashes.

Live mode requires the new protocol acknowledgement and an exclusive fresh
output under the outputs root. Reject occupied/invalid destinations; never
overwrite or resume. Only after preflight read process `DASHSCOPE_API_KEY`;
no automatic dotenv, legacy key fallback, global model/base changes, keys in
arguments/logs or provider exception bodies. Preserve StageQwenLedger's original
offline-contract manifest. Add separate write-once identity and authorization
records for this batch, without pretending the old manifest granted permission.
An operator acknowledgement is not independent proof of user consent. Persist
all setup records before any dispatch. A single-owner ledger is not production
admission, a customer receipt or provider exactly-once delivery.

Pin the existing Beijing endpoint and exact model; non-thinking/non-streaming,
one tool per turn, no retries/redirects/environment proxies, TLS verification,
12 KiB request/64 KiB response and 512 output-token bounds. Keep existing
10-second connect/60-second owned request timeout. Preserve stage schemas;
final wire omits tools and retains explicit `none`.

Reuse frozen conservative rates (USD 0.573 input / 3.44 output per million),
16,384 input-token reservation and USD 0.011149312 next-request reservation.
They are the previous dated estimate, not today's tariff or invoice; check their
adequacy before a separately authorized live run. Report usage and reserved
budget separately. Uncertain requests are not free. One journal owns all calls.

## Stop and acceptance

For each case inspect transport protocol/model/usage/pending state, policy/core
audit, final envelope and its actual read-delivery condition. Transport acceptance
alone is not case success. Wrong model, missing/contradictory usage, invalid final,
policy/core refusal, identity loss, unresolved dispatch or persistence failure
stops later requests/cases. Preserve usage already received with rejected output.
Batch pass requires both cases and accounted requests; remaining cases are unrun,
not passed or omitted. Keep `semantic_support=not_assessed` and
`answer_verification=not_verified`. Outcomes/summary are write-once, request
events append/fsync; no automatic repeat or resumption exists.

Run full suite before/after, focused tests, latest Ruff, narrow Pylint and an
independent read-only review. Assert CLI preflight before key access, and real
policy/local tools through intercepted HTTP to journal/summary. Use synthetic
keys, short parameter IDs and HTTP interception that preserves Windows internal
socketpairs. Cover final-only wire, source/call/evidence binding, distinct case
gates, usage states, first-case failure suppressing second-case HTTP, occupied
output and failed setup/final writes at side-effect seams. Re-inject a missing
first-case failure stop (or equivalent dispatch defect), require a red test,
restore source hash and rerun. No weaker warnings/assertions/deadlines/skips.

A green offline runner only prepares a separately authorized experiment. It
does not complete Tool Calling or add a production saved-evidence follow-up route.
