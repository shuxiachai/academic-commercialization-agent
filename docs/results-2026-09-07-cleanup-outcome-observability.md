# Best-effort cleanup outcomes at the HTTP boundary

Date: 2026-09-07. Base: `89afc3670d0f6687aa16079170968540f5d733ec`.
Zero-provider maintenance; not a retention-policy or readiness-eviction change.

## Evidence before the change

The unmodified suite passed 2,405 tests and 1,181 subtests. A preceding bounded
same-revision observation sampled twenty health/readiness GETs over about
5 minutes 17 seconds. All returned 200 and all sampled cleanup checks were ok;
ten capacity samples showed zero active paid operations. That short observation
does not establish busy-load reliability, deletion completeness or a safe
freshness threshold. Raw operational samples stay in the private notes archive.

Code inspection identified a different gap: cleanup deliberately catches
per-directory OSError, continues with peers and returns a removal count/list.
The supervisor therefore observes normal return, even when some deletions fail.
Two new regressions first failed on missing HTTP cleanup detail after actually
retaining one denied fixture directory and removing its peer. This reproduces
an observation gap offline, not a confirmed Railway deletion incident.

## Contract and implementation

Both `/health` and `/health/ready` include `maintenance.cleanup.papers` and
`maintenance.cleanup.retention`. These are the last observed attempts, paired
with the same stage's last-completion clocks. Legacy `checks` still means
normal return versus an escaped stage failure; clients must inspect cleanup
detail to distinguish best-effort partial results. Existing readiness policy
is unchanged, including advisory cleanup faults and blocking watchdog faults.

| State | Meaning |
|---|---|
| not_checked | No completed stage observation in this lifespan |
| complete | Root enumeration completed with no recorded entry-operation failure |
| partial | Enumeration completed but one or more entry operations failed |
| disabled | Run retention was explicitly disabled, with no root scan |
| absent | Root stat established absence, with no root scan |
| unavailable | Root/iteration/stage failure, or no collector observation |

Each summary exposes `scan_complete`, `scanned`, `deleted`, `skipped`,
`failed`, `skip_reasons` and `failure_reasons`. No scan has null counts,
not a fabricated zero-count success. An empty completed scan has zero counts.
An interrupted enumeration retains observed prefix counts with
`scan_complete=false`; those are not a complete inventory. A root/iterator
failure is not an invented failed directory, so `failed` may be zero while
the state is unavailable.

Completed scans partition enumerated entries into deleted, deliberately skipped
or failed operations. Skip reasons are fresh/live/unrelated; failure reasons
are metadata/delete. No paths, IDs, raw exception text or unbounded per-entry
lists enter the public summary. A deletion race can produce an operation error;
the count alone does not prove that the target remains on disk.

A per-call collector preserves the historical integer/list return values and
default calling forms. It is not a process-global mutable tally. Only a
completed immutable projection is published with the stage clock/result under
the existing short snapshot lock. A new in-flight attempt, including repeated
cancellation/drain, retains its previous completed observation. New lifespans
clear the records. Calls without a collector cannot fabricate observation facts.

Use explicit root stat so absence and unreadability are not conflated by
platform-dependent is_dir behavior. A file where a directory is required is
unavailable. Root failures still reach the per-stage supervisor; individual
metadata/delete errors are counted while peer processing continues. Preserve
age selection, exclusions for occupied/stop-owned runs and serial offloading.
No new abort-on-first-error cleanup, readiness failure for an individual
deletion error, retry, forced restart or distributed ownership is introduced.

## Verification

Twenty-three new cases cover denied deletion with successful peers and a later
recovery cycle; empty/absent/file/denied roots; disabled retention; mid-listing
failure before and after a deletion; entry metadata errors; fresh/unrelated
skips; stop-owned retention exclusions; cancellation-held publication; lifespan
reset and complete OpenAPI fields. Counters, partition/reason sums and no-path
disclosure are asserted at both actual HTTP response schemas.

Existing maintenance fake callables now accept the optional collector keyword.
Their original blocking, ownership, cancellation, timing and HTTP assertions
remain unchanged. The unstarted exact schema assertion includes the additive
cleanup field; no warning filter was relaxed and no test was skipped.

Six defect re-injections target missing HTTP projection, hidden paper deletion
failure, hidden run deletion failure, false empty-success, premature loss of a
prior observation and false completed coverage after an iterator fault.
An initial temporary harness reverse patch matched a repeated line; its source
hash guard stopped the run. Restore with contextual patches and use a uniquely
marked mutant before repeating the full six-case audit. The final audit caught
all six intended failures and restored each exact pre-mutation file hash.

The restored-source Windows/Python 3.12 full suite passed 2,428 tests and
1,186 subtests, with fresh coverage 88.86% above the unchanged 85% floor.
Latest Ruff, narrow Pylint and both real Chromium journeys passed. The read-only
journey had no external requests, mutations, page errors or console errors;
the composer intercepted ten simulated POSTs with zero API requests reaching
its static server, unexpected requests or paid-provider calls.

## Limits

This reports per-attempt operations, not directory-size inventory, recovered
storage bytes or proof that all expired artifacts are gone. Enumeration is not
an atomic filesystem snapshot. Best-effort cleanup remains serial, can block
on filesystem work and cannot forcibly interrupt a native/thread operation.
Unknown totals stay unknown. The observation is not a long-term SLO, compliance
erasure guarantee or evidence of a production storage fault.

No provider, scoring rule, frozen experiment or production supplementary
Tool Calling change was made. Tool Calling remains zero-call shadow mode.
