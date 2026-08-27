# Result: claim-scope v3 source-lock and human-review boundary

**Implemented:** 2026-08-27

**Authority:** zero-network implementation and packet preparation only. This
does not label a source, pass the source-value gate, authorize a planner study,
or connect Tool Calling to production.

## Why a separate review module exists

The completed v3 run passed its mechanical 6/8 accepted-case gate, but its 13
accepted rows are still model-free heuristic decisions rather than source
truth. Reusing the older D01-D04 review module would silently substitute a
different case set, denominator and candidate identity. The new
`openalex_claim_scope_review.py` therefore freezes this execution separately
instead of rewriting an earlier experiment after observation.

## Implemented boundary

The module provides three explicit zero-network operations:

1. `lock` validates and binds all four aggregate files, the artifact index and
   eight case journals to their exact SHA-256 values and the executed revision;
2. `prepare` creates a separate Schema v2 packet containing the frozen
   baseline, claim-scope profiles, provider abstract/metadata, aboutness signals
   and exact acceptance provenance for all 13 candidates;
3. `summarize` revalidates the source bytes, source lock, packet manifest,
   candidate identities, labels and reviewer declaration before calculating
   any metric.

The live output stays immutable. A reviewer edits only `labels.csv` and
`reviewer_declaration.csv` in the separate packet. Reordering is allowed;
changing case id, provider result index, candidate hash, title or URL is not.

The result states remain distinct:

- a blank or partial return is `incomplete / not_evaluated`;
- substantive generated judgments are
  `excluded_substantive_ai / not_evaluated`;
- unattempted or uninspectable sources are
  `not_inspectable / not_evaluated`;
- only a complete eligible return can produce `pass` or `fail`.

The frozen pass rule remains unchanged: accepted candidates in at least 6/8
cases, zero or at most 5% directly irrelevant rows, novel relevant evidence in
at least 6/8 cases, every source attempted, and no substantive generative-AI
judgment. A pass still authorizes no production connection.

## Verification

Sixteen focused zero-network tests cover the source lock, all source and
candidate identities, visible baselines, blank-packet semantics, each value
gate, substantive-AI exclusion, source-attempt declarations, uninspectable
sources, mechanical-gate refusal, journal drift, packet baseline drift, label
identity drift and the production import boundary.

The lock-after-drift defect was then re-injected by temporarily disabling the
expected-hash comparison. A journal received one whitespace-only byte change,
so its parsed model remained identical. The seam test failed because no
exception was raised. Restoring the byte check made the same test pass again.
This demonstrates that the test protects the content-addressed boundary rather
than merely detecting invalid JSON.

The real source directory independently validates as 13 candidates, eight
baseline contexts and 13 joined candidate contexts. The study owner then
created source lock `479fd2a7...` and packet manifest `b3c62047...` in the
separate private artifacts repository. Summarizing that exact blank packet
reported 0/13 complete rows, `incomplete / not_evaluated`, all 13 row ids
explicitly missing, and no calculated provider metric. No human labels have
been supplied, so the current source-value state remains `not_evaluated`.

