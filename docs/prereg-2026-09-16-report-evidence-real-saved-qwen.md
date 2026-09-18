# RS real saved-report Qwen pilot

Registered: 2026-09-16, before the new runner and any RS provider request.
Starting implementation: `77f8f01c2b2d101b67df42aad214115303d24b1d`.
Protocol: `report_evidence_real_saved_qwen_canary_v1`.

## Question, scope and authority

Can the catalog-native path select and fully read a relevant saved abstract
from a real 20-source catalog, then answer within its scope or abstain when
the same NONEMPTY text is insufficient? The separate
[offline preparation](prereg-2026-09-16-report-evidence-real-saved-offline.md)
defines two fixed developmental tasks, RS01 and RS02. Neither that preparation
nor the closed CQ synthetic batch is authorization for this experiment.

The user explicitly authorized this one real-data batch after the runner's
tests, independent review and CI pass and its version is frozen: exact model
`qwen3.5-plus`, at most FOUR sequential requests in total, at most TWO per case,
USD 0.10 soft stop, with a possible small overshoot from one in-flight request.
No retries, redirects, repair, fallback, search, recovery, extra paid judging or
production activation are allowed. This is not permission to restart Railway
or merge a PR. A CLI acknowledgement records operator intent, not independent
proof that a user consented.

The approved data identity is the local packet manifest SHA-256
`087c2f6b82e3f775f9eadc8f57bb342dcf1b23a100fa7c1264eb624b845388cc`.
Allowed model inputs are the two fixed questions, all 20 visible source titles
and necessary citation metadata, and at most one selected saved-text window
of 1,500 Unicode code points per case. The model may choose any advertised ID:
authority is not restricted to the expected answer source. Full report prose,
raw run metadata, filesystem paths, reference labels, reviewer notes and
credentials are excluded from model messages.

The manifest and all raw packet files remain unchanged and private. Its
`live_authorization=false` describes the completed offline preparation and
must NOT be rewritten. This protocol and a separate live authorization record
describe the new operation. The packet is consumed historical evidence with
new developmental questions, not an unseen source-truth or accuracy study.

## Identity and execution contract

Add a separate RS runner, CLI and synthetic tests. Preserve all frozen
preparation/core/catalog/transport/old-runner files. Current configuration,
code/dependency blobs and this protocol must match a committed expected
revision; dirty or hidden fixed-path changes fail closed. Record disk and
committed hashes with the existing CRLF-to-LF text convention and installed
dependency versions. Versions are not attestation of package bytes.

Load only the packet's fixed permitted basenames, reject indirect/traversal
paths and verify the exact manifest and every declared file hash. Rebuild
prepared inputs from the original report/source/metadata/question bytes and
compare with the frozen prepared object, snapshot/catalog/configuration and
separate label binding. A stored prepared object or a hash field alone is not
proof that projection was checked. Recheck identity before and after each
possible request; drift stops the batch without discarding observed usage.

Default CLI operation is identity-only: no key lookup, output creation or
provider call. Live mode requires a fresh explicit RS acknowledgement and a
code-fixed fresh single-batch directory under project outputs; there is no
alternate-output or resume option to obtain another allowance. Only the dedicated process
`DASHSCOPE_API_KEY` is read; the runner does not load dotenv, select another
provider, use a global key fallback or echo malformed arguments.

Publish code/data identity and scope/authorization records before dispatch.
Use the existing native catalog transport with a fresh conversation per case
and one shared ledger. Independently enforce the four-request/two-per-case
ceiling without widening the older ledger or adapter limits. Reserve before
POST, retain parsed usage after later failures, and stop with the outstanding
reservation on unknown usage. Frozen conservative prices are estimates, not
invoices. No free-request inference follows from an interrupted response.

Keep strict schemas, visible-ID selection, one actual source read, final-only
JSON Object, snapshot/paired-tool-message validation, 12,288-byte callback and
full HTTP request limits and existing response/time limits. Do not silently
delete distractors, truncate a required full read, repair a response or relax
a gate to make this batch pass.

