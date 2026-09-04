# Runtime terminal integrity post-browser-seam paid canary result

Date: 2026-09-04

- **Execution revision:** `522094a4330133c33aba2c3059bfd646be80b792`
- **Railway deployment:** `6259902301`, successful before admission
- **CI:** 8/8 required checks passed on the execution revision
- **Frozen manifest SHA-256:**
  `3293fe6abc95f1a2da113136e152a15ae1d27db432f0efe27ee9e776dc5fde37`
- **Case:** `RTI02`
- **Run ID:** `20260904T074754Z-737dc6af90498c395a3ff2ac942c1cf8`
- **Outcome lane:** `completed_reviewed`
- **Primary acceptance:** **PASS, 12/12**
- **Protocol conformance:** qualified by a minor read-only observer-cadence
  deviation described below

## Admission and execution bounds

The admission preflight completed before the only paid POST. The local checkout
and Railway deployment matched the authorized revision. The committed manifest
reproduced its frozen digest; readiness returned HTTP 200 with `llm`, `search`,
`outputs`, and `paid_accounting` all `ok`; both OpenAPI response schemas exposed
the five runtime fields; and the deployed HTML and JavaScript contained the
terminal reason/method DOM seam. The selected operator code passed without its
value entering a URL, manifest, observation artifact, or result document.

Pre-run owner history contained 10 runs, zero with the frozen topic. Shared
capacity reported zero active runs and zero active paid operations out of five.
The POST created one root. Post-run history contained 11 runs and exactly one
matching topic. No child, operator retry, resume, cancellation, Planner call, or
supplementary search occurred.

## Observed path

The first observations of each public stage were:

| Seconds after admission | State | Stage | Cumulative cost state |
|---:|---|---|---|
| 10 | running | status accepted | unavailable |
| 20 | running | Source Collection & Validation | unavailable |
| 80 | running | Evidence Collection | unavailable |
| 310 | running | Report Writing | USD 0.016776 lower bound |
| 530 | running | Quality Review & Citation Check | USD 0.040317 lower bound |
| 690 | running | Commercialization Scoring | USD 0.053175 lower bound |
| 890 | completed | Done | USD 0.067922 complete |

The immutable record reports 885 seconds from worker start to finish. The
submission-to-terminal interval was 885.581212 seconds, only 0.581212 seconds
different from the recorded monotonic elapsed value.

## Primary acceptance result

| # | Frozen criterion | Result | Observed evidence |
|---:|---|---|---|
| 1 | One root, no child, exact revision | PASS | One new history row; no `resumed_from`; status and progress both report `git:522094a...` |
| 2 | Normal immutable completion | PASS | Schema 1, `completed`, `worker_completed`, `worker_exit`; both timestamps are timezone-aware |
| 3 | Runtime budget survives both APIs | PASS | `active`; 1800 / 150 / 240 / 60-second policy agrees field-for-field |
| 4 | Artifact/status/progress terminal agreement | PASS | State, reason, method, timestamp instants, elapsed, last stage and timeout agree |
| 5 | Wall and monotonic elapsed agree | PASS | Difference 0.581212 seconds, below the frozen 30-second maximum |
| 6 | Complete final usage | PASS | `complete`, `run_complete=true`, no possible in-flight spend; usage agrees across all three seams |
| 7 | Cumulative counters never decrease | PASS | 89 snapshots; 51 status and 51 progress counters checked with zero regressions |
| 8 | Cost remains within authorization | PASS | USD 0.067922, below USD 0.10 |
| 9 | Provider/model and pricing identity | PASS | Six requests and 69,932 tokens; all six roles are exactly `qwen3.5-plus`; pricing is complete with no unpriced model |
| 10 | No Tool Calling mutation | PASS | `planner_state=not_run`, zero proposed/executed calls, USD 0.00 added search cost, `evidence_changed=false` |
| 11 | Browser receives the real terminal truth | PASS | Real Chromium showed `COMPLETED · worker completed`; tooltip preserved `worker_completed` and `worker_exit` |
| 12 | Orientation remains non-binding | PASS | No supplied fields, no owner-approved threshold, and `go_no_go_allowed=false` on status and progress |

The real-browser inspection allowed only same-origin GET requests. It observed
20 GETs, zero mutating methods, and zero blocked attempts. This is DOM evidence,
not an inference from shipped source text.

## Usage, persistence, and review

The final six model requests used 69,932 tokens and a conservative USD 0.067922
estimate. `usage.cost_complete=true`, `unpriced_models=[]`, and the price basis
is the built-in Qwen3.5 Plus peak tier dated 2026-08-30. Intermediate accounting
correctly remained a lower bound; only the final snapshot became complete.

Checkpointing finished `complete` with retrieval, academic, patent, market,
Writer, Reviewer, and Scorer committed and no persistence errors. Recovery was
`not_requested`. The independent quality-review projection was `passed` with
zero unapplied corrections. Retrieval retained 3 academic, 8 patent, and 5
market sources with no failed domain and no incomplete evidence artifact.

## Observer protocol deviation

The observer intended a fixed ten-second cadence. Of 88 repeated intervals,
86 were at least 10.000 seconds when measured at dispatch and two were 9.984
seconds. The maximum early dispatch was therefore 16 milliseconds. This arose
because the loop scheduled against absolute ten-second boundaries: ordinary
timer jitter in one cycle can be followed by a slightly shorter interval in
the next.

This did not create another root, provider call, search call, mutation, or
cost, and it cannot change any of the 12 primary terminal assertions. It is
still a literal deviation from the frozen instruction to poll no more often
than every ten seconds. The result is therefore reported as
`completed_reviewed / primary PASS with minor observer-protocol deviation`, not
as perfectly conformant. A future observer must sleep ten seconds after each
completed status/progress pair rather than target absolute clock boundaries.
RTI02 is consumed and must not be rerun to erase this note.

## Secondary observations outside the primary question

Three observations are retained without turning this terminal canary into a
quality or latency benchmark:

1. The 885-second completion is much slower than the README and API's old
   roughly-three-minute wording. Together with the earlier 306-second Qwen
   completion, it proves provider-bound variability but does not establish a
   percentile or SLO. Absolute public time promises should be removed.
2. The advisory report audit emitted six
   `decision_threshold_has_no_local_authority_qualifier` warnings even though
   the report labels each pass item `Proposed Pass Threshold` and immediately
   precedes the section with a global statement that every threshold is an
   analyst proposal requiring owner confirmation. This is a precision-study
   candidate, not evidence for blocking or a reason to edit the heuristic
   before measuring the existing 30 reports.
3. Claim grounding checked one quantitative academic claim with zero
   mismatches and marked three market claims unverifiable. Authority coverage
   returned `not_applicable` for a clinical-screening topic. That classification
   is a separate applicability hypothesis requiring offline measurement; this
   run alone does not justify changing the detector.

## What this establishes — and what it does not

This run establishes one ordinary Qwen completion's terminal, deadline,
accounting, checkpoint, decision-gate, API, and browser delivery seams on the
named deployment. It also establishes that the production shadow planner made
zero calls and did not mutate evidence for this run.

It does not establish a latency SLO, report accuracy, source truth, clinical
validity, repeated-run stability, Reviewer fallback, hard-timeout behavior,
cancel behavior, missing/unreadable-terminal behavior, interrupted-request
billing, or production Tool Calling value. Those unobserved branches remain
unobserved; offline tests cannot promote them to live evidence.
