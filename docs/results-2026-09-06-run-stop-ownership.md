# Retain run ownership through stop and terminal publication

Date: 2026-09-06. Base: `c9d92d22efe1c4bfa6107ae2985fac93c7824365`.
Zero-provider maintenance, not a paid experiment or observed production incident.

## Evidence before changing production code

The unmodified baseline passed 2,341 tests and 1,166 subtests. A read-only census
found 109 direct timestamped run directories and no `terminal.json` in that
cohort. These retained historical artifacts cannot measure a transient ownership
gap, its production frequency or financial impact. No benchmark was rerun.

Twelve new deterministic regressions failed against the original implementation:
four capacity checks read `(0, 0)` while a stop was held; four deletion checks
returned 200 instead of conflict and removed the fixture directory; two failed
termination paths escaped HTTP handling; pending launch cancellation and a natural
completion race each returned 200 instead of conflict. No paid worker was launched.

Cancellation, timeout and shutdown removed registrations before waiting for the
process. Restoring a timeout handle only after an exception did not close this
transient gap, and cancellation did not restore it at all. Keeping the handle
only until `wait()` returned would still leave a gap during terminal publication.

## Change and rejected alternatives

- A local, identity-bound stop claim retains the existing registry entry through
  terminate/wait/kill and the caller's outcome publication. Slot counters, both
  HTTP readers, Delete and retention honor that same claim.
- Claims are acquired/released under the registry lock, while waiting and disk
  writes remain outside it. Holding that global lock for a potentially ten-second
  stop was rejected because it would block unrelated health and admission calls.
- Competing mutations return 409, including legacy DELETE: an already-owned stop
  is not an absent handle and cannot fall through to deletion. No new public run
  state or second server-side ownership identity is introduced.
- A pending launch is rejected as a stop conflict, not acknowledged through its
  no-op placeholder. The watchdog skips it until an actual process is registered;
  shutdown reports unresolved launch/stop overlap instead of silently clearing it.
- Failed physical termination returns safe HTTP 503 and retains ownership in the
  registry for later attempts. The watchdog still attempts other expired workers.
  A natural exit before termination keeps its own outcome.
- Readers snapshot ownership before reading disk, so release during a stale
  terminal read cannot produce a prematurely settled projection. Progress is
  `done=false` during the observed ownership interval.

No scoring, model/provider, CrewAI, checkpoint identity, retrieval, frozen fixture
or experimental selector was changed. Supplementary retrieval remains zero-call
shadow mode. No fee authorization or Railway restart was used.

## Tests and fault injection

Twenty-one new tests include eight event-held cancel/timeout × process/terminal
checks, denied and timed-out stop failures, launch and shutdown conflicts,
natural completion, read/release and pending-launch deadline races. The last
regression also failed during self-review: selecting an old placeholder and
claiming a newly installed process killed a fresh worker as overdue. Candidate
selection now excludes placeholders before their registration can be replaced.
Four cases use real local Python
children blocked on stdin to verify OS terminate and kill/wait paths; those
children do not import the pipeline or call a provider. Escalation's first wait
timeout is injected, not a measurement of the real five-second grace period.

Assertions cross HTTP health/status/progress, both inline funding modes, root
admission, explicit/legacy mutations, retained report bytes and terminal files.
The original four-caller concurrency assertion is retained and strengthened to
require all four threads to settle with exactly one successful stop. Its fixture
now isolates wallet cache/date from operator configuration; charging stays enabled.
A mkdir injection is scoped after reservation so it tests both slot cleanup and
refund instead of failing prematurely at the durable ledger's own mkdir.

Nine defect re-injections are checked independently: early registry removal,
physical-exit-only reaping, release after denied stop, no-op launch cancellation,
natural-exit relabelling, late ownership observation, retention ignoring the
writer, Delete ignoring the writer and reservation age killing a fresh worker.
Each must fail its intended assertion;
each production file is restored to its exact SHA-256 before further checks.

All nine triggered their intended assertions and were restored. Final local
verification passed 2,362 tests and 1,171 subtests, latest Ruff, narrow Pylint and
both real Chromium journeys. Fresh Windows/Python 3.12 coverage was 88.69%, above
the unchanged 85% floor. The read-only browser journey recorded zero external
requests, mutations, page/console errors or provider requests; the separate
composer journey used ten intercepted POSTs, with zero API requests reaching its
static-only server, zero unexpected requests and zero provider calls. These
are revision-specific offline observations, not a production reliability rate.

## Limits

This closes a reproduced single-process stop/finalization seam, not distributed
ownership, queued cancellation of a blocked launch, forced recovery, arbitrary
filesystem integrity, remote-provider interruption/refund, exactly-once billing,
or a production SLO. Terminal persistence remains best effort after a confirmed
physical stop; a broken volume can still lose the audit record. Shutdown assumes
normal ASGI request draining and explicitly reports unexpected outstanding work.

An unchanged historical report count is not evidence of zero past incidents.
Deployment verification should be read-only health/readiness and version checks;
this deterministic ownership fix does not require a paid canary.
