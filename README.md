# Academic Commercialization Assessment Agent

[中文](README.zh-CN.md) · [Live application](https://academic-commercialization-agent.up.railway.app) · [Documentation](docs/README.md) · [Case study](docs/portfolio-case-study.md)

An evidence-constrained workflow for assessing research commercialization:
collect sources, analyse technical maturity, patents and market signals, then
deliver a cited report with an auditable scorecard.

Built with Python, CrewAI, FastAPI and a build-free JavaScript client. The
production system deliberately limits autonomy: retrieval is deterministic,
and six LLM stages reason over validated evidence. **Supplementary Tool Calling
is experimental and remains disconnected from production.**

<a id="english"></a>

## What you can do

- Submit a research topic or attach a paper PDF; choose report language and
  scoring profile.
- Optionally provide Decision Context: the system distinguishes exploratory
  orientation from an actor-specific decision and identifies whether a
  threshold is owner-approved.
- Follow progress, inspect citations and reliability warnings, export Markdown
  or PDF, and share a run link.
- Recover an interrupted run as an immutable child using its longest validated
  checkpoint prefix and fresh credentials.
- Use an operator-issued access code or supported bring-your-own-key (BYOK)
  credentials on a gated deployment.

A report supports research triage; it is **not** technical, legal, regulatory,
investment or freedom-to-operate due diligence. Valid citation IDs do not
establish that a source entails a claim.

## Architecture

```text
Topic / PDF + optional Decision Context
                   │
Deterministic retrieval → validation → frozen source registry
                   │
         ┌─────────┼─────────┐
     Academic    Patent    Market
         └─────────┼─────────┘
                 Writer
                   │
                 Reviewer
                   │
                  Scorer → deterministic weighted total
                   │
        Shared run artifacts + terminal truth
                   │
       FastAPI / browser / CLI / recovery
```

The three evidence specialists run in parallel. Writer, Reviewer and Scorer
follow in sequence. A stage is not a promise of exactly one model request.
See the [code map and contribution rules](AGENTS.md) before changing orchestration.

| Boundary | Implemented behaviour |
|---|---|
| Evidence | Source-native clients plus web search; URL/DOI checks, provenance tiers, deduplication and registered source IDs |
| Output | Pydantic contracts, guardrails, deterministic scoring and bounded Reviewer corrections |
| Quality | Non-blocking precision-first claim/citation screens; unavailable checks are distinct from passes |
| Runtime | Subprocess isolation, content-addressed checkpoints, immutable recovery children and write-once terminal records |
| Cost | Shared run/PDF admission, persistent daily operator-funded quota and complete/lower-bound/unavailable usage states |
| Observability | Optional redacted OpenTelemetry/OpenInference traces to Phoenix or another OTLP collector |
| Delivery | FastAPI, vanilla HTML/CSS/ES modules, Docker and Railway; one application replica |

### Measured results

The frozen baseline contains **10 topics × 3 live repetitions**:

| Check | Observed |
|---|---|
| End-to-end completion | **30/30** |
| TRL calibration | **26/30** |
| Weighted formula correctness | **30/30** |
| Complete report structure | **30/30** |
| Unsupported numeric lines | **0 across 30 reports** |

These are different checks, not a combined accuracy score. Expected TRL ranges
were adjusted after early observations, so this is not independent held-out
validation. The uncited-numeric proxy does not measure all hallucinations.
Seven of ten topics met their TRL range in all three runs.

Other completed evidence includes:

- **90-cell topology ablation:** the four-node arm used 54.89% fewer median
  tokens and 47.03% lower median cost than the six-node arm. Six nodes were
  not established as universally necessary.
- **Five-reviewer utility study:** 20 eligible judgments; the registered success
  rule failed despite a 6:4 full-workflow preference in each round.
- **Two target-user pilot:** both retained `DEFER` and answered `MAYBE` to reuse;
  neither checked external sources. This does not establish product adoption.
- **Recovery:** 30/30 offline fault-injection children completed; one production
  child reused four committed nodes. This is not an exactly-once or general
  cost-saving guarantee.
- **Runtime RTI02:** one normal Qwen completion passed 12/12 primary terminal
  checks, with a disclosed minor observer-cadence deviation. Timeout/fallback
  lanes and general report quality were not validated by that run.

Protocols, source artifacts and limitations are linked in the
[current evidence ledger](docs/evidence-status.md).

## Tool Calling: current status

The bounded execution kernel, adapters, accounting, source-locked review and
unseen-test harnesses exist. Production remains **phase-1 zero-call shadow
mode**: gap signals may be recorded, but they do not add sources or paid searches.

The latest Adaptive Role-Gap v8 passed its AC development gates but failed
three of six gates on AD unseen evaluation: routing 5/8, closure-role value
2/7, and only +1 coverable case over the anchor. V8 is sealed, AC/AD are
consumed, and production integration is not authorized by these results.

The [version-by-version ledger](docs/evidence-status.md#tool-calling-experiments)
keeps v1–v8 failures distinct from transport and mechanical successes. A later
method needs a new protocol and fresh cohorts, not tuning on the failed unseen set.

## Quick start

Use Python 3.11 or 3.12 for the CI-tested environment and
[uv](https://docs.astral.sh/uv/). Dependency installation needs network access;
the default test suite does not call providers.

```bash
git clone https://github.com/shuxiachai/academic-commercialization-agent.git
cd academic-commercialization-agent
uv sync
```

Copy [.env.example](.env.example) to `.env`. For Qwen, set these values and
replace the placeholders locally; do not commit or share keys:

```dotenv
LLM_PROVIDER=qwen
DASHSCOPE_API_KEY=your-key
QWEN_MODEL=qwen3.5-plus
QWEN_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
TAVILY_API_KEY=your-search-key
```

Choose the endpoint matching your operator account/region. This project's
browser BYOK default uses the China-region endpoint. With multiple LLM keys
present, set `LLM_PROVIDER` explicitly; otherwise auto-selection is
DeepSeek → Qwen → Anthropic → OpenAI. Tavily takes precedence over Serper
when both search keys are present. Remove unused placeholder keys.

```bash
uv run uvicorn api.main:app --reload
# Browser: http://localhost:8000
# Alternative CLI (starts real provider work):
uv run academic_agent --topic "solid-state batteries for electric vehicles"
```

Real analysis incurs provider usage. Duration is provider-bound: observed Qwen
completions include 306 and 885 seconds, not a promised three-minute SLA.
See the [operating guide](docs/operating-guide.md) for HTTP endpoints, output
files, Docker, access codes, BYOK, tracing and recovery.

## Security and deployment

Run URLs carry **128 bits of randomness** and act as read capabilities:
anyone with the full URL can read that run until retention removes it.
Code-owned mutation additionally requires its owner/admin code; ownerless
BYOK runs have no second server-side identity. Do not publish private run URLs.

Before public deployment, configure access control, paid-operation limits,
retention and persistent storage. PDF extraction is a paid operation too.
Use **one application replica / one Uvicorn worker**: in-memory ownership and
file-backed quotas are not a distributed queue. See
[deployment controls](docs/operating-guide.md#deploying-publicly) and
[checkpoint recovery](docs/checkpoint-recovery.md).

## Tests and benchmark

The pre-consolidation baseline at `0fdaa76` passed **2071 tests and 678
subtests**. CI covers Linux/Windows × Python 3.11/3.12, latest Ruff, narrow
Pylint, an 85% coverage floor, zero-provider Chromium smoke, and Docker.
These do not constitute a paid-provider production SLO.

```bash
uv run pytest -q
uv run --with ruff ruff check .
# Scheduling preview only; no provider requests:
uv run python benchmark.py --dry-run
```

### Benchmark

| # | Topic | Expected TRL | Industry |
|---|-------|-------------|---------|
| 01 | CAR-T cell therapy for blood cancers | 7–9 | Biomed |
| 02 | mRNA vaccines for cancer immunotherapy | 6–8 | Biomed |
| 03 | solid-state batteries for electric vehicles | 5–7 | Energy |
| 04 | perovskite solar cells for utility-scale power generation | 6–8 | Clean Energy |
| 05 | CRISPR gene editing for genetic diseases | 7–9 | Biomed |
| 06 | carbon capture and storage for industrial emissions | 6–8 | Climate |
| 07 | cultivated meat for food industry | 6–8 | Food |
| 08 | quantum computing for drug discovery | 2–4 | Computing |
| 09 | graphene-based flexible electronics | 3–5 | Materials |
| 10 | room temperature ambient pressure superconductors | 1–2 | Materials |

The [benchmark guide](docs/operating-guide.md#benchmark) explains repetitions,
frozen evidence and paid-run precautions. Do not change scoring rules to
improve these historical numbers.

## Documentation and limitations

- [中文项目说明](README.zh-CN.md)
- [Documentation map](docs/README.md) — current guides versus dated decisions.
- [Evidence ledger](docs/evidence-status.md) — measurements and what they cannot prove.
- [Operating guide](docs/operating-guide.md) — setup, API, deployment and scoring.
- [Contributing](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md) — tested constraints
  and rejected approaches.
- [Experiment archive](docs/experiment-index.md) — unchanged protocols, results
  and errata; older numbers are historical snapshots.

Open limitations include qualitative source entailment, independently measured
decision utility, multilingual/short/non-technical benchmark coverage, legacy
metadata read-state clarity, and single-replica scale. More agents, a vector
database or Kubernetes would not by themselves resolve these gaps.

## Screenshots

Historical UI snapshots; exact deployed wording may evolve.

![Home screen](assets/screenshot-home.png)
![Run result](assets/screenshot-results.png)

<a id="chinese"></a>

For Chinese documentation, open [README.zh-CN.md](README.zh-CN.md).
