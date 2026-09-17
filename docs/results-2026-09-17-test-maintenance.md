# Maintain regression value, not a test-count target

Date: 2026-09-17. Baseline: `96b46f196ee4d978a1c0889ac611f742a9d2fc16`.
This is test/CI maintenance, not a runtime, model, scoring or retrieval change.

## Why this change

A read-only collection found 5,355 pytest items across 178 test files. By
filename, saved-evidence follow-up tests account for 2,165 items and the
retrieval-experiment family for 501. These are inventory categories, not
production-dependency classifications. Identical function bodies can exercise
different adapters; duplication alone does not authorize removing coverage.

The useful first step is narrower than retiring historical experiments:

- Assert that two nonempty patent assignees reach the decoded crew input,
  rather than separately checking that an empty output is a list. Keep the
  empty-input contract in the existing generic-assignee scenario.
- Combine translation success cases while checking the requested language
  and original text at the model-call seam, not just a mocked return value.
  This does not assess translation quality.
- Run the directional patent scenario once for both result and rejection
  audit. The non-directional control must retain its cathode record; an empty
  collection is no longer accepted. A cathode-only fixture avoids another
  patent or deduplication obscuring the specific boundary.
- Inspect executable CI YAML nodes instead of display names, text counts,
  comments or job ordering. Negative controls cover missing/skipped work,
  swallowed failures and loss of matrix or coverage requirements.
- Check current launch examples rather than banning a retired product name
  from all prose. Historical explanation is allowed; invalid launch examples
  and missing current web/CLI entry points remain errors.

## Four full executions, unchanged release boundaries

Each Linux/Windows and Python 3.11/3.12 cell still executes the complete suite
with verbose reporting. Ubuntu Python 3.12 measures the existing src/api/ui
coverage and enforces the same 85% floor during that execution. It no longer
runs once without coverage and again in a separate measurement job.

The existing coverage check name remains as an explicit matrix-result gate,
not a second measurement. It runs after the matrix and rejects failure,
cancellation or skip. All eight check names are retained; lint, Chromium and
Docker jobs are unchanged. This reduces full-suite executions from five to
four, not a measured 20% latency improvement. Scheduling and coverage overhead
can still dominate completion time.

## Validation and qualifications

The unchanged baseline passed 5,355 tests and 1,462 subtests in 349.17s.
The first attempt encountered the documented global pytest temporary-directory
permission error. A fresh, verified workspace temporary directory resolved it
without changing permissions, assertions, skips or warning policy.

Targeted controls and defect reinjections exercise the changed boundaries.
The original whole-document product-name ban failed the new historical-prose
positive control when reintroduced within one test call. Initial standalone
feature mutation probes emitted a masked language-helper warning without a
transport observer; those observations are not accepted as zero-provider
verification. Three replacements ran in separate pytest processes with the
project's autouse fixtures and call-scoped provider/urllib/socket guards:

| Reintroduced defect | Observed failure | Transport / warning attempts |
|---|---|---|
| Deliver an empty assignee list | One failed test, both named applicants missing | 0 / 0 |
| Omit the requested translation language | Four failed language subtests; pytest exit 1 | 0 / 0 |
| Force anode filtering on a non-directional topic | One failed test, required cathode missing | 0 / 0 |

Each had one call scope and one verified restoration. The translation parent
printed passed, but its four failed subtests and exit 1 are the authoritative
failure, not a success. These repetitions do not prove that the old standalone
script never reached a network path.

An independent read-only review also identified two maintenance pitfalls:
stripping a Python launcher could misclassify a nonexistent script as a valid
entry point, and tokenizing a shell gate could erase its variable-expansion
quoting. The corrected checks use explicit supported launch forms, accept a
valued annotated app assignment, and preserve shell-gate quotes. The targeted
CI/documentation run passed 41 tests and 797 subtests in 1.74s. Removing the
invalid-script guard caused eight expected subtest failures. The benchmark,
CSV, security and navigation test-class ASTs remained unchanged.

The actual Bash gate returned 0 for success and 1 for failure, cancelled and
skipped. A single-quoted variable variant returned 1 even for success and is
rejected by the structural control. The negative cases do not invoke Actions.

The broader guarded feature-file check additionally found that the old fuzzy
title test's injected Semantic Scholar client did not intercept the separate
arXiv citation backfill. That path uses source_pipeline.urlopen directly.
The test now supplies a synthetic citationCount response, checks the single
lookup URL and timeout, and guards the actual urllib opener throughout the
collection call. Its existing title and rejection-audit assertions remain.

After repair, all 68 feature-file tests and 34 subtests passed in 1.65s with
zero transport-guard attempts, zero warnings and 68 restored call scopes.
Removing that mock in memory caused one expected pytest failure and one local
opener-guard hit for the synthetic arXiv citation-count URL; DNS/connection
execution was blocked. Other transport and warning counts were zero, and
the call scope restored once. The original baseline pass is not retrospectively
described as proof of zero external HTTP. An in-progress final regression was
stopped to repair this observed gap before starting the final suite again.

The final complete local regression passed 5,383 tests and 1,492 subtests in
359.72s. Repository-wide latest Ruff, the prescribed narrow Pylint and
git diff --check passed. The three replaced/combined feature test definitions
are not counted as lost failure coverage; explicit CI and launch counterexamples
increase the collected total. The before/after timings are single observations,
not a speed benchmark.

An independent read-only reviewer inspected the final test/CI changes and the
HTTP isolation repair; execution and mutation evidence came from the authors
and parent, not an independent rerun. Exact-head remote outcomes are reported
separately on [PR153](https://github.com/shuxiachai/academic-commercialization-agent/pull/153).
Local success neither substitutes for green CI nor authorizes a merge.

## Deliberately unchanged

No default collection filters, warning exceptions, coverage floor, provider
configuration, production files or frozen experiment files are changed. No
closed experiment is reopened and no paid canary or production activation is
part of this maintenance. Historical counts and results retain their dates.
The consolidation need not reduce the total collected item count: new negative
controls have value when they catch an actual false pass or false rejection.
