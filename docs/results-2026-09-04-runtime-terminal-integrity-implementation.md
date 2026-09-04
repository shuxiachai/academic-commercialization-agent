# Runtime terminal integrity P0 — implementation result

Date: 2026-09-04
Scope: zero-network implementation and regression validation
Production provider calls: none

## Trigger

The separately pre-registered Decision Context canary reached a validated
Writer checkpoint and then the 30-minute API watchdog stopped Reviewer. Its
public record reported 1,404 seconds because elapsed time came from the stale
`status.json` mtime, while final usage was `null` because the kill bypassed the
worker's exception path. Raising the watchdog would not repair either seam.

## Implemented

1. Added an immutable `terminal.json` owned by the worker for normal exits and
   by the API after externally stopping a process. It records actual monotonic
   duration, terminal reason/method, last stage, timeout policy, usage state,
   and checkpoint/recovery snapshots.
2. Added cumulative usage snapshots at every completed-node callback. Per-role
   counters and cost merge monotonically under locks; collection failure is
   `unavailable`, not a zero or a pass.
3. Added one API-to-worker deadline identity. API workers use a 150-second
   provider timeout, disable SDK-hidden retries, reserve 240 seconds before the
   hard edge for Reviewer fallback, and reserve 60 seconds for finalization on
   the other nodes.
4. Threaded `usage_accounting`, `runtime_budget`, and `terminal` through both
   public run endpoints. Browser copy distinguishes complete, partial, and
   unavailable accounting.

The implementation deliberately reuses the existing validated-Writer Reviewer
fallback and independent guarded Scorer. It does not weaken a guardrail, change
the score formula, alter retrieval, add a tool call, or increase the hard
timeout.

## Validation

The post-change suite passed **2,043 tests and 674 subtests** with zero network
access. Latest Ruff and the CI-matching narrow Pylint checks also passed.
The loopback Chromium smoke also passed with zero console/page errors, zero
external requests, zero mutation attempts and zero paid-provider requests.
Additional endpoint/client seams confirm that a usage-collector diagnostic
remains `unavailable` after an API-owned stop, and that a durable zero-token
snapshot still displays its lower-bound state rather than disappearing.


Three original defects were then re-injected independently:

| Re-injected defect | Required failure |
|---|---|
| Removed the pre-call full-window check | Deadline test failed because the provider stub was called instead of raising `RunDeadlineExceeded` |
| Removed usage/accounting from the task-completion write | Worker seam test failed with missing intermediate `usage`, although final collection still computed 100 tokens |
| Removed terminal elapsed precedence | Timeout test observed the old mtime-derived `0` seconds instead of the terminal record's `1,801` seconds |

Each temporary defect was reversed, and all three focused tests returned to
green. The tests therefore exercise the call, callback-to-disk, and
disk-to-client seams rather than merely checking that new fields exist.

## Interpretation and limits

This closes the deterministic P0 implementation gap exposed by the failed
canary. It does **not** establish production success, a timeout rate, stable
Qwen latency, exact billing, or that Reviewer fallback will occur in the next
live run. Provider acceptance of an in-flight request remains unknowable when
no response returns, so externally stopped runs intentionally report a lower
bound or unavailable accounting state.

The next evidence step is one new post-deployment canary under a separately
frozen identity and explicit owner budget. Until that happens, documentation
must say “implemented and zero-network validated,” not “production validated.”

See [the runtime contract](runtime-terminal-integrity.md) and the
[triggering canary result](results-2026-09-04-report-decision-seams-paid-canary.md).

## Post-deployment admission follow-up

The first authorized RTI01 attempt stopped before submission because the
deployed browser did not consume `terminal.reason_code` or
`terminal.termination_method`. The result was zero roots, zero
provider/search requests, and USD 0.00 cost. This exposed a fourth delivery
seam rather than invalidating the runtime record itself.

The browser now renders a translated reason and a raw reason/method tooltip,
with explicit missing and unreadable terminal states. The loopback Chromium
fixture commits a real terminal record and follows it through disk, FastAPI,
JavaScript, and the DOM. Removing the final DOM assignment made that browser
journey fail before the correct code was restored. The expanded zero-network
suite passes 2,062 tests plus 678 subtests; latest Ruff, the CI-matching narrow
Pylint gate, and the loopback Chromium smoke also pass. The replacement paid study
remains separately authorized work; see the
[preflight result](results-2026-09-04-runtime-terminal-integrity-paid-canary-preflight.md)
and
[RTI02 pre-registration](prereg-2026-09-04-runtime-terminal-integrity-post-browser-seam-paid-canary.md).
