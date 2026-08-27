# Public per-run pipeline revision seam

Date: 2026-08-27

## Question

Can a caller determine which non-secret code revision actually executed a run
from either public status surface, without incorrectly attributing historical
runs to the deployment that happens to serve them later?

This is a zero-network implementation result. It authorizes and measures no
provider request, supplementary search, Tool Calling, report generation, or
production canary.

## Pre-change measurement

The existing local output corpus was measured before code changed:

- `rg --files -uu outputs` found 1,459 files, including ignored run artifacts;
- 75 real run directories contained `status.json`;
- 0/75 status files contained `pipeline_revision`;
- revision identity already existed in 997 checkpoint manifests.

The checkpoint layer therefore knew the execution identity, but the run-status
contract did not persist or expose it. Looking up the current API process's
revision would not repair that seam: after a deployment it would relabel an old
run as code that never executed it.

## Implementation

The worker now computes `pipeline_revision()` before its first durable status
write and persists the value in `status.json`. Status rewrites use a
first-write-wins rule: omission and a conflicting later value both preserve the
identity recorded when the run began.

`api.runs.get_state()`, `RunStatus`, `RunProgress`, and the explicit progress
constructor now carry that exact persisted value. A historical run without the
field returns `null`; the API never synthesizes a replacement from its current
deployment.

The value is a non-secret code identity (`git:<sha>` in deployed environments,
or the existing source-content fallback locally). It is not a credential and
does not change checkpoint identity, recovery behavior, retrieval, prompts,
scoring, or Tool Calling.

## Verification

Tests were added at both relevant seams:

1. a worker run must retain the patched execution revision through its terminal
   status write;
2. status rewrites must preserve the first revision even when a conflicting
   value is offered later;
3. both public endpoints must return the persisted value byte-for-byte; and
4. historical runs must return `null` rather than the current deployment.

The new tests were run before implementation and failed because both endpoints
omitted the field and status rewrites discarded it. After the repair, the
focused API/worker suite passed 58 tests and 77 subtests. The original progress
seam was then re-injected by temporarily removing its explicit constructor
mapping; the endpoint-specific subtest failed (`None` versus the persisted
revision), proving that the test detects the actual boundary defect. The line
was restored before final validation.

Final zero-network verification passed 1,554 tests and 639 subtests. The
CI-equivalent coverage run remained at 87.26%, above the 85% floor; latest Ruff
and the narrow exception-order Pylint checks also passed. Resource warnings
reported by the Windows/Python 3.13 coverage run were non-failing third-party
SQLite cleanup observations, not suppressed `UserWarning` network fallbacks.

## Claim boundary

This establishes an offline persistence and API-contract repair for future
runs. It does not retrospectively identify the three Decision Context canary
runs, change their frozen 7/10 result, prove a Railway deployment, or provide a
new paid observation. A future provider-backed run may use the field as one
piece of execution provenance only after the revision containing this change is
deployed.
