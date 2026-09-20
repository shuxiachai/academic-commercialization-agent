# Isolated saved-source receipt entry

This entry connects the prepared saved-source controller to a separate HTTP app
and browser. It is not mounted by `api.main`, does not change the original
callback-only lab, and contains no native model adapter or provider credential
discovery. The selector is still disabled by default. Tests inject a scripted
callback and use temporary storage and synthetic access codes.

The [controller contract](saved-source-paid-controller.md) still owns code and
report-owner authorization, shared run/PDF admission, durable intent identity,
physical-thread lifetime and replay against unchanged saved sources. This layer
must not turn an uncertain acknowledgement into another execution.

## HTTP contract

`api.saved_source_receipt_app.create_saved_source_receipt_app` takes explicit
`load_snapshot`, `journal_root`, optional `selector` and `selector_identity`.
It owns one controller and drains it on shutdown. It serves its own page at `/`
and only the new `/receipt-static/` assets. It is not a deployment command or an
instruction to expose this app publicly.

- `POST /api/runs/{run_id}/saved-source-location` accepts exactly one `question`
  string, unchanged, nonblank and at most 4096 Unicode code points. Both a current
  `X-Access-Code` and a valid `Idempotency-Key` are required.
- `GET /api/saved-source-receipts` observes that key with the current code. It
  cannot select, spend again, cancel or resume. Lookup remains available when
  new execution is disabled.
- Queries, duplicate critical headers and ambiguous JSON are rejected. POST
  requires JSON and caps actual streamed body bytes at 64 KiB; GET has no body.
  Credentials and receipt keys do not belong in query strings or error text.
  Ingress has a five-second body-read deadline, not an execution timeout.
  Critical header names/values have an 8 KiB aggregate bound, and the access
  code is limited to 4096 printable ASCII bytes. This is not a server-wide
  request or header limit.
- Successful receipt observations use HTTP 200 for pending, unknown, completed
  and failed states. The complete controller result is preserved, with only
  `receipt_key_sha256` added to bind delivery to the actual requested key.
  `completed` is not a semantic-success flag. Inner locator outcomes remain
  intact, including refusal, missing text, failed and unavailable results.
- The full response is validated before serialization and bounded to 128 KiB.
  A malformed or oversized response is unavailable, not a trimmed result.
  Errors contain only a fixed diagnostic and a fixed error category.

The app uses same-origin checks, no CORS, no cookie authentication, no-store and
restrictive security headers. A valid code does not activate a disabled selector.
The original production run/PDF APIs and their receipt schema remain unchanged.

## Browser intent and recovery

The only sessionStorage record is `{"version":1,"receipt_key":"..."}` under
`saved-source-receipts:v1`. A fresh key uses 256 cryptographically random bits.
The browser must write and read back the exact record before sending POST.
Failure to persist means no new POST. It never stores access codes, questions,
report IDs, source text or responses in browser storage.

Page load and refresh make no automatic request. A saved key blocks new intent.
After entering a fresh code, the user may explicitly query the receipt using GET.
Recovered delivery shows the returned report ID and says that the original
question was not retained. Receipt identity, result shape and delivered text
hash are checked before displaying exact saved text as inert text nodes.

Input/code changes and reset invalidate late replies and clear displayed text;
they neither erase the pending receipt nor cancel server work. A stale 401 cannot
erase a newer code. A pending, unknown, not-found, malformed or transport-failed
observation keeps new POST blocked. Known storage loss/corruption cannot look
like a fresh tab with no outstanding work. A retained in-memory key can still
be explicitly queried if storage subsequently becomes unavailable.

Only a verified terminal observation or explicit expiry can offer ending the
current receipt, with a separate risk acknowledgement. Removal and readback must
both succeed before a new manual intent becomes possible. This is not cancellation
or a refund. There is no automatic resend, retry, polling or provider fallback.

## Verification and limits

Before changes, the complete zero-provider suite passed 6325 tests and 1574
subtests. Read-only measurement of 30 current local registries produced 632
scripted saved-text deliveries; the largest canonical locator JSON was 7770
bytes. This is neither a fresh native result nor attested original benchmark
identity or an all-input bound.

Acceptance requires actual HTTP/controller/journal tests and a real Chromium
journey: withhold a real POST acknowledgement, refresh, enter the code again and
explicitly GET the same receipt. The displayed result must preserve exact saved
text with one actual selector entry and one daily-admission charge. Fault cases
must preserve uncertain intent, safe diagnostics, stale-reply isolation and
the distinction between an attempt, receipt completion and available delivery.

All browser/provider network guards remain in place. The production router must
still lack these new receipt/page routes; a negative-control registration must
make that absence assertion fail. This is single-process engineering verification,
not distributed ownership, provider exactly-once execution, semantic accuracy or
user benefit. Native integration, bounded provider accounting and activation/data
authority remain separate work.

A missing receipt does not establish that an earlier request was free. Even a
pre-claim rejection can therefore leave this conservative page blocked until a
conclusive terminal/expiry observation; it does not offer a resend shortcut.
Deleting tab storage outside the page, losing a browser session or losing the
journal can remove recovery ability. Separate tabs/new keys are separate intents,
not deduplicated copies of the same research question. Local text-hash comparison
checks delivered bytes, not source authenticity or scientific support.

## Observed verification

The new HTTP boundary and existing dependent tests passed 300 targeted cases.
The shipped browser scripts passed 211 Node scenarios plus one actual
ASGI/controller-to-script delivery case (11 pytest entries). These are separate
denominators, not extra provider calls or independent model-accuracy samples.

Real Chromium passed 14 scenarios with one disabled POST, one executed POST and
nine GET requests. The executed POST reached the real controller, journal and
temporary shared admission ledger before its response was discarded. Refresh
made no request; a fresh code and explicit GET recovered the exact 1500-code-point
text. Selector calls and daily-admission charges both remained one. Provider
calls were zero. Wrong-code and stale responses, malformed delivery, bounded GET
timeout, explicit receipt ending and failed storage stayed fail-closed.

Independent review found three test-boundary faults: the production absence
probe omitted the new GET/assets; Playwright's upstream fetch could follow a
redirect outside the browser allowlist; and a busy indicator was mistaken for
arrival of a held response. Optional real-router GET/static negative controls,
zero redirect following with a local zero-target-request check, and explicit
upstream-held DOM signals corrected those faults. CSP was not relaxed; the
original probe's default checks and network/filesystem guards remain intact.

Seven deliberate defect variants each made an assertion fail: wrong receipt
hash, dropped response field, persistence after fetch, accepting another key's
reply, unlocking after a lost acknowledgement, unlocking after a stale reply,
and automatic upstream redirect following. Every variant was restored with a
matching source hash. The final static re-review had no unresolved finding.
All four existing/new Chromium journeys and current Ruff/narrow Pylint passed
again on the reviewed code. These observations do not activate a public route
or establish provider-level exactly-once behavior.

The later [RQ protocol](prereg-2026-09-20-saved-source-receipt-qwen-canary.md)
composes this unchanged factory with a fixed-case native selector in a separate
synthetic runner. It adds no provider configuration or public activation to this
page; its native accounting remains separate from the receipt wire fields.

Final whole-tree regression passed 6,499 tests and 1,578 subtests, compared with
the 6,325/1,574 starting baseline. This local result and the reviewed source
identity precede, rather than replace, cross-platform CI and deployment checks.
