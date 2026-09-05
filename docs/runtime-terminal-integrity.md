# Runtime terminal integrity and deadline budget

The API's 30-minute watchdog is the final availability boundary for a paid
assessment. It is not a useful timeout for each model request: if Reviewer is
allowed to consume that whole window, the parent can kill the worker after a
validated Writer checkpoint exists but before Reviewer fallback, independent
Scorer execution, usage accounting, and final artifacts are persisted.

This contract adds an earlier provider-call budget and an immutable process
outcome without changing retrieval, prompts, guardrails, scoring, checkpoints,
or the six-node topology.

## Time budget

The API calculates one wall-clock deadline when it launches the subprocess and
passes that deadline plus the public watchdog duration to the worker. The
worker converts the remaining interval to `time.monotonic()` exactly once, so a
later system-clock correction cannot extend paid execution.

Current code-owned policy:

| Boundary | Value | Purpose |
|---|---:|---|
| API hard watchdog | 1,800 seconds | Last-resort process termination; unchanged |
| One provider attempt | 150 seconds | Bounds the OpenAI-compatible transport |
| Reviewer reserve | 240 seconds | Leaves room for validated-draft fallback and Scorer |
| Other paid-node reserve | 60 seconds | Leaves room for usage, audits, status and terminal writes |

Reviewer therefore may not begin an attempt unless its full 150-second window
fits before `hard deadline - 240 seconds`. Other nodes use `hard deadline - 60
seconds`. The existing project retry wrapper is the only retry owner: SDK
retries are set to zero inside API workers, and another visible retry is refused
unless its backoff plus a complete request window still fit. A code-owned
`RunDeadlineExceeded` is not classified as a transport failure and is never
retried.

The 240-second reserve is operational policy, not an SLO. It was selected from
an observed 102-second Writer/Reviewer/Scorer recovery suffix and must be
re-measured before it is changed. A direct CLI invocation has no parent
watchdog, so its runtime budget is explicitly reported as `unbounded_cli`; the
private worker transport setting is removed rather than inherited from a stale
environment.

## Immutable terminal record

`status.json` remains the mutable live projection. Every normal stage update
rewrites it atomically, but it cannot authoritatively report a parent kill: the
worker that owns it has already been stopped.

`outputs/<run_id>/terminal.json` is a smaller write-once record containing:

- terminal state and reason code;
- whether the worker exited itself or the API used terminate/kill;
- timezone-aware start/end timestamps and monotonic elapsed seconds;
- last observed stage and configured hard timeout;
- the last durable usage snapshot plus its accounting state;
- checkpoint and recovery snapshots needed to explain resumability.

The worker writes the record after its final status update for `completed` and
`failed`. The API writes it only after it has stopped a worker for cancellation
or timeout. A byte-equivalent repeat is idempotent; a conflicting second
outcome raises instead of rewriting history. Historical runs without this file
retain their existing derivation rules. An invalid file is exposed as
`terminal.record_state=unreadable`, not silently treated as absent.

With no live process, an unreadable terminal makes the outcome `unknown`;
it cannot fall through to historical done/error/cancellation markers. A valid
terminal remains authoritative even when the live status is damaged, including
when its usage is explicitly unavailable. `status_record_state` distinguishes
absent/readable/unreadable live metadata at both HTTP endpoints. Unknown progress
has `done=false`; history reuses the safe projection instead of reading corrupt
status again. The browser labels the fault, renders unknown elapsed time as a
dash and does not paint stale `Done` stages green. See the
[zero-provider fault verification](results-2026-09-05-runtime-metadata-integrity.md).

Both `/api/runs/{id}` and `/api/runs/{id}/progress` expose the same terminal
projection and use its elapsed time. The browser renders the translated reason
and preserves raw `reason_code` and `termination_method` in an inspection
tooltip. A missing or unreadable immutable record after a terminal state is
explicitly labelled rather than looking like an ordinary clean finish. The
downloadable `terminal` artifact contains the full non-secret record.

