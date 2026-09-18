# PCQ native Qwen proposition-contrast canary

Registered 2026-09-17 before implementation or any PCQ provider request.
Preparation baseline: `d0b4906ae412152108ff586363329c9d31338df7`.
New protocol identity: `report_evidence_claim_contrast_qwen_canary_v1`.
Transport remains `report_evidence_claim_qwen_transport_v1`.

## Question, prior evidence and limits

Can exact `qwen3.5-plus` read a nonempty saved source, abstain about an
unmeasured physical value, yet refute the distinct claim that the same record
reports that value? A separate recorded measurement is the positive control.
The [preparation](results-2026-09-17-claim-proposition-contrast.md) froze
LLM-reviewed synthetic development references, not expert gold or live answers.
The [CLQ batch](results-2026-09-16-claim-qwen-canary.md) stays closed and failed;
neither its labels nor its runner, output, allowance or hashes may be reset.

Replaying the existing PCQ helper before this change passed three scripted
read-to-final paths, including a usable receipt retained with abstention.
Scripts are not native responses. The shared-record pair plus one positive
control is not three independent samples or an unseen accuracy estimate.
This protocol tests no retrieval ranking, long document, unavailable-text
control, real report, commercial decision, adoption or production admission.

## Frozen inputs and disclosure

Use the original `tests/fixtures/report_evidence_claim_contrast.json` bytes:
`bfc9347b28a7d284b8d959c93a038a14f1c15c9adb0d3394c9c6463012141c78`.
Preserve its `draft_before_llm_review` status as original provenance; the
separate preparation result records the later freeze gate.

Order is fixed: PCQ01 physical-value claim / insufficient; PCQ02 claim about
record contents / refuted; PCQ03 recorded measurement / supported.
Keep the exact source fields, `source_type=synthetic_control` and default
`origin=unknown`. Shared source bytes do not allow shared conversations or
a substituted receipt. Each case constructs a fresh snapshot-bound and
verbatim-claim-bound native transport, sharing only the exact batch ledger.

Only the original claim, allowlisted source catalog and actually selected
saved-text receipt enter Qwen. Never send reference relation, proposition kind,
rationale, scripted answer, old results or private RS material. No new fixture,
cohort selection or rewording after observing native answers.

## Implementation and identity

Add only `src/academic_agent/report_evidence_claim_contrast_qwen_canary.py`,
root `report_evidence_claim_contrast_canary.py`, dedicated tests and current
guides/results. Do not evolve frozen modules or execute the closed CLQ runner.
Reuse the exact claim wrapper, native adapter and ledger. Adapt bounded
identity/publication/dispatch checks into the new runner with provenance
comments. Do not use the offline rehearsal gate: it compares a scripted answer,
which is not a native-model acceptance rule.

Bind committed code/CLI/tests/protocol, the original fixture/helper and freeze
documents, the complete executing project dependency closure, configuration,
actual disk bytes, committed blobs and locked installed dependency versions.
Keep the established CRLF-to-LF comparison for fixed text paths only; reject
symlinks/reparse paths and hidden source edits. Version matching is not
installed-package byte attestation. Verify before and after every request,
including rejected responses; preserve parsed usage on post-response drift.

Default CLI only verifies identity: no key lookup, dotenv, output or HTTP.
Live mode requires a full expected commit, exact fixture hash and exact new
protocol acknowledgement. Acknowledgement records operator intent, not proof
of independent user consent or CI. No force, retry, resume, case selection,
output override or model override. Fixed output:
`outputs/report_evidence_claim_contrast_qwen_canary_v1`.
Exclusive creation rejects any occupied or partial output, including a stopped
batch. Never remove/rename it to buy another attempt. This single-owner local
journal is not distributed admission, disk-loss safety or provider exactly-once.

## Bounded dispatch and first-failure rule

The user's standing equivalent low-cost synthetic Qwen scope is at most six
sequential exact-model requests and USD 0.10 soft stop, accepting a small
single in-flight overshoot. This separately named batch is not unused old
allowance. Only the parent may dispatch it after committed identity freeze,
full zero-provider tests, independent read-only code review and every exact-SHA
CI job green. The implementation stage itself performs no live requests.

