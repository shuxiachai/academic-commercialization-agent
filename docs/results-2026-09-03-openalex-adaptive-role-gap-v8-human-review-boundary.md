# Adaptive role-gap v8 AC human-review boundary

**Implemented:** 2026-09-03

**Source provider run:** AC01-AC08 on merged revision
`59b5870614d23c0d9c61e7e398fa363026b6a528`

**Production connection:** false

**Provider or model calls made by this boundary:** 0

## Outcome

A production-disconnected source lock, route- and lane-blind Schema v2 packet,
and strict human-label intake now cover the exact completed v8 AC provider run.
The boundary does not open AD01-AD08 and is not imported by the production
worker or provider adapter.

The source validator checks the exact artifact-index digest before parsing it,
then independently recomputes all thirty-eight indexed hashes. It parses and
rejoins the manifest, execution aggregate, fifteen one-attempt request
journals, eight deterministic route journals, eight deduplicated portfolios,
and all seven aggregate CSVs. Both original review CSVs must still be blank.
This rejects not only corrupt bytes but also a different mechanically valid v8
run.

The real source reconstructed as:

- 39 locked files including the index;
- 15 successful one-attempt requests;
- 8 checked route decisions and 7 selected closures;
- 90 provider rows: 72 abstract-bearing candidates and 18 provider-schema
  rejections;
- 64 DOI/OpenAlex-deduplicated review candidates; and
- USD 0.015 provider-reported anonymous-budget usage.

## Blindness and result semantics

The reviewer sees all sixty-four titles and abstracts, the frozen baseline,
and the five role descriptions for each case. The packet omits lane membership,
provider rank, duplicates, route action, signal observations, missing roles,
selected closure role, computed coverability and aggregate answers.

Only after every candidate label and the declaration validate may intake join
the hidden provenance. It then computes:

1. relevant-and-novel case coverage;
2. directly relevant candidate precision;
3. human-grounded routing correctness;
4. selected-role value from closure-only candidates;
5. union coverability using at most three sources; and
6. coverability gain over the anchor alone.

A human cover requires every required role, at least one scope role, and at
least one supporting role. A search route is correct only when the selected
role is absent from directly relevant anchor rows. An abstention is correct
only when the anchor's directly relevant, baseline-novel rows are already
coverable. A cross-lane duplicate cannot earn incremental closure credit.

Incomplete, substantively AI-generated, unconfirmed, and unverifiable review
states remain distinct from pass. The exact raw reviewer declaration and file
hash are retained alongside its normalized interpretation.

## Real blank-state audit

The source lock and blank packet were generated in the separate private notes
repository. Their identities are:

- source-lock SHA-256:
  `237a9b901d055a4d325316042e7ae343c465659e1428d209be35d4f4e0607659`
- packet-manifest SHA-256:
  `6d53a097d7c2cf046f2ac49dc7dc47a793b727a1fcff5dd56586e8f2791ef2bb`
- blank labels SHA-256:
  `e2bd72797f6e3331cb3a82a4aed7cb54a2820b349575921ca8f5d712d1af3231`
- blank declaration SHA-256:
  `eb17b0ae23599575afcd9a68ad6a6d64644d4c0001fd10cdabb853a3f3ee1a31`

Strict intake reports `incomplete / not_evaluated`, 0/64 completed rows, no
route assessments, no provenance join, and `ad_evaluation_eligible=false`.
This proves that an available source denominator with no human work cannot be
misreported as a zero-error pass.

## Verification

- 15/15 focused zero-network review tests passed.
- The complete suite passed: **1,943 tests and 657 subtests**.
- Latest Ruff passed repository-wide.
- CI-equivalent narrow Pylint passed.
- The real AC directory passed 39-file, 64-candidate, 15-request and 8-route
  reconstruction.

The route-leak defect was re-injected by adding `frozen_route_decision` to the
reviewer projection. The packet-boundary test failed on that hidden field and
passed again after restoration. Assertions were not weakened and no test was
skipped.

## Interpretation and next step

This completes the review infrastructure, not the source-value experiment.
The sixty-four rows still require an eligible independent human review. Until
then, all six gates are `not_evaluated`, AC has neither passed nor failed human
qualification, and AD01-AD08 must remain unopened.

If the eligible AC review passes all six frozen gates, the next permissible
step is a separately pre-registered AD evaluation. If any gate fails, v8 is
sealed. Neither outcome by itself authorizes production Tool Calling.
