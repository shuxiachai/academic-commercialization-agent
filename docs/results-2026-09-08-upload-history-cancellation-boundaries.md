# Upload ingress, history generations and abandoned PDF finalization

Date: 2026-09-08. Base: `f65732b92fd51f92c8cbd0ae81dc951ebb7be91f`.
This is offline boundary maintenance, not a paid canary or a measured production
incident rate. The unchanged baseline passed 2,667 tests and 1,206 subtests.

## Reproduced before changes

- A streaming unauthenticated multipart request with no Content-Length reached
  the parser with 52,429,824 file bytes before returning 401. The endpoint's
  52,428,800-byte file limit occurred after spooling. The audit counted writes
  without persisting that synthetic large payload and blocked provider calls.
- Shipped app/sidebar code let an old A history response overwrite B's newly
  rendered history after the same-page logout fallback and explicit B login.
  The old capability remained clickable. Ordinary out-of-order refreshes also
  reverted the list. This was client delivery, not a server authorization bypass.
- The existing extraction cancellation test correctly retained the paid slot
  through real thread exit, but its raw PDF still existed after exit. It did
  not assert storage cleanup. Stored benchmark reports cannot establish the
  frequency of any of these request/browser races.

## Changed contracts

### Ingress before multipart parsing

A pure-ASGI boundary caps the whole upload at 50 MiB plus 1 MiB of multipart
overhead, checks both declared and received bytes, and rejects malformed length
headers. No Content-Length and understated lengths still meet the receive cap;
extra files share the total. The existing 50 MiB PDF limit remains unchanged.
The original 50 MiB-plus-1 KiB probe fits within the new total overhead allowance:
this is bounded preprocessing, not authentication before every received byte.
Rejected bodies are not drained or copied into another full buffer.

Two process-local preprocessing slots cover parsing and the bounded local copy,
then release before model work. They are not operator daily charges or paid
concurrency slots. A body has a 30-second idle and 120-second total receive
deadline; neither is an LLM timeout. Multipart rejection uses the parser's
file-close exception path and preserves specific 413/408 responses. Upload
capacity has its own 429 code and bilingual client hint. Headerless BYOK remains
supported and still requires its existing body credential validation.

### Identity-bound history delivery

Every refresh captures a generation. Only the latest generation may paint,
including both code-backed and session-backed BYOK history. Logout clears
visible capabilities and invalidates pending reads before opening the gate;
explicit mode selection invalidates them again. Aborting a fetch is not relied
on for correctness. This does not change read-capability or mutation auth rules.

### Thread-owned PDF finalization

An owned shielded thread task now performs extraction, atomic metadata storage
and raw cleanup together. Cancelling its waiter cannot prevent queued cleanup
work from starting or remove the existing in-thread paid reservation. A waiter
already abandoned before its thread starts gets cleanup only, without provider
admission. Shielding is not permission to spend money on abandoned queued work.
A running thread discards an abandoned result. Completion
callbacks retrieve exceptions without logging provider messages or secrets.
Storage errors retain their sanitized 500 contract, distinct from admission
429/503 and provider-output 422. Failed best-effort discard logs its error class
without capability ids, filenames or content instead of silently implying success.

## Verification

HTTP/parser tests exercise streamed and understated lengths, early rejection,
multiple small files, auth preservation, deadline file closure, capacity recovery
and release before model work. No provider is invoked. Cancellation tests cover
queued/running work with successful, provider-error and storage-error outcomes;
the old paid-slot test additionally asserts raw-file removal.

Node tests execute the shipped app, API and sidebar code with delayed replies:
same-session order, code/BYOK identity transitions, and the still-open login gate.
Chromium adds three held history GETs to the existing 12 + 5 + 6 intercepted-POST
journeys. The server remains static-only for composer tests. The independent
read-only browser journey retains zero mutations and external/provider requests.

Nine defects were re-injected separately: missing streaming cap, missing
declared-size rejection, unrestricted parser admission, missing code/BYOK
generation checks, missing logout invalidation, missing thread finalization and
unshielded queued cancellation, and provider admission after queued abandonment.
Every selected regression failed at its intended
assertion; each source SHA-256 was restored. The audit harness initially expected
the literal word AssertionError; pytest's shortened `E assert` output required
correcting that detector, not changing a test. A new test import initially let
local dotenv quota configuration reach older tests; import isolation was corrected
without changing default-quota assertions. Chromium's installed Response.finished
helper left a losing close task; request-finished events now wait without that
orphan task or a warning suppression.

After restoration, the complete Windows/Python 3.12.9 suite passed 2,690 tests
and 1,211 subtests with 88.99% Python coverage (the floor remains 85%). Latest
Ruff, narrow Pylint and both Chromium journeys passed. This is 23 additional
tests relative to the unchanged baseline, not a new model-quality measurement.
All eight PR checks and deployment verification remain release gates; local
results alone are not evidence that production serves this revision. No
assertions were weakened, skips added, or warning policy changed.

## Limits

- This is one-process application resource bounding, not distributed ownership,
  edge protection, a bandwidth guarantee, a stuck native-thread kill, or an
  assertion about Railway's separate ingress settings. Parsing slots do not
  change readiness or the existing paid ledger.
- The transport may deliver one over-limit ASGI chunk before rejection; that
  chunk is not forwarded to the multipart parser. The application cannot stop
  a proxy from buffering bytes before ASGI sees them.
- Cancellation after successful thread finalization can leave bounded derived
  metadata for the normal 24-hour pending-paper retention window. It does not
  leave the raw PDF. Hard process death or inaccessible storage can still leave
  files for maintenance; logged cleanup failure is not proof of deletion.
- History generations are document-local, not global logout or server receipt
  recovery. A previously shared capability cannot be revoked by clearing a list.
- No scoring formula, evidence floor, provider identity, CrewAI version, frozen
  experiment, production Tool Calling gate or paid-retry policy changed. There
  was no paid assessment, destructive online test or manual Railway restart.
