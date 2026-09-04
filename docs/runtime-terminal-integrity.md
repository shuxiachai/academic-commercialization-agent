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

Both `/api/runs/{id}` and `/api/runs/{id}/progress` expose the same terminal
projection and use its elapsed time. The downloadable `terminal` artifact
contains the full non-secret record.

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

## Remaining boundary

This implementation has zero-network test evidence only. A fresh, separately
authorized paid canary is required after deployment to observe whether the
runtime contract survives real provider execution. That canary is now frozen
in [its pre-registration](prereg-2026-09-04-runtime-terminal-integrity-paid-canary.md)
with a new topic, one root, zero operator retry/resume/cancellation, a USD 0.10
soft stop, and explicit outcome lanes. The protocol authorizes zero provider
calls by itself. A normal completion cannot be used to claim that Reviewer
fallback or external-timeout accounting was observed; either path remains
`not_observed` unless it actually occurs. The consumed earlier 2026-09-04
Decision Context canary must not be rerun or reclassified.

An operating-system or host loss that bypasses both worker cleanup and the API
watchdog can still leave no terminal record. Checkpoints remain the recovery
source in that case; distributed process supervision and exactly-once provider
accounting are outside this single-process Railway design.
