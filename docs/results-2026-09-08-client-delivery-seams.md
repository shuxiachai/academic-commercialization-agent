# Optional logs, artifact details and browser storage delivery

Date: 2026-09-08. Base: `6904b7227882e6f0991870f69440c922759909c3`.
This is zero-provider boundary maintenance, not a new report-quality study.

## Evidence before editing

The unchanged baseline passed 2,428 tests and 1,186 subtests. The review's
bounded local inventory covered 139 timestamped/benchmark directories, with
57 step logs containing 610 lines and 109 score files. It found no invalid
step rows or empty score objects. The fault cases below were synthetic, not
an observed production-incident denominator. Original runs were not changed;
private reviewer files and reserved experiment cohorts were not inspected.

Actual HTTP probes reproduced status 200 beside progress 500 for malformed
step objects, and duplicate suffix events after a rejected physical line.
The shipped JS reproduced empty score JSON as 0.0/Nascent, empty consistency
JSON as agreement, and localStorage denial before any HTTP request was sent.

## Changed contracts

### Step log reads

`steps_next_cursor` is a complete physical-line offset for the existing `since`
parameter, not the length of returned valid events. `steps_read_state` distinguishes
absent, readable, partial and unavailable; `steps_rejected` counts observed
rejected complete lines, not failed tasks. Prefix scanning retains loss visibility
after a cursor advances. Binary iteration isolates malformed UTF-8 per line.
The reader withholds every non-newline-terminated tail until the writer completes
it, even if its current bytes parse as JSON. File errors expose no raw paths.

The browser adopts that cursor, retains a fallback for older servers without
the field, and shows degraded log state in the header without overriding the
run outcome. Log failure does not suppress a readable saved report or trigger
a paid rerun. Existing external clients counting valid events must adopt the
returned cursor themselves. This assumes append-only logs, not arbitrary file
replacement, distributed streaming or guaranteed delivery of a torn final row.

### Downloaded details

The artifact route still serves original bytes. Score numbers must be finite,
in display range and correctly typed; missing values become unavailable/dashes,
not zero or a maturity band. Valid dimensions survive a bad aggregate. Grounding
checks validate counters and displayed row shapes, isolate malformed neighbours,
and never paint zero coverage as a pass. Consistency requires an explicit checked
flag, valid findings and matching counts before displaying a clear result.
Skipped/failed checks and malformed details have distinct bilingual messages.

This is display validation, not score recalibration, writer repair, general
citation entailment or a new blocking guardrail. Historical optional detail can
remain unavailable beside readable counters. Reports and healthy tabs survive.

### Browser storage

Access-code and BYOK persistence can fall back to page-local memory. A failed
storage slot remains latched there until reload so a later read cannot resurrect
a value whose removal failed. Language and sidebar preferences degrade without
preventing module initialization or UI updates. Authentication, BYOK isolation,
server ownership and paid-request retry policy are unchanged.

The UI states that credentials/history may not persist. Failed persistent logout
does not reload into stale credentials: it clears page-local identities, returns
to the gate and asks the visitor to clear site data before reopening. This cannot
purge inaccessible browser storage or other tabs. Closing/reloading ends memory
fallback; it does not cancel a server run or revoke a run capability. Optional
BYOK history still warns on failed writes rather than claiming durable history.
Same-document gate re-entry clears old form inputs and replaces its handlers;
repeated login must complete the current gate promise with one access check.

## Verification

- Final local full suite: 2,499 passed and 1,191 subtests passed on Windows / Python
  3.12.9, with fresh coverage 88.89% against the unchanged 85% floor. All 71 added cases
  run without network/provider requests; no assertions or warning filters weakened.
- Latest Ruff and the narrow CONTRIBUTING Pylint command passed.
- HTTP-file-to-JS cases cover malformed roots/counters/rows, partial UTF-8 tails,
  permission failure, physical cursors, completion, and healthy positive controls.
- Real Chromium read-only journey: no external requests, mutations, unexpected
  console errors or page errors; report navigation survives bad logs/details.
- Real Chromium composer journey: ten intercepted fixture POSTs, zero API requests
  reaching its static-only server and zero page errors. Added storage-denial login,
  language switch, logout and memory-only BYOK checks make no additional paid POSTs.
- Eight defect injections were detected: event validation removal, event-count
  cursor restoration, old detail renderers, old pre-fetch storage access,
  language initialization storage access, sidebar initialization access, and
  reload after failed logout, and accumulated gate handlers after re-entry.
  Every edited file's pre-injection hash was restored.

Documentation indexing can add subtests independently. The final PR CI owns
the exact committed-tree counts across both platforms. No paid canary, Railway
restart, scoring/model change, frozen-cohort reuse or production Tool Calling
connection belongs to this maintenance.
