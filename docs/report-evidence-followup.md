# Report evidence follow-up

## Scope

This is a production-disconnected, read-only conversation prototype. It is not
the supplementary Evidence-gap Planner, does not reopen v8, and cannot add
sources to a report. Its task is helping a reader locate saved evidence, not
deciding whether an investment or scientific claim is correct.

The ordinary alternative remains browsing the same source cards and summaries.
Reader benefit relative to that alternative has not been measured. This phase
tests the tool conversation protocol, not model quality or product adoption.

New semantic evaluations follow the [LLM-only review policy](llm-review-policy.md).
Human review is not required to proceed; independent model judgment is still
separate from structural admission and cannot establish actual user adoption.

## Separate code-owned saved-source locator

The [locator contract](prereg-2026-09-18-saved-source-locator.md) removes model
answer generation from a new, isolated callback path. At most one visible-ID
selection is followed by one local read and code-owned JSON containing the
complete saved text within the 1,500-code-point limit. Missing, blank, declined,
out-of-scope and failed/unavailable cases remain distinct. It reuses the frozen
catalog and reader without rewriting the earlier conversation experiments.

Run `uv run python report_evidence_source_locator_demo.py` for the no-argument
synthetic `scripted_offline` demonstration. It reads no credentials or files and
does not contact a model. Native selection quality, benefit over the Sources
browser, private-data authority and production admission are still unestablished.
Do not describe this demo or JSON serialization as a deployed Tool Calling UI.

## Separate offline claim-relation contract

The [read-first successor](prereg-2026-09-18-read-first-followup.md) separately
constrains native admission while retaining this frozen claim/RP chain. It
accepts only zero/one complete short saved source and explicitly forces the
first named read when a source exists. Source availability, local execution,
inner/RP delivery and native request observations remain separate. This is
controlled tool execution, not autonomous source selection or semantic proof;
there is still no public follow-up route or production activation.

The [RF native batch](results-2026-09-18-read-first-qwen-canary.md) subsequently
completed one real forced-read conversation but failed its first relation label.
The batch is closed, later controls are unrun and automatic expansion stops.
This establishes neither general semantic judgment nor a shipped user feature.

The [new preregistration](prereg-2026-09-16-followup-claim-relation.md) defines
`run_claim_relation_followup(snapshot, claim, *, transport)` in the isolated
`report_evidence_claim_relation` module. The caller supplies an explicit
proposition verbatim. This is not automatic claim extraction from arbitrary
questions, an existing Qwen adapter option or a production endpoint.

The model declares `claim_relation`, `answer`, `supporting_evidence_ids` and
`caveats`; it cannot independently set delivery `status`. A `supported` claim
and an explicitly `refuted` claim can both produce evidence-backed delivery.
`insufficient` means nonempty material was delivered but does not establish the
claim or its refutation; `unavailable` means no usable read reached the callback.
Both abstain. Negation in prose is not a rule for selecting any of these states.

The wrapper checks structural consistency and actual receipts, preserves the
declaration on serialization and derives the old core envelope without changing
frozen code. It does **not** verify the model's semantic relationship. A false
but structurally consistent declaration can still pass; all semantic flags
remain unverified. Scripts are not model inference.

One read and two callbacks remain the ceiling. The transformed callback request
is checked again against 12 KiB; the outer wrapper's earlier byte/delivery
counts cannot stand in for the final callback. Early ending, checked missing
text, delivered-but-insufficient evidence and execution failure stay distinct.
That callback-only contract adds no provider adapter, automatic judging request
or paid runner. The separate native candidate below has its own identity.

## Separate claim-relative native Qwen candidate

The [native wire protocol](prereg-2026-09-16-claim-qwen-transport.md) adds
`ClaimQwenLedger` and `ClaimQwenFollowupTransport` for the claim wrapper, not
an option that silently changes the older catalog adapter. Construction binds
the trusted snapshot and caller-owned claim; even a different first-turn claim
must be refused before reservation. The full paired local read result is
compared against the snapshot and original arguments, without another read.

The four-field final content returns unchanged to the wrapper. JSON Object is
a wire constraint, not schema or semantic proof; the wrapper still validates
the declaration and derives delivery. It preserves the frozen exact model,
HTTP primitive, one-read/two-request ceiling and accounting rules. Full encoded
HTTP size and journal hashes are checked at the dispatch boundary, separately
from callback entry. A wrapper failure is not a successful batch merely because
the transport accepted its response; future callers must handle that outcome.

