# AGENTS.md — working on this project

An index, not a summary. Almost everything worth knowing is already in the
repository — the point of this file is to tell you where, and to stop you
redoing a handful of things that have already been tried and measured.

## What it is

A six-agent CrewAI pipeline that assesses whether a piece of academic research
is commercially viable. Three evidence agents (academic / patent / market) run
in parallel, then a report writer, a reviewer, and a scorer. Served two ways
from one codebase: a FastAPI + vanilla-JS web client and a CLI.

Live at https://academic-commercialization-agent.up.railway.app

Current state: 1569 tests (639 subtests), CI green on Linux + Windows × Python
3.11/3.12, deployed on Railway.

## Commands

```bash
uv run pytest -q                       # the whole suite; ~24s on Windows, zero network
uv run --with ruff ruff check .        # CI uses latest ruff, the local pin is older
uv sync --group e2e                    # opt-in real-browser dependency; not part of the default suite
uv run --group e2e playwright install chromium
uv run --group e2e python -m e2e.browser_smoke   # loopback only; zero provider calls
uv run uvicorn api.main:app --reload   # web client on :8000
uv run academic_agent --topic "<topic>"          # one run from the CLI
```

`uv run --with ruff` is deliberate. The pinned local ruff is 0.12.0 and CI
resolves `latest`; they disagree, and the flag is what makes a local check mean
what CI will say.

## Hard conventions

- **`filterwarnings = ["error::UserWarning"]`.** What it mainly guards: code
  paths that would reach a paid API warn and fall back rather than raising, so
  a test that leaks would otherwise pass silently. When a test trips it, read
  *which* warning fired before concluding anything. If it is the network one,
  the test is calling something real — fix the test's isolation, never add an
  ignore. But the project also warns deliberately on an unrecognised weight
  profile and on an audit screen that failed, and two test files assert those
  on purpose (`assertWarns`), so not every UserWarning is a leak.
- **No bare `except Exception`** without a `# noqa: BLE001` and a reason. ruff
  enforces it; the exceptions in this repo each say why in a comment.
- **CI also runs pylint, narrowly,** for `E0701` alone (except-clause ordering).
  ruff has no equivalent, and a real bug here was `except HTTPError` placed
  after `except URLError` — dead code, so every auth failure was retried as
  transient.
- **Commit messages carry the reasoning.** They are long on purpose and are a
  primary record — see below. **Do not add `Co-Authored-By` lines.**
- **Reply to the user in Chinese.** The code, comments, and commit messages
  stay in English.

## Where the reasoning lives

This project deliberately keeps its "why" out of chat logs and inside artifacts
that travel with the repo. When you want to know why something is the way it
is, in this order:

| Question | Where |
|---|---|
| Why is this code like this? | The comment above it. Non-obvious decisions are commented, including rejected alternatives |
| Why does this test exist? | Its docstring names the specific failure it caught |
| Why was this change made? | `git log` — bodies run to ~25 lines and explain the alternative that was rejected |
| Was this hypothesis tested? | `docs/prereg-*.md` — predictions and falsification criteria registered *before* paid runs |
| How does crash recovery work? | `docs/checkpoint-recovery.md` — identity, persistence, authorization, observable states, the 30/30 offline process audit, and the at-least-once boundary |
| Full decision history, first person | `notes/简历项目说明.md` — **a separate private repo** (`shuxiachai/academic-agent-notes`), gitignored here. 4,000+ lines with 61 numbered postmortems and supporting decision records. Ask the user for access if you need it |

Before writing or modifying CrewAI code specifically — the crew, the agents,
the task definitions — read `docs/crewai-reference.md`. That is the vendor's
auto-generated reference, and the library moves faster than most training
data. It used to occupy this filename, which meant an assistant opening the
repo got 1,000 lines about the framework and nothing about the project.

## Do not redo these

Each of these was implemented or measured and then rejected **on data**. The
numbers are the point; if you want to revisit one, beat the number.

- **Do not change the scoring formula or the `evidence_confidence` floor.**
  Every calibration figure this project reports comes from 30 runs scored under
  the current rules (26/30 TRL calibration, 30/30 formula correct, 30/30
  completed). Changing the computation retires that baseline, which is the only
  external anchor the project has. The floor is knowingly asymmetric — it only
  ever raises confidence — and `evidence.py` says so explicitly.
