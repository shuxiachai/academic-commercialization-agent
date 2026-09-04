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

Current state: 2049 tests (674 subtests), CI green on Linux + Windows × Python
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
| How are timeout and partial usage facts preserved? | `docs/runtime-terminal-integrity.md` — deadline ownership, immutable terminal records, monotonic usage snapshots, and complete/lower-bound/unavailable semantics |
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
  openalex_precision.py
                        conjunctive ACCEPT/ABSTAIN source gate; experimental only
  openalex_claim_scope.py
                        provider-assisted source gate; experimental only
  openalex_scope_link.py
                        role-structured same-segment gate; experimental only
  openalex_evidence_set.py
                        quote-grounded two-pass set selector; experimental only
  openalex_role_slot.py
                        candidate-local three-pass role-slot consensus; experimental only
  tools/qwen_role_slot_judge.py
                        strict one-request Qwen v6 judge; never production imported
  tools/evidence_search.py
                        one-request read-only adapter response contract
  tools/anonymous_openalex_search.py
                        key-free experimental wrapper; never production imported
  tools/openalex_claim_scope_search.py
                        abstract-filtered aboutness adapter; never production imported
  pipeline_worker.py    the subprocess one run executes in
  checkpoint_runtime.py
                        CrewAI hydration, task identity, and post-guardrail commits
  run_spec.py           immutable, non-secret input and decision-applicability
                        contract for child recovery
  checkpoints.py        atomic content-addressed storage and inspection states
  runtime_budget.py     API-worker provider deadlines and reserved closeout windows
  run_terminal.py       write-once terminal truth and usage-accounting state
api/                    FastAPI: runs registry, papers, access gate, models
web/                    vanilla JS client, no build step, strict CSP
ui/                     shared i18n, run-reader, and PDF-export utilities
tests/                  121 test modules plus conftest, organised by subject
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
evidence_gap_openalex_review.py
                        exact-run source lock plus Schema v2 human review
openalex_precision_unseen.py
                        frozen U01-U08 profile/identity preflight; zero-network
openalex_precision_live.py
                        disconnected unseen runner; CLI defaults to dry-run
openalex_precision_audit.py
                        label-blind frozen development replay; zero-network only
openalex_claim_scope_unseen.py
                        frozen V01-V08 claim-scope preflight; zero-network only
openalex_claim_scope_live.py
                        write-once V01-V08 runner; CLI defaults to dry-run
openalex_claim_scope_review.py
                        exact-run source lock plus Schema v2 human review
openalex_scope_link_unseen.py
                        frozen W01-W08 scope-link preflight; zero-network only
openalex_scope_link_live.py
                        write-once W01-W08 runner; CLI defaults to dry-run
openalex_scope_link_abstention_review.py
                        post-outcome W01-W08 label-blind diagnostic; zero-network
openalex_role_slot_unseen.py
                        frozen Y/Z role-slot identity preflight; zero-network only
openalex_role_slot_development.py
                        write-once Y runner; CLI defaults to zero-network dry-run
openalex_role_slot_failure_review.py
                        label-blind 64-row v6 failure diagnostic; zero-network
openalex_role_directed_unseen.py
                        frozen AA/AB two-lane v7 preflight; zero-network only
openalex_role_directed_live.py
                        write-once AA v7 runner; CLI defaults to zero-network
openalex_role_directed_review.py
                        exact AA source lock, lane-blind packet + five-gate review
openalex_role_gap_unseen.py
                        frozen AC/AD adaptive role-gap identities and router
openalex_role_gap_live.py
                        write-once AC adaptive runner; defaults to zero-network
openalex_role_gap_evaluation.py
                        write-once AD unseen runner; defaults to zero-network
openalex_role_gap_review.py
                        exact AC source lock, route/lane-blind Schema v2 review
openalex_role_gap_evaluation_review.py
                        exact AD source lock, route/lane-blind Schema v2 review
ops_report.py           what real runs actually did, vs what the benchmark covers
user_utility_audit.py   zero-network 3–5 reviewer packet + strict unblinding
checkpoint_fault_audit.py
                        pre-registered hard-kill/restart matrix and strict checker
