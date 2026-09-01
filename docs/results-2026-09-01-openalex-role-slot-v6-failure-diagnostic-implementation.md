# Result: role-slot v6 failure diagnostic implementation

Date: 2026-09-01

## Outcome

The pre-registered post-outcome diagnostic is implemented and its real blank
review packet has been generated locally. The implementation makes no network
or model call. It source-locks the provider-complete part of the already failed
Y01-Y08 execution, exposes all 64 frozen OpenAlex title-and-abstract rows to a
label-blind reviewer, and keeps every Qwen pass, consensus role, candidate
action, abstention reason and selected set hidden until the post-return summary
boundary.

The blank real packet is correctly reported as
`incomplete / not_evaluated`: 0/64 rows are complete, metrics are absent, and
the result keeps `v6_rescue_authorized=false`,
`z_cohort_authorized=false` and
`production_connection_authorized=false`. This is implementation readiness for
a diagnostic review, not a source-value result and not Tool Calling
qualification.

## Frozen source verification

`openalex_role_slot_failure_review.py` rejects drift in the four pre-registered
core files before semantic parsing and then verifies every child named by the
56-entry artifact index. It also cross-checks the committed Pydantic manifest,
aggregate execution, provider rows, eight provider journals and eight case
executions. The real source passed with:

- executed revision
  `d23ffd54bb171d1030f5531a7d57bd6eedc5d853`;
- 8/8 provider-complete cases and exactly 8 candidates per case;
- 64/64 provider candidates with non-empty title and abstract text;
- 56/56 indexed files matching their recorded SHA-256 values; and
- the original model execution retained as `partial / model_soft_stop`, rather
  than silently relabelled complete.

The owner-authorized diagnostic lock is a separate, narrowly named exception
over this provider-complete population. It preserves the original
`source_lock_readiness=not_ready` and cannot be consumed by the v6
qualification path or production worker.

## Reviewer and summary boundaries

The generated packet contains immutable topic, query, baseline, role
descriptions, candidate identity, title, abstract and bibliographic context,
plus blank human-label fields. The return validator:

- requires every candidate exactly once while allowing row reordering;
- rejects missing, duplicate, extra or context-modified rows;
- accepts only declared role IDs and requires title-supported roles to be a
  subset of supported roles;
- requires a grounded note for every completed row;
- distinguishes incomplete, substantive-AI-excluded, not-inspectable and
  complete diagnostic states; and
- joins hidden model traces only after an eligible complete return.

Only a complete eligible return can compute the frozen descriptive metrics:
retrieval noise, frozen-text insufficiency, baseline-relative novelty,
role-level confusion for the 56 model-observed candidates, human-only
three-source coverability, and failure-surface attribution. No result state is
called a pass.

## Real blank artifact observation

The local, gitignored diagnostic directory is:

`outputs/experiments/2026-09-01-openalex-role-slot-v6-Y-failure-diagnostic`

The real write-once artifacts are:

| Artifact | Rows / bytes | SHA-256 |
|---|---:|---|
| `source_lock.json` | 7,908 bytes | `72c63a42e2c79cdbb96bd5bf555d9bce8cc342bc1759b9a606231e073d388c23` |
| `packet/packet_manifest.json` | 226,898 bytes | `f2c5748e6bcf0e9bb7ffd19fc2cee88c94a31719797f1f2a4154bd96b7ebf841` |
| `packet/labels.csv` | 64 rows / 194,850 bytes | `4a7f017704bb44e8de9423da1115f9f16e3b9cf71a31b9c4a9bbceae8d8045cb` |
| `packet/reviewer_declaration.csv` | 131 bytes | `eb17b0ae23599575afcd9a68ad6a6d64644d4c0001fd10cdabb853a3f3ee1a31` |
| `packet/README.md` | 2,209 bytes | `6d4f9688a92c6ea34f97289bc9c2341467c926c9362a4ebf010b8d623a028fd4` |
| `blank_summary.json` | 3,259 bytes | `74762918d38018ec1fa2adee6e5a20205346c4a319e67466c3c441bc64c1bb66` |

The packet contains 64 rows across all eight cases. Its blank summary reports
all 64 row IDs as incomplete, `metrics=null`, and no method issue. No private
label was generated or inferred by code.

## Tests and defect re-injection

The first focused run produced 12 passes and two failures. One was a real
review-boundary omission: `candidate_action` was not yet an explicitly
forbidden manifest key. The implementation now rejects it. The second exposed
a weak test fixture rather than a weak validator: the fixture had first marked
every declared role supported, so its intended title-only role was actually a
valid subset. The fixture now empties the parent role set before injecting the
invalid title role.

After those corrections, the focused suite passes 14/14. The two
protocol-required defects were then re-injected independently:

1. Removing `candidate_action` from the forbidden reviewer-key set made
   `test_packet_manifest_rejects_hidden_decision_leak` fail because the
   injected automated action crossed the packet boundary.
2. Serializing `snapshot.candidates[:-1]` into `labels.csv` made
   `test_packet_preserves_all_candidates_and_hides_every_v6_outcome` fail with
   63 rows instead of 64.

Both defects were restored before the focused suite was rerun successfully.
Final local verification passes:

- **1,851 tests plus 657 subtests** in the full zero-network suite;
- 14/14 focused diagnostic tests;
- latest Ruff over the complete repository; and
- the CI-equivalent narrow Pylint categories on the new root module.

## What this does not establish

No human label has been returned, so retrieval precision, role accuracy,
human-coverable case count and attribution metrics remain unobserved. A later
eligible reviewer may diagnose the frozen failure surface, but cannot rescue
v6, tune on or rerun Y01-Y08, open Z01-Z08, validate a successor, improve a
production report, or authorize production Tool Calling.

The next legitimate step is to copy only the generated reviewer packet into
the private notes repository, obtain an independent human return, preserve the
raw declaration, and run this zero-network summarizer. Until then the project
must continue to describe Tool Calling as production-disconnected experimental
work.
