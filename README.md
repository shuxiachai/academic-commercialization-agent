# Academic Commercialization Assessment Agent

> **Turn any research paper or topic into a commercialization readiness report in minutes** — six AI agents gather academic, patent, and market evidence, then produce a scored report with verifiable citations.

[![Tests](https://github.com/shuxiachai/academic-commercialization-agent/actions/workflows/test.yml/badge.svg)](https://github.com/shuxiachai/academic-commercialization-agent/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![CrewAI](https://img.shields.io/badge/CrewAI-1.14.x-orange.svg)](https://github.com/crewAIInc/crewAI)

[![Live demo](https://img.shields.io/badge/live%20demo-try%20it-brightgreen.svg)](https://academic-commercialization-agent.up.railway.app)

[English](#english) | [中文](#chinese)

---

<a name="english"></a>

## English

A multi-agent system built on [CrewAI](https://github.com/crewAIInc/crewAI) that evaluates the commercialization readiness of academic research.

Input a research direction or paper topic. Six specialized AI agents automatically gather evidence from academic literature, patent databases, and market intelligence sources, then produce a structured commercialization assessment report with verifiable citations and a quantitative scorecard.

---

### Try it online

**https://academic-commercialization-agent.up.railway.app**

Running on Railway — nothing to install. The gate offers two ways in:

- **Bring your own API keys** — no access code needed. Pick your LLM provider,
  paste an LLM key and a search key, and the run is billed to you. The keys go
  only into that one run's subprocess environment: never written to disk, never
  merged into the server's own environment, never visible to another run
  happening at the same time, and gone when you close the tab.
- **Access code** — runs on the deployment's own keys. Codes are handed out
  privately; without one, use the BYOK option above.

A full run takes roughly 3 minutes and costs a few cents of LLM plus about 9
search queries. The deployment therefore caps shared paid-operation concurrency
and daily operator-funded admissions per code, including PDF extraction. See
[Deploying publicly](#deploying-publicly) for the exact boundary.

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

### Measured results

The frozen baseline exercises live retrieval and the complete six-agent
pipeline: **10 topics × 3 live repetitions**. The row-level evidence is committed in
[`benchmark_summary.csv`](outputs/benchmark/benchmark_summary.csv).

| Metric | Result |
|---|---|
| End-to-end completion | **30/30** |
| TRL calibration | **26/30** |
| Weighted formula correctness | **30/30** |
| Complete report structure | **30/30** |
| Unsupported numeric lines | **0 across 30 reports** |

TRL calibration compares the scorecard with milestone-anchored ranges whose
public events can be checked independently. It is calibration evidence, not a
blinded held-out accuracy score: the ranges were revised after earlier scores
had been observed. The numeric-line check is a citation-risk proxy, not a claim
that every possible form of hallucination has been eliminated.

---

### What's different from the CrewAI starter template

| | Original demo | This project |
|---|---|---|
| Agents | 2 (researcher + reporting_analyst) | 6 (specialized roles) |
| Tasks | 2 | 6 (sequential + guardrail validation) |
| Tools | None | OpenAlex + PubMed + arXiv + Semantic Scholar + Lens + Serper/Tavily + Crossref |
| Source collection | None | Structured pre-run retrieval with topic planning, provenance tiers, authority coverage, and a rejection audit |
| Output format | Free-form text | Markdown report with `[A1][P2][M3]` inline citations + References block + JSON scorecard |
| Output management | Fixed filename (overwritten) | Unique run ID per execution, stored in `outputs/` |
| Data quality | None | Structured evidence + citation integrity check + minimum summary length filter + auto-retry |
| Score reproducibility | — | JSON-mode agents all at `temperature=0`, so scoring is reproducible **for a given set of evidence**. Across runs the evidence itself moves — market sources come from live search — so repeat runs of a topic are close, not identical |
| Score traceability | — | Each dimension records source IDs (`trl_source_ids`, `patent_source_ids`, etc.) |

---

### Agent architecture

```
Agent 1: Academic Literature Analyst
         Sources: OpenAlex / PubMed / arXiv / Semantic Scholar papers (pre-validated in Step 0)
         Output:  Structured EvidenceReport JSON — maturity, breakthroughs, citations (A1/A2/…)

Agent 2: Patent Landscape Analyst
         Sources: Structured Lens records plus allowlisted WIPO / EPO / aggregator records;
                  the source tier retains which path supplied the record
         Output:  Structured EvidenceReport JSON — holders, white spaces (P1/P2/…)

Agent 3: Market & Competitive Intelligence Analyst
         Sources: Domain-allowlisted market and authority records; applicable clinical topics
                  query regulators and trial registries directly
         Output:  Structured EvidenceReport JSON — players, target industries, opportunities (M1/M2/…)

Agent 4: Technology Commercialization Report Writer
         Tools:   None (uses Agents 1–3 output as context only)
         Output:  Markdown draft with inline citations [A1][P2][M3] and References block
         Guard:   Section structure + citation integrity; auto-retries up to 2×

Agent 5: Report Reviewer
         Tools:   None (uses Agent 4 draft as input)
         Rules:   6 rules — citation integrity, unsupported numeric claims, overconfident
                  language, patent legal framing, evidence consistency, narrative TRL removal
         Output:  Bounded JSON correction plan; code applies exact edits to the validated draft
                  and saves actual changes as Reviewer Notes. If review cannot complete, the
                  validated draft ships unchanged and the reliability panel records the fallback.

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
Step 0  Source collection & validation (subprocess, before the six agents)
        Input:    free-form request → concise English search topic + equivalent aliases;
                  the original wording remains the report's display topic
        Academic: OpenAlex Works API (filter=title.search, sorted by citation count)
                  → PubMed / arXiv domain supplements and Semantic Scholar fallback
                  → DOI deduplication; summaries < 100 chars auto-rejected
                  → Concurrent Crossref citation-count backfill (ThreadPoolExecutor)
        Patent:   Lens structured API when configured; otherwise Serper/Tavily →
                  allowlisted WIPO / EPO / aggregator records. Official WIPO/EPO web
                  records are high tier; secondary web extracts are medium tier
        Market:   Serper/Tavily + domain allowlist; low-quality sites removed.
                  Clinical-product topics prepend FDA, EMA, and ClinicalTrials.gov queries;
                  missing authority categories become a non-blocking reliability warning
        Metadata: Crossref API for DOI, journal name, publication date
        Output:   validated_sources.json + status.json passed to subprocess pipeline
        Failure:  retrieval_diagnostics.json preserves the search plan and rejection audit

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

> **Multilingual and free-form input**: Language is auto-detected from the user's unedited topic. The retrieval layer derives a concise English search topic plus equivalent aliases while preserving the original wording for the report. Reports in Simplified/Traditional Chinese, Japanese, Korean, German, French, and 6 more languages are fully localized — section headings, citation legend, and patent disclaimers all adapt automatically.

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
- **Reliability**: a separate panel distinguishes a failed retrieval domain,
  incomplete clinical-authority coverage, a check that could not run, and a
  check that ran without finding a problem — silence is never rendered as pass
- **Attach a paper**: drop a PDF on the composer and it becomes source A1; the
  pipeline then searches around that paper's specific contribution. Its DOI
  and URL were read out of the PDF by a model, so they are resolved before
  the paper is cited — one that does not resolve is dropped rather than
  printed as a reference, and the source drops to `medium` credibility to
  say so

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
| `GET` | `/health` | Liveness, active-run and shared paid-operation capacity, resolved LLM provider |
| `POST` | `/api/papers` | Upload a PDF and extract its contribution (`429` at shared paid capacity) |
| `POST` | `/api/runs` | Queue an assessment (`202`, or `429` at shared paid capacity) |
| `GET` | `/api/runs` | List runs, newest first |
| `GET` | `/api/runs/{id}` | Stage, state, elapsed time, available artifacts |
| `DELETE` | `/api/runs/{id}` | Terminate a running assessment |
| `GET` | `/api/runs/{id}/report` | Final report as Markdown |
| `GET` | `/api/runs/{id}/{artifact}` | Run artifacts, including `scores`, `sources`, checks, and failed-run `retrieval` diagnostics |

Concurrency is capped at 2 paid operations (`API_MAX_CONCURRENT` to change),
shared by worker runs and inline PDF extraction — the binding constraint is
upstream provider capacity, not local CPU. Runs exceeding 30 minutes are
terminated automatically; extraction releases its slot on every exit path.

The web client and the JSON API share the same `outputs/` directory and launch the
same worker, so a run started from one is visible to the other.

**Option C — Command line**

```bash
uv run academic_agent --topic "solid-state batteries for electric vehicles"
```

Pass a different value to `--topic` for each run; no source edit is required.

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

Runs that stop before meeting the academic-source minimum write
`retrieval_diagnostics.json` instead of a report. The API and browser expose
the submitted topic, canonical search phrase, aliases, candidate counts, and
rejection audit so a retrieval failure is not presented as an unexplained error.

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

Both `/api/runs` and `/api/papers` can trigger real, billed calls — a full
pipeline makes six LLM calls plus search-API calls, while PDF contribution
extraction makes an inline LLM call. For a link shared with a specific, small
audience (e.g. reviewers) rather than the general public, two settings in
`.env` close those paths without building a login system:

```bash
ACCESS_CODE=choose-a-long-random-string        # gates every /api/ route
API_DAILY_PAID_OPERATION_CAP=3                 # per-code provider admissions
```

`ACCESS_CODE` (or `ACCESS_CODES` — see below) is checked by a middleware in
`api/main.py` against an `X-Access-Code` header; the web client prompts once
and remembers it in `localStorage`. `/health` stays open for platform probes.
Leaving every access-code setting unset (the default) makes the gate inert, so
local development sees no difference.

`API_DAILY_PAID_OPERATION_CAP` is an independent, per-process wallet guard. A
full assessment and a PDF extraction each consume one operator-funded unit, so
an upload-then-run journey consumes two. It is applied separately to each
validated code (including the admin code); BYOK operations are exempt because
the visitor pays. 0 disables it. The old `API_DAILY_RUN_CAP` name remains a
backward-compatible fallback when the new variable is unset. Because the ledger
is in memory, UTC midnight and a process restart reset it; durable multi-replica
accounting would require an external store.

Size the value against the stricter of your **LLM and search** budgets. Across
30 measured runs, one full assessment issues a median of 9 web searches (range
5-15); PDF extraction adds one LLM call but no search call. Tavily's
1000-per-month free tier is therefore roughly 110 full runs in total across all
codes. The per-code cap bounds one leaked credential, not the aggregate of every
code.

**Two more settings worth turning on before a link goes public**, both
default-off so local use is unaffected:

```bash
API_RATE_LIMIT_PER_MINUTE=300   # requests per client per minute
RUN_RETENTION_DAYS=30           # delete finished runs after N days
```

The rate limit counts *HTTP requests*; the caps above count *paid operations*.
A capability URL can be polled without a code, so cheap routes still need a
bound. A validated access code receives its own bucket; all other callers use
the peer address resolved by the ASGI server. The application deliberately does
not trust raw `X-Forwarded-For` or arbitrary code text as identity — trusted
proxy handling belongs in Uvicorn/deployment configuration. `/health` is exempt,
because a throttled health check reads as the service being down.

Retention matters *because* run links are shareable. Reading a run needs only
its id, so a shared link lives exactly as long as the run does, and a visitor
who uploads an unpublished paper otherwise leaves its contents, the extracted
contribution and the resulting assessment on your server indefinitely. Age is
taken from the run id's timestamp rather than the directory mtime, so
rendering a PDF on first download does not quietly extend the life of the runs
people are actually opening; live runs are never deleted. `/health` reports
the window and the web client shows it, since a deletion nobody was told about
reads as data loss rather than as policy.

Every response also carries `Content-Security-Policy`, `X-Content-Type-Options`,
`Referrer-Policy` and `Cross-Origin-Opener-Policy`. The policy needs no
`unsafe-inline`: the client has no inline script, no inline style and no `on*`
attributes, and sets style through CSSOM properties. Report text is model
output plus third-party titles reaching innerHTML, so this is what bounds a
missed escape. HSTS is deliberately absent — Railway terminates TLS ahead of
this process, and an app sending `max-age` for a host it does not control can
outlive its own certificate story.

**What a run cost.** Every run reports its token count per agent, on the
failure path too — a run that crashed halfway still spent whatever it spent.
The web client shows tokens and, where a price is known, an estimate; hover
for the per-agent breakdown and the basis the figure came from.

Tokens are measured. Cost is not: it needs a price this program cannot
verify, so a model the built-in table does not know reports its tokens and no
dollar figure, rather than a `$0.00` that reads as "free". Set
`LLM_PRICE_PER_MTOK=input:output` (USD per 1M tokens, optional third field for
the cache-read rate) to price such a model or correct a stale entry.

**Optional Agent tracing.** An opt-in OpenTelemetry/OpenInference adapter
emits one redacted Trace across source collection, the six CrewAI tasks,
provider SDK calls, and the post-run quality screens. Phoenix is only the OTLP
backend: the files under `outputs/<run_id>/` remain the source of truth, and a
missing collector degrades observability rather than failing a paid report.
Tracing adds no LLM or search calls, never exports the capability-bearing run
id or raw topic, and exposes its `trace_id` and explicit
disabled/active/degraded state through both run endpoints. See
[Agent observability](docs/observability.md) for setup and the data contract.

`API_BYOK_MAX_CONCURRENT` bounds the BYOK share of the shared slots across both
full runs and PDF extraction; it defaults to one below `API_MAX_CONCURRENT`.
BYOK operations skip the daily wallet cap because the visitor pays, but still
consume finite host/provider capacity. This prevents anonymous traffic —
including bad-key failures — from filling every slot and locking out code
holders.

**Handing out a separate code per person:** `ACCESS_CODES` accepts a
comma-separated list instead of one shared value — `ACCESS_CODES=for-alice,
for-bob`. Each code's run history is scoped to itself: the sidebar for
whoever holds `for-alice` only ever shows runs submitted with that same
code, never `for-bob`'s. This is a run-time tag (a hash of the code, written
to each run's directory), not a separate deployment per person — one
process, one `outputs/` directory, codes just partition what `GET /api/runs`
returns. `ACCESS_CODE` (singular) still works for the original one-code-for-
everyone setup; both may be set together.

`ACCESS_CODE_ADMIN` is one further code that authorizes runs like any other
(its own owner tag and paid-operation budget) but is exempt from that same
history filter, so its holder sees every code's runs combined. The daily cap
is likewise per code, including the admin one, rather than one shared total
that an enthusiastic tester could exhaust for everyone else.

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
as it's open. `POST /api/papers` accepts the same BYOK LLM provider/key pair
(the extractor does not need a search key); both upload extraction and full
runs enter the shared paid-operation admission boundary before calling a
provider.

`GET /api/runs` (the run-history list) always stays behind a code
regardless of any of this — opening it up would show every visitor's topics
to every other visitor. Reading or cancelling one specific run by its id
needs no code either way — the id itself carries 128 bits of randomness, the
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

**Attaching a Railway Volume at `/app/outputs`** (so run history survives a
redeploy) surfaces two more platform-specific gotchas once the build itself
is working:

- A freshly attached volume is owned by root regardless of what the image
  `chown`'d at build time — the mount replaces the directory entirely, so the
  non-root `appuser` the container runs as can't write into it.
  `docker-entrypoint.sh` fixes this by starting as root, re-`chown`ing
  `/app/outputs`, then dropping to `appuser` via `setpriv` before `exec`-ing
  into uvicorn (no wrapper process left behind — `tini` still supervises
  uvicorn directly).
- `setpriv` switches the effective uid/gid but does not touch `$HOME`, which
  stays `/root` unless the entrypoint sets it explicitly. Docker's `USER`
  instruction used to do this for free; dropping it for the
  root-then-`setpriv` startup means `docker-entrypoint.sh` has to
  `export HOME=/home/appuser` itself. Left unset, `crewai`'s own chromadb
  storage-path resolution (`appdirs.user_data_dir()`, which expands
  `$HOME/.local/share/<app>`) tries to create a directory under `/root` as
  `appuser` and fails — taking down `/health` and every pipeline run, since
  both import `crewai` and both inherit this process's environment.

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

# Run each topic 3 times, to measure spread rather than a single sample
uv run python benchmark.py --repeat 3 --force --concurrency 3

# Check the scheduling without spending any API credit
uv run python benchmark.py --dry-run --concurrency 3

# Generate summary table and CSV
uv run python benchmark_check.py
```

**Use `--repeat` before concluding that a scoring change did anything.** Market
sources come from live search, so two runs of the same topic see different
evidence and land on different scores — a single run cannot separate "the
pipeline changed" from "the evidence changed". This is not hypothetical: a
rubric edit here was measured against a one-shot re-run, scores moved up on
five topics and down on four, and the result was indistinguishable from noise.
With `--repeat`, `benchmark_check.py` additionally writes
`benchmark_stability.csv` and reports mean, standard deviation, range and
pass-rate per topic, naming the widest spread so it is clear what size of
change is measurable at all. Repetitions are interleaved across the batch, not
run back to back, so a slow window upstream does not land entirely on one topic
and read as that topic being unstable. Repetitions after the first write to a
`__r2`/`__r3` directory; earlier single runs still aggregate, as a sample of one.

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
│   ├── source_pipeline.py   # Structured pre-agent source collection & validation
│   ├── source_clients.py    # API clients (OpenAlex, S2, PubMed, arXiv, Lens, Crossref, Serper)
│   ├── pdf_extractor.py     # Uploaded-paper contribution extraction
│   ├── language.py          # Language detection, free-form search planning, localization
│   ├── llm_config.py        # Multi-LLM config (DeepSeek / OpenAI / Anthropic; JSON mode)
│   ├── run_output.py        # Run ID, report & scorecard persistence; StepEntry TypedDict
│   └── config/
│       ├── agents.yaml      # Agent role definitions + scoring rubrics (6 agents)
│       └── tasks.yaml       # Task requirements & citation rules (6 tasks)
├── web/                     # Static client (HTML + CSS + ES modules)
├── ui/                      # What outlived the Gradio interface: the seven
│   │                        # rendering modules went with it, these three are
│   │                        # independent of any particular front end
│   ├── i18n.py              # Report / scorecard / warning strings (12 languages)
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
│   └── benchmark/           # benchmark.py outputs (benchmark_summary.csv, and
│                            # benchmark_stability.csv when --repeat was used)
├── .env.example             # Environment variable template
├── pyproject.toml           # Project dependencies
└── README.md
```

---

### Tech stack

- **Framework**: CrewAI 1.14.x
- **LLM**: DeepSeek-V3 / OpenAI GPT-4o / Anthropic Claude — auto-detected from API key, or set `LLM_PROVIDER` explicitly
- **Academic sources**: OpenAlex Works API (primary) + PubMed / arXiv domain supplements + Semantic Scholar fallback
- **Patent sources**: optional structured Lens API plus allowlisted WIPO / EPO and aggregator discovery records with provenance-aware credibility
- **Patent / market web search**: Serper or Tavily (3-attempt retry with exponential backoff), auto-selected by which API key is set — see "Deploying publicly" for why there are two
- **Clinical authority coverage**: direct FDA / EMA / ClinicalTrials.gov query planning for applicable topics, surfaced as a non-blocking reliability state
- **Academic metadata**: Crossref API (DOI verification and abstract retrieval)
- **Data validation**: Pydantic v2 + custom guardrails (source structure, citation integrity, report structure, scoring formula, hallucinated source ID detection)
- **Agent observability**: OpenTelemetry + OpenInference instrumentors with redacted content and optional Arize Phoenix OTLP export
- **Web client**: static HTML, CSS and ES modules served by FastAPI — no build step, no framework
- **HTTP API**: FastAPI + Uvicorn, serving both the client and the JSON API (OpenAPI docs at `/docs`)
- **PDF export**: reportlab Platypus (embedded TTFont for CJK; falls back to CID fonts)
- **Container**: Docker multi-stage build (dependency layer cached separately from source), `tini` as PID 1 for subprocess reaping, non-root user, build-time CJK font verification
- **Paid-operation boundary**: validated-code access control, shared concurrency across runs/PDF extraction, per-code daily wallet cap, launch-failure refunds, and a separately bounded BYOK path
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

Detection runs in priority order — biomedical → material_science → clean_tech → software_ai → industrial — by matching keyword markers against the canonical English search topic. The selected profile is stored in `validated_sources.json` and shown as a badge in the UI scorecard.

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

### 在线体验

**https://academic-commercialization-agent.up.railway.app**

已部署在 Railway，无需安装任何环境。门禁提供两个入口：

- **自带 API Key（BYOK）**——不需要访问口令。选择 LLM 供应商、填入自己的 LLM Key 与检索 Key 即可运行，费用记在自己账上。密钥只进入这一次运行的子进程环境变量：不落盘、不并入服务端自身环境、不会被同时运行的其他任务看到，关闭标签页即清除
- **访问口令**——用部署方自己的 Key 运行。口令私下提供；没有口令请用上面的 BYOK 入口

一次运行约 3 分钟，消耗几美分的 LLM 额度加约 9 次检索，因此部署方设有并发上限和每个口令的每日次数上限。两个入口的具体机制见下方「访问控制」。

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

### 实测结果

冻结基线使用实时检索并执行完整六智能体流水线：
**10 个主题 × 每个主题 3 次实时检索运行**。逐行结果随仓库保存在
[`benchmark_summary.csv`](outputs/benchmark/benchmark_summary.csv)。

| 指标 | 结果 |
|---|---|
| 端到端完成 | **30/30** |
| TRL 校准 | **26/30** |
| 加权公式正确 | **30/30** |
| 报告结构完整 | **30/30** |
| 无引用数值行 | **30 份报告中 0 行** |

TRL 校准将评分卡与基于公开里程碑建立、可独立核查的区间进行比较。它属于
校准证据，而不是盲测准确率：这些区间是在观察过早期评分后修订的。
“无引用数值行”也是引用风险代理指标，并不代表系统已经消除了所有形式的
大模型幻觉。

---

### 改造说明

本项目基于 CrewAI 官方模板（researcher + reporting_analyst 两个 Agent）改造而来。

| | 原始 Demo | 本项目 |
|---|---|---|
| Agent 数量 | 2（researcher + reporting_analyst） | 6（专职分工） |
| Task 数量 | 2（research_task + reporting_task） | 6（顺序执行 + guardrail 验证） |
| 工具 | 无 | OpenAlex + PubMed + arXiv + Semantic Scholar + Lens + Serper/Tavily + Crossref |
| 输入变量 | topic + current_year | research_topic |
| 来源收集 | 无 | 运行前结构化检索，含主题规划、来源分级、临床权威覆盖与候选拒绝审计 |
| 输出格式 | 自由文本报告 | 带 [A1][P2][M3] 行内引用 + References 区块的 Markdown 报告 + JSON 评分卡 |
| 输出管理 | 固定文件名（覆盖） | 每次运行生成唯一 ID，存入 outputs/ 目录 |
| 数据质量保障 | 无 | 结构化证据 + 引用完整性校验 + 来源最低字数过滤 + 自动重试 |
| 评分确定性 | — | JSON 模式 Agent 全部 temperature=0，因此**给定同一份证据**时评分可复现。但跨次运行证据本身会变（市场来源走实时检索），所以同一话题重复跑是接近而非完全一致 |
| 评分可追溯性 | — | 每个评分维度标注来源 ID（trl_source_ids / patent_source_ids 等） |

---

### Agent 架构

```
Agent 1: Academic Literature Analyst（学术前沿分析师）
         来源：Step 0 预验证的 OpenAlex / PubMed / arXiv / Semantic Scholar 学术论文
         输出：结构化 EvidenceReport JSON，含技术成熟度、研究突破、引用来源（A1/A2/…）

Agent 2: Patent Landscape Analyst（专利图谱分析师）
         来源：Lens 结构化记录，以及白名单内的 WIPO / EPO / 聚合站记录；
               可信度等级保留记录来自哪条路径
         输出：结构化 EvidenceReport JSON，含专利持有人、空白领域（P1/P2/…）

Agent 3: Market & Competitive Intelligence Analyst（市场情报分析师）
         来源：域名白名单内的市场与权威记录；适用的临床主题会直接检索
               监管机构与临床试验注册库
         输出：结构化 EvidenceReport JSON，含商业玩家、目标行业、市场机会（M1/M2/…）

Agent 4: Technology Commercialization Report Writer（报告撰写师）
         工具：无（以前三个 Agent 输出作为上下文）
         输出：Markdown 报告草稿，含行内引用标注 [A1][P2][M3] 和 References 区块
         校验：章节、正文引用、References 和数字引用完整性，不通过则自动重试（最多 2 次）

Agent 5: Report Reviewer（质量审查员）
         工具：无（以 Agent 4 草稿作为输入）
         规则：6 条规则——引用完整性、无来源数字声明、过度乐观语言、
               专利法律免责措辞、证据一致性、移除正文中的 TRL 数字标签
         输出：有限 JSON 修订计划；代码对已校验草稿应用精确替换，并将实际修改保存至
               reviewer_notes.md。若审查未完成，则原样交付已校验草稿，并在可靠性面板标记回退。

Agent 6: Commercialization Readiness Scorer（量化评分员）
         工具：无（以 Task 1/2/3 结构化证据为输入，独立于报告流程）
         输出：CommercializationScore JSON 评分卡，含 TRL / MRL / 专利 / 市场 / 证据置信度五维评分
         校验：JSON 格式 + 幻觉来源 ID 检测 + 加权公式自动修正，不通过则自动重试（最多 2 次）
```

Agent 1/2/3 并行执行（`async_execution=True`），显著缩短总运行时间。

---

### 执行流程

```
Step 0  来源收集与验证（子进程，在六智能体启动前完成）
        输入：自由描述 → 简洁的英文学术检索主题 + 等价检索短语；
              报告展示仍保留用户原始表述
        学术：OpenAlex Works API（filter=title.search，按引用数降序）
              → PubMed / arXiv 领域补充与 Semantic Scholar 回退
              → 按 DOI 去重，摘要 <100 字符的记录自动剔除
              → 并发 Crossref 引用数补全（ThreadPoolExecutor）
        专利：配置 Key 时优先使用 Lens 结构化 API，否则 Serper/Tavily →
              白名单内 WIPO / EPO / 聚合站记录；WIPO/EPO 网页记录为 high，
              二级聚合网页摘录为 medium
        市场：Serper/Tavily + 域名白名单，剔除低质量站点；临床产品主题优先
              检索 FDA、EMA 与 ClinicalTrials.gov，缺失类别以非阻断警告展示
        元数据：Crossref API 补充 DOI、期刊名、发表日期
        输出 validated_sources.json + status.json 传入子进程流水线
        失败：retrieval_diagnostics.json 保留检索规划与候选拒绝审计

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

> **多语言与自由描述输入**：系统根据用户未改写的原始主题检测输出语言，同时为检索生成简洁的英文主题和等价短语，报告仍保留用户原始表述。支持中文简体/繁体、日文、韩文、德文、法文等 12 种语言；各语言版本的章节标题、引用图例及专利免责声明均自动本地化。

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
- **结果**：评分卡、报告、来源按需加载；检索不足的失败运行会展示独立的“检索诊断”页。引用标记有独立样式——它们是报告可审计的凭据。可导出 Markdown 或 PDF（内嵌 CJK 字体）
- **附加论文**：把 PDF 拖到输入框即成为来源 A1，流水线随后围绕该论文的具体贡献检索证据。论文的 DOI 和 URL 是模型从 PDF 正文里读出来的，因此在被当作引用之前会先做一次解析校验——解析不通过的定位符会被丢弃而不是照样印进参考文献，同时这条来源的可信度降为 `medium` 以如实反映"读者无法自行核查"

界面功能：
- **可靠性面板**：明确区分检索域失败、临床权威来源覆盖不完整、检查未能运行与检查后未发现问题，不把沉默显示成通过
- **实时进度**：Phase 1 并行三个 Agent 的独立状态行 + 已用时间
- **评分卡**：综合分（0–100）+ 五维雷达图 + 条形图，每个维度展示支撑来源 ID 标签（如 `A2` `M1`）；Weight Profile 徽章显示当前使用的评分权重方案
- **来源与权威覆盖**：检索域失败或适用临床主题缺少监管/试验注册来源时显示警告，但不把“没检索到”写成“不存在”
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
| `GET` | `/health` | 存活检查、运行数、共享付费操作容量、已解析的 LLM provider |
| `POST` | `/api/papers` | 上传 PDF 并提取贡献（共享付费容量满时返回 `429`） |
| `POST` | `/api/runs` | 提交评估任务（共享付费容量满时返回 `429`） |
| `GET` | `/api/runs` | 列出历史运行，最新在前 |
| `GET` | `/api/runs/{id}` | 阶段、状态、已用时长、可用产物清单 |
| `DELETE` | `/api/runs/{id}` | 终止运行中的任务 |
| `GET` | `/api/runs/{id}/report` | Markdown 格式的最终报告 |
| `GET` | `/api/runs/{id}/{artifact}` | 运行产物，包括 `scores`、`sources`、自动检查及失败运行的 `retrieval` 诊断 |

共享付费操作并发上限默认为 2（通过 `API_MAX_CONCURRENT` 调整），完整运行与 PDF 在线提取共用这组槽位——真正的瓶颈是上游 Provider 容量而非本机 CPU。超过 30 分钟的运行会被自动终止；PDF 提取无论成功或失败都会释放槽位。

网页客户端与 JSON API 共享同一个 `outputs/` 目录、启动同一个 worker，因此从任一入口发起的运行在另一侧都可见。

**方式三：命令行**

```bash
uv run academic_agent --topic "用于电动汽车的固态电池"
```

每次运行通过 `--topic` 传入研究主题，不需要修改源代码。

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

未达到学术来源最低数量的运行不会生成报告，而会写入
`retrieval_diagnostics.json`。API 与浏览器会展示原始输入、规范化检索主题、
等价短语、候选数量和拒绝审计，让“检索失败”与“没有检查出问题”明确区分。

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

`/api/runs` 与 `/api/papers` 都可能触发真实计费：完整流水线会调用六次 LLM 与检索 API，PDF 核心贡献提取则会在线调用一次 LLM。如果只把链接发给少数面试官或评审，而不是公开运营，`.env` 里的两个开关可以同时封住这两条路径：

```bash
ACCESS_CODE=换成一串足够长的随机字符串          # 拦截所有 /api/ 路由
API_DAILY_PAID_OPERATION_CAP=3                  # 每个口令的付费操作额度
```

`ACCESS_CODE`（或下面的 `ACCESS_CODES`）由 `api/main.py` 中间件校验请求头 `X-Access-Code`；网页只在首次访问时询问并记入 `localStorage`。`/health` 仍对云平台探针开放。所有口令设置都留空（默认）时，门禁完全不生效，本地开发不受影响。

`API_DAILY_PAID_OPERATION_CAP` 是独立的**单进程账单保险丝**：完整评估和 PDF 提取各消耗一个由部署方付费的单位，因此“上传论文再运行”会消耗两个。额度按每个已验证口令分别计算（包括管理员口令）；BYOK 因访客自行付费而豁免。0 表示关闭。旧变量 `API_DAILY_RUN_CAP` 在新变量未设置时仍作为兼容回退。这个账本保存在内存中，因此 UTC 零点或进程重启都会清零；要支持多副本持久计数，需要外部存储。

这个值应按 **LLM 与检索预算中更严格的一项**确定。30 次实测中，完整评估的网页检索中位数为 9 次（区间 5–15）；PDF 提取增加一次 LLM 调用，但不使用搜索 API。Tavily 每月 1000 次免费额度约对应所有口令合计 110 次完整运行；每口令上限兜住的是单个泄漏凭证，而不是所有口令的总花费。

**链接公开之前还值得打开的两个设置**，两个都默认关闭，本地使用不受影响：

```bash
API_RATE_LIMIT_PER_MINUTE=300   # 每个客户端每分钟请求数
RUN_RETENTION_DAYS=30           # N 天后自动删除已完成的运行
```

请求限流计的是 **HTTP 请求数**，上面的容量与每日上限计的是**付费操作**。能力 URL 无需口令即可轮询，所以便宜接口同样需要边界。只有校验成功的访问口令才拥有独立桶；其他请求按 ASGI 服务器解析出的对端地址计数。应用层刻意不直接信任原始 `X-Forwarded-For`，也不会让任意错误口令生成新桶；可信代理应在 Uvicorn/部署层配置。`/health` 豁免，否则限流会被平台误判为宕机。

保留期之所以重要，**正是因为运行链接可以分享**：读取一个运行只需要 id，所以分享出去的链接活多久，取决于那次运行活多久；而一个上传了未发表论文的访客，会把论文内容、提取出的核心贡献、以及据此写成的评估长期留在你的服务器上。计龄用的是 run_id 自带的时间戳而不是目录 mtime，这样首次下载时渲染 PDF 不会给"正在被人打开的运行"偷偷续期；正在执行的运行永不删除。`/health` 会上报保留窗口、前端会显示——没被告知的删除读起来是数据丢失，不是策略。

此外每个响应都带 `Content-Security-Policy`、`X-Content-Type-Options`、`Referrer-Policy` 和 `Cross-Origin-Opener-Policy`。这套策略不需要任何 `unsafe-inline`：前端没有内联脚本、没有内联样式、没有 `on*` 属性，样式通过 CSSOM 逐属性设置。报告正文是模型输出加第三方标题、最终会进入 innerHTML，所以这一层限定的是"万一某处转义漏了，能造成多大后果"。**刻意没有加 HSTS**——Railway 在这个进程之前就终结了 TLS，一个应用给自己并不掌控的域名下发 `max-age`，可能比它的证书方案活得更久。

**一次运行花了多少。** 每次运行按 agent 记录 token 用量，失败的运行也记——跑崩的运行照样花了钱。前端显示 token 数，以及在有价格时显示成本估算；悬停可看逐 agent 明细和这个数字的计价依据。

token 是测出来的，成本不是：它需要一份本程序无法验证的价格。所以内置价格表不认识的模型，只报 token、不报金额，而不是给一个会被读成"免费"的 `$0.00`。要给这类模型定价、或修正一条过期的价格，设置 `LLM_PRICE_PER_MTOK=输入:输出`（美元 / 每 100 万 token，可选第三个字段为缓存读取价）。

**可选的 Agent 链路追踪。** 项目现在可以显式启用 OpenTelemetry/OpenInference：一次运行会把来源采集、六个 CrewAI 任务、模型 Provider SDK 调用和运行后质量检查串成同一条脱敏 Trace，Phoenix 只是可替换的 OTLP 后端。`outputs/<run_id>/` 中的文件仍是事实来源；Collector 不可用只会把可观测性标成 `degraded`，不会让已经付费的报告失败。Trace 不增加 LLM/检索调用，也不上传作为能力令牌的完整 run id、原始话题、Prompt 或模型输出；两个运行接口都会返回同一个 `trace_id` 及 disabled/active/degraded 状态。配置与数据边界见 [Agent observability](docs/observability.md)。

`API_BYOK_MAX_CONCURRENT` 限制 BYOK 流量在完整运行与 PDF 提取之间合计最多占用多少共享槽位，默认比 `API_MAX_CONCURRENT` 少一个。BYOK 不计每日账单额度，因为 token 由访客支付；但它仍消耗有限的主机与 Provider 容量，因此错误 Key 等匿名请求也不能占满所有槽位、挡住口令持有者。

**给每个人发不同的口令：** `ACCESS_CODES` 接受逗号分隔的多个值，而不是一个共用口令——`ACCESS_CODES=给alice的口令,给bob的口令`。每个口令的运行历史都只属于它自己：持有"给alice的口令"的人，侧栏永远只看得到用这个口令跑过的记录，看不到"给bob的口令"跑过的。这只是运行时打的一个标记（口令的哈希值，写进每次运行的目录里），不是给每个人单独跑一套部署——还是一个进程、一个 `outputs/` 目录，口令只是决定 `GET /api/runs` 返回哪些。`ACCESS_CODE`（单数）还是照常可用，对应原来那种所有人共用一个口令的设置；两者可以同时设置。

**第二个开放入口：** `POST /api/runs` 的请求体里也可以带 `llm_provider` / `llm_api_key` / `serper_api_key`，作为任意访问口令的替代——用访客自己的 Key，花费算在他们自己头上，不算在部署方头上。这条路不需要额外的服务端配置：只要配置了口令，网页客户端就会在门禁弹窗里自动多出这个选项；不设口令时它也不会出现，因为没有什么需要绕过。密钥直接进入这一次运行的子进程环境变量——不落盘、不并入服务端自身的环境——所以无论是不是 BYOK，并发的运行之间互相看不到对方的密钥。BYOK 提交的运行不会被打上任何口令标记，所以服务端不会把它记进任何一个口令的历史里；网页客户端转而在 `sessionStorage` 里维护一份访客自己这次会话提交过的运行列表，让侧栏依然能显示自己提交过什么——标签页一关就消失，标签页开着的时候完整可见。`POST /api/papers` 同样接受 BYOK 的 LLM provider/key（提取不需要搜索 Key）；PDF 提取与完整运行都会在调用 Provider 前进入同一付费操作准入边界。

`GET /api/runs`（运行历史列表）无论如何都始终留在口令后面——开放的话会把每个访客的话题暴露给所有其他访客。按 `run_id` 读取或取消某一次具体的运行则不需要口令——`run_id` 本身带 128 位随机性，用的是和"分享一份已完成报告的链接"同一套能力令牌信任模型。

**`ACCESS_CODE_ADMIN`** 是再多的一个口令，授权运行的方式和其他口令完全一样（有自己的归属标记、自己的每日额度），但它不受历史列表过滤的限制——持有这个口令的人能看到所有口令的历史合在一起，用来确认"到底哪几个口令真的被用过"而不用一个个去查。

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

# 每个话题跑 3 次，测的是分布而不是单个样本
uv run python benchmark.py --repeat 3 --force --concurrency 3

# 仅验证调度逻辑，不消耗任何 API 额度
uv run python benchmark.py --dry-run --concurrency 3

# 生成摘要表格并输出 CSV
uv run python benchmark_check.py
```

**判断一次评分改动是否真的起了作用之前，先用 `--repeat`。** 市场来源走实时检索，
同一话题两次运行看到的证据本就不同、分数也会不同——单次运行无法区分"流水线变了"
和"证据变了"。这不是假设：本项目就发生过一次 rubric 改动只做了一次重跑来验证，结果
5 个话题分数上调、4 个下调，和噪声无法区分，等于什么都没测出来。加上 `--repeat` 后，
`benchmark_check.py` 会额外输出 `benchmark_stability.csv`，给出每个话题的均值、标准差、
极差与通过率，并点名波动最大的话题——好让人知道多大的改动才是测得出来的。重复运行
在整批里**交错执行**而非同一话题连跑，避免上游某个时段变慢集中砸在一个话题上、被误读
成该话题不稳定。第 2 次起写入 `__r2`/`__r3` 目录；此前的单次运行仍会作为"样本量为 1"
参与聚合。

话题运行在**独立进程**而非线程中 —— CrewAI 持有全局状态（尤其是 event bus），
同一解释器内跑两个 crew 存在事件流串扰的风险。

并发上限取决于上游 API 限速而非本机 CPU：每个话题以最高 `MAX_RPM`（默认 6）的速率
调用 LLM，外加对 OpenAlex、Serper、Crossref 的突发请求，因此总速率约为
`并发数 × MAX_RPM`。每次运行都会在 `meta.json` 中记录 `rate_limit_hits`，汇总行输出总数
——**只有该值保持为 0 时才可以继续调高 `--concurrency`**。任务启动默认错开 10 秒
（`--stagger`），因为每个话题开头都是同一批来源检索请求的突发。

| # | 话题 | 预期 TRL | 行业 |
|---|------|---------|------|
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
│   ├── source_pipeline.py   # 六智能体启动前的结构化来源收集与验证
│   ├── source_clients.py    # API 客户端（OpenAlex / S2 / PubMed / arXiv / Lens / Crossref / Serper）
│   ├── pdf_extractor.py     # 上传论文的核心贡献提取
│   ├── language.py          # 语言检测、自由描述检索规划、本地化
│   ├── llm_config.py        # 多 LLM 配置（DeepSeek / OpenAI / Anthropic；JSON 模式）
│   ├── run_output.py        # 运行 ID、报告与评分 JSON 持久化；StepEntry TypedDict
│   └── config/
│       ├── agents.yaml      # Agent 角色配置 + 评分 rubric（6 个）
│       └── tasks.yaml       # Task 需求与引用规则（6 个）
├── web/                     # 静态客户端（HTML + CSS + ES 模块）
├── ui/                      # Gradio 界面移除后留下的三个模块：其余 7 个渲染
│   │                        # 模块随之一并删除，这三个与具体前端无关
│   ├── i18n.py              # 报告 / 评分卡 / 警告文案（12 种语言）
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
- **学术来源**：OpenAlex Works API（主力）+ PubMed / arXiv 领域补充 + Semantic Scholar 回退
- **专利来源**：可选 Lens 结构化 API，以及白名单内 WIPO / EPO 与聚合站发现记录，可信度保留来源路径
- **专利 / 市场网页搜索**：Serper 或 Tavily（3 次重试 + 指数退避），按配置了哪个 Key 自动选择——原因见"公网部署"一节
- **临床权威覆盖**：适用主题直接规划 FDA / EMA / ClinicalTrials.gov 查询，以非阻断可靠性状态到达网页
- **学术元数据**：Crossref API（DOI 验证与摘要检索）+ 并发引用数补全
- **数据校验**：Pydantic v2 + 自定义 guardrail（来源结构、引用完整性、报告结构、幻觉来源 ID 检测、评分算法验证）
- **Agent 可观测性**：OpenTelemetry + OpenInference 自动埋点，内容脱敏，可选导出到 Arize Phoenix OTLP 后端
- **网页客户端**：静态 HTML / CSS / ES 模块，由 FastAPI 托管——无构建步骤、无框架
- **HTTP API**：FastAPI + Uvicorn（OpenAPI 文档位于 `/docs`）
- **PDF 导出**：reportlab Platypus（嵌入式 TTFont，支持 CJK；回退至 CID 字体）
- **容器化**：Docker 多阶段构建（依赖层与源码层分离缓存），`tini` 作 PID 1 回收子进程，非 root 运行，构建期 CJK 字体校验
- **付费操作边界**：已验证口令门禁、运行/PDF 提取共享并发、按口令每日账单熔断、启动失败额度回滚，以及独立限额的 BYOK 通道
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

方案检测按优先级顺序进行——biomedical → material_science → clean_tech → software_ai → industrial，通过关键词标记匹配规范化后的英文学术检索主题。选中的方案存入 `validated_sources.json`，并在 UI 评分卡中以徽章显示。

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
