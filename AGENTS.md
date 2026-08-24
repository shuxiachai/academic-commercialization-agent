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

Current state: 1332 tests (564 subtests), CI green on Linux + Windows × Python
3.11/3.12, deployed on Railway.

## Commands

```bash
uv run pytest -q                       # the whole suite; ~24s on Windows, zero network
uv run --with ruff ruff check .        # CI uses latest ruff, the local pin is older
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
| Full decision history, first person | `notes/简历项目说明.md` — **a separate private repo** (`shuxiachai/academic-agent-notes`), gitignored here. 4,217 lines, 58 write-ups. Ask the user for access if you need it |

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
  source_pipeline.py    ~2,900 lines, retrieval for all three domains
  evidence.py           models, guardrails, scoring rubric
  pipeline_worker.py    the subprocess one run executes in
  checkpoint_runtime.py
                        CrewAI hydration, task identity, and post-guardrail commits
  run_spec.py           immutable, non-secret input contract for child recovery
  checkpoints.py        atomic content-addressed storage and inspection states
api/                    FastAPI: runs registry, papers, access gate, models
web/                    vanilla JS client, no build step, strict CSP
ui/                     shared i18n, run-reader, and PDF-export utilities
tests/                  63 test modules plus conftest, organised by subject
benchmark.py            paid batch runs; --fixtures replays frozen evidence
patent_relevance_candidate.py
                        offline frozen candidate screen; never production filtering
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
- The pre-registered offline process audit recovered 30/30 immutable children
  across ten frozen evidence collections and three post-commit boundaries. It
  skipped 90 committed task executions with zero duplicate task executions.
  This closes the offline mechanics question only: there is still no paid
  provider or production Railway fault-injection result. Do not turn it into a
  token reduction, cost reduction, latency, production-SLO, or exactly-once
  claim. See `docs/results-2026-08-23-checkpoint-fault-recovery.md`.
- The benchmark's input distribution misses the shapes real traffic has:
  Chinese topics, very short inputs, non-technical topics. Before adding them,
  decide whether each is a "should succeed" or a "should fail gracefully" case;
  the assertions differ completely.
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
  See docs/results-2026-08-23-user-utility-audit.md. The largest remaining gap
  is independent utility evidence from more actual target users.
