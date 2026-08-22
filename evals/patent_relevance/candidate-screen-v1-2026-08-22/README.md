# Patent topic-slot review screen v1 — result

This directory archives the first frozen candidate evaluated against the
completed 81-case human patent-relevance audit.

- Pre-registration commit: `b011f86`
- Frozen implementation commit: `aeb3d18`
- Network/API calls: zero
- Design: post-hoc development, not held-out validation
- Production retrieval change: none

## Outcome

The candidate **failed** its pre-registered gates.

| Metric | Baseline / requirement | Candidate | Outcome |
|---|---:|---:|---|
| Direct precision among auto-kept cases | 85.2% baseline; improve by ≥2 pp | 35/37 (94.6%), +9.4 pp | Pass |
| Human `RELEVANT` sent to `DROP` | 0 required | 6 | **Fail** |
| Human `IRRELEVANT` leaving `KEEP` | 2/2 required | 2/2 | Pass |
| Human `WEAK` leaving `KEEP` | ≥6/10 required | 8/10 | Pass |
| Manual-review load | ≤20/81 required | 36/81 (44.4%) | **Fail** |
| Frozen case hashes | 81/81 required | 81/81 | Pass |

The precision gain is therefore not an operational improvement: it was bought
by auto-dropping six relevant patents and sending another 28 relevant patents
to manual review. `qualified_for_held_out_challenge` is false and
`production_change_authorized` remains false.

## What failed

The final token of a technology phrase is not a safe universal anchor. The six
relevant auto-drops used legitimate neighbouring language:

- CAR-T treatment/manufacturing without the literal word `therapy` (2 cases);
- carbon `sequestration` without `storage`;
- CRISPR methods for `altering expression` without `editing`;
- a graphene flexible solar cell without `electronics`;
- sodium-ion `energy storage` material without `battery`.

The application-slot rule was also too broad: 36 cases entered `REVIEW`,
including 28 relevant patents. Conversely, two weak quantum-computing patents
remained in `KEEP` because their snippets contained apparently focused drug
discovery language outside the frozen generic-list windows. A lexical snippet
screen cannot reliably distinguish the invention's claim scope from background
or illustrative uses.

This is a useful falsification result. The next candidate must use a different
method—claim-scope or semantic evidence with explicit abstention—not another
threshold adjustment to this lexical rule. Any successor requires a new
pre-registration and a genuinely unseen challenge before production use.

## Reproduce

```bash
uv run python patent_relevance_candidate.py \
  benchmark_fixtures \
  evals/patent_relevance/human-review-2026-08-22/labels.csv \
  evals/patent_relevance/human-review-2026-08-22/manifest.json \
  outputs/patent-relevance-audit/reproduced-candidate-v1 \
  --challenge evals/patent_relevance/sodium-ion-grid-storage-challenge.json
```

`decisions.csv` preserves every action, reason, anchor, feature, and human label.
`result.json` preserves the aggregate metrics, corpus split, gates, and frozen
candidate constants.