This candidate is tested with intercepted HTTP and fake keys. It adds no live
runner, provider-data grant, search or production endpoint. Ledger journals
contain source text and answers: future real-data journals remain private;
hashing does not make them safe to publish. Semantic judging follows the
LLM-only policy and remains separate from this engineering validation.

## Separate claim-relative synthetic canary

The [new CLQ preregistration](prereg-2026-09-16-claim-qwen-canary.md) freezes
three invented single-source controls for support, refutation and nonempty
insufficiency. It permits at most six sequential requests in one closed batch,
USD 0.10 soft stop, only after exact-tree CI and independent implementation
review. The unavailable relation remains offline-only for this batch.

The new runner separates code/protocol checks, local expected-label matching
and later blind LLM semantic review. Labels never enter provider prompts or
the blind judge's first pass. A correct refutation is distinct from an
unsupported answer. Any first transport, wrapper, label, accounting or
publication failure stops further cases; missing judgments are not matches.

The fixed output directory cannot be reused, including after partial setup.
Identity-only default mode reads no key and sends no request. This protocol
does not reopen a CQ/RS budget, transmit private reports, establish general
accuracy, or authorize a production endpoint. Its frozen method is a plan,
not a claim that the native model already passed the new controls.

The subsequent [single live result](results-2026-09-16-claim-qwen-canary.md)
completed six requests after the execution SHA's CI passed. All three cases
passed mechanical checks, but only two matched the frozen relation labels;
the batch failed and is closed. Blind LLM review supported the model's third
refutation: the proposition concerns a recorded flow, which the source
explicitly denies measuring. Preserve that reference-design diagnostic
separately from the failed frozen gate. Neither the intended live
insufficiency lane nor general semantics is now established.

## New PCQ reference preparation

The [PCQ protocol](prereg-2026-09-17-claim-proposition-contrast.md) uses a new
physical-value/record-content contrast pair and a separate measurement control.
Fresh-context LLM pre-review occurred without author labels or scripted answers;
the [aggregate result](results-2026-09-17-claim-proposition-contrast.md) records
three matching proposals and the limitations of AI-generated development labels.

```bash
uv run python report_evidence_contrast_check.py --review-input
uv run python report_evidence_contrast_check.py
```

The first command prints the allowlisted question/source view; the second
prints a scripted local read-to-final rehearsal. Neither calls a provider,
reads credentials, authorizes a paid run or judges native model correctness.
Do not replace the frozen CLQ fixture or reset its closed output directory.

### Separate PCQ native execution contract

The [new native protocol](prereg-2026-09-17-claim-proposition-contrast-qwen-canary.md)
uses those exact reviewed fixture bytes with a dedicated runner, a distinct
fixed output and a new execution identity. It does not execute the closed CLQ
runner or use the scripted preparation answer as a native-output assertion.
Three fixed cases allow at most two sequential requests each. The first failed
read, receipt, wrapper, accounting, identity, label or publication gate stops
the batch and leaves later cases explicitly unrun.

The dedicated CLI defaults to identity-only: no credential lookup, output
creation or HTTP. A later native dispatch requires separately recorded protocol
acknowledgement, exact commit/fixture identity, independent implementation review
and all exact-head CI checks. The adapter's offline manifest stays unchanged.
The model sees only the claim, catalog and actual local read, never reference
labels, rationales or scripted answers. Nonempty-insufficient must retain its
usable read while abstaining with no supporting IDs.

Case mechanical results, reference agreement and later LLM review are distinct.
Overall batch success additionally requires known accounting, no pending or
stopped state and complete summary publication. Neither offline intercepted
HTTP nor a declared claim relation establishes semantic correctness; runtime
not-assessed/not-verified flags are unchanged. No public route, production
admission, real saved-report disclosure or automatic deployment is added.

The [subsequent native batch](results-2026-09-17-claim-proposition-contrast-qwen-canary.md)
is now closed after two requests. PCQ01 passed the actual read/receipt/JSON
checks but declared refuted where the frozen reference is insufficient;
PCQ02/03 were not run. Label-blinded LLM review judged the answer mixed, but
inherited project history prevents claiming complete context isolation.
Do not invoke this occupied output again or rewrite its protocol/prompt/labels.
The intended live nonempty-evidence abstention lane remains unproven; any
successor begins with a new offline contract rather than another paid retry.

