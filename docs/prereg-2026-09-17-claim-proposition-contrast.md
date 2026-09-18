# PCQ proposition-contrast preparation

Date: 2026-09-17. Scope: new synthetic development controls, offline preparation
only. This document does not authorize a Qwen request or a production route.

## Hypothesis and irreversible history

The closed CLQ batch exposed a reference-design error: a claim that a record
reports a measurement is not the same proposition as a claim about the actual
physical value. Its frozen third label stays `insufficient`, its mismatch stays
a failure, and no CLQ case is repaired or rerun here. See the
[closed result](results-2026-09-16-claim-qwen-canary.md).

PCQ uses new fictional films, records and questions. PCQ01 and PCQ02 share the
same no-measurement record but assert different propositions. PCQ03 is a
separate explicit-measurement control. This deliberately dependent pair plus
one positive control is not three independent samples or an unseen accuracy
benchmark. There is no missing-text control; `unavailable` remains out of scope.

## Pre-review reference and blind projection

The author wrote all three questions, source texts, proposed references and
scripted rehearsal answers before dispatching independent semantic review.
The exact draft file is `tests/fixtures/report_evidence_claim_contrast.json`:

`bfc9347b28a7d284b8d959c93a038a14f1c15c9adb0d3394c9c6463012141c78`

Its `draft_before_llm_review` field records that authoring stage; do not rewrite
the bytes after seeing the judge. A dated result separately records whether
these bytes qualify as frozen development controls. A hash is an identity,
not proof of correct labels.

The fresh-context LLM sees only each case ID, verbatim claim, source title and
source text. It sees no author relation, proposition category, rationale,
scripted answer, old batch result, expected score or other review. No external
sources or workspace inspection are allowed. Judging follows the
[LLM-only policy](llm-review-policy.md); the review is model-generated, not
human expert gold. Record the full local prompt/input/output and their hashes;
publish only aggregate judgments and method limitations.

Rubric: support establishes the same proposition under its stated subject,
conditions and scope; refutation establishes an incompatible proposition;
insufficiency establishes neither despite usable text; unavailable means no
usable text. Ambiguity is reported as uncertain rather than forced to a label.
The reviewer must name the asserted proposition and quote exact source spans.
Literal quote checks do not establish semantic entailment.

Freeze only if all three independently proposed relations match the prewritten
references, all judgments are reviewable, no material ambiguity is identified,
and every supplied evidence quotation occurs in its own source. On disagreement
retain both judgments and stop this freeze; do not silently retune the questions
or labels and present a later agreement as first-pass independence.

## Offline delivery gate

Only after baseline tests pass, add a separate hash-bound preparation helper,
allowlisted review projection and scripted two-callback rehearsal. Rehearsal
must exercise the existing claim wrapper: a real local `read_source` receipt
must reach the second callback. Support/refutation cite that usable receipt;
insufficiency has no supporting IDs and an abstained state but retains the
delivered usable evidence. Observe the serialized result, not a precomputed
expected field. The original claim, source bytes, counters and immutable
`not_assessed` / `not_verified` / `injected_transport_unverified` flags survive.

Scripted success is an engineering observation, never native model success.
Include a control showing that a structurally valid wrong semantic relation
can still pass the existing wrapper. Re-inject a projection or delivery defect
in the new helper and require the seam regression to fail before restoration.
Run full zero-provider tests, latest Ruff, narrow Pylint and independent code
review. Do not change production, old experiments, their hashes, or score rules.

## Next live boundary

This helper has no paid mode and creates no provider client. Freezing these
controls alone does not establish live `insufficient` behavior. A future run
needs a separately frozen PCQ runner, dependency/code/fixture identity, bounded
ledger, fresh output directory, applicable budget authorization and green CI.
Never pass this fixture to the closed CLQ runner or reset its failed output.
Any post-run semantic judgment remains separate from mechanical accounting
and must be explicitly labeled LLM review.