- **Do not add a "maturity language vs TRL" consistency check.** Built,
  measured on all 30 baseline reports, produced 2 flags and both were wrong: a
  paragraph attributes properties to several subjects and phrase matching
  cannot tell which one carries it. Requiring the topic's words nearby does not
  help — the incumbent in a carbon-capture report is also called "capture". The
  reasoning is preserved in `consistency.py` so nobody tries it a third time.
- **Do not make the uncited-claim screen blocking.** Measured on 30 delivered
  reports: 134 warnings across 30/30 reports, so blocking would have failed
  every run. After four exclusions it is 62 across 20/30 — still two thirds.
  The precision work is worth continuing; the blocking is not viable yet.
- **Do not add prompt caching.** Measured: 3.4% cache hit. A run is 6 requests
  and the six agents have different prefixes, so there is nothing reusable
  within a run.
- **Do not "improve" claim-grounding coverage by scraping more abstracts.**
  Checked: academic sources are already 68/68 with real abstracts. The only
  remaining headroom is the patent domain, and it needs a free Lens key, not
  code.
- **Do not upgrade CrewAI on main.** Pinned at `1.14.7`. If it needs upgrading,
  do it on a branch with a full benchmark comparison.

Two TRL rubric hypotheses were pre-registered and **both falsified** (see
`docs/`). If you want to improve calibration, the next step is a different
method — independent scores from several models, compared — not another rubric
edit.

## How work is done here

These are not style preferences; each came from a specific failure.

- **Measure before you change.** Twice now an external review's premise was
  correct and its proposed implementation was wrong, and the only thing that
  distinguished them was running the check over the 30 reports already on disk
  first. That data is free.
- **Re-inject the defect after fixing it.** Confirm the new test actually goes
  red. Twice this caught a weak *test* rather than a weak implementation.
- **Test the seam, not the field.** The worst class of bug here has been a
  value computed correctly and stored correctly that never reached the client:
  `response_model` silently drops undeclared fields, and two features never
  worked in a browser while 948 tests passed. Assert at the boundary, and
  assert the rule ("every key on the payload reaches both endpoints"), not the
  instance.
- **Precision over recall for every heuristic screen.** These report; they do
  not reject. A false positive on a finished six-agent run discards a paid
  assessment over a wording choice.
- **Silence is not a pass.** "0 unsupported out of 0 checked" and "everything
  passed" produce the same two numbers. Anywhere a check can fail to run, say
  so distinctly — the reliability panel and `claim_grounding.py` both do.
- **Prose is not covered by tests.** One recent round found five places where a
  comment, a docstring, or UI copy described behaviour the code did not have.
  When you change behaviour, the sentence next to it is part of the change.

## Layout

```
src/academic_agent/     pipeline: crew, agents/tasks config, source retrieval,
                        evidence models + guardrails, scoring, worker
  source_pipeline.py    ~3,400 lines, retrieval for all three domains
  source_title_recovery.py
                        precision-first neutral labels for broken official titles
  evidence.py           models, guardrails, scoring rubric
  evidence_gap.py       phase-1 gap signals and strict plan authorization
  evidence_gap_execution.py
                        phase-2 bounded executor; disconnected from production
  tools/evidence_search.py
                        one-request read-only adapter response contract
  tools/anonymous_openalex_search.py
                        key-free experimental wrapper; never production imported
  pipeline_worker.py    the subprocess one run executes in
  checkpoint_runtime.py
                        CrewAI hydration, task identity, and post-guardrail commits
  run_spec.py           immutable, non-secret input and decision-applicability
                        contract for child recovery
  checkpoints.py        atomic content-addressed storage and inspection states
api/                    FastAPI: runs registry, papers, access gate, models
web/                    vanilla JS client, no build step, strict CSP
ui/                     shared i18n, run-reader, and PDF-export utilities
tests/                  80 test modules plus conftest, organised by subject
e2e/browser_smoke.py    real Chromium access/input/report seam; blocks external
                        and mutating requests, so it cannot start paid work
benchmark.py            paid batch runs; --fixtures replays frozen evidence
patent_relevance_candidate.py
                        offline frozen candidate screen; never production filtering
regulator_title_audit.py
                        zero-network title census; zero denominator is not a pass
regulator_title_recovery_candidate.py
                        frozen title-recovery comparison; never performs retrieval
evidence_gap_phase2_audit.py
                        frozen zero-network Tool Calling contract replay
evidence_gap_phase3_audit.py
                        frozen five-case Tavily harness; dry-run is zero-network
evidence_gap_phase3_review.py
                        provenance-locked zero-network human-review intake
evidence_gap_phase4_audit.py
                        frozen eight-case domain-adapter preflight; zero-network only
evidence_gap_phase4_live.py
                        frozen live runner; explicit authorization, never production
evidence_gap_phase4_review.py
                        source lock plus provenance-checked Schema v2 human review
evidence_gap_openalex_live.py
                        anonymous four-case OpenAlex study; never production
ops_report.py           what real runs actually did, vs what the benchmark covers
user_utility_audit.py   zero-network 3–5 reviewer packet + strict unblinding
checkpoint_fault_audit.py
                        pre-registered hard-kill/restart matrix and strict checker
```

