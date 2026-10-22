# Experiment archive index

[Back to the documentation map](README.md) · [Current evidence status](evidence-status.md)

This is a historical archive, not a setup checklist or a list of enabled features.
Entries below retain their original dates, results and limitations. Start with
the current evidence status for today's qualified conclusions; open a dated
protocol or result when tracing a specific decision. An archive link does not
authorize rerunning a paid batch, moving its files or treating a failed gate as passed.

- [2026-10-22 patent family v1: both bars hold](results-2026-10-22-patent-family-v1.md): on 46 test registries (345 rows), 33 rows were another publication of an invention already listed, and the current check rejected none. The frozen rule rejected 29 rows: precision 0.93 (27/29), recall 0.82 (27/33). Its two wrong rejections are one pair, in two runs, with the same inventor, priority and filing date, which Google Patents puts in different DOCDB families. Six duplicates were missed: retitled, translated or uncleaned titles. Production adopts the rule for the web-search patent path; no TRL effect claimed.

- [2026-10-22 patent family v1 protocol](prereg-2026-10-22-patent-family-v1.md): the collector's duplicate-patent check compares whole titles, and Google Patents titles carry the publication number, so one invention filed in several offices took several slots (five of eight in one run). `patent_family.py` merges rows that are the same publication, or whose titles match without numbers and whose numbers come from different offices or are an application and a grant. Development, against Google Patents DOCDB families: the current check rejected 0 of 18 family duplicates; the frozen rule rejected 11, all correct. A titles-only rule made 3 wrong merges. Test: 46 registries from five other batches. Adopt only if precision ≥ 0.90 and recall ≥ 0.40. No TRL effect claimed.

- [2026-10-22 market page dates v1: all three bars hold](results-2026-10-22-market-page-dates-v1.md): on 109 admitted test URLs, 85 were dated (coverage 0.78). The date was found within a day on 75 rendered pages (precision 0.88), and two pages print a different date of their own (0.024). Four more print the same date in a form the search misses. Two labels were added and the labels were corrected once before the write-up; the labeller was not blind. Of the 85 dated sources, 38 were over a year old on their run's day. Production adopts the change for market sources; no TRL effect claimed.

- [2026-10-22 market page dates v1 protocol](prereg-2026-10-22-market-page-dates-v1.md): none of 229 held-out v2 market sources had a date. `page_dates.py` reads a page's own publication metadata (JSON-LD, meta, itemprop, a full URL date) for sources other than market reports, Wikipedia and home pages. Development: 41/63 admitted pages dated, 37 of them confirmed within a day on the rendered page, one contradicted. Test: 109 admitted URLs from five other batches. Adopt only if precision ≥ 0.80, contradictions ≤ 0.05 and coverage ≥ 0.50. No TRL effect claimed.

