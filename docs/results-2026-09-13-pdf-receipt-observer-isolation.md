# PDF receipt test observer isolation

Date: 2026-09-13. Starting main: `890bae1154edc544979dbf6e9be97577a13c52d6`.
Scope: a zero-provider test-harness correction, not a production runtime fix.

## Observed incident versus demonstrated mechanism

The [first main-CI attempt](https://github.com/shuxiachai/academic-commercialization-agent/actions/runs/34690118668/attempts/1)
failed on Windows/Python 3.11 in the cancelled-waiter/concurrency case of
`test_actual_pdf_thread_publishes_failure_even_without_waiter`. The assertion
`await asyncio.to_thread(entered.wait, 3)` returned false before receipt checks.
That attempt had 1 failure, 3178 passes, one existing skip and 1249 subtests.
The earlier unchanged-SHA retry passed; neither that retry nor this experiment
establishes the original machine's exact timing cause.

The test queued its blocking observer on the same default executor needed by
the real PDF task. With one worker, the observer is submitted first and holds
the only slot while waiting for work behind itself. Adding a loop-local
single-worker case, without changing implementation or assertions, produced
**10 failures / 10 default-pool passes** across the five failure categories
and cancelled/live waiter combinations. Each failure was the entry assertion,
not evidence of a broken receipt finalizer.

This demonstrates a causal observer dependency under a constrained executor.
The CI log does not show that its default pool had only one available slot.
Thread startup, receipt binding/SQLite work and host scheduling are not separately
timed in that incident; they cannot be assigned a root cause from this result.

## Narrow repair and retained contract

The actual worker now notifies a test-local `asyncio.Event` through
`loop.call_soon_threadsafe`. Waiting happens on the loop and does not consume
an executor slot. Keep both the unmodified default-pool case and the explicit
single-worker case; `asyncio.run` owns that loop's executor shutdown.

The original three-second entry bound, five-second fake-provider release
bound, cleanup polling and HTTP/SQLite assertions remain. The test additionally
requires the waiter to remain unfinished before cancellation. No enlarged pool,
sleep-before-cancel workaround, retry, skip or warning filter is added. Actual
thread execution, cancellation, terminal status/error code, sanitized detail,
raw-file cleanup and absent extraction metadata are still checked.

The [thread-owned failure contract](results-2026-09-11-pdf-numeric-receipt-seams.md)
and `api/main.py` are unchanged. A later entry timeout can still indicate slow
startup or storage and must be investigated, not automatically retried as noise.

## Verification

- Before edits: full offline suite **3180 passed + 1279 subtests**.
- After event isolation: all **20** targeted combinations passed.
- Ten further bounded repetitions passed **200/200** targeted combinations;
  any failure would have stopped the repetition command, not triggered a retry.
- Reinjecting the old blocking observer into the single-worker cancelled
  concurrency case failed again at the original entry assertion.
- Suppressing failure publication after waiter abandonment failed at the real
  HTTP receipt assertion (`pending` instead of `failed`). This proves the new
  synchronization still reaches the behavioral contract, not just a signal.
- Both mutations were restored with exact SHA-256 matches before further
  checks. Full Windows/Python 3.12.9 regression passed **3190 tests + 1282
  subtests**; latest Ruff and narrow Pylint passed. Cross-platform CI and
  release identity are recorded on the delivery PR; these counts do not
  measure production reliability or report accuracy.

No application behavior, scoring formula, provider configuration, frozen
experiment fixture or production Tool Calling mode changes. No model/search
request, paid canary or manual production restart is part of this correction.
This does not establish a production incident rate or eliminate all timing
failures in other tests.
