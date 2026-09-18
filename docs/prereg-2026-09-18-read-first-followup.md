# Read-first saved-evidence successor: isolated synthetic preparation

Registered 2026-09-18, before successor implementation or provider calls.
Preparation baseline: `134a7051fb05b5121d9fcacb78dfd5530fc81675`.
Protocol identity: `report_evidence_read_first_qwen_canary_v1`.
Transport identity: `report_evidence_read_first_qwen_transport_v1`.
Native transform identity: `report_evidence_read_first_native_transform_v1`.

Status: **reference preparation complete; no implementation or native result**.
A different requested route_reviewer / gpt-6-astra / high context received only
neutral IDs, the three literal claim/text pairs and a relation rubric. It did
not receive author labels or rationales, inspect files or make external calls.
Its first-pass relations agreed with all three draft references; all three
supporting quotations were checked against the supplied text. Inherited project
instructions included historical context, so this is label-blinded,
context-limited LLM review, not fully blind judgment or human gold. Effective
backend metadata is unavailable. Raw input/output stay local and ignored.
The parent must commit this protocol and the reviewed fixture before code.
The parent owns PR153 integration, current ledgers, full-suite validation and
any later live dispatch. This preparation does not assert that PR153 CI passed.

## Question and preserved failure history

Can a named first-stage `read_source` choice deliver one complete saved summary
before the unchanged explicit relation policy judges the caller's proposition?
This tests forced read admission and a dependent synthetic proposition contrast,
not autonomous tool selection, unseen accuracy, retrieval or production use.

[RPQ stopped](results-2026-09-18-relation-policy-qwen-canary.md) after one native
request returned an early unavailable final under `tool_choice: auto`. It made
no local read or second request, so it did not test nonempty-evidence
insufficiency. Keep RPQ, PCQ, CLQ and all earlier frozen prompts, fixtures,
tests, results, allowances and occupied outputs unchanged. No unused RP case
becomes a new control here.

Alibaba Cloud's [official Function Calling documentation](https://www.alibabacloud.com/help/en/model-studio/qwen-function-calling),
fetched 2026-09-18 and marked updated that date, documents named function choice.
That documents the request form, not observed compatibility of this exact
`qwen3.5-plus`, pinned Beijing endpoint and two-stage contract. Compatibility
remains unproven until the separately gated new canary. Use named function
choice, not the generic `required` value, and do not change provider or endpoint
to make a rejected request work.

## Fresh dependent controls and blind reference gate

The only native cohort is
`tests/fixtures/report_evidence_read_first_qwen.json`, RF01-RF03 in that order.
These newly written fictional examples are dependent synthetic development
controls. Their contrast is informed by prior failures; they are not unseen
evaluation data, independent samples, real laboratory evidence or human gold.

| Case | Proposition | Frozen relation |
|---|---|---|
| RF01 | Ilex-M's physical thermal conductivity is 2.4 W/(m K) at 20 C; only density is measured | insufficient |
| RF02 | The same record reports measured conductivity 2.4 W/(m K) at 20 C; the record explicitly says it contains no conductivity result | refuted |
| RF03 | Ilex-N's physical conductivity is 2.4 W/(m K) at 20 C; its separate record explicitly reports that measurement | supported |

RF01 and RF02 share the literal saved text. Every case still gets a fresh
snapshot, conversation and receipt. RF03 uses a different fictional sample.
Preserve each literal English claim and saved text, including units and scope.
The text concerns the saved laboratory record, not the contents of all sources.

Before freezing, a different parent-arranged LLM judging context receives only
neutral case identifiers, literal claim/text pairs and a neutral relation
rubric. Withhold this table, draft labels, proposition kinds, rationales,
desired outcome and earlier reviews on its first pass. Follow the
[LLM-only review policy](llm-review-policy.md); record context limits, requested
role/model, available backend metadata, input/output identities and external
access honestly. This author cannot supply an independent reference review.
Missing review is pending, never agreement. Disagreement must be retained and
resolved or explicitly left uncertain before the parent freezes references;
no native result may be used to repair the reference later.

