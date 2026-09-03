# Adaptive role-gap v8: AD unseen human-review result

**Date:** 2026-09-03 (Australia/Sydney)

**Status:** `complete / fail`; AD consumed; adaptive role-gap v8 sealed;
production Tool Calling remains disconnected

## Outcome

One eligible human review completed all 67 source rows from the exact AD01-AD08
run on revision `b54fa22666805f8d0de0ff7e26c42af88b641615`. The final strict
intake validated the source lock, packet manifest, every read-only candidate
field, all labels and visible role IDs before joining hidden route and lane
provenance. It then evaluated the same six conjunctive gates frozen before the
AD review implementation.

Three gates passed and three failed:

| Frozen gate | Observed | Required | Result |
|---|---:|---:|---|
| cases with relevant, baseline-novel evidence | 8/8 | at least 6/8 | pass |
| directly relevant candidate share | 33/67 (49.25%) | at least 25% | pass |
| human-correct routing decisions | 5/8 | at least 6/8 | **fail** |
| closure cases with selected-role value | 2/7 | at least 4/7 | **fail** |
| union role-coverable cases | 6/8 | at least 6/8 | pass |
| union gain over anchor coverability | +1 (6 versus 5) | at least +2 | **fail** |

Because all six gates were conjunctive, the strict decision is `fail`.
Adaptive role-gap v8 did not generalize from its AC development pass to the AD
unseen cohort. AD is consumed and must not be tuned or rerun as validation.

## Route findings

The deterministic route was human-correct for AD03, AD04, AD06, AD07 and AD08.
It was incorrect for AD01, AD02 and AD05 because directly relevant anchor
evidence already contained the mechanically selected role. Only AD04 and AD08
obtained closure-only evidence supporting the selected role.

Anchor evidence alone was human-coverable within three sources for AD01-AD05.
The bounded closure added only AD08, taking union coverability to 6/8. AD06 and
AD07 remained incomplete. This is the measured reason v8 failed: the adaptive
search often spent its second request on a role that the anchor already
covered, and the closure improved a complete role set in only one new case.

## Review audit history

The first returned packet contained 67/67 structurally valid labels: 32
`YES/YES`, 34 `NO/N/A`, and one `UNVERIFIABLE/UNVERIFIABLE`. Its declaration
mistakenly recorded `generative_ai_use=MOST_OR_ALL`. The strict first intake
therefore returned `excluded_substantive_ai / not_evaluated` before joining
hidden provenance or scoring any gate. The original declaration, labels and
excluded result are retained privately by hash.

The study owner then confirmed that the judgments were human-completed and no
generative AI had been used. Only the declaration's AI-use field was corrected
to `NONE`; the 67 labels were unchanged. That second strict intake returned
`not_inspectable / not_evaluated` because row `AD01/d871d82909fa` remained
explicitly unverifiable. It still did not join route provenance or expose gate
metrics.

The human reviewer subsequently inspected the publisher full text for that
single row while the packet remained route- and lane-blind. The row was revised
to `YES/YES`, its visible supported roles and source-grounded note were
completed, and the declaration was updated to `external_sources_checked=SOME`.
The other 66 judgments were unchanged. Only then did the strict intake join
hidden provenance and compute the final result above.

## Frozen identities

- executed revision:
  `b54fa22666805f8d0de0ff7e26c42af88b641615`;
- fixture SHA-256:
  `0be98f249bfd1eaf891cd3c20903b9d6ae4cd2d6431282ee32e82298a2d8ecc7`;
- source-lock SHA-256:
  `ac4aa3027e0675e7c24528b999a2d0113654703fbb2ad763913f3ecd814b0be8`;
- packet-manifest SHA-256:
  `f017b1d993f6c47acf974959b8de4214856aac3589c3856dddc081859489248f`;
- final labels SHA-256:
  `8b1b97782a6762351c8e66b67f054742fc5896d16674b27576205461dcf98c74`;
- final declaration SHA-256:
  `557867391b0f86aaa518bf73c055166c9a1aa5b0f41269d40201cac5f3c38fb2`;
- final strict-result SHA-256:
  `babfff8f7ffd1a73a20e6e385f272280b57a924ac0c5753d8676c97dd0f45933`.

## Limits and next decision

This is one human reviewer judging 66 rows from frozen titles and abstracts and
one row with publisher full-text assistance. It does not establish full-text
truth for the remaining sources, retrieval recall, inter-rater agreement,
planner-trigger precision, report improvement, user utility, latency or an
SLO. The AI-use correction was relayed by the study owner rather than supplied
as a separately signed reviewer amendment.

The failed unseen result retires adaptive role-gap v8. It does not authorize a
Planner trigger, source insertion, report-path integration or production Tool
Calling. Any later method must start with a new pre-registration and fresh
development/evaluation cohorts; it may use this result only as disclosed
development evidence.
