# Offline claim-relative delivery and LLM-only review

Date: 2026-09-16. Scope: callback-only engineering controls, not provider
inference, semantic accuracy, production delivery or a reinterpretation of any
historical paid result. The [preregistration](prereg-2026-09-16-followup-claim-relation.md)
and [future LLM-only review policy](llm-review-policy.md) were committed as
`84d6513` before implementation.

## Implemented boundary

`run_claim_relation_followup(snapshot, claim, *, transport)` composes the
unchanged frozen catalog/core executor. The caller's proposition is preserved
verbatim. The final declaration contains exactly `claim_relation`, `answer`,
`supporting_evidence_ids` and `caveats`; the caller receives that declaration
and a separate code-derived state. The model cannot supply a second status.

- `supported` and `refuted` require an actually delivered, usable cited receipt
  and derive `answered_with_evidence`.
- `insufficient` requires usable delivered text, retains that read record,
  cites no supporting receipt and derives `abstained`.
- `unavailable` requires no usable delivered read and derives `abstained`.
  `not_checked` remains distinct from a checked missing/empty/out-of-range read.
- A whitespace receipt is delivered but not usable. A native model refusal has
  no invented relation; malformed or contradictory declarations fail closed.

The bridge substitutes the new final-format instruction in a detached request,
retains the catalog trust restrictions and native tool pairing, and checks the
complete transformed request against 12 KiB. Actual downstream delivery is
recorded only after preflight. The nested catalog audit is an earlier boundary,
not proof the downstream callback ran. A later response failure retains actual
receipt delivery; a preflight refusal cannot claim it. One read and two callback
entries remain the limit.

## Verification and failure history

Fresh fictional pump controls cover positive/negative propositions, all four
relations, refusal, missing/blank text, empty windows, invalid tools, strict
JSON/field bounds, forged receipts, mutation isolation, exact/over-budget
requests, late exceptions and actual result JSON round-trips. Maximum-length
legal fields and semantically unrelated but structurally legal declarations
are also retained as positive controls.

- Before-change full suite: 4,577 passed / 1,391 subtests, 264.92 seconds.
- Focused final suite: 60 passed, 1.54 seconds; zero provider requests.
- Two initial medium-tier validation failures were retained (20 passed / four
  failed, then 22 passed / two failed). Escalated diagnosis fixed a missing test
  assignment and exact catalog-refusal expectations, and corrected premature
  delivery recording rather than weakening the boundary assertions.
- Reinjecting premature delivery recording caused three targeted assertions to
  fail. Exact source restoration returned all 60 controls to green.
- Independent read-only LLM code review found no actionable issue in the new
  module/tests and relevant frozen dependencies. The reviewer did not execute
  tests; this was not semantic judging or backend-model attestation.
- Implementation full suite: 4,637 passed / 1,398 subtests, 268.42 seconds.
  Result/navigation links were added during that run; a separate final
  documentation check passed six tests / 707 subtests. These are not additive
  denominators or a claim that the in-flight suite observed every new link.
- Repository-wide `uv run --with ruff ruff check .` and narrow Pylint passed.
  CI has not run for this increment at the time of this record; its exact
  pushed-SHA outcome must be checked separately, not inferred from local tests.

## Limits and next gate

The relation is model-declared, not established semantic truth. A structurally
legal but wrong declaration still passes admission; `semantic_support` stays
`not_assessed`, `answer_verification` stays `not_verified`, and callback origin
is `injected_transport_unverified`. Scripted controls are not actual inference.

New semantic/reference/experiment judgments use explicitly labeled independent
LLM review, with no human-review prerequisite. Missing evidence or disagreement
does not become a pass, and simulated judgments cannot establish observed
adoption, willingness to pay or real time savings. Historical cohorts and
human declarations remain unchanged.

There is no new provider adapter, CLI, paid batch, search, retry, production
route or private-results publication in this increment. The next engineering
gate is a separately bound native transport and independent semantic controls,
not reusing an old paid runner or enabling the production Planner.
