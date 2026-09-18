# Offline claim-relation contract

Registered 2026-09-16 before implementation. Protocol:
`report_evidence_claim_relation_v1`. This is a new callback-only prototype,
not a paid protocol, a production route or an amendment to a frozen batch.

## Hypothesis and scope

An explicit caller-owned proposition and a model-declared evidence relation
can separate a supported negative answer from insufficient evidence without
letting the model independently choose a conflicting delivery status.
Structural consistency does not establish that the relation is semantically
correct. Use new synthetic controls only; do not republish private observations,
change historical labels or turn old failures into successes.

Add `run_claim_relation_followup(snapshot, claim, *, transport)` in a separate
module around the frozen catalog callback path. The original claim is preserved
verbatim and is not extracted or rewritten by another model. Do not change
existing snapshots, core loops, provider adapters, runners or production paths.
No new CLI, credentials, provider requests, search, retry or persistence.

## Model declaration and code-owned delivery

The strict final JSON contains exactly `claim_relation`, `answer`,
`supporting_evidence_ids` and `caveats`; no independently supplied `status`.
Relations apply to the caller's proposition, not positive/negative wording.

| Declaration | Meaning | Required actual read | Derived delivery |
| --- | --- | --- | --- |
| `supported` | The model judges the same claim, conditions and scope supported | One cited usable receipt | `answered_with_evidence` |
| `refuted` | The model judges evidence to support a conclusion incompatible with the claim | One cited usable receipt supporting the refutation | `answered_with_evidence` |
| `insufficient` | Nonempty saved evidence does not establish support or refutation | Usable read; no supporting IDs | `abstained` |
| `unavailable` | No usable read actually reached the callback | No supporting IDs | `abstained` |

Usable means a code-owned successful nonblank saved read was delivered, not
that it is relevant, complete publisher text or semantically entailing. Retain
served evidence on abstention. Preserve `no_read`, missing text and empty or
out-of-range windows separately; absence is not a claim about all literature.
Model refusal may abstain with no relation declaration; protocol failure is
`failed`, not invented insufficiency. Contradictory declarations fail rather
than being silently repaired. A wrong but well-formed semantic declaration can
still pass structure; record that limitation explicitly.

The bridge maps the accepted declaration to the frozen core's old envelope,
preserving answer bytes and admitted IDs. A new serialized result preserves
the full declaration/caveats and original claim. All semantic verification
fields remain unverified; a scripted callback is not actual LLM inference.

## Seams and limits

Replace conflicting old final-format instructions in detached callback messages
with the new code-owned contract, retaining snapshot-only tools, untrusted
source/catalog treatment, saved-text limitations and the original budget.
Keep the caller claim, separate catalog message and native tool pairing intact.
Recount the full transformed request against the existing 12 KiB bound. Record
actual delivery only immediately before invoking the downstream callable.
Pre-forward refusal does not deliver a receipt; later response failure does not
erase a delivered receipt. At most one read and two callback invocations.

Strictly reject extra fields, duplicate keys, nonfinite values, wrong types,
oversized answers/caveats, forged or undelivered IDs and extra tool requests.
The old envelope after translation must also fit the frozen message limit.
No keyword heuristic infers claim polarity or forces a relation from prose.

## Frozen offline acceptance and review

Fresh fictional pump controls cover support, explicit refutation, nonempty but
insufficient evidence and no readable text. Include positive and negative
propositions, early final/refusal, malformed declarations, contradictory read
states, forged IDs, callback mutation/exception and over-budget transformed
requests. Assertions observe actual callback arguments and serialized results,
not only isolated fields. A deliberately unrelated yet structurally legal
declaration must remain explicitly unverified, not become semantic proof.

Reinject a mapping/delivery defect, observe a meaningful failing assertion,
restore exact bytes and rerun. Require pre/post full zero-provider tests,
latest Ruff, narrow Pylint and independent read-only LLM code review. Baseline:
4,577 tests / 1,391 subtests, 264.92 seconds.

All subsequent semantic judging uses the separate
[LLM-only review policy](llm-review-policy.md); no human review prerequisite.
This phase uses scripted engineering controls, not another paid semantic
evaluation. Model judgment, structural admission and actual user adoption are
different evidence. Success authorizes neither production nor paid inference.
