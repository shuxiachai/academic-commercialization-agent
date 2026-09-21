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

The Sources panel separately supports local exact-ID/literal-keyword lookup
and expansion of saved text through the existing artifact read. It does not
run an LLM, supplement evidence or judge claim support. Text can have been
cleaned, truncated or supplied as a fallback description during collection;
missing/malformed/over-budget fields are not a negative evidence finding.
See the [viewer scope and limits](operating-guide.md#web-cli-and-http-api).

Planning/translation now shares complete provider configuration with the main
factory; fixed BYOK destinations and narrow credential/content-safe diagnostics
are offline-tested. Historical node usage totals still exclude auxiliary calls.
See the [verified repair and limits](results-2026-09-10-provider-and-log-boundaries.md).

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

Test maintenance consolidates weak/repeated feature scenarios and checks actual
launch/workflow commands. The canonical matrix cell now measures coverage in
its single full-suite execution; the existing coverage check is an explicit
matrix-result gate rather than a fifth test run. All four environments, the
85% floor, browser/container checks and frozen experiments remain. See the
[maintenance evidence and limits](results-2026-09-17-test-maintenance.md).

The PDF failure-receipt test observer no longer consumes the executor slot
needed by its worker. A single-slot control reproduced ten entry failures;
event-loop notification preserves all twenty default/single-slot failure and
cancellation cases without relaxing timeouts. Both observer and missing-receipt
mutations were caught. Production is unchanged, and the earlier CI incident's
exact timing cause remains unproven. See the
[test isolation result and limits](results-2026-09-13-pdf-receipt-observer-isolation.md).

Complete numeric tokens now prevent scientific/sign/compound suffixes from
earning false support. Ninety-artifact replay moves nine range-bearing findings
to unverifiable (32 -> 23 checked), not improved independent accuracy. New
validated scores record actual pre/post cap arithmetic through checkpoints,
HTTP and the browser; legacy missing records cannot be reconstructed. Scoring
and source-comparability policy stay unchanged. See the
[repair, controls and tradeoff](results-2026-09-12-numeric-token-and-cap-provenance.md).

Market scores now disclose that same-definition estimates are **not assessed**,
including historical artifacts viewed in the current browser. Fresh/restored
score JSON reasserts this limitation instead of trusting generated verification.
Thirty local score replays preserve all previous fields and 183 historical
JSON/CSV hashes. The 3.5 cap and scoring formula remain unchanged; this fixes
missing disclosure, not the known untyped comparison policy. See the
[delivery contract and regression](results-2026-09-11-market-score-delivery-disclosure.md).

Agent-only inspection now covers all 20 saved market candidates over two dates.
The first six retain their [original observations](results-2026-09-11-market-source-spot-check.md);
the [remaining 14](results-2026-09-12-market-source-followup.md) add seven pairs:
three explicit scope/time/year mismatches and four insufficient-information
outcomes. Across ten pairs, five are explicitly incompatible and five lack
sufficient information; no fully comparable real pair is established. One
same-page market-size/funding negative is separate, not another pair. Missing
pricing and revenue boundaries remain unknown; original drafts stay unreviewed.
This is not independent human review, market accuracy or a scoring-policy change.

A local merged-tree upload test failed before any parser file opened, despite
green CI. Deadline injection now follows actual file creation and separately
asserts wait selection, cancellation, cleanup and capacity recovery. Production
limits are unchanged. See the [ordering failure and regression](results-2026-09-11-upload-deadline-parser-order.md).

Market-estimate preparation now separates 16 synthetic comparison controls
from 20 unreviewed local source-summary candidates. Literal anchors and hashes
are checked; unknown dimensions stay null, and no real comparisons or expert
accuracy are claimed. Scoring is unchanged. See the
[sample contract and remaining evidence gate](results-2026-09-11-market-estimate-sample-contract.md).

An existing upload test leaked its injected 20ms timeout into a normal capacity
probe and failed one main Windows CI job. Scoped fault injection retains exact
408/401 assertions and now uses one slot to expose leakage. Runtime limits are
unchanged. See the [CI failure and behavioral repair](results-2026-09-11-upload-timeout-test-isolation.md).

An offline market-metric audit reproduces the untyped >5 spread in 30/30
current local units, but their metadata is 29 live + 1 fixture, unlike the
archived all-live CSV. Strict typed comparison finds no fully attributable
pairs, so all 30 are `not_assessed`, not verified agreement. This does not
change market scores or establish penalty counts. See the
[qualified snapshot and next gate](results-2026-09-11-market-metric-comparability.md).

PDF candidate locators are now separate from A1 citation identity, including
legacy extraction conversion. Signed quantities and milli/mega symbols remain
distinct; unsupported unit notation abstains. The actual PDF thread publishes
known failure receipts after HTTP cancellation. Read-only 90-artifact replay
moves 18 previously checked findings to unverifiable; it is not an accuracy
gain. See the [repair and explicit limits](results-2026-09-11-pdf-numeric-receipt-seams.md).

Run/PDF/resume acceptance now supports opt-in durable idempotency and read-only
receipt lookup. Fresh-document Chromium recovery for all three first-party
operations uses intercepted POSTs, not paid-provider calls; unknown and corrupt
receipts do not dispatch again. This is not provider exactly-once or measured
cost savings. See the [receipt evidence and limits](results-2026-09-10-durable-paid-receipts.md).

Crew-node cost scope and invalid-rate/overflow states are explicit at HTTP and
browser delivery. New general benchmark batches bind execution identities and
preserve archived results; this fixes provenance, not model accuracy or complete
provider billing. See the [cost/batch contract](results-2026-09-10-cost-scope-and-benchmark-identity.md).

Decimal grounding, production score-citation admission, bounded PDF page
coverage/candidate identity and terminal-authoritative ops outcomes have new
offline behavioral regressions. The 30-score replay is unchanged, not new
calibration. Remaining audit gaps are explicit in the
[repair and scope record](results-2026-09-10-evidence-pdf-terminal-boundaries.md).

Upload ingress also bounds bytes/time/preprocessing slots before multipart
parsing; delayed history replies cannot repaint a newer view or login; actual
extraction threads finalize raw PDF cleanup even after waiter cancellation.
These are offline HTTP/Node/Chromium contracts, not incident-rate or cost-savings
claims. See the [boundary result and retention limits](results-2026-09-08-upload-history-cancellation-boundaries.md).

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

Optional step-log failures now stay separate from run completion and report
delivery. Physical-line cursors prevent replay after rejected events; detail
tabs reject fake zero/pass states, and denied browser storage degrades to
page-local identity with explicit persistence/logout limits. These are
offline HTTP/Chromium contracts, not production incident rates or semantic
report validation. See the [delivery seam audit](results-2026-09-08-client-delivery-seams.md).

The follow-up corrects integer-only score display against 109 stored score
files (64 contain fractions). Malformed BYOK no longer chooses operator billing;
pending acknowledgements retain their identity, and stale progress reads have a
separate visible state. These are bounded offline request/browser regressions,
not measured production charge errors or an uptime SLO. See the
[combined client-boundary audit](results-2026-09-08-client-boundary-combinations.md).

Open documents now retain their selected access-code identity across other
tabs' storage changes; late/candidate 401s cannot clear a newer choice, and a
conflicting logout returns to explicit credential selection. Seventeen new
offline tests and a five-POST intercepted two-tab journey establish the narrow
contract, not global logout, cross-tab deduplication or durable receipt recovery.
See the [identity maintenance record](results-2026-09-08-browser-access-identity.md).

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

New semantic evaluations follow the [LLM-only review policy](llm-review-policy.md).
No new human panel is required. Independent AI judgment remains distinct from
structural validation, historical human declarations and observed user adoption.
The [new offline claim-relation protocol](prereg-2026-09-16-followup-claim-relation.md)
uses caller-owned propositions and code-derived delivery for support, refutation,
insufficiency and unavailable reads. It does not alter frozen transports or
authorize a provider run or production connection.
The [offline implementation record](results-2026-09-16-followup-claim-relation.md)
keeps scripted contract evidence separate from model semantic quality.
The [separate native claim transport protocol](prereg-2026-09-16-claim-qwen-transport.md)
binds first-turn claim identity and complete native tool history. Its scope is
offline HTTP/accounting validation, not another paid batch or production hook.
The [intercepted-wire result](results-2026-09-16-claim-qwen-transport.md) records
88 new controls, four targeted defect reinjections and 60 local intercepted
requests; none is a real model response or evidence of semantic accuracy.

The separate [CLQ synthetic protocol](prereg-2026-09-16-claim-qwen-canary.md)
was executed once after exact-tree CI and independent implementation review.
Its [closed result](results-2026-09-16-claim-qwen-canary.md) records six requests,
USD 0.006361992 estimated known use, three per-case mechanical passes and
2/3 frozen-label matches: the batch failed. A fresh blind LLM judged all three
answers supported, including refutation of a claim that a flow was recorded
when the text explicitly says no measurement was made. This exposes a
reference/proposition mismatch, not permission to revise the consumed label.
The intended nonempty-insufficiency lane remains unproven live; unavailable
remains offline-only. No private-data grant or production admission follows.

The [PCQ successor preparation](results-2026-09-17-claim-proposition-contrast.md)
separates physical-value and record-content propositions using new synthetic
controls. A fresh blind LLM's three proposals match the prewritten references;
these are AI-reviewed development labels, not independent gold. Offline scripted
receipt checks are separate from semantics. No new Qwen request is included,
and the live insufficiency lane remains unproven.
The [separate PCQ native executor](results-2026-09-17-claim-proposition-contrast-qwen-runner.md)
now has 208 offline tests, three dispatch-count defect reinjections and distinct
mechanical/label/publication gates. Its fixed-output identity is not the closed
CLQ batch; no new paid observation or production admission follows.

The subsequent [single PCQ native observation](results-2026-09-17-claim-proposition-contrast-qwen-canary.md)
is closed and failed after two requests, estimated USD 0.002044425. PCQ01 read
the complete source and passed mechanics but declared refuted instead of the
frozen insufficient label (0/1 checked matches); PCQ02/03 were unrun. A label-blinded
LLM with inherited project context inferred insufficient and judged the answer mixed, distinguishing
missing measurement from physical contradiction. Runtime unverified flags and
the old failed batches are unchanged. This is not a general accuracy estimate;
the intended native insufficiency lane and production admission remain unproven.

The [explicit relation-policy successor](results-2026-09-17-claim-relation-policy.md)
is offline-only: seven text-bearing development references and one missing-text
control received label-blinded, context-limited LLM review. Its implementation
contract separates policy-to-callback delivery from frozen inner facts and
does not correct a model's semantic label or add a native/production path.

Its [separate native wire successor](results-2026-09-17-relation-policy-qwen-transport.md)
binds the frozen policy and trusted claim/snapshot through intercepted HTTP
and an independent ledger. Callback entry, reserved wire intent and observed
response remain separate. No new provider result or production admission.
The [CI follow-up](results-2026-09-17-relation-policy-ci-isolation.md) preserves
the subsequent verbose-reporting failure and test-only isolation correction;
local suite success must not be substituted for exact-head CI.

The [RPQ batch protocol](prereg-2026-09-18-relation-policy-qwen-canary.md)
froze RP01-RP03 for a separately identified synthetic native experiment.
Its three cases are dependent development controls, not fresh unseen evidence.
The [dedicated runner verification](results-2026-09-18-relation-policy-qwen-runner.md)
records intercepted HTTP and targeted stop/guard mutations, not native answers.
The [closed native result](results-2026-09-18-relation-policy-qwen-canary.md)
records one request and an early unavailable final with no tool call. The batch
failed before evidence delivery: zero label checks, semantic not_reviewable,
RP02/RP03 unrun. Estimated usage cost is USD 0.001229421; no retry or production
activation occurred. The occupied batch and frozen bytes must not be reused.

The separately [registered read-first candidate](prereg-2026-09-18-read-first-followup.md)
narrows the task to zero/one short saved source. It preserves the original RP
callback and audits a declared named-read transformation on the native request,
rather than repairing an early model final. RF01-RF03 are new dependent synthetic
development controls with context-limited LLM reference review, not unseen gold.
The native compatibility gate remains separate from offline engineering; this
candidate neither adds sources nor enables production follow-up.
The [offline engineering record](results-2026-09-18-read-first-followup-implementation.md)
retains two independent-review findings, their delivery/error-path repairs and
defect-reinjection evidence rather than treating a green test count as proof.
Its [single native result](results-2026-09-18-read-first-qwen-canary.md) is closed
and failed: two requests, one actual complete read, one mechanical pass, but
zero matches in one frozen-label check. RF02/RF03 are unrun. A later
context-limited LLM review judged the answer mixed; estimated known usage is
USD 0.002436429. No retry, follow-on batch or production activation follows.

A separate [saved-source locator](prereg-2026-09-18-saved-source-locator.md)
now narrows the next offline path to one selection callback, one actual local
read and code-owned saved-text JSON. It does not generate an answer, judge
support/refutation or reuse the old CQ native contract. Fresh local capacity
inspection found 632 of 632 saved texts fit the existing catalog/read bounds
across 30 snapshots; this is not model-selection accuracy or benchmark
revalidation. A post-implementation scripted replay through the actual selector,
reader and JSON renderer preserved all 632 saved texts, with 632 observed
callback entries and local reads; its maximum callback envelope was 4,867 ASCII
bytes. IDs were prescribed, not selected by an LLM, so this is delivery/capacity
evidence, not 100% selection accuracy. A separate
[single-selection Qwen transport](prereg-2026-09-18-source-locator-qwen-transport.md)
now prepares the native boundary using intercepted HTTP, not provider calls.
It binds question/catalog/schema identity, complete wire bytes and a dedicated
one-request durable ledger; it does not send the locally read text back to a
model. Before implementation, the same 30-snapshot fixed-question inspection
measured maximum complete native bodies of 4,990 bytes, below 12,288 bytes.
This is not arbitrary-question coverage or a live compatibility result. A new
[SLQ batch protocol](prereg-2026-09-19-source-locator-qwen-canary.md) freezes four
synthetic development controls and a dedicated executor. Default identity checks
have no credential/output side effects; native admission has aggregate four-
request/USD 0.05 bounds and first-failure stop. Reference labels received a
context-limited LLM blind review, not human expert validation. The separate
[single native SLQ observation](results-2026-09-19-source-locator-qwen-canary.md)
then completed four requests with 4/4 mechanical and 4/4 development-reference
checks, two nonempty saved-text deliveries, explicit decline and preserved
missing text. Known-use estimate was USD 0.001656723; conservative reservation
consumption was USD 0.044597248, not an invoice. Separate label-blinded LLM
inspection supported the narrow location/delivery observations. The batch is
closed; this is neither independent accuracy nor production admission.

A [public-bibliography comparison](prereg-2026-09-19-public-source-search-comparison.md)
now prepares six fresh questions over twenty historical public ID/title entries,
without reconstructing unavailable saved abstracts. It observes the shipped
Sources filter under a minimal DOM, separating whole-question diagnostics from
author-assisted keyword queries and set coverage from unique hits. The twelve
paired condition observations are not twelve independent samples. No model
comparison or production admission follows from this offline preparation.
The [observed keyword baseline](results-2026-09-19-public-source-search-baseline.md)
found acceptable titles for 5/5 positive cases (four unique, one valid pair),
and no titles for its one no-fit control. Author-supplied queries and whole-
question diagnostic misses cannot establish a model advantage or human savings;
the model lane remains `not_run` with null quality/benefit and no provider calls.

The separate [SLCQ native protocol](prereg-2026-09-19-public-source-locator-qwen-comparison.md)
prepares a comparison on the same six questions and public-title scope, with a
fresh fixed output, six-request/USD 0.10 ceiling and first-failure stop. It does
not rewrite SLC's historical model lane or send unavailable original summaries.
An acceptable selection with `missing_text` remains location, not evidence
delivery; refusal is not successful no-fit abstention. No native outcome is
established by this preparation.
The [baseline encoding erratum](erratum-2026-09-19-slc-baseline-encoding.md)
retains the earlier hash and its missing normalization qualifier while binding
the new runner to the directly reproducible, unmodified Python-output identity.
The baseline hit sets and references did not change.
The [separate native SLCQ result](results-2026-09-19-public-source-locator-qwen-comparison.md)
completed six requests and 6/6 mechanical/reference checks, with five acceptable
locations and one explicit decline. The assisted baseline also passed; native
selection reduced the valid patent pair to P5 without proving human savings.
Five reads returned missing text and delivered zero evidence. Reported-use
estimate was USD 0.004639290, reservation consumption USD 0.066895872; separate
blind LLM inspection supports only title location. The batch is closed and no
production route is enabled.

The separate [saved-source HTTP/browser entry](saved-source-entry.md) is an
unmounted callback integration shell, default-disabled, with bounded saved-data
loading and a dedicated scripted Chromium journey. It does not enable the
production endpoint, native provider dispatch, BYOK or paid receipts. Before
edits, prescribed-ID callbacks delivered 632/632 saved texts from 30 current
local snapshots exactly; that is neither model selection nor original benchmark
identity. Browser validation is a separate engineering boundary.

A separate [backend paid controller](saved-source-paid-controller.md) prepares
shared paid-operation admission and durable, code-owned locator receipts. Its
[isolated receipt entry](saved-source-receipt-entry.md) adds HTTP/browser recovery,
not a connection to the original lab, production API or a provider. The journal
binds saved identities without duplicating private excerpts; replay and unknown
acknowledgement are distinct from another selector call. This is billing-boundary
preparation, not a native result or production admission.

The separate [RQ protocol](prereg-2026-09-20-saved-source-receipt-qwen-canary.md)
prepares two fictional native receipt/browser controls under a fresh two-request
USD 0.05 ceiling. The old locator/transport and receipt wire remain unchanged;
first-failure stopping and separate native accounting protect the pilot. The
[closed native result](results-2026-09-20-saved-source-receipt-qwen-canary.md)
passed 2/2 mechanical/reference gates and actual lost-ack browser recovery,
without another selector request or daily charge on replay. Known-use estimate
was USD 0.000799403; HTTP accounting remains unobserved and separate. These
fictional development controls do not establish real-report value or production
capability.

The [usage delivery successor](saved-source-usage.md) keeps that historical wire
unchanged and adds opt-in operation-bound accounting to a separate envelope and
isolated page. It distinguishes reported use, estimates, reservations and absent
observations. Its implementation and intercepted tests are not new native results,
provider invoices, real-report utility or public activation.

Real saved-report follow-up now has a separate [offline preparation protocol](prereg-2026-09-16-report-evidence-real-saved-offline.md).
Its candidate is one historical live-report snapshot with all 20 saved sources
and two newly authored questions. Labels are kept outside model inputs and
reference review is distinct from mechanical rehearsal. No real-report model
call, privacy grant, production route or new general-accuracy result follows
from this preparation; CQ remains a closed synthetic-only observation.
The [offline rehearsal result](results-2026-09-16-report-evidence-real-saved-offline.md)
records four intercepted scripted HTTP requests, not four provider calls.

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

## Separate saved-evidence conversation prototype

The [report evidence follow-up](report-evidence-followup.md) implements two
read-only tools over one supplied snapshot, with a native-shaped assistant/tool
round trip through a scripted transport. The 127 new offline tests and synthetic
demo establish bounded dispatch and content-bound evidence delivery, not actual
model behavior. A separate pinned Qwen transport and single-owner canary ledger
are governed by a [two-control, six-request protocol](prereg-2026-09-14-report-evidence-followup-qwen.md).
The synthetic allowance is not production authorization; no paid endpoint or
production hook exists.
Semantic support remains `not_assessed`; reader benefit versus direct source
browsing is unmeasured. This is not v9 and does not change the failed v8 gates.
See the [protocol and validation result](results-2026-09-14-report-evidence-followup-phase1.md).

The [first real Qwen canary](results-2026-09-15-report-evidence-followup-qwen-canary.md)
received three valid native responses with complete reported usage, but failed
closure after two lookups exhausted the tool budget. No read/final answer was
delivered; the second synthetic case was not run. Conservative known-usage
estimate: USD 0.001813194, not an invoice. No retry or production activation.

The separate [offline stage policy](report-evidence-followup.md#separate-offline-stage-policy)
restricts both advertised actions and local dispatch, retaining the original
two-tool/three-turn ceilings and frozen modules. It distinguishes entering the
legacy callback from actually forwarding evidence to the injected transport.
This is control-boundary work, not a fresh model observation or a reversal of
FQ01/v8 failures. Its [offline protocol](prereg-2026-09-15-report-evidence-stage-policy.md)
does not grant new paid requests or a production route.
The [offline result](results-2026-09-15-report-evidence-stage-policy.md) records
43 new tests, the repeated-lookup defect reinjection and the remaining live
adapter/semantic limits; scripted closure is not a new Qwen success rate.

The separate [stage-aware Qwen transport](report-evidence-followup.md#stage-aware-qwen-transport)
preserves explicit final-only wire semantics and uses a distinct journal
identity. Its [offline protocol](prereg-2026-09-15-report-evidence-stage-qwen-transport.md)
covers intercepted HTTP and failure accounting, not a new live runner, paid
allowance or general semantic validation. Both earlier failures remain binding.
The [transport result](results-2026-09-15-report-evidence-stage-qwen-transport.md)
retains the Windows test-isolation failure and distinguishes code deployment
from successful live closure or production follow-up.

A [separately preregistered stage-aware canary](prereg-2026-09-15-report-evidence-stage-qwen-canary.md)
has independent commit/fixture identity and default-off execution. Its
[preparation result](results-2026-09-15-stage-qwen-canary-preparation.md) retains
81 new offline tests and the first-failure dispatch counterexample.
The [subsequent live batch](results-2026-09-15-stage-qwen-canary-live.md) made
three requests: lookup and saved-text read reached final-only HTTP, but SQ01
failed because prose plus fenced JSON violated the strict final envelope.
SQ02 was not run. Reported usage was 2529 input / 401 output tokens;
USD 0.002828557 is a frozen conservative estimate, not an invoice. No retry,
accepted final answer, general semantic verification or production activation
is claimed; the original failed batch and sealed retrieval results stay intact.

The [separate final-only JSON candidate](report-evidence-followup.md#separate-final-only-json-candidate)
has a [new JQ synthetic protocol](prereg-2026-09-16-report-evidence-final-json-qwen.md).
It requests JSON Object output only after tools are disabled, keeping strict
local parsing and the old failed batches intact. Its [single live JQ batch](results-2026-09-16-report-evidence-final-json-qwen.md)
made two requests: the multi-concept contiguous lookup missed an existing source,
then strict JSON abstention passed formatting but failed the positive read gate.
JQ02 was unrun. Estimated usage cost USD 0.000937594 is not an invoice.
This is neither native read closure, semantic correctness nor production authorization.

A separate [bounded metadata catalog](report-evidence-followup.md#bounded-metadata-catalog-candidate)
addresses discovery offline, preserving the closed JQ result. The candidate gives
unranked titles/IDs, restricts the first action to one visible-ID read, and keeps
actual read receipts separate from metadata. It is not a silent replacement for
literal lookup, a live adapter or evidence of source selection accuracy.
The [new protocol](prereg-2026-09-16-report-evidence-catalog.md) preserves old
frozen bytes and forbids additional paid requests in this phase.
The [local capacity result](results-2026-09-16-report-evidence-catalog.md) covers
30 snapshots / 632 source rows without omitted metadata; it does not establish
which source answers a question or revalidate the original benchmark identity.

A separate [catalog-native transport contract](report-evidence-followup.md#catalog-native-qwen-wire-contract)
now carries the 32-ID declaration and final-only JSON through an independently
identified, snapshot-bound adapter. Its [offline protocol](prereg-2026-09-16-report-evidence-catalog-qwen-transport.md)
keeps the full HTTP byte cap, actual request/journal identity and unknown-usage
stop rule. Intercepted HTTP is not a live Qwen result; no production follow-up
route is added. Callback forwarding is not HTTP delivery.
The [offline result](results-2026-09-16-report-evidence-catalog-qwen-transport.md)
keeps pre-change capacity, actual intercepted transport, failure controls and
review findings in separate denominators; none establishes model selection quality.

The separate [CQ protocol](prereg-2026-09-16-report-evidence-catalog-qwen-canary.md)
freezes two new synthetic cases and an independently bounded runner: at most four
sequential requests, USD 0.10, first failure stops. A sixth-ID read and its actual
paired HTTP delivery precede strict final JSON; the missing-text case must read
before abstaining. The adapter's offline manifest is not live authorization.
The [one CQ batch](results-2026-09-16-report-evidence-catalog-qwen-canary.md)
passed both controls with four requests and complete reported usage; estimated
cost USD 0.002839152 is not an invoice. This demonstrates native read-to-final
closure on these easy invented cases, not general source selection, semantic
correctness or user benefit. It is closed and production remains disabled;
old failed batches and production gates retain their original meaning.

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

First-party paid intent now survives document refresh as a credential-free
session warning, with explicit risk acknowledgement before a new submission.
Three real Chromium reload cases and fault-injected Node delivery/settlement
contracts establish a bounded client guard, not recovered receipts or measured
billing savings. See the [verification and limits](results-2026-09-08-paid-refresh-warning.md).

1. The core metadata read fault path is now hardened through both HTTP endpoints,
   history and Chromium; see the [measured scope and limits](results-2026-09-05-runtime-metadata-integrity.md).
   Nine reliability-summary fields now have field-local read isolation and
   explicit unreadable rows; see the [nested fault verification](results-2026-09-05-nested-audit-metadata-integrity.md).
   Selected usage/accounting/checkpoint/recovery summaries now also have
   [read isolation and browser fault tests](results-2026-09-05-runtime-summary-read-integrity.md).
   Report-audit, score, grounding and consistency detail renderers now validate
   their displayed shapes/counters locally; optional step logs have separate
   availability and cursor contracts. Other artifacts and nested payloads remain
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
