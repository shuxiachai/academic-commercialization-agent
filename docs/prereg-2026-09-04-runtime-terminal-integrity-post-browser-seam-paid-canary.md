# Pre-registration: runtime terminal integrity post-browser-seam paid canary

- **Frozen:** 2026-09-04, after the zero-request RTI01 preflight and before
  any replacement provider-backed run
- **Implementation baseline:**
  `67399495477d8651d0004c7b8e26b4e453e4ff91`
- **Execution revision:** the first `main` merge commit containing this
  browser fix, protocol, and manifest; record the full deployed SHA before
  submission
- **Manifest:**
  `tests/fixtures/runtime_terminal_integrity_post_browser_seam_canary_manifest.json`
- **Manifest SHA-256:** `3293fe6abc95f1a2da113136e152a15ae1d27db432f0efe27ee9e776dc5fde37`
- **Predecessor result:**
  `docs/results-2026-09-04-runtime-terminal-integrity-paid-canary-preflight.md`
- **Provider calls authorized by this document:** none
- **Future paid scope requiring fresh authorization:** one operator-funded
  root, with no resubmission, recovery child, cancellation, Planner call, or
  supplementary search
- **Future soft cost stop requiring fresh authorization:** USD 0.10; the one
  already admitted root may finish slightly above the boundary

## Question

After the missing browser seam is repaired, does the deployed implementation
preserve one real Qwen run's deadline policy, cumulative usage state, immutable
terminal outcome, reason code, termination method, and elapsed time through
disk, both public read endpoints, and the browser?

This remains a production delivery-seam canary. It is not a report-quality
benchmark, provider-latency SLO, clinical-validity study, or production Tool
Calling evaluation.

## Why the topic remains eligible

The exact request is unchanged:

> AI-assisted handheld ultrasound for heart-failure screening in rural clinics
> commercialization

RTI01 did not create a run. Its preflight found that the deployed browser
bundle omitted the immutable terminal reason and method, then stopped with
zero provider/search requests and USD 0.00 cost. No retrieval result, model
output, report, or outcome exists for this topic. Reusing the frozen question
therefore preserves the original experimental variable rather than rerunning
a consumed case. RTI02 is a new execution identity and may run only against
the new merged deployment.

The topic-only request remains an `orientation` assessment with no GO/NO_GO
permission and no established threshold.

## Change under study

The runtime writer, terminal schema, accounting model, timeout policy,
retrieval, prompts, six-node topology, guardrails, and scoring are unchanged.

The browser now has one dedicated `#run-terminal` seam. It translates the
four current reason codes, preserves a future unknown code verbatim, exposes
the raw `reason_code` and `termination_method` in the tooltip, stays silent
for a live run with no terminal record, and distinctly labels missing or
unreadable records after a terminal state. The loopback Chromium smoke commits
a real schema-1 terminal fixture and asserts the complete
disk-to-API-to-JavaScript-to-DOM path.

These added branches are test evidence, not claims that a paid run observed
failure, cancellation, timeout, missing-record, or unreadable-record paths.

## Frozen production policy

| Boundary | Frozen value |
|---|---:|
| API hard watchdog | 1,800 seconds |
| One provider attempt | 150 seconds |
| Reviewer reserve | 240 seconds |
| Other-node finalization reserve | 60 seconds |
| Terminal schema | 1 |
| Poll interval | 10 seconds |
| Maximum observation window | 1,900 seconds |

The deployed wrapper remains the visible retry owner. "No operator retry"
does not erase code-owned retries. SDK-hidden retries remain disabled, and
normal accounting must represent every visible provider attempt.

## Admission preflight

The paid root is inadmissible until all of the following are recorded:

1. this protocol, manifest, browser code, and tests are merged to `main`;
2. the committed manifest bytes reproduce the SHA-256 above;
3. public CI passes the full Linux/Windows Python 3.11/3.12 matrix, coverage,
   latest Ruff, narrow Pylint, Docker, and loopback Chromium smoke;
4. Railway serves the exact merge revision and readiness returns HTTP 200 with
   `llm`, `search`, `outputs`, and `paid_accounting` all `ok`;
5. both OpenAPI schemas expose `pipeline_revision`, `runtime_budget`,
   `usage`, `usage_accounting`, and `terminal`;
6. deployed markup and JavaScript contain `#run-terminal`,
   `terminalSummary(terminal, state)`, and
   `terminalTitle(terminal, state)`, including `worker_completed`,
   `reason_code`, and `termination_method`;
7. an operator code passes read-only admission without its value entering a
   manifest, URL, log projection, or artifact;
8. pre-run history, readiness, revision, and active paid-operation count are
   recorded before submission; and
