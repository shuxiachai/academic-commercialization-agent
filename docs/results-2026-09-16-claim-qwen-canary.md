# Claim-relative Qwen canary: engineering closure, frozen-label failure

Observed 2026-09-16 under the [frozen CLQ protocol](prereg-2026-09-16-claim-qwen-canary.md).
Execution commit: `4d2475b58470314af24a93370d7ebe407dbd169b`.
Protocol/fixture were committed first at `cb54a97`.
This result document is later than execution and is not the executed code SHA.

## Bounded native observation

One batch used exact `qwen3.5-plus` and the three newly invented single-source
controls. Six sequential requests completed: one native read and one final
declaration per case. All six response model names matched the authorized
alias; this is not independent backend attestation.

- Three of three cases passed the mechanical wrapper/wire/receipt checks.
- Two of three matched the preregistered relation label.
- The batch **failed** with `expected_relation_mismatch` on CLQ03.
  Its immutable summary has `mechanical_passed=false` because the whole
  batch must also finish without a stop; this does not erase its three
  individual mechanical passes.
- Zero unknown-usage requests, zero unrun cases, no pending request.
- Reported usage: 6,024 input + 846 output = 6,870 tokens.
- Conservative known-use estimate: **USD 0.006361992**, not an invoice.
  Reservation accounting consumed USD 0.066895872; that is not another
  charge and must not be added to known-use cost. Soft stop was USD 0.10.
- No retry, repair, search, fallback, recovery, real-report transmission,
  new production endpoint or deployment occurred.

The fixed batch directory is consumed. Do not reuse, delete or rename it
to obtain another attempt. Original case/summary/ledger records remain
unchanged; raw synthetic transcripts and separate review records stay
in ignored local output.

## Why CLQ03 did not match its frozen label

| Case | Frozen relation | Native declaration | Independent LLM relation | LLM answer assessment |
|---|---|---|---|---|
| CLQ01 | supported | supported | supported | supported |
| CLQ02 | refuted | refuted | refuted | supported |
| CLQ03 | insufficient | refuted | refuted | supported |

Claim relations and answer assessments are different label spaces. A correct
refutation can be a supported answer.

CLQ03's publicly frozen proposition says that flow **was recorded** as a
specific value. Its invented source explicitly says that flow was not
measured and no flow result exists in that record. This is not merely a
missing mention of physical flow. The native answer treated the recording
assertion as contradicted, and the independent blind judge agreed.

The post-hoc diagnostic therefore identifies a reference/proposition mismatch:
the intended insufficient control asks about an existing recording rather
than an unknown physical value. This does **not** retroactively change the
preregistered label, turn 2/3 into 3/3, or establish that the model is generally
correct. The closed batch still failed. It did not demonstrate the intended
live nonempty-insufficiency lane; unavailable also remains offline-only.

A next protocol should separate a physical-value proposition from a
record-existence proposition and have a fresh LLM inspect that distinction
before the fixture is frozen. Use new inputs and a new identity, not an edit
or rerun of CLQ03. This is a proposed next step, not an additional paid run.

## Independent LLM review and limits

A fresh `route_reviewer` context, configured as `gpt-6-astra/high`, received
only the original claims, the actual second-HTTP delivered receipts, native
candidate declarations and the preregistered rubric. It did not receive
reference labels, mechanical outcomes, previous judgments or repository access.
It was separate from the implementation author, architect and code reviewer.

The review judged all three candidate answers supported within the supplied
fictional saved summaries and inferred supported/refuted/refuted for the
original propositions. Seven quoted spans were mechanically located:
six in delivered source text and one in the candidate answer. The latter
is not a seventh source quote. Substring matching does not prove entailment.

The exact review input/output and quote checks are hash-recorded locally.
The configured model/role is observable; effective backend metadata was not
available and is not self-attested. This was an AI assessment, not human
review, external fact verification, independent expert gold or user adoption.
The separate Codex-agent review made zero extra project Qwen requests; its
LLM resources are outside that six-request ledger, not claimed to be free.

The runtime flags `semantic_support=not_assessed`,
`answer_verification=not_verified` and the unverified callback-origin label
are preserved. Review occurred after dispatch and could not stop an earlier
request. The batch's fixed single-source design does not evaluate ranking,
general claim extraction, negative physical propositions or real reader value.

## Engineering verification before dispatch

- Before changes: 4,725 passed / 1,408 subtests.
- Added 180 zero-provider tests exercising the real wrapper, local tool and
  native adapter through intercepted HTTP. Final related regression was a
  separate 865 tests; these counts are not additional independent experiments.
- The original wrapper/label continuation mutation caused nine expected
  failures, eight at an excess-HTTP assertion.
- Independent code review found three negative tests were masked by an earlier
  journal rejection. The fix keeps unrelated prerequisites valid and asserts
  exact failure reasons. Independently removing the tool-pair, request-hash
  and native-final checks then caused one targeted failure each, all detecting
  six actual intercepted requests where only two were allowed. Every mutation
  was exactly restored; no assertion was relaxed or skip added.
- Final local full suite: **4,905 passed / 1,412 subtests**, 248.66 seconds.
  Latest Ruff and narrow Pylint passed. Independent static code review closed
  its finding; that reviewer did not execute tests.
- All 77 inspected pre-existing frozen files remained unchanged.
- The execution commit's [CI run 35098828648](https://github.com/shuxiachai/academic-commercialization-agent/actions/runs/35098828648)
  passed all eight jobs before the paid call. Each Linux/Windows x Python
  3.11/3.12 job reported 4,904 passed, one existing skip and 1,382 subtests.
  Coverage was 90.26%, with the 85% floor unchanged; browser smoke and Docker
  runtime checks passed. Local/CI denominators remain separate.

Identity-only CLI verification preceded paid mode without credential lookup,
output creation or network. No private RS results, source links, raw reviews
or resume notes are part of this public result. Production Tool Calling
remains zero-call shadow mode; this isolated observation is not a release.