Publish each completed case and summary without overwriting an existing file.
Temporary incomplete output is not an authoritative result. Stop on the first
transport, protocol, identity, accounting, persistence or mechanical failure;
later cases are explicitly unrun. This is single-owner local orchestration,
not provider exactly-once or crash-resumable production admission.

## Frozen mechanical gates

Both cases retain their offline reference targets and expected states:

- RS01: two accounted requests; actual complete nonempty read; final
  `answered_with_evidence` referencing exactly the delivered receipt.
- RS02: two accounted requests; complete read of the SAME nonempty source;
  final `abstained` with no final IDs while the served receipt remains in audit.

Each case needs exact-model responses, known usage, the full untruncated
catalog, one native tool call executed locally, its exact result paired in the
second HTTP request, and a strict final object matching the delivered result.
Callback activity alone cannot pass. Compare reference labels only after the
observed execution; they never choose tools, change prompts or generate answers.
First-case checking must not invent an unrun second result to satisfy a helper.
If the first accounted response already proposes the wrong reference source,
an insufficient window or early termination, record that observation and stop
before a second paid HTTP request. This is a frozen mechanical failure, not a
claim that every other source is semantically irrelevant; do not repair the
model's choice into the reference action.

Safe early abstention fails the predeclared read-to-final gate. A careful answer
that explains insufficiency but declares the wrong final status still fails
RS02's mechanical gate; its semantic merits remain separately reportable.

## LLM semantic review, not human ground truth

The user allows LLM judgment in future tasks. For this batch, a fresh read-only
reviewing agent may inspect each available answer against only its question,
actually delivered saved text and necessary source metadata. Do not provide
reference labels or expected answer prose in the first review; do not let the
answering model's self-rating stand in for this review. No additional paid
project-provider request is included. Keep machine gates unchanged.

Record the review method, requested model/role, effective backend metadata
availability, input/output hashes, scope and rationale. Report unverified
backend identity as unavailable, never infer it from a role name. The rubric:

1. Are factual and numeric claims supported by exact delivered text?
2. Are material/test-scope observations kept separate from vehicle/deployment
   claims, without inventing a comparator, measurement condition or milestone?
3. Is missing evidence communicated without claiming worldwide absence?
4. Does the answer address the question within those limitations?

Require short exact supporting excerpts where support is claimed; absence
claims cite the inspected scope, not an invented quotation. Use
`supported / mixed / unsupported / uncertain / not_reviewable` judgments
with reasons, separately from mechanical `passed`. Missing final answers are
`not_reviewable`; unrun cases are not positive results. An LLM reviewer is
fallible and can share model biases. This is NOT human expert validation,
independent gold accuracy, publisher full-text verification, user utility or
evidence that LLMs generally outperform experts. Runtime semantic states remain
`not_assessed` / `not_verified`; the post-hoc assessment is a separate artifact.

## Validation and publication

Before changes: 4,342 tests / 1,388 subtests, 196.22 seconds, zero provider calls.
Add synthetic behavioral tests at the CLI/packet/HTTP/ledger/publication seams:
byte/projection drift, path rejection, no-side-effect identity mode, labels
excluded from HTTP, exact actual tool receipt, nonempty read-then-abstain,
per-case and total caps, first-failure suppression of later calls, unknown
usage preservation, malformed/secret-bearing replies and failed publication.
Reinject a meaningful preflight or dispatch defect, observe red, restore exact
code and rerun. Require complete tests, latest Ruff, narrow Pylint, independent
read-only review and all public CI checks before the one live batch.

Record failures without retrying or rewriting references. Private transcripts
and raw reports/labels stay local; only qualified aggregates, method limits and
hashes may enter public docs. Keep FQ/SQ/JQ/CQ and v8 results sealed. Passing
this two-case pilot would be a limited real saved-text observation, not
production Tool Calling readiness or a reason to enable autonomous retrieval.