### Explicit relation-policy successor

The [new offline protocol](prereg-2026-09-17-claim-relation-policy.md) and
[qualified result](results-2026-09-17-claim-relation-policy.md) define a separate
callback layer, not an update to the frozen claim wrapper. Its single-request
callback signature deliberately differs from old native adapters. A nested
inner result records entry into the policy layer; its own audit records entry
into the final injected callback. A read can reach the former and be blocked
before the latter. Neither observation proves a model obeyed the rubric.

The explicit rubric preserves the original proposition and distinguishes
missing measurements, actual contradiction, record-content claims, scope and
negation. Scripted controls are not semantic model validation. All runtime
semantic flags remain unverified; no native executor or production connection
is added, and PCQ/CLQ outputs must not be retried or relabeled.

### Relation-policy native wire adapter

The [separate wire protocol](prereg-2026-09-17-relation-policy-qwen-transport.md)
and [offline record](results-2026-09-17-relation-policy-qwen-transport.md)
define a new positional-request adapter and exact-type ledger for RP. The
trusted snapshot, verbatim claim and frozen policy are bound before the first
request; complete native history and saved-text results are compared without
rewriting messages or model relations.

The complete final HTTP body has its own byte check and pre-dispatch journal.
An RP callback entry may exist without a dispatched request; keep these facts
separate. Native protocol admission is not strict-wrapper or semantic success.
This network-capable adapter is tested with intercepted HTTP and fake keys,
not a live runner, production integration or new private-data authorization.
The [CI isolation correction](results-2026-09-17-relation-policy-ci-isolation.md)
records why the environment-read guard must end before pytest reports the test,
while remaining active throughout adapter construction and intercepted HTTP.

## Offline demonstration

```bash
uv run python report_evidence_followup_demo.py
```

The demo supplies synthetic sources and a scripted transport. It exercises the
real local lookup/read functions and tool-call/result pairing, but makes **zero
provider requests**. It does not read `.env`, accept credentials, read a saved
run directory or fetch a URL. It must not be presented as a live Qwen demo.

## Trusted snapshot boundary

The caller supplies one source collection and a report reference; the module
projects them into a detached immutable snapshot. Duplicate source identifiers,
wrong domain prefixes and malformed relevant fields are rejected rather than
silently overwritten. Modifying the original collection later cannot change
the conversational evidence.

This in-memory boundary does not implement web authentication or authorize the
caller. A future route must authenticate and select the source collection
before constructing a snapshot. Model arguments must never supply a run ID,
file path, URL, credential or alternative provider. Hashes bind content to this
supplied snapshot; they do not prove authenticity, ownership or source truth.

## Available tools

| Tool | Reads | Limits and explicit absence |
|---|---|---|
| `lookup_sources` | Literal matches in this snapshot's saved titles/summaries | Query 1–256 characters, at most five hits; total matches and truncation remain visible. No matches is not evidence that the literature lacks an answer. |
| `read_source` | One source's saved summary, by its local source ID | Strict integer character window, at most 1,500 characters; unknown IDs and unavailable text issue no evidence. A non-empty truncated window may be delivered successfully, but remains explicitly incomplete. |

Window offsets use Python/Unicode code points and half-open `[start, end)`
intervals, not UTF-8 byte offsets or JavaScript UTF-16 indices. A complete window
means all **saved** text was returned; the saved text may itself be a truncated
abstract, search snippet or material with unspecified origin. Nothing here
retrieves or verifies publisher full text.

`window_truncated` means that some saved text lies outside the returned window,
not that the requested length was clipped at the end. A partial non-empty
window can issue an evidence ID and support `answered_with_evidence` as a
delivery state; it does not establish completeness or semantic support.

Tool descriptions and the initial instruction treat returned source text as
untrusted data. Enforcement comes from the fixed dispatcher, strict arguments,
snapshot binding and budgets, not a promise that prompting defeats injection.

## Conversation and evidence delivery

