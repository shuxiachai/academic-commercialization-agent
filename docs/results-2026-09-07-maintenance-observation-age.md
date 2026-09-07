# Time-qualified maintenance observations at both health endpoints

Date: 2026-09-07. Base: `19719798ae35d8505e007980fa9e20933febdc2f`.
Zero-provider maintenance, not a new freshness policy or production SLO.

## Starting evidence

The unmodified suite passed 2,381 tests and 1,176 subtests. The retained cohort
still contains 109 direct timestamped run directories and 30 benchmark reports.
Those files do not contain the process-local maintenance observation clock;
they cannot establish the age of a live watchdog's last result or how often
an operator has misread it. No benchmark, provider call or retained run changed.

The health payload exposed only the last `ok`/`failed`/`not_checked` result, and
the readiness payload omitted the maintenance snapshot entirely. Three new
HTTP regressions first failed at that missing readiness projection. A frozen
clock then makes the important distinction testable without waiting an hour:
polling an hour after completion must retain its result and timestamp, but
report an age of 3,600 seconds rather than manufacturing another fresh check.

## Contract

`/health.maintenance` and `/health/ready.maintenance` share the same typed
projection. Separate requests have separate snapshot times; equality tests
freeze the clock deliberately, not because real responses must be identical.
Existing state, checks and HTTP status rules remain compatible.

| Field | Meaning |
|---|---|
| `observed_at` | UTC time this snapshot was taken, not when maintenance completed |
| `checks[name]` | Last completed result for that stage, not a current freshness verdict |
| `timings[name].current_started_at` | UTC dispatch time of an attempt without a completed observation; null when none is retained |
| `current_elapsed_seconds` | Monotonic dispatch-to-snapshot interval, including queueing and drain; null without an unfinished attempt |
| `last_started_at`, `last_finished_at` | UTC start/completion labels of the last completed attempt |
| `last_duration_seconds` | Monotonic dispatch-to-observed-completion duration |
| `last_finished_age_seconds` | Monotonic age of that last completed result, whether success or failure |

Unknown completion facts are null, never a zero duration or a passing check.
A zero age is valid only immediately after a completed observation. Starting
another attempt preserves the previous result and its clock pair; cancellation
drain does not refresh those completed facts. On success or ordinary failure,
completion is published with its matching clocks and the current attempt clears.
Failure in one stage neither refreshes nor clears another stage's observations.
Supervisor death stays a failed/stopped supervisor even beside a past `ok`.

Short process-local locking pairs results and immutable clock records for
threaded HTTP readers. It does not enclose provider work, filesystem operations
or process waits. UTC labels support inspection; monotonic anchors measure
durations and ages and never leave the process. A wall-clock adjustment can
make UTC labels appear reordered without creating negative durations or
artificial freshness. A new managed lifespan discards the old clock anchors.

The standalone configuration-only `readiness()` does not acquire an ASGI
supervisor requirement and leaves `maintenance` null. The HTTP wrapper adds
the explicit managed or `not_started` snapshot. A failed timeout stage or
dead supervisor still returns 503; an old success alone does not introduce
a new failure threshold. A cleanup-only failure remains advisory.

## Verification

Twenty-four new cases cover ageing completed results, preservation of both old
success and old failure while a subsequent success/failure is draining, first
in-flight attempts, UTC jumps in either direction, lifecycle reset, supervisor
death and the public schema. Assertions cross actual health/readiness HTTP
responses and OpenAPI, not only an in-memory field. Clocks are locally frozen;
the real asyncio scheduler is not patched. Existing cancellation-drain,
stop-ownership and readiness tests remain active without relaxed assertions.

Five defect re-injections target a lost readiness snapshot, wall-clock-derived
age, polling that resets age, dispatch that discards previous completion, and
a new lifespan that keeps old clock anchors. Each must fail its intended seam
and restore the exact production-file SHA-256 before further verification.

All five re-injections failed at their intended seams and restored the exact
file hash. The final local Windows/Python 3.12 suite passed 2,405 tests and
1,181 subtests, with fresh coverage of 88.76% above the unchanged 85% floor.
Latest Ruff, narrow Pylint and both real Chromium journeys passed. The read-only
journey recorded zero external requests, mutations and page/console errors;
the composer intercepted ten simulated POSTs with zero API requests reaching
its static server, unexpected requests or paid-provider calls. No warning
filter was relaxed and no existing test was skipped.

## Limits and rejected shortcuts

There is no measured safe freshness cutoff, so this adds observation facts,
not an invented stale threshold, automatic cancellation, restart or readiness
eviction. Operators can inspect age alongside current elapsed time and task
state; this is not a browser dashboard or an alerting/SLO implementation.
The nominal reaper sleep interval is not a maximum interval between checks:
stages remain serial, and stuck cleanup may delay the next cycle and graceful
shutdown. Forced process loss may leave no final observation. Nothing here
establishes provider connectivity, source truth, report accuracy, distributed
ownership or lower billing. Scoring and frozen experiments are unchanged;
production supplementary Tool Calling remains zero-call shadow mode.
