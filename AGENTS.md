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

Baseline at `0fdaa76` (2026-09-05 documentation audit): 2071 tests and 678
subtests. CI covers Linux + Windows × Python 3.11/3.12; Railway hosts the demo.
See [current evidence status](docs/evidence-status.md) for qualified results,
not an ever-growing chronological paragraph here.

## Commands

```bash
uv run pytest -q                       # the whole suite; zero provider calls
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
- **No bare `except Exception`** without a `# noqa: BLE001` and a reason.
  This is a review convention; the current Ruff selection does not enable
  BLE001. Do not assume a green lint job enforces it.
- **CI also runs pylint, narrowly,** for bad exception order, unreachable code,
  used-before-assignment and undefined variables. The exception-order check
  caught `HTTPError` placed after `URLError`: dead code that retried auth
  failures as transient. Use the exact command in `CONTRIBUTING.md`.
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
| Full decision history, first person | `notes/简历项目说明.md` — **a separate private repo** (`shuxiachai/academic-agent-notes`), gitignored here. Numbered postmortems and supporting decision records; historical entries retain their dates. Ask the user for access if you need it |

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

## Layout and boundary-specific reading

| Change surface | Start here | Read before changing |
|---|---|---|
| Production entry points | `api/`, `web/`, `src/academic_agent/main.py` | [Operating guide](docs/operating-guide.md), `tests/test_api.py`, browser-contract tests |
| Retrieval and title recovery | `source_pipeline.py`, `source_clients.py`, `source_title_recovery.py` under `src/academic_agent/` | Nearby precision-first comments, frozen baseline, [ultrasound applicability result](docs/results-2026-09-04-handheld-ultrasound-authority-applicability.md) |
| CrewAI and structured output | `crew.py`, `config/agents.yaml`, `config/tasks.yaml`, `evidence.py` | [CrewAI reference](docs/crewai-reference.md), unchanged scoring baseline |
| Decision applicability and citation checks | `report_applicability.py`, `report_audit.py`, `claim_grounding.py`, `consistency.py` | [Report seams](docs/results-2026-09-03-report-decision-and-citation-seams.md), [threshold precision result](docs/results-2026-09-04-decision-threshold-warning-precision.md) |
| Checkpoint/recovery | `checkpoint_runtime.py`, `checkpoints.py`, `run_spec.py` | [Recovery design](docs/checkpoint-recovery.md) |
| Timeouts, terminal state and usage | `pipeline_worker.py`, `runtime_budget.py`, `run_terminal.py`, `token_usage.py`, `api/runs.py`, `ui/run_reader.py` | [Terminal integrity](docs/runtime-terminal-integrity.md) |
| LLM identity and BYOK | `llm_config.py`, `pdf_extractor.py`, API schemas and browser provider controls | [Qwen adapter](docs/results-2026-08-30-qwen35-plus-provider-adapter-implementation.md), [first live canary](docs/results-2026-08-30-qwen35-plus-first-paid-canary.md) |
| Trace export | `src/academic_agent/observability/` | [Observability contract](docs/observability.md) |
| Tool Calling experiments | `evidence_gap*.py`, `openalex_*.py`, `src/academic_agent/tools/` | [Version ledger](docs/evidence-status.md#tool-calling-experiments), exact experiment pre-registration |
| Offline evidence and user studies | `outputs/benchmark/`, `benchmark_check.py`, `ops_report.py`, `user_utility_audit.py`, `checkpoint_fault_audit.py` | [Experiment index](docs/experiment-index.md), source locks and method declarations |
| Public documentation | `README.md`, `README.zh-CN.md`, `docs/` | `tests/test_public_docs.py`; both languages must retain the full executable benchmark contract |

Unless qualified, the Python module names in this table are under
`src/academic_agent/`. The dated experiment documents and their code comments
carry the detailed lineage, not this index.

## Runtime boundaries that must survive edits

Runs are subprocesses writing to `outputs/<run_id>/`. API, browser and CLI
read those shared artifacts. A completed, failed, cancelled or timed-out API run
also has write-once `terminal.json`: workers commit their own exits; the API
commits only after an external stop. Monotonic per-node snapshots distinguish
`complete`, `lower_bound` and `unavailable` usage. An interrupted request is
not free, and a normal-completion canary does not validate timeout/fallback.

A run URL is a read capability. Code-owned mutation requires owner/admin code;
ownerless BYOK has no second server-side identity. Recovery requires fresh
credentials and creates an immutable child from the longest validated prefix,
snapshotting its parent before launch. Persistence and reuse are separate
states. Local committed-node reuse is not provider-level exactly-once delivery.

The shared run/PDF admission and persistent daily paid-operation ledger protect
a single process. Do not increase replica/worker counts without redesigning
ownership, quota transactions and persistence. Do not infer permission to
restart Railway, invoke a paid canary or publish private run links.

## Tool Calling: do not turn experimental code into production by accident

- Production is phase-1 **zero-call shadow mode**. Phase-2 execution, provider
  adapters and later OpenAlex/Qwen selectors are production-disconnected.
- Adaptive Role-Gap v8 passed AC development and **failed AD unseen evaluation**:
  only three of six gates passed. Routing was 5/8, closure-role value 2/7 and
  coverability gain +1. See the [final result and provenance limits](docs/results-2026-09-03-openalex-adaptive-role-gap-v8-ad-human-review.md).
- AC/AD are consumed and v8 is sealed. Earlier D/U/V/W/Y/AA cohorts are also
  consumed in the roles described by their protocols. Do not open reserved
  cohorts, tune consumed evaluation labels and call it validation, or rewrite
  historical failures as passes.
- A new method needs a new pre-registration, fresh development/evaluation
  cohorts and separate live authorization. Source truth, planner precision,
  report improvement and production authorization are separate gates.
- Do not relocate experimental modules as a cosmetic cleanup: frozen runners
  bind fixture bytes, source files and dependency hashes. A path or hash change
  can invalidate a paid protocol before it makes a request.
- Raw reviewer files stay private. A declaration correction must retain the
  original, the amendment and the limits of its provenance. Never infer a
  missing judgment merely to complete a denominator.

## Known-open work, not implied permission to implement it

1. Qualitative citation entailment and invented decision thresholds: narrow
   non-blocking checks exist, but general correctness is unestablished. The
   110-report threshold replay removed seven known false positives and retained
   six qualifying candidates; it is not an independent precision estimate.
2. Decision value: the five-person utility study failed its success rule and
   the two-target-user pilot did not establish adoption. Both studies are
   closed; new participants belong in a new protocol, not their old denominator.
3. Metadata reads: the core status/progress/history/browser fault seam now
   distinguishes absent and unreadable records; see the
   [fault verification](docs/results-2026-09-05-runtime-metadata-integrity.md).
   Nine display-facing audit-summary fields have field-local isolation; see
   the [nested contract and limits](docs/results-2026-09-05-nested-audit-metadata-integrity.md).
   Other nested payloads, detailed audit artifacts and unused auxiliary readers
   are not comprehensively validated; this is not a main-pipeline outage.
4. Input distribution: language/shape admission is tested, but the 30-run
   benchmark does not validate Chinese, very short or non-technical requests.
5. Scale and long-term operations: one replica, no distributed ownership or
   repeated production SLO measurement. Recovery and RTI02 each have explicitly
   bounded live observations.
6. Code-package analysis and longitudinal report comparison remain unbuilt.
   Add them only against a concrete task, not a technology-stack checklist.

Current provider transport: logical `qwen` over the pinned OpenAI-compatible
transport, exact default `qwen3.5-plus`, non-thinking JSON output. Five pipeline
nodes require that JSON contract. Explicit empty BYOK sentinels prevent
CrewAI's import-time dotenv from restoring operator keys. Old DeepSeek frozen
experiments keep their original provider identities.

## Keeping this index short without erasing decisions

- Update the current ledger and link a dated result; do not append the complete
  experiment narrative to both READMEs and this file.
- Keep historical preregistrations, results, errata, frozen bytes and long
  reasoning commits unchanged. The [experiment index](docs/experiment-index.md)
  links them and the immutable pre-consolidation README/AGENTS snapshots.
- Current guides describe current behaviour. Release notes and dated result
  documents describe what existed then; do not overwrite their old counts.
- First-person decision history belongs in the separate private notes repo.
  Do not stage raw reviews or credentials into this public repository.
