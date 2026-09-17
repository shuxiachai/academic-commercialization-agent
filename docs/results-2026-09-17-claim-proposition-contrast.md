# PCQ reference pre-review and offline preparation

Date: 2026-09-17. Synthetic development preparation, not a paid Qwen result,
production release, human evaluation or general accuracy estimate.

## Measured failure and frozen successor

The [closed CLQ result](results-2026-09-16-claim-qwen-canary.md) remains three
per-case mechanical passes, 2/3 frozen-reference matches and a failed batch.
Its third claim asserts a recording, while the reference intended uncertainty
about the physical value. No historical label, source, runner or output changes.

The [new PCQ protocol](prereg-2026-09-17-claim-proposition-contrast.md) and its
original draft bytes were committed as `3b07e74` separately from the preparation helper.
Fixture SHA-256:
`bfc9347b28a7d284b8d959c93a038a14f1c15c9adb0d3394c9c6463012141c78`.
The author wrote references before independent review. The original draft
status is retained; this result records that the freeze gate passed rather
than rewriting the authoring provenance inside the fixture.

PCQ01 asserts an actual physical value against a record with no measurement.
PCQ02 asserts that the same record reports that measurement. PCQ03 asserts a
recorded value against a separate explicit-measurement record. These are new
fictional materials and texts, not relabeled CLQ cases. The shared-record pair
is deliberate, so three cases are not three independent statistical samples.

## Blind LLM pre-review

A fresh `route_reviewer`, configured as `gpt-6-astra/high`, received only the
case IDs, verbatim claims, source titles/texts and a neutral relation rubric.
No expected relation, proposition category, rationale, scripted answer, old
outcome or prior review was supplied. It used no workspace or external tools.
Effective backend identity metadata was unavailable; role configuration is not
backend attestation. This reviewer was separate from the drafting author.

All three independent relation proposals matched the prewritten references:
insufficient, refuted and supported, respectively. No material ambiguity was
identified. Four source quotations matched their own record text literally;
that check verifies quotations, not entailment. Raw prompt, inputs, output,
quote checks and method metadata are retained with hashes locally, not staged
in this public repository. Only this aggregate and method limitations are public.

These references are LLM-reviewed synthetic development labels, not human gold.
The judge could share systematic biases with a later answering model. It has
not evaluated a Qwen answer to these questions. The reference-freeze gate is
separate from the later native model gate, and neither establishes user value.
The Codex-agent review uses LLM resources outside the project's Qwen ledger;
zero project-provider requests does not mean zero-resource review.

## Engineering contract and remaining gate

The separate offline helper loads exact fixture bytes, constructs an
allowlisted blind projection and scripts one local read plus one final callback
per case through the existing claim wrapper. Mechanical checks inspect the
actual serialized result and callback-delivered source, not a presumed answer.
The insufficient branch must abstain with no supporting IDs while preserving
a usable read. A structurally valid wrong relation can still pass the original
wrapper: it does not perform semantic verification.

Runtime `semantic_support=not_assessed`, `answer_verification=not_verified`
and `assessment_origin=injected_transport_unverified` stay unchanged. The helper
has no provider client, credential lookup, paid flag or production import.
The source summaries fit one read; this does not test source discovery, ranking,
missing text, adversarial long documents or general claim extraction.

## Verification and initial defects

- Before changes: **4,905 passed / 1,418 subtests**, 243.48 seconds.
- Initial targeted validation failed: Python-mode strict validation rejected
  the fixture's JSON array where an immutable tuple was required. Loading via
  Pydantic's JSON entry point preserves strict Python-mode rejection rather
  than weakening the model. A separate local temporary-directory permission
  fault used a new checked test root, not weaker assertions or an ACL change.
- Review of that draft also found a fake-semantic-error test only altered the
  returned model. The replacement sends the wrong relation from the actual
  callback: the wrapper admits it with unverified flags, while the rehearsal
  independently observes reference mismatch. It is not a semantic verifier.
- A subsequent validation exposed serializer normalization of an injected
  boolean counter to integer `1`. The helper checks retained raw counter types
  as well as serialized counters. This is not complete raw-model reconstruction.
- **26 new tests** passed. Exact second-callback receipt, claim/answer, read
  counters, IDs, final-only pairing, provenance and CLI exit codes are checked.
  Network guards also run inside the CLI subprocess, with dummy credentials.
- Three separate mutations leaked a label, removed the original-claim check,
  and removed the raw counter-type check. Each produced one intended assertion
  failure (the claim matrix retained ten passing controls). Every mutation was
  exactly restored to its pre-injection source bytes. A final docstring correction
  explicitly says that author labels stay outside blind-review inputs; it does
  not change the projection or the already-recorded mutation evidence.
- The actual CLI rehearsal passed all three scripted cases. PCQ01 retained one
  usable read but abstained with no supporting IDs; PCQ02/03 answered with their
  actual receipts. The CLI blind projection exactly matched the earlier
  independent judge's input. None is a Qwen response.
- Final full local suite after the docstring correction: **4,931 passed /
  1,426 subtests**, 300.18 seconds (the preceding pass took 256.29 seconds).
  Latest Ruff and narrow Pylint passed. A separate read-only code reviewer
  found no actionable issue in the restored source; this was static review,
  not a second independent execution of the tests.
- All **245 inspected pre-existing frozen files** retained their hashes.
  The closed CLQ summary and event-log hashes also remained unchanged.

These test totals are revision snapshots, not semantic accuracy or independent
statistical samples. CI/release state must be checked against the current PR;
local success does not claim that PR #153 is merged or deployed.

A future live PCQ batch needs a dedicated hash-bound runner and fresh output
identity, tested against the native adapter and frozen before dispatch. It must
not reuse the closed CLQ runner/output or imply approval to serve Tool Calling
in production. The intended live nonempty-insufficiency lane remains unproven.