There are at most two HTTP requests per case, six total, one local read per
case. Native tool choice remains auto: do not force or repair the requested
read. Reject a no-read/wrong/partial read after the first response before
buying the next request. Each passing case needs the actual complete nonblank
receipt in the second native request, exact call pairing, correct body hashes,
strict four-field final content, all wrapper/catalog/core observations and
complete valid accounting. Retain raw integer-type checks as well as the final
serialized payload; booleans must not impersonate read counts.

Supported/refuted require answered_with_evidence and the actual supporting
receipt. Insufficient requires abstained and empty supporting IDs while
retaining that same complete usable text in served/delivered/usable observations.
Keep `not_assessed`, `not_verified` and
`injected_transport_unverified`; a declared relation is not semantic proof.

Record mechanical acceptance, frozen-label agreement and later semantic review
separately. A valid wrong relation can pass mechanics but must fail the label
gate and stop. Overall `batch_passed` requires all three mechanical and label
passes, complete known accounting, no stop/pending state and published summary.
A label mismatch must not retroactively erase a case's mechanical observation.

Any setup, transport, accounting, identity, wrapper, receipt, label or
publication failure prevents further dispatch; later cases are explicitly unrun.
Persist separate identity/experiment/acknowledgement before HTTP, leaving the
adapter manifest's `live_authorization=False` unchanged. Intent precedes
dispatch; canonical full HTTP bytes, not callback lengths, bind reserve/finish.
Unknown usage is not zero: retain reservation and stop. Flush/fsync/close
case/summary files before write-once publication; pending files are not success.
A successful label observation is not proof that publication succeeded.

## Credentials and frozen transport

Use only process `DASHSCOPE_API_KEY`; no import-time dotenv or alternate keys.
Only in a later authorized dispatch may the parent load that single assignment
from existing .env without printing/persisting it. Destination is exclusively
`https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`.
Exact `qwen3.5-plus`, non-thinking, non-streaming, temperature zero, no parallel
calls, 512 output tokens, 12 KiB full request, 64 KiB response, 10-second connect
and 60-second request deadline, TLS, trust_env=False. No redirects, retries,
search, supplemental retrieval, repair, fallback, recovery or model replacement.

Retain the adapter's frozen conservative estimate, not a fresh price assertion:
USD 0.573/3.44 per million input/output tokens, 16,384-input reservation,
USD 0.011149312 per request and USD 0.066895872 for six. Estimates and
reservations are not invoices. This implementation does not reprice old runs.
Reported model identity is not independent backend attestation.

## Validation, judgment and closure

Offline tests use fake keys and real wrapper/local tools/native adapter through
MockTransport. Check both complete six-request wire/journal delivery and
first-failure no-extra-HTTP behavior. Cover identity/default-import isolation,
label hiding, wrong/partial/no read, unpaired/forged receipt, final schema,
raw counter types, false semantic relation, bounded/unknown usage, timeout,
redirect, wrong model, occupied output and setup/finish/case/summary write loss.
Counterfactual tests must reach their named gate: keep earlier accounting
consistent when testing a later receipt/hash/final-content gate.

Reinject defects separately in new mechanical admission, label-stop and receipt
pairing logic; require regression failures at actual dispatch boundaries, not
only changes in summary text. Restore exact source bytes after each mutation.
Run full tests, latest Ruff, narrow Pylint and a different independent read-only
reviewer before commit/push; wait exact-head CI before any live use.

After a single later batch, a fresh independent LLM context receives only each
original claim, actually delivered text/receipt, candidate answer and a neutral
support/refute/insufficient/unavailable/uncertain rubric. First infer the claim
relation, then judge the answer as supported/mixed/unsupported/uncertain/
not_reviewable; do not confuse a refuted proposition with an unsupported answer.
Hide references, desired outcomes, test results and previous reviews initially.
Record exact short quotations, uncertainty, input/output identities and honest
AI provenance; missing/malformed answers are not_reviewable, not fabricated.
Use the configured separate agent context, not extra project Qwen judging
requests. Record unavailable backend metadata; quotation match is not entailment.
This follows the [LLM-only policy](llm-review-policy.md), not human expert gold.

Close whether pass or fail; no automatic retuning, rerun, repair, new allowance,
merge/deploy or production release. Keep raw responses/reviews ignored locally.
Publish only synthetic aggregates and limits. Sync the two local project
experience records without exposing private RS inputs or rewriting past failures.