Runs are subprocesses writing to `outputs/<run_id>/`; the API, the browser and
the CLI all observe the same run through those files rather than shared memory.
A run URL is a read capability. Mutating a code-owned run additionally requires
its owner/admin code; an ownerless BYOK run has no second server-side identity.
Failed, cancelled, or timed-out runs with a retrieval checkpoint can start an
immutable child from the longest validated prefix. The child snapshots its
parent before launch, requires fresh credentials, and reports persistence and
reuse separately. See `docs/checkpoint-recovery.md` before changing this seam.

## Things that are known-open

- Blocking on uncited claims (above) — needs the detector tighter first.
- Evidence-gap Tool Calling now has a phase-2 execution kernel and a phase-3
  production-disconnected Tavily adapter; the production workflow is still
  phase-1 zero-call shadow mode. The phase-2 frozen 14-case synthetic
  challenge passed 14/14 dispositions and deterministic replays, retained six
  valid rows in a separate delta, and retained zero unexpected rows.
  Phase 3 freezes five collection/plan identities and one request per case. Its
  adapter forces basic search, code-owned domains, no redirects or internal
  retry, and requires provider request/credit accounting. Candidates, malformed
  result rows, local quarantine decisions, cost, latency and trace data reach
  write-once JSON/CSV artifacts. The first authorized post-merge preflight
  found that the implementation result had recorded a pre-commit draft's raw
  fixture hash rather than the first committed artifact. It stopped before
  adapter construction with zero requests and zero cost. The runner now checks
  the canonical committed bytes before JSON parsing or case expansion.
  A fresh authorization on deployed revision `adde83d` then completed the exact
  five-case pilot: five single-attempt requests, five inspectable credits, USD
  0.040 conservative cost, and 25 unique policy-valid rows reached the frozen
  blank review artifact. Production and report connections remained false. The
  separate review packet later returned 25/25 source-grounded rows and declared
  every URL attempted, but its own provenance records `MOST_OR_ALL` substantive
  AI use. The strict result is `excluded_substantive_ai / not_evaluated`, not a
  human-value pass. The observed form contains 5 relevant and 20 not-relevant
  candidates across the five cases. Three cases contain at least one
  `YES/YES`; these are descriptive labels only. Even if treated as eligible,
  the implied 80% wrong-source rate would fail the frozen 5% maximum.
  Intake also found that packet schema v1 did not expose the frozen baseline
  against which it asked the reviewer to judge novelty. Schema v2 now carries
  and revalidates the collection identity, gap state and source summaries.
  Legacy packets remain inspectable as history but explicitly report
  `baseline_context_not_exposed_to_reviewer`; they cannot silently produce an
  eligible novelty headline. The hardened review intake passes 19/19 targeted
  tests, including baseline-drift and legacy-state seams.
  This result does not establish source truth, general provider precision,
  report improvement, reliability, or planner precision. The current generic
  adapter missed its candidate-value gate and remains disconnected. A future
  value study must use domain-specific retrieval on an unseen challenge before
  planner-trigger precision is worth measuring.
  Phase 4 now freezes eight previously unused academic/patent cases and adds
  source-native, one-request OpenAlex and claim-oriented Lens adapters. Offline
  dry-run validates 8/8 identities; the adapter/executor subset passes 71/71,
  including explicit provider-versus-client request identity, row-complete
  accounting, OpenAlex reported USD, Lens uninspectable cost, credential-safe
  tracebacks and BYOK key scrubbing. Hidden-retry and missing-row-accounting
  defects were each re-injected and made their seam tests fail.
  A separately pre-registered live-value harness now freezes the exact fixture
  and implementation hashes before credentials, output reservation or live
  provider adapters. It permits exactly one request per attempted case and
  commits each case journal before a later request. Human labels pass through a
  separate source lock and Schema v2 packet that exposes the frozen baseline
  context, rejects lineage or method-limit drift, distinguishes incomplete or
  ineligible review from a pass, and always keeps
  `production_connection_authorized=false`. The runner/review/adapter subset
  passes 50/50 zero-network tests. No live OpenAlex/Lens request has run, so
  provider compatibility, wrong-source rate, novel-evidence yield and report
  value are all not observed. Do not connect these adapters until a separately
  authorized frozen run and eligible Schema v2 human review meet both
  provider-specific value gates.
  Because the project owner does not want to configure OpenAlex or Lens keys,
  a narrower anonymous OpenAlex study now isolates D01-D04 without changing the
  frozen credentialed adapter. Its outbound seam removes a local non-secret
  sentinel before the actual request, refuses to run when `OPENALEX_API_KEY` is
  configured, caps execution at four one-request cases and USD 0.01 of
  provider-reported usage, and writes the same candidate/rejection review seam.
  The anonymous adapter/runner adds 15 focused tests; the 33/33 combined
  adapter/runner subset and full 1,569-test suite pass, including a re-injected
  key-leak defect at the outbound boundary. No anonymous live request has run,
  so compatibility and evidence value remain `not_evaluated`. A future live
  run still needs separate authorization for an exact merged revision.
  Keep `pipeline_worker.py` disconnected from the executor, adapters, live
  runner and review module.
  See `docs/results-2026-08-25-evidence-gap-tool-execution-phase2.md`,
  `docs/results-2026-08-25-evidence-gap-live-adapter-phase3-implementation.md`,
  `docs/errata-2026-08-25-evidence-gap-phase3-fixture-identity.md`,
  `docs/results-2026-08-25-evidence-gap-live-provider-phase3.md`, and
  `docs/results-2026-08-25-evidence-gap-human-review-packet-phase3.md`, and
  `docs/results-2026-08-26-evidence-gap-human-review-phase3.md`,
  `docs/prereg-2026-08-26-evidence-gap-domain-adapters-phase4.md`,
  `docs/results-2026-08-26-evidence-gap-domain-adapters-phase4-implementation.md`,
  `docs/prereg-2026-08-26-evidence-gap-domain-live-phase4.md`,
  `docs/results-2026-08-26-evidence-gap-domain-live-phase4-implementation.md`,
  `docs/prereg-2026-08-27-evidence-gap-anonymous-openalex.md`, and
  `docs/results-2026-08-27-evidence-gap-anonymous-openalex-implementation.md`.