The reviewed complete fixture SHA-256 is
`ab4813b2479e14cecbf8834a44979e6f6a01aa847b05ea478c4735aaaa9fc500`.
Its `reference_status` is `llm_label_blinded_context_limited_reviewed`.
Commit this protocol/fixture before implementation; the executing code needs a
later independent identity. Raw review material stays local/ignored, and neither
these reference checks nor this hash authorizes disclosure or native dispatch.

For each native case construct report_ref=case_id and one source A1, group
academic, title "Fictional laboratory record", publisher "Synthetic controls",
source_type synthetic_control, origin unknown, accessed_date 2026-09-18.
Leave optional locators and publication date absent. Metadata is neutral and
identical across cases apart from the report reference. Only the literal claim,
unchanged policy, allowlisted catalog and actual selected read enter native
messages. Never send reference status, expected relation, proposition kind,
rationale, scripted response, historical outcome or private RS material.

## Narrow source scope and separate availability audit

Admit only a validated trusted snapshot with zero or one source, complete
untruncated catalog metadata and at most 1,500 Unicode code points of saved
summary. More sources, a longer summary, an omitted catalog entry, partial
coverage or a truncated title are **out_of_scope**, before HTTP or local read.
Do not truncate the snapshot to fit, choose a convenient source, search, or
misreport scope rejection as unavailable evidence. Invalid inputs fail admission.

Availability is a separate code-derived audit, not the model's relation or a
renaming of the frozen inner result. Record scope, actual read execution,
delivered receipt IDs, usable receipt IDs and the observed reader outcome.
When the read was never executed, say so; do not invent a missing-text result.

| Admitted input | Required native/read path | Permitted final relation and IDs |
|---|---|---|
| No source | One final-only request; zero reads/receipts | unavailable, empty supporting IDs |
| One source with `None` or empty summary | Named first read still executes; actual `missing_text`; no receipt | unavailable, empty supporting IDs |
| One source containing only whitespace | Named first read; actual delivered receipt, zero usable receipts | unavailable, empty supporting IDs |
| One source with nonblank summary | Named first read; one complete delivered and usable receipt | supported/refuted with that one supporting receipt, or insufficient with empty supporting IDs |

A nonblank read establishes usability only, not semantic relevance or truth.
Insufficient keeps the actual delivered/usable receipt in audits even though
the model's supporting IDs are empty. No-source, missing and blank variants
are offline boundary tests, not extra native cohort members.

## Frozen callback, new native transformation

Reuse the frozen RP wrapper, claim parser, catalog wrapper, reader and core.
Do not alter relation instructions or the strict four-field final JSON. The RP
callback continues to emit its original request: first nonempty-catalog
`tool_choice: auto`, then `none`; no-source is final-only `none` from the start.
The adapter accepts one positional request object and never mutates it.

After exact callback admission, the new deterministic native transform changes
only the registered wire controls and adds pinned transport configuration:

- First nonempty catalog: `tool_choice` is
  `{"type":"function","function":{"name":"read_source"}}`. Advertise only
  `read_source`, require exactly source_id/offset/length with no extra arguments,
  limit source_id to the sole visible ID, offset to integer enum `[0]`, and
  length to integer enum `[1500]`. Preserve other frozen schema descriptions.
  Omit `response_format` on this first read request.
- First empty catalog: omit `tools`, use `tool_choice: none` and
  `response_format: {"type":"json_object"}`.
- Every second request: omit `tools`, use `tool_choice: none` and that same
  JSON Object format. No third request, second read or final-stage tool call.

Require exactly one actual native `read_source` call with the full valid
arguments before returning its message to the frozen executor. Reject early
finals, refusals, wrong IDs/names, multiple calls, missing/extra arguments,
partial reads and nonzero offsets. Validate exact integer types: booleans,
floats and strings cannot pass as 0 or 1500. These failures stop before any
local read or second POST; no synthesized call, defaulting or repair is allowed.