- [2026-10-22 erratum: the source-search comparison's observer becomes a snapshot](errata-2026-10-22-source-locator-observer-snapshot.md): the 2026-09-19 comparison observed the live `result.js`, `i18n.js` and source-browser contract, so keeping it reproducible froze the product's result page. The observer is now a byte-identical copy under `evals/source_locator_observer_v1/`; the fixture and every pinned hash are unchanged, and the snapshot reproduces the registered baseline digest. No result changes.

- [2026-10-22 erratum: OpenAlex refused two batches' requests, unrecorded](errata-2026-10-22-openalex-budget-outages.md): local batches ran without an OpenAlex key, and the anonymous daily budget ran out. The last five held-out v2 runs and both hyperloop confirmation runs were scored with every OpenAlex lane empty; refusals were not recorded before #252. Held-out v2 still counts 25/30, but two of its three below-floor misses are degraded runs (22/25 in range without them). The hyperloop confirmation shows the fix reached the minimum without OpenAlex, not what production delivers. `benchmark.py` now stops on an OpenAlex refusal and needs a key for live batches.

- [2026-10-22 two-word title gate v1: no rule advanced](results-2026-10-22-two-word-gate-v1-dev.md): development only. On 240 live candidate titles that R5 accepts although the two input words are not adjacent, no adjacency rule removed off-topic papers at the 2:1 ratio set as the bar (best: 67 off-topic to 48 relevant). The rules help only where the first word has several senses (fusion power 29:9, wave energy 23:0) and remove relevant work elsewhere (tidal power 2:11). No pre-registration; test labels are committed unread; production unchanged.

- [2026-10-21 hyperloop confirmation](results-2026-10-21-hyperloop-confirmation.md): two live runs of V07 after #248 on `qwen3.8-27b`. Both completed with seven on-topic academic sources and none off-topic. TRL was 6 and 5, both in the 4–6 range; before the fix all four live-check runs stopped at the academic minimum. The batch was interrupted once by a working-tree switch and resumed under an unchanged identity. Two runs on a development topic; not a calibration measure.

- [2026-10-21 planner keeps the user's term](results-2026-10-21-planner-keeps-user-term.md): a development check of the corrections that followed the live check. The planner prompt now keeps the input's own technology name, and an academic shortfall is topped up with the earlier gate, last and only up to the minimum. With `qwen3.8-27b` plans, all 20 consumed topics delivered 8 academic sources under R5, against 18/20 before. Hyperloop went from 0 to 8 and vertical farming from 1 to 8. A request that keeps "commercial potential" in its plan still delivered 0 under both gates. Spot checks found hyperloop 7/8 relevant and fusion power 6/8. No crew run and no TRL effect.

- [2026-10-21 academic title gate live check v1 result](results-2026-10-21-academic-gate-live-v1.md): Part A, with live retrieval on the v2 plans: the new gate delivered 13 off-topic papers against 20 (registered threshold 15), left no topic short, and delivered 146 relevant papers against 140. Part B: **4/8 in range**. Space-based solar power scored in range 4/4, but on thin academic evidence (47% off-topic, prediction ≤ 20%). All four hyperloop runs stopped at the academic minimum. Diagnosis after the batch: the `qwen3.8-27b` planner rewrote "hyperloop" as "low-pressure tube transportation", so the user's term was never searched (the old gate also kept only 1 paper). On vertical farming the plan drifted, the new gate kept 1 paper and the old gate 8. The registered B1 reading ("misses persist") is recorded, but its premise does not hold, and corrections follow separately.

- [2026-10-21 academic title gate live check v1 protocol](prereg-2026-10-21-academic-gate-live-v1.md): two parts. Part A runs live academic retrieval on the 20 consumed topics, with both gates filling capped slots from the same cached responses; it makes no model or web-search request. Cleaner delivered evidence means the new gate delivers at most 0.75× the old gate's off-topic papers; a shortage flag is raised if two or more extra topics fall below three sources. Part B is eight live runs of hyperloop and space-based solar power under the production configuration (`qwen3.8-27b`, free quota). The reading: ≥ 7/8 in range means the v2 below-floor misses do not recur; ≤ 4/8 means they persist. The gate and model changed together, so Part B cannot attribute the cause. Prepared; dispatch waits for the maintainer's review.

- [2026-10-20 academic title gate v1 erratum: maintainer check delegated; deployed with two declared changes](errata-2026-10-20-academic-title-gate-v1-deployment.md): the maintainer delegated the registered blind check and adopted the AI's judgments, so no independent human check exists. The deciding judgment is that three general UAV surveys are off-topic; reversed, the comparison would be partial. Production gates the academic lanes with a port of R5 that reproduces all 494 replayed decisions. Two changes are declared on top: the user's words anchor the gate only when they name a topic (requests fall back to the planned phrase, and no replayed decision changes), and a plural-only stemmer changes five test decisions, four of them relevant titles. Patents are unchanged, and no TRL effect is claimed.

- [2026-10-20 academic title gate v1 result](results-2026-10-20-academic-title-gate-v1.md): **supported** on the test split (the v1 topics, evaluated once). R5 reached 88.9% precision against production's 83.5%, with recall 78.0% for both, and off-topic acceptances fell from 19 to 12. The rules disagree on only 11 of 237 rows, 9 of them in R5's favour. Five labels written from titles cut at 120 characters are recorded as errata, and the reading holds with them. An exploratory plural-stemming fix, found by reading test errors, would recover four more relevant titles but is not validated. Production stays unchanged until the maintainer's blind check of 21 rows. No TRL effect is claimed.

- [2026-10-20 academic title gate v1 protocol](prereg-2026-10-20-academic-title-gate-v1.md): offline replay of 494 saved academic title-gate decisions from the 70 held-out runs; no model or search request. The production gate admitted arXiv papers that share only generic words with the planner's expanded topic, and rejected relevant titles with one distinctive word, such as `Hyperloop System Optimization`. Rule R5 anchors the gate on the user's own words. It was frozen after five variants on the v2 topics: development precision 83.0% → 91.3%, recall 78.6% → 84.8%. The v1 topics are the test split, where support needs +3.0 points of precision and at most 3.0 points of recall lost. Labels are by an AI assistant, with a blind maintainer check of the rows the two rules decide differently. No TRL effect is claimed.

- [2026-10-19 held-out TRL calibration v2 result](results-2026-10-19-heldout-trl-v2.md): **25/30 in range** (supported; registered expectation 15–21), 28/30 completed. One run failed on a reviewer field bound, one on a provider `Arrearage` stop, after which the batch resumed under the unchanged identity. 11 runs scored 8–9, so v1's compression did not recur. Low-maturity topics were not inflated (0/9 above ceiling), but all three TRL misses fell below floor (hyperloop, space-based solar power). Retrieval predictions were met: deployment query 30/30, anchor-entity coverage on 8/10 topics. Topics and model also changed, so the improvement is not attributed to retrieval alone.

- [2026-10-19 held-out TRL calibration v2 protocol](prereg-2026-10-19-heldout-trl-v2.md): ten new topics, five of them with ranges reaching 8–9 and three with ceilings of 5–6, tested under the retrieval changes of #213 and #215 with `qwen3.8-max`. Ranges and case-sensitive anchor entities are frozen in `evals/heldout_trl_v2/cohort.json`, and v1's thresholds apply. The registered readings: zero runs at 8 or above means compression persists despite retrieval; four or more of nine low-topic runs above ceiling means inflation. Prepared; dispatch waits for the maintainer's cohort review.

- [2026-10-19 market allowlist: Wikipedia and sector sources admitted](results-2026-10-19-market-allowlist-sector-sources.md): maintainer-approved policy change. Wikipedia is admitted at low credibility, one entry per collection, and eleven sector bodies, analysts and trade titles are added. On the same cached results, four topics each gained one source, none off-topic: Hywind for floating wind, named DAC firms, the fusion industry report, and a weak DNA storage member list. The sector additions help only the development sectors.

- [2026-10-19 market retrieval development probe](results-2026-10-19-market-retrieval-development-probe.md): development measurement on the consumed v1 topics (market domain only, saved plans, 77 Tavily searches); the label is a market source naming an operator from the topic's anchor. After #213, production queries gave 30 such sources over ten topics against a mean of 20.7 in the v1 runs. Zipline went from absent in all three v1 runs to 3 of 8 sources, and psilocybin from 1 to 6. Operator wording and news search did not beat production on either pilot topic, so they were not adopted. The remaining losses are the allowlist (Wikipedia deliberately blocked; sector sources unapproved) and the per-query limit. Not held-out; no TRL.

- [2026-10-19 market retrieval: the topic's own queries never ran](results-2026-10-19-market-query-slot-sharing.md): on the 30 held-out runs, component queries supplied 166 of 219 market sources and the market-size query 37, while the topic's own deployment and revenue queries ran 0 times. 40 of 75 news-classed sources were syndicated market-size releases, which suppressed the company-news guard in 6 runs. Component queries now admit one source each and other market queries three. The deployment queries run first, and market-estimate titles are classed as market reports. A two-topic retrieval probe confirmed the mechanics, but operator evidence such as Zipline is still missing. No TRL effect is shown; that needs a new cohort.

- [2026-10-18 TRL compression diagnosis](results-2026-10-18-trl-compression-diagnosis.md): diagnosis (not validation) of the held-out runs. 15 of 20 TRL-7 rationales quote the TRL-7 label. Scale, cost or adoption reasons withhold 8–9 despite the rubric forbidding it. 53% of market sources are market-size pages, which the rubric discounts (17/17 for drone delivery, where Zipline was never retrieved). Construction and plans are counted as demonstration (fusion power). Fix directions are listed for a separate protocol.

- [2026-10-18 held-out TRL calibration v1 result](results-2026-10-18-heldout-trl-v1.md): 21/30 runs in range on ten held-out topics (`qwen3.7-plus`, batch `heldout-trl-v1-c`), exactly the registered "supported" threshold. But scores compressed toward 7 (only 4, 6 and 7 occurred; no run above 7), with a registered directional bias toward under-scoring: mature technologies were scored below their anchors and fusion power above. A constant-7 scorer would reach 15/30 (exploratory). Chinese reports were structurally complete; the structure checker matches English headings only.

- [2026-10-18 held-out TRL v1 amendment: measure `qwen3.7-plus` in batch c](protocol-2026-10-18-heldout-trl-v1-amendment-qwen37.md): batch `heldout-trl-v1-b` (`qwen3.5-plus`) stopped on a provider `Arrearage` account error after five successes, one false-positive monitor kill and one account failure; no outcome was inspected. The maintainer chose `qwen3.7-plus`, so all 30 runs repeat in `heldout-trl-v1-c` with an upper-bound price basis. Results will describe `qwen3.7-plus`, not production's model. Cohort, ranges and thresholds are unchanged.

- [2026-10-18 held-out TRL v1 erratum: first batch stopped on a runner defect](errata-2026-10-18-heldout-trl-v1-harness.md): batch `heldout-trl-v1` halted by its stop rule after three kickoff failures (`benchmark.py` omitted the Decision Context template inputs, a defect present since that feature landed); no TRL was produced or inspected. The runner was fixed with an offline template-coverage test, and the measurement repeats as batch `heldout-trl-v1-b` under the unchanged protocol.

- [2026-10-18 held-out TRL calibration v1 protocol](prereg-2026-10-18-heldout-trl-v1.md): ten topics never run before, with expected ranges anchored from external evidence and frozen in `evals/heldout_trl_v1/cohort.json` before any run; registered thresholds (≥21/30 supported, ≤15/30 not supported); includes one short and two Chinese inputs. Prepared, not yet authorized or run.

- [2026-10-11 Reviewer follow-up closeout](results-2026-10-11-reviewer-follow-up-closeout.md): the separate reason-schema invocation stopped at RSP01 with `observation_unavailable`; RSP02/RSP03 are `not_run`, POST count and usage are unknown, and the consumed invocation cannot be replayed. A later offline parser diagnostic found only R5 on one local snapshot, with no provider call and no conclusion about provider authentication or the historical failure.

- [2026-10-10 Reviewer comparison v3 closeout](results-2026-10-10-reviewer-comparison-v3.md): all eight ordinary checks and four preparation cells passed before one response violated the transmitted 300-code-point reason bound; zero reports were delivered, semantic comparison is `not_run`, and the consumed batch is closed without repair or retry.

- [2026-10-10 offline Reviewer output-constraint review](reviewer-output-constraint-feasibility.md): separates the local schema and intercepted-byte coverage from unestablished provider model/region/keyword enforcement; no new native test, successor allowance or production change.

- [2026-10-10 Reviewer reason-schema probe proposal](prereg-2026-10-10-reviewer-reason-schema-probe.md): design only, with three fixed synthetic controls and an unchanged 300-code-point bound; endpoint, numeric budget, implementation and execution authorization remain pending, with zero native calls.

- [2026-10-01 Reviewer comparison v2 closeout](results-2026-10-01-reviewer-comparison-v2.md): one response-backed request stopped on reason lengths exceeding an untransmitted field bound; no final reports or semantic comparison, no retry or production activation.

- [2026-10-01 offline common Reviewer output contract](../evals/reviewer_output_contract_v1/README.md): explicit complete-schema addition and local intercepted-byte checks for newly prepared requests; no provider, new native batch or production integration.

- [2026-09-30 Reviewer comparison v2 protocol](prereg-2026-09-30-reviewer-comparison-v2.md): dependent synthetic controls, credential-safe preflight, version-qualified extracted helpers and bounded sequential execution; immutable preparation retained outside main.

- [2026-09-30 Reviewer comparison preflight closeout](results-2026-09-30-reviewer-comparison-preflight.md): one claimed batch stopped on selected-credential syntax before client creation; zero native calls/deliveries, semantic judgment not run, immutable preparation kept outside main.

- [2026-09-30 Reviewer comparison development protocol](prereg-2026-09-30-reviewer-comparison.md): three fresh synthetic pairs, isolated native instructions, actual correction application and blind LLM judgment; six-request/USD 0.10 ceiling, no production activation.

- [2026-09-30 Reviewer comparison preparation](results-2026-09-30-reviewer-comparison-preparation.md): frozen synthetic inputs and instruction roots, credential/import/history boundaries, meaningful failure controls; mechanical preparation does not establish native semantic gain.

- [2026-09-30 RFID evidence boundaries](results-2026-09-30-rfid-evidence-boundaries.md): compound-aware patent admission and cautious news provenance; saved-candidate replay and scripted comparison delivery, not native semantic prevention or a new paid experiment.

- [2026-09-29 synthetic auxiliary restoration](results-2026-09-29-auxiliary-volume-restore.md): copied helper/PDF ledgers, source isolation, cleared caches, handler/model delivery, known lower bounds and unknown states; no double counting or read repair, original bounded inventory and stale-snapshot limits retained, no provider or real-volume operation.

- [2026-09-27 auxiliary LLM accounting](results-2026-09-27-auxiliary-llm-accounting.md): independent language/PDF observations, actual-thread settlement, read-only receipts and reference-only PDF associations; unknown usage and failed-storage lower bounds stay explicit, no new paid run or end-to-end invoice claim.

- [2026-09-27 positive saved-source selection closeout](results-2026-09-27-positive-source-selection-closeout.md): four existing native requests, mechanics 4/4, development-reference agreement 3/4, three exact saved-text deliveries and one decline; USD 0.003559650 frozen-rate estimate, reference-aware post hoc LLM audit, closed failed batch and immutable preparation reference rather than a new main-branch executor.

- [2026-09-27 ordered-window offline rule](prereg-2026-09-27-ordered-window-conjunction-offline.md) and [comparison result](results-2026-09-27-ordered-window-conjunction-offline.md): fixed queries, old and combined coverage 1/11, zero additions; failed development gate, uncertain reference and early self-test computation retained, isolated reproduction archive, no provider calls or production change.

- [2026-09-27 NQ native query result](results-2026-09-27-candidate-query-synthetic-canary.md): four requests, mechanics 4/4, positive coverage 1/3 and explicit decline 1/1; closed failed development batch, USD 0.001421807 frozen-rate estimate, no production admission.

- [2026-09-26 NQ synthetic query protocol](prereg-2026-09-26-candidate-query-synthetic-canary.md): pre-live question-only controls, separate candidate coverage/cancellation/mechanical gates and durable aggregate slots; known development miss retained and later native results recorded separately, no production activation.

- [2026-09-26 candidate-query Qwen wire preparation](prereg-2026-09-26-candidate-query-qwen-transport.md): question-only native query proposals, exact body/ledger binding, one-request accounting and intercepted-HTTP validation; no real key, paid allowance, source transfer, answer generation or production activation.

- [2026-09-26 bounded production saved-source acceptance](results-2026-09-26-production-source-locator-acceptance.md): one native selection delivered exact saved text; after execution closure and redeployment, one manual GET preserved the receipt and accounting. USD 0.000764436 frozen-rate estimate, original POST-body observer limitation, not unseen accuracy or permanent enablement.

- [2026-09-23 production saved-source public-origin repair](results-2026-09-23-source-locator-public-origin.md): one rejected production pilot before provider dispatch, explicit public-origin/Host binding across TLS termination, unchanged frozen labs, and zero-provider proxy-browser receipt recovery; paid execution stays disabled.

- [2026-09-22 RUQ native saved-source usage result](results-2026-09-22-real-source-usage-qwen.md): four native requests, three exact saved excerpts and one decline; complete POST/GET accounting, USD 0.003321282 frozen-rate estimate, no redispatch. Closed development batch, not model superiority or production activation.

- [2026-09-22 RU independent reference sidecar](results-2026-09-22-real-source-usage-reference-review.md): fresh-context LLM title-location judgments agree with four development drafts; exact quotation checks, set-valued references and article-type uncertainty are preserved. Not human gold, native model accuracy or measured user benefit.

- [2026-09-22 RUQ native usage pilot preparation](prereg-2026-09-22-real-source-usage-qwen.md): immutable RU origin, independent LLM reference sidecar, separate current-code binding and proposed four-request/USD 0.05 fixed batch; no live authority, new native observation or production activation.

- [2026-09-22 RU offline preparation result](results-2026-09-22-real-source-usage-offline.md): four scripted real-data receipt/usage rehearsals, unchanged source bytes and zero external provider calls; assisted-keyword candidate coverage, AI draft references and native efficacy unrun, not a model-advantage claim.

- [2026-09-22 RU real saved-source offline preparation](prereg-2026-09-22-real-source-usage-offline.md): two complete historical registries, four new questions, separate AI reference drafts/scripts, title-only no-model observation and isolated intercepted usage replay; no native efficacy, completed blind review or private-data transmission grant.

- [2026-09-20 RQ native receipt/browser result](results-2026-09-20-saved-source-receipt-qwen-canary.md): two native selections, 2/2 mechanical/reference gates, exact saved-text/decline delivery and lost-ack recovery without redispatch; USD 0.000799403 reported-use estimate, separate unobserved HTTP accounting, closed synthetic batch and no public activation.

- [2026-09-20 RQ synthetic receipt/browser preregistration](prereg-2026-09-20-saved-source-receipt-qwen-canary.md): two fresh fictional controls, exact-case native binding, two-request/USD 0.05 maximum and receipt recovery through the real isolated browser; preparation is not a native result or production activation.

- [2026-09-19 SLCQ native comparison result](results-2026-09-19-public-source-locator-qwen-comparison.md): six native requests and 6/6 mechanical/reference checks, five valid title locations and one explicit decline; assisted keywords also succeed, five reads deliver no text, USD 0.004639290 reported-use estimate. Closed batch, no quality superiority or production activation.

- [2026-09-19 SLCQ native comparison preregistration](prereg-2026-09-19-public-source-locator-qwen-comparison.md) and [pre-live baseline encoding erratum](erratum-2026-09-19-slc-baseline-encoding.md): same six frozen questions and public-title scope as SLC, separate six-request/USD 0.10 batch, set-valued reference gates and explicit missing-text delivery; preparation is not a native outcome.

- [2026-09-19 SLC public-title comparison preregistration](prereg-2026-09-19-public-source-search-comparison.md) and [observed baseline](results-2026-09-19-public-source-search-baseline.md): six new questions over twenty public bibliography titles; assisted keywords cover all five positive-reference cases, with four unique and one valid pair. Whole-question misses are diagnostic, unavailable states stay explicit, and the model lane is not run.

- [2026-09-19 SLQ native source-location result](results-2026-09-19-source-locator-qwen-canary.md): four native requests, 4/4 mechanical and 4/4 development-reference checks, USD 0.001656723 reported-use estimate; explicit decline/missing text preserved, separate LLM inspection, closed synthetic batch and no production activation.

- [2026-09-19 SLQ synthetic locator preregistration](prereg-2026-09-19-source-locator-qwen-canary.md): four newly frozen title-selection/decline/missing-text controls, separate code-owned delivery and reference gates, one fixed four-request/USD 0.05 batch; preparation is not native success or production admission.

- [2026-09-18 source-locator Qwen wire preregistration](prereg-2026-09-18-source-locator-qwen-transport.md): isolated one-selection adapter, exact question/catalog wire identity and a dedicated one-request durable ledger; intercepted HTTP only, no new native result or production route.

- [2026-09-18 saved-source locator preregistration](prereg-2026-09-18-saved-source-locator.md): one callback selection and code-owned complete saved-text delivery; reuses existing catalog/read primitives without a model-generated answer, native adapter or production route.

- [2026-09-18 read-first native result](results-2026-09-18-read-first-qwen-canary.md): two requests and one actual full read, but a failed first relation label; later controls unrun, context-limited LLM judgment mixed, batch closed and production unchanged.

- [2026-09-18 read-first follow-up preregistration](prereg-2026-09-18-read-first-followup.md) and [offline engineering](results-2026-09-18-read-first-followup-implementation.md): three fresh dependent synthetic controls, a named-read native boundary and separate delivery observations; not autonomous selection, a native result or production admission.

- [2026-09-18 RPQ native early-final result](results-2026-09-18-relation-policy-qwen-canary.md): one request, zero reads/receipts/admitted answers, first-stage mechanical rejection; no label checks, RP02/RP03 unrun and the fixed batch closed.

- [2026-09-18 relation-policy native canary preregistration](prereg-2026-09-18-relation-policy-qwen-canary.md) and [runner verification](results-2026-09-18-relation-policy-qwen-runner.md): a separate RP01-RP03 synthetic batch with policy/callback/native delivery gates, exact identity, six-request limit and first-failure stop; preparation is not a provider observation.

- [2026-09-17 test maintenance and CI consolidation](results-2026-09-17-test-maintenance.md): stronger delivery/call assertions, executable workflow checks and four full matrix executions with the existing coverage floor; frozen experiments and production remain unchanged.

- [2026-09-17 RP native CI isolation correction](results-2026-09-17-relation-policy-ci-isolation.md): a process-global test guard outlived the operation and broke verbose pytest reporting; scoped restoration preserves strict adapter checks without changing the runtime or frozen experiments.

- [2026-09-17 relation-policy native wire preregistration](prereg-2026-09-17-relation-policy-qwen-transport.md) and [offline result](results-2026-09-17-relation-policy-qwen-transport.md): separate positional adapter, exact policy/claim/read-result binding and HTTP/journal boundaries; no new provider observation or production route.

- [2026-09-17 explicit relation-policy offline contract](prereg-2026-09-17-claim-relation-policy.md) and [development result](results-2026-09-17-claim-relation-policy.md): a separate absence/contradiction policy, new synthetic development controls, callback delivery audit and unchanged native/production boundaries.

- [2026-09-17 PCQ native canary result](results-2026-09-17-claim-proposition-contrast-qwen-canary.md): two requests before the first reference mismatch; one mechanical pass, zero of one checked label matches and two unrun controls. Context-limited LLM assessment is mixed; closed failure, not production admission.

- [2026-09-17 PCQ native executor offline result](results-2026-09-17-claim-proposition-contrast-qwen-runner.md): dedicated identity and output, 208 new intercepted-HTTP tests, distinct mechanical/label/publication observations and three actual dispatch-count fault reinjections; no new Qwen observation.

- [2026-09-17 PCQ native Qwen preregistration](prereg-2026-09-17-claim-proposition-contrast-qwen-canary.md): a separate fixed-output executor for the already frozen synthetic contrast controls, at most six sequential requests after exact-tree validation; preparation is not a live result.

- [2026-09-17 PCQ proposition-contrast preparation](results-2026-09-17-claim-proposition-contrast.md): fresh-context LLM pre-review of three synthetic references before native testing, plus a separate offline rehearsal; no Qwen result or relabeling of the failed CLQ batch.
- [2026-09-17 PCQ offline preregistration](prereg-2026-09-17-claim-proposition-contrast.md): distinguish actual physical value from the content of a measurement record; blind projection, immutable draft identity and independent freeze gate.

- [2026-09-16 claim-relative Qwen canary result](results-2026-09-16-claim-qwen-canary.md): six requests, three per-case mechanical passes but 2/3 frozen-label matches; batch failed. Blind LLM review diagnoses a recording-versus-physical-value reference mismatch without changing the label or rerunning the batch.

- [2026-09-16 claim-relative synthetic Qwen canary preregistration](prereg-2026-09-16-claim-qwen-canary.md): three fresh support/refutation/insufficiency controls, six sequential requests maximum and first-failure stop; separate blind LLM judging, no private report transmission or production activation.

- [2026-09-16 claim-relative Qwen wire result](results-2026-09-16-claim-qwen-transport.md): native HTTP/ledger admission, 88 synthetic controls, four targeted mutation failures and local 30-snapshot capacity replay; no provider inference or semantic-accuracy claim.

- [2026-09-16 claim-relative Qwen wire preregistration](prereg-2026-09-16-claim-qwen-transport.md): independent snapshot/claim-bound native bridge, full HTTP byte and usage boundaries; intercepted transport only, no new live batch or old allowance reuse.

- [2026-09-16 offline claim-relation result](results-2026-09-16-followup-claim-relation.md): actual callback delivery, four model-declared relations and code-derived status, with fresh synthetic controls; no semantic-accuracy or live-provider claim.

- [2026-09-16 offline claim-relation preregistration](prereg-2026-09-16-followup-claim-relation.md): separate model-declared evidence relationship from code-owned delivery; new synthetic controls, LLM-only future judging, no paid inference or production activation.

- [2026-09-16 real saved-report Qwen pilot preregistration](prereg-2026-09-16-report-evidence-real-saved-qwen.md): separate exact-packet authorization, four sequential requests, fixed single-batch output, first-failure stop and disclosed post-hoc LLM review; not another synthetic run or production activation.

- [2026-09-16 real saved-report offline result](results-2026-09-16-report-evidence-real-saved-offline.md): full 20-source catalog, separate labels and two scripted read-to-final probes; no provider requests, model correctness or live authorization.

- [2026-09-16 real saved-report offline preparation](prereg-2026-09-16-report-evidence-real-saved-offline.md): one historical live report, two new developmental questions, private byte-bound inputs and nonempty read-then-abstain; no real-data transmission or live runner.

- [2026-09-16 CQ native synthetic result](results-2026-09-16-report-evidence-catalog-qwen-canary.md): both frozen cases passed in four accounted requests; actual read-to-final closure and missing-text abstention, not general quality or production activation.

- [2026-09-16 catalog-native CQ canary preregistration](prereg-2026-09-16-report-evidence-catalog-qwen-canary.md): two fresh synthetic controls, four requests maximum and first-failure stop; independent from the adapter's offline manifest and all closed batches.

- [2026-09-16 catalog-native Qwen offline result](results-2026-09-16-report-evidence-catalog-qwen-transport.md): actual intercepted bodies and journal hashes, with separate protocol/semantic limits and no live model claim.

- [2026-09-16 catalog-native Qwen offline protocol](prereg-2026-09-16-report-evidence-catalog-qwen-transport.md): a separate 32-ID wire/history/accounting contract, not a widened old adapter or a live batch.

- [2026-09-16 bounded catalog offline result](results-2026-09-16-report-evidence-catalog.md): local metadata capacity and read-before-cite contract; not a native provider observation or production enablement.

- [2026-09-16 offline bounded catalog protocol](prereg-2026-09-16-report-evidence-catalog.md): metadata discovery plus one actual read; no new paid batch, production route or reinterpretation of JQ failure.

- [2026-09-16 final-only JSON JQ result](results-2026-09-16-report-evidence-final-json-qwen.md): valid final envelope on the zero-hit branch, failed positive saved-read gate, second case unrun; no production admission.

- [2026-09-16 final-only JSON Qwen protocol](prereg-2026-09-16-report-evidence-final-json-qwen.md) — new JQ synthetic controls, final-only JSON Object wire contract, strict parsing and separate bounded authorization; old failures unchanged.

- [2026-09-15 stage-aware Qwen live result](results-2026-09-15-stage-qwen-canary-live.md) — three accounted requests; saved text reached final-only HTTP, SQ01 failed strict JSON-envelope parsing, SQ02 unrun; no retry or production activation.

- [2026-09-15 stage-aware Qwen canary preparation result](results-2026-09-15-stage-qwen-canary-preparation.md) — 81 new offline tests, default committed identity check and first-case failure dispatch counterexample; no live cases run.

- [2026-09-15 stage-aware Qwen canary protocol](prereg-2026-09-15-report-evidence-stage-qwen-canary.md) — new synthetic identity and default-off runner; offline preparation, separate live authorization required.

- [2026-09-15 stage-aware Qwen transport result](results-2026-09-15-report-evidence-stage-qwen-transport.md) — final-only intent reaches intercepted HTTP and its journal; Windows fixture failure retained, no provider observation.

- [2026-09-15 stage-aware Qwen transport protocol](prereg-2026-09-15-report-evidence-stage-qwen-transport.md) — preserve final-only semantics at intercepted HTTP and journal boundaries; no live authorization.

- [2026-09-15 offline stage-control result](results-2026-09-15-report-evidence-stage-policy.md) — dispatch and actual-forwarding seams; 43 new tests, no new provider observations.

- [2026-09-15 offline follow-up stage policy](prereg-2026-09-15-report-evidence-stage-policy.md) — reserve read/finalization within unchanged limits; no new live authorization.

- [2026-09-15 native Qwen follow-up result](results-2026-09-15-report-evidence-followup-qwen-canary.md) — three accounted native requests; closure failed at the tool budget, second case unrun, no retry.

- [2026-09-14 bounded Qwen follow-up canary](prereg-2026-09-14-report-evidence-followup-qwen.md) — two synthetic controls, at most six requests and USD 0.10; production-disconnected.

- [2026-09-14 saved-evidence follow-up protocol](prereg-2026-09-14-report-evidence-followup-phase1.md) — isolated read-only conversation hypothesis, direct-browsing baseline, no live authorization.
- [2026-09-14 saved-evidence follow-up result](results-2026-09-14-report-evidence-followup-phase1.md) — bounded native-shaped offline loop and evidence receipts, not production supplementation or semantic verification.

- [2026-09-13 PDF receipt observer isolation](results-2026-09-13-pdf-receipt-observer-isolation.md) — deterministic single-slot observer failure and event-loop handshake; original CI timing cause unproven, production unchanged.

- [2026-09-12 market-source follow-up](results-2026-09-12-market-source-followup.md) — remaining 14 candidates and seven comparisons; all 20 inspected across two dates, no fully established real positive and no scoring change.
- [2026-09-12 numeric token and cap provenance](results-2026-09-12-numeric-token-and-cap-provenance.md) — whole expressions/explicit abstention and pre/post arithmetic receipts; frozen formula unchanged, no independent accuracy claim.

- [2026-09-11 market-score delivery disclosure](results-2026-09-11-market-score-delivery-disclosure.md) — writer/HTTP/browser qualification and fault reinjection; frozen numeric cap unchanged, semantic comparability unestablished.

- [2026-09-11 six-source market spot check](results-2026-09-11-market-source-spot-check.md) — agent-only public-page inspection; scope mismatch and source/version uncertainty, no scoring change or independent accuracy claim.

- [2026-09-11 upload deadline parser ordering](results-2026-09-11-upload-deadline-parser-order.md) — preserve a local failure despite green CI; deterministic post-open fault injection, no production timeout change.

- [2026-09-11 market estimate sample contract](results-2026-09-11-market-estimate-sample-contract.md) — synthetic controls and unreviewed snapshot preparation, not an independent market-accuracy evaluation.

- [2026-09-10 durable paid receipts](results-2026-09-10-durable-paid-receipts.md) — offline HTTP/SQLite/browser acceptance recovery and defect reinjection; no paid experiment.

[Current evidence ledger](evidence-status.md) · [Documentation map](README.md)

These dated records are historical evidence, not statements that every feature
is currently production-enabled. Failed, incomplete and excluded outcomes stay
visible. Review declarations, frozen-source identities and protocol limitations
belong to the linked record, not a blended headline.

## Before the documentation consolidation

The long chronological narratives remain available at the exact audited commit,
without duplicating them into another current guide:

- [README at 0fdaa76](https://github.com/shuxiachai/academic-commercialization-agent/blob/0fdaa76a107cf034c16c1ffa6e3ae623e4c63fe2/README.md)
- [AGENTS at 0fdaa76](https://github.com/shuxiachai/academic-commercialization-agent/blob/0fdaa76a107cf034c16c1ffa6e3ae623e4c63fe2/AGENTS.md)
- [Reasoning commits through 0fdaa76](https://github.com/shuxiachai/academic-commercialization-agent/commits/0fdaa76a107cf034c16c1ffa6e3ae623e4c63fe2/)

No frozen fixtures, results, source locks or experimental implementation paths
were moved or rewritten by this consolidation. Files after this snapshot must
be evaluated under their own protocols; existing failures are not permission
to reuse consumed cohorts.

## Recent offline maintenance

- [2026-09-11 upload timeout test isolation](results-2026-09-11-upload-timeout-test-isolation.md) — retained main-CI failure, scoped 20ms fault injection and single-slot recovery assertions; production limits unchanged.

- [2026-09-11 market-metric comparability](results-2026-09-11-market-metric-comparability.md) — offline typed diagnostic, snapshot/CSV identity mismatch and explicit non-assessment; production cap unchanged.

- [2026-09-11 PDF/numeric/receipt seams](results-2026-09-11-pdf-numeric-receipt-seams.md) — separate candidate identity, signed/case-sensitive quantities and thread-owned failure receipts; zero provider calls.

- [2026-09-10 evidence/PDF/terminal boundaries](results-2026-09-10-evidence-pdf-terminal-boundaries.md) — precision-aware numeric matching, production-only citation admission, actual PDF input coverage, candidate identity limits and terminal-authoritative operational outcomes; zero provider calls.

- [2026-09-08 upload/history/cancellation boundaries](results-2026-09-08-upload-history-cancellation-boundaries.md) — pre-parser byte/time/capacity limits, generation-bound history and thread-owned PDF cleanup; zero provider calls.

- [2026-09-08 paid-request refresh warning](results-2026-09-08-paid-refresh-warning.md) — credential-free session warning, explicit acknowledgement and view-delivery settlement; zero provider calls, not server idempotency.

- [2026-09-08 client delivery seams](results-2026-09-08-client-delivery-seams.md) — optional log isolation/cursors, truthful details and browser-storage fallback, zero provider calls.
- [2026-09-08 combined client boundaries](results-2026-09-08-client-boundary-combinations.md) — fractional score regression, explicit BYOK identity and visible stale reads; zero provider calls.
- [2026-09-08 browser access identity](results-2026-09-08-browser-access-identity.md) — document-local payer selection, late-401 isolation and explicit conflict logout; zero provider calls.
- [2026-09-07 cleanup outcomes](results-2026-09-07-cleanup-outcome-observability.md) — advisory per-attempt counters and explicit incomplete coverage at both HTTP schemas.
- [2026-09-07 maintenance observation age](results-2026-09-07-maintenance-observation-age.md) — time-qualified health/readiness snapshots without a new SLO or provider call.
- [2026-09-06 maintenance event-loop ownership](results-2026-09-06-maintenance-event-loop.md) — held-stage HTTP probes and shutdown drain, zero provider calls.
- [2026-09-06 run stop ownership](results-2026-09-06-run-stop-ownership.md) — cancellation/timeout capacity and artifact boundaries, no provider calls.
- [2026-09-06 readiness, PDF query and audit-detail maintenance](results-2026-09-06-maintenance-readiness-query-audit.md) — offline boundary verification, not a paid experiment.

## Release snapshot

- [2026-09-10 provider identity and diagnostic privacy](results-2026-09-10-provider-and-log-boundaries.md) — shared routing, fixed BYOK destinations, redirect refusal and narrow sensitive-error logging; no paid calls.

- [v2.0.0 release record](release-v2.0.0.md) — numbers are from that release.

## Pre-registrations and protocols

- [2026 08 14 trl scope rule](prereg-2026-08-14-trl-scope-rule.md)
- [2026 08 14 trl8 anchor](prereg-2026-08-14-trl8-anchor.md)
- [2026 08 21 agent topology ablation](prereg-2026-08-21-agent-topology-ablation.md)
- [2026 08 22 patent relevance audit](prereg-2026-08-22-patent-relevance-audit.md)
- [2026 08 22 patent relevance candidate screen v1](prereg-2026-08-22-patent-relevance-candidate-screen-v1.md)
- [2026 08 22 reviewer value audit](prereg-2026-08-22-reviewer-value-audit.md)
- [2026 08 22 user utility audit](prereg-2026-08-22-user-utility-audit.md)
- [2026 08 23 checkpoint fault recovery](prereg-2026-08-23-checkpoint-fault-recovery.md)
- [2026 08 24 input shape contracts](prereg-2026-08-24-input-shape-contracts.md)
- [2026 08 24 paid same revision recovery follow up](prereg-2026-08-24-paid-same-revision-recovery-follow-up.md)
- [2026 08 24 paid same revision recovery post fix](prereg-2026-08-24-paid-same-revision-recovery-post-fix.md)
- [2026 08 24 paid same revision recovery](prereg-2026-08-24-paid-same-revision-recovery.md)
- [2026 08 25 evidence gap human review phase3](prereg-2026-08-25-evidence-gap-human-review-phase3.md)
- [2026 08 25 evidence gap live adapter phase3](prereg-2026-08-25-evidence-gap-live-adapter-phase3.md)
- [2026 08 25 evidence gap shadow planner](prereg-2026-08-25-evidence-gap-shadow-planner.md)
- [2026 08 25 evidence gap shadow post fix canary](prereg-2026-08-25-evidence-gap-shadow-post-fix-canary.md)
- [2026 08 25 evidence gap tool execution phase2](prereg-2026-08-25-evidence-gap-tool-execution-phase2.md)
- [2026 08 25 regulator title recovery candidate](prereg-2026-08-25-regulator-title-recovery-candidate.md)
- [2026 08 25 regulator title recovery paid canary](prereg-2026-08-25-regulator-title-recovery-paid-canary.md)
- [2026 08 26 decision context paid canary](prereg-2026-08-26-decision-context-paid-canary.md)
- [2026 08 26 decision context report contract](prereg-2026-08-26-decision-context-report-contract.md)
- [2026 08 26 evidence gap domain adapters phase4](prereg-2026-08-26-evidence-gap-domain-adapters-phase4.md)
- [2026 08 26 evidence gap domain live phase4](prereg-2026-08-26-evidence-gap-domain-live-phase4.md)
- [2026 08 26 target user decision pilot](prereg-2026-08-26-target-user-decision-pilot.md)
- [2026 08 27 evidence gap anonymous openalex](prereg-2026-08-27-evidence-gap-anonymous-openalex.md)
- [2026 08 27 openalex claim scope v3](prereg-2026-08-27-openalex-claim-scope-v3.md)
- [2026 08 27 openalex precision v2](prereg-2026-08-27-openalex-precision-v2.md)
- [2026 08 27 openalex scope link v4](prereg-2026-08-27-openalex-scope-link-v4.md)
- [2026 08 28 openalex scope link v4 live](prereg-2026-08-28-openalex-scope-link-v4-live.md)
- [2026 08 29 openalex evidence set v5](prereg-2026-08-29-openalex-evidence-set-v5.md)
- [2026 08 29 openalex scope link v4 abstention diagnostic](prereg-2026-08-29-openalex-scope-link-v4-abstention-diagnostic.md)
- [2026 08 30 openalex evidence set v5 provider contract amendment](prereg-2026-08-30-openalex-evidence-set-v5-provider-contract-amendment.md)
- [2026 08 31 openalex evidence set v5 qwen failure diagnostic](prereg-2026-08-31-openalex-evidence-set-v5-qwen-failure-diagnostic.md)
- [2026 08 31 openalex evidence set v5 qwen provider amendment](prereg-2026-08-31-openalex-evidence-set-v5-qwen-provider-amendment.md)
- [2026 08 31 openalex evidence set v5 qwen timeout amendment](prereg-2026-08-31-openalex-evidence-set-v5-qwen-timeout-amendment.md)
- [2026 09 01 openalex role directed retrieval v7 live runner](prereg-2026-09-01-openalex-role-directed-retrieval-v7-live-runner.md)
- [2026 09 01 openalex role directed retrieval v7](prereg-2026-09-01-openalex-role-directed-retrieval-v7.md)
- [2026 09 01 openalex role slot consensus v6 development runner](prereg-2026-09-01-openalex-role-slot-consensus-v6-development-runner.md)
- [2026 09 01 openalex role slot consensus v6 runner identity clarification](prereg-2026-09-01-openalex-role-slot-consensus-v6-runner-identity-clarification.md)
- [2026 09 01 openalex role slot consensus v6](prereg-2026-09-01-openalex-role-slot-consensus-v6.md)
- [2026 09 01 openalex role slot v6 failure diagnostic](prereg-2026-09-01-openalex-role-slot-v6-failure-diagnostic.md)
- [2026 09 02 openalex adaptive role gap closure v8](prereg-2026-09-02-openalex-adaptive-role-gap-closure-v8.md)
- [2026 09 02 openalex adaptive role gap v8 live runner](prereg-2026-09-02-openalex-adaptive-role-gap-v8-live-runner.md)
- [2026 09 02 openalex role directed v7 human review](prereg-2026-09-02-openalex-role-directed-v7-human-review.md)
- [2026 09 03 openalex adaptive role gap v8 ad evaluation](prereg-2026-09-03-openalex-adaptive-role-gap-v8-ad-evaluation.md)
- [2026 09 03 openalex adaptive role gap v8 ad human review](prereg-2026-09-03-openalex-adaptive-role-gap-v8-ad-human-review.md)
- [2026 09 03 openalex adaptive role gap v8 human review](prereg-2026-09-03-openalex-adaptive-role-gap-v8-human-review.md)
- [2026 09 03 report decision and citation seams](prereg-2026-09-03-report-decision-and-citation-seams.md)
- [2026 09 04 decision threshold warning precision](prereg-2026-09-04-decision-threshold-warning-precision.md)
- [2026 09 04 report decision seams paid canary](prereg-2026-09-04-report-decision-seams-paid-canary.md)
- [2026 09 04 runtime terminal integrity paid canary](prereg-2026-09-04-runtime-terminal-integrity-paid-canary.md)
- [2026 09 04 runtime terminal integrity post browser seam paid canary](prereg-2026-09-04-runtime-terminal-integrity-post-browser-seam-paid-canary.md)
- [2026 08 25 regulator title quality audit](protocol-2026-08-25-regulator-title-quality-audit.md)

## Results and implementation records

- [2026 08 23 checkpoint fault recovery](results-2026-08-23-checkpoint-fault-recovery.md)
- [2026 08 23 reviewer value audit](results-2026-08-23-reviewer-value-audit.md)
- [2026 08 23 user utility audit](results-2026-08-23-user-utility-audit.md)
- [2026 08 24 paid same revision recovery follow up](results-2026-08-24-paid-same-revision-recovery-follow-up.md)
- [2026 08 24 paid same revision recovery post fix](results-2026-08-24-paid-same-revision-recovery-post-fix.md)
- [2026 08 24 paid same revision recovery](results-2026-08-24-paid-same-revision-recovery.md)
- [2026 08 24 production checkpoint follow up](results-2026-08-24-production-checkpoint-follow-up.md)
- [2026 08 25 evidence gap human review packet phase3](results-2026-08-25-evidence-gap-human-review-packet-phase3.md)
- [2026 08 25 evidence gap live adapter phase3 implementation](results-2026-08-25-evidence-gap-live-adapter-phase3-implementation.md)
- [2026 08 25 evidence gap live provider phase3](results-2026-08-25-evidence-gap-live-provider-phase3.md)
- [2026 08 25 evidence gap shadow planner phase1](results-2026-08-25-evidence-gap-shadow-planner-phase1.md)
- [2026 08 25 evidence gap shadow post fix canary](results-2026-08-25-evidence-gap-shadow-post-fix-canary.md)
- [2026 08 25 evidence gap tool execution phase2](results-2026-08-25-evidence-gap-tool-execution-phase2.md)
- [2026 08 25 regulator title quality audit](results-2026-08-25-regulator-title-quality-audit.md)
- [2026 08 25 regulator title recovery candidate](results-2026-08-25-regulator-title-recovery-candidate.md)
- [2026 08 25 regulator title recovery paid canary](results-2026-08-25-regulator-title-recovery-paid-canary.md)
- [2026 08 26 decision context paid canary](results-2026-08-26-decision-context-paid-canary.md)
- [2026 08 26 decision context report contract](results-2026-08-26-decision-context-report-contract.md)
- [2026 08 26 decision readiness baseline](results-2026-08-26-decision-readiness-baseline.md)
- [2026 08 26 evidence gap domain adapters phase4 implementation](results-2026-08-26-evidence-gap-domain-adapters-phase4-implementation.md)
- [2026 08 26 evidence gap domain live phase4 implementation](results-2026-08-26-evidence-gap-domain-live-phase4-implementation.md)
- [2026 08 26 evidence gap human review phase3](results-2026-08-26-evidence-gap-human-review-phase3.md)
- [2026 08 26 target user decision pilot](results-2026-08-26-target-user-decision-pilot.md)
- [2026 08 27 evidence gap anonymous openalex implementation](results-2026-08-27-evidence-gap-anonymous-openalex-implementation.md)
- [2026 08 27 evidence gap anonymous openalex live](results-2026-08-27-evidence-gap-anonymous-openalex-live.md)
- [2026 08 27 evidence gap anonymous openalex review implementation](results-2026-08-27-evidence-gap-anonymous-openalex-review-implementation.md)
- [2026 08 27 evidence gap anonymous openalex review](results-2026-08-27-evidence-gap-anonymous-openalex-review.md)
- [2026 08 27 openalex claim scope v3 implementation](results-2026-08-27-openalex-claim-scope-v3-implementation.md)
- [2026 08 27 openalex claim scope v3 live implementation](results-2026-08-27-openalex-claim-scope-v3-live-implementation.md)
- [2026 08 27 openalex claim scope v3 live](results-2026-08-27-openalex-claim-scope-v3-live.md)
- [2026 08 27 openalex claim scope v3 review implementation](results-2026-08-27-openalex-claim-scope-v3-review-implementation.md)
- [2026 08 27 openalex claim scope v3 review](results-2026-08-27-openalex-claim-scope-v3-review.md)
- [2026 08 27 openalex precision v2 development](results-2026-08-27-openalex-precision-v2-development.md)
- [2026 08 27 openalex precision v2 unseen implementation](results-2026-08-27-openalex-precision-v2-unseen-implementation.md)
- [2026 08 27 openalex precision v2 unseen live](results-2026-08-27-openalex-precision-v2-unseen-live.md)
- [2026 08 27 openalex scope link v4 implementation](results-2026-08-27-openalex-scope-link-v4-implementation.md)
- [2026 08 27 public pipeline revision seam](results-2026-08-27-public-pipeline-revision-seam.md)
- [2026 08 28 openalex scope link v4 live implementation](results-2026-08-28-openalex-scope-link-v4-live-implementation.md)
- [2026 08 29 openalex evidence set v5 development runner implementation](results-2026-08-29-openalex-evidence-set-v5-development-runner-implementation.md)
- [2026 08 29 openalex evidence set v5 implementation](results-2026-08-29-openalex-evidence-set-v5-implementation.md)
- [2026 08 29 openalex scope link v4 abstention diagnostic implementation](results-2026-08-29-openalex-scope-link-v4-abstention-diagnostic-implementation.md)
- [2026 08 29 openalex scope link v4 abstention diagnostic review](results-2026-08-29-openalex-scope-link-v4-abstention-diagnostic-review.md)
- [2026 08 29 openalex scope link v4 live](results-2026-08-29-openalex-scope-link-v4-live.md)
- [2026 08 30 openalex evidence set v5 development provider drift](results-2026-08-30-openalex-evidence-set-v5-development-provider-drift.md)
- [2026 08 30 openalex evidence set v5 provider contract amendment implementation](results-2026-08-30-openalex-evidence-set-v5-provider-contract-amendment-implementation.md)
- [2026 08 30 qwen35 plus first paid canary](results-2026-08-30-qwen35-plus-first-paid-canary.md)
- [2026 08 30 qwen35 plus provider adapter implementation](results-2026-08-30-qwen35-plus-provider-adapter-implementation.md)
- [2026 08 31 openalex evidence set v5 qwen development timeout](results-2026-08-31-openalex-evidence-set-v5-qwen-development-timeout.md)
- [2026 08 31 openalex evidence set v5 qwen failure diagnostic](results-2026-08-31-openalex-evidence-set-v5-qwen-failure-diagnostic.md)
- [2026 08 31 openalex evidence set v5 qwen provider implementation](results-2026-08-31-openalex-evidence-set-v5-qwen-provider-implementation.md)
- [2026 08 31 openalex evidence set v5 qwen schema4 development](results-2026-08-31-openalex-evidence-set-v5-qwen-schema4-development.md)
- [2026 08 31 openalex evidence set v5 qwen timeout amendment implementation](results-2026-08-31-openalex-evidence-set-v5-qwen-timeout-amendment-implementation.md)
- [2026 09 01 openalex role directed retrieval v7 offline](results-2026-09-01-openalex-role-directed-retrieval-v7-offline.md)
- [2026 09 01 openalex role slot consensus v6 development live](results-2026-09-01-openalex-role-slot-consensus-v6-development-live.md)
- [2026 09 01 openalex role slot consensus v6 development runner implementation](results-2026-09-01-openalex-role-slot-consensus-v6-development-runner-implementation.md)
- [2026 09 01 openalex role slot consensus v6 offline](results-2026-09-01-openalex-role-slot-consensus-v6-offline.md)
- [2026 09 01 openalex role slot v6 failure diagnostic implementation](results-2026-09-01-openalex-role-slot-v6-failure-diagnostic-implementation.md)
- [2026 09 01 openalex role slot v6 failure diagnostic review](results-2026-09-01-openalex-role-slot-v6-failure-diagnostic-review.md)
- [2026 09 02 openalex adaptive role gap closure v8 offline](results-2026-09-02-openalex-adaptive-role-gap-closure-v8-offline.md)
- [2026 09 02 openalex adaptive role gap v8 ac live](results-2026-09-02-openalex-adaptive-role-gap-v8-ac-live.md)
- [2026 09 02 openalex adaptive role gap v8 live runner](results-2026-09-02-openalex-adaptive-role-gap-v8-live-runner.md)
- [2026 09 02 openalex role directed retrieval v7 development live](results-2026-09-02-openalex-role-directed-retrieval-v7-development-live.md)
- [2026 09 02 openalex role directed retrieval v7 live runner](results-2026-09-02-openalex-role-directed-retrieval-v7-live-runner.md)
- [2026 09 02 openalex role directed v7 human review boundary](results-2026-09-02-openalex-role-directed-v7-human-review-boundary.md)
- [2026 09 02 openalex role directed v7 human review](results-2026-09-02-openalex-role-directed-v7-human-review.md)
- [2026 09 03 openalex adaptive role gap v8 ad human review boundary](results-2026-09-03-openalex-adaptive-role-gap-v8-ad-human-review-boundary.md)
- [2026 09 03 openalex adaptive role gap v8 ad human review](results-2026-09-03-openalex-adaptive-role-gap-v8-ad-human-review.md)
- [2026 09 03 openalex adaptive role gap v8 ad live](results-2026-09-03-openalex-adaptive-role-gap-v8-ad-live.md)
- [2026 09 03 openalex adaptive role gap v8 ad runner implementation](results-2026-09-03-openalex-adaptive-role-gap-v8-ad-runner-implementation.md)
- [2026 09 03 openalex adaptive role gap v8 human review boundary](results-2026-09-03-openalex-adaptive-role-gap-v8-human-review-boundary.md)
- [2026 09 03 openalex adaptive role gap v8 human review](results-2026-09-03-openalex-adaptive-role-gap-v8-human-review.md)
- [2026 09 03 report decision and citation seams](results-2026-09-03-report-decision-and-citation-seams.md)
- [2026 09 04 decision threshold warning precision](results-2026-09-04-decision-threshold-warning-precision.md)
- [2026 09 04 handheld ultrasound authority applicability](results-2026-09-04-handheld-ultrasound-authority-applicability.md)
- [2026 09 04 report decision seams paid canary](results-2026-09-04-report-decision-seams-paid-canary.md)
- [2026 09 04 runtime terminal integrity implementation](results-2026-09-04-runtime-terminal-integrity-implementation.md)
- [2026 09 04 runtime terminal integrity paid canary preflight](results-2026-09-04-runtime-terminal-integrity-paid-canary-preflight.md)
- [2026 09 04 runtime terminal integrity post browser seam paid canary](results-2026-09-04-runtime-terminal-integrity-post-browser-seam-paid-canary.md)

## Runtime maintenance verification

- [2026-09-10 cost scope and benchmark identity](results-2026-09-10-cost-scope-and-benchmark-identity.md) — finite estimates, explicit Crew-only scope, immutable batch/reuse/export boundaries; no provider experiment.

- [2026 09 06 runtime and paid-delivery maintenance](results-2026-09-06-maintenance-runtime-paid-delivery.md)

- [2026 09 06 composer paid-operation integrity](results-2026-09-06-composer-paid-operation-integrity.md)

- [2026 09 06 report applicability authority](results-2026-09-06-report-applicability-authority.md)

- [2026 09 06 run mutation intent](results-2026-09-06-run-mutation-intent.md)

- [2026 09 05 runtime summary read integrity](results-2026-09-05-runtime-summary-read-integrity.md)
- [2026 09 05 nested audit metadata integrity](results-2026-09-05-nested-audit-metadata-integrity.md)
- [2026 09 05 runtime metadata integrity](results-2026-09-05-runtime-metadata-integrity.md)

## Errata

- [2026 08 25 evidence gap phase3 fixture identity](errata-2026-08-25-evidence-gap-phase3-fixture-identity.md)
- [2026 08 26 target user pilot form enums and ai timing](errata-2026-08-26-target-user-pilot-form-enums-and-ai-timing.md)
- [2026 08 27 anonymous openalex review declaration](errata-2026-08-27-anonymous-openalex-review-declaration.md)
- [2026 08 27 decision context reviewer zero target](errata-2026-08-27-decision-context-reviewer-zero-target.md)
- [2026 08 27 openalex precision v2 unseen fixture](errata-2026-08-27-openalex-precision-v2-unseen-fixture.md)
- [2026 09 01 openalex role directed v7 ab05 query](errata-2026-09-01-openalex-role-directed-v7-ab05-query.md)
- [2026 09 02 openalex role gap v8 query scope](errata-2026-09-02-openalex-role-gap-v8-query-scope.md)

The source-native retrieval and runtime contracts are indexed separately in
[AGENTS.md](../AGENTS.md); reviewer guides are in the [documentation map](README.md).