- Regulator title recovery is integrated from one frozen development challenge,
  not a production-rate estimate. A zero-network census of 95 historical runs
  found only 3 in-scope rows across 2 unique ClinicalTrials.gov URLs. The
  candidate then matched 29/29 disclosed cases while preserving 23/23 clean
  official API titles byte for byte. It may derive only a neutral identifier
  label from an exact FDA 510(k) or ClinicalTrials.gov URL; unsupported broken
  official titles are rejected. One provider-backed post-integration canary
  completed for `$0.032665`, but no supported structural defect recurred, so
  the primary recovery criterion was `not_observed`. The run instead exposed a
  structurally plausible FDA title that lost its device entity and passed the
  frozen structural detector. Do not turn either observation into title truth,
  real-world precision/recall, report-quality improvement, or production
  recovery success. See
  `docs/prereg-2026-08-25-regulator-title-recovery-candidate.md` and
  `docs/results-2026-08-25-regulator-title-recovery-candidate.md`, plus
  `docs/prereg-2026-08-25-regulator-title-recovery-paid-canary.md` and
  `docs/results-2026-08-25-regulator-title-recovery-paid-canary.md`.
- The pre-registered offline process audit recovered 30/30 immutable children
  across ten frozen evidence collections and three post-commit boundaries. It
  skipped 90 committed task executions with zero duplicate task executions.
  One authorized Railway resume on 2026-08-24 then completed the paid workflow,
  but `identity.pipeline_revision` differed across PR #24 and PR #25, so the
  child correctly reported `cold_start` and reused zero nodes. This closes the
  post-fix paid startup path and fail-safe cross-revision invalidation only.
  A later pre-registered production canary reached a four-node checkpoint
  prefix and restarted the same Railway revision successfully. The source
  became failed with that prefix intact, but the only child admission was
  rejected before provider work by the three-operation daily cap. This is a
  non-pass, not paid same-revision reuse evidence; all source checkpoint
  `usage` fields were null, so partial tokens and cost are not inspectable.
  Do not turn these results into token reduction, cost reduction, latency,
  production-SLO, or exactly-once claims. See
  `docs/results-2026-08-23-checkpoint-fault-recovery.md` and
  `docs/results-2026-08-24-production-checkpoint-follow-up.md`, plus
  `docs/results-2026-08-24-paid-same-revision-recovery.md`.
  A separately pre-registered second-code follow-up then admitted a child on
  the same revision and reused the exact four-node prefix with byte-identical
  output hashes. The three reused evidence agents made zero new child
  requests. The child still failed: hydration restored `TaskOutput.raw` but
  not the typed `EvidenceReport`, while the Writer guardrail builds its source
  registry only from `TaskOutput.pydantic`. Both Writer attempts were rejected
  as having no validated evidence context. Paid same-revision reuse is now
  observed, but end-to-end paid recovery is not; source usage remains null, so
  total cost is also uninspectable. See
  `docs/results-2026-08-24-paid-same-revision-recovery-follow-up.md`.
  Recovery now reconstructs reused evidence JSON as `EvidenceReport` only
  after repeating schema and evidence-integrity validation. A real Writer
  guardrail seam test reaches the short-report check, and schema-invalid JSON
  is exposed as `corrupt` instead of being reused as raw-only context. A
  separately pre-registered post-fix Railway canary then passed: one immutable
  child reused the exact four-node prefix, the three evidence agents made zero
  child provider requests, Writer/Reviewer/Scorer completed, the report served
  at HTTP 200, and all seven checkpoints committed without error. Child usage
  was 88,780 tokens and `$0.033593`; interrupted-source usage remained null, so
  total cost is `not_inspectable`. This is one end-to-end provider-backed
  observation, not a recovery rate, SLO, exactly-once, latency, or general
  savings result. Raw Railway checkpoint files were not exported, so retained
  evidence supports runtime validation and public inspections rather than
  independent hash recomputation. See
  `docs/results-2026-08-24-paid-same-revision-recovery-post-fix.md`.