## Usage states

Price coverage and temporal accounting are different questions. Existing
`usage.cost_complete` still means every observed model had a known price.
Adjacent `usage_accounting.state` means:

- `complete`: the run completed and its final usage collector succeeded;
- `lower_bound`: a durable snapshot exists, but the run did not complete and a
  provider request may have spent without returning counters;
- `unavailable`: no trustworthy counters are available, including when the
  collector itself failed. This never means zero spend.

Each completed Crew node takes a cumulative usage snapshot. Parallel callbacks
are serialized, and per-agent counters merge monotonically so a late provider
counter update cannot erase a larger value already on disk. A timeout or
cancellation copies the last snapshot into `terminal.json` as a lower bound;
the browser labels it as partial. If no snapshot exists, the browser says
`usage unavailable` rather than showing an empty or zero bill.

This is still at-least-once cost observability. No local process can prove
whether a provider accepted a request whose response never returned. The
in-flight flag preserves that uncertainty instead of fabricating an exact
total.

## Reviewer deadline behavior

Deadline exhaustion enters the existing narrow Reviewer recovery path. It is
eligible only when Writer has a validated output and neither Reviewer nor
Scorer has completed. The unchanged Writer draft is delivered with an explicit
`quality_review.status=fallback`, while Scorer executes independently under its
own guardrail and earlier deadline. A Writer failure or Scorer failure still
fails the run.

## Production observation and remaining boundary

The first separately authorized canary never crossed admission. Its preflight
confirmed the deployed revision, readiness, API schemas, accounting branches,
and access boundary, then found that the browser did not consume terminal
reason or method. It stopped before the paid POST with zero roots, zero
provider/search requests, and USD 0.00 observed cost. See the
[zero-request preflight result](results-2026-09-04-runtime-terminal-integrity-paid-canary-preflight.md).

The browser seam is covered by both shipped-JavaScript tests and a real loopback
Chromium journey whose on-disk fixture contains a valid immutable terminal
record. A replacement study was frozen in the
[post-browser-seam pre-registration](prereg-2026-09-04-runtime-terminal-integrity-post-browser-seam-paid-canary.md)
under a new RTI02 identity.

One separately authorized root then completed on exact deployed revision
`522094a4330133c33aba2c3059bfd646be80b792`. The schema-1 terminal record,
status, progress, and real browser agreed on `completed`,
`worker_completed`, `worker_exit`, timezone-aware timestamps, 885 seconds,
and the 1,800-second timeout. Six `qwen3.5-plus` requests used 69,932 tokens
with a complete USD 0.067922 estimate. All seven checkpoints committed,
Reviewer passed, every observed cumulative counter was nondecreasing, and the
orientation gate remained non-binding. The browser visibly rendered
`worker completed` and preserved the raw reason and method in its tooltip.
The primary gate passed 12/12. See the
[paid result](results-2026-09-04-runtime-terminal-integrity-post-browser-seam-paid-canary.md).

The observer also records a minor protocol deviation rather than hiding it:
two of 88 read-only polling intervals were 9.984 seconds, 16 milliseconds
earlier than the frozen ten-second minimum. It did not change provider work,
cost, or any primary assertion. RTI02 is consumed and must not be rerun to
erase that qualifier.

This normal completion still cannot validate Reviewer fallback or external-
timeout accounting; either path remains `not_observed` unless it actually
occurs. It establishes no latency SLO: this run took 885 seconds while an
earlier Qwen completion took 306 seconds. The consumed earlier 2026-09-04
Decision Context canary must not be rerun or reclassified.

An operating-system or host loss that bypasses both worker cleanup and the API
watchdog can still leave no terminal record. Checkpoints remain the recovery
source in that case; distributed process supervision and exactly-once provider
accounting are outside this single-process Railway design.
