# Pre-registration: runtime terminal integrity post-deployment paid canary

- **Frozen:** 2026-09-04, before any provider-backed run in this study
- **Implementation baseline:** `cca509ea7e1c122a044eb3d4d90debd46568d05b`
- **Execution revision:** the first `main` merge commit containing this protocol
  and its manifest; record the full deployed SHA before submission
- **Manifest:**
  `tests/fixtures/runtime_terminal_integrity_paid_canary_manifest.json`
- **Manifest SHA-256:** `4aaa13f6f2fba30ffd479a086b0f192c86bfb5c2ce87c49d77f4728671a5a2b5`
- **Provider calls authorized by this document:** none
- **Future paid scope requiring fresh authorization:** one operator-funded root
  run, with no operator resubmission, recovery child, cancellation, Planner call,
  or supplementary search
- **Future soft cost stop requiring fresh authorization:** USD 0.10; the single
  already admitted root may finish slightly above the boundary

## Question

Does the deployed runtime-integrity implementation preserve one real Qwen
run's deadline policy, cumulative usage state, immutable terminal outcome and
elapsed time through disk, both public read endpoints, and the browser?

This is a production delivery-seam canary. It is not a report-quality
benchmark, a provider-latency SLO, an evaluation of clinical evidence, or a
test of production Tool Calling.

## Why this case was frozen

The exact topic is:

> AI-assisted handheld ultrasound for heart-failure screening in rural clinics
> commercialization

Repository history contains no earlier canary or benchmark with this exact
topic. It was selected before the first provider call because it is a
source-rich biomedical commercialization question that should exercise all
three deterministic retrieval domains, authority coverage, six LLM stages,
usage accounting and terminal publication. It is not designed to trigger a
failure, and being previously unused does not make one run an independent
generalization study.

The request intentionally contains only the topic. It must therefore remain
an `orientation` assessment with no GO/NO_GO permission and no established
decision threshold. Decision Context behavior is not the variable under test.

## Frozen production policy

The manifest binds the canary to the following code-owned values:

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
means this study will not submit another root, resume a child, or repair a
failed result. It does not pretend that code-owned retries disappeared; SDK-
hidden retries must remain disabled and every visible provider attempt must be
represented by the run's normal accounting.

## Admission preflight

The paid root is inadmissible until all of the following are recorded:

1. this protocol, manifest, and manifest tests are merged to `main`;
2. the committed manifest bytes reproduce the SHA-256 above;
3. Railway serves the exact merge revision and `/health/ready` returns HTTP
   200 with `llm`, `search`, `outputs`, and `paid_accounting` all `ok`;
4. the deployed OpenAPI schemas expose `pipeline_revision`, `runtime_budget`,
   `usage`, `usage_accounting`, and `terminal` on both `RunStatus` and
   `RunProgress`;
5. the deployed browser bundle contains the complete/lower-bound/unavailable
   accounting branches and terminal-reason rendering;
6. one operator access code passes the read-only admission check without the
   code entering the manifest, URL, inspected log projection, or artifact;
7. pre-run history, readiness, revision and active paid-operation count are
   recorded before submission; and
8. the user gives fresh authorization naming the exact deployed revision,
   chosen access code, one root run, USD 0.10 soft stop, the bans above, and
   the possible small overrun of the already admitted root.

Failure of any item means zero paid submissions. Readiness and access checks
are not permission to start the run.

## Frozen execution protocol

1. Recompute the manifest digest from the committed bytes and validate `RTI01`
   through the deployed request schema.
2. Submit the root exactly once and persist its run ID before the first poll.
3. Poll both status and progress at no less than ten-second intervals. Preserve
   every observed stage, elapsed value, cumulative usage snapshot, accounting
   state, runtime budget, terminal projection, checkpoint state and quality-
   review state in a non-secret observation artifact.
4. Do not cancel, replace, retry or resume the run. The API hard watchdog may
   stop it under the deployed policy; that is an observed `timeout`, not an
   operator cancellation.
5. Stop polling after a terminal state or 1,900 seconds. If neither endpoint
   exposes an inspectable terminal state by then, classify the result as
   `not_inspectable`; do not launch another run.
6. After terminal observation, fetch status, progress, the full `terminal`
   artifact, top-level usage fields, checkpoint index, report if present,
   evidence-gap shadow,
   run history and browser run page. Do not call a supplementary evidence
   adapter or open external source pages.
7. Compare the full terminal record with its bounded projection on both read
   endpoints. Compare the final durable usage snapshot with top-level usage
   and accounting on both endpoints.
