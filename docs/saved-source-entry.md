# Isolated saved-source entry: callback and browser contract

This is a separate application factory, not a route in `api.main`, a Railway
feature flag, a native provider adapter or production Tool Calling. Its default
selector is disabled. Tests inject deterministic callbacks; an arbitrary
injected Python callable is trusted code, not sandboxed or automatically
network-free. No provider credentials are accepted or discovered here.

## Why this boundary is separate

The SLCQ development batch demonstrated six native title selections but no
saved-text delivery on its public-title input. This entry verifies a different
seam: bounded saved JSON -> detached snapshot -> one selector/local read ->
complete HTTP JSON -> inert visible text. It does not re-open a closed canary,
add evidence, generate an answer or validate scientific claims.

Before editing at `b53fcbce08a1248f195d0a7c696b13a3553b825c`, local inspection
found 30 current source registries / 632 nonempty saved texts, all at most 1500
Unicode code points. Files were at most 66,453 bytes, catalogs 19-24 sources.
Prescribed-ID callbacks delivered all 632 texts exactly with no catalog omissions
or clipped titles (largest catalog 3,428 ASCII bytes). These current local
snapshots are not attested original benchmark identities; this was scripted
delivery, not model selection, HTTP/browser evidence or a paid run.

The existing paid journal only admits run/resume/paper operations and their
specific saved responses. Do not extend its whitelist or counterfeit one of
those types for this entry. **Paid quota, billing, persistent locator receipts
and BYOK integration are not implemented.** A local occupancy guard is not a
paid allowance, token budget or duplicate-intent journal.

## Loader and HTTP interface

New `academic_agent.saved_source_loader` projects bounded UTF-8 JSON directly;
do not call live EvidenceSource validators, fetch URLs or repair metadata.
Its byte projector accepts a server-owned report reference; its filesystem
loader binds a server-owned root and one strict run ID, reads only
`validated_sources.json`, rejects indirect/escaping paths and caps actual reads
at 1 MiB before JSON parsing. Preserve stored strings, dates and None/empty/blank
text; malformed/duplicate source identities or malformed groups are unavailable,
not a silently shortened candidate set. Missing registry and unreadable/corrupt/
oversized registry remain distinct safe exceptions. There are no report writes.

New `api.saved_source_app.create_saved_source_app(*, load_snapshot, selector=None)`
returns an independent FastAPI app, with no module-level app or environment
switch. `api.main` must not import, mount or advertise it. The factory serves
only its new `web/saved-source-lab/` page/assets and the one operation below.
There is no list/history, mutation, key lookup or native transport import.

`POST /api/runs/{run_id}/saved-source-location` accepts exactly
`{"question": "..."}`. Preserve the question verbatim, require a nonblank string
of at most 4096 code points, reject extra fields (including model, endpoint,
credentials and prescribed source ID) and cap actual streamed body bytes at
64 KiB. Do not rely only on Content-Length or echo validation input.

The run ID retains the existing **read-capability** meaning, not an owner/admin
paid credential. No code header grants extra rights or selects a payer.
A missing selector yields `503 / selector_disabled` before registry access;
a valid capability cannot enable a selector or provider.

Successful domain responses (including missing/blank/out-of-scope/declined/no
sources) are HTTP 200 with this complete envelope:

```json
{
  "schema_version": 1,
  "selector_mode": "injected_callback",
  "billing_integration": "not_implemented",
  "result": {}
}
```

`result` is the full validated serialized frozen LocatorResult object, not an
arbitrary dict, quoted JSON or generated answer. Do not silently drop fields.
The unchanged locator owns the at-most-one full saved-text read (1500 code
points maximum) and distinct outcome states. Titles are not evidence.

Errors use fixed `detail` and `error_code` strings, never user content, path,
raw exception or rejected projection: 404 missing; 413 body too large; 422 invalid
request; 429 `locator_busy`; 502 selector contract failure; 503 disabled, closing,
saved-source unavailable or execution unavailable. All replies use no-store.
No CORS or credential persistence is introduced; same-origin CSP, no framing and
nosniff protect the separate page. This is not a newly hardened production API.

## Execution ownership and lifecycle

At most one operation executes per app instance. A nonblocking slot inside the
actual synchronous worker covers loader, selector, read and serialization;
overlapping work returns `429 / locator_busy` without another callback.
The worker's finally releases it. Cancelling/disconnecting an HTTP waiter cannot
free a still-running thread, start replacement work or trigger a retry.

Shutdown atomically marks closing, rejects new work with
`503 / locator_closing`, and asynchronously waits for the actual worker to
exit. Do not block the ASGI loop while waiting. A permanently stuck trusted
callback cannot be safely killed, so no bounded shutdown or distributed
ownership is claimed. Tests coordinate events, not arbitrary sleeps.

## Browser and verification cutline

Only new assets are used; existing hashed result.js/i18n.js/harnesses remain
unchanged. The page prominently says isolated/injected callback, billing not
implemented, not source-truth validation. No automatic submission, retry,
polling, provider key or persistent browser storage is allowed.

Render source metadata and exact saved text with inert text nodes/preformatted
whitespace, never markdown or innerHTML. Show all distinct domain states,
catalog coverage and explicit semantic-not-assessed status. Validate response
shape; missing or malformed data must not look like empty evidence. Input/reset
changes invalidate earlier replies; do not show one report's late response under
another report ID. A failed request cannot leave a stale excerpt looking current.

Tests exercise actual loader/locator/HTTP serialization and a real Chromium
journey with fixture data and deterministic selector injection. Block all
external browser/HTTP provider traffic. Cover default-off and absent production
route, traversal/indirection/byte bounds, field preservation, hostile strings,
no silent text clipping, no metadata leak in errors, occupied/cancelled/shutdown
seams, and stale browser responses. Reinject concrete boundary defects and
require unchanged tests to fail; then restore exact source.

Full before/after zero-provider tests, latest Ruff, narrow Pylint, existing
browser journeys and the new dedicated smoke remain required. CI adds a new
step without weakening existing jobs. Only after independent review and green
CI may this inert preparation merge/deploy. Any later native integration needs
an explicit production adapter with shared paid admission, durable receipts,
fresh credential isolation and separate activation/data authority.
