# Qwen evidence-set v5 post-outcome failure diagnostic

- Date: 2026-08-31
- Status: complete diagnostic; original v5 failure unchanged
- Network, model and retrieval calls: 0
- Production connection: not authorized and not performed

## Question and boundary

The schema-4 W01-W08 development run completed all 16 bounded Qwen calls but
failed its frozen disposition-agreement gate at 38/64. This separately frozen
post-outcome diagnostic asks which observable boundary prevented the 28
human-labelled relevant rows from surviving.

This is not a blind validation. Before the analysis plan was committed, the
aggregate v5 result, the earlier human totals and the two schema-invalid raw
responses were already known. The diagnostic cannot rescue v5, lower its gate,
reopen W01-W08, open X01-X08, or authorize production Tool Calling.

## Provenance and execution

The zero-network utility validated the complete 27-file Qwen artifact index,
then parsed the schema-4 manifest, execution, 16 call journals, eight case
decisions and 64-candidate aggregate through the committed Pydantic contracts.
Repeated call and decision files had to equal the copies already embedded in
the execution artifact.

The private side was independently locked before label parsing:

- the original v4 diagnostic source lock;
- the exact 64-row packet manifest;
- the completed human labels; and
- the already archived normalized reviewer declaration.

The first invocation correctly stopped before label joining because the raw
returned declaration used `0` for `external_sources_checked`, outside the
allowed vocabulary. The earlier review intake had preserved that raw file and
normalized the owner's confirmed meaning to `NONE`. An explicit analysis-plan
amendment changed only the declaration input identity to that existing
normalized artifact. No output had been written before the amendment.

All 64 label rows then had to match the mechanical packet on case, provider
index, candidate SHA, topic, title and URL. The eligible declaration states
that one reviewer read all rows, used no substantive generative AI and opened
no external sources. The labels therefore describe only the frozen titles and
abstracts; they are not source-truth or inter-rater evidence.

## Mutually exclusive failure partition

Every candidate was classified once, using persisted v5 state rather than a
counterfactual repair:

| Observable failure surface | All 64 | Human relevant (28) | Human irrelevant (36) |
|---|---:|---:|---:|
| Whole-batch invalid-pass exposure | 16 | 12 | 4 |
| Stable abstention in both valid passes | 37 | 9 | 28 |
| KEEP/ABSTAIN action instability | 5 | 2 | 3 |
| KEEP role-set instability | 5 | 4 | 1 |
| Deterministic post-consensus rejection | 1 | 1 | 0 |
| Stable retained candidate | 0 | 0 | 0 |

The largest single class among the 28 relevant rows was
`invalid_pass_exposure` at 12. This is an observable system boundary, not a
causal claim that every exposed candidate would have survived a different
schema.

For the five human-inferred semantic-link rows, two were exposed to an invalid
pass, two had role-set instability, and one was stably abstained. No one failure
class explains all five.

## What the two invalid responses show

W01 pass 2 and W07 pass 1 were valid JSON objects with the correct case ID,
candidate order, all eight decision rows and recognized actions. They failed
the strict response schema because role IDs were duplicated within individual
candidate decisions:

| Invalid pass | Candidates with duplicate role IDs | Extra duplicate role quotes |
|---|---:|---:|
| W01 pass 2 | 4 | 7 |
| W07 pass 1 | 2 | 2 |

The shape probe did not deduplicate those rows or run a repaired parser. Under
the frozen contract, one malformed batch still exposes all eight candidates to
`invalid_pass_exposure`. These observations establish schema fragility in two
calls, not the quality of any hypothetical repaired output.

## Order sensitivity

Among the seven valid calls in each pass position, pass one proposed 17 KEEP
rows out of 56 candidates while the reversed second pass proposed 8/56. Five
candidates changed action and five retained KEEP but changed exact role sets.

This directional 17-versus-8 observation is consistent with order sensitivity,
but one frozen run cannot separate ordering from ordinary model variability.
It does explain why simply accepting syntactically valid batches would not be
sufficient: the valid-valid cases still contained ten action or role-set
disagreements.

## Decision

Evidence-set v5 remains sealed and failed. The diagnostic does not justify:

- relaxing the 90% agreement gate;
- silently deduplicating duplicate roles;
- replaying W01-W08 until they pass;
- opening X01-X08;
- another paid v5 run; or
- production or report integration.

If this research line continues, a v6 proposal would need a new hypothesis and
new frozen challenge. Its design must address both response-schema robustness
and order stability before spending money. A schema-only patch is not enough,
because 16 of the 28 relevant rows failed elsewhere; an order-only patch is
also not enough, because two whole batches were lost before comparison.

The more conservative alternative is to stop this Tool Calling admission
candidate here. The existing deterministic evidence pipeline remains the
production path, while v5 serves as evidence that bounded tools and detailed
audits do not automatically produce a reliable semantic admission rule.

## Verification

The public aggregate seam was defect-reinjected by temporarily dropping the
computed `metrics` object. The boundary test failed with `KeyError: 'metrics'`;
restoring the implementation returned the focused diagnostic suite to 11/11.
The complete zero-network suite then passed 1,798 tests plus 657 subtests.
Latest Ruff and the CI-equivalent narrow Pylint gate also passed.

## Artifacts

- Analysis plan:
  `docs/prereg-2026-08-31-openalex-evidence-set-v5-qwen-failure-diagnostic.md`
- Zero-network utility: `openalex_evidence_set_failure_diagnostic.py`
- Regression seams:
  `tests/test_openalex_evidence_set_failure_diagnostic.py`
- Private row-level result: retained only in the separate private notes
  repository.