The transport must be explicitly injected. The core has no implicit network
fallback. It exchanges assistant `tool_calls` and tool-result messages with
the exact original `tool_call_id`, following the documented
[Qwen-compatible Function Calling message shape](https://help.aliyun.com/en/model-studio/qwen-function-calling).
The scripted demo remains offline; native model observations belong to the
separate bounded canary below, not to that demonstration.

At most two tool requests and three transport turns are allowed, with at most
one tool request per turn. Bad tool names and arguments consume tool budget;
ambiguous/duplicate IDs fail the protocol. There is no automatic retry, repair,
search fallback or autonomous switch to another report. The injected
transport must separately enforce network timeout, credentials and cost; an
in-process injected callback cannot be safely preempted by this library.

Successful reads issue code-owned evidence IDs bound to the snapshot, source,
field, exact interval and excerpt hash. The model can select only IDs actually
issued in this conversation. The application assembles their source metadata
and text; it does not accept model-invented quotes or provenance. Lookup hits
alone do not authorize an evidence citation.

The final answer distinguishes evidence-backed *delivery* from an answer without
delivered evidence, deliberate abstention and execution failure. In all cases,
`semantic_support` remains `not_assessed`: exact excerpt attribution is not
proof that the prose is entailed by the excerpt. No-tool responses do not count
as successful tool use or completed evidence checking.

## Separate offline stage policy

See the [measured offline result](results-2026-09-15-report-evidence-stage-policy.md)
for regression counts, the dispatch-level mutation and limits.

The [stage-policy protocol](prereg-2026-09-15-report-evidence-stage-policy.md)
adds an opt-in wrapper around the unchanged original loop. This is not a
replacement for the frozen Qwen runner. It narrows both the tool declarations
sent to the injected callback and the responses admitted back to local dispatch.

The new entry is `run_policy_followup` in
`academic_agent.report_evidence_guarded_followup`. Its separate demonstration is:

```bash
uv run python report_evidence_guarded_followup_demo.py
```

This uses an invented orchard-probe record and a scripted callback, accepts no
arguments, and labels its JSON output `scripted_offline`. It is not a paid
rerun of FQ01 and cannot consume the previous batch's remaining allowance.

| Stage observed from actual local results | Allowed next tool action |
|---|---|
| Before a result | One lookup or a direct read of an ID present in this snapshot. |
| Lookup with hits | Read only an ID in those returned hits; no second lookup. |
| Lookup without hits, or after a read result | No tool; final answer/abstention only. |
| Last allowed turn | No tool, even if another numeric tool slot remains. |

The final-only call has `tools=[]` and `tool_choice="none"`. A response that
ignores this restriction is rejected before a tool executes, not retried with
more permissions. Lookup is one case-insensitive contiguous literal phrase,
not a keyword bag or semantic search. Zero hits do not prove absent sources or
justify invented content. A direct-read existence check does not prove the
model obtained the ID without guessing; the catalog still exposes no ID list.

Policy state follows actual paired tool results, not model-written stage
claims. The original core counts delivery at entry to its callback. The wrapper
therefore distinguishes that legacy diagnostic from reaching the actual
downstream callback: pre-dispatch rejection is not downstream delivery, and
post-response rejection cannot erase evidence already handed to that callback.
Neither observation proves a provider received or understood the evidence.

The ceiling stays two tool attempts and three core turns. Scripted positive and
negative controls exercise this policy without credentials or network. They do
not establish a higher live success rate. Earlier abstention is not a successful
answer to the consumed positive FQ01 case. The original adapter accepts only
`auto`; silently translating `none` to `auto` is not a supported integration.

## Stage-aware Qwen transport

The separate `report_evidence_stage_qwen_transport.py` connects the callback
contract to an explicit HTTP body without editing the old adapter or runner.
`StageQwenFollowupTransport` uses `StageQwenLedger`, whose code-owned manifest
labels this as an offline contract and records `tool_choice_by_stage`. Reusing
an auto-only manifest would misdescribe the operation even if a mock answered.
The scope label is not a network sandbox or live authorization.

Its permitted inputs are the policy's original lookup/read declarations, the
single read declaration retaining its returned-hit enum, or an empty list with
`tool_choice=none`. No dummy tool, hidden `auto` replacement or schema repair is
used to make finalization appear compatible. In final-only mode, the callback's
empty tool list becomes an omitted `tools` member in the HTTP body, while
explicit `tool_choice=none` remains. This mapping occurs before serialization
and reservation; it is not an after-the-fact rewrite of an auto request.
Native IDs/results remain in the message history, and the exact wire bytes must
match the pre-dispatch journal. The offline preparation did not observe live
acceptance. The [later bounded batch](results-2026-09-15-stage-qwen-canary-live.md)
received three accepted transport responses, including final-only, but the
final envelope failed core parsing. This is not successful answer closure.

HTTP cancellation/TLS/proxy/redirect limits and response/usage/key protections
reuse frozen primitives. The old `__call__` is not reused because it hardcodes
auto. The new source documents that dependency coupling; a later runner must
bind the new module and every reused dependency rather than copying an old
experiment identity. The ledger remains single-owner, not customer admission.

Transport acceptance does not mean the final envelope, evidence citations or
answer semantics passed the policy/core. The separate runner below must stop
on those failures too. Verification uses synthetic keys and intercepted HTTP;
no new paid experiment or production route is implied. See the
[offline transport protocol](prereg-2026-09-15-report-evidence-stage-qwen-transport.md).
The [scoped result](results-2026-09-15-report-evidence-stage-qwen-transport.md)
records validation and the failed Windows isolation attempt without relabeling
either as provider behavior.

## Stage-aware canary preparation

The [new protocol](prereg-2026-09-15-report-evidence-stage-qwen-canary.md)
freezes SQ01/SQ02 separately from the failed original batch. The new command
`report_evidence_stage_canary.py` defaults to identity checking, not execution.
It requires an exact committed version and the new fixture's SHA-256 before
any credential lookup, output creation or possible provider request. Its
execution path composes the actual stage policy and separate HTTP adapter.

For an already committed checkout, this PowerShell example performs only the
default check; selecting HEAD here identifies the checkout, not a paid approval:

```powershell
$commit = git rev-parse HEAD
uv run python report_evidence_stage_canary.py --expected-commit $commit --expected-fixture-sha256 93d3872b7789a1ff99fbe236274a0ec7a52ce987ece9d53f63e4080fba27ffa6
```

Do not add `--authorize-paid` or an output directory to a dry check. Code-owned
failure categories are printed instead of raw key, path or provider exceptions.

The future live path requires an explicit acknowledgement for the new protocol,
a fresh exclusive output and only the process `DASHSCOPE_API_KEY`. There is no
automatic `.env` read, provider fallback, retry, repair or resume. An operator
acknowledgement records an action; it is not independently verified user consent
or reuse of the old batch's unused calls. Fresh bounded user authorization is
still required before anyone executes it.

SQ01 requires an actual saved-text read and a cited final answer; SQ02 requires
an actual missing-text read followed by abstention. Transport acceptance alone
does not pass either case. First-case protocol/core/accounting failure prevents
the next case, preserving received usage and marking the rest unrun. Default-off
preparation is not live Qwen closure, semantic support or production admission.
The [offline preparation result](results-2026-09-15-stage-qwen-canary-preparation.md)
records the committed default check and dispatch-level defect re-injection.

The [subsequent authorized live result](results-2026-09-15-stage-qwen-canary-live.md)
is a failure, not an extension of that offline pass. SQ01 performed lookup and
read, with the complete saved excerpt reaching a final-only HTTP request, but
the response mixed prose and fenced JSON and failed `invalid_final_envelope`.
Three requests were accounted; SQ02 was not run. Do not repair or rerun this
closed batch using its remaining budget. A separate final-output contract is
the next offline candidate; no production route or semantic-validation claim
follows from observing one successful read.

## Separate final-only JSON candidate

The [new protocol](prereg-2026-09-16-report-evidence-final-json-qwen.md) addresses
the observed SQ final-envelope failure without changing its frozen adapter or
parser. A distinct transport adds `response_format={"type":"json_object"}`
only when tools are disabled; native lookup/read requests keep their original
shape. The final HTTP request still omits `tools` and retains `tool_choice=none`.
This asks for valid JSON, not schema compliance or semantic correctness.

The JSON keyword must already appear as a standalone ASCII word in string
system/user content before reservation. Assistant/tool text cannot satisfy
the prerequisite; the adapter does not add missing instructions. Body encoding,
reservation hash and actual HTTP agree on the complete final request. The core
continues to reject prose, fences, malformed envelopes and invalid evidence IDs.

The separate `report_evidence_final_json_canary.py` entry defaults to committed
identity checking only, before key/output/network work. JQ01/JQ02 are new
synthetic controls, not repaired or repeated SQ outcomes. Live use requires
the final implementation identity, fixture hash and applicable bounded user
authorization. No retry, remaining-budget continuation or production route
follows from the prior failed batch or from preparing this candidate.

For a committed checkout, the default identity-only check is:

```powershell
$commit = git rev-parse HEAD
uv run python report_evidence_final_json_canary.py --expected-commit $commit --expected-fixture-sha256 f0e8233a7b0e0d86783f069d96880ace941cd0ac16dbfa934e723d653febb5ca
```

Do not supply an output path or paid acknowledgement to this check. It must
return before inspecting a key, whether or not a credential exists. Live mode
uses a new code-owned ledger identity and exclusive output path, retains known
usage when a final answer is rejected, and stops on the first failing case.
JSON Object output alone is not a successful read/citation or abstention gate.

Only `JQ01.json`, `JQ02.json` and `summary.json` are authoritative results.
Each is published without replacing an existing name, after its same-directory
candidate is fully written, flushed, fsynced and closed. A leftover dot-prefixed
`.pending` file is diagnostic material, never a successful result or a resume
token. Unsupported hard links fail closed. Cleanup after successful publication
cannot reverse the returned truth; this is not power-loss or distributed safety.

The [single JQ live batch](results-2026-09-16-report-evidence-final-json-qwen.md)
used two requests and failed JQ01: a long contiguous lookup query missed the
existing source, and the final-only response was valid JSON abstention without
a read. JQ02 was unrun. JSON-format compatibility on this zero-hit branch is not
successful saved-evidence closure. The next offline gate is the lookup contract;
do not use the remaining allowance for another batch or enable a production route.

## Bounded metadata catalog candidate

The [offline protocol](prereg-2026-09-16-report-evidence-catalog.md) registers a
separate `report_evidence_catalog_v1` entry. It does not alter the frozen lookup,
core, stage policy, Qwen adapters or old runners. The caller supplies the same
trusted in-memory snapshot; the new wrapper derives unranked titles and source
IDs before the first callback. No summary, URL, DOI or evidence ID is supplied
through this metadata path. Titles remain untrusted data, not instructions.

Limits are 32 entries, 256 Unicode code points per title and 6,144 canonical
ASCII JSON bytes for the entire catalog. Counts and explicit coverage disclose
prefix omission and title clipping. Zero sources is a valid empty catalog;
failure is not empty success. Canonical callback arguments are independently
limited to 12 KiB before dispatch. A future HTTP adapter must also account for
its own outer request fields and escaping, rather than assuming that this check
proves wire acceptance.

The first action permits only one `read_source` of a visible ID, or finalization;
an empty catalog permits no tool. After the actual read result, the next action
is final-only. This deliberately narrower candidate uses at most one local tool
and two downstream callbacks, under the old two-tool/three-turn ceiling. It is
not a controlled experiment isolating metadata from policy changes. It cannot
fall back to another source, lookup, external search, pagination or a repair.

The old count-only overview remains unchanged; the new supplementary catalog
contains IDs. It is injected as user-data with a code-owned system warning, not
as a fake tool result or source text promoted to system authority. Each outgoing
history contains one copy. Direct read receipts still come exclusively from the
frozen executor. Metadata-only citations, invisible IDs and repeated reads fail
before granting more evidence. Delivered evidence means supplied to the actual
injected callback, not read bookkeeping performed before a rejected dispatch.

`run_catalog_followup` and `report_evidence_catalog_demo.py` are isolated,
callback-only entry points. The no-argument demo is `scripted_offline`; it reads
no credential, real report or provider. The old Qwen transports only admit up to
five hit IDs, so they are not compatible adapters for this catalog's 32-entry
enum. The separate catalog-native wire contract below does not widen those
frozen files. The separate CQ protocol below freezes a new synthetic live gate;
the scripted demo still needs no key or provider call.

```bash
uv run python report_evidence_catalog_demo.py
```

Catalog coverage is not question relevance or semantic support. Similar titles,
omitted entries, truncation and facts split across sources remain limits. The
candidate cannot claim reader benefit or model selection quality from scripted
controls. JQ, SQ, FQ and v8 keep their recorded failures; production stays off.

## Catalog-native Qwen wire contract

The [separate protocol](prereg-2026-09-16-report-evidence-catalog-qwen-transport.md)
adds a network-capable adapter for the catalog wrapper, validated through
intercepted HTTP rather than provider requests. The caller explicitly supplies
one trusted snapshot, a dedicated ledger and key; no ambient credential lookup
or production route is added. Each adapter instance belongs to one conversation.

The visible-ID enum can contain up to 32 entries and must agree with the bound
catalog. Nonempty initial calls use only `read_source`; after the actual local
read, final-only requests use `none`, omit tools and request JSON Object. The
strict core parser still checks the final envelope and issued receipt IDs.
Metadata does not issue citations, and JSON mode is not semantic validation.

Before a second reservation, compare the complete paired result with the saved
window in the bound snapshot, including absence, offsets, text and receipt
identity. Retaining a source hash cannot legitimize changed text. This computes
comparison bytes only: it neither repeats the read nor issues another receipt,
and cannot prove a Python caller actually executed the tool.

The complete canonical HTTP body, including model and output parameters, must
fit 12 KiB before reservation. Its bytes must match the durable request hash.
Callback entry, HTTP dispatch and observed response are separate facts: the
catalog's forwarded receipt alone does not prove the provider received it.
Unknown usage retains a reservation and stops further dispatch; it is not zero.

The adapter reuses pinned one-shot HTTP/accounting primitives, not an old batch
identity. The original model, destination, price estimates, TLS/proxy isolation,
timeouts and retry restrictions remain. The ledger is single-owner, not public
paid admission or a grant to use any remaining experiment allowance. No new
paid runner or synthetic batch was implemented in that offline phase, and old
failed observations remain closed. The new CQ gate is separate from it.

## Catalog-native synthetic canary

The [CQ preregistration](prereg-2026-09-16-report-evidence-catalog-qwen-canary.md)
freezes two fresh invented cases, six titles each, with the target sixth. CQ01
requires an actual full saved-text read and a strict final answer citing that
receipt; CQ02 requires an actual missing-text read before abstaining. Exactly
two accounted requests per passing case must demonstrate the paired tool result
in the same native conversation. Callback forwarding alone cannot pass.

The separate runner independently caps the batch at four sequential Qwen
requests and USD 0.10, stops on the first failure and leaves later cases unrun.
The adapter's offline manifest remains unchanged; separate committed identity
and authorization records carry this experiment's scope. The identity-only CLI
does not read keys, create output or call providers. Only explicit live mode
under the new protocol may use its dedicated process credential. Occupied output
is rejected and no old batch is retried, resumed or given a replacement budget.

Parsed usage is preserved even if a later gate fails. Non-200 or unreadable
responses may leave usage unknown: retain the reservation and stop, not zero
cost. Case and summary publication occurs after complete flush/fsync/close,
without overwriting existing records. Local single-owner publication is not
power-loss durability, distributed coordination or provider exactly-once.

These easy synthetic controls are a compatibility gate, not independent source
selection accuracy, general semantic support, reader value or production
admission. Raw traces stay local. The [single CQ result](results-2026-09-16-report-evidence-catalog-qwen-canary.md)
passed both mechanical gates in four accounted requests, with estimated usage
cost USD 0.002839152 and reservation consumption USD 0.044597248, not an invoice.
A narrow AI content inspection matched the two synthetic controls; semantic
support remains not_assessed. The batch is closed, without a production API
route or browser control.

## Real saved-report preparation

The separate [RS offline protocol](prereg-2026-09-16-report-evidence-real-saved-offline.md)
prepares one historical live-report snapshot and two new Chinese questions.
All 20 saved sources remain in their original order. The positive task explains
a saved material-level finding; the negative task must read the same nonempty
text before declining an unsupported deployment conclusion. This is a small
developmental pilot, not an unseen accuracy study.

`report_evidence_real_saved_eval.py` binds original report/source/metadata bytes,
questions, projection, configuration, snapshot and catalog. Private reference
labels are bound separately and never enter callback construction. Explicit
scripted callbacks and an intercepted full-wire probe verify delivery only;
the module has no implicit transport, live runner, credential option or route.
Reference review is AI saved-text inspection, not human labels or external
paper verification. Content hashes do not establish ownership or permission.

A real-model run still requires a distinct frozen runner and data authorization
covering the whole visible catalog and any selectable saved window. Neither
CQ's synthetic allowance nor successful offline preparation grants that scope.

## Bounded Qwen compatibility work

The later [real saved-report RS pilot](prereg-2026-09-16-report-evidence-real-saved-qwen.md)
has its own runner and data authorization, not another CQ attempt. It verifies
the exact private packet and rebuilds inputs from originals, separately binds
the current committed import closure, and uses one fixed fresh output location.
Identity-only operation does not read credentials or create output. Live mode
is limited to four sequential requests, two per case, and USD 0.10; a known
first-response failure prevents the next paid request, and any first-case
failure leaves the second case unrun. The original offline manifest remains
unchanged and grants no live authority.

Semantic inspection uses a separate read-only LLM review of available answers
against actually delivered windows, without first seeing reference labels.
This is not human expert validation, source truth or independent gold accuracy.
Mechanical results and runtime semantic states remain unchanged by that
post-hoc judgment. No additional project-provider judging call is authorized.

The [Qwen canary protocol](prereg-2026-09-14-report-evidence-followup-qwen.md)
defines two synthetic controls and one shared allowance: six sequential requests,
USD 0.10 soft stop, exact `qwen3.5-plus`, no retry or supplemental search.
It uses only the dedicated DashScope key and the official Beijing destination,
independently of the ordinary pipeline's selected provider. Global credentials,
model configuration and `.env` are not rewritten.

The separate adapter and experiment ledger enforce transport limits and record
request intent before dispatch. Missing usage or an uncertain attempt stops the
batch instead of being estimated as zero. Reported tokens and conservative cost
estimates are separate from the provider invoice. An occupied output cannot be
reused. This local, single-owner experiment ledger is not the application's
shared paid-admission service or a customer receipt system.

No real saved report is read by the canary. Its fixture identities, source and
dependency hashes must match a committed version before network execution.
The core's delivered evidence means handed to the transport callback; the
network ledger separately records dispatch/response observations. Neither
establishes that the model understood the excerpt.

The [first native observation](results-2026-09-15-report-evidence-followup-qwen-canary.md)
failed the closure gate: Qwen spent both local tool attempts on literal lookups,
then requested a read after the allowance was exhausted. Three replies were
accounted, no final answer was delivered, and the second case was not run.
This is transport evidence, not a successful read-to-answer conversation.

## What is intentionally not connected

- No FastAPI route, browser button, production worker hook or scoring change.
- No production follow-up admission or customer receipt. Local canary accounting
  must not be presented as protection for a public paid endpoint.
- No external retrieval, new source registration, cross-run memory or report
  mutation. The existing v1–v8 source locks and evaluation decisions remain intact.
- No claim of full-text verification, hallucination elimination, independent
  accuracy, user time savings or production-ready Tool Calling.

## Next gates

The [RPQ protocol](prereg-2026-09-18-relation-policy-qwen-canary.md) fixed three
dependent synthetic development controls, not real saved reports. Its
[native batch is closed](results-2026-09-18-relation-policy-qwen-canary.md):
one request returned unavailable without reading the advertised source.
The runner stopped before a second request. No receipt or admitted assessment
exists; label checks are zero and semantic support is not_reviewable.
Next investigate first-stage read admission offline under a new contract.
Forced tool execution, if chosen, must not be called autonomous tool selection.
Do not reuse the occupied batch, old allowances or private real-report material.
The [runner verification record](results-2026-09-18-relation-policy-qwen-runner.md)
separates offline execution, failed test-harness attempts and restored checks.
The dedicated CLI verifies identity by default without key access or HTTP.

The [phase-one protocol](prereg-2026-09-14-report-evidence-followup-phase1.md)
defines offline acceptance and the non-model comparison. The bounded canary
has separate frozen inputs, authorization and failure criteria. A production
release additionally needs ownership, shared paid
admission, accounting, request receipts, safe diagnostics and user-visible
failure states. The experimental library being importable is not that release.
