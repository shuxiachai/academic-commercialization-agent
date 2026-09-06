# Readiness, PDF query freshness and audit-detail maintenance

Date: 2026-09-06. Base: `aeabd2bd5f6ec51f175053e511408fe596f1883d`.
This is offline boundary maintenance, not a paid canary or a new quality study.

## Evidence and scope before editing

The unmodified baseline passed 2,265 tests and 1,149 subtests. The default
Windows pytest temporary root was inaccessible; the successful run used a
fresh project-local `--basetemp`, without changing assertions or warning filters.

The bounded inventory found 30 frozen benchmark reports and no retained
`report_audit.json` files immediately under timestamped historical run folders.
Replaying the unchanged audit on the 30 reports and their validated source
registries produced 27 not-applicable and three partial records: 22 lexically
checkable citation segments, 16 unverifiable segments, zero findings. These
are coverage counters, not independently verified facts. No original report
or source file was rewritten. No private reviews or reserved cohorts were read.

The readiness race and malformed-detail cases were synthetic reproductions.
There is no observed production-incident rate for either defect. The stale PDF
query year was confirmed in code, not as a measured retrieval-quality loss.

## Changed boundaries

### Readiness

Each request creates an exclusively opened, uniquely named probe and performs
a real write. It removes only a file it created, including after a write
failure. A collision cannot overwrite or remove an existing file. Cleanup-only
failure remains unready but is distinguished from an unwritable mount; an
earlier write failure is preserved. Configuration, paid-ledger checks and the
HTTP 200/503 contract are unchanged. No provider is contacted by readiness.

The regression synchronizes two HTTP requests after their writes and orders
the removals. The first test draft merely raced the removals and survived one
old-code reinjection on Windows; it was strengthened rather than accepted as
proof. The final test also asserts that both requests crossed the probe seam.

### PDF market queries

The worker's PDF-domain prelude now uses the existing `_recent_years` helper,
just as ordinary market queries do. The unchanged second query and the PDF
source seed still reach collection. The regression crosses RunSpec -> worker
-> collector at 2026-12-31 and 2027-01-01, stopping before paid retrieval.
It does not change query ordering, source limits, relevance, scoring or frozen
historical query bytes. A calendar window does not guarantee fresh results.

### Report-audit details

The actual downloaded artifact is checked at the browser's display boundary.
Unsupported/malformed root structures become unreadable, not empty findings.
Malformed nested coverage remains local to that section. Valid neighbouring
sections and the saved report remain usable. Counts, partial/not-applicable/
unavailable states and the unsupported-language reason are displayed in both
English and Chinese. Numeric counter types and simple count relationships
are validated; no missing counter is invented as zero.

The artifact route still serves original bytes. This is not a storage repair,
writer validation, general schema audit of every artifact, or semantic fact
check. Existing non-blocking rules, language scope and warning findings are
unchanged. Text excerpts and reason codes remain text, never artifact HTML.

## Verification

- Targeted HTTP/worker/detail tests: 92 passed and four subtests passed.
- Restore the shared readiness implementation: its concurrent HTTP test fails.
- Restore the PDF `2024 2025` literal: both calendar-boundary subtests fail.
- Restore the old detail renderer: 20 tests fail and its valid-warning positive
  control still passes. The fixed implementation is restored after every run.
- Real loopback Chromium exercises the audit writer, artifact route, visible
  coverage, malformed details and navigation back to the saved report. It
  passed with zero paid-provider calls, external requests, mutation attempts,
  unexpected console errors and page errors.

- After restoring all fixes and synchronizing these documents, the full suite
  passed 2,291 tests and 1,156 subtests. Latest Ruff and the narrow CONTRIBUTING
  Pylint command also passed. Counts are revision-specific, not an accuracy score.

No production restart, paid run, scoring change, CrewAI upgrade or supplementary
Tool Calling connection is part of this maintenance.
