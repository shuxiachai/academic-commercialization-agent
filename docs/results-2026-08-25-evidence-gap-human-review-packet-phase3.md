# Result: Phase 3 human evidence-value review packet

**Date:** 2026-08-25  
**Source pilot revision:** `adde83dfd7d40c7fdd425b6f665eb121bb300e33`  
**Protocol:**
[`prereg-2026-08-25-evidence-gap-human-review-phase3.md`](prereg-2026-08-25-evidence-gap-human-review-phase3.md)

## Outcome

The separate human-review packet is prepared and the strict zero-network
intake path is implemented. This is a **packet-readiness result**, not a human
evidence-value result. All 25 label rows are still blank and the reviewer
declaration is unfilled, so the current protocol state is `incomplete`, both
headline metrics are `not_evaluated`, and production connection remains
unauthorized.

Preparing and summarizing the packet performed no provider, search, or LLM
call and incurred no incremental API cost. The original paid pilot directory
was read only; its four registered hashes remained byte-identical.

## Artifact separation and identity

The original write-once source remains:

`outputs/evidence-gap-phase3-live-20260825-adde83d/`

The reviewer works only in the separate local directory:

`outputs/evidence-gap-phase3-human-review-20260825-adde83d/`

| Source artifact | SHA-256 after packet preparation |
|---|---|
| `manifest.json` | `8989acda104e55066b91f42c7f3f78ec33141f440a9f91c6e2b322e315f6c84b` |
| `execution.json` | `2625c20b40d216fb067cbda307880342843ec22d38b76c1ea39e6762ce77b133` |
| `candidates.csv` | `0ba0c36518deff990dd36bf3c9a212aa1e61860c54bd0dd4ad273f5f50b762a5` |
| `review.csv` | `3eaee269f838c4d5b36a4dc16d1c797a713c9c95f2635c572686e8312020d52d` |

The packet manifest SHA-256 is
`cabc5353ab8f47b3fb1e8cd268c54eaf90424168607fadc604e845fffbb19004`.
It freezes all 25 `(case_id, accepted_source_id, title, URL)` identities and
their per-row hashes. The generated blank `labels.csv` is byte-identical to the
source blank `review.csv`; neither file is evidence of completed review.

## Intake contract

`evidence_gap_phase3_review.py` enforces the following boundaries before it
will calculate either exploratory metric:

1. all four source hashes and all five registered case definitions must still
   match the paid pilot;
2. the packet must contain exactly the same 25 full row identities, although
   rows may be reordered for reviewer convenience;
3. accepted label pairs are limited to `YES/YES`, `YES/NO`, `NO/N/A`, and
   `UNVERIFIABLE/UNVERIFIABLE`, with a source-grounded note on every completed
   row;
4. a reviewer must declare all rows attempted, external-source checking,
   elapsed time, completion date, and generative-AI use;
5. substantive AI judgment is retained as provenance but excluded from the
   human-value headline; and
6. any incomplete or unverifiable row produces `incomplete` or
   `not_inspectable`, never a zero-error pass.

Only an eligible, complete, fully inspectable review can evaluate the frozen
thresholds: at most one wrong source among 25 rows and novel relevant evidence
in at least three of five cases. Even a pass leaves planner-trigger precision
and the disabled-path regression gate unresolved.

## Current machine-readable state

The blank packet was immediately passed through the same summarizer and wrote
an immutable `initial-summary.json` with SHA-256
`d5f9e4f97edd9671941100443184047e3aa0ea00a37680dfc03347221fb61039`.

| Field | Observed value |
|---|---|
| Rows registered | 25 |
| Rows completed | 0 |
| Protocol status | `incomplete` |
| Decision | `not_evaluated` |
| Wrong-source rate | `not_evaluated` |
| Novel relevant case count | `not_evaluated` |
| Production connection authorized | `false` |

This explicitly distinguishes “not checked” from “checked with zero errors.”

## Verification and defect re-injection

The new zero-network review subset passed **17/17** tests. Two original defects
were then deliberately re-injected one at a time:

1. bypassing the full title/URL identity comparison made
   `test_label_title_drift_is_rejected_even_when_the_key_still_matches` fail
   because a changed source was accepted behind an unchanged join key; and
2. omitting `UNVERIFIABLE` rows from protocol-state selection made
   `test_unverifiable_row_is_not_inspectable_and_never_becomes_a_pass` fail
   because the result became `complete`.

Both defects were removed before the subset returned to 17/17 passing. The
complete zero-network suite then passed **1,463 tests plus 627 subtests**.
Latest Ruff and the narrow CI Pylint checks passed, and measured coverage was
**87.07%**, above the frozen 85% floor.

## Reviewer handoff and next gate

The reviewer should read the packet `README.md`, attempt every listed URL, edit
only `labels.csv` and `reviewer_declaration.csv`, and return the whole packet.
The study owner must then write the result to a **new** path; the summarizer
refuses to overwrite an earlier interpretation:

```bash
uv run python evidence_gap_phase3_review.py summarize \
  outputs/evidence-gap-phase3-live-20260825-adde83d \
  outputs/evidence-gap-phase3-human-review-20260825-adde83d \
  outputs/evidence-gap-phase3-human-review-20260825-adde83d/final-summary.json
```

No result should be described as a human-review pass until that strict intake
completes with `protocol_status=complete` and `decision=pass`.

## Supported claim

> A zero-network, provenance-locked review packet now carries all 25 live
> Tavily candidates through an immutable human-label intake; the packet is
> ready, but no human evidence-value result exists yet.

## Post-return status (2026-08-26)

The returned form later completed 25/25 rows, but its declaration recorded
`MOST_OR_ALL` substantive AI use and packet schema v1 had not exposed the
frozen baseline collection. The strict result is therefore
`excluded_substantive_ai / not_evaluated`; the generic adapter remains
disconnected. See the
[returned-form result](results-2026-08-26-evidence-gap-human-review-phase3.md).
