# Maintenance: supervisor, native PDF, paid acknowledgement and export cache

Date: 2026-09-06. Starting revision: `5acb80a4280f65c560851b0f446a88f63adf62da`.
The starting zero-provider suite passed 2,323 tests and 1,161 subtests.
These defects were reproduced locally before edits; this is not a paid experiment
or evidence of observed production crashes, billing loss or incident frequency.

## Findings and changes, in maintenance order

1. A root enumeration `PermissionError` escaped paper/run pruning and stopped
   the shared reaper. Awaiting that already-failed task at shutdown also skipped
   worker termination. Independent supervised stages now retain explicit
   `not_checked`/`ok`/`failed` observations and logs, and subsequent cycles still
   enforce timeouts. `/health` exposes task liveness/degradation/death; managed
   watchdog death or a failed timeout stage fails readiness, while retention
   failure alone does not restart paid work. Shutdown cleanup is in `finally`.
   Expected process-stop errors no longer abandon the rest of a batch; timeout
   handles whose stop failed are restored for later supervision and accounting.
2. Two legitimately admitted PDF extractions could enter the native parser
   concurrently. PDFium explicitly disallows this even for different documents
   ([primary library contract](https://pypdfium2.readthedocs.io/en/stable/python_api.html)).
   A process-wide lock now encloses parsing and explicit child-handle closure,
   including exception paths. It does not enclose downstream LLM work. The
   concurrency test uses instrumented handles and real paid admission rather
   than attempting to crash a real native library. Existing generated-real-PDF
   extraction tests continue to cover actual page selection and text output.
3. A real 202 followed by `sessionStorage` quota failure used to remain on the
   composer and look like failed submission. Optional history persistence now
   cannot discard accepted root/child navigation; the UI asks users to save the
   capability URL. Parent-keyed pending resume state survives button replacement.
   Lost transport or truncated success bodies are explicitly unknown paid
   acknowledgements, not definite rejection; no automatic retry was added.
4. A renderer writing some final-path bytes before raising produced a 500,
   followed by a cached 200 serving those bytes. Rendering now publishes a
   unique sibling only after success, preserving any existing complete cache
   on failure. A bounded set of per-run striped locks coalesces simultaneous
   first downloads. An obvious legacy torn cache is regenerated using a narrow
   header/trailer check, not a claim of complete PDF validation.

## Verification

HTTP boundary tests cover maintenance health/readiness, shutdown after task
death, sequential PDF failure/retry and concurrent first downloads. Node tests
execute shipped handlers and fetch/storage code for both accepted roots and
children, resume re-renders, storage faults and ambiguous paid responses.
The old recovery-history test asserted a particular inline source string; it
was replaced with actual stored child identity and navigation assertions, not
weakened to accept the new helper's spelling.

Eight original-defect re-injections target cleanup escape, skipped shutdown,
unlocked native calls, lost accepted navigation, duplicate resume, hidden unknown
acknowledgement, direct partial PDF publication and duplicate PDF builds.
Each must fail its intended regression; restored file bytes are SHA-256 checked.
The reinjection harness initially needed a more specific reverse-patch context.
The duplicate-export mutation also caused a Windows replacement/share failure;
the existing call-count assertion was moved before HTTP-success assertions to
identify the duplicate build first, retaining both assertions.

Two real Chromium journeys retain zero external/provider calls. The extended
composer journey fulfills ten synthetic POSTs in a static-only fixture and
asserts zero API requests reaching the server, unexpected requests and page
errors. The separate read-only ASGI journey remains unchanged.

After restoration and document-index repair, the full suite passed **2,341
tests and 1,166 subtests**. Local Windows/Python 3.12 coverage measured **88.63%**
against the unchanged 85% floor. Latest Ruff and narrow Pylint passed; both
Chromium journeys passed again. These are local revision-specific figures,
not CI measurements, report accuracy or a live-provider result.

## Limits and unchanged decisions

- No scoring formula, evidence rule, CrewAI version, provider identity, frozen
  experiment or production Tool Calling gate changed. Shadow mode remains zero-call.
- The reaper is still a single-process periodic supervisor. This is not a
  distributed ownership design, a hard real-time deadline or a stuck-thread kill.
  Its successful cleanup call is not proof every artifact was deletable.
- Tab-local exclusion is not durable request idempotency. Refreshes, other tabs
  and lost acknowledgements remain distinct boundaries; BYOK may lack server
  history and an unreceived run capability cannot be reconstructed here.
- Cache locks are process-local; striped collisions only serialize other exports.
  A hard process crash can leave a temporary sibling, never a newly partial final
  cache. Legacy header/trailer checks cannot detect all malformed PDFs, stale
  semantic content or concurrent deletion after a download begins.
- No paid assessment, provider call, production restart, new quality estimate,
  monetary-savings percentage or long-term SLO measurement was performed.
