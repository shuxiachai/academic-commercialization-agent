# Saved-source query: isolated Qwen wire contract

Registered before implementation from
`e7747a44919cf31c1c9433ae4c08d6048c9c2524`. This is fake-key, intercepted-HTTP
preparation, not a native evaluation, data-transmission grant, paid allowance
or production activation. The [offline candidate library](saved-source-candidate-search.md)
and all earlier experimental batches remain unchanged.

## Scope and interfaces

Add `saved_source_candidate_query_qwen_transport.py` and focused tests.
`CandidateQueryQwenLedger(output_dir)` explicitly creates a fresh private
journal. `CandidateQueryQwenTransport(api_key, ledger, *, question)` binds an
explicit dedicated credential and question without constructor I/O. Its
`transport(question, policy, /)` callback returns only a new plain query dict
or explicit decline dict accepted by `propose_saved_candidates`.

The adapter receives no snapshot, source catalog, IDs, titles, summaries,
report reference, path or reference labels. Only the verbatim question, fixed
policy, code-owned native encoding instructions and tool/model controls enter
the request. This does not remove private information a user includes in the
question itself. The unchanged wrapper owns snapshot detachment, local search
and candidate JSON. Empty-snapshot suppression belongs to that wrapper, not
an adapter which cannot inspect sources.

There is one model request at most, no second turn with search results, no
automatic `read_source`, and no generated answer or semantic-support judgment.

## Fixed native request

The sole tool is `search_saved_candidates(query)`. Its object schema requires
only a string `query` of 1-256 characters and forbids additional properties.
Local checks also reject whitespace-only strings and non-scalar surrogates.
Use `tool_choice="auto"`, not a forced tool or `required`. Fixed native
instructions clarify that a query proposal belongs in function arguments,
whereas a decline is exactly `{"action":"decline"}` in no-call content.

Keep exact `qwen3.5-plus`, the inherited Beijing HTTPS endpoint, temperature
zero, 512 output tokens, non-thinking, non-streaming and parallel calls
disabled. Omit `response_format`; there is no provider, model or endpoint
fallback, environment lookup or SDK retry. Construct the complete canonical
JSON body with the frozen `_encoded` helper and bind its hash to the bytes
actually passed as HTTP content. Headers and TLS framing are not part of that
body-byte measurement and credentials never enter the journal.

Question admission remains 1-4096 nonblank Unicode scalar characters, without
trimming or repair. Callback question and policy must be exact plain strings
matching the bound question and `QUERY_POLICY`. Enforce the full 12,288-byte
request-body ceiling: a legal 4096-character question can still exceed it
after JSON escaping. Reject rather than truncate, change the model, enlarge
the reservation or silently omit controls. Retain the inherited 16,384 input-
token reservation and separate 64 KiB response ceiling.

## Response admission

Require an exact model identity, coherent integer usage, one assistant choice
and matching finish reason. Admit only:

1. One named tool call, no nonempty content/refusal, strict unique-key arguments
   containing only a valid query, with finish reason `tool_calls`.
2. No tool calls/refusal and strict unique-key content `{"action":"decline"}`,
   with finish reason `stop`.

A standalone provider refusal becomes a safe `provider_refusal` failure, not
a legitimate query-proposal decline. Content-only query JSON is rejected even
if it would be a valid internal callback result: structured text is not proof
of a native function call. Reject wrong tools, multiple calls/choices, duplicate
keys, extra fields, mixed answers, truncation, invalid Unicode and malformed
usage. Do not repair or request another answer. Raw function-argument limits,
the canonical internal proposal's 4 KiB cap, and the full raw-response cap are
separate measurements.

## Durable intent and safe accounting

Reuse only the existing one-shot HTTP primitive, key/strict-JSON/message/usage
validation, bounded secret scanner and accounting/journal primitives. Never
call an older adapter's `__call__`, old runner, fixture loader or batch identity.
List actual source/dependency coupling without pretending that path names are
verified hashes. Do not modify those frozen dependencies.

The new ledger has a code-owned method/transport manifest and explicitly states
`offline_contract_no_live_authorization`. Enforce one reservation over the whole
ledger, including multiple preconstructed transports. The inherited six-call
ceiling and USD 0.10 are not an allowance for this new scope. Frozen rates and
the single-request reservation are engineering estimates, not current prices,
provider guarantees or an invoice.

Bind the explicit key to an in-memory scan guard; unbound reservation and
replacement by a different key are rejected. Scan before request persistence
and before response acceptance, including recoverable escaped echoes and
provider metadata. The guard is not a general secret detector. Persist no
credential/hash, response body, arguments, raw refusal or arbitrary exception
text. The question-bearing request journal is private, not public telemetry.

Consume the attempt at callback entry. Invalid first callback input stops the
shared ledger; pending, used or stopped ledgers cannot be resumed/reset or
rebound to get a fresh attempt. Reserve and fsync before possible POST;
reservation failure means no dispatch. Keep validated reported usage even when
model/query acceptance fails. Unknown usage retains its reservation and stops;
it is not free. Failed finalization retains pending intent and observed usage
in memory, never a successful returned proposal.

The inherited transport verifies TLS, disables retries/redirects/environment
proxies, accepts identity content encoding and uses a 10-second connect and
60-second HTTP deadline. These are not a hard filesystem/callback timeout.
The ledger is a single synchronous owner's journal, not concurrent/distributed
quota, a public receipt, provider exactly-once or power-loss-safe storage; file
fsync is not directory fsync. The scope label does not disable networking if
someone explicitly calls the adapter with a real key.

## Offline acceptance and following gate

Tests must use the actual inherited HTTP primitive with `httpx.MockTransport`,
not replace the outer callback. Assert exact wrapper -> native wire -> fsynced
intent -> plain proposal -> local query -> serialized candidate delivery. Cover
privacy, byte edges, identity drift, strict native-versus-text distinctions,
provider refusal, timeout/HTTP/JSON faults, shared-ledger exhaustion, persistence
failure and retained known/unknown accounting. Verify empty snapshots do not
dispatch and local-search failure cannot repeat an accepted native request.

Reinject at least binding bypass, dispatch-before-reservation and ledger-cap
bypass; the corresponding boundary tests must fail without weakening them.
Run complete baseline/final tests, latest Ruff, narrow Pylint and independent
review. Import/configuration/transport construction must not read ambient keys
or perform I/O; only explicit ledger construction creates its private files.

No CLI, public factory or production registration follows. A later native run
needs fresh frozen cases, source/dependency identities, a separate output and
applicable budget/data authority. Intercepted tests cannot establish native
Qwen compatibility, query relevance or user benefit.

## Vendor reference

The [official Function Calling guide](https://www.alibabacloud.com/help/en/model-studio/qwen-function-calling),
checked 2026-09-26, lists Qwen3.5-Plus support and describes native function
arguments, `auto` selection and non-thinking controls. We deliberately stop
before its optional answer-generation loop. Documentation support does not
verify a particular key/endpoint combination or authorize a live request.