```

Runs are subprocesses writing to `outputs/<run_id>/`; the API, the browser and
the CLI all observe the same run through those files rather than shared memory.
A completed, failed, cancelled or timed-out API run also has a write-once
`terminal.json`. Worker-owned exits commit it directly; the API commits it only
after an external stop. Monotonic per-node snapshots mean usage is reported as
`complete`, `lower_bound`, or `unavailable` rather than conflating an interrupted
request with zero cost. See `docs/runtime-terminal-integrity.md` before changing
this boundary.

A run URL is a read capability. Mutating a code-owned run additionally requires
its owner/admin code; an ownerless BYOK run has no second server-side identity.
Failed, cancelled, or timed-out runs with a retrieval checkpoint can start an
immutable child from the longest validated prefix. The child snapshots its
parent before launch, requires fresh credentials, and reports persistence and
reuse separately. See `docs/checkpoint-recovery.md` before changing this seam.

## Things that are known-open

- Blocking on uncited claims (above) — needs the detector tighter first.
- Qwen3.5 Plus is implemented as a logical `qwen` provider over CrewAI's
  pinned OpenAI-compatible transport. The adapter covers the official
  `DASHSCOPE_API_KEY`, default and operator-overridden endpoints, model
  selection, non-thinking JSON Object contract, OpenAI-shaped cached-token
  accounting, conservative peak-tier pricing, readiness, PDF extraction and
  browser/API BYOK seams. BYOK child environments use explicit empty
  sentinels, so CrewAI's import-time dotenv load cannot restore operator keys.
  A real CrewAI request-body seam confirms that `enable_thinking=false`
  reaches OpenAI SDK `extra_body`; putting it at top level was re-injected and
  made the test fail. One authorized single-topic paid canary later completed
  on merged revision `ff8732d`: all recorded role identities were exactly
  `qwen3.5-plus`; seven requests used 79,261 tokens with a conservative USD
  0.075657 estimate, all three retrieval domains retained 8 sources, and no
  retrieval domain failed. That observes one live transport/accounting path,
  not general report quality, stable latency/cost or DeepSeek equivalence.
  The run exposed two Qwen-specific internal-x10 score phrases at the client
  prose seam. Narrow normalization now covers only bounded rating forms and
  preserves percentages and counts; removing it made both regression tests
  fail before restoration. A separate invented-threshold and citation-
  entailment finding remains open and was not folded into this regex fix.
  The frozen DeepSeek evidence-set v5 provider contract is unchanged. See
  `docs/results-2026-08-30-qwen35-plus-provider-adapter-implementation.md` and
  `docs/results-2026-08-30-qwen35-plus-first-paid-canary.md`.
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
  passes 50/50 zero-network tests. No credentialed Phase 4 OpenAlex/Lens run has
  executed, so provider compatibility, wrong-source rate, novel-evidence yield and report
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
  adapter/runner subset passes, including a re-injected key-leak defect at the
  outbound boundary. A separately authorized run on merged revision `7bfe4ead`
  then completed D01-D04 with four single-attempt requests and USD 0.004 of
  provider-reported anonymous-budget usage. Twenty provider rows became seven
  provider rejections, four local rejections and nine quarantine-accepted
  review rows; every case retained at least one. Production/report connections
  remained false. A separate 15-test review boundary now locks the exact four
  aggregates, artifact index and four case journals; its Schema v2 packet
  exposes all four frozen baselines and all nine candidate identities. A
  re-injected baseline-drift defect made its seam test fail. The real blank
  packet preflight is `incomplete / not_evaluated`. A later return completed
  9/9 rows and declared every URL attempted. Its first declaration row was
  copied from an unrelated AI-assisted review, so the initial strict result was
  correctly `excluded_substantive_ai / not_evaluated`. The owner then relayed
  the human reviewer's corrected `generative_ai_use=NONE` declaration; both
  versions and an erratum are retained. The superseding result is
  `complete / fail`: accepted-case and novel-relevant coverage each passed at
  4/4, while four of nine candidates were directly irrelevant and the 44.4%
  wrong-source rate failed the frozen 5% maximum. A separately pre-registered
  precision-v2 method now uses code-owned conjunctive concept groups and only
  emits `ACCEPT` or `ABSTAIN`. Its label-blind replay checked every source and
  journal hash before opening labels, accepted all 5/5 relevant development
  rows, abstained all 4/4 known wrong rows and retained relevant evidence in
  4/4 cases. This is development-set qualification only. A source-locked
  U01-U08 harness is now implemented: its zero-network dry-run verifies the
  unchanged fixture, a separately locked pre-provider duplicate-phrase
  correction, all eight collection/plan/profile identities, implementation
  hashes, and the request/cost gates before adapter construction. Its 19/19
  focused seams pass, including a re-injected broad-acceptance defect at the
  review-output boundary. A separately authorized run on merged revision
  `9f84a9f` completed all eight one-attempt anonymous requests for USD 0.008 of
  provider-reported usage. Forty provider rows became nine provider
  rejections, eight legacy-quarantine rejections and 23 precision decisions;
  precision v2 accepted five candidates across only 3/8 cases. The frozen
  coverage gate requires at least 6/8, so no later human label could make the
  all-gates rule pass. The study stopped before review; source value remains
  `not_evaluated`, not zero-error. Do not rerun, tune on U01-U08 and call it
  validation, or connect either the original adapter or precision v2. A
  provider-assisted claim-scope v3 method is now implemented against a
  different, byte-frozen V01-V08 challenge. It requests only abstract-bearing
  Works and preserves OpenAlex topics/keywords as scored aboutness metadata.
  Provider metadata may bridge at most one required concept; at least one
  required concept must still match source text and one must match the title.
  Provider labels alone therefore cannot authorize a source. The zero-network
  preflight expands eight distinct collection/plan/profile/idempotency
  identities, and the new decision/adapter/preflight subset passes 16/16 tests.
  A deliberately wrong outbound filter made the transport-seam test fail before
  being reverted. A separate write-once live runner now locks the fixture and
  eight implementation hashes before output reservation, writes the complete
  manifest before adapter construction, commits each one-request case journal
  before a later request, distinguishes provider/accounting/cost states, records
  per-request latency, and emits only ACCEPT rows to a blank review boundary.
  Its 17/17 focused seams pass; moving manifest persistence after adapter
  construction made the request
  boundary test fail before the correct order was restored. A separately
  authorized run on merged revision `ad70d721` then completed all eight
  anonymous requests for USD 0.008 of provider-reported usage. Sixty-four
  provider rows became 13 ACCEPT and 51 ABSTAIN decisions; 7/8 cases retained
  at least one candidate. The exact manifest, aggregate, artifact index and
  eight case journals passed mechanical validation. This establishes the
  frozen harness's provider compatibility and bounded accounting only. A
  separate source-lock and Schema v2 review boundary now exposes every frozen
  baseline, profile, source abstract, aboutness signal and exact decision
  provenance without importing production code. Its 16/16 focused seams pass,
  including a re-injected valid-JSON byte-drift defect. One eligible human
  source review later completed 13/13 rows, declared no substantive generative
  AI use, and attempted every source. Twelve candidates were directly relevant
  and baseline-novel; one V08 row was directly irrelevant because its
  graphene/cellulose/melamine construction was outside the declared
  biomass-aerogel scope. Accepted-case and novel-relevant coverage both passed
  at 7/8, but the 1/13 wrong-source rate was 7.69%, above the frozen 5% maximum.
  The strict result is therefore `complete / fail`, and planner-trigger study
  eligibility remains false. The returned date `2026/8/27` was normalized to
  ISO `2026-08-27` only after preserving the raw declaration privately. Do not
  tune on or rerun V01-V08, connect v3, or advertise completed Tool Calling.
  A separately pre-registered scope-link v4 candidate now addresses that
  failure class without moving the provider threshold: required technology
  concepts, source-text-only scope concepts and source-text-only supporting
  concepts have distinct roles, and at least one exact required/scope pair
  must occur in the same title or abstract sentence. Provider metadata may
  still bridge at most one required group but cannot establish scope, support
  or a relation. The raw-byte-locked W01-W08 preflight expands eight unique
  collection/plan/profile/idempotency identities with zero sockets. Its 15/15
  focused seams pass; combining the whole abstract into one relation segment
  was re-injected and made the cross-sentence test fail before restoration.
  A separately pre-registered write-once live runner now locks the fixture and
  nine decision/transport dependency hashes before output reservation, records
  its observed self-hash without creating a recursive lock, persists the full
  manifest before adapter construction, and commits each one-attempt case
  journal before a later request. Every provider candidate or rejection reaches
  the aggregate CSV, with required/scope/support/link provenance kept distinct;
  only ACCEPT rows reach a blank review boundary. Its 17/17 runner seams pass,
  and dropping link evidence after a correct internal decision was re-injected
  and made the client-boundary test fail. The combined v4 subset passes 32/32.
  A separately authorized run on merged revision `678254d` completed all eight
  anonymous one-attempt requests for USD 0.008 of provider-reported usage. All
  64 candidates reached the v4 decision seam, but every candidate was
  `ABSTAIN` and 0/8 cases retained an accepted row, below the frozen 6/8
  coverage gate. The runner correctly emitted `mechanical_gate_failed`; no
  source lock or human-review packet was created, and source value remains
  `not_evaluated`. Sixty-three decisions record `missing_scope_link`, which is
  a deterministic trace observation rather than a source-relevance label.
  W01-W08 are now consumed evaluation cases: do not tune on them, rerun them
  and call the result validation, or connect v4.
  A separately pre-registered post-outcome diagnostic now locks the exact 64
  abstentions and emits a label-blind packet containing only the frozen
  baseline context and source text. The real packet has 64/64 rows across 8/8
  cases, exposes none of the v4 action or match-provenance fields, and its blank
  summary is incomplete / not_evaluated with zero metrics. Sixteen focused
  tests pass, including a re-injected decision-field leak and a Windows GBK
  stdout regression. One eligible human reviewer later completed 64/64 rows
  without substantive generative-AI use or external-source checks. The strict
  result is complete / evaluated as a diagnostic only: 28/64 rows were directly
  relevant from the frozen title and abstract, 36/64 were retrieval noise, all
  8/8 cases retained relevant and baseline-novel evidence, and v4 missed four
  of five human-inferred semantic links. This identifies both retrieval noise
  and lexical relation recall as contributors; it does not establish source
  truth or inter-rater agreement. It cannot rescue v4, validate v5, reopen
  W01-W08, or authorize production. See
  docs/prereg-2026-08-29-openalex-scope-link-v4-abstention-diagnostic.md and
  docs/results-2026-08-29-openalex-scope-link-v4-abstention-diagnostic-implementation.md,
  plus
  docs/results-2026-08-29-openalex-scope-link-v4-abstention-diagnostic-review.md.
  A separately pre-registered quote-grounded evidence-set v5 hypothesis uses
  that diagnostic only for development qualification. The originally frozen
  label-blind `deepseek-chat` judge must produce mechanically verified source
  quotes in two order-reversed passes, and a deterministic set-cover step may
  combine at most three complementary sources. W01-W08 remain consumed
  development evidence; raw-byte-locked X01-X08 are the unseen challenge. All
  provider rows require human review even after a mechanical failure. The v5
  zero-network kernel and X01-X08 preflight are implemented and pass 21/21
  focused tests. They mechanically verify both passes' quotes, fail closed on
  disagreement or malformed rows, select at most three sources, and validate
  that every computed role reaches the serialized audit boundary. Both
  protocol-mandated defects were re-injected and caught.
  A production-disconnected W01-W08 development runner now locks the exact
  source packet, source lock, completed human labels and reviewer declaration
  before parsing only the label-blind packet. Role descriptions are derived
  mechanically from the earlier frozen v4 source-text groups, not from labels.
  Its strict one-request DeepSeek adapter rejects redirects, retries, model or
  usage identity drift, and uninspectable cost. The runner writes its complete
  manifest before client construction, each response and usage before a later
  call, and each deterministic case decision before a later case. The focused
  runner/adapter suite now passes 16/16 tests. The first authorized execution
  on merged revision `5f6526b` made one potentially billable request and then
  stopped without retry because the returned model identity did not equal the
  frozen legacy alias. It is `partial / not_evaluated`: zero completed calls,
  cases and candidate decisions; its cost is uninspectable, not zero; and no
  raw semantic response was persisted. It made zero OpenAlex requests, parsed
  no human labels and remained disconnected from production.
  A separately frozen amendment now requests exact `deepseek-v4-flash` with
  thinking explicitly disabled, keeps exact model rejection, and persists
  only safe returned-model and usage observations when semantic output is
  rejected. Aggregate tokens and cost are checked against the call journals;
  one uninspectable potentially spending call makes the whole cost
  uninspectable. Conservative V4 Flash peak rates carry their own 2026-08-30
  basis date. The real zero-network preflight again verified 8/8 cases, 64/64
  candidate identities, 16 prompt identities and all implementation hashes.
  Removing `thinking.disabled` made the outbound seam test fail before the
  correct implementation was restored. No later paid request is authorized or
  has occurred. W01-W08 remain consumed development evidence, and this
  transport amendment does not reopen their semantic method or gates.
  A separately pre-registered Qwen profile is implemented without editing that
  historical DeepSeek contract. Its raw one-request adapter fixes exact
  `qwen3.5-plus`, top-level `enable_thinking=false`, JSON Object mode, nested
  cached-token accounting and the committed conservative price basis. The
  historical Qwen contract uses manifest/execution schema 3 and a 60-second
  timeout. Its real zero-network preflight verified 8/8 W cases, 64/64
  candidates and 16 prompt identities with no socket or model call. Removing
  the thinking field and the cross-provider journal check independently made
  their seam tests fail before restoration. A separately authorized run on
  merged revision `d9adfa4` then attempted two sequential Qwen calls. W01 pass
  1 completed in 41.405 seconds with 4,431 tokens and a locally reconstructed
  USD 0.006358 cost. Pass 2 exceeded 60 seconds and stopped without retry.
  Because that in-flight request may have spent without returning usage,
  aggregate cost is `uninspectable`, not USD 0.006358 or zero. The strict
  result remains `partial / not_evaluated`: zero cases and candidate decisions
  completed, none of the five development gates ran, and every production
  connection remained false.

  A later transport-only amendment is now implemented for fresh Qwen
  development runs. Schema 4 persists a bounded 120-second timeout in all 16
  request identities, the manifest, each journal and the execution. The
  adapter rejects persisted/actual timeout drift before transport and records
  safe monotonic elapsed time on failures. Historical schemas 2 and 3 remain
  readable with their original behavior. The bound is the adapter's
  pre-existing maximum, not a measured percentile or SLO. The real zero-network
  preflight again verified 8/8 cases, 64/64 candidates, 16/16 prompt/timeout
  identities and all dependency hashes with no socket or model call. Restoring
  only the default adapter argument to 60 seconds made the client-seam test
  fail with observed `[60.0]`; restoration returned it to green. The focused
  suite passes 26/26 and the full suite passes 1787 tests plus 657 subtests.
  At that implementation stage no later paid request had been authorized. The
  amendment alone did not
  complete or connect production Tool Calling. See
  `docs/prereg-2026-08-31-openalex-evidence-set-v5-qwen-provider-amendment.md`,
  `docs/results-2026-08-31-openalex-evidence-set-v5-qwen-provider-implementation.md`,
  `docs/results-2026-08-31-openalex-evidence-set-v5-qwen-development-timeout.md`,
  `docs/prereg-2026-08-31-openalex-evidence-set-v5-qwen-timeout-amendment.md`,
  and
  `docs/results-2026-08-31-openalex-evidence-set-v5-qwen-timeout-amendment-implementation.md`.

  A separately authorized run on exact merged revision `7a2d73e` then completed
  all 16 sequential `qwen3.5-plus` calls and all eight case decisions without
  retry or recovery. It recorded 74,874 tokens, zero cached tokens, USD
  0.113971 of known conservative cost, and 25.897-49.900-second observed
  request latency with a 29.680-second median. All 27 indexed artifact hashes,
  schema contracts, model identities and key-isolation checks passed; every
  production/report/planner connection remained false. Transport therefore
  passed, but the semantic method failed its first frozen gate: reversed-pass
  disposition agreement was 38/64 (59.375%) against the >=90% requirement,
  two passes were schema-invalid, the join emitted zero KEEP decisions, and all
  eight cases abstained. W01-W08 are consumed, X01-X08 must remain unopened,
  and v5 must not connect to production Tool Calling. Do not tune or replay the
  consumed set into a pass, lower the threshold, or describe a zero-network
  diagnostic label join as rescuing the conjunctive protocol. See
  `docs/results-2026-08-31-openalex-evidence-set-v5-qwen-schema4-development.md`.
  A separately frozen post-outcome diagnostic then joined all 64 persisted
  candidate decisions to the earlier human labels without network, model,
  retrieval or repair calls. Among 28 human-labelled relevant rows, 12 were
  exposed to a whole-batch invalid response, nine were stable abstentions,
  four had role-set instability, two had action instability and one failed a
  post-consensus rule; zero were stable KEEP. The two invalid batches had full
  row coverage but duplicate role IDs, while valid calls also proposed 17/56
  versus 8/56 KEEP rows by order position. This is a disclosed failure
  diagnostic, not validation or causality: it rejects both a schema-only and
  an order-only explanation, leaves v5 sealed, and does not open X01-X08 or
  production. See
  `docs/prereg-2026-08-31-openalex-evidence-set-v5-qwen-failure-diagnostic.md`
  and
  `docs/results-2026-08-31-openalex-evidence-set-v5-qwen-failure-diagnostic.md`.
  See docs/prereg-2026-08-29-openalex-evidence-set-v5.md,
  A separately pre-registered candidate-local role-slot consensus v6 starts from
  new Y01-Y08 development and Z01-Z08 unseen identities; W stays consumed and X
  stays unopened. The model no longer owns candidate actions or role IDs. It can
  only fill fixed positional `SUPPORTED`/`ABSTAIN` role slots with exact title-
  or-abstract quotes. Malformed candidate rows and slots are contained locally,
  three deterministic candidate orders require two mechanically verified
  observations per role, and Python alone derives candidate admission plus a
  maximum-three-source set cover.

  The production-disconnected Y development runner and exact
  `qwen3.5-plus` one-request adapter are now implemented. A global manifest
  freezes eight OpenAlex request identities, 24 judge-template identities and
  12 transitive implementation hashes before client construction. Because exact
  prompts depend on provider-returned source text, each provider journal and its
  derived three-request model plan are durable before Qwen construction or a
  model call. OpenAlex and Qwen have separate request ceilings, soft stops, cost
  states and write-once journals. No candidate means no model client; a paid
  malformed semantic object becomes an explicit unavailable pass without repair;
  any uninspectable potentially spending call cannot become zero cost. Every
  provider row, model request, candidate row and fixed role slot reaches the final
  serialized boundary.

  The combined v6 kernel/preflight/adapter/runner subset passes 39/39 tests; the
  new runner/adapter subset passes 16/16, and the full zero-network suite passes
  1851 tests plus 657 subtests. Moving manifest persistence after adapter
  construction and dropping Y08 only from the final aggregate were each
  re-injected and made their exact seam tests fail before restoration. The
  default CLI remains zero-network dry-run and `pipeline_worker.py` imports none
  of v6. See
  `docs/prereg-2026-09-01-openalex-role-slot-consensus-v6.md`,
  `docs/results-2026-09-01-openalex-role-slot-consensus-v6-offline.md`,
  `docs/prereg-2026-09-01-openalex-role-slot-consensus-v6-development-runner.md`,
  `docs/prereg-2026-09-01-openalex-role-slot-consensus-v6-runner-identity-clarification.md`
  and
  `docs/results-2026-09-01-openalex-role-slot-consensus-v6-development-runner-implementation.md`.

  A separately authorized Y run on merged revision `d23ffd5` completed 8/8
  anonymous OpenAlex requests and 21/24 exact `qwen3.5-plus` calls before the
  model soft stop. It recorded 64 candidates, 56/56 hash-valid artifacts, USD
  0.008 OpenAlex cost and USD 0.204363 Qwen cost. The serialized state is
  correctly `partial / model_soft_stop`: Y08 has a provider journal and model
  plan but no model call. This is already an irrecoverable v6 failure rather
  than a reason to buy three more calls. Even perfect Y08 outcomes could raise
  provisional unanimity only from 34/56 to 42/64 (65.625%), below 80%, and
  selected-case coverage only from 4/8 to 5/8, below 6/8. Y is consumed, Z stays
  unopened, and v6 is sealed. The original protocol still requires a label-
  blind review of all 64 provider candidates after mechanical failure; that
  review is diagnostic only and cannot rescue v6 or authorize production. See
  `docs/results-2026-09-01-openalex-role-slot-consensus-v6-development-live.md`.

  The separately pre-registered post-outcome v6 failure diagnostic is now
  implemented. Its diagnostic-only owner lock preserves the original
  `source_lock_readiness=not_ready`, verifies the four exact core hashes and
  all 56 indexed child artifacts, cross-checks the eight provider journals and
  eight case executions, and permits review only because the provider boundary
  is complete at 8/8 cases and 64/64 candidates. It exposes baseline context,
  code-owned role descriptions, titles and abstracts while hiding all model
  passes, consensus roles, candidate actions and selected sets. The real local
  blank packet was `incomplete / not_evaluated` with 0/64 completed rows,
  `metrics=null`, and no network or model call.

  Its focused suite passes 14/14. Removing the explicit
  `candidate_action` block and dropping the final candidate only from the
  labels CSV were each re-injected and made their client-boundary tests fail
  before restoration. One eligible human reviewer later completed 64/64 rows,
  declared no substantive generative-AI use and did not check external sources.
  Thirteen candidates were directly relevant and 51 were retrieval noise. Six
  of eight cases contained baseline-novel relevant evidence, but only Y04-Y06
  were human-coverable as complete role sets. Candidate admission was 9 TP,
  7 FP, 38 TN and 2 FN; role-level precision/recall were 86.92%/90.29%.
  Candidate-pool quality and missing role coverage therefore dominate the
  failure, while semantic consensus errors remain a secondary contributor.
  The diagnostic cannot rescue v6, open Z01-Z08, validate a successor or
  connect production. See
  `docs/prereg-2026-09-01-openalex-role-slot-v6-failure-diagnostic.md` and
  `docs/results-2026-09-01-openalex-role-slot-v6-failure-diagnostic-implementation.md`,
  plus
  `docs/results-2026-09-01-openalex-role-slot-v6-failure-diagnostic-review.md`.

  A separately pre-registered retrieval-first v7 now tests the bottleneck that
  the v6 human diagnostic actually measured. It freezes fresh AA01-AA08
  development and AB01-AB08 unseen cohorts, with one `technology_scope` and
  one `technology_evidence` OpenAlex query per case. Both queries must target
  all required roles; the first must target scope and the second supporting
  evidence. Each query is limited to one read-only request and six rows. No
  semantic model is permitted until the candidate portfolio passes frozen
  relevance, role-coverability, pool-precision and second-lane incremental-value
  gates. Z remains unopened under v6 and is not reused.

  The raw-byte-locked zero-network preflight is now implemented. It expands
  8/8 AA cases, 16/16 unique call identities and 16/16 unique lane-contract
  identities, exposes every query and target role at the serialized boundary,
  and advertises zero model calls and no live authority. One AB05 query was
  corrected before implementation or any request after a scope audit showed
  that a weak token had created a formal rather than meaningful overlap; the
  original commit and erratum remain visible. The focused suite passes 10/10
  and the full suite passes 1878 tests plus 657 subtests. Dropping every second
  lane only at serialization was re-injected and made the boundary test fail
  before restoration. No OpenAlex request or human review has occurred, so AA
  remains unconsumed, AB remains unopened, and candidate value is
  `not_evaluated`. See
  `docs/prereg-2026-09-01-openalex-role-directed-retrieval-v7.md`,
  `docs/errata-2026-09-01-openalex-role-directed-v7-ab05-query.md`, and
  `docs/results-2026-09-01-openalex-role-directed-retrieval-v7-offline.md`.

  The separately pre-registered write-once AA runner has now completed its one
  permitted development execution on exact merged revision `2a61c32`. Sixteen
  of sixteen one-attempt anonymous OpenAlex requests and all eight portfolios
  committed for USD 0.016 of provider-reported cost. All 96 provider rows (84
  candidates and 12 rejections) reached the aggregate boundary, producing 79
  DOI/URL-deduplicated blank-review candidates. Independent recomputation found
  zero mismatches across 29 indexed files; all request IDs, idempotency keys,
  and costs were inspectable. No model or production/report/Planner/recovery
  connection occurred. After every artifact committed, strict Windows GBK
  stdout failed on U+2022 in one title. AA was not rerun: a zero-network test
  reproduced the original exception, and only the stdout projection now uses
  reversible ASCII JSON escapes while authoritative UTF-8 artifacts remain
  unchanged. AA is consumed and AB is unopened.

  The separately pre-registered zero-network review boundary binds the 29
  indexed source files plus the artifact index, independently reconstructs all
  16 lane journals, eight portfolios, 96 provider rows and 79 unique
  candidates, and emits a lane-blind Schema v2 packet. The focused suite passes
  15/15 and the full suite passes 1894 tests plus 657 subtests. Leaking lane
  provenance and calculating scope-only coverage from the two-lane union were
  each re-injected and made their seam test fail before restoration.

  One eligible human return has now completed all 79 rows. Its initial
  declaration incorrectly recorded `MOST_OR_ALL`, so the strict first intake
  was correctly `excluded_substantive_ai / not_evaluated`. The owner later
  relayed that the judgments were human and that the field was a filling error;
  the original declaration, excluded result, correction record and corrected
  declaration are retained privately. No label, role or note changed. The
  superseding strict result is `complete / fail`: relevant-novel coverage
  passed at 8/8, candidate-pool precision passed at 37/79 (46.84%), and unique
  evidence-lane value passed at 7/8; role coverability failed at 5/8 and the
  union-minus-scope coverability gain failed at 0 rather than at least +2.
  AA is sealed, AB must remain unopened, and production remains disconnected.
  Do not rerun or tune on AA, open AB, or connect v7. A future successor needs
  a new pre-registration and fresh development/unseen cohorts. See
  `docs/prereg-2026-09-01-openalex-role-directed-retrieval-v7-live-runner.md`,
  `docs/results-2026-09-02-openalex-role-directed-retrieval-v7-live-runner.md`,
  `docs/results-2026-09-02-openalex-role-directed-retrieval-v7-development-live.md`,
  `docs/prereg-2026-09-02-openalex-role-directed-v7-human-review.md`,
  `docs/results-2026-09-02-openalex-role-directed-v7-human-review-boundary.md`,
  and `docs/results-2026-09-02-openalex-role-directed-v7-human-review.md`.


  A separately pre-registered adaptive role-gap closure v8 now targets the
  measured v7 failure instead of adding a third fixed broad query. Fresh
  AC01-AC08 development and AD01-AD08 unseen cohorts each freeze one anchor
  query, five candidate-local role-signal portfolios, one closure priority and
  five mutually exclusive role-bound closure queries. The router may select
  only the first mechanically missing role in frozen priority order, or emit
  `abstain_no_mechanical_role_gap`; a future case can execute at most one
  anchor and one closure request, with no model-written query.

  The raw-byte-locked zero-network preflight is implemented and passes 15/15
  focused tests. It exposes 48 potential call identities per cohort while
  capping future execution at 16 requests and zero model calls. The first run
  stopped because six closure queries failed the existing two-token topic-
  scope authorization through lexical inflection. The authorization rule was
  retained; a narrow pre-provider erratum appended one existing topic token to
  each query and preserves both fixture hashes. Cross-candidate phrase pooling
  and dropping one valid closure only at serialization were separately
  re-injected and made their seam tests fail before restoration.

  The separately pre-registered, production-disconnected AC write-once runner
  is implemented. Its default CLI path remains zero-network. It locks the
  fixture and six behavior dependencies before output reservation, persists
  the complete manifest before adapter construction, the anchor journal before
  routing, the full five-observation route before an optional closure, and the
  case portfolio before the next case. Both eight-anchor no-gap completion and
  sixteen-request closure completion pass in injected tests. Every provider
  row, rejection, route decision, selected closure, occurrence, deduplication
  owner, cost and latency reaches content-addressed aggregate and blank-review
  boundaries. The runner/review seams pass 19/19 focused tests, and the full
  suite passes 1928 tests plus 657 subtests. Moving manifest persistence after
  adapter construction and dropping one route only at serialization were
  separately re-injected and made their tests fail before restoration.

  The owner then separately authorized AC execution on exact merged revision
  `59b5870614d23c0d9c61e7e398fa363026b6a528` and fixture
  `0be98f249bfd1eaf891cd3c20903b9d6ae4cd2d6431282ee32e82298a2d8ecc7`.
  The default dry-run passed before the live flag was supplied. The live run
  completed 15/15 single-attempt anonymous OpenAlex requests: eight anchors,
  seven role closures and one AC08 no-gap abstention. All 8/8 portfolios were
  committed. Ninety accounted provider rows became 72 abstract-bearing
  candidates plus 18 no-abstract schema rejections and 64 unique candidates
  after deduplication. Provider-reported anonymous-budget usage was USD 0.015.
  Independent SHA-256 recomputation found 0/38 indexed source-file mismatches.
  The mechanical state is `eligible_for_source_lock`.

  A separate zero-network source lock and route/lane-blind Schema v2 human-
  review boundary now bind that exact artifact index. The validator rebuilds
  all 39 files, 15 request journals, eight route journals, eight portfolios and
  64 deduplicated candidates before emitting review material. The blank packet
  is `incomplete / not_evaluated`: 0/64 labels, no hidden-provenance join and
  no scored gate. Its source-lock SHA-256 is
  `237a9b901d055a4d325316042e7ae343c465659e1428d209be35d4f4e0607659`.
  Fifteen focused seams and the 1943-test / 657-subtest suite pass; injecting a
  route decision into the blind projection made the boundary test fail.

  One independent reviewer later completed all 64 title-and-abstract rows. The
  first declaration recorded `MOST_OR_ALL`, so the unchanged strict intake
  correctly returned `excluded_substantive_ai / not_evaluated` without joining
  hidden provenance or scoring a gate. The owner then relayed that the
  judgments were human-completed and the AI-use field was a filling error. The
  original declaration and excluded result remain byte-preserved privately;
  only that field was corrected to `NONE`, with every label, role, note and
  other declaration field unchanged.

  The superseding strict result is `complete / pass`. All six frozen gates
  passed: relevant-novel evidence appeared in 8/8 cases; 31/64 candidates were
  directly relevant (48.44%); 7/8 routing decisions were human-correct; 5/7
  closure cases added selected-role value; union coverability reached 6/8; and
  coverability gained three cases over the anchor's 3/8. AC02 and AC07 remained
  incomplete, and AC06 was the one human-incorrect route. The review used one
  reviewer, titles and abstracts only, no external-source checks, and an owner-
  relayed rather than separately signed declaration correction.

  AC is consumed. A separate AD01-AD08 unseen-evaluation protocol was frozen on
  merged base `9121bcc`, before an AD-capable runner or any AD provider response.
  It preserves the same six conjunctive gates, eight-to-sixteen sequential
  anonymous OpenAlex request bound and USD 0.02 maximum soft stop; retries,
  query rewriting, models, recovery and production imports remain forbidden.

  The separately named AD-only runner is now implemented on base `243d23f` and
  zero-network verified. It accepts only `unseen`, validates the raw fixture,
  AD identities, contracts and behavior dependencies before output reservation
  or adapter construction, persists the complete manifest first, and carries
  provider rows, routes, portfolios, costs, latency and candidate lineage to
  content-addressed client artifacts. Its dry run exposes eight AD cases,
  forty-eight potential call identities, a sixteen-request maximum and zero
  model or network calls. The 21/21 focused suite and complete 1964-test /
  657-subtest suite pass. Allowing `development` and dropping a route only at
  serialization were each re-injected; both made their seam tests fail before
  restoration. Existing AC code and artifacts were not changed.

  A separately authorized run on merged revision `b54fa22` then completed all
  eight AD cases. It made fifteen single-attempt anonymous OpenAlex requests:
  eight anchors and seven selected closures, with AD03 the only explicit
  abstention. Provider-reported usage was USD 0.015. Ninety provider rows
  became 73 abstract-bearing candidates, 17 schema rejections and 67
  DOI/OpenAlex-deduplicated review rows. All 38 indexed files recomputed to the
  recorded hashes. There were zero model calls, retries, redirects, recovery
  attempts or production/report/planner connections. This is a mechanical
  provider-execution pass, not evidence that v8 generalized.

  The AD human-review protocol was separately frozen after that run and before
  its review implementation or any human label. A dedicated AD-only review
  module now binds the exact artifact-index digest, rebuilds every journal,
  portfolio and aggregate row, and emits all 67 candidates plus eight frozen
  contexts through a route- and lane-blind Schema v2 packet. Its private source
  lock is `ac4aa302...`; the packet manifest is `f017b1d9...`. The blank result
  is `incomplete / not_evaluated`, with zero completed labels, no route join and
  no gate metrics. Sixteen focused tests pass. Replacing the explicit AD
  closure set with the AC positional `CASE_IDS[:-1]` assumption and leaking a
  route decision into the blind projection were each re-injected and made the
  intended seam test fail before restoration. The full suite passes 1980 tests
  plus 657 subtests; Ruff, narrow Pylint and Chromium smoke are green locally.

  One human reviewer then completed 67/67 rows. The first declaration recorded
  `MOST_OR_ALL`, so the strict first intake correctly preserved
  `excluded_substantive_ai / not_evaluated` without joining hidden provenance.
  The owner confirmed the judgments were human-completed and that no generative
  AI was used; only that field was corrected to `NONE`. The unchanged labels
  still contained one explicit `UNVERIFIABLE` row, so the second intake
  correctly remained `not_inspectable / not_evaluated`. The reviewer then
  inspected the publisher full text for that single row, revised its label,
  visible roles and note, and updated the declaration to
  `external_sources_checked=SOME`. The other 66 judgments were unchanged.

  The final eligible result is `complete / fail`. Relevant novel evidence
  covered 8/8 cases, candidate precision was 33/67 (49.25%), and union role
  coverability reached 6/8. Human-correct routing was only 5/8, selected-role
  closure value only 2/7, and union coverability gained only +1 case over the
  anchor (6 versus 5). Three of six conjunctive gates therefore failed. AD is
  consumed, adaptive role-gap v8 is sealed, and planner-trigger, report and
  production Tool Calling connections remain false.

  Do not tune on or rerun AC or AD as validation, infer source value from the
  blank packet, or connect v8 to the planner or production. See
  `docs/prereg-2026-09-02-openalex-adaptive-role-gap-closure-v8.md`,
  `docs/errata-2026-09-02-openalex-role-gap-v8-query-scope.md`,
  `docs/results-2026-09-02-openalex-adaptive-role-gap-closure-v8-offline.md`,
  `docs/prereg-2026-09-02-openalex-adaptive-role-gap-v8-live-runner.md`,
  `docs/results-2026-09-02-openalex-adaptive-role-gap-v8-live-runner.md`,
  `docs/results-2026-09-02-openalex-adaptive-role-gap-v8-ac-live.md`,
  `docs/prereg-2026-09-03-openalex-adaptive-role-gap-v8-human-review.md`,
  `docs/results-2026-09-03-openalex-adaptive-role-gap-v8-human-review-boundary.md`,
  `docs/results-2026-09-03-openalex-adaptive-role-gap-v8-human-review.md`,
  `docs/prereg-2026-09-03-openalex-adaptive-role-gap-v8-ad-evaluation.md`,
  `docs/results-2026-09-03-openalex-adaptive-role-gap-v8-ad-runner-implementation.md`,
  `docs/results-2026-09-03-openalex-adaptive-role-gap-v8-ad-live.md`,
  `docs/prereg-2026-09-03-openalex-adaptive-role-gap-v8-ad-human-review.md`,
  `docs/results-2026-09-03-openalex-adaptive-role-gap-v8-ad-human-review-boundary.md`,
  and
  `docs/results-2026-09-03-openalex-adaptive-role-gap-v8-ad-human-review.md`.
  docs/results-2026-08-29-openalex-evidence-set-v5-implementation.md, and
  docs/results-2026-08-29-openalex-evidence-set-v5-development-runner-implementation.md,
  plus
  docs/results-2026-08-30-openalex-evidence-set-v5-development-provider-drift.md,
  docs/prereg-2026-08-30-openalex-evidence-set-v5-provider-contract-amendment.md,
  and
  docs/results-2026-08-30-openalex-evidence-set-v5-provider-contract-amendment-implementation.md.
  Keep
  `pipeline_worker.py` disconnected from the executor, adapters,
  v2/v3/v4/v5/v6/v7/v8
  candidates, live runners and review modules.
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
  `docs/prereg-2026-08-27-evidence-gap-anonymous-openalex.md`,
  `docs/results-2026-08-27-evidence-gap-anonymous-openalex-implementation.md`,
  `docs/results-2026-08-27-evidence-gap-anonymous-openalex-live.md`,
  `docs/results-2026-08-27-evidence-gap-anonymous-openalex-review-implementation.md`,
  `docs/results-2026-08-27-evidence-gap-anonymous-openalex-review.md`,
  `docs/errata-2026-08-27-anonymous-openalex-review-declaration.md`,
  `docs/prereg-2026-08-27-openalex-precision-v2.md`,
  `docs/results-2026-08-27-openalex-precision-v2-development.md`,
  `docs/errata-2026-08-27-openalex-precision-v2-unseen-fixture.md`,
  `docs/results-2026-08-27-openalex-precision-v2-unseen-implementation.md`, and
  `docs/results-2026-08-27-openalex-precision-v2-unseen-live.md`, plus
  `docs/prereg-2026-08-27-openalex-claim-scope-v3.md` and
  `docs/results-2026-08-27-openalex-claim-scope-v3-implementation.md`, plus
  `docs/results-2026-08-27-openalex-claim-scope-v3-live-implementation.md`,
  `docs/results-2026-08-27-openalex-claim-scope-v3-live.md`, and
  `docs/results-2026-08-27-openalex-claim-scope-v3-review-implementation.md`,
  plus `docs/results-2026-08-27-openalex-claim-scope-v3-review.md`, and
  `docs/prereg-2026-08-27-openalex-scope-link-v4.md` plus
  `docs/results-2026-08-27-openalex-scope-link-v4-implementation.md`, plus
  `docs/prereg-2026-08-28-openalex-scope-link-v4-live.md` and
  `docs/results-2026-08-28-openalex-scope-link-v4-live-implementation.md`, plus
  `docs/results-2026-08-29-openalex-scope-link-v4-live.md`.
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

  A subsequent zero-network P1 change closes the two observed delivery seams
  without rerunning that consumed canary. Decision Context now records optional
  success criteria separately from an explicit owner-approval declaration and
  derives `not_established`, `user_supplied_unapproved`, or `owner_approved`.
  The authority state changes checkpoint identity, while the public gate omits
  the criteria text. A localized code-owned block writes the exact mode,
  GO/NO_GO applicability and threshold provenance into delivered Markdown.

  A separate non-blocking audit now checks only pre-measured narrow decision-
  threshold phrases and electrolyte-family citation contradictions. The broad
  vocabulary that matched legitimate facts in 9/30 baseline reports remains
  excluded. The 30-report baseline has zero threshold findings and zero
  mismatches among 23 checkable segments; the known Qwen sulfide/oxide example
  produces the intended finding. Uncheckable and non-English content is
  explicitly partial or unavailable, never a pass. Full findings persist in
  `report_audit.json`; bounded state reaches both APIs and the browser. Defect
  reinjection caught both a dropped applicability block and a swallowed source-
  scope mismatch. This remains advisory and does not change scoring, block a
  report, or connect production Tool Calling.

  A separately pre-registered one-root post-fix paid canary froze the earlier
  sulfide-electrolyte topic with a complete synthetic Decision Context and
  explicitly owner-approved success criteria. One authorized root then ran on
  exact deployed revision `46b93a3c...` and reached the Reviewer after
  retaining 7/8/8 sources and committing retrieval, all three evidence nodes
  and Writer. The API's 30-minute watchdog terminated it before Reviewer or
  Scorer completion. No child, Planner call, supplementary search or second
  root occurred. Decision-gate identity, authority and raw-criteria privacy
  agreed across both public endpoints, but the final report, report audit and
  usage ledger were unavailable. The frozen count is 2/8 pass, 2 fail, 3
  not-inspectable and 1 not-observed; generated content is not inspectable.
  The run also exposed that timeout duration is derived from the stale final
  status write (`1404` seconds) rather than the later watchdog marker, and that
  an external kill bypasses the worker's final usage snapshot. Do not rerun or
  resume this consumed canary, call the P1 production seam validated, infer
  zero cost, or raise the timeout alone. Fix terminal timing/accounting and
  stage-budget behavior under a separate measured change first.
  That P0 change is now implemented and zero-network validated: API workers
  receive one hard-deadline identity, provider requests are bounded at 150
  seconds with hidden SDK retries disabled, Reviewer reserves 240 seconds for
  the existing validated-Writer fallback, and other paid work reserves 60
  seconds for finalization. Every completed-node callback persists monotonic
  usage; externally stopped runs commit an immutable terminal record whose
  accounting state is explicitly `lower_bound` or `unavailable`. Both public
  endpoints and the browser expose the distinction. Three defect reinjections
  proved the provider-call, callback-to-disk and disk-to-client seams. This does
  not establish production success or exact interrupted-request billing.
  A new one-root production canary is now separately pre-registered against a
  previously unused handheld-ultrasound topic. It freezes the deployed runtime
  policy, one orientation request, USD 0.10 soft stop, zero operator retries,
  resumes, cancellations, Planner calls or supplementary searches, and
  outcome-specific semantics that cannot promote a timeout or unavailable seam
  to a pass. The protocol itself authorizes zero provider calls; execution still
  requires a fresh user authorization naming the merged deployed revision. See
  `docs/runtime-terminal-integrity.md` and
  `docs/results-2026-09-04-runtime-terminal-integrity-implementation.md`, plus
  `docs/prereg-2026-09-04-runtime-terminal-integrity-paid-canary.md`.

  See
  `docs/prereg-2026-08-26-decision-context-report-contract.md`,
  `docs/results-2026-08-26-decision-context-report-contract.md`,
  `docs/prereg-2026-08-26-decision-context-paid-canary.md`,
  `docs/results-2026-08-26-decision-context-paid-canary.md`, and
  `docs/errata-2026-08-27-decision-context-reviewer-zero-target.md`, plus
  `docs/results-2026-08-27-public-pipeline-revision-seam.md`,
  `docs/prereg-2026-09-03-report-decision-and-citation-seams.md`, and
  `docs/results-2026-09-03-report-decision-and-citation-seams.md`, plus
  `docs/prereg-2026-09-04-report-decision-seams-paid-canary.md`, and
  `docs/results-2026-09-04-report-decision-seams-paid-canary.md`.
