# Result: anonymous OpenAlex evidence-gap harness — implementation only

**Date:** 2026-08-27

**Protocol:**
[`prereg-2026-08-27-evidence-gap-anonymous-openalex.md`](prereg-2026-08-27-evidence-gap-anonymous-openalex.md)

## Outcome

A production-disconnected, no-key OpenAlex measurement path now exists for the
four frozen academic Phase 4 cases. Its default command is a zero-network
dry-run. No live OpenAlex request was made, no API key was configured or
consumed, and no result entered a production report.

This closes an implementation and auditability gap only. Provider
compatibility, candidate relevance, novelty and report value remain
`not_evaluated` until a separately authorized frozen execution and an eligible
source-grounded human review are complete.

## Implemented boundary

The implementation adds:

- an anonymous wrapper around the existing strict OpenAlex response parser;
- an outbound transport seam that removes exactly one local sentinel and
  proves the actual endpoint contains no `api_key`;
- refusal to run while `OPENALEX_API_KEY` is present;
- four-case and four-request hard caps over D01–D04;
- a provider-reported soft stop no greater than USD 0.01;
- pre-request fixture and implementation identity checks;
- write-once manifest, per-case journals, aggregate execution, candidate,
  review and artifact-index files; and
- explicit `partial`, `cost_uninspectable`, `request_failed` and
  `accounting_invalid` states.

The runner reuses the Phase 4 candidate projection so accepted candidates and
provider-rejected rows cannot disappear between executor output and the CSV
review boundary. It imports neither the production worker nor the report
registry, and the production worker imports neither the runner nor anonymous
adapter.

## Zero-network verification

The dry-run selected D01–D04 in frozen order, matched the fixture and four
implementation hashes, reported `api_key_used=false`, and performed zero
network calls.

The targeted adapter, runner and existing domain-adapter set passed **33/33**
tests. The new seams cover:

- removal of the key before the injected network transport;
- exactly one outbound request per attempted case;
- manifest-before-request and journal-before-next-request ordering;
- request and provider-reported cost accounting through final JSON;
- candidate and provider-rejection delivery through both CSV boundaries;
- budget, acknowledgement, configured-key, existing-path and identity-drift
  rejection before adapter construction;
- inspectable partial states for soft-stop and provider failure;
- artifact secret/sentinel exclusion; and
- continued production-worker disconnection.

## Defect re-injection

After the targeted suite first passed, the sentinel-removal line was
deliberately changed so the local `api_key` parameter reached the injected
network transport. The outbound-boundary test failed on the exact leaked query
parameter. The mutation was immediately removed, and all 33 targeted tests
passed again.

This demonstrates that the test observes the final request seam rather than
only the adapter's constructor or returned model.

## Project verification

- complete zero-network suite: **1,569 tests plus 639 subtests passed**;
- measured coverage: **87.28%**, above the unchanged 85% CI floor;
- latest Ruff: passed; and
- the CI Pylint exception-order, unreachable and undefined-name checks: passed.

The coverage run emitted nine inherited `ResourceWarning` messages from CrewAI
SQLite lifecycle paths. It emitted no `UserWarning`, entered no provider
fallback, and required no warning filter or test relaxation.

## Decision and next gate

The disconnected harness is eligible to merge. Production Tool Calling is
not.

After merge and green CI, the next action is a separately authorized run on
the exact merged revision, with at most four anonymous requests and the USD
0.01 provider-reported soft stop. If execution is complete and inspectable, a
source lock and eligible human review must evaluate the frozen academic value
gates before any planner-trigger experiment is considered.

## Supported claim

> A production-disconnected OpenAlex harness can exercise four byte-frozen
> academic evidence-gap cases without an API key, while enforcing one-request
> accounting, a small provider-reported soft stop, write-once artifacts and a
> key-free outbound seam. Its zero-network tests pass; live source value and
> production readiness have not been measured.