- The 30-run calibration benchmark still has no report-output evidence for
  Chinese, very short, or non-technical topics. A pre-registered zero-network
  public-boundary contract now distinguishes them: specific Chinese input is
  preserved, invalid short input is rejected before paid admission, and
  explicit non-research requests receive an overridable, high-precision
  confirmation. That tests admission and warning behavior, not report quality.
  Any future model-output cases must still declare "should succeed" versus
  "should fail gracefully" before execution and must not rewrite the existing
  calibration baseline.
- Code-package analysis (the other half of "upload a paper or a code package")
  is unbuilt.
- Patent topical relevance has one completed human label set over the frozen
  81-case audit. Benchmark-core direct relevance is 64/75 (85.3%) and usable
  relevance is 73/75 (97.3%). This is not an expert panel: there is no second
  reviewer or inter-rater agreement. The first frozen lexical candidate was
  compared and rejected: it falsely dropped 6 relevant patents and sent 36/81
  cases to review. Production filtering remains unchanged. The next method must
  be semantic/claim-scope with abstention and must face an unseen challenge.
- **The first report-level Reviewer audit is complete, but is not a general
  utility result.** Both evaluator forms completed 9/9 pairs and passed the
  frozen retention criterion. Exact agreement was 9/9 on overall preference,
  8/9 on citation support, 3/9 on decision usefulness, and 7/9 on harm. Neither
  evaluator opened external sources, so this measures report-internal support,
  not source truth. One evaluator's method declaration was corrected by the
  study owner after return; the result retains that form with explicit
  disclosure rather than presenting the provenance as cleaner than it is. See
  `docs/results-2026-08-23-reviewer-value-audit.md`. A stronger claim needs a
  larger independently recruited sample and preferably correction-level plans
  persisted by a future experiment.
