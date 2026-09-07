# Current evidence status

Snapshot for the documentation consolidation on 2026-09-05, based on public
main `0fdaa76a107cf034c16c1ffa6e3ae623e4c63fe2`. This page separates implemented
contracts from observed behaviour and from claims that have not been established.
It does not change an experiment's result, threshold or authorization.

## Production capability

The shipped system is an evidence-constrained six-stage LLM workflow, with
deterministic retrieval before CrewAI. It supports topic/PDF input, optional
Decision Context, validated references, scoring, bounded review, single-replica
paid admission, checkpoint recovery and explicit terminal/accounting states.

Qwen3.5 Plus, DeepSeek, Anthropic and OpenAI configuration paths exist. A
provider being configurable is not proof of equivalent quality or cost.
Supplementary Tool Calling remains **zero-call shadow mode**.

The documentation audit reran the unmodified code and obtained 2071 tests plus
678 subtests. CI includes four OS/Python cells, lint, an 85% coverage floor,
zero-provider Chromium and Docker. Test totals are revision snapshots, not
an accuracy metric. Installation/lint resolution can need network even though
the default test execution uses no provider calls.

Subsequent maintenance also preserves explicit Cancel/Delete intent across
the first-party browser and API, and withholds mutation controls for unknown
states. Legacy unqualified DELETE remains dual-purpose for compatibility;
this is an offline-verified contract, not an observed data-loss rate. See the
[stale-click regression and limits](results-2026-09-06-run-mutation-intent.md).

The delivered applicability paragraph is also rebound to the current code-owned
gate even when generated prose contains a copied or forged internal marker.
Persistence, report download and Chromium are covered; this is not general
semantic verification or evidence of an observed production forgery. See the
[authority regression and 110-report diagnostic](results-2026-09-06-report-applicability-authority.md).

Readiness probes are isolated across concurrent requests, PDF market queries
share the rolling year window, and report-audit details distinguish coverage
and malformed data. These are offline-verified delivery fixes, not measured
production incident rates or improved report accuracy. See the
[maintenance record](results-2026-09-06-maintenance-readiness-query-audit.md).

## Main evaluation ledger

Composer maintenance now excludes overlapping tab-local submissions/extractions,
binds attachment responses to the current selection, and preserves distinct 429
reasons in the UI. LLM readiness shares effective credential resolution with
operator construction. HTTP/Node/Chromium regressions are offline evidence, not
an observed reduction in bills, server exactly-once delivery or a quality gain.
See the [verified scope](results-2026-09-06-composer-paid-operation-integrity.md).

Further maintenance isolates recurring cleanup faults from timeout supervision,
serializes native PDF parsing/closure, preserves paid acceptance through browser
storage failures and resume re-renders, and atomically publishes single-flight PDF
exports. These are fault-injected offline contracts, not measured production
incident reductions, exact-once billing or PDF semantic validation. See the
[runtime/paid-delivery maintenance record](results-2026-09-06-maintenance-runtime-paid-delivery.md).

Stop ownership also spans process termination and terminal publication: capacity,
status/progress, deletion and retention share that boundary. Failed termination
retains the worker; concurrent stops cannot acknowledge two successful owners.
Event-held HTTP tests and local child-process tests establish the bounded offline
contract, not a production incident rate or remote-provider cancellation. See the
[stop-ownership verification](results-2026-09-06-run-stop-ownership.md).

Synchronous maintenance is also offloaded from the ASGI loop without abandoning
an active stage on cancellation. Held-stage HTTP requests and ordered shutdown
are offline-tested; this is not a probe-latency SLO, freshness guarantee or proof
that a stuck filesystem can be interrupted. See the
[event-loop/drain contract](results-2026-09-06-maintenance-event-loop.md).