Bind the trusted snapshot and verbatim claim at construction. Check the full
system message, exact policy bytes/hash, catalog and original claim on every
callback. On the second callback compare the complete accepted native assistant
history, tool-call ID and actual tool-result payload with the trusted snapshot
and accepted arguments. Compare all metadata, text, status, offsets, lengths,
truncation flags, hashes and receipt identity, not just ID/hash subsets. A
forged `missing_text` cannot replace present text. Derive the finite expected
payload for comparison without executing an extra read; actual execution
counts come from the frozen executor, not that deterministic comparison.

Preserve provider assistant content and tool argument strings unchanged,
including spacing, null content and the strict final declaration. Projection
may omit provider-only metadata. Label stored messages as **projected native
assistant messages**, not complete raw HTTP responses or packet captures.
No full raw-response capture/storage is required. Reject secret echoes before
persistence; safe omission of a rejected message must not erase observed usage.

## Separate callback, wire, delivery and accounting facts

The original RP callback and transformed native request are different objects.
Record original canonical callback hash, complete byte count, ordinal, choice,
policy identity and delivery facts separately from native transform identity,
wire ordinal, complete body hash and byte count. Keep the RP callback audit and
native journal distinct; entering a callback, reserving intent, receiving a
reply, executing a read and delivering that result are not interchangeable.

The new runner must not reuse RPQ's wire-to-callback audit helper: inverse
projection now loses the original `auto` choice and broad callback schema.
Independently recompute the registered deterministic transform from each
validated original callback and compare all canonical wire bytes with the
reserved journal body and actual POST. Reservation bytes must equal POST bytes.
Keep frozen inner delivery and RP policy-to-callback delivery separately checked.

Preserve the 12 KiB complete request-body limit after all transformations,
64 KiB HTTP response limit, 512 output tokens, exact `qwen3.5-plus`, non-thinking,
non-streaming, temperature zero and no parallel tool calls. Use only the pinned
Beijing endpoint `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`,
TLS verification, `trust_env=False`, zero redirects/retries, 10-second connect
and 60-second overall request bounds. Preserve strict protocol/model/secret
guards and raw integer usage validation, including total-token consistency.

Use the frozen base `CanaryLedger`, key validation, HTTP and accounting
primitives only; never invoke an old native adapter's `__call__`, old runner or
patch module globals to repurpose them. Give the new ledger its own manifest,
with `live_authorization=False`. Preserve pre-dispatch reservation and known
usage even on rejected replies, post-response identity drift, budget stop or
journal finalization failure. Unknown/contradictory usage retains its reservation
and stops; unknown is not zero, and inability to persist is not successful
publication. Retain safe code-owned error categories rather than raw exceptions.

## Dedicated files, identity and single-batch authority

Implementation, only after the parent's protocol/reference freeze, is limited
to these new files in addition to this protocol and fixture:

- `src/academic_agent/report_evidence_read_first_qwen_transport.py`
- `tests/test_report_evidence_read_first_qwen_transport.py`
- `src/academic_agent/report_evidence_read_first_canary.py`, with `main()`
- `tests/test_report_evidence_read_first_canary.py`

No root CLI, CrewAI change, production route, old frozen-file/test/result edit,
credential read, provider call, push or merge belongs to this implementation
assignment. Parent-owned current documentation/ledger changes stay separate.

The runner binds its new implementation/tests/protocol/fixture, full executing
project dependency closure, frozen policy and reused primitives, configuration
and locked installed dependency versions to an exact committed SHA. Compare
committed blobs and fixed-path disk bytes using existing CRLF-to-LF rules;
reject indirect/reparse paths, hidden source drift and package-version mismatch.
Installed versions are not installed-package byte attestation. Recheck exact
commit, fixture and dependency identity before and after each native call,
including failed calls, without discarding already observed usage.

Default `python -m academic_agent.report_evidence_read_first_canary` verifies
identity only: no `.env`, credential lookup, output creation or HTTP. Future
native mode requires the full expected commit, frozen complete-fixture hash and
this new protocol acknowledgement. Acknowledgement is not evidence of review,
CI success or a new spending grant. No force/resume, output/case/model override,
retry, repair, fallback, search, private report or real-data transmission.