- **The first user-utility result is complete, and it did not prove the
  six-stage advantage.** Five reviewers returned 20/20 eligible blinded
  judgments over two rounds. Both rounds preferred the full workflow 6:4 for
  decision usefulness, but both failed the pre-registered rule because the
  monolith was allowed at most two wins. Across both rounds the monolith won
  information gain 11:5, and topic-level agreement was only 2/10. The panel had
  one target user, one technical proxy, and three other reviewers; several
  returned enums required disclosed post-return coding. This is small proxy-user
  evidence, not adoption, ROI, accuracy, or proof that six agents are necessary.
  See docs/results-2026-08-23-user-utility-audit.md. The remaining product gap
  is a larger independent target-user sample and longitudinal adoption evidence.
- **The separate two-slot target-user decision pilot is complete, but it is
  descriptive rather than product validation.** It deliberately did not append
  new responses to the closed five-reviewer audit. Each recruited target user
  first recorded their role and baseline decision without seeing a report; only
  then did the coordinator materialize one frozen report and collect a
  post-report decision. The packet makes source checking, AI assistance,
  consent, and unusable observations explicit, and its public projection
  excludes free text. Both registered reviewers qualified as target users,
  selected topic 08 before report exposure, completed the same frozen report,
  consented to aggregate publication, and declared no substantive AI use in
  either stage. Both retained `DEFER` while confidence increased from 3/5 to
  4/5. Median usefulness and information gain were 3/5; actionability, evidence
  trust, and recommendation acceptance were 2/5. Both answered `MAYBE` to
  reuse and estimated 420 minutes of revision at the median; one reported a
  blocking error and one did not. Neither opened an external source, so source
  truth is `not_evaluated`. Their raw Stage 2 `no` values are retained
  privately and owner-coded to `NONE` with disclosure. These two observations
  do not establish adoption, ROI, accuracy, time savings, or population-level
  value. See `docs/prereg-2026-08-26-target-user-decision-pilot.md`,
  `docs/target-user-decision-pilot-guide.md`,
  `docs/errata-2026-08-26-target-user-pilot-form-enums-and-ai-timing.md`, and
  `docs/results-2026-08-26-target-user-decision-pilot.md`.
- **Decision Context has one completed production canary, and it failed its
  frozen all-mode criterion.** Seven optional bounded fields cross the browser,
  API, immutable RunSpec, checkpoint identity, Crew input, and public status.
  Code derives `orientation`, `decision_context_incomplete`, or
  `decision_support`, and clients cannot self-assert that mode. Three authorized
  root runs then completed sequentially for `$0.109342` / 266,648 tokens / 21
  requests, with exact status/progress gates, no child, zero evidence-gap tool
  calls, and no supplementary-search cost. Seven of ten report/execution
  criteria passed. `DC01` fell back to the Writer draft and committed 6/7
  checkpoints; `DC03` humanized the frozen mode token; and `DC02` supplied an
  unqualified commercial pass threshold that the incomplete context had not
  established. A dated operator follow-up later recovered DC01's persisted
  process log: correction 2 targeted text that occurred zero times. The narrow
  repair leaves that item unapplied, preserves other exact corrections, and
  exposes `quality_review.status=partial` rather than a false pass; ambiguous
  multi-match targets and all report-integrity failures remain blocking. This
  is a zero-network regression repair with no paid post-fix effectiveness
  observation. The frozen canary's public response did not expose its own
  `pipeline_revision`, so its per-run field remains `not_inspectable`. A later
  zero-network boundary repair persists the worker's immutable identity and
  carries it through both status endpoints for future runs; historical absence
  remains `null` rather than being backfilled from the current deployment. It
  does not retrospectively identify these three runs or add paid evidence. This
  is prompt-compliance and operational evidence only: source truth, decision
  correctness, usefulness, adoption, and time savings remain unmeasured. Do not
  call it a validated decision-quality result or rerun it as post-fix evidence.
  See
  `docs/prereg-2026-08-26-decision-context-report-contract.md`,
  `docs/results-2026-08-26-decision-context-report-contract.md`,
  `docs/prereg-2026-08-26-decision-context-paid-canary.md`,
  `docs/results-2026-08-26-decision-context-paid-canary.md`, and
  `docs/errata-2026-08-27-decision-context-reviewer-zero-target.md`, plus
  `docs/results-2026-08-27-public-pipeline-revision-seam.md`.
