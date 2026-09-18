# PCQ native executor: offline implementation

Date: 2026-09-17. This is an engineering result, not a Qwen observation,
semantic-accuracy result, production release or new source-search feature.

## Why a separate executor

The [PCQ preparation](results-2026-09-17-claim-proposition-contrast.md) separates
an unmeasured physical-value claim from a statement about what a record reports.
Its three synthetic references were written before fresh-context LLM review.
They remain AI-reviewed development labels, not human gold; the shared-record
pair and separate positive control are not three independent accuracy samples.

The [native protocol](prereg-2026-09-17-claim-proposition-contrast-qwen-canary.md)
was committed first as `9b8d64a`. It freezes a new runner/output identity while
retaining the original PCQ fixture and its authoring provenance. CLQ remains
closed and failed; no label, native response, old runner or journal is repaired.
The new executor does not run the old CLQ batch or reuse its allowance.

## Delivered boundary

`report_evidence_claim_contrast_qwen_canary.py` uses the existing exact claim
wrapper, native adapter and ledger. The root
`report_evidence_claim_contrast_canary.py` defaults to identity-only, without
key lookup, dotenv, output creation or HTTP. It binds committed code, fixture,
configuration, dependency versions and actual bytes, and checks identity before
and after each request. A post-response drift keeps observed usage, not zero.

A future explicit live invocation has one exclusive fixed output and a new
acknowledgement record. It cannot select cases, replace a model, resume, force,
retry or redirect. At most six sequential `qwen3.5-plus` requests and USD 0.10
soft stop cover the fixed three cases; no extra search or judging request is
part of that project-provider allowance. The frozen adapter manifest still
says `live_authorization=False`; it is not rewritten as an experiment grant.

Only the claim, catalog and actual saved-text receipt enter the model.
References, proposition classification, rationale and scripted answer stay out.
Each case gets a fresh snapshot-bound conversation; the two shared-text cases
do not share a receipt. Source provenance remains `synthetic_control` with
default `origin=unknown`, not a fabricated paper identity.

The executor observes the full canonical HTTP bytes, reserve/finish journal,
native call pairing, actual complete receipt, wrapper/catalog/core audits and
strict final declaration. It validates the published JSON seam and retained raw
counter types, so serializer normalization cannot turn a boolean into a count.
Nonempty insufficiency retains a usable read while abstaining with no supporting
IDs; support/refutation require the actual receipt.

Case mechanics, reference agreement, publication and later LLM judgment are
separate. The new `batch_passed` combines mechanical and reference checks,
complete known accounting, no stopped/pending state and successful publication.
Later LLM judgment is excluded: `semantic_review` can still be pending when
the engineering batch passes. This is not a semantic-verification flag.
A third-case label mismatch or final file
failure must not erase the three mechanical observations; neither may produce
successful batch/CLI status. First failure prevents any later HTTP and marks
remaining cases unrun. Unknown usage retains reservation and stops.

## Offline evidence

- Original full-suite attempt hit a Windows pytest temporary-directory access
  error; a short first-error run confirmed setup `PermissionError`, not a
  provider/implementation assertion. Following CONTRIBUTING, a new checked
  workspace temporary root produced **4,931 passed / 1,426 subtests** in
  269.73 seconds before changes. No ACL, assertion, warning filter or skip changed.
- Free replay of the existing preparation produced all three scripted paths,
  including nonempty-read abstention. This was not a native Qwen run.
- **208 new offline tests** exercise the real wrapper/local read/native adapter
  through MockTransport with fake keys. The first run passed in 47.26 seconds;
  the same set passed in 54.62 seconds after all fault reinjections were restored.
- Six intercepted requests cover the three distinct relation paths, complete
  HTTP/journal pairing, label hiding and strict result delivery. Negative cases
  cover partial/wrong/no read, malformed/fake final output, wrong original
  claim, raw counter types, identity drift, transport/usage errors, output
  collisions, budget bounds and each publication stage.
- Mechanical-gate, label-stop and receipt-pairing bypasses were injected
  independently in the new code. Each targeted regression failed on actual
  HTTP dispatch count `6 != 2`; exact source hashes were restored after each.
  The late-pairing test keeps earlier accounting consistent, so a different
  gate does not accidentally mask the defect.
- All **244 inspected pre-existing frozen files** retained their hashes.
  No production route, worker import or browser control was added.

Independent read-only AI code review is distinct from those executed tests.
Whole-suite/lint results and public CI must be read at the exact current PR
commit, not inferred from a historical test total. The new test count is part
of the full suite, never an additional accuracy denominator.

## What remains unproven

This stage made no new project-provider request. The intended live
nonempty-but-insufficient path is still unproven. A future batch requires the
committed exact identity, independent final review and every CI job green;
preparation success or an acknowledgement string cannot prove those facts.

After that single batch, a different blind LLM context may judge the original
claims and available answers using only delivered text. Keep its interpretation,
uncertainty and exact-quote checks separate from frozen-label matching and
unchanged runtime `not_assessed/not_verified/injected_transport_unverified`
flags. Such a judgment is AI-generated, not source-truth verification, human
expert gold, user adoption or a production-admission decision.

No real saved-report input is sent by this executor. Production remains
zero-call shadow mode. Shared public paid admission, ownership and receipts
for a customer follow-up endpoint are not implemented by this local runner.