8. Verify that every *observed* cumulative token/request/cost counter is
   monotonic. Polling need not see every node; an unseen intermediate snapshot
   is `not_observed`, not a failure or a fabricated measurement.
9. Classify the run into exactly one frozen outcome lane and report both the
   primary canary result and any narrower terminal/accounting observation.
10. Publish the result even if it fails, times out, exceeds the soft stop, or
    cannot be inspected.

## Primary acceptance criteria

The post-deployment canary passes only if every item below passes:

1. Exactly one root exists, no child is created, and its
   `pipeline_revision` exactly equals the separately authorized deployed SHA.
2. The root reaches `completed`. Its immutable record has schema 1,
   `state=completed`, `reason_code=worker_completed`,
   `termination_method=worker_exit`, and a timezone-aware start and end.
3. `runtime_budget.state=active` and all four frozen timeout/reserve values are
   identical on status and progress. Missing metadata is not a historical-run
   exemption because this canary is created after deployment.
4. The downloadable `terminal` artifact and both public projections agree on
   state, reason, method, timestamps, elapsed time, last stage and timeout.
   Public elapsed time must equal the monotonic terminal value, not a status-
   file modification-time estimate.
5. External submission-to-terminal duration and terminal elapsed time differ
   by no more than 30 seconds. This tolerance covers polling and network delay;
   it is not a latency target.
6. `usage_accounting.state=complete`, `run_complete=true`, and
   `in_flight_request_may_have_spent=false`. Usage is a non-null snapshot on
   disk and is identical on status and progress. `unavailable` or a missing
   snapshot fails this completed-run criterion rather than meaning zero spend.
7. Every cumulative counter actually observed during polling is nondecreasing,
   and the final snapshot is no smaller than any earlier snapshot. Absence of
   an intermediate poll sample is reported separately.
8. The final estimated cost is inspectable and no greater than USD 0.10. A
   permitted overrun is preserved as evidence but fails this numerical gate.
9. Every recorded LLM role identity is exactly `qwen3.5-plus`; provider,
   request, token and cost-completeness fields remain inspectable.
10. The evidence-gap artifact records zero Planner/tool calls, zero
    supplementary-search cost and no supplementary mutation of the validated
    source set.
11. Status, progress and the browser agree that the run is terminal and expose
    the same accounting meaning. The browser must not display an exact or zero
    bill when the API says lower-bound or unavailable.
12. The orientation gate remains bounded and contains no supplied owner,
    threshold or GO/NO_GO authority.

## Outcome lanes fixed before execution

The primary gate above deliberately requires completion. Other outcomes may
still provide narrower evidence, but cannot be promoted to a pass:

- `completed_reviewed`: the primary gate is evaluated; only the ordinary
  completion path was observed.
- `completed_reviewer_fallback`: the primary gate is evaluated, and
  `quality_review.status=fallback` plus the validated Writer and independent
  Scorer artifacts are additionally required. This is the only lane that can
  support a live Reviewer-deadline fallback claim.
- `failed`: the worker's failed terminal record and accounting semantics are
  evaluated, while the primary canary fails.
- `timeout`: the API's `hard_timeout` record must use `terminate`, `kill`, or
  `already_exited`; elapsed time must be at least 1,800 seconds, and accounting
  must be `lower_bound` when a snapshot exists or `unavailable` when it does
  not. Any in-flight uncertainty must remain explicit. The primary canary
  fails even when this narrower timeout contract is correct.
- `cancelled`: this violates the no-cancellation protocol and fails.
- `not_inspectable`: a required seam or artifact could not be read; silence is
  not a pass.

If Reviewer fallback or hard timeout does not occur, that path remains
`not_observed`. A successful ordinary completion cannot validate it by analogy.

## Measurement limits fixed in advance

This study cannot establish:

- report accuracy, source truth, citation entailment or clinical validity;
- whether the topic is commercially viable or useful to a real decision maker;
- stable latency, cost, availability, timeout rate or any production SLO;
- behavior on another topic, model, language, deployment or host failure;
- exactly-once provider billing after an interrupted request;
- Reviewer fallback unless that lane actually occurs;
- hard-timeout lower-bound behavior unless that lane actually occurs; or
- value, precision, recall or readiness of production Tool Calling.

One run is one boundary observation, not a rate. All failed, partial,
unavailable, over-budget, `not_inspectable`, and `not_observed` states must be
retained.

## Explicit exclusions

This protocol changes no scoring formula, evidence-confidence floor, maturity-
language check, uncited-claim blocking policy, prompt cache, source-summary
retrieval, CrewAI version, model adapter, retrieval rule, timeout value,
guardrail, or production Tool Calling connection. It authorizes no provider
request by itself.