Both health endpoints additionally expose UTC dispatch/completion times and
monotonic duration/age facts. A current attempt preserves the previous result;
polling does not refresh it. This is observation metadata, not a new stale
threshold or readiness eviction rule. See the
[time-qualified snapshot contract](results-2026-09-07-maintenance-observation-age.md).

Cleanup now exposes per-attempt deleted/skipped/failed counts at both health
endpoints, with partial/unavailable scan states rather than inferring full
deletion from a normal return. Unknown inventory is not zero; cleanup-only
faults remain advisory. This is not proof of a production storage failure or
complete erasure; see the [outcome contract](results-2026-09-07-cleanup-outcome-observability.md).

| Question | Observed evidence | Boundary / decision |
|---|---|---|
| Can the frozen baseline complete with consistent mechanics? | 30/30 completed; 26/30 TRL-range hits; 30/30 correct formula and structure; zero uncited numeric lines; 7/10 topics hit their range in every repetition | Expected ranges were revised after early observations. Not independent accuracy or full hallucination measurement. [CSV](../outputs/benchmark/benchmark_summary.csv), [stability](../outputs/benchmark/benchmark_stability.csv) |
| Are six nodes necessary? | 90 cells across 1/4/6-node arms; four-node median tokens -54.89%, median cost -47.03% against six-node | Supports examining decomposition, not a universal six-node benefit. [Protocol and analysis](prereg-2026-08-21-agent-topology-ablation.md) |
| Does the Reviewer add value? | Two 9-pair reviews; registered retention gate passed, but citation agreement 8/9 and decision agreement 3/9 | Small text-based review, no external-source checks; not source truth. [Result](results-2026-08-23-reviewer-value-audit.md) |
| Do users prefer the full workflow? | Five reviewers, 20 eligible judgments; each round decision preference 6:4; information gain favoured the monolith 11:5 | Registered success rule failed. Only one actual target user. [Result](results-2026-08-23-user-utility-audit.md) |
| Does the report help a target decision? | Two users, same frozen topic/report; both retained DEFER, confidence 3→4/5; median usefulness/information gain 3/5 and actionability/trust/acceptance 2/5; both MAYBE on reuse | Estimated revision effort is not observed time saved. No external-source checks, cross-topic validation or adoption. Closed two-slot pilot. [Result](results-2026-08-26-target-user-decision-pilot.md) |
| Can a killed process resume committed nodes? | 30/30 offline child runs completed; 90 task executions skipped, zero duplicate committed-task executions | Zero-network fault injection, not provider exactly-once. [Result](results-2026-08-23-checkpoint-fault-recovery.md) |
| Has real recovery been observed? | One production child reused four nodes, made no new evidence-agent requests and completed its suffix | Interrupted-source usage unavailable; total spend and savings cannot be computed. [Result](results-2026-08-24-paid-same-revision-recovery-post-fix.md) |
| Does the Qwen transport work? | One completed canary: 7 requests, 79,261 tokens, conservative USD 0.075657, 306 seconds; all roles qwen3.5-plus | One live delivery/accounting path, not cross-topic quality or DeepSeek equivalence. Narrow internal-x10 prose defect was fixed separately. [Result](results-2026-08-30-qwen35-plus-first-paid-canary.md) |
| Does Decision Context constrain prose? | Three-mode canary completed three roots, primary result 7/10 (fail) | Later deterministic applicability and advisory checks do not retrospectively turn this into a pass. [Original result](results-2026-08-26-decision-context-paid-canary.md), [report seams](results-2026-09-03-report-decision-and-citation-seams.md) |
| Does terminal truth reach the actual browser? | RTI02 normal completion passed 12/12 primary checks: 6 requests, 69,932 tokens, USD 0.067922 estimate, 885 seconds | Minor read-only polling-cadence deviation disclosed; no timeout/fallback/cancellation/recovery lane or general quality claim. [Result](results-2026-09-04-runtime-terminal-integrity-post-browser-seam-paid-canary.md) |
| Did the threshold screen become more precise on stored reports? | 110-report replay: seven known false positives removed, six qualifying RTI02 candidates retained | Development replay; zero baseline candidates does not establish precision. [Result](results-2026-09-04-decision-threshold-warning-precision.md) |
| Does handheld-ultrasound applicability preserve unrelated domains? | 1/110 profile changes for the exact observed phrase; other 109 unchanged | Narrow lexical fix, not general device classification or better source truth. [Result](results-2026-09-04-handheld-ultrasound-authority-applicability.md) |

