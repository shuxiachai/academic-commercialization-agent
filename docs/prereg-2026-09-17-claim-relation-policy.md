# Explicit claim-relation policy: offline development contract

Date: 2026-09-17. Offline injected callbacks only; no native adapter, paid
executor, production route or new data-transfer authorization.

## Motivation and immutable history

The closed PCQ batch delivered nonempty text correctly, but called an
unmeasured physical value refuted rather than insufficient. This supports
testing a more explicit relation policy; it does not establish that prompt
wording is the unique cause. Keep PCQ/CLQ artifacts, prompts and labels unchanged.

This successor changes the instructions delivered to an injected callback,
not the relation returned by a model. Never rewrite a refuted answer to
insufficient in Python or declare semantic correctness from valid receipts.

## Decision contract

Retain the original caller proposition verbatim. Determine what it actually
asserts, including subject, conditions, time, scope and negation, without
rephrasing it into a claim that the source reports a value.

1. With no usable delivered read, unavailable is the only evidence-state
   declaration; this does not mean no relevant literature exists.
2. With usable text, supported requires the same proposition established by
   that text; refuted requires an incompatible proposition under the same
   subject and conditions. A different subject or condition is not refutation.
3. No measurement, no mention or lack of support for a physical property does
   not show the property is false. Use insufficient when neither side is
   established, including unresolved scope ambiguity.
4. An explicit statement that a record contains no measurement may refute a
   proposition that this record reports that measurement. A mere omission from
   a saved excerpt does not prove the complete source lacks it.
5. Honor negation in the caller claim. Negative answer wording alone cannot
   determine the relation. Do not use metadata or titles as evidence.

Supported/refuted still require exactly one actual usable receipt; insufficient
requires a usable read and no supporting IDs; unavailable requires no usable
read and no IDs. These frozen mechanical constraints are unchanged.

## New development controls and reference provenance

RP01-RP08 are eight new fictional controls: unmeasured physical value, explicit
record-content contradiction, exact support, exact contradiction, condition
mismatch, subject mismatch, negated support and missing text. Some share source
text and form dependent contrasts; they are not eight independent trials or an
unseen evaluation. The absent-text control is not a semantic entailment sample.

The author prepared labels in memory before the separate LLM assessment.
That assessment occurred before this document and fixture were committed;
this is a preregistration of implementation/verification, not a retrospective
claim of preregistered reference review. The independent task message contained
only IDs, claims, saved text and a neutral rubric, no author labels or rationales.
Inherited project context may include earlier outcomes: call this label-blinded,
context-limited LLM reference review, not fully blind or human expert gold.

All seven text-bearing references agreed; the eighth was unavailable and
not-reviewable. Nine source quotations matched literally; this checks
transcription, not truth. No material ambiguity was reported. Local prompt and
canonicalized judgment records preserve the limitation. Requested reviewer is
route_reviewer / gpt-6-astra / high; effective backend metadata is unavailable.
No external source inspection or project Qwen request occurred.

Fixture path: tests/fixtures/report_evidence_relation_policy.json.
The implementation binds its committed byte hash; references never enter
the callback prompt. A disagreement in future native testing stays a failure,
not an invitation to rewrite these controls and call them held-out.

## Engineering acceptance

Use a new module around the frozen claim wrapper; do not edit its parser,
tool loop, receipt construction or native adapter. The injected callback must
receive the new system policy on both stages, while every other request field
and the original claim remain unchanged. Detach data before transformation.

Expose nested frozen results and a separate policy audit. Distinguish configured
policy from actual callback entry, including when preflight refuses dispatch.
Count and hash/size the transformed requests at that entry point, retaining the
same two-callback, one-read and 12 KiB callback ceilings. This is callback
delivery, not HTTP dispatch or proof that a model followed the policy. Do not
inflate old inner byte counters to pretend they measured the new layer.

Preserve not_assessed, not_verified and injected_transport_unverified.
Scripted replies exercise delivery and strict serialization only. Include a
structurally valid but semantically wrong reply that is not silently repaired.
Unknown/no-text, whitespace, early refusal, malformed finals, forged receipts,
oversize requests, callback exceptions and changed claim/instruction contracts
must remain distinguishable. The new public callback takes one detached request object, unlike the old
three-keyword native adapters. Validate callable signature before entering the
inner executor so a directly miswired old adapter cannot touch its ledger or
HTTP. This is a shape fence, not proof that arbitrary callback code is offline;
tests must still forbid HTTP. Do not adapt the old native wire contract.

Re-inject at least policy omission, post-transformation budget omission and
claim-identity omission, require corresponding behavioral regressions to fail,
then restore. Run baseline/final full zero-provider suites, latest Ruff, narrow
Pylint and independent read-only code review. Preserve old frozen-file hashes.

## Release boundary

Document offline evidence separately from future native accuracy. No prompt
caching, scoring/rubric changes, general uncited-claim blocking, CrewAI upgrade
or abstract scraping is involved. No production integration, paid calls,
real-report disclosure, automatic merge or Railway deployment follows.

A later native experiment needs its own exact-policy/snapshot/claim wire
contract, identity/ledger and new fixed output. Do not pass these controls to
an old paid runner or reuse any occupied/closed batch allowance. Fresh unseen
evidence is still necessary before general effectiveness or production claims.
