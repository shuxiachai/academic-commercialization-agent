# Catalog-native Qwen transport: offline wire contract

Registered on 2026-09-16 before implementing the new transport. Baseline:
`886bfd8d141992638053703676d8d424b0d267c7` (PR #150). Scope is offline
implementation and intercepted HTTP validation, not a live batch or rollout.

## Observed boundary and pre-change measurement

The [catalog candidate](results-2026-09-16-report-evidence-catalog.md) exposes
at most 32 saved-source IDs. Frozen stage/final-JSON adapters admit at most five
hit IDs. Passing the catalog through that old contract, silently truncating it,
or widening the frozen validator would misstate prior experiments. JQ, SQ and
FQ remain closed failures; native read plus valid final JSON in one successful
live conversation has not yet been observed.

Baseline regression passed 3943 tests / 1360 subtests in 142.67 seconds.
Before implementation, a local scripted capacity probe used 30 existing source
snapshots (632 rows), the fixed question `Offline metadata capacity probe.`,
and the first visible ID with offset zero and length 1500. It then abstained;
selection was positional, not relevant or model-generated. All 30 conversations
reached two callbacks without refusal. Canonical initial callback bodies plus
the existing fixed provider envelope measured 4957--5873 bytes; final-only
bodies with omitted tools and JSON Object measured 6026--7919 bytes. None
exceeded 12 KiB. This constructed-envelope probe is not the new adapter's
execution, an accuracy result, or a provider request. Existing live/fixture
and original-CSV identity limitations remain. No stored source left the machine.

## New interface and invariants

Add only a separate `report_evidence_catalog_qwen_transport.py` and dedicated
tests; do not edit the frozen core, catalog wrapper, snapshot, older adapters,
runners, fixtures, manifests or historical results. Reuse pinned HTTP and
accounting primitives without calling an old adapter's request builder or
claiming its allowance. Introduce a new transport/configuration/ledger identity
explicitly marked `offline_contract_no_live_authorization`.

The adapter accepts an explicit key, its own ledger type and a trusted snapshot.
Revalidate/detach the snapshot and bind its canonical catalog; imports and
configuration resolve no credentials. It is a single-conversation adapter,
with at most two requests and one permitted local read through the wrapper.
The ledger remains single-owner and is not production paid admission. Its
inherited six-request/USD0.10 accounting ceilings do not authorize this phase
or supersede the two-request conversation limit.

- Admit only the exact ordered visible-ID enum (1--32 entries) on the frozen
  `read_source` schema. No lookup, hidden ID, other tool or schema repair.
- Initial nonempty catalogs use `auto` without response format; empty catalogs
  and read-completed turns use `none`, omit tools, and request JSON Object.
  The strict core final parser and receipt validation remain unchanged.
- Preserve the catalog, question, native assistant call ID, paired local result
  and saved text. Minimal per-instance history/stage validation must reject
  a replaced catalog/question, fake stage, duplicate/repeated read or unrelated
  assistant/tool pair before another reservation. Allow only the wrapper's
  deterministic stage-owned instruction change, not arbitrary history edits.
- Snapshot membership and actual read execution remain wrapper/core duties.
  Metadata is not evidence, serialized consistency is not authenticity, and
  neither transport acceptance nor JSON mode establishes semantic support.
- Keep exact `qwen3.5-plus`, pinned official Beijing destination, non-thinking,
  non-streaming, no parallel calls, 512 output tokens, existing conservative
  price/reservation values, TLS verification, proxy isolation, zero retries,
  no redirects and existing request/response/time limits. Do not migrate to
  a new model or destination shown in current documentation examples.
- The entire final encoded HTTP body must fit 12288 bytes before reservation.
  The journal's request hash and dispatched bytes must match; no post-reservation
  mutation of tools, history or output mode. Callback bounds are not wire bounds.
- Record/describe callback entry, dispatch and response observation distinctly.
  Catalog `forwarded` means entry into the injected callable: a later adapter
  preflight failure does not prove a provider received evidence. A received
  HTTP response also does not prove successful model processing or an answer.
- Preserve observed usage even on invalid replies. Unknown usage remains
  unknown/lower-bound with its reservation, not zero. Any failure prevents
  further dispatch. Failed pre-dispatch persistence must produce zero HTTP
  requests; failed finish leaves unresolved intent and no retry.
- Raw or JSON-escaped credential echoes and private exception content must not
  reach persisted transcripts or diagnostics. Only synthetic keys are used here.

The official [Function Calling guide](https://help.aliyun.com/zh/model-studio/qwen-function-calling)
and [structured-output guide](https://help.aliyun.com/zh/model-studio/qwen-structured-output)
were checked on 2026-09-16. They document tool-result history and JSON Object
with a JSON keyword in system/user messages; non-thinking Qwen3.5-Plus is listed.
These are interface references, not evidence that the pinned destination/model
has executed this new 32-ID conversation. Do not copy their unrestricted loops.

## Prospective offline acceptance

Use invented questions/sources, a synthetic key and httpx.MockTransport at the
HTTP boundary. Exercise the actual catalog wrapper, local executor, adapter,
encoded request and on-disk reservation/finish events, not a mocked callback.

1. With more than five visible IDs (including 32), read a late visible ID and
   finalize with its real receipt. Both actual bodies, IDs, text and hashes agree.
2. Empty catalogs, missing text, partial windows, similar/hostile titles and
   initial abstention retain their distinct states. No title-only citation.
3. Hidden IDs, changed schemas/catalog/history, a reopened read stage and tools
   returned during finalization fail without another paid or local-tool action.
4. Test exact wire byte boundaries, escaping/Unicode and the case where a valid
   callback fits but its full HTTP envelope does not. No allowance inflation.
5. Wrong model, malformed/unknown/contradictory usage, redirects, deadlines,
   oversized/compressed responses, ambient credentials/proxies and persistence
   failures preserve accounting and sanitized failure boundaries.
6. Re-inject at least the five-ID restriction and final-only wire regression;
   actual boundary tests must go red. Also target request-hash or history drift
   if applicable. Restore exact hashes and rerun before reporting a pass.
7. Replay the same local capacity probe through intercepted new HTTP only;
   do not send benchmark data externally or treat scripted answers as quality.
8. Run focused old/new tests, full zero-provider regression, latest Ruff, narrow
   Pylint, offline lock check and independent read-only review. Preserve the 94
   protected code/test/protocol/config/snapshot/historical artifact hashes.

## Stop and next gate

No live request, key read, new runner/fixture allowance, source expansion,
production route, web button, scoring change or CrewAI change is authorized
by this document. Package deployment is not activation. Keep public/private
documentation synchronized without publishing raw reviews or run capabilities.

After this gate, a fresh synthetic fixture and hash-bound runner/configuration
can be registered for a separately bounded live batch under applicable user
authority. Do not rerun a closed batch, spend its remaining calls or combine
its partial successes. Model selection quality, general entailment, real user
value and production payer/ownership controls remain separate unmet gates.
