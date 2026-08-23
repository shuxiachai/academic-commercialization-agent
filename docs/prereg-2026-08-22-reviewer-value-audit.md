# Pre-registration: blinded audit of Reviewer value

**Registered:** 2026-08-22, before any human preference labels were collected
**Cost:** zero API calls; existing topology-ablation artifacts only

> **Status (2026-08-23): complete.** Two evaluator forms completed all nine
> report pairs and independently passed the frozen criterion. See the
> [result report](results-2026-08-23-reviewer-value-audit.md). The thresholds
> below remain unchanged from registration.

## Question

The full topology's Reviewer accepted 34 corrections across 9 of 29 successful
reports. "Accepted by the structural guardrail" does not mean "helpful to a
reader." This audit asks whether the delivered, reviewed report is actually
better than its validated Writer draft.

## Historical-data boundary

The 90-cell experiment persisted each Writer draft, delivered report, Reviewer
notes, and the number of accepted correction-plan items. It did **not** persist
the original structured `find` / `replace` / `reason` objects. Character or
token diffs cannot reconstruct those objects one-to-one: the 34 plan items
produce 51 token-level edit opcodes. Therefore:

- the audit unit is one complete report pair, giving 9 cases;
- the 34 count describes how many plan items produced those pairs;
- no result from this audit may be described as "34 corrections independently
  judged" or as a correction-level accuracy rate.

This limitation is preferable to manufacturing a more precise-looking sample
from an irreversible diff.

## Blinding and packet construction

`reviewer_audit.py prepare` strips deterministic Reviewer Notes, shuffles the
9 cases with a fixed seed, and randomly assigns the reviewed report to A or B.
The packet contains only the A/B reports, rubric, manifest, and blank form. The
answer key is required to live outside the packet directory.

For each pair, an evaluator records:

1. overall preferred version;
2. version with better citation support;
3. version with greater commercialization-decision usefulness;
4. whether either version contains a harmful change;
5. confidence from 1 to 5 and a short rationale.

Allowed A/B judgments are `A`, `B`, `TIE`, and `UNCERTAIN`. Harm uses `A`, `B`,
`NONE`, or `UNCERTAIN`. Empty means **not evaluated**, never tie or pass.

## Pre-registered decision rule

The Reviewer is provisionally supported only if all 9 cases are completed and:

- the reviewed version is preferred in at least 6 of 9 reports;
- the reviewed version is identified as harmful in at most 1 of 9 reports;
- the draft has better citation support in at most 1 of 9 reports.

This is a small, one-experiment audit. Passing supports retaining the Reviewer
for a larger independent evaluation; it does not prove general user value.
Failing means the six-node topology has not justified the Reviewer's extra cost
and latency. A tie-heavy result is inconclusive, not positive.

## Execution

```bash
uv run python reviewer_audit.py prepare \
  outputs/ablation/20260821T234300Z-7dd894ef \
  outputs/reviewer-audit/20260822-packet \
  outputs/reviewer-audit/20260822-answer-key.json \
  --seed 20260822

# Fill outputs/reviewer-audit/20260822-packet/review_form.csv without opening
# the answer key, then unblind once every row is complete:
uv run python reviewer_audit.py summarize \
  outputs/reviewer-audit/20260822-packet/review_form.csv \
  outputs/reviewer-audit/20260822-answer-key.json \
  outputs/reviewer-audit/20260822-summary.json
```

For a resume-grade claim, two independent evaluators should complete separate
copies of the packet before either sees the key. Agreement and disagreements
should be reported alongside the aggregate outcome.
