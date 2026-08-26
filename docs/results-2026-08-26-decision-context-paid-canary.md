# Decision Context three-mode paid production canary — result

**Date:** 2026-08-26
**Protocol:** [`prereg-2026-08-26-decision-context-paid-canary.md`](prereg-2026-08-26-decision-context-paid-canary.md)
**Authorized production revision:** `cf00c9a20118a552b8418b5770cce5336a28b9da`
**Manifest SHA-256:** `bd18ecb13f91d0f4dc9a3dde5059259f0d39579a41e6b2d4f62992d2196b63ad`
**Outcome:** valid three-case production observation; primary canary failed

## Executive result

All three frozen root requests were admitted once, ran sequentially on the
authorized Railway deployment, and reached `completed`. Public status and
progress returned the expected code-derived gate for each request. The study
created no child run, executed no evidence-gap tool call, changed no accepted
evidence collection, and stayed below both cost stops.

The primary canary nevertheless failed. Seven of the ten frozen criteria
passed and three did not:

- `DC01` delivered the validated Writer draft after Reviewer fallback, so the
  run committed six rather than seven checkpoints;
- `DC03` used the human-readable heading `Decision Support Mode` rather than
  the frozen report token `decision_support`; and
- `DC02` supplied a commercial pass threshold — at least one pharmaceutical
  partner or pilot customer — without marking that threshold as unapproved or
  as an analyst proposal, even though the incomplete context had not supplied
  a target application, owner, decision type, or success threshold.

These are prompt-compliance and observability findings. No cited source was
opened during this audit, so they say nothing about factual correctness or the
commercial correctness of the `DEFER` recommendation.

## Execution

The operator authorized exactly three sequential root runs with USD 0.05 per
run and USD 0.12 study soft stops. Before submission:

- GitHub/Railway deployment `6103812791` reported `success` for the exact
  revision above, and no newer production deployment appeared during the
  study;
- `/health/ready` returned HTTP 200 with `llm`, `search`, `outputs`, and
  `paid_accounting` all `ok`;
- `/api/access/check` accepted the selected owner code without persisting the
  code in any study artifact;
- active run and paid-operation counts were both zero; and
- that owner's visible history contained five runs, with none started on
  2026-08-26 UTC.

The internal owner count in the durable paid-operation ledger is intentionally
not exposed by the public API. Its schema/readability state was therefore
observed through readiness, while its exact pre-run count remained
`not_inspectable`. Admission of all three requests and the final owner history
are additional boundary evidence; they do not make the hidden pre-run count
publicly reconstructable.