Do not combine these denominators. Offline tests, mechanical proxies, blinded
preferences, provider requests and target-user decisions answer different
questions. Cost estimates are not invoice reconciliation, and complete local
accounting does not make incomplete source-run spending inspectable.

## Tool Calling experiments

This is the completed research history, **not completed production Tool Calling**.
Compatibility, source relevance, role coverage, novelty, planner triggering and
report value have independent gates. A provider request succeeding is not a
value pass.

| Version / stage | Frozen observation | Decision and evidence |
|---|---|---|
| Execution kernel, phase 2 | 14/14 synthetic dispositions and deterministic replays; six valid delta rows, no unexpected rows | Contract proof only. [Result](results-2026-08-25-evidence-gap-tool-execution-phase2.md) |
| Generic Tavily, phase 3 | 5 requests, 25 candidates, conservative USD 0.040; returned labels describe 5 relevant / 20 irrelevant | Substantive AI use excluded the review; legacy packet hid the novelty baseline. Not a human-value pass; even descriptive labels would fail the 5% wrong-source ceiling. [Result](results-2026-08-26-evidence-gap-human-review-phase3.md) |
| Credentialed domain adapters, phase 4 | OpenAlex/Lens offline contracts and source-locked runner/review implemented | No credentialed live phase-4 execution; no production eligibility. [Result](results-2026-08-26-evidence-gap-domain-live-phase4-implementation.md) |
| Anonymous OpenAlex / v1, D | 4 requests, USD 0.004 reported anonymous usage; 9 retained candidates, 4 irrelevant (44.4%); coverage 4/4 | Eligible superseding human review failed after a disclosed declaration correction. [Result](results-2026-08-27-evidence-gap-anonymous-openalex-review.md) |
| Conjunctive precision v2, U | 8 requests, USD 0.008; five accepted candidates in 3/8 cases, below 6/8 coverage | Mechanical failure before human review; source value not evaluated. Development success did not generalize. [Result](results-2026-08-27-openalex-precision-v2-unseen-live.md) |
| Provider-assisted claim-scope v3, V | 8 requests, USD 0.008; 13 candidates across 7/8 cases; one irrelevant, 7.69% wrong-source rate | Human review failed the frozen 5% maximum. [Result](results-2026-08-27-openalex-claim-scope-v3-review.md) |
| Same-segment Scope-Link v4, W | 8 requests, USD 0.008; all 64 candidates ABSTAIN, 0/8 coverage | Mechanical fail. Post-outcome human diagnostic found 28 relevant / 36 noise and missed semantic links; this cannot rescue v4. [Live result](results-2026-08-29-openalex-scope-link-v4-live.md), [diagnostic](results-2026-08-29-openalex-scope-link-v4-abstention-diagnostic-review.md) |
| Two-pass evidence-set v5, consumed W development | DeepSeek identity and earlier Qwen timeout runs remained incomplete; separately authorized Qwen schema-4 completed 16 calls for USD 0.113971, 38/64 disposition agreement (59.375%), zero KEEP | Execution completed but mechanical development gate failed. X unseen cohort not opened. [Complete-run result](results-2026-08-31-openalex-evidence-set-v5-qwen-schema4-development.md), [diagnostic](results-2026-08-31-openalex-evidence-set-v5-qwen-failure-diagnostic.md) |
| Three-pass role-slot consensus v6, Y | 8 OpenAlex requests and 21/24 Qwen calls before soft stop; USD 0.008 + USD 0.204363 known spend; gates already mathematically unreachable | Failed/partial execution, not a 24-call completion. Diagnostic: 13/64 relevant, only 3/8 human-coverable cases. Z unopened. [Live result](results-2026-09-01-openalex-role-slot-consensus-v6-development-live.md), [diagnostic](results-2026-09-01-openalex-role-slot-v6-failure-diagnostic-review.md) |
| Retrieval-first role-directed v7, AA | 16 requests, USD 0.016; 79 unique rows, 37 relevant/novel; relevant evidence 8/8, union coverability 5/8, gain 0 | Human review failed coverage and incremental coverage gates. AB unopened. [Result](results-2026-09-02-openalex-role-directed-v7-human-review.md) |
| Adaptive Role-Gap v8, AC development | 15 requests, USD 0.015; 64 unique rows, 31 relevant; all six development gates passed | Development qualification only. [Result](results-2026-09-03-openalex-adaptive-role-gap-v8-human-review.md) |
| Adaptive Role-Gap v8, AD unseen | 15 requests, USD 0.015; 67 unique rows, 33 relevant; routing 5/8, closure-role value 2/7, coverable gain +1 | Three of six gates failed. AD consumed, v8 sealed, no production connection. [Final result](results-2026-09-03-openalex-adaptive-role-gap-v8-ad-human-review.md) |

