# Reviewer comparison fidelity: paired development challenge

Registered from production revision
`ff5dcee18f91672ea368e2bdb110f02377df80d5` on 2026-09-30, before any native
request in this batch. Method: `reviewer_comparison_v1`.

## Question and changed variable

Can the comparison-fidelity instructions make an isolated Reviewer correct a
physical-difference/calibration-error misinterpretation and its dependent
decision target while preserving genuinely supported measurements and separately
labelled analyst experiment proposals?

Compare the complete Reviewer agent and task instructions at
`ee0a00e442735cb78c6950eb55d0e4fe1398a9bf` and
`ff5dcee18f91672ea368e2bdb110f02377df80d5`. Each pair receives identical sources,
intermediate findings, draft, output-language guidance, model and parameters.
Only the instruction arm changes. Freeze the rendered requests, fixture,
ordering, implementation and dependency identities before dispatch.

This is a direct native instruction experiment with the production correction
application and report validation functions. It does not reproduce the entire
CrewAI agent wire, scheduler, Writer, Scorer, retries or full production run.
Do not extend a successful result to those unmeasured paths.

## New development controls

Use three fresh fictional controls, independent of the stored RFID report and
old scripted fixtures:

1. A physical difference between conditions is incorrectly described in an
   intermediate finding and draft as instrument error; a dependent numerical
   decision target repeats that false premise.
2. A genuine instrument-versus-reference error is correctly described, with a
   separately labelled experiment target requiring owner confirmation. Preserve
   the measurement and the proposal's stated authority.
3. Two comparisons with the same unit are mixed up. Preserve a relevant negative
   caveat and correct the misassigned values and dependent claim.

These are deliberately constructed development challenges, not unseen accuracy
data, expert labels, external paper verification or observed user benefit.
The fixture and requests contain only synthetic data. No historical report,
private review packet, closed cohort, credential or run capability is sent.

## Bounded native execution

- One fixed batch, at most six sequential requests, three paired cases.
- Exact model `qwen3.5-plus`, the fixed DashScope compatible endpoint, JSON Object
  output, non-thinking mode, temperature zero and bounded output tokens.
- Total USD 0.10 soft stop. Reserve before each possible POST and retain known
  usage even when later parsing/application fails. The frozen-rate estimate is
  not an invoice or guaranteed monetary cap; an in-flight request can overrun.
- No retries, redirects, fallback, repair, resumed execution, search, tools or
  additional paid judge. Unknown usage, insufficient budget, transport or
  mechanical failure stops later requests. A semantic miss is judged afterward
  and does not authorize another request.
- Refuse an occupied output directory or unresolved old reservation. Do not
  replay the batch using a new process, key or directory after failure.
- Default import and identity preparation read no credentials and make no
  provider request. Live execution reads only `DASHSCOPE_API_KEY` from this
  project's `.env` after its identity gate. Never print or persist the key.
- Offline verification, independent code review, green CI and committed identity
  precede native execution. The project owner's standing bounded low-cost
  authorization applies to this synthetic batch; closed experiments stay closed.

The transport retains exact byte bounds, strict model/usage checks and safe
failure categories. A reported token count exceeding the reservation stops the
batch rather than silently widening it. The input reservation is an estimate,
not a tokenizer proof.

## Mechanical delivery and semantic judgment

Apply the actual returned JSON plan with the production
`_apply_reviewer_corrections`, then validate the resulting report. Record exact
applied text, unapplied corrections, errors and known usage. A partial plan is
not complete mechanical delivery. This composition is not the complete
`make_reviewer_guardrail`; describe its measured scope precisely.

After native execution, a fresh LLM judging context receives only the source
text, original draft, actual delivered report and this frozen rubric. Hide arm
identity, candidate instructions, expected edits, correction reasons and prior
judgments. Preserve the first judgment; do not request a favourable rewrite.
Record requested role/model and disclose unavailable effective backend metadata.
Style may still reveal an arm, so blinding is an input restriction, not a claim
that inference of identity is impossible.

The original draft is common task input for both arms, needed to assess whether
a qualified independent proposal was preserved. It is not a reference answer.
Treat it as the object under review, never as evidence for measurement facts;
the supplied sources determine those facts. Preserve semantic meaning and
authority qualifications rather than requiring byte-identical wording.
A hypothetical experiment target does not require factual evidence for its
numerical value when it is explicitly a proposal requiring owner confirmation;
it must not be presented as an observed capability or source-established gate.

The judge assigns `supported`, `mixed`, `unsupported`, `uncertain` or
`not_reviewable`, explaining whether the report:

- preserves the measured subject, reference, conditions, units and direction;
- corrects the primary misinterpretation and every dependent false derivation;
- retains genuine error measurements, negative caveats and independently
  proposed experiment targets with their existing qualifications; and
- introduces no new unsupported comparison or source-backed decision gate.

All three candidate-arm deliveries must be mechanically complete and judged
`supported`. A local paired gain additionally requires at least one baseline
`mixed`/`unsupported` result to become `supported`, with no regression in any
other pair. Both arms passing every case means no gain was observed. An
uncertain or unreviewable baseline does not become a definitive improvement;
missing observations remain missing, and disagreement stays visible.

One fallible LLM judgment over three constructed pairs supports a bounded
development observation. It cannot establish general semantic correctness,
calibrated accuracy, robustness across runs or end-user value. No production
semantic blocker or feature activation follows automatically.

## Closeout and maintenance scope

Keep runner, fixture, manifest and their tests at the immutable reviewed
preparation commit. After this one batch, main receives only qualified method
and result documentation linking that full commit; the preparation PR is not
merged, and its commit/branch remain available. This avoids adding a consumed
experiment's shared-source hash pins to main's future default test suite.
Close the batch after success, failure or early stop without retrying it or
changing its output directory. Raw outputs and judging transcripts are not
automatically public. A changed preparation identity requires renewed checks
before the first dispatch, not a repair of observed outcomes.
