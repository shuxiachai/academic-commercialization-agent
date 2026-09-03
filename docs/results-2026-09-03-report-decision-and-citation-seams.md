# Result: report decision and citation seams

Date: 2026-09-03

## Outcome

The pre-registered P1 change is implemented and qualifies for delivery as a
zero-network reliability improvement. It does not change scoring, block a paid
report, enable production Tool Calling, or claim that an advisory heuristic has
verified the report.

The delivered Markdown now contains a localized, code-owned applicability
block with the exact assessment mode, actor-specific GO/NO_GO permission, and
success-criteria provenance. Decision Context distinguishes three states:
`not_established`, `user_supplied_unapproved`, and `owner_approved`. A bare
approval field without criteria is invalid, and both the criteria and approval
state participate in the immutable run and checkpoint identity.

## Report audit

The post-generation audit is deliberately narrow and non-blocking:

- only pre-registered decision-gate phrases are considered, while broad factual
  uses of `minimum`, `at least`, and bare `threshold` remain outside scope;
- electrolyte-family contradictions require exactly one claimed family, valid
  citations, sufficiently long non-snippet evidence, and an explicit different
  family in every cited source;
- matching, mixed, short, snippet, missing, multilingual, and otherwise
  undecidable evidence produces an abstention or unavailable state rather than
  a mismatch;
- full findings are written to `report_audit.json`, while bounded counts and
  check status cross `status.json`, both API endpoints, and the browser.

The frozen 30-report baseline remains at zero threshold findings and zero
material-family mismatches among the 23 checkable segments. The known Qwen
example produces both the unqualified-threshold warning and the sulfide-claim
versus oxide-source mismatch. The 40 baseline segments that were not decidable
remain recorded as unverifiable and are never presented as cleared.

## Verification

- New and directly affected subset: 60 tests plus 2 subtests passed.
- Full zero-network suite: 2,009 tests plus 660 subtests passed.
- Latest Ruff: passed.
- Narrow Pylint `E0701`: 10.00/10.
- Loopback Chromium smoke: passed with zero external requests, zero mutation
  attempts, zero paid-provider requests, zero page errors, and zero console
  errors.
- Defect reinjection: removing the applicability block from the persistence
  seam made its delivery test fail; suppressing the material mismatch made the
  known-Qwen audit test fail. Both defects were restored and the same tests
  passed.

## Interpretation limits

This result makes two observed failure classes inspectable. It does not prove
semantic entailment in general, source truth, decision correctness, or user
value. Non-English reports currently expose the deterministic applicability
block but report the English-only heuristic audit as unavailable. Findings are
review warnings and never discard, retry, or rewrite a completed report.
