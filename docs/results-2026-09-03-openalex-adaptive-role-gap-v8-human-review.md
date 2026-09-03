# Adaptive role-gap v8 AC human-review result

**Date:** 2026-09-03 (Australia/Sydney)

**Status:** eligible human review completed; all six frozen development gates
passed; AC consumed; AD remains unopened; production remains disconnected

## Bound evidence

The zero-network summarizer validated the exact AC01-AC08 provider run, source
lock, packet manifest, all 64 candidate identities, every immutable reviewer
field, all role IDs and every row-level note before joining the hidden route
and retrieval-lane provenance. No provider request or model call occurred
during intake.

| Artifact | SHA-256 |
|---|---|
| source lock | `237a9b901d055a4d325316042e7ae343c465659e1428d209be35d4f4e0607659` |
| packet manifest | `6d53a097d7c2cf046f2ac49dc7dc47a793b727a1fcff5dd56586e8f2791ef2bb` |
| unchanged 64-row labels | `5d9fd791de5cdacb6379592bfc0475756e474f6958f3d042c1478365e661eb65` |
| first returned declaration | `924170b0df14b23434257d3f677c2166d161c5c5c7642b51b421cf7b9d6c8be6` |
| first strict excluded result | `2f04bd9523cd88da225f10a9a176350c7e232cbbcf62a8026733c01cd6bac9aa` |
| owner-relayed correction | `c97f116258d2037d1597d1c3ea001d582cb2de0d2ce19fa6528219e14b2269df` |
| corrected declaration | `c9c94af60515f30de9fdb015b702fdafc4b7b4be06148e20eb8f1a811f444e3d` |
| corrected strict result | `7651aa1f7d6de14b05b3ee33fc0e2b8828e7bc168f44cdc0f1750b568998b187` |

## Declaration correction

The first returned declaration recorded `generative_ai_use=MOST_OR_ALL`. The
strict first intake therefore correctly produced
`excluded_substantive_ai / not_evaluated`, did not join hidden provenance and
ran none of the six gates. The study owner subsequently relayed that the
substantive judgments were completed by a human reviewer and that this field
was a filling error. The original declaration, excluded result, owner-relayed
correction and corrected declaration are retained in the private audit archive.
No candidate label, role assignment, note or other declaration field changed.

The superseding declaration records `reviewed_all=YES`,
`generative_ai_use=NONE`, `external_sources_checked=NONE`, 60 elapsed minutes,
and expertise in academic literature screening and evidence synthesis. This
makes the review eligible under the frozen protocol, while the correction
remains an owner-relayed attestation rather than a separately signed reviewer
amendment.

## Frozen gate result

All 64 rows were complete and inspectable. The reviewer marked 31 candidates
directly relevant and baseline-novel and 33 not directly relevant; no row was
unverifiable.

| Frozen gate | Observed | Required | Result |
|---|---:|---:|---|
| cases with relevant, baseline-novel evidence | 8/8 | at least 6/8 | pass |
| directly relevant candidate share | 31/64 (48.44%) | at least 25% | pass |
| human-correct routing decisions | 7/8 | at least 6/8 | pass |
| closure cases with selected-role value | 5/7 | at least 4/7 | pass |
| union role-coverable cases, at most three sources | 6/8 | at least 6/8 | pass |
| union coverability gain over anchor | +3 (6 versus 3 cases) | at least +2 | pass |

The anchor alone was coverable in AC04, AC06 and AC08. Adding the bounded
closure result made AC01, AC03 and AC05 newly coverable, producing the required
three-case gain. AC02 and AC07 remained incomplete. Seven routing decisions
were human-correct; AC06 was the exception because its anchor already contained
directly relevant evidence for the mechanically selected
`manganese_oxide_ion_sieve` role. Selected-role closure value was present in
AC01, AC03, AC05, AC06 and AC07.

Because all six gates are conjunctive and all passed, the strict result is
`complete / pass` and `ad_evaluation_eligible=true`.

## Interpretation

This development result supports the v8 hypothesis that a bounded second call
can be more useful when it targets one observed role gap instead of repeating a
fixed broad query. It also preserves abstention: AC08 made only its anchor call
because the mechanical screen observed no missing role.

The pass does not validate the method on unseen topics. AC01-AC08 are consumed
development cases and must not be rerun, tuned and represented as validation.
The next permitted step is a separate pre-registration for the already frozen
AD01-AD08 cohort, followed by separately authorized provider execution and an
eligible source-locked review.

## Limits and production decision

This is one reviewer judging frozen titles and abstracts without opening
external sources. It does not establish full-text source truth, recall,
inter-rater agreement, planner-trigger precision, report improvement, user
utility, latency or an SLO. The owner-relayed declaration correction is also a
method limitation that must remain visible.

AD01-AD08 remain unopened. The AC pass does not authorize the Planner, report
insertion or production Tool Calling. Production remains in zero-call shadow
mode until an unseen AD evaluation, disabled-path regression checks, trigger
precision and report-value evidence are separately completed.
