# RPQ native batch: early final before any saved evidence was read

Date: 2026-09-18. Execution commit:
`b053eba9cf47dcd2c1f1276fbd572e82d45b4191`.
The [protocol](prereg-2026-09-18-relation-policy-qwen-canary.md) and
[runner verification](results-2026-09-18-relation-policy-qwen-runner.md)
precede this observation. This batch is closed and failed; RP02/RP03 remain
unrun. It is not a new semantic/reference disagreement.

## Actual observation

The single native request advertised `read_source` for A1 with
`tool_choice: auto`. Its messages contained the policy, literal synthetic
claim and one-entry title/ID catalog. No saved source body had yet been sent.
The 4,486-byte canonical HTTP JSON matches the journal's recorded hash.

The provider response passed the transport protocol and response-model
comparison recorded by the adapter. Its projected assistant message had no
tool calls: it returned a four-field JSON declaration of `unavailable`,
explaining that it had not read the source. This raw first-turn message is
not an admitted evidence-backed answer.

The runner's full-read check rejected the reply before it entered the inner
workflow. The journal retains `full_native_read_required`; the incomplete RP
callback audit subsequently records `relation_policy_audit_failed`. These
are two layers of one stopped exchange, not two provider errors.
There was no second request, local source read, receipt, final-stage HTTP,
accepted model assessment or delivered answer.

| Observation | Count or state |
|---|---|
| Selected development controls | 3, fixed in advance |
| Attempted cases / native requests | 1 / 1 |
| Observed tool calls / executed reads | 0 / 0 |
| Usable delivered receipts / admitted answers | 0 / 0 |
| Mechanically passed attempted cases | 0 of 1 |
| Reference-label checks | 0; agreement unavailable |
| Semantic-support judgment | not_reviewable |
| Unrun controls | RP02, RP03 |
| Pending request / unknown-usage requests | none / 0 |
| Case record and summary publication | completed |

The returned `unavailable` is not evidence that the saved source lacks useful
content or that the original claim is false. Because no read reached Qwen,
this observation does not test the intended nonempty-insufficiency distinction.
Do not count unrun cases as model mistakes or report zero checked labels as
zero-percent accuracy.

## Scope, cost and stopping

Execution used the standing synthetic-only six-request / USD 0.10 scope after
a fresh 5,531-test / 1,500-subtest baseline (343.63 seconds), independent source
review from the preparation stage and all eight exact-head CI checks.
The parent loaded only the dedicated DASHSCOPE_API_KEY assignment into the
child process; no key was printed or persisted by that setup.

The frozen request selected `qwen3.5-plus` at the Beijing endpoint,
non-thinking/non-streaming, temperature zero and no parallel tool calls.
The transcript contains journaled request content and a projected assistant
message, not a complete raw-response or TLS packet capture. Stored acceptance
flags do not independently attest the provider's backend model implementation.

Reported usage was 1,137 input plus 168 output tokens, total 1,305. Applying
the frozen conservative rates yields USD **0.001229421**. The journal's
USD **0.011149312** budget occupancy retains the full request reservation;
it is not an additional charge or an invoice. Unknown usage is zero, not a
claim about unobserved future requests.

The fixed output directory now contains seven immutable batch artifacts.
No retry, continuation, response repair, alternate provider, search, real-report
disclosure, production route, merge or deployment followed the first failure.
Remaining ceilings are not authority to reopen this occupied batch.

## Review and interpretation

A fresh requested route_reviewer / gpt-6-astra / high context independently
inspected the logs, runner, protocol and existing early-final test. It found
no actionable implementation defect in that scoped inspection: the observed
stop follows the frozen admission rule. It did not run tests, read credentials,
access external sources or modify files.

This was an engineering audit, not a blind semantic judgment: its task included
the reported stop, inherited project instructions contained earlier hypotheses,
and the supplied identity/manifest contained the configured label order.
No fixture or earlier semantic review was opened. Effective reviewer backend
metadata is unavailable. Its support disposition is **not_reviewable**, because
there is no admitted answer or delivered evidence to judge. Raw review and
provenance remain local/ignored; neither this audit nor the raw wire declaration
changes runtime semantic flags.

The existing first-stage test already checks early-final rejection before a
second request. This archival step changes no runtime, frozen test or label;
it adds no duplicate test solely to raise the count. Final documentation
regression, full-suite, lint and new exact-result-head CI outcomes will be
recorded after validation on
[PR153](https://github.com/shuxiachai/academic-commercialization-agent/pull/153).
Historical green checks on that PR do not attest this new archival commit.

## What should change next, separately

The observed wire still permits reading a visible ID **or finalizing**, while
this native experiment requires a complete first read. With no usable read,
the relation policy explicitly permits an unavailable declaration. The model's
early-final path was therefore representable by the advertised contract even
though this experiment deliberately rejects it.

The next bounded offline question is first-stage read admission, not another
attempt to score missing-versus-refuted reasoning without evidence. A separately
registered candidate should distinguish an available-source first read from a
genuinely unavailable source before permitting finalization. If a candidate
uses provider-required tool selection, describe it as forced execution, not
evidence of autonomous tool selection. Review its failure boundaries offline
before any new native scope.

Keep RPQ's prompt, fixture, source identity and seven artifacts unchanged.
Its three controls are dependent development data, not a fresh unseen cohort.
No production readiness or general Qwen capability conclusion follows from
this single early-final observation.