9. the user gives fresh authorization naming the new deployed revision,
   selected operator code, one root, USD 0.10 soft stop, all bans above, and
   the possible small overrun of the already admitted root.

Failure of any item means zero paid submissions. The earlier authorization
named `6739949...` and cannot authorize changed code.

## Frozen execution protocol

1. Recompute the committed manifest digest and validate RTI02 through the
   deployed request schema.
2. Submit the root exactly once and persist its run ID before polling.
3. Poll status and progress no more often than every ten seconds. Preserve
   every observed stage, elapsed value, cumulative usage snapshot, accounting
   state, runtime budget, terminal projection, checkpoint state, and
   quality-review state in a non-secret artifact.
4. Do not cancel, replace, retry, or resume the run. A watchdog stop is an
   observed timeout, not operator cancellation.
5. Stop after a terminal state or 1,900 seconds. If neither endpoint exposes an
   inspectable terminal state, classify it as `not_inspectable` and do not
   launch another run.
6. At terminal observation, fetch status, progress, the full terminal artifact,
   top-level usage fields, checkpoint index, report if present, evidence-gap
   shadow, run history, and the browser run page. Do not invoke a supplementary
   adapter or open external source pages.
7. Compare terminal artifact, status, and progress field by field. Compare the
   final durable usage snapshot and accounting state across both endpoints.
8. Verify every observed cumulative token/request/cost counter is
   nondecreasing. Missing intermediate samples are `not_observed`.
9. Inspect the browser's visible terminal reason and tooltip. The completed
   lane requires visible `worker completed` plus raw `worker_completed` and
   `worker_exit`; API-only presence is insufficient.
10. Classify exactly one outcome lane and publish the result even if it fails,
    times out, exceeds the soft stop, or is not inspectable.

## Primary acceptance criteria

The canary passes only if every item below passes:

1. Exactly one root and no child exist, and `pipeline_revision` equals the
   separately authorized deployed SHA.
2. The root reaches `completed`; schema 1 records
   `reason_code=worker_completed`, `termination_method=worker_exit`, and
   timezone-aware start/end values.
3. `runtime_budget.state=active` and all four frozen timeout/reserve values
   agree on status and progress.
4. The terminal artifact and both public projections agree on state, reason,
   method, timestamps, elapsed time, last stage, and timeout.
5. Submission-to-terminal time and terminal elapsed time differ by no more
   than 30 seconds.
6. `usage_accounting.state=complete`, `run_complete=true`,
   `in_flight_request_may_have_spent=false`, and a non-null usage snapshot
   agree on status and progress.
7. Every observed cumulative counter is nondecreasing, and the final snapshot
   is no smaller than any earlier sample.
8. Inspectable estimated cost is no greater than USD 0.10.
9. Every recorded LLM role identity is exactly `qwen3.5-plus`; provider,
   request, token, and price-completeness fields remain inspectable.
10. Evidence-gap records zero Planner/tool calls, zero supplementary-search
    cost, and no supplementary mutation of the validated source set.
11. Status, progress, and browser agree that the run is terminal. The browser
    visibly renders the translated reason, and its tooltip preserves the raw
    reason code and termination method. It must not display exact or zero cost
    when the API says lower-bound or unavailable.
12. The orientation gate contains no supplied owner, threshold, or GO/NO_GO
    authority.

## Outcome lanes fixed before execution

- `completed_reviewed`: evaluate the primary gate; only ordinary completion
  was observed.
- `completed_reviewer_fallback`: evaluate the primary gate and additionally
  require `quality_review.status=fallback`, the validated Writer artifact, and
  independent Scorer output.
- `failed`: evaluate the failed record and accounting semantics; primary gate
  fails.
- `timeout`: require `hard_timeout`, a valid API termination method, at least
  1,800 elapsed seconds, and lower-bound or unavailable accounting; primary
  gate fails.
- `cancelled`: protocol interruption; primary gate fails.
- `not_inspectable`: a required artifact, response, revision, accounting
  state, or browser field cannot be read; silence is not a pass.

Unobserved fallback, timeout, missing-record, and unreadable-record branches
remain `not_observed`; test coverage cannot turn them into live evidence.

## Measurement limits and exclusions

One run cannot establish report accuracy, source truth, clinical validity,
stable latency/cost/availability, an SLO, generalization to another topic or
provider, exactly-once interrupted-request billing, or production Tool Calling
value. It observes only the lane that actually occurs.

This protocol changes no scoring formula, evidence-confidence floor, maturity-
language check, uncited-claim blocking policy, prompt cache, source-summary
retrieval, CrewAI version, model adapter, retrieval rule, timeout value,
guardrail, or Tool Calling connection. It authorizes no provider request by
itself.