| Case | Public mode | State | Sources A/P/M | Review | Checkpoints | Tokens / requests | Cost | Duration |
|---|---|---|---:|---|---|---:|---:|---:|
| [`DC01`](https://academic-commercialization-agent.up.railway.app/run/20260826T124329Z-cfd5dc20e750ae6048e3dd503e577960) | `orientation` | completed | 3 / 8 / 8 | fallback | 6 / 7 | 80,643 / 7 | $0.032993 | 152 s |
| [`DC02`](https://academic-commercialization-agent.up.railway.app/run/20260826T124828Z-7126fa03452d0ddc95e52ad3c6d6425e) | `decision_context_incomplete` | completed | 4 / 8 / 8 | passed | 7 / 7 | 87,623 / 7 | $0.035534 | 120 s |
| [`DC03`](https://academic-commercialization-agent.up.railway.app/run/20260826T125132Z-17277cad7e2025ee8881b81687b851f4) | `decision_support` | completed | 4 / 8 / 8 | passed | 7 / 7 | 98,382 / 7 | $0.040815 | 185 s |
| **Total** | — | 3 / 3 completed | — | — | — | **266,648 / 21** | **$0.109342** | **457 s** |

The owner history increased from five to eight, and its newest three entries
were exactly `DC01`, `DC02`, and `DC03` in execution order. Every run reported
`recovery.state=not_requested`. No retry, resume, cancellation, replacement
topic, or fourth paid operation was used.

## Frozen criteria

| # | Verdict | Observation |
|---:|---|---|
| 1 | **fail** | All three runs completed with no child, but `DC01` reported `quality_review.status=fallback` and committed retrieval, three evidence nodes, Writer, and Scorer only. Its Reviewer checkpoint was absent. The public run contract also does not expose `pipeline_revision`; the exact deployment was verified externally, while per-run revision reporting remained `not_inspectable`. |
| 2 | **pass** | Status and progress both exposed byte-equivalent gates for `orientation`, `decision_context_incomplete`, and `decision_support`, including provided fields, missing core fields, and GO/NO_GO authority. |
| 3 | **pass** | Each persisted shadow artifact reported `planner_state=not_run`, zero executed calls, USD 0 added search cost, `evidence_changed=false`, and its own source-collection SHA-256. |
| 4 | **pass** | Every cost was complete and below USD 0.05; the USD 0.109342 total was below USD 0.12. |
| 5 | **pass** | `DC01` named orientation mode, said actor-specific `GO/NO_GO is not assessed`, marked the decision owner and cost/time as not established, and contained none of the context unique to `DC02` or `DC03`. |
| 6 | **pass** | `DC02` named `decision_context_incomplete`, withheld actor-specific GO/NO_GO, explicitly listed `target_application`, `decision_owner`, and `decision_type` as missing, and did not copy their values from `DC03`. |
| 7 | **fail** | `DC03` addressed the supplied committee, application, horizons, and funding question and issued one operative, evidence-conditioned `DEFER`. Its report heading was `Decision Support Mode`, not the frozen literal `decision_support`; the criterion is not rewritten after observing that semantically equivalent wording. |
| 8 | **pass** | The reports labelled supplied decision context separately from retrieved sources, marked analyst proposals/inferences, and repeated that patent white-space analysis was preliminary research rather than legal advice or an FTO opinion. The synthetic asset was attributed to decision context rather than presented as independently verified. |
| 9 | **fail** | No report invented a budget, and `DC03` preserved the supplied 90-day/12-month horizons while stating that no success threshold was approved. `DC02`, however, introduced `At least one pharma partner or pilot customer` as a measurable pass threshold without the proposal/unapproved qualification used elsewhere. The all-cases criterion therefore failed. |
| 10 | **pass** | `DC01` contained none of the asset, jurisdiction, application, owner, decision, horizon, or constraint prose from later cases. `DC02` contained its own asset only and none of the `DC03`-unique application, owner, decision, horizon, or validation constraints. |

## Additional observations

`DC01` spent two Reviewer requests and then exposed only the stable public
classification `failure_type=Exception`. No reviewer notes artifact or Reviewer
checkpoint was produced. The underlying exception is intentionally absent from
the public response, and no operator log was exported into this study, so its
root cause is `not_inspectable`; it must not be guessed from the fallback state.

A 2026-08-27 operator follow-up later obtained the persisted process log and
identified a Reviewer correction whose exact target occurred zero times. That
post-study diagnosis and its zero-network repair are recorded separately in
[the dated erratum](errata-2026-08-27-decision-context-reviewer-zero-target.md).
It does not change this frozen result or make the canary a pass.

Claim-grounding screens completed but checked zero claims in all three reports.
They recorded 2, 1, and 5 unverifiable quantitative claims respectively. That
is neither a grounding pass nor evidence of hallucination: the check ran, but
the retained source text could not verify those claims. Source truth remains
`not_evaluated` as frozen in the protocol.

Source retrieval varied across repeated requests for the same topic: `DC01`
retained three academic sources, while `DC02` and `DC03` retained four, and all
three source-collection hashes differed. This is expected for live retrieval
and prevents treating the three reports as a causal comparison of context
mode. The canary measures each mode's contract independently.

## Next admissible work

No production behavior changed during this result capture. The next work should
be narrow and evidence-led:

1. the operator-side `DC01` exception and offline red/green reproduction are
   complete in the dated erratum; no paid rerun has been performed;
2. a zero-network follow-up now persists a non-secret immutable
   `pipeline_revision` and exposes it at both status endpoints. Historical runs
   remain `null`, so this does not retrospectively identify these three canary
   runs; see the
   [boundary result](results-2026-08-27-public-pipeline-revision-seam.md);
3. make the report's applicability label deterministic at the delivery seam,
   and distinguish supplied/approved success thresholds from explicitly
   labelled analyst proposals; and
4. freeze a new regression protocol before any paid rerun. These three runs may
   not be reused as post-fix evidence.

This result does not authorize a rerun, a production fix, Tool Calling,
supplementary search, source verification, or a user-value study.
