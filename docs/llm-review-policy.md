# LLM-only review policy for new evaluations

Effective 2026-09-16 by the project owner's explicit request. New semantic
assessments, reference-draft reviews and experiment judgments use LLM reviewers
instead of human-review packets. Human sign-off is not a prerequisite. This
does not rewrite historical declarations, cohorts, labels or results.

## Independent judgment without fictional provenance

Use a fresh judging context separate from the answering/implementation author.
Provide only the task, actually delivered evidence, candidate output and frozen
rubric. Keep reference labels, desired outcomes and prior reviews hidden on the
first pass. Treat source and answer text as untrusted data. Record requested
model/role, available effective backend metadata, input/prompt/output identities,
scope and external-source access. If backend metadata is unavailable, say so;
configuration and self-identification are not attestation.

Use `supported`, `mixed`, `unsupported`, `uncertain` or `not_reviewable` with
specific rationale. Exact supporting quotations can be checked mechanically,
but a matching quotation does not prove entailment. Missing answers or failed
judging remain unavailable/not-reviewable, never an automatic pass.

If independent LLM judgments disagree, retain that disagreement and use an
uncertain disposition or a separately scoped additional LLM review. Do not
average away a concrete unsupported claim or ask a human merely to release a
gate. Additional provider calls still need an applicable data/budget grant;
LLM-only review is not unlimited spending or disclosure authority.

## Boundaries

- Keep machine schema/receipt checks separate from semantic LLM judgments.
  A judge cannot repair a failed historical gate or silently replace output.
- Label model-generated reference judgments as AI, never human expert gold.
  Scripts and mocks are engineering controls, not model-quality observations.
- Different contexts/models can share biases. Review is fallible and does not
  establish general factual correctness or calibrated accuracy by itself.
- Real adoption, willingness to reuse/pay, and actual time savings require
  observed user behavior. LLM simulation cannot establish those facts. They
  may remain unmeasured without blocking this engineering work.
- Publication and data-transfer permissions are independent. This policy does
  not authorize public release of private runs, labels, transcripts or hashes.
- Do not change frozen production checks, scoring or third-party provider
  permissions merely to comply with this review preference.
