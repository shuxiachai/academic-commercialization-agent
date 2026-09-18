# SLQ: frozen one-selection Qwen compatibility and development controls

Registered before runner implementation from `498617ff71b43d0e71fbd8ef2b06eadfb771ec18`
on 2026-09-19. Identity: `report_evidence_source_locator_qwen_canary_v1`.
The [locator](prereg-2026-09-18-saved-source-locator.md) and its
[native adapter](prereg-2026-09-18-source-locator-qwen-transport.md) are unchanged.
Their offline manifests do not grant live authority.

## Question and scope

Can the exact Qwen model emit the single native selection accepted by this
contract, and does that selection match four freshly frozen synthetic
development references? One selection may cause one complete local read and
code-owned saved-text JSON. No second model request or generated answer exists.
This is not unseen accuracy, semantic claim validation, source truth, user
benefit or production admission. Closed CQ/CLQ/PCQ/RPQ/RF and v8 remain closed.

The new fixture is `tests/fixtures/report_evidence_source_locator_qwen.json`.
Only questions and title/ID catalog data reach the provider. Saved text,
publisher/provenance fields and reference labels remain local. All twelve
sources are author-created fiction with no private reports or real user inputs.

| Order | Control | Frozen selection | Local outcome |
|---|---|---|---|
| SLQ01 | English freeze-thaw versus fire-resistance titles | A12 | excerpt |
| SLQ02 | Chinese question, English mechanical vibration-label title | P21 | excerpt |
| SLQ03 | None of the three titles concerns the requested industrial inspection | explicit decline | declined, zero reads |
| SLQ04 | Matching collapsible insert title but no saved text | P41 | missing_text, one completed read |

SLQ03 requires the explicit decline action, not merely a provider refusal.
A matched title is only a candidate location: it cannot establish the recording
function in SLQ02 or patent status/validity in SLQ04. SLQ04 also cannot prove the
model detected missing text; text availability is hidden from the selector.

## Pre-freeze reference review and capacity

A fresh `route_reviewer` context saw only the four questions and visible
ID/title catalogs, not draft labels or stored text. It independently chose
A12, P21, DECLINE and P41. It noted the recording-function and patent-status
limitations above. This is label-blinded, context-limited LLM review, not human
expert gold. The role is configured as Astra/high; effective backend metadata
was unavailable. No external source or project-provider judge was used.

The frozen rubric is location by supplied metadata, not scientific truth.
Any later review must retain that scope and cannot repair a mechanical failure
or silently relabel this consumed development batch.

Before editing, the existing 30 local benchmark snapshots again delivered all
632 saved texts through prescribed-ID callbacks. That is delivery evidence,
not selection accuracy. The four new candidate native envelopes measured
1,786 / 1,959 / 1,765 / 1,785 canonical ASCII bytes respectively; all are below
12,288 bytes and their longest stored text is 146 code points. No HTTP was sent.

## Allowance and operational admission

This new batch falls within the owner's standing permission to perform later
low-cost Qwen tests without repeated questions, narrowed for this batch to:

- exact `qwen3.5-plus` at the pinned DashScope Beijing compatible endpoint;
- at most four sequential requests total, one per case;
- USD 0.05 aggregate soft stop, accepting one in-flight request may slightly
  exceed it; inherited frozen conservative estimates are not vendor invoices;
- synthetic question/catalog data only; no private RS material, live reports,
  external search, retries, redirects, repair, fallback, resume or production.

This is not reuse of an old batch's consent. Parent/operator execution must
bind the final committed SHA and fixture hash after independent code review
and all CI checks pass. A CLI acknowledgement records that action; it cannot
independently verify user consent, review completion or remote CI.
No native request may run during implementation/tests.

## Dedicated runner and identity

Add `academic_agent.report_evidence_source_locator_canary` and dedicated tests;
use `python -m academic_agent.report_evidence_source_locator_canary` as the CLI.
Default operation requires expected commit and fixture SHA-256 and only checks
identity. It must not read credentials, create outputs or contact any provider.
An explicit `--authorize-paid` value exactly matching the new protocol identity
is required for execution. Live credential lookup reads only process
`DASHSCOPE_API_KEY`; no automatic dotenv or other-provider fallback.

Bind fixture bytes and the closed source/dependency path set, including this
protocol, new runner/tests, unchanged locator/native imports, package init,
`.gitattributes`, `pyproject.toml` and `uv.lock`. Compare committed blobs and
disk content with the existing fixed CRLF-to-LF text rule, retaining both hashes.
Validate installed dependency versions and configuration; this is not package
byte attestation. Recheck identity before and after every callback, including
failure paths, without erasing already observed usage.

Use one fixed, fresh, non-resumable output:
`outputs/report_evidence_source_locator_qwen_canary_v1`.
Reject occupied or indirect/symlink/reparse paths, never select another batch
directory automatically. Persist identity/experiment/operator acknowledgement
before any native request. Each case gets its own new single-request ledger;
the runner additionally owns the aggregate four-request and USD 0.05 admission.
Check sum of max(reserved, known estimated cost) plus the next reservation
before dispatch. Missing/contradictory usage or persistence failure stops all
following cases. Do not refund an uncertain attempt or reset a used directory.

## Gates, observations and publication

The runner observes original callback bytes, native ledger bytes, admitted
reply choice and the serialized locator result. Reconcile request hashes,
one complete reserve/finish pair, exact response model/coherent usage, one
callback and zero/one local read. Bind selected ID and exact saved text/hash
to the trusted snapshot. Persist only safe choice metadata, never raw refusal
prose, response/error bodies, arbitrary exception text or credentials.

Mechanical acceptance is separate from frozen source-ID/state/reason agreement.
An accepted wrong visible ID or an inappropriate explicit decline is a reference
mismatch, not a transport failure. Labels are checked only after mechanical
acceptance. First mechanical, reference, identity, unknown-usage or publication
failure stops the whole batch, leaving later cases explicitly unrun.
Batch success requires all four mechanical and reference checks plus complete
case/summary publication and no pending/unknown accounting.

Retain per-case monotonic end-to-end elapsed time, including local checks and
publication where stated; do not call it isolated provider latency or an SLO.
Separate reported token/cost coverage, reservations and observations. Publish
JSON only after complete flush/fsync/close, using write-once atomic linking
inside the fixed output. A failed write never authorizes the next request.
This single-owner local design is not power-loss/distributed safety.

## Offline acceptance and later judgment

Use fake keys and intercepted actual HTTP through the new runner and existing
adapter; do not replace the locator/adapter callback on the successful path.
Assert that labels and saved text never enter provider requests, and that
full request bytes and actual saved text survive their respective seams.

Cover default identity-only behavior, wrong/dirty source identity, occupied and
indirect output, request/global-budget gates, partial usage, atomic publication
faults, accurate unrun/denominator reporting and safe CLI errors. Reinject a
first-failure-stop bypass, pre-dispatch identity bypass, and an incorrect
mechanical-versus-reference gate; unchanged assertions must fail then restore.

Run baseline/final whole offline suites, latest Ruff, narrow Pylint and a fresh
independent review before native use. New semantic judgment, if needed, uses
a separate label-blinded LLM context, never a simulated human reviewer or an
extra paid judging request. It remains fallible and cannot change frozen gates.
Production routes, source validation, scores and access control stay unchanged.
