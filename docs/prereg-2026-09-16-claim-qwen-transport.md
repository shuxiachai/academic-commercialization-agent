# Claim-relative Qwen transport: offline wire contract

Registered 2026-09-16 before implementation. Baseline commit:
`3de54f29bbc43eaf429be51f43ec6499bc7d2388`. This phase implements a native
transport for the [claim-relative callback contract](prereg-2026-09-16-followup-claim-relation.md),
not a provider run, historical-label amendment or production route.

## Measurement and design

Before edits the complete zero-provider suite passed 4,637 tests / 1,401
subtests in 269.19 seconds. A local capacity probe projected 30 saved benchmark
snapshots (632 sources), used the same synthetic proposition, selected the first
visible ID positionally, read at most 1,500 code points, and returned scripted
insufficiency/unavailability. All 30 reached two callbacks and abstained.
Constructed provider bodies measured 5,769--6,685 bytes initially and
6,823--8,716 bytes finally; none exceeded 12,288. This is not execution of the
new adapter or model quality. No saved material left the machine, and current
disk projections do not establish historical CSV identity or source truth.

Add `report_evidence_claim_qwen_transport.py` and focused tests only. Preserve
all frozen claim/catalog/core/snapshot/provider code, old tests, manifests,
runners and results. Use an independent session implementation; do not wrap
the old catalog request builder, bypass its ledger type guard or mutate module
globals. Reuse only pinned credential/HTTP/accounting and validation primitives.

Interfaces: `ClaimQwenLedger(output_dir)`,
`ClaimQwenFollowupTransport(api_key, ledger, *, snapshot, claim)` and its
`messages/tools/tool_choice` callback. Construction detaches/revalidates the
trusted snapshot and binds the caller's verbatim claim, including the first
request. Only the new ledger type is admissible. Its manifest has a distinct
transport identity, claim method identity and `live_authorization=False`.
Dependency paths disclose coupling, not verified hash identities or authority.

## Frozen boundaries

- Preserve the exact ordered catalog and visible-ID tool schema, full assistant
  call/arguments/ID and complete deterministic local read result. A forged
  text window, absence, history or first-turn claim fails before reservation.
  Expected result reconstruction is comparison, never a second read.
- At most two HTTP requests and one visible-ID read. Nonempty initial catalogs
  use auto tools without response format; empty/read-completed stages omit
  tools, use `none` and JSON Object. No lookup, search, retry, repair or fallback.
- Return the native four-field final content unchanged. The claim wrapper owns
  strict parsing, relation/receipt consistency and code-derived delivery. The
  transport neither rewrites relations nor verifies semantic entailment.
- Match only the expected claim-contract system texts; build comparison text
  from frozen helpers without repairing caller messages. Snapshot/title text
  remains untrusted data. Metadata is not evidence or publisher full text.
- Exact `qwen3.5-plus`, pinned Beijing endpoint, non-thinking/non-streaming,
  no parallel calls, temperature zero, 512 output tokens, TLS verification,
  no ambient proxies/keys, redirects or retries. No provider/model migration.
- Check the complete final encoded HTTP body against 12,288 bytes before
  reserve; journal request hash must equal the actual dispatched bytes. Retain
  the 65,536-byte response, 10-second connect and 60-second total bounds.
- Reuse frozen input reservation 16,384 tokens and USD 0.011149312 per call.
  The inherited ledger's six-request/USD0.10 ceiling is not new live allowance;
  it cannot supersede two requests per conversation or grant data transmission.
- Known usage survives invalid replies; unknown usage retains reservation and
  stops further dispatch. Failed reservation persistence produces no HTTP;
  failed finish leaves unresolved intent. Callback entry, HTTP dispatch,
  observed response and semantic success remain distinct. A wrapper failure
  must be handled as failure by any future runner, not as a passed ledger row.
- Scan raw and escaped credential echoes before persistence; no private
  exception details. Future real-data journals are private even if hash-bound.

The official [Function Calling guide](https://help.aliyun.com/zh/model-studio/qwen-function-calling)
and [structured-output guide](https://help.aliyun.com/zh/model-studio/qwen-structured-output)
were checked on 2026-09-16. They describe native tool-result history and JSON
Object for non-thinking Qwen3.5-Plus, requiring a JSON keyword but not guaranteeing
our schema. Current examples do not authorize endpoint/model changes or loops.

## Offline acceptance and next gate

Use invented controls, explicit fake keys and `httpx.MockTransport` at HTTP,
not a mocked adapter callback. Cover four relations/positive-negative claims,
32-ID selection, unavailable/whitespace reads, exact serialized declarations,
all history/schema/receipt tampering, response/model/usage errors, raw/escaped
secrets, persistence failure and callback-versus-wire byte boundaries.

Reinject at least first-claim admission loss, final wire-bound loss and a
post-reservation wire mutation; require targeted red assertions and exact source
restoration. Also cover full-result checks rather than hash-only acceptance.
Repeat the local capacity probe through intercepted new HTTP, without external
requests or quality claims. Require focused/full regression, latest Ruff,
narrow Pylint, unchanged frozen bytes and independent read-only LLM review.

This phase adds no CLI, live fixture/runner, real-key read, production hook or
private-result publication. Future semantic review follows the
[LLM-only policy](llm-review-policy.md); no human sign-off gate is introduced.
After this engineering gate, a new bounded native batch requires its own frozen
identity and applicable authority. Closed CQ/RS allowances and results are not
reused, and structural success is not semantic accuracy or user adoption.
