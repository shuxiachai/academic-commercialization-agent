# Runtime summary read integrity — 2026-09-05

## Scope and prior evidence

This is offline fault isolation on top of public `da27f4a`, not a paid run or
evidence of a current production outage. The starting suite passed 2,151 tests
and 1,118 subtests. Among 109 direct historical run directories, 67 contained
readable status files and 42 had none. The 30 benchmark directories did not
contain status files. Of the four runtime-summary fields in the 67 readable
files, only two usage objects were non-null; accounting, checkpoint and recovery
summaries were absent/null. Replaying the new projection changed zero records
and rejected zero summaries. This small legacy sample cannot establish
recovery compatibility, corruption incidence or a production success rate.

## Reproduced faults

- Broad runtime dictionaries let string prices reach JavaScript `toFixed`,
  non-finite prices break HTTP JSON serialization, and malformed agent/error
  lists break browser rendering before a saved report loads.
- String `reused_nodes` was counted by character length. String
  `committed_nodes="not_retrieval"` satisfied the browser's substring check and
  exposed Resume; server manifest/ownership/admission checks were not bypassed.
- Empty terminal checkpoint/recovery objects fell back by truthiness to the
  weaker mutable status, resurrecting stale persistence/reuse claims.
- An unavailable accounting state beside positive/default counters still
  rendered a dollar value, including `$0.0000`, instead of unavailable.

## Changed read contract

`api/runtime_projection.py` validates only the selected usage, accounting,
checkpointing and recovery display summaries, after immutable snapshot
selection. Known counters must be non-negative JavaScript-safe integers, prices
finite and non-negative (or null), flags real booleans, and consumed lists the
expected element types. Node names are known and unique. Optional legacy fields
remain optional; valid extension fields survive. No numeric-string coercion,
counter recomputation, manifest inspection or artifact rewrite occurs here.

Unreadable fields are isolated and named in `runtime_metadata_unreadable` on
both status and progress. The browser displays fixed, translated field labels,
not raw bad values or exception text. A valid terminal outcome, elapsed time,
report and healthy sibling summaries remain available. Missing/null is still
different from a malformed present field. Explicitly empty terminal snapshots
do not revive mutable state; optional null checkpoint/recovery snapshots retain
the existing legacy fallback. Terminal usage null remains authoritative.

Bad usage means unavailable accounting, not a zero bill. Valid independent
completion flags and snapshot time survive that loss. Bad accounting beside
readable usage yields a lower bound, never a certified final total. Complete
accounting without a usable measurement cannot certify spend. An explicitly
unavailable collector overrides numeric defaults in both summary and tooltip.

These are read-side contracts, not proof of checkpoint validity or resume
eligibility. Writers, recovery authorization, checkpoint identity, execution,
monotonic collection, quota accounting and provider requests are unchanged.
Invalid top-level immutable records still follow the existing unreadable
terminal contract; this work does not salvage an invalid terminal schema.

## Verification and defect reinjection

- 38 malformed status cases and 27 nested-terminal cases traverse real files
  and both HTTP endpoints; valid terminal facts and original bytes survive.
- Ten compatibility/authority cases cover valid immutable precedence,
  legacy/absent/unpriced/degraded summaries, collector diagnostics with/without
  accounting, and complete-without-measurement. The first full replay caught a
  legitimate diagnostic-only legacy shape; the reader was corrected without
  weakening the existing timeout test or adding default counters.
- Two browser-formatter regressions cover unavailable numeric defaults and
  fixed unreadable labels. The Chromium journey adds three runtime fixtures
  (seven total), including report visibility and positive/negative Resume
  controls without submitting a request.
- Reinjecting old passthrough makes all 65 malformed-field cases fail.
  Restoring truthiness fallback makes both empty-terminal cases fail.
  Dropping the progress warning makes Chromium fail on the missing DOM label.
  Restoring old usage display order makes the numeric-default test fail with
  `$0.0000` instead of unavailable. All injections are reverted before commit.

After restoring all fixes, the full zero-provider suite passed 2,228 tests and
1,126 subtests. Latest Ruff, narrow Pylint and loopback Chromium passed. The
browser observed zero external requests, zero mutation attempts and zero page
errors. Cross-platform publication checks still belong to the exact PR SHA;
this change needs no provider calls or paid recovery experiment.

## Limits and next step

No claim of broader semantic correctness, billing accuracy, fault frequency,
exactly-once delivery, actual recovery success or production SLO follows from
these fixtures. Other payloads such as runtime-budget diagnostics, detailed
audit artifacts and unused auxiliary readers are not comprehensively validated.
Experimental Tool Calling remains zero-call production shadow mode, and v8's
unseen failure is unchanged. After review/merge, check the deployed revision
and the two response schemas read-only; do not launch paid work just to verify
this display contract.
