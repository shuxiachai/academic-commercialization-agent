# Academic Commercialization Assessment Agent

> **Turn any research paper or topic into a commercialization readiness report in minutes** — six AI agents gather academic, patent, and market evidence, then produce a scored report with verifiable citations.

[![Tests](https://github.com/shuxiachai/academic-commercialization-agent/actions/workflows/test.yml/badge.svg)](https://github.com/shuxiachai/academic-commercialization-agent/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![CrewAI](https://img.shields.io/badge/CrewAI-1.14.x-orange.svg)](https://github.com/crewAIInc/crewAI)

[English](#english) | [中文](#chinese)

---

<a name="english"></a>

## English

A multi-agent system built on [CrewAI](https://github.com/crewAIInc/crewAI) that evaluates the commercialization readiness of academic research.

Input a research direction or paper topic. Six specialized AI agents automatically gather evidence from academic literature, patent databases, and market intelligence sources, then produce a structured commercialization assessment report with verifiable citations and a quantitative scorecard.

---

### Screenshots

<img src="assets/screenshot-home.png" alt="Composer — type a topic and press Enter, or attach a paper" width="800">

<details>
<summary>▶ Analysis in progress — live agent status + source list</summary>
<br>
<img src="assets/screenshot-running.png" alt="Live progress — all five pipeline stages visible at once" width="800">
</details>

<details>
<summary>▶ Full results — scorecard, radar chart, and complete report</summary>
<br>
<img src="assets/screenshot-results.png" alt="Scorecard, report and sources as tabs, citation IDs traceable to the source list" width="800">
</details>

---

### What's different from the CrewAI starter template

| | Original demo | This project |
|---|---|---|
| Agents | 2 (researcher + reporting_analyst) | 6 (specialized roles) |
| Tasks | 2 | 6 (sequential + guardrail validation) |
| Tools | None | OpenAlex + Semantic Scholar + SerperDevTool + Crossref |
| Source collection | None | Deterministic pre-run retrieval with URL reachability check |
| Output format | Free-form text | Markdown report with `[A1][P2][M3]` inline citations + References block + JSON scorecard |
| Output management | Fixed filename (overwritten) | Unique run ID per execution, stored in `outputs/` |
| Data quality | None | Structured evidence + citation integrity check + minimum summary length filter + auto-retry |
| Score reproducibility | — | JSON-mode agents all at `temperature=0`; same topic produces stable results across runs |
| Score traceability | — | Each dimension records source IDs (`trl_source_ids`, `patent_source_ids`, etc.) |

---

### Agent architecture

```
Agent 1: Academic Literature Analyst
         Sources: OpenAlex / Semantic Scholar papers (pre-validated in Step 0)
         Output:  Structured EvidenceReport JSON — maturity, breakthroughs, citations (A1/A2/…)

Agent 2: Patent Landscape Analyst
         Sources: Google Patents / WIPO records (Serper search + URL validation)
         Output:  Structured EvidenceReport JSON — holders, white spaces (P1/P2/…)

Agent 3: Market & Competitive Intelligence Analyst
         Sources: Domain-allowlisted market reports (Serper search)
         Output:  Structured EvidenceReport JSON — players, target industries, opportunities (M1/M2/…)

Agent 4: Technology Commercialization Report Writer
         Tools:   None (uses Agents 1–3 output as context only)
         Output:  Markdown draft with inline citations [A1][P2][M3] and References block
         Guard:   Section structure + citation integrity; auto-retries up to 2×

Agent 5: Report Reviewer
         Tools:   None (uses Agent 4 draft as input)
         Rules:   6 rules — citation integrity, unsupported numeric claims, overconfident
                  language, patent legal framing, evidence consistency, TRL label consistency
         Output:  Corrected final report; Reviewer Notes saved separately (only actual changes logged)

Agent 6: Commercialization Readiness Scorer
         Tools:   None (reads Tasks 1–3 evidence JSON directly, independent of the report)
         Output:  CommercializationScore JSON — TRL / MRL / Patent / Market / Evidence confidence
         Guard:   JSON format validation + hallucinated source ID check + weighted formula
                  correction; auto-retries up to 2×
```

Agents 1–3 run in **parallel** (`async_execution=True`), reducing total pipeline time.

---

### Execution flow

```
Step 0  Source collection & validation (subprocess, deterministic)
        Academic: OpenAlex Works API (filter=title.search, sorted by citation count)
                  → Semantic Scholar supplement (when OpenAlex count is below target)
                  → DOI deduplication; summaries < 100 chars auto-rejected
                  → Concurrent Crossref citation-count backfill (ThreadPoolExecutor)
        Patent:   Serper (3-attempt retry with exponential backoff) → Google Patents / WIPO;
                  URL reachability verified; patent hosts short-circuited
        Market:   Serper + domain allowlist (30+ approved institutions); low-quality sites removed
        Metadata: Crossref API for DOI, journal name, publication date
        Output:   validated_sources.json + status.json passed to subprocess pipeline

Steps 1–3  Agents 1/2/3 — Academic / Patent / Market analysis  (parallel)
Step 4     Agent 4 — Comprehensive report writing  (guardrail validates citations)
Step 5     Agent 5 — Quality review  (Reviewer Notes saved separately)
Step 6     Agent 6 — Quantitative scoring  (independent of report; formula auto-corrected)
```

The pipeline runs in a **subprocess** (`pipeline_worker.py`) so a run can be cancelled immediately via `proc.terminate()` rather than waiting for the current agent to finish.

---

### Report structure

```
# Academic Commercialization Assessment: <research_topic>
## Executive Summary
## 1. Technology Overview & Maturity
## 2. Patent Landscape & White Spaces
## 3. Target Industries & Use Cases
## 4. Competitive Landscape
## 5. Commercialization Opportunities & Recommendations
## Evidence Limitations
## References
    *Reference codes: A = Academic paper · P = Patent · M = Market/industry source*
    [A1] … [P1] … [M1] …
```

> **Multilingual support**: Language is auto-detected from the topic string. Reports in Simplified/Traditional Chinese, Japanese, Korean, German, French, and 6 more languages are fully localized — section headings, citation legend, and patent disclaimers all adapt automatically.

The scorecard (`commercialization_scores.json`) additionally contains: TRL score, patent strength, market accessibility, evidence confidence, overall score, key risks, and key opportunities.

See the [`examples/`](examples/) folder for three complete real reports across different industries.

---

### Sample output

<details>
<summary>▶ Example report excerpt — CRISPR base editing for hemophilia A (overall score: 41.3 / 100)</summary>

---

**Overall Score: 41.3 / 100** · Biotech profile · TRL 3.3/9 · MRL 2.0/10 · Patent 4.0/5 · Market 2.0/5 · Evidence 3.0/5

---

**Executive Summary**

This assessment evaluates single-dose LNP-ABE8e base editing therapy for hemophilia A targeting the F8 Arg2038Cys mutation. The technology demonstrates strong preclinical proof-of-concept with durable factor VIII restoration (83.7 ± 9.1% at 52 weeks, no detectable immune response [A1]) but remains at an early readiness stage with significant clinical development milestones ahead.

**1. Technology Overview & Maturity**

In vivo adenine base editing via LNP delivery achieved 72 ± 8% on-target A-to-G correction in bulk liver tissue at 4 weeks, with FVIII activity restoration confirmed durable to 52 weeks [A1]. Tail-clip bleeding time normalised to 2.8 ± 0.4 min (wild-type: 2.6 ± 0.3 min) [A1][A2]. No off-target editing or immune response was detected.

> **TRL 3.3 / 9** — Active R&D with in vivo animal model proof-of-concept; no IND filing or human data available.

**2. Patent Landscape & White Spaces**

LNP-mediated liver delivery for in vivo base editing is actively patented by Beam Therapeutics, Intellia Therapeutics, and Precision BioSciences [P2][P4]. The specific F8 Arg2038Cys correction approach may represent a differentiated white space, but freedom-to-operate analysis is required before clinical or commercial use [P1][P3].

**Evidence Limitations**

- Academic: All efficacy data from a single murine model; primate or human data absent [A1]
- Patent: USPTO PatentsView API retired — patent search via Google Patents / WIPO only [P1–P6]
- Market: Hemophilia A gene therapy market projections vary widely ($2.9B–$4.3B by 2032) [M1][M3]

**References**

- [A1] Kim et al. (2025). *In Vivo CRISPR-Cas9 Base Editing Achieves Durable Factor VIII Restoration…* https://doi.org/10.1038/s41587-025-02314-8
- [P1] ENDONUCLEASE FOR TARGETING BLOOD COAGULATION FACTOR VIII — Google Patents
- [M1] *Hemophilia Gene Therapy Market Report, Market Size and Revenue…* — Market Research Future

---

</details>

---

### Quick start

#### 1. Install dependencies

```bash
uv sync
```

#### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

LLM — pick **one** of:

| Variable | Provider | Default model |
|---|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek ([get key](https://platform.deepseek.com/api-keys)) | `deepseek-chat` |
| `ANTHROPIC_API_KEY` | Anthropic Claude ([get key](https://console.anthropic.com/)) | `claude-sonnet-5` |
| `OPENAI_API_KEY` | OpenAI ([get key](https://platform.openai.com/api-keys)) | `gpt-4o` |

Also required — one of:

| Variable | Where to get it |
|---|---|
| `SERPER_API_KEY` | [serper.dev/api-key](https://serper.dev/api-key) (free tier: 2 500 queries/month) |
| `TAVILY_API_KEY` | [tavily.com](https://tavily.com) (free tier: 1 000 credits/month, no card required) |

If both are set, `TAVILY_API_KEY` wins. Serper proxies Google search and, like
similar scraping-based APIs, may reject requests from cloud/datacenter IP
ranges — confirmed blocking every request from a Railway deployment while the
same key worked fine from a home network. Tavily is built for server-side
callers and was not observed to have this problem; prefer it for a cloud
deployment, Serper is fine for local use.

Optional:

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | Override auto-detection: `deepseek` / `anthropic` / `openai` |
| `MAX_RPM` | API requests per minute (default `6`; raise to `20`+ for OpenAI/Anthropic) |
| `SEMANTIC_SCHOLAR_API_KEY` | Raises S2 rate limit from 1 req/s → 10 req/s; system works without it |

#### 3. Run

**Option A — web interface (recommended)**

```bash
uv run uvicorn api.main:app --port 8000
```

Open `http://localhost:8000`, type a research topic, and press Enter.

The client is static HTML, CSS and ES modules served by the same process as
the API — no build step and no framework, so what is in `web/` is what runs.

- **Left rail**: every run, grouped by recency, with a live state dot. Runs
  accumulate, so the list is permanent furniture rather than a tab
- **Composer**: the topic field grows with its content; language and scoring
  profile are chips on its bottom bar; `N` starts a new run, Enter submits
- **Live progress**: the five pipeline stages at once, so what is finished and
  what is left are both visible. The elapsed clock ticks locally rather than on
  poll responses, which arrive up to four seconds apart
- **Result**: scorecard, report and sources as three tabs, loaded on demand.
  Citation markers are styled distinctly — they are what makes the report
  auditable. Download as Markdown or PDF (CJK glyphs embedded)
- **Attach a paper**: drop a PDF on the composer and it becomes source A1; the
  pipeline then searches around that paper's specific contribution

**Option B — HTTP API**

The same process serves it; no second command. Interactive docs at
`http://localhost:8000/docs`. Submit a run, poll for progress, fetch the result:

```bash
# Submit — returns immediately with a run_id
curl -X POST http://localhost:8000/api/runs \
     -H 'Content-Type: application/json' \
     -d '{"topic": "solid-state batteries for electric vehicles"}'
# → {"run_id": "20260729T031500Z-a1b2c3d4e5", "state": "running", ...}

# Poll — state is running | completed | failed | cancelled | timeout
curl http://localhost:8000/api/runs/20260729T031500Z-a1b2c3d4e5

# Fetch the report once state is "completed"
curl http://localhost:8000/api/runs/20260729T031500Z-a1b2c3d4e5/report
```

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness, active-run count, resolved LLM provider |
| `POST` | `/api/runs` | Queue an assessment (`202`, or `429` at capacity) |
| `GET` | `/api/runs` | List runs, newest first |
| `GET` | `/api/runs/{id}` | Stage, state, elapsed time, available artifacts |
| `DELETE` | `/api/runs/{id}` | Terminate a running assessment |
| `GET` | `/api/runs/{id}/report` | Final report as Markdown |
| `GET` | `/api/runs/{id}/{artifact}` | `scores`, `sources`, `notes`, or `steps` |

Concurrency is capped at 2 runs (`API_MAX_CONCURRENT` to change) — the binding
constraint is upstream API rate limits, not local CPU. Runs exceeding 30 minutes
are terminated automatically.

The web client and the JSON API share the same `outputs/` directory and launch the
same worker, so a run started from one is visible to the other.

**Option C — Command line**

```bash
uv run crewai run
```

Set the topic via `_DEFAULT_TOPIC` in `src/academic_agent/main.py`.

#### 4. Output

Each run creates an isolated directory that never overwrites previous results:

```
outputs/
└── 20260625T120000Z-a1b2c3d4e5/
    ├── commercialization_report.md    # Final report (Markdown)
    ├── commercialization_report.pdf   # Final report (PDF, CJK-font-aware)
    ├── commercialization_scores.json  # Quantitative scorecard
    ├── validated_sources.json         # Pre-validated source list
    ├── academic_evidence.json         # Task 1 findings, with source IDs and claim types
    ├── patent_evidence.json           # Task 2 findings
    ├── market_evidence.json           # Task 3 findings
    ├── reviewer_notes.md              # Reviewer change log (separated from main report)
    ├── status.json                    # Pipeline stage + source counts (polled by UI)
    └── steps.jsonl                    # Per-agent step events (polled for live progress)
```

The three `*_evidence.json` files are what the report writer and scorer actually
read — neither sees the raw source registry. They record how a validated source
became a cited finding, each carrying `source_ids`, a `claim_type` of
`observed_fact` / `estimate` / `analyst_inference`, a confidence level, and its
own limitations.

---

### Docker

```bash
mkdir -p outputs          # bind-mounted; create it first so it is not root-owned
cp .env.example .env      # add your keys
docker compose up --build
```

The interface is then on http://localhost:8000.

Three things in the image are specific to this project rather than boilerplate:

| Choice | Why |
|---|---|
| `fonts-wqy-zenhei` | The PDF exporter embeds a CJK font instead of trusting the reader to have one. None ship in `python:slim`. **Not `fonts-noto-cjk`** — the obvious choice — Debian's Noto CJK is PostScript/CFF outlines, and reportlab's `TTFont` only reads TrueType, so it is rejected outright. The failure is silent: the font falls back to CID, then Helvetica, and Chinese reports render as blank boxes with nothing logged. The build runs `scripts/verify_container_fonts.py` and fails if no embedded font resolves. |
| `tini` as PID 1 | Each run is a `subprocess.Popen` that the UI cancels with `proc.terminate()`. A bare Python PID 1 neither forwards signals nor reaps children, so cancelled runs would accumulate as zombies and `docker stop` would block until it timed out. |
| Single uvicorn worker | Runs are subprocesses tracked in an in-process registry. A second worker would enforce its own separate concurrency cap and could neither see nor cancel the first one's runs. |

`outputs/` is a bind mount because run history, reports and status files are
state. API keys come from `.env` at runtime and are never baked into a layer.

---

### Deploying publicly

Anything reachable on the open internet at `/api/runs` triggers real, billed
calls — the pipeline makes six LLM calls and dozens of search-API calls per
run. For a link shared with a specific, small audience (e.g. reviewers
looking at this project) rather than the general public, two settings in
`.env` close that off without building a login system:

```bash
ACCESS_CODE=choose-a-long-random-string   # gates every /api/ route
API_DAILY_RUN_CAP=20                      # hard ceiling, in case the code leaks
```

`ACCESS_CODE` (or `ACCESS_CODES` — see below) is checked by a middleware in
`api/main.py` against an `X-Access-Code` header; the web client prompts for
it once and remembers it in `localStorage` from then on. `/health` stays
open regardless — platform load balancers poll it without a header, and
serving it costs nothing. Leaving both unset (the default) makes the gate
inert: local development sees no difference from before it existed.

`API_DAILY_RUN_CAP` is a second, independent line of defence: the
concurrency cap only limits how many runs execute at once, so a leaked code
could still trigger hundreds of runs one after another over a day. This caps
the total regardless of pacing. 0 (default) disables it.

**Handing out a separate code per person:** `ACCESS_CODES` accepts a
comma-separated list instead of one shared value — `ACCESS_CODES=for-alice,
for-bob`. Each code's run history is scoped to itself: the sidebar for
whoever holds `for-alice` only ever shows runs submitted with that same
code, never `for-bob`'s. This is a run-time tag (a hash of the code, written
to each run's directory), not a separate deployment per person — one
process, one `outputs/` directory, codes just partition what `GET /api/runs`
returns. `ACCESS_CODE` (singular) still works for the original one-code-for-
everyone setup; both may be set together.

**A second, open entrance:** `POST /api/runs` also accepts `llm_provider` /
`llm_api_key` / `serper_api_key` in the body as an alternative to any access
code — a visitor's own keys, billed to them, not to the deployment. This
needs no extra server configuration; it becomes reachable in the web client
automatically once a code is configured (the gate modal offers it as a
second option), and stays invisible when the gate is off, since there is
nothing to bypass. The credentials go straight into that one run's
subprocess environment — never to disk, never merged into the server's own
environment — so concurrent runs, BYOK or not, cannot see each other's keys.
A BYOK run gets no code tag at all, so it never appears in any code's
history server-side; the web client instead keeps a session-only list of
the visitor's own runs (in `sessionStorage`) so their sidebar still shows
what they submitted — gone the moment the tab closes, complete for as long
as it's open.

`GET /api/runs` (the run-history list) always stays behind a code
regardless of any of this — opening it up would show every visitor's topics
to every other visitor. Reading or cancelling one specific run by its id
needs no code either way — the id itself carries 40 bits of randomness, the
same capability-URL trust model already used for sharing a finished
report's link.

**Deploying to Railway specifically:** the Dockerfile builds cleanly with
plain `docker build`/`docker-compose`, but Railway's builder is stricter
about a couple of things a local build never exercises:

- It requires an explicit `id` on any `--mount=type=cache`, in a
  Railway-specific format that isn't publicly documented — this image just
  drops that cache mount rather than guessing at it; the lockfile-only layer
  above it (reused whenever `pyproject.toml`/`uv.lock` don't change) is the
  speedup that actually matters.
- It rejects the `VOLUME` instruction outright — persistence there is
  configured through Railway's own Volumes feature in its dashboard, not the
  Dockerfile.
- It assigns a port at deploy time via `$PORT`, so a hardcoded `--port 8000`
  builds fine and then is unreachable. The `CMD` here reads `${PORT:-8000}`
  (falling back to 8000 for `docker-compose`, where the mapping is fixed on
  the host side instead).

None of this needs to be hunted down again — it's already fixed in this
Dockerfile — but if you fork it and see a build fail in under a few seconds
on another platform, this is the shape of thing to check first.

---

### Benchmark

`benchmark.py` ships with 10 preset topics spanning different industries and expected TRL ranges, for validating scoring accuracy and consistency.

```bash
# Run all 10 topics serially (already-succeeded runs are skipped, so an
# interrupted batch resumes where it left off)
uv run python benchmark.py

# Run 3 topics at a time — cuts a full pass from ~30 min to roughly a third
uv run python benchmark.py --concurrency 3

# Re-measure after changing the pipeline. Without --force every completed
# topic is skipped and nothing new is produced.
uv run python benchmark.py --force --concurrency 3

# Re-run one topic
uv run python benchmark.py --only 03 --force

# Check the scheduling without spending any API credit
uv run python benchmark.py --dry-run --concurrency 3

# Generate summary table and CSV
uv run python benchmark_check.py
```

Topics run in **separate processes**, not threads — CrewAI keeps global state
(notably the event bus), so two crews in one interpreter risk cross-talk.

The limit on concurrency is upstream API rate limits, not local CPU: each topic
issues LLM requests at up to `MAX_RPM` (default 6) plus bursts to OpenAlex,
Serper and Crossref, so the aggregate is roughly `concurrency × MAX_RPM`. Every
run records a `rate_limit_hits` count in its `meta.json`, and the summary line
reports the total — **raise `--concurrency` only while that stays at 0**. Starts
are staggered by 10 s (`--stagger`) because every topic opens with the same
burst of source-collection requests.

| # | Topic | Expected TRL | Industry |
|---|-------|-------------|---------|
| 01 | CAR-T cell therapy for solid tumors | 6–8 | Biotech |
| 02 | mRNA vaccines for non-infectious disease | 6–8 | Pharma |
| 03 | CRISPR base editing for monogenic disorders | 4–6 | Biotech |
| 04 | Perovskite solar cells for building-integrated PV | 5–7 | CleanTech |
| 05 | Solid-state batteries for EV | 5–7 | Energy |
| 06 | Green hydrogen via proton exchange membrane electrolysis | 5–7 | Energy |
| 07 | Cultivated meat for food manufacturing | 4–6 | FoodTech |
| 08 | Quantum key distribution for enterprise networks | 4–6 | Cybersecurity |
| 09 | Biodegradable microplastic alternatives for packaging | 5–7 | Materials |
| 10 | Room temperature superconductors | 1–3 | Materials |

`benchmark_check.py` produces `outputs/benchmark/benchmark_summary.csv` and auto-checks:
- 10/10 run success rate
- TRL scores within expected range (pass / flag)
- Weighted formula correctness
- Report section completeness
- Unsupported numeric claim count (hallucination-risk indicator)

---

### Project structure

```
academic_agent/
├── src/academic_agent/
│   ├── crew.py              # Crew definition (6 agents / tasks wired together)
│   ├── pipeline_worker.py   # Subprocess worker: runs pipeline, writes status.json + steps.jsonl
│   ├── main.py              # CLI entry point (--topic "your topic" flag)
│   ├── evidence.py          # Evidence models, guardrail validators, CommercializationScore
│   ├── source_pipeline.py   # Pre-run deterministic source collection & validation
│   ├── source_clients.py    # API clients (OpenAlex, S2, PubMed, arXiv, Lens, Crossref, Serper)
│   ├── pdf_extractor.py     # Uploaded-paper contribution extraction
│   ├── language.py          # Language detection, translation, synonym generation
│   ├── llm_config.py        # Multi-LLM config (DeepSeek / OpenAI / Anthropic; JSON mode)
│   ├── run_output.py        # Run ID, report & scorecard persistence; StepEntry TypedDict
│   └── config/
│       ├── agents.yaml      # Agent role definitions + scoring rubrics (6 agents)
│       └── tasks.yaml       # Task requirements & citation rules (6 tasks)
├── web/                     # Static client (HTML + CSS + ES modules)
├── ui/                      # PDF export, report i18n, run-directory reader
│   ├── ui.py                # Blocks definition and all callbacks
│   ├── runner.py            # Analysis entry points (subprocess + streaming)
│   ├── history.py           # Run history tab
│   ├── i18n.py              # All UI / scorecard / warning strings (12 languages)
│   ├── html_scorecard.py    # Score card rendering
│   ├── html_sources.py      # Source list and detail panel
│   ├── html_progress.py     # Progress steps and stage constants
│   ├── html_misc.py         # Header, reviewer notes, paper divider
│   ├── pdf_export.py        # reportlab PDF export
│   └── run_reader.py        # Run directory metadata readers
├── api/                     # FastAPI HTTP layer
│   ├── main.py              # Endpoints, OpenAPI docs, timeout reaper
│   ├── runs.py              # Worker process registry, concurrency cap, state derivation
│   └── models.py            # Request / response schemas
├── tests/                   # Unit tests and integration tests
├── benchmark.py             # 10-topic benchmark runner
├── benchmark_check.py       # Benchmark result analyzer (CSV + terminal table)
├── outputs/
│   ├── <run_id>/            # Per-run output directory
│   └── benchmark/           # benchmark.py outputs (includes benchmark_summary.csv)
├── .env.example             # Environment variable template
├── pyproject.toml           # Project dependencies
└── README.md
```

---

### Tech stack

- **Framework**: CrewAI 1.14.x
- **LLM**: DeepSeek-V3 / OpenAI GPT-4o / Anthropic Claude — auto-detected from API key, or set `LLM_PROVIDER` explicitly
- **Academic sources**: OpenAlex Works API (primary) + Semantic Scholar Academic Graph API (supplement)
- **Patent / market search**: Serper or Tavily (3-attempt retry with exponential backoff), auto-selected by which API key is set — see "Deploying publicly" for why there are two
- **Academic metadata**: Crossref API (DOI verification and abstract retrieval)
- **Data validation**: Pydantic v2 + custom guardrails (source structure, citation integrity, report structure, scoring formula, hallucinated source ID detection)
- **Web client**: static HTML, CSS and ES modules served by FastAPI — no build step, no framework
- **HTTP API**: FastAPI + Uvicorn, serving both the client and the JSON API (OpenAPI docs at `/docs`)
- **PDF export**: reportlab Platypus (embedded TTFont for CJK; falls back to CID fonts)
- **Container**: Docker multi-stage build (dependency layer cached separately from source), `tini` as PID 1 for subprocess reaping, non-root user, build-time CJK font verification
- **Access control**: optional shared-secret middleware (`ACCESS_CODE`) plus a daily run cap, for exposing a demo link without an open API bill — with an open bring-your-own-key path alongside it, so a visitor without the code can still run it on their own keys
- **Python**: 3.11+

Invalid or unreachable URLs/DOIs, mismatched citation IDs, References inconsistencies, malformed report sections, hallucinated source IDs in scoring, and scoring JSON format errors all block the task and trigger automatic retries.

---

### Scoring dimensions & weight profiles

Scores are computed using a **weight profile** selected automatically based on the topic's industry domain. The profile is stored in `validated_sources.json` and shown as a badge in the UI scorecard.

| Profile | Market | TRL | MRL | Patent | Evidence | Typical domain |
|---|---|---|---|---|---|---|
| `industrial` | 35% | 20% | 15% | 20% | 10% | Default — general manufacturing and anything unmatched |
| `biomedical` | 25% | 20% | **30%** | 15% | 10% | Therapy, vaccine, gene editing, medical device, cultivated meat |
| `material_science` | 20% | **30%** | 20% | 20% | 10% | Perovskite, graphene, electrolyte, solid-state battery, fuel cell |
| `clean_tech` | 25% | **30%** | 20% | 15% | 10% | Green hydrogen, offshore wind, grid storage, direct air capture |
| `software_ai` | **40%** | 30% | 10% | 10% | 10% | LLM, computer vision, SaaS / cloud platform |

Rationale for the weightings: MRL dominates in `biomedical` because manufacturing scale-up is the main gate for biologics; TRL leads in `material_science` and `clean_tech` because lab-to-production cycles are long; `software_ai` puts weight on market traction since distribution cost is near zero and patent moats are weak relative to trade secrets.

Detection runs in priority order — biomedical → material_science → clean_tech → software_ai → industrial — by matching keyword markers against the (English-translated) topic string. The selected profile is stored in `validated_sources.json` and shown as a badge in the UI scorecard.

All profiles sum to 100%, enforced by an `assert` at module load. The `overall_score` is computed by the system from dimension scores and the active profile — the LLM always writes `overall_score: 0` and the formula corrects it automatically.

| Dimension | Field | Max | Description |
|-----------|-------|-----|-------------|
| Technology readiness | `trl_score` | 9 | NASA TRL 1–9 |
| Manufacturing readiness | `mrl_score` | 10 | DoD MRL 1–10 |
| IP landscape navigability | `patent_strength` | 5 | 1 = highly contested, 5 = minimal coverage |
| Market accessibility | `market_accessibility` | 5 | 1 = no commercial activity, 5 = mature market |
| Evidence confidence | `evidence_confidence` | 5 | Cross-validation across source types |
| **Overall score** | `overall_score` | **100** | Weighted formula, profile-dependent |

Each dimension records its supporting source IDs, shown on the scorecard and traceable to the original source.

---

---

<a name="chinese"></a>

## 中文

基于 [CrewAI](https://github.com/crewAIInc/crewAI) 框架开发的学术成果商业化评估智能体系统。

输入一个研究方向或论文主题，系统将自动调度多个专职 AI Agent，从学术文献、专利图谱、市场竞争三个维度完成分析，最终生成一份带可验证引用的结构化商业化评估报告和量化评分卡。

---

### 界面截图

<img src="assets/screenshot-home.png" alt="输入区 — 键入话题后按回车，或附加一篇论文" width="800">

<details>
<summary>▶ 分析运行中 — 实时 Agent 进度 + 来源列表</summary>
<br>
<img src="assets/screenshot-running.png" alt="实时进度 — 五个流水线阶段同时可见" width="800">
</details>

<details>
<summary>▶ 完整结果 — 评分卡、雷达图与完整报告</summary>
<br>
<img src="assets/screenshot-results.png" alt="评分卡、报告、来源三个标签页，引用 ID 可追溯至来源列表" width="800">
</details>

---

### 改造说明

本项目基于 CrewAI 官方模板（researcher + reporting_analyst 两个 Agent）改造而来。

| | 原始 Demo | 本项目 |
|---|---|---|
| Agent 数量 | 2（researcher + reporting_analyst） | 6（专职分工） |
| Task 数量 | 2（research_task + reporting_task） | 6（顺序执行 + guardrail 验证） |
| 工具 | 无 | OpenAlex + Semantic Scholar + SerperDevTool + Crossref |
| 输入变量 | topic + current_year | research_topic |
| 来源收集 | 无 | 运行前确定性预检索，URL 可达性验证 |
| 输出格式 | 自由文本报告 | 带 [A1][P2][M3] 行内引用 + References 区块的 Markdown 报告 + JSON 评分卡 |
| 输出管理 | 固定文件名（覆盖） | 每次运行生成唯一 ID，存入 outputs/ 目录 |
| 数据质量保障 | 无 | 结构化证据 + 引用完整性校验 + 来源最低字数过滤 + 自动重试 |
| 评分确定性 | — | JSON 模式 Agent 全部 temperature=0，同一话题多次运行结果稳定 |
| 评分可追溯性 | — | 每个评分维度标注来源 ID（trl_source_ids / patent_source_ids 等） |

---

### Agent 架构

```
Agent 1: Academic Literature Analyst（学术前沿分析师）
         来源：Step 0 预验证的 OpenAlex / Semantic Scholar 学术论文
         输出：结构化 EvidenceReport JSON，含技术成熟度、研究突破、引用来源（A1/A2/…）

Agent 2: Patent Landscape Analyst（专利图谱分析师）
         来源：Google Patents / WIPO 专利记录（经 Serper 检索 + URL 验证）
         输出：结构化 EvidenceReport JSON，含专利持有人、空白领域（P1/P2/…）

Agent 3: Market & Competitive Intelligence Analyst（市场情报分析师）
         来源：域名白名单过滤的市场报告（Serper 检索）
         输出：结构化 EvidenceReport JSON，含商业玩家、目标行业、市场机会（M1/M2/…）

Agent 4: Technology Commercialization Report Writer（报告撰写师）
         工具：无（以前三个 Agent 输出作为上下文）
         输出：Markdown 报告草稿，含行内引用标注 [A1][P2][M3] 和 References 区块
         校验：章节、正文引用、References 和数字引用完整性，不通过则自动重试（最多 2 次）

Agent 5: Report Reviewer（质量审查员）
         工具：无（以 Agent 4 草稿作为输入）
         规则：6 条规则——引用完整性、无来源数字声明、过度乐观语言、
               专利法律免责措辞、证据一致性、TRL 标签与正文一致性
         输出：修正后的最终报告；Reviewer Notes 仅记录实际修改条目，自动保存至 reviewer_notes.md

Agent 6: Commercialization Readiness Scorer（量化评分员）
         工具：无（以 Task 1/2/3 结构化证据为输入，独立于报告流程）
         输出：CommercializationScore JSON 评分卡，含 TRL / MRL / 专利 / 市场 / 证据置信度五维评分
         校验：JSON 格式 + 幻觉来源 ID 检测 + 加权公式自动修正，不通过则自动重试（最多 2 次）
```

Agent 1/2/3 并行执行（`async_execution=True`），显著缩短总运行时间。

---

### 执行流程

```
Step 0  来源收集与验证（子进程，确定性）
        学术：OpenAlex Works API（filter=title.search，按引用数降序）
              → Semantic Scholar 补充（当 OpenAlex 不足最大来源数时触发）
              → 按 DOI 去重，摘要 <100 字符的记录自动剔除
              → 并发 Crossref 引用数补全（ThreadPoolExecutor）
        专利：Serper（3 次重试 + 指数退避）→ Google Patents / WIPO，验证 URL 可达性
        市场：Serper 检索 + 域名白名单过滤（30+ 认可机构），剔除低质量站点
        元数据：Crossref API 补充 DOI、期刊名、发表日期
        输出 validated_sources.json + status.json 传入子进程流水线

Steps 1–3  Agent 1/2/3 — 学术 / 专利 / 市场分析（并行）
Step 4     Agent 4 — 综合报告撰写（guardrail 校验引用完整性）
Step 5     Agent 5 — 质量审查（Reviewer Notes 单独保存）
Step 6     Agent 6 — 量化评分（独立于报告；公式自动修正）
```

流水线在 **子进程**（`pipeline_worker.py`）中运行，可通过 `proc.terminate()` 即时取消，无需等待当前智能体结束。

---

### 报告结构

```
# Academic Commercialization Assessment: <research_topic>
## Executive Summary
## 1. Technology Overview & Maturity
## 2. Patent Landscape & White Spaces
## 3. Target Industries & Use Cases
## 4. Competitive Landscape
## 5. Commercialization Opportunities & Recommendations
## Evidence Limitations
## References
    *文献编码说明：A = 学术论文 · P = 专利 · M = 市场/行业来源*
    [A1] … [P1] … [M1] …
```

> **多语言支持**：系统根据研究主题自动检测输出语言（支持中文简体/繁体、日文、韩文、德文、法文等 12 种语言）。各语言版本的报告结构、章节标题、引用图例（A/P/M 说明行）及专利免责声明均自动本地化。

评分卡（`commercialization_scores.json`）额外包含：TRL 评分、专利强度、市场可及性、证据置信度、综合评分、关键风险和机遇列表。

完整报告示例见 [`examples/`](examples/) 文件夹（钙钛矿太阳能 / CAR-T 疗法 / 固态电池，三个行业）。

---

### 示例输出

<details>
<summary>▶ 报告节选示例 — CRISPR 碱基编辑治疗血友病 A（综合评分：41.3 / 100）</summary>

---

**综合评分：41.3 / 100** · 生物技术权重方案 · TRL 3.3/9 · MRL 2.0/10 · 专利强度 4.0/5 · 市场可及性 2.0/5 · 证据置信度 3.0/5

---

**执行摘要**

本次评估针对靶向 F8 Arg2038Cys 突变的单次给药 LNP-ABE8e 碱基编辑疗法（血友病 A）。该技术在动物模型中展现出强有力的概念验证，FVIII 活性恢复可持续 52 周且无免疫反应 [A1]，但距离临床转化仍有较大距离（TRL 3.3/9）。

**1. 技术概览与成熟度**

体内腺嘌呤碱基编辑通过 LNP 递送，在小鼠肝脏组织中实现 72 ± 8% 的靶向 A-to-G 编辑，FVIII 活性恢复率在 52 周时仍维持在 83.7 ± 9.1%，止血时间恢复正常 [A1][A2]。

> **TRL 3.3 / 9** — 已完成动物模型概念验证；尚无 IND 申请或人体数据。

**2. 专利图谱与空白领域**

LNP 体内碱基编辑递送领域专利竞争激烈，Beam Therapeutics、Intellia Therapeutics 等公司已布局核心专利 [P2][P4]。针对 F8 Arg2038Cys 特定位点的修正策略或存在差异化空间，但商业化前须完成自由实施分析 [P1][P3]。

**证据局限性**

- 学术：所有有效性数据来自单一小鼠模型，缺乏灵长类或人体数据 [A1]
- 专利：USPTO PatentsView API 已退役，仅通过 Google Patents / WIPO 检索 [P1–P6]
- 市场：血友病 A 基因疗法市场规模预测差异较大（2032 年 $29 亿–$43 亿）[M1][M3]

---

</details>

---

### 快速开始

#### 1. 安装依赖

```bash
uv sync
```

#### 2. 配置环境变量

将 `.env.example` 复制为 `.env` 并填入你的 API Key：

```bash
cp .env.example .env
```

LLM — 三选一填入：

| 变量 | Provider | 默认模型 |
|---|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek（[申请](https://platform.deepseek.com/api-keys)） | `deepseek-chat` |
| `ANTHROPIC_API_KEY` | Anthropic Claude（[申请](https://console.anthropic.com/)） | `claude-sonnet-5` |
| `OPENAI_API_KEY` | OpenAI（[申请](https://platform.openai.com/api-keys)） | `gpt-4o` |

必填——二选一：

| 变量 | 申请地址 |
|---|---|
| `SERPER_API_KEY` | [serper.dev/api-key](https://serper.dev/api-key)（免费额度：2500 次/月） |
| `TAVILY_API_KEY` | [tavily.com](https://tavily.com)（免费额度：1000 credits/月，不需要绑卡） |

两个都设置时优先用 `TAVILY_API_KEY`。Serper 本质是代理抓取 Google 搜索结果，跟同类抓取型 API 一样，可能会拒绝来自云主机/数据中心 IP 段的请求——实测在 Railway 部署上，同一把 key 从家庭网络请求正常、从云端请求全部被拒。Tavily 是为服务器端调用设计的，没观察到这个问题；云端部署建议优先用 Tavily，本地开发用 Serper 没问题。

可选项：

| 变量 | 用途 |
|---|---|
| `LLM_PROVIDER` | 手动指定 provider：`deepseek` / `anthropic` / `openai` |
| `MAX_RPM` | API 每分钟请求数（默认 `6`；使用 OpenAI/Anthropic 可调高至 `20`+） |
| `SEMANTIC_SCHOLAR_API_KEY` | 将 S2 速率限制从 1 req/s 提升至 10 req/s；不填也可正常运行 |

#### 3. 运行

**方式一：网页界面（推荐）**

```bash
uv run uvicorn api.main:app --port 8000
```

浏览器打开 `http://localhost:8000`，输入研究方向后按回车。

客户端是静态 HTML / CSS / ES 模块，由 API 同一个进程托管——无构建步骤、无框架，`web/` 里是什么跑的就是什么。

- **左侧栏**：全部运行按时间分组，带实时状态点。运行会不断累积，因此列表是常驻结构而非一个标签页
- **输入区**：话题框随内容增高；报告语言与评分方案收在底部小 chip 中；`N` 新建，回车提交
- **实时进度**：五个流水线阶段同时可见，已完成与待执行一目了然。计时在本地每秒走，而非依赖间隔可达四秒的轮询响应
- **结果**：评分卡、报告、来源三个标签页，按需加载。引用标记有独立样式——它们是报告可审计的凭据。可导出 Markdown 或 PDF（内嵌 CJK 字体）
- **附加论文**：把 PDF 拖到输入框即成为来源 A1，流水线随后围绕该论文的具体贡献检索证据

界面功能：
- **实时进度**：Phase 1 并行三个 Agent 的独立状态行 + 已用时间
- **评分卡**：综合分（0–100）+ 五维雷达图 + 条形图，每个维度展示支撑来源 ID 标签（如 `A2` `M1`）；Weight Profile 徽章显示当前使用的评分权重方案
- **来源警告**：任一域名来源不足时显示橙色提示横幅
- **报告**：Markdown 全文渲染 + `.md` / `.pdf` 双格式下载（PDF 后台生成，报告立即显示）
- **History 标签页**：浏览所有历史运行；点击任意行自动填入 Run ID；包含 Run ID 列便于复制

**方式二：HTTP API**

同一个进程提供，无需另外启动。

交互式文档：`http://localhost:8000/docs`。提交任务、轮询进度、获取结果：

```bash
# 提交 —— 立即返回 run_id，不阻塞
curl -X POST http://localhost:8000/api/runs \
     -H 'Content-Type: application/json' \
     -d '{"topic": "solid-state batteries for electric vehicles"}'
# → {"run_id": "20260729T031500Z-a1b2c3d4e5", "state": "running", ...}

# 轮询 —— state 取值：running | completed | failed | cancelled | timeout
curl http://localhost:8000/api/runs/20260729T031500Z-a1b2c3d4e5

# state 变为 completed 后获取报告
curl http://localhost:8000/api/runs/20260729T031500Z-a1b2c3d4e5/report
```

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/health` | 存活检查、当前运行数、已解析的 LLM provider |
| `POST` | `/api/runs` | 提交评估任务（`202`，达到并发上限时 `429`） |
| `GET` | `/api/runs` | 列出历史运行，最新在前 |
| `GET` | `/api/runs/{id}` | 阶段、状态、已用时长、可用产物清单 |
| `DELETE` | `/api/runs/{id}` | 终止运行中的任务 |
| `GET` | `/api/runs/{id}/report` | Markdown 格式的最终报告 |
| `GET` | `/api/runs/{id}/{artifact}` | `scores` / `sources` / `notes` / `steps` |

并发上限默认为 2（通过 `API_MAX_CONCURRENT` 调整）——真正的瓶颈是上游 API 限速而非本机 CPU。
超过 30 分钟的运行会被自动终止。

网页客户端与 JSON API 共享同一个 `outputs/` 目录、启动同一个 worker，因此从任一入口发起的运行在另一侧都可见。

**方式三：命令行**

```bash
uv run crewai run
```

研究主题在 `src/academic_agent/main.py` 中修改 `_DEFAULT_TOPIC` 字段。

#### 4. 查看报告

每次运行生成独立目录，不会覆盖历史结果：

```
outputs/
└── 20260625T120000Z-a1b2c3d4e5/
    ├── commercialization_report.md   # 最终报告（Markdown）
    ├── commercialization_report.pdf  # 最终报告（PDF，支持 CJK 字体）
    ├── commercialization_scores.json # 量化评分卡
    ├── validated_sources.json        # 预验证来源清单
    ├── academic_evidence.json        # Task 1 的发现，含来源 ID 与论断类型
    ├── patent_evidence.json          # Task 2 的发现
    ├── market_evidence.json          # Task 3 的发现
    ├── reviewer_notes.md             # 审查员修改记录（与正文分离）
    ├── status.json                   # 流水线阶段 + 来源数量（UI 轮询用）
    └── steps.jsonl                   # 每个 Agent 的步骤事件（实时进度用）
```

三个 `*_evidence.json` 是报告撰写与评分 Agent 实际读取的内容——它们都看不到原始来源清单。这些文件记录了"一条已验证的来源如何变成一条带引用的结论"，每条发现都带有 `source_ids`、`claim_type`（`observed_fact` / `estimate` / `analyst_inference`）、置信度，以及它自身的局限性。

---

### Docker 部署

```bash
mkdir -p outputs          # 会被挂载，先建好以免属主变成 root
cp .env.example .env      # 填入 API Key
docker compose up --build
```

启动后访问 http://localhost:8000

镜像里有三处配置是针对本项目的，不是通用模板：

| 配置 | 原因 |
|---|---|
| `fonts-wqy-zenhei` | PDF 导出会嵌入 CJK 字体，而非依赖阅读器本地有字库，`python:slim` 里一个都没有。**注意不是 `fonts-noto-cjk`**——Debian 的 Noto CJK 是 PostScript/CFF 轮廓，reportlab 的 `TTFont` 只读 TrueType，会直接拒绝。而这个失败是静默的：字体会降级到 CID 再到 Helvetica，中文报告渲染成空白方块却没有任何报错。构建期会运行 `scripts/verify_container_fonts.py`，解析不到嵌入字体就让构建失败。 |
| `tini` 作 PID 1 | 每次运行都是一个 `subprocess.Popen`，UI 通过 `proc.terminate()` 取消。裸 Python 作 PID 1 既不转发信号也不回收子进程，取消的运行会堆积成僵尸进程，`docker stop` 也会一直卡到超时。 |
| 单个 uvicorn worker | 运行是进程内注册表跟踪的子进程。第二个 worker 会各自执行独立的并发上限，且看不到也无法取消对方的运行。 |

`outputs/` 用绑定挂载，因为运行历史、报告和状态文件都是状态数据。API Key 在运行时从 `.env` 读取，不会进入镜像层。

CI 每次提交都会构建镜像并断言 PID 1 是 tini、容器非 root 运行、四种 CJK 语言都能解析到嵌入字体。

---

### 公网部署

只要 `/api/runs` 能被公网访问到，任何人都能触发真实计费的调用——一次运行会调六次 LLM，再加几十次检索 API。如果只是把链接发给特定的少数人看（比如给面试官看这个项目），而不是面向公众开放，`.env` 里两个开关就能把这个口子堵上，不用做一整套登录系统：

```bash
ACCESS_CODE=换成一串足够长的随机字符串     # 拦截所有 /api/ 路由
API_DAILY_RUN_CAP=20                      # 硬上限，万一口令泄漏出去兜底
```

`ACCESS_CODE`（或下面的 `ACCESS_CODES`）由 `api/main.py` 里的中间件校验请求头 `X-Access-Code`；网页客户端只在第一次访问时弹窗询问，之后记在 `localStorage` 里不用重复输入。`/health` 不受影响——云平台的健康检查不会带请求头，这个接口本身也不花钱。两个都不设置（默认）时门禁完全不生效，本地开发和之前没有任何区别。

`API_DAILY_RUN_CAP` 是第二道独立防线：并发上限只管同时跑几个，管不住口令泄漏后被人在一天内前后接力刷上百次；这个直接卡总数，与节奏无关。默认 0 表示不限制。

**给每个人发不同的口令：** `ACCESS_CODES` 接受逗号分隔的多个值，而不是一个共用口令——`ACCESS_CODES=给alice的口令,给bob的口令`。每个口令的运行历史都只属于它自己：持有"给alice的口令"的人，侧栏永远只看得到用这个口令跑过的记录，看不到"给bob的口令"跑过的。这只是运行时打的一个标记（口令的哈希值，写进每次运行的目录里），不是给每个人单独跑一套部署——还是一个进程、一个 `outputs/` 目录，口令只是决定 `GET /api/runs` 返回哪些。`ACCESS_CODE`（单数）还是照常可用，对应原来那种所有人共用一个口令的设置；两者可以同时设置。

**第二个开放入口：** `POST /api/runs` 的请求体里也可以带 `llm_provider` / `llm_api_key` / `serper_api_key`，作为任意访问口令的替代——用访客自己的 Key，花费算在他们自己头上，不算在部署方头上。这条路不需要额外的服务端配置：只要配置了口令，网页客户端就会在门禁弹窗里自动多出这个选项；不设口令时它也不会出现，因为没有什么需要绕过。密钥直接进入这一次运行的子进程环境变量——不落盘、不并入服务端自身的环境——所以无论是不是 BYOK，并发的运行之间互相看不到对方的密钥。BYOK 提交的运行不会被打上任何口令标记，所以服务端不会把它记进任何一个口令的历史里；网页客户端转而在 `sessionStorage` 里维护一份访客自己这次会话提交过的运行列表，让侧栏依然能显示自己提交过什么——标签页一关就消失，标签页开着的时候完整可见。

`GET /api/runs`（运行历史列表）无论如何都始终留在口令后面——开放的话会把每个访客的话题暴露给所有其他访客。按 `run_id` 读取或取消某一次具体的运行则不需要口令——`run_id` 本身带 40 位随机性，用的是和"分享一份已完成报告的链接"同一套能力令牌信任模型。

**部署到 Railway 需要特别注意的地方：** 这个 Dockerfile 在普通 `docker build`/`docker-compose` 下构建完全正常，但 Railway 的构建器比标准 Docker 严格，有几处本地构建根本测不出来的差异：

- `--mount=type=cache` 必须显式带 `id`，还得符合 Railway 自己的格式（没有公开文档写清楚）——这个镜像直接去掉了这个缓存挂载，没有去猜这个格式；真正的加速来自上面那层只依赖 `pyproject.toml`/`uv.lock` 的层缓存，`lockfile` 不变就整层复用
- `VOLUME` 指令 Railway 直接不认，持久化要在它自己的 Volumes 功能里配置，不能写在 Dockerfile 里
- 端口是运行时通过 `$PORT` 环境变量动态分配的，写死 `--port 8000` 会导致构建成功但外部访问不到。这里的 `CMD` 读取 `${PORT:-8000}`（没有 `$PORT` 时退回 8000，兼容 `docker-compose` 固定端口映射的场景）

这些坑已经在这份 Dockerfile 里修好了，不需要重新踩一遍——但如果你 fork 之后在别的平台上遇到几秒钟就构建失败的情况，可以先往这个方向查。

---

### 基准测试

`benchmark.py` 包含 10 个预设话题，覆盖不同行业和预期 TRL 范围，用于验证系统的评分准确性和一致性。

```bash
# 串行运行全部 10 个话题（已成功的自动跳过，因此中断后可续跑）
uv run python benchmark.py

# 并发 3 个话题 —— 完整一轮从约 30 分钟压缩到三分之一左右
uv run python benchmark.py --concurrency 3

# 改动流水线后重新测量。不加 --force 的话，已完成的话题会全部跳过、不产生新结果
uv run python benchmark.py --force --concurrency 3

# 重跑单个话题
uv run python benchmark.py --only 03 --force

# 仅验证调度逻辑，不消耗任何 API 额度
uv run python benchmark.py --dry-run --concurrency 3

# 生成摘要表格并输出 CSV
uv run python benchmark_check.py
```

话题运行在**独立进程**而非线程中 —— CrewAI 持有全局状态（尤其是 event bus），
同一解释器内跑两个 crew 存在事件流串扰的风险。

并发上限取决于上游 API 限速而非本机 CPU：每个话题以最高 `MAX_RPM`（默认 6）的速率
调用 LLM，外加对 OpenAlex、Serper、Crossref 的突发请求，因此总速率约为
`并发数 × MAX_RPM`。每次运行都会在 `meta.json` 中记录 `rate_limit_hits`，汇总行输出总数
——**只有该值保持为 0 时才可以继续调高 `--concurrency`**。任务启动默认错开 10 秒
（`--stagger`），因为每个话题开头都是同一批来源检索请求的突发。

| # | 话题 | 预期 TRL | 行业 |
|---|------|---------|------|
| 01 | CAR-T cell therapy for solid tumors | 6–8 | Biotech |
| 02 | mRNA vaccines for non-infectious disease | 6–8 | Pharma |
| 03 | CRISPR base editing for monogenic disorders | 4–6 | Biotech |
| 04 | Perovskite solar cells for building-integrated PV | 5–7 | CleanTech |
| 05 | Solid-state batteries for EV | 5–7 | Energy |
| 06 | Green hydrogen via proton exchange membrane electrolysis | 5–7 | Energy |
| 07 | Cultivated meat for food manufacturing | 4–6 | FoodTech |
| 08 | Quantum key distribution for enterprise networks | 4–6 | Cybersecurity |
| 09 | Biodegradable microplastic alternatives for packaging | 5–7 | Materials |
| 10 | Room temperature superconductors | 1–3 | Materials |

`benchmark_check.py` 生成 `outputs/benchmark/benchmark_summary.csv`，自动校验：
- 10/10 运行成功率
- TRL 评分是否落在预期范围（pass / flag）
- 加权公式正确性
- 报告章节完整性
- 悬空数字行数（幻觉风险指标）

---

### 项目文件结构

```
academic_agent/
├── src/academic_agent/
│   ├── crew.py              # Crew 定义（6 个 Agent / Task 接线）
│   ├── pipeline_worker.py   # 子进程 Worker：运行流水线，写入 status.json + steps.jsonl
│   ├── main.py              # 命令行入口（支持 --topic 参数）
│   ├── evidence.py          # 证据模型、guardrail 校验、CommercializationScore 模型
│   ├── source_pipeline.py   # 运行前确定性来源收集与验证
│   ├── source_clients.py    # API 客户端（OpenAlex / S2 / PubMed / arXiv / Lens / Crossref / Serper）
│   ├── pdf_extractor.py     # 上传论文的核心贡献提取
│   ├── language.py          # 语言检测、翻译、同义词生成
│   ├── llm_config.py        # 多 LLM 配置（DeepSeek / OpenAI / Anthropic；JSON 模式）
│   ├── run_output.py        # 运行 ID、报告与评分 JSON 持久化；StepEntry TypedDict
│   └── config/
│       ├── agents.yaml      # Agent 角色配置 + 评分 rubric（6 个）
│       └── tasks.yaml       # Task 需求与引用规则（6 个）
├── web/                     # 静态客户端（HTML + CSS + ES 模块）
├── ui/                      # PDF 导出、报告国际化、运行目录读取
│   ├── ui.py                # Blocks 定义与全部回调
│   ├── runner.py            # 分析入口（子进程 + 流式输出）
│   ├── history.py           # 历史运行标签页
│   ├── i18n.py              # 全部 UI / 评分卡 / 警告文案（12 种语言）
│   ├── html_scorecard.py    # 评分卡渲染
│   ├── html_sources.py      # 来源列表与详情面板
│   ├── html_progress.py     # 进度步骤与阶段常量
│   ├── html_misc.py         # 页头、审查记录、论文分隔线
│   ├── pdf_export.py        # reportlab PDF 导出
│   └── run_reader.py        # 运行目录元数据读取
├── api/                     # FastAPI HTTP 层
│   ├── main.py              # 端点定义、OpenAPI 文档、超时回收
│   ├── runs.py              # Worker 进程注册表、并发控制、状态推导
│   └── models.py            # 请求 / 响应模型
├── tests/                   # 单元测试与集成测试
├── benchmark.py             # 10 话题基准测试运行器
├── benchmark_check.py       # 基准结果分析器（生成 CSV + 终端表格）
├── outputs/
│   ├── <run_id>/            # 每次正常运行的输出目录
│   └── benchmark/           # benchmark.py 输出目录（含 benchmark_summary.csv）
├── .env.example             # 环境变量模板
├── pyproject.toml           # 项目依赖
└── README.md
```

---

### 技术栈

- **框架**：CrewAI 1.14.x
- **LLM**：DeepSeek-V3 / OpenAI GPT-4o / Anthropic Claude — 自动从 API Key 检测，或通过 `LLM_PROVIDER` 显式指定
- **学术来源**：OpenAlex Works API（主力）+ Semantic Scholar Academic Graph API（补充）
- **专利 / 市场搜索**：Serper 或 Tavily（3 次重试 + 指数退避），按配置了哪个 Key 自动选择——原因见"公网部署"一节
- **学术元数据**：Crossref API（DOI 验证与摘要检索）+ 并发引用数补全
- **数据校验**：Pydantic v2 + 自定义 guardrail（来源结构、引用完整性、报告结构、幻觉来源 ID 检测、评分算法验证）
- **网页客户端**：静态 HTML / CSS / ES 模块，由 FastAPI 托管——无构建步骤、无框架
- **HTTP API**：FastAPI + Uvicorn（OpenAPI 文档位于 `/docs`）
- **PDF 导出**：reportlab Platypus（嵌入式 TTFont，支持 CJK；回退至 CID 字体）
- **容器化**：Docker 多阶段构建（依赖层与源码层分离缓存），`tini` 作 PID 1 回收子进程，非 root 运行，构建期 CJK 字体校验
- **访问控制**：可选的共享口令中间件（`ACCESS_CODE`）+ 每日运行次数熔断，用于对外发布演示链接而不暴露一张空白账单；旁边还留了一条开放的"自带 Key"通道，没有口令的访客也能用自己的 Key 跑起来
- **Python**：3.11+

URL/DOI 无效或不可达、引用编号错误、References 不一致、报告结构错误、幻觉来源 ID 和评分 JSON 格式错误都会阻止任务并触发重试。

---

### 评分维度与权重方案

评分使用**权重方案（weight profile）**，系统根据话题所属行业自动选择，并存入 `validated_sources.json`，在 UI 评分卡中以徽章显示。

| 方案 | 市场 | TRL | MRL | 专利 | 证据 | 典型领域 |
|---|---|---|---|---|---|---|
| `industrial` | 35% | 20% | 15% | 20% | 10% | 默认方案 —— 通用制造业及未匹配到其他方案的话题 |
| `biomedical` | 25% | 20% | **30%** | 15% | 10% | 疗法、疫苗、基因编辑、医疗器械、培养肉 |
| `material_science` | 20% | **30%** | 20% | 20% | 10% | 钙钛矿、石墨烯、电解质、固态电池、燃料电池 |
| `clean_tech` | 25% | **30%** | 20% | 15% | 10% | 绿氢、海上风电、电网储能、直接空气捕集 |
| `software_ai` | **40%** | 30% | 10% | 10% | 10% | 大语言模型、计算机视觉、SaaS / 云平台 |

权重设计依据：`biomedical` 中 MRL 占比最高，因为生物制品的量产工艺是商业化的主要瓶颈；`material_science` 与 `clean_tech` 以 TRL 为主，因为从实验室到量产的周期极长；`software_ai` 侧重市场牵引，因为分发成本接近于零，且专利护城河相对商业秘密更弱。

方案检测按优先级顺序进行——biomedical → material_science → clean_tech → software_ai → industrial，通过关键词标记匹配（已翻译为英文的）话题字符串。选中的方案存入 `validated_sources.json`，并在 UI 评分卡中以徽章显示。

所有方案权重之和为 100%，由模块加载时的 `assert` 强制校验。`overall_score` 由系统根据维度分数和当前方案自动计算——LLM 始终输出 `overall_score: 0`，系统公式自动修正。

| 维度 | 字段 | 满分 | 说明 |
|------|------|------|------|
| 技术成熟度 | `trl_score` | 9 | NASA TRL 1–9 |
| 制造成熟度 | `mrl_score` | 10 | DoD MRL 1–10 |
| IP 景观可导航性 | `patent_strength` | 5 | 1=高度竞争，5=几乎无专利保护 |
| 市场可及性 | `market_accessibility` | 5 | 1=无商业活动，5=成熟市场有收入数据 |
| 证据置信度 | `evidence_confidence` | 5 | 多维来源交叉验证程度（元维度） |
| **综合分** | `overall_score` | **100** | 加权公式，因方案而异 |

每个维度评分同时记录支撑来源 ID，可在评分卡中直接查看并追溯至原始文献。
