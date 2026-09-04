# Runtime terminal integrity paid canary - preflight result

Date: 2026-09-04
Authorized deployed revision: `67399495477d8651d0004c7b8e26b4e453e4ff91`
Frozen manifest SHA-256: `4aaa13f6f2fba30ffd479a086b0f192c86bfb5c2ce87c49d77f4728671a5a2b5`
Strict outcome: **not_started / preflight_failed**
Paid provider or search requests: **0**
Observed cost: **USD 0.00**

## What happened

The user separately authorized one production root under the frozen RTI01
protocol. The admission preflight ran before any paid POST, as the protocol
requires. At `2026-09-04T06:36:54.2841603Z`, Railway deployment
`6258716986` reported success and served the authorized revision. Readiness
returned HTTP 200 with `llm`, `search`, `outputs`, and
`paid_accounting` all healthy. The operator access check passed, while the
access-code value was deliberately excluded from URLs, logs, manifests, and
this result.

The committed manifest bytes reproduced the frozen digest. Both deployed
OpenAPI response schemas exposed `pipeline_revision`, `runtime_budget`,
`usage`, `usage_accounting`, and `terminal`. The deployed browser bundle
also contained the complete, lower-bound, and unavailable usage branches.

The final browser requirement failed. Although the API exposed
`terminal.reason_code` and `terminal.termination_method`, the deployed
JavaScript did not consume either field and did not render
`worker_completed`. A user could see the broad state and accounting meaning
but not the immutable process reason or stop method. Treating the API field as
equivalent to browser delivery would repeat the exact class of dropped-client-
field defect this project tests against.

## Stop evidence

The preflight therefore stopped before adapter or run construction:

| Boundary | Observed |
|---|---:|
| Root runs submitted | 0 |
| Recovery children | 0 |
| Provider requests | 0 |
| Search requests | 0 |
| Planner calls | 0 |
| Supplementary searches | 0 |
| Observed cost | USD 0.00 |
| Active paid operations after preflight | 0 |

Pre-run owner history remained at 10 records; its latest existing run was
`20260903T160613Z-6586ac1d3fe13034f891df46571b6401`. No RTI01 run ID
exists because no root POST occurred.

## Interpretation

This is a successful fail-closed admission decision, not a successful runtime
canary and not a production defect in provider execution. It establishes that
the frozen preflight prevented spending when one required user-visible seam
was absent. It does not establish terminal behavior under a real Qwen run,
report quality, timeout behavior, Reviewer fallback, cost stability, or
production Tool Calling.

Because the topic never reached retrieval or a provider, it remains
unconsumed. A browser fix, real API-to-DOM regression test, newly frozen
manifest, merged deployment, and fresh exact-revision authorization are
required before one replacement root may be submitted. The prior authorization
cannot be carried forward to changed code.