Reserve exactly `outputs/report_evidence_read_first_qwen_canary_v1` exclusively.
Any occupied or partially created directory prevents another run; never delete,
rename or change the output to evade that stop. Persist identity/experiment/
acknowledgement before dispatch; append/flush/fsync journal intent before POST.
Case and summary publication must be write-once after successful flush/fsync
and close. Pending files and failed writes cannot signal completion or release
another case. This is local single-owner accounting, not distributed admission,
provider exactly-once, hostile-deletion protection or disk-loss recovery.

The standing synthetic scope is at most six sequential requests and USD 0.10
soft stop, accepting one in-flight small overshoot. At most two requests and
one read belong to each fresh case. Preserve inherited conservative estimates:
USD 0.573/3.44 per million input/output tokens, 16,384 reserved input tokens,
USD 0.011149312 per request and USD 0.066895872 for six. These frozen estimates
are not current prices or invoices; budget occupancy is not an extra charge.

Only the parent may later dispatch, after a committed exact identity, different
strong route_reviewer review and all exact-SHA CI jobs pass. Only an explicit
process `DASHSCOPE_API_KEY` may serve that future native path; default CLI and
this implementation stage never inspect it or load dotenv. Old remaining
allowances, a draft manifest or passing mocked HTTP are not live authority.

## Prospective acceptance, stopping and focused verification

Hypothesis: each nonempty control reaches exactly one complete actual read and
one final-only native request; admitted relations match RF01/RF02/RF03 in order.
A mechanical pass requires full original callback/RP audits, deterministic wire
and journal agreement, separate availability facts, unchanged final schema and
receipt rules, known usage, and no pending or stopped state. A valid but wrong
relation is a mechanical pass and a separate frozen-reference failure, never a
rewritten answer. Semantic truth remains unverified by these mechanical gates.

First setup, identity, HTTP, protocol, read-admission, accounting, audit,
mechanical, frozen-label or publication failure stops the batch. Mark all later
cases unrun, not failed answers. Batch success requires all three mechanical,
reference and case-publication passes plus known complete accounting and a
successfully published summary. Missing observation/review is never a pass.

Focused tests use the real frozen RP wrapper and reader plus the new adapter
and base HTTP path with fake-key `httpx.MockTransport`; assert actual request
bytes and HTTP/read counts. They cover all availability rows and out-of-scope
inputs; early exits and malformed schemas; full native history/tool-result
forgery; byte limits and callback-versus-wire audit tampering; strict protocol,
model, secret and usage rejection; retained usage, budget and failed-journal
states; runner identity/occupied-output/publication/first-stop behavior; and a
full six-request intercepted batch with labels absent from native messages.
Test default CLI isolation without accessing ambient credentials. End any
process-global test guard with the operation, before pytest reporting.

Reinject three defects separately: restore native first choice to `auto`, drop
the full first-read reply gate, and drop complete tool-result comparison.
Provide otherwise valid downstream responses so each regression fails on its
dispatch/read boundary, not an exhausted mock. Restore exact bytes and rerun.
Keep tests focused rather than copying hundreds of frozen cases. Use `uv` for
focused checks; the parent coordinates baseline/final full suite, latest Ruff,
narrow Pylint and exact CI. Do not weaken assertions, add warning ignores or
claim this author performed independent review. Shared failed fix/test count
starts at zero and follows the routing escalation policy without resets.

After any separately authorized live batch, obtain a fresh label-blind,
context-qualified LLM judgment of actual claim/text/receipt/answer with a neutral
rubric. Missing admitted answers are `not_reviewable`. No extra paid judging
call is authorized here. Close and preserve the batch whether pass or fail;
report mechanical, availability, reference and later semantic judgments
separately. Only permitted synthetic aggregates/method limits may be public.
No native result authorizes retuning, another batch, private-data release,
production activation, merge or deployment.
