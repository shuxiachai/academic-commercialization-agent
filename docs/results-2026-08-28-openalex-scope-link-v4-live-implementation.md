# OpenAlex scope-link v4 live-runner implementation result

Date: 2026-08-28

Status: **implementation complete; no live provider request authorized or made**

## Question

Can the byte-frozen W01-W08 scope-link v4 challenge be given the same
write-once, bounded, auditable live-execution boundary as the earlier v3 study
without connecting the experiment to production or claiming source value?

## Frozen boundary

The implementation follows
`docs/prereg-2026-08-28-openalex-scope-link-v4-live.md`. In particular:

- the raw W01-W08 fixture remains locked at
  `f4267c6a79c0bb8a685664de5086e4cfff59ebac1b352cbb56c2277957a55cc3`;
- all decision and transport dependencies are verified before output
  reservation or adapter construction;
- execution is capped at eight anonymous, one-attempt requests and a USD 0.01
  provider-reported soft stop;
- a configured `OPENALEX_API_KEY` is refused rather than silently used;
- production and report-workflow connections remain false; and
- a future live execution still requires separate authorization naming the
  merged revision and budget.

The runner's observed byte hash is
`bfd0bb7b4e668c56f3acd57a95d87a7fdedcd17699ae0b6d225dd882320de96d`.
It is recorded in the manifest and final execution artifact instead of being
placed in its own expected-hash table, which would create a recursive and
therefore unsatisfiable self-hash contract.

## What was implemented

`openalex_scope_link_live.py` reuses the previously bounded anonymous OpenAlex
transport but replaces the v3 decision with the frozen v4 scope-link gate. The
complete manifest is written before a network-capable adapter can be
constructed. Each attempted case writes its journal before any later case may
start. Provider candidates and provider rejections both reach the aggregate
CSV boundary.

For evaluated candidates, the artifact keeps required, scope and supporting
match provenance separately and also carries the exact same-segment
`link_evidence`. Only `ACCEPT` rows enter the blank human-review CSV;
`ABSTAIN` and provider-rejected rows remain inspectable in `candidates.csv`.
No human labels, source-value result, planner decision or report claim are
created by this runner.

## Verification

- 17 new live-runner tests pass.
- The combined v4 decision, unseen preflight and live-runner subset passes
  **32/32** zero-network tests.
- The complete repository passes **1,695 tests plus 609 subtests**; one
  pre-existing optional test is skipped.
- Latest Ruff passes across the repository.
- Narrow Pylint checks for exception ordering, unreachable code,
  use-before-assignment and undefined variables pass for the new runner.
- The production worker imports none of the v4 runner, preflight or decision
  modules.

The pre-registered delivery defect was re-injected by dropping
`link_evidence` while leaving the internal v4 decision intact. The CSV-boundary
test failed on accepted rows, proving that it checks delivery to the review
artifact rather than merely checking an internal field. The correct mapping
was restored and the full 32-test subset passed again.

## Observed outcome and limits

The live execution harness is mechanically ready and remains disconnected.
Real network calls performed: **0**. Provider cost: **USD 0.00**. W01-W08
provider compatibility, accepted-case coverage, wrong-source rate, novelty and
source value all remain **`not_evaluated`**. This result must not be described
as completed Tool Calling, production integration, provider validation or a
quality improvement.

The next admissible step is a separately authorized run on the merged revision.
Only if all eight case journals are valid and at least six cases retain an
`ACCEPT` candidate may a source-locked human-review packet be prepared. A live
run alone cannot establish value.
