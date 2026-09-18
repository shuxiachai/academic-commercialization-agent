# Saved-source locator: one selection, code-owned saved text

Registered before implementation on 2026-09-18, from main
`4f41605dd69dadfc8e3c7b70f178d76936778844`. Method identity:
`report_evidence_source_locator_v1`. This is an offline callback contract,
not authorization for native requests, private-data transmission or production.

## Why this scope

The closed [RF observation](results-2026-09-18-read-first-qwen-canary.md)
completed a real read but failed its claim-relation reference. This candidate
does not attempt another relation policy: the selector chooses an existing ID,
and code returns saved text without a generated answer or a second callback.
Source choice remains unverified; a genuine excerpt can still be irrelevant.
The shipped Sources browser remains the no-model alternative.

A fresh local capacity check used the existing snapshot, catalog and reader
over 30 on-disk benchmark source artifacts: 632 sources, 632 catalog entries,
zero omissions/title clips, and 632 exact complete saved-text reads. The maxima
were 24 sources per snapshot, 3,428 canonical ASCII catalog bytes and 1,500 saved
Unicode code points. These are snapshot-qualified capacity facts, not selection
quality, original benchmark identity or a new 30-run model evaluation. No raw
texts were published and no provider was called.

## Interface and invariants

The new module is `academic_agent.report_evidence_source_locator`:

```python
locate_saved_source(snapshot, question, *, selector) -> LocatorResult
render_locator_result(result) -> str
```

Validate and detach the trusted snapshot before use. A question must be a
nonblank string of 1..4,096 code points; preserve its original bytes/characters
in the request, not a normalized rewrite. Invalid construction raises before
callback entry. Reuse the existing metadata-only `build_catalog` without edits:
32 entries, 256 code points per visible title, 6,144 canonical ASCII bytes,
saved-order prefix, explicit omissions and title clipping. Catalog metadata is
untrusted data, not evidence. Never send summaries, URLs, DOI, report references
or reference labels to the selector.

The entire detached callback request includes fixed instructions, the original
question, catalog data and a single native-shaped `read_source(source_id)` tool
declaration with the visible-ID enum. Bound its canonical ASCII JSON to 12 KiB
before entry. This is a callback envelope limit, not a future HTTP-body limit.
Invoke `selector(request)` at most once; an empty snapshot needs no callback.
Do not retry, repair, search, paginate, fall back or enter the old answer loop.

Accept only plain native-shaped assistant data under the existing strict
message/JSON parsers. A single valid visible-ID call may select a source;
offset and length are not model-controlled arguments. Alternatively accept a
no-call content object containing exactly `{"action":"decline"}`, or a
standalone refusal. Discard all assistant prose/refusal text. Reject arbitrary
final answers, duplicate JSON keys, extra arguments, multiple or unknown tools
and IDs outside the offered catalog. A model-supplied citation, reason or
claimed excerpt never becomes displayed saved text.

For an admitted source of at most 1,500 saved code points, call the unchanged
local `read_source(snapshot, id, 0, 1500)` at most once. Longer selected text is
`out_of_scope` without a read; do not silently deliver a prefix as complete.
Build the result from the trusted selected source and the actual local read.
Preserve original whitespace, Unicode, hashes, provenance and saved-text scope.
Missing and blank content cannot become a useful-evidence success. The returned
JSON is data, never interpreted HTML, Markdown or instructions.

## Outcomes and observation limits

Distinguish `excerpt`, `missing_text`, `blank_text`, `no_sources`, `declined`,
`out_of_scope`, `unavailable` and `failed`. Missing means absent/empty saved
text; blank means a whitespace-only saved string. Empty catalog/snapshot is
not a failed read. A declined choice is not a finding of no relevant literature.
Invalid selector contracts fail; selector/read execution errors remain explicit
unavailability. Keep only code-owned reason categories, never raw exceptions or
model explanations. No answer, support/refutation judgment or generated advice
field exists. Selection relevance and semantic support remain not assessed.

The result and JSON renderer expose fixed projections, catalog coverage and
local `callback_entries`, `read_attempts` and `read_completed` facts. Rendering
must revalidate rather than trusting bypass-constructed result models. These
counters are not HTTP counts, provider receipt, a cost ledger, timeout control,
authentication, cryptographic execution attestation or proof of browser display.
The injected callable is a trusted Python boundary, not a sandbox. Tests/demo
use a scripted callback and zero provider work; arbitrary callbacks are not
made network-free by this wrapper.

## Prospective offline acceptance

Use fresh synthetic demonstration data and generated boundary cases, not old
CQ/CLQ/PCQ/RPQ/RF labels or private RS material. The demonstration has no
arguments, file/credential inputs or writes; stdout explicitly says
`scripted_offline`. Its scripted selection is not model inference.

Verify actual callback -> reader -> serialized JSON seams: catalog/question
delivery without saved text, one selected read, no second callback, exact
parsed saved text, and separate decline/missing/blank/error states. Test visible
ID admission, strict response/argument parsing, snapshot/request mutation,
Unicode and exact byte/character bounds, safe diagnostics and immutable inputs.
Inject bypassed visible-ID admission, model text substituted for saved text,
and truncated text masquerading as complete; corresponding positive/boundary
assertions must fail, then pass after exact restoration. Keep these engineering
controls out of semantic-accuracy denominators.

Run baseline/final zero-provider suites, latest Ruff, narrow Pylint and an
independent read-only review. Preserve all frozen modules, fixtures, manifests,
old batch files and runtime entry points. Stop if implementation requires an
old-file change, another callback, expanded reads or production wiring.

## Following gate, not part of this implementation

The old CQ adapter binds its old prompt, schema and final-answer conversation;
it is not a generic first-round adapter for this contract. A future native
boundary must independently bind request identity, full wire size, provider
configuration and usage before new model-quality evaluation. Fresh real-task
selection assessment, applicable data/budget authority and production admission
remain separate gates. This registration supplies none of those permissions.