Anonymous OpenAlex amounts above are provider-reported budget usage, not a
claim that an invoice was charged. Review source-check coverage and corrected
declarations differ between studies; consult each linked methodology. Most
labels are title/abstract judgments, not full-text ground truth.

The AD failure showed that the second request often targeted a role already
covered by the anchor, and it added a complete role set in only one new case.
A subsequent method must change that hypothesis on fresh development evidence
before a separately frozen unseen evaluation. None of this authorizes a new
paid run, a new reviewer packet, reserved-cohort access or production insertion.

## Negative findings that remain binding

[AGENTS.md](../AGENTS.md#do-not-redo-these) retains the six measured exclusions:
scoring formula/floor edits, maturity-language checks, blocking uncited claims,
prompt caching, extra academic abstract scraping and main-branch CrewAI upgrades.

The separate patent candidate improved selective precision to 94.6% but
dropped six truly relevant patents, so it was rejected. The
[patent candidate protocol and outcome](prereg-2026-08-22-patent-relevance-candidate-screen-v1.md)
does not establish recall, FTO coverage or inter-rater agreement.

The release, historical result documents and exact fixture/dependency hashes
remain unchanged. Browse the [full experiment index](experiment-index.md).

## Highest-value next work

1. The core metadata read fault path is now hardened through both HTTP endpoints,
   history and Chromium; see the [measured scope and limits](results-2026-09-05-runtime-metadata-integrity.md).
   Nine reliability-summary fields now have field-local read isolation and
   explicit unreadable rows; see the [nested fault verification](results-2026-09-05-nested-audit-metadata-integrity.md).
   Selected usage/accounting/checkpoint/recovery summaries now also have
   [read isolation and browser fault tests](results-2026-09-05-runtime-summary-read-integrity.md).
   The report-audit detail renderer now also validates its displayed shapes
   and counters locally. Other detailed artifacts and nested payloads remain
   outside these contracts; reproduce their client failure before proposing changes.
2. New decision-utility research should target the already observed low trust
   and actionability, use a new protocol and disclose external-source checks.
   Do not append new reviewers to completed panels or claim estimated
   correction effort as measured time savings.
3. If supplementary Tool Calling is reopened, start a genuinely new retrieval/
   routing hypothesis. Do not tune AD or simply add more model calls to a
   candidate pool that lacks role-complete evidence.

These are proposals, not authorization. Distributed infrastructure, more agents
and code-package ingestion remain lower priority unless a concrete use case
changes the tradeoff.
