# Saved-evidence follow-up: offline phase-one result

Date: 2026-09-14 (Australia/Sydney)

Scope: isolated protocol implementation; no live model or production integration.

The [protocol](prereg-2026-09-14-report-evidence-followup-phase1.md) was committed
as `ad38e21` before the implementation. This is a separate read-only task, not
an attempt to rescue sealed Adaptive Role-Gap v8 or change its evaluation gates.

## Implemented boundary

The trusted caller projects one supplied source collection into an immutable,
bounded snapshot. Two tools search literal saved text and read exact Unicode
character windows. They cannot select another report, file, URL or provider.
Strict source IDs, schemas and duplicate checks prevent ambiguous lookup.

An injected transport exchanges native-shaped assistant/tool messages, with
at most two tool requests and three transport turns. Tool results use the
original call ID. Successful non-empty reads issue content-bound evidence IDs;
final citations must select IDs actually passed back to the callback. Their
text and provenance are code-owned rather than accepted from model prose.

`answered_with_evidence` is a delivery state only. `semantic_support` remains
`not_assessed` and `answer_verification` remains `not_verified`. Truncated
non-empty windows may be delivered successfully, with incompleteness visible.
A complete saved window does not prove full-abstract or full-text coverage.

Delivery here means passed as an argument to the injected callback, not a
provider acknowledgement. The callback can fail after seeing the result: the
audit retains that history but publishes neither a successful answer nor final
citations. An in-process callback needs its own bounded network implementation
before live use; this library does not guarantee preemptive timeout or costs.

## Measurements and contract validation

- Pre-change full suite: **3,190 passed / 1,282 subtests passed**.
- New snapshot/conversation tests: **127 passed** after the harness correction
  below. These are synthetic engineering tests, not 127 user evaluations.
- Final full suite after correcting the archive index: **3,317 passed / 1,292
  subtests passed** on Windows / Python 3.12, in 92.97 seconds. This is local
  verification; remote CI and any later release have their own revision identity.
- Real local demo: two tool executions, three scripted transport turns, one
  served synthetic excerpt, `semantic_support=not_assessed`.
- The demo subprocess test blocks socket operations and provider imports; it
  checks actual stdout JSON rather than trusting a self-reported no-network flag.
- Latest Ruff (0.16.7) and the project's narrow Pylint checks passed.
- Independent read-only review found one documentation mismatch and requested
  an additional post-read transport-failure test. Both were addressed; final
  scoped review reported no remaining actionable findings, not production approval.

The 30 existing local source artifacts still contain 632 repeated-run entries:
173 abstract origins, 451 snippets and eight unspecified. All contain saved
text. The sorted list of their uppercase SHA-256 strings, joined with LF and
hashed as UTF-8, remained
`be4d8673989d5e586103624e305460dbb47af370043e14e783c0e8b2ea654cee`.
These local counts do not establish unique-source truth or the old CSV's
original identity; the previously disclosed fixture unit remains in the set.

## Failures kept in the record

The first default-temp baseline encountered `PermissionError` while pytest
traversed the existing Windows `pytest-of-shuxia` directory. That run was
stopped; a first-error diagnostic produced 22 passed / one setup error. The
unmodified suite then passed using a fresh workspace `--basetemp`, as prescribed
by CONTRIBUTING. No ACL, assertion or warning policy was changed.

The new focused suite initially reported 125 passed / two errors; a narrow
diagnostic reported five passed / two errors. A very long parameter label
overflowed Windows' 32,767-character environment variable limit when pytest set
`PYTEST_CURRENT_TEST`. An explicit short parameter ID fixed the harness while
preserving the original over-limit input and exception assertion. No skip or
weaker test was introduced. The additional post-read failure test subsequently
brought the passing focused total to 127.

The first full post-change run had 3,317 passing tests and 1,286 passing
subtests, but failed the archive-navigation subtest because the new protocol
had not yet been linked from `experiment-index.md`. The index was corrected;
the missing-link failure is not counted as a passing full run.

## Defect reinjection

1. Returning a different `tool_call_id` made the exact next-request round-trip
   assertion fail (**one failed test**).
2. Silently accepting a repeated source ID made the duplicate-source admission
   tests fail (**three failed tests**).

Both mutations were removed. Restored core SHA-256 values match the separately
reviewed implementation:

- snapshot: `5d37a0033427ec274c1dae7bedf431eb9f7f821de87f7d348e857146275d643f`;
- follow-up: `417f22f05dba4e2f74537dcb79165af6d13088337ac06cb66200eef102d554fe`.

## Reproduction and limits

```bash
uv run pytest -q tests/test_report_evidence_snapshot.py tests/test_report_evidence_followup.py
uv run python report_evidence_followup_demo.py
```

Use a fresh workspace `--basetemp` if the system pytest directory is unreadable.
The demo is explicitly scripted and synthetic. No real transport, provider key
read, paid request, source fetch, production route, browser control, score
change or Railway restart was added or executed. Frozen v1–v8 implementations
and evaluation artifacts are unchanged.

Before live testing, separately freeze the exact model, inputs, request limit
and cost limit and obtain authorization. Before a public paid endpoint, review
ownership/admission, receipts, accounting and failure delivery. Before claiming
reader benefit, compare the feature with ordinary source browsing. Passing this
offline contract establishes none of those separate claims.
