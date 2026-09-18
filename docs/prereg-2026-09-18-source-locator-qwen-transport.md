# Saved-source locator: dedicated single-selection Qwen wire contract

Registered before implementation from `173d6c4e2affb42208adb99956051f2325017ede`.
This is offline adapter preparation, not a live runner, data-transmission grant,
paid allowance or production admission. The existing
[locator contract](prereg-2026-09-18-saved-source-locator.md) stays unchanged.

## Scope and measurement

One metadata-only native selection can request one existing source ID. The
unchanged locator performs its local read and returns code-owned saved text;
there is no second model request or generated answer. Source relevance remains
unassessed. Earlier CQ/CLQ/PCQ/RPQ/RF batches and allowances stay closed.

Before implementation, a fixed-question local inspection of 30 saved source
snapshots (632 sources) found maximum callback/native bodies of 4,867/4,990
canonical ASCII bytes, with zero native bodies above 12,288 bytes. The wire
projection included all fixed model controls below. This is local capacity,
not provider acceptance, arbitrary-question capacity or selection accuracy.
No source text was transmitted and no provider was called.

## Interfaces and identity

Add `report_evidence_source_locator_qwen_transport.py` and its dedicated tests.
`LocatorQwenTransport(api_key, ledger, *, snapshot, question)` binds an explicit
credential, detached validated snapshot and verbatim nonblank question at
construction. It accepts exactly one positional callback dictionary. Rebuild
the expected request with the unchanged locator request/schema helpers and
catalog builder; compare complete canonical structures before reservation.
No caller-supplied system text, model, tools, visible enum or configuration may
replace the bound values. Empty catalogs are not a native-call opportunity.

Configuration fixes `qwen3.5-plus`, the existing DashScope Beijing compatible
endpoint, temperature zero, max_tokens 512, non-thinking, non-streaming,
parallel_tool_calls false and tool_choice auto. Do not force a read or add
response_format to the selection request. Bind the final complete wire bytes,
not just the callback dictionary, to a 12,288-byte limit and the journal hash.
The locator's 12 KiB callback admission does not guarantee the larger native
envelope fits; refuse over-limit bodies rather than rewriting them.

Reuse only the frozen base key validation/one-shot HTTP primitive, usage and
native-message projection helpers, strict JSON parser, bounded secret scanner,
and the locator's request/selection/decline helpers. Document dependency paths;
do not edit old helpers or inherit an older adapter's request/answer loop.
No ambient environment, dotenv, credential lookup, alternate endpoint, SDK
retry, redirect, repair, fallback or new scheduling layer is introduced.

## Single-owner durable intent

Use a dedicated `LocatorQwenLedger(CanaryLedger)`, with a new code-owned scope
manifest written at creation, never an old manifest subsequently overwritten.
Its explicit fresh output directory is created and fsynced by construction;
transport construction itself does not write files or contact a provider.
Reject the old ledger type. Override reservation to enforce one request for
the entire ledger, including sequential transport instances sharing it.
The inherited six-request ceiling must not become this candidate's allowance.

Consume the transport's sole attempt at callback entry. Invalid first input
stops the shared ledger even before any reservation; a new transport cannot
bypass that stop. Persist the complete admitted request and reservation before
possible HTTP dispatch. A failed reservation/fsync means zero dispatch. A
timeout, malformed response or failed finalization never refunds the attempt.
Pending/used/stopped ledgers cannot be resumed or reset. This remains a
single-owner, non-thread-safe local journal, not concurrent/distributed quota
control, a public paid receipt, disk-loss safety or provider exactly-once.

Retain inherited conservative price/reservation arithmetic as engineering
limits, not a new budget or invoice. Record valid reported usage independently
of selection acceptance. Missing or contradictory usage stops the candidate
and remains unknown; an uncertain request is not free. The journal may contain
the question and title/ID catalog and therefore is not a public-safe log.

## Response and diagnostic boundaries

Keep the inherited pinned HTTP primitive: no retries/redirects/environment
proxies, TLS verification, 10-second connect and 60-second overall deadline,
64 KiB raw response cap and identity content encoding. Tests must exercise that
primitive through intercepted HTTP rather than mocking the adapter callback.

Require exact response model, coherent integer token usage, a single projected
assistant message and matching finish reason. Admit only one visible-ID
read_source(source_id) with no nonempty content, strict no-call decline JSON,
or standalone refusal. Reject extra/duplicate arguments, unknown IDs, mixed
prose/tool replies and other final answers without repair. The locator repeats
its own existing checks and alone owns the local read and final projection.

Screen recoverable credential echoes before journaling requests or accepting
replies. Never persist response/error bodies, arbitrary exception text or raw
refusal prose. Retain only fixed safe categories and any validated choice
metadata needed for audit. A returned refusal may remain unchanged in memory;
the locator discards it. Unknown exceptions, including arbitrary messages in
the shared stop exception class, map to code-owned categories without chains.

## Offline acceptance and following gate

Use new synthetic controls with fake keys and intercepted HTTP. Assert the
actual locator -> native bytes -> fsynced intent -> one local read -> JSON
path, including decline, missing, blank and long-text outcomes. Check exact
question/catalog/schema binding, whole-wire size and Unicode, secret-safe
failure paths, usage retained on invalid selection, no second dispatch across
shared ledger instances, and reserve/finalization persistence faults.

Reinject request-identity bypass, reservation-before-dispatch reversal and a
shared-ledger one-request-cap bypass; unchanged boundary tests must fail before
exact restoration. Keep all frozen files/fixtures/results and production entry
points unchanged. Run baseline/final full zero-provider tests, latest Ruff,
narrow Pylint and independent read-only review before merge.

Intercepted HTTP proves wire/journal behavior, not native Qwen compatibility or
selection quality. A future live runner must bind fresh cases, committed source
and dependency identities, a new output location and applicable data/budget
authority. This module does not authorize that run or an online endpoint.
