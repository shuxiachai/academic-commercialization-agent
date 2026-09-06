# Keep synchronous maintenance off the ASGI loop without losing ownership

Date: 2026-09-06. Base: `db6e27c9cea158df529ab99ceaede35507528d13`.
Zero-provider maintenance; no paid canary or observed production outage claim.

## Before changing code

The unmodified suite passed 2,362 tests and 1,171 subtests. A read-only census
found 109 direct timestamped run directories and the 30 benchmark reports.
These artifacts do not capture event-loop scheduling or probe latency; they
cannot establish how often a watchdog wait stalled a real production request.
No retained report or frozen experiment was rerun or modified.

The async reaper directly invoked synchronous process waits and directory
cleanup. Releasing the registry lock around termination had fixed capacity
ownership, but it did not release the ASGI event loop. Three new tests held
the timeout, paper and retention callbacks in turn. Each original-code test
failed because four HTTP requests could not finish within an independent
observer's five-second bound. An asyncio-only timeout was rejected: that timer
would also be unable to run while the loop was blocked.

## Change and rejected alternatives

Each stage runs via `asyncio.to_thread`, still serially and with a single active
stage. Completed observations and logs are applied back on the loop; a running
stage does not become `ok` merely because it was dispatched. A stage fault
remains isolated and visible, and later stages/cycles still run normally.

Plain offloading is not enough. Cancelling a `to_thread` await does not stop
the native thread. Without explicit ownership, lifespan shutdown could call
`shutdown_all` while the abandoned watchdog still owned a process stop and
terminal write. A strongly referenced, shielded stage task drains before
cancellation propagates. Repeated cancellation of either the supervisor or its
lifespan waiter must not break that drain. Cancellation then stops the cycle;
it does not dispatch the next cleanup. Ordinary exceptions that settle during
drain retain the same failed observation/log instead of disappearing.

No fire-and-forget cleanup batch, additional worker replica, process ownership
redesign, provider call or production restart was introduced. The existing
shutdown fallback still executes after supervisor failure. Readiness's timeout
failure versus cleanup-only advisory distinction is unchanged.

## Verification

Nineteen new cases exercise:

- four real ASGI GET responses before releasing each of three held stages:
  health, readiness, retained-run status and progress;
- twelve success/failure, stage and cancellation-target combinations, with
  repeated cancellation, no next-stage dispatch and shutdown ordered last;
- two real registry/stop-claim/terminal-writer paths around a simulated process,
  including a denied first stop that shutdown must subsequently take over;
- idle shutdown with no cleanup dispatch, and ordered cycles whose timeout
  failures remain HTTP 503 without exposing internal diagnostics.

The held-stage post-fix sample returned all four HTTP responses in 0.000–0.016
seconds (rounded local monotonic readings). The assertion is completion before
release, not a claimed zero latency or a production SLO. Processes in these new
tests are fakes, but the stop ownership and terminal writer are real; earlier
real-child stop tests continue to run unchanged.

Four independent re-injections cover direct loop blocking, an unshielded stage,
abandoned drain and premature success publication. Each must fail its intended
assertion and restore the exact production-file SHA-256. The temporary harness
needed a unique reverse-patch context for the drain; that was corrected before
the complete verification was repeated. No assertions or warning policy changed.

All four re-injections failed at their intended seams and were restored. The
complete local Windows/Python 3.12 suite passed 2,381 tests and 1,176 subtests;
fresh coverage was 88.72% against the unchanged 85% floor. Latest Ruff and
narrow Pylint passed. Both real Chromium journeys passed: the read-only journey
observed zero external requests, mutations or page/console errors; the composer
intercepted ten simulated POSTs, with zero API requests reaching its static
server and zero unexpected requests. Neither journey called a paid provider.

## Limits

This removes one reproduced scheduling blocker, not every possible blocking
API handler, executor saturation, dead filesystem or CPU-bound workload. Stages
remain serial: a stuck cleanup can still delay the next watchdog cycle. A last
successful observation is not a measured freshness/SLO guarantee.

Python cannot forcibly stop a filesystem thread. Graceful shutdown drains owned
work and therefore has no new finite shutdown-time guarantee; forced process or
host loss can bypass it. This is not distributed supervision, exact-once billing,
provider cancellation/refund, improved report accuracy or live fault evidence.
Scoring, providers, CrewAI, checkpoint identities and all frozen Tool Calling
protocols remain unchanged; production supplementary retrieval is zero-call shadow.
