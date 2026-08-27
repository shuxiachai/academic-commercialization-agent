# Result: OpenAlex precision-v2 development gate

**Date:** 2026-08-27
**Protocol:**
[`prereg-2026-08-27-openalex-precision-v2.md`](prereg-2026-08-27-openalex-precision-v2.md)
**Fixture SHA-256:**
`355782bbe40278f44cb76f650d57fbb13be6b9097bfecb6e101815a24c47ea8b`

## Outcome

The conjunctive precision-v2 candidate passed its frozen development gate.
All nine decisions were generated from the four byte-verified case journals
before the audit opened the human-label file. After the identity-locked join:

- all **5/5** directly relevant rows were `ACCEPT`;
- all **4/4** directly irrelevant rows were `ABSTAIN`;
- all **4/4** development cases retained at least one relevant row; and
- every decision and aggregate reached write-once CSV/JSON artifacts.

The formal status is `qualified_for_unseen_harness`. This is a development-set
result, not an unseen precision estimate. No network request or model call was
performed, and production/report connections remain false.

## Why the old false acceptances stopped

The previous quarantine used a broad additive relevance score. Precision v2
requires all code-owned core concept groups, enough independent supporting
groups, and a title anchor to co-occur:

| Case/source | Human label | Decision | Decisive reason |
|---|---:|---:|---|
| D03/A3 plant ROS review | not relevant | `ABSTAIN` | missing `carbon_fixation` and the title anchor |
| D03/A4 cyanobacterial engineering review | not relevant | `ABSTAIN` | missing both required groups and the title anchor |
| D04/A2 generic stability consensus | not relevant | `ABSTAIN` | only 1/2 required supporting groups matched |
| D04/A3 broad photovoltaic-materials review | not relevant | `ABSTAIN` | only 1/2 required supporting groups matched |

The rule did not reinterpret these rows as irrelevant truth. It emitted
`ABSTAIN`, preserving the precision-first distinction between “not accepted by
this contract” and “proven off-topic.”

## Lineage

The audit revalidated all source bytes before calculation:

| Artifact | SHA-256 |
|---|---|
| Frozen fixture | `355782bbe40278f44cb76f650d57fbb13be6b9097bfecb6e101815a24c47ea8b` |
| Original candidate CSV | `91d148f97320582fe29987ff2ef139f7e3cb3d53ab2473ef1ac4ad3119805006` |
| Human labels | `aaff469be0e10698a5464611343823e91b4f7256b8a881ed6361f3b27d56b296` |
| Development `result.json` | `333e9261c313513136baee1fe72e1a03a049b3c712fb335a0bdb0edfaf71d479` |
| Development `decisions.csv` | `a31944aadc48f0ffd48e601086cd027a65ce6b098f9b203a8e2d75c10073a4f5` |

The raw labels and generated development outputs remain Git-ignored. Public
artifacts retain only their hashes and aggregate/decision facts; free-text
review notes are not projected into the result.

## Verification and defect re-injection

The new focused suite passes **12/12**. It covers profile limits, duplicate
concept evidence, complete-token matching, punctuation normalization,
serialization order, label/file drift, duplicate label identities, label-blind
execution order, write-once outputs, and the production-worker disconnect.

The original D03 plant-ROS defect was then re-injected by temporarily disabling
the required-group and title-anchor rejection paths. Its dedicated seam test
failed immediately; the `AcademicPrecisionDecision` invariant independently
rejected an `ACCEPT` carrying missing required groups. Reversing the temporary
patch restored all 12 tests. Latest Ruff and the CI-scope narrow Pylint check
also pass. The complete zero-network run finishes with **1,595 passed, 1
skipped and 609 subtests passed**. CI-scope coverage is **87.31%**, above the
unchanged 85% floor.

## Decision and next gate

The candidate may now be implemented in the already frozen U01-U08 live
harness, but this result does **not** authorize execution. A future run needs a
separate user authorization naming the merged revision, no more than eight
anonymous OpenAlex requests, and a cost soft stop. It must remain disconnected
from `pipeline_worker.py` and from report evidence.

After that run, a source-locked Schema-v2 packet must be reviewed without
substantive generative-AI judgment. Production remains prohibited unless the
unseen study simultaneously achieves at least six accepted cases, at least six
cases with relevant baseline-absent evidence, no more than 5% wrong accepted
sources, and complete URL attempts/labels.

## Supported claim

> A label-blind, deterministic conjunctive gate reproduced the intended result
> on nine development rows: 5/5 relevant candidates were accepted and 4/4
> known wrong candidates were abstained while preserving relevant coverage in
> all four cases. This qualifies an unseen disconnected study only; it is not a
> provider-wide precision, recall, report-quality, planner or production claim.
