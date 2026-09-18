# Explicit relation-policy Qwen transport: offline wire contract

Registered 2026-09-17 before implementation. Baseline:
`c2384f366715da22015a95c55514c05dab9ab6b5`. This is an independent native
adapter for the frozen [RP callback policy](prereg-2026-09-17-claim-relation-policy.md),
not a live experiment, new data-transfer allowance or production feature.

## Measurement and immutable inputs

The pre-edit full zero-provider suite passed 5,195 tests / 1,448 subtests in
291.45s. A socket-blocked local replay of 30 existing benchmark snapshots /
632 source rows reached 60 RP callbacks. Initial requests were 6,944-7,860
bytes and final requests 7,983-9,876, within 12,288. This measures callback
capacity with one short invented claim and positional first-source reads,
not HTTP, retrieval quality, original calibration identity or model accuracy.
No saved material was transmitted externally.

Freeze the RP module, fixture, references and all older adapters, runners,
protocols and results. RP source SHA-256:
`2c77e90ece7ae37bd59e65fc71df5478d037d8c16966b54f074e0fc85c8a7691`.
RP fixture SHA-256:
`a39622a3f2fd1f40da3d1f112e8d989e78ed25ccef4d369f8b714bde58fadf4c`.
The appended policy has 1,297 UTF-8 bytes and SHA-256:
`61dfb78cb81435850dd8adc9cf9990833a87c75dd756e3f22b18ede5cee14ea4`.
Its synthetic cases are dependent development controls, not held-out trials.
PCQ/CLQ stay closed and failed; no retrospective repair or relabeling.

## Separate implementation and identities

Add `report_evidence_relation_policy_qwen_transport.py` and dedicated tests.
Expose `RelationPolicyQwenLedger(output_dir)`,
`RelationPolicyQwenFollowupTransport(api_key, ledger, *, snapshot, claim)`,
`__call__(self, request, /)` and `relation_policy_qwen_configuration()`.
Compose only via `run_relation_policy_followup(..., callback=transport)`.

Reuse frozen key/HTTP and ledger primitives, canonical encoding, response
projection/usage, stage reply admission and catalog helpers. Own session state,
request admission, full read-result comparison and wire construction in the
new module. Do not wrap/invoke the old claim/catalog adapters, bypass their
ledger checks, mutate globals or patch prompts on the outgoing path. Limited
duplication is preferable to changing a hash-bound predecessor's contract.

Construction binds a detached revalidated snapshot, verbatim 1-4,096-codepoint
claim and fixed policy, whose literal hash is checked. Accept only the exact
new ledger type. Its code-owned manifest names the new transport, policy ID/hash,
claim method, configuration and `live_authorization=False`. Dependency paths
disclose coupling, not attested source hashes, authority or a network sandbox.
One instance is one synchronous single-owner conversation, not concurrent use.

## Admission and delivery seams

The positional callback accepts only an exact dict with exactly
messages/tools/tool_choice. Detach it; do not ignore extra keys. Compare the
complete system against the frozen catalog template with exactly one old/new
claim-contract replacement and one policy append. This template is comparison
only, never message repair. Bind claim and ordered catalog on the first request
as well as the second.

Nonempty initial catalog: exactly three messages, the exact visible-ID
read_source schema and auto choice, no response_format. Empty initial catalog:
three messages, no tools and none choice. After a read: five messages with
the exact accepted native assistant call and paired deterministic tool result,
no tools and none choice. For none stages omit the HTTP tools field and add
JSON Object with the existing ASCII JSON-keyword guard. At most two native
requests and one local visible-ID read; no lookup, search, repair or fallback.

Compare the entire read result computed from trusted snapshot and accepted
arguments, including status, text window, hashes and receipt ID. Reconstruction
is comparison, not another tool read. Preserve missing-text precedence,
Unicode offsets, end-of-text empty windows and whitespace receipts that are
delivered but unusable. Reject forged absence/text/extra fields, boolean integer
substitution, assistant/history changes, second reads and third requests.

Return native final content unchanged. The frozen wrapper still owns strict
four-field parsing and relation/receipt checks. A mechanically valid but
semantically wrong answer remains wrong; never fix its label in Python.
Preserve `PolicyResult.inner`, `PolicyResult.audit` and all unverified flags.
Inner-to-policy delivery, policy-to-callback entry, reserved HTTP intent,
observed response and semantic success are separate observations. In particular,
RP can record a second callback/read while wire refusal prevents that HTTP.

## HTTP, accounting and failure rules

Keep exact qwen3.5-plus and the existing pinned Beijing endpoint; no provider
migration or ambient credential/configuration lookup. Retain non-thinking,
non-streaming, temperature zero, no parallel calls, 512 output tokens, TLS,
no proxies/redirects/retries, 10-second connect and 60-second total bounds.
Limit response bytes to 65,536.

Canonical-encode the complete final HTTP JSON body after stage transformation;
12,288 bytes excludes HTTP headers. Reserve that same body then send that same
immutable encoding. Reserved hash must equal the intercepted HTTP content hash.
The preliminary size check cannot substitute for final JSON-mode admission.

Reuse the frozen 16,384 input-token reservation / USD0.011149312 per request.
The inherited six-request / USD0.10 ledger ceilings are accounting limits,
not current pricing or a live grant. They do not increase two requests per
conversation or authorize running all eight development controls in a batch.

Invalid request or failed reserve: no HTTP. Unknown usage retains reservation
and stops; known usage survives invalid native output. Failed finish preserves
pending intent and observed in-memory usage; no subsequent dispatch. Refuse
raw/escaped key echoes before persisting transcripts and expose only safe
failure categories. Journals containing saved text are private. Native
protocol_accepted does not mean the RP wrapper or semantic assessment passed.

The official [Function Calling guide](https://help.aliyun.com/zh/model-studio/qwen-function-calling)
and [structured-output guide](https://help.aliyun.com/zh/model-studio/qwen-structured-output)
were read on 2026-09-17. Qwen3.5-Plus supports these tools and non-thinking JSON
Object; JSON Object does not guarantee our schema. Newer examples/models do
not justify changing the frozen endpoint/model, or adding automatic repair.

## Offline acceptance and next gate

Exercise real RP, frozen wrappers/tool executor, new adapter, inherited _post
and httpx.MockTransport with explicit fake keys. Do not substitute mocked
adapter callbacks for HTTP delivery. Cover both policies/claim/catalog on wire,
32-ID selection, eight frozen controls without label leakage, all four
relations, absence/empty/whitespace/Unicode and early final/refusal, wrong but
valid semantics, complete history/receipt tampering, exact/+1-byte boundaries,
model/usage/protocol failures, HTTP deadlines/redirect/encoding/size failures,
secrets, persistence failure, limits and detached state.

Reinject only in the new module: policy/system admission omission, first-claim
admission omission, final wire-bound omission, post-reservation wire mutation
and complete read-result comparison omission. Require actual behavioral failures
with valid downstream scripted responses, restore exact source identity, rerun.
Replay existing capacity through intercepted new HTTP separately; no source
content leaves the host and only aggregate measurements are published.

Require focused and full regression, latest Ruff, narrow Pylint, unchanged
frozen hashes and a different read-only strong-tier LLM code reviewer. No
weakened assertions, warning ignores, skips or historical result edits.

This phase adds no CLI, paid executor, real-key access, new model outcome,
production route, merge or deployment. A later bounded native batch needs a
new frozen runner/identity/output and applicable authority; old runners and
occupied allowances cannot be reused. Engineering acceptance is not semantic
accuracy, fresh unseen validation or observed user adoption.

