# Reviewer comparison: execution preparation

Date: 2026-09-30. Status: offline preparation; native outcome unmeasured here.

The [registered development challenge](prereg-2026-09-30-reviewer-comparison.md)
uses three fictional comparisons and two Reviewer instruction arms. The isolated
executor lives in `evals/reviewer_comparison_v1/`; production routes, task
definitions, scoring and closed Tool Calling batches are unchanged.

The fixture SHA-256 is
`4ee81119c3e680e96c8904ac0946e6d96a91a06fd5a84fd101966809301fef4a`.
The final manifest SHA-256, after binding the closeout-scope note, is
`175b297c2bad813494c3d8a3a0bf0a553de38b0533614232d93228ed51be13ba`.
An earlier offline manifest identity is not treated as native authorization.
It records complete instruction blocks and original Git blob identities,
production helper/source/dependency identities, the fixed six-request order
and exact request hashes. Preparation checks snapshot consistency without
historical Git objects; the native gate additionally checks the original full
blobs before reading a key. A shallow CI checkout therefore does not silently
waive the historical native check.

## Delivered controls

- Default import and identity preparation refuse credential-file reads and
  provider connections, including the Chroma/dotenv import path.
- Actual imported production helpers must come from the hash-bound checkout.
- A fresh fixed output directory, exact committed identity, operator-reported
  review/CI identity and durable reservation precede dispatch.
- One aggregate six-request/USD 0.10 allowance, fixed Qwen endpoint/model,
  no retry/redirect/resume and strict response/model/usage limits.
- Decoded and nested escaped credential echoes are rejected before any raw
  response or generated text is persisted. Malformed JSON retains a digest
  and safe failure category rather than unchecked response text.
- The actual production correction application and report validator process
  native JSON unchanged. Missing targets, invalid plans and incomplete delivery
  stop later dispatch. Harmless no-op plans remain mechanically valid.
- Final source/draft/output packets omit arm identity, candidate instructions,
  correction reasons and expected edits for a later fresh LLM judgment.

The native gate's review/CI argument is an operator assertion. The parent must
observe real CI independently; neither a matching string nor a preview hash
attests that CI or semantic judgment happened.

## Offline evidence and failures retained

The pre-change suite passed 7,411 tests and 1,680 subtests. The new focused
controls passed 64 tests across twelve groups. Four defects were independently
reintroduced in memory: suppressing escaped-credential detection made three
controls fail; suppressing imported-helper origin checks, hiding unapplied
corrections, and removing only the native historical-check call each made one
control fail. Those mutations were removed and the fixed controls passed.

Initial snapshot encoding, dotenv import isolation, formatting and mutation
bootstrap-order failures were corrected. Early manifest preparation may have
reached Chroma's indirect credential-file reader despite disabling
`load_dotenv`; no credential was printed or persisted. The final protection
also denies the actual shared dotenv stream and restores it afterward, with
fresh-process refusal controls. This is an execution-preparation failure
record, not a claim that the first implementation had complete isolation.

The integrated preparation suite passed 7,475 tests and 1,684 subtests; latest
Ruff, narrow Pylint and independent static review passed. These counts belong
to the preparation version. Its execution code and tests remain outside main
after closeout, so they must not be added to main's maintenance denominator.
Native use still requires exact committed identity and green CI. No semantic
gain follows from this preparation record. Later results must retain missing
observations, apply the frozen rubric and preserve this record.
