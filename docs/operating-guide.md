# Operating guide

[Project overview](../README.md) · [中文概览](../README.zh-CN.md) · [Evidence status](evidence-status.md)

This guide describes the shipped interfaces, not permission to run a paid
experiment. Frozen experiments have separate identities and authorization gates.

## Local setup and provider selection

Use `uv sync` with Python 3.11/3.12 to reproduce the CI-tested environment.
Copy [the public template](../.env.example) to `.env`; only real execution
requires keys. On PowerShell:

```powershell
Copy-Item .env.example .env
uv sync
```

For Qwen, explicitly set `LLM_PROVIDER=qwen`, `DASHSCOPE_API_KEY` and
`QWEN_MODEL=qwen3.5-plus`. The built-in China-region compatible endpoint is
`https://dashscope.aliyuncs.com/compatible-mode/v1`; operators may override
`QWEN_API_BASE` for their account/region. The browser BYOK endpoint is fixed
by the provider contract rather than accepting arbitrary visitor URLs.

| Provider selector | Key | Optional model / endpoint |
|---|---|---|
| `qwen` | `DASHSCOPE_API_KEY` | `QWEN_MODEL`, `QWEN_API_BASE` |
| `deepseek` | `DEEPSEEK_API_KEY` | `DEEPSEEK_MODEL`, `DEEPSEEK_API_BASE` |
| `anthropic` | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODEL` |
| `openai` | `OPENAI_API_KEY` | `OPENAI_MODEL`, `OPENAI_API_BASE` |

Auto-selection is DeepSeek → Qwen → Anthropic → OpenAI; unused keys do not
force extra model calls, but they can change the selected provider if
`LLM_PROVIDER` is absent. Remove unused template placeholders. Qwen's
`enable_thinking=false` and JSON Object settings are code-owned pipeline
contracts, not optional prompt tweaks.

Set one web-search key: `TAVILY_API_KEY` or `SERPER_API_KEY`; Tavily wins
when both are configured. The project observed Serper rejection from Railway
while the same key worked locally, so an installed key is not a successful
production connectivity check. Provider plans and quotas are not guaranteed
by this repository.

Optional source credentials and their scope are documented in
[.env.example](../.env.example). The experimental credentialed OpenAlex/Lens
adapters are not required to enable production Tool Calling: that path is
not connected. Do not configure or purchase optional keys merely to run tests.

## Web, CLI and HTTP API

```bash
uv run uvicorn api.main:app --reload
# CLI alternative: real provider work, not an offline smoke test
uv run academic_agent --topic "solid-state batteries for electric vehicles"
```

The web client is served at `http://localhost:8000`; OpenAPI is at `/docs`.
HTML/CSS/ES modules in `web/` have no frontend build step. The client supports
topic/PDF submission, optional Decision Context, languages, scoring profiles,
progress, history, scorecard/report/source views, reliability details and
Markdown/PDF export.

Missing Decision Context does not reject a topic. The immutable RunSpec
derives its applicability mode and carries threshold provenance. An exploratory
report must not be presented as an owner-authorized GO/NO_GO instruction.

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Liveness and capacity snapshot; not proof of report quality |
| GET | `/health/ready` | Explicit provider/configuration, output and paid-accounting readiness |
| POST | `/api/papers` | PDF contribution extraction; paid LLM admission applies |
| POST | `/api/runs` | Start an assessment; shared capacity can return 429 |
| GET | `/api/runs` | Owner-filtered run history when access control is enabled |
| GET | `/api/runs/{id}` | State, stage, execution identity and available artifacts |
| GET | `/api/runs/{id}/progress` | Progress plus the same observable runtime contract |
| GET | `/api/runs/{id}/report` | Final Markdown |
| GET | `/api/runs/{id}/{artifact}` | Supported source, score, check and diagnostic artifacts |
| DELETE | `/api/runs/{id}` | Cancel/delete subject to state and ownership rules |
| POST | `/api/runs/{id}/resume` | New immutable recovery child, not mutation of the old result |

For a local, ungated deployment, a JSON POST starts paid work:

```bash
curl -X POST http://localhost:8000/api/runs   -H "Content-Type: application/json"   -d '{"topic":"solid-state batteries for electric vehicles"}'
```

Read `run_id` from the actual response and use it in later requests; example
IDs are not credentials for real runs. On gated deployments, supply an
`X-Access-Code` header or the supported BYOK fields, never put keys or codes
in URLs. Consult the local OpenAPI schemas for exact field validation.

## Artifacts and recovery

Each run writes its own `outputs/<run_id>/` directory. Files depend on how
far the run progressed; a missing report on an early failure is not a completed
assessment.

| Artifact | Meaning |
|---|---|
| `validated_sources.json` | Frozen source registry and scoring profile |
| `academic_evidence.json`, `patent_evidence.json`, `market_evidence.json` | Source-linked findings, claim types, confidence and limitations |
| `commercialization_report.md` | Delivered report |
| `commercialization_scores.json` | Scorecard after deterministic validation |
| `commercialization_report.pdf` | PDF export when generated; CJK-aware embedded font |
| `reviewer_notes.md` | Review changes separate from the main report |
| `status.json`, `steps.jsonl`, `meta.json` | Progress, events and run metadata |
| `terminal.json` | Write-once terminal truth for API runs |
| `evidence_gap_shadow.json` | Optional zero-call gap audit; not new evidence |
| `retrieval_diagnostics.json` | Early retrieval failure diagnostics where applicable |

A source-collection failure exposes canonical query, candidate counts and
rejection reasons instead of silently inventing evidence. Pydantic and local
guardrails validate structure and source identities; advisory checks cannot
guarantee factual entailment.

Failed, cancelled and timed-out runs with a usable retrieval checkpoint may
resume from the longest contiguous verified prefix. The child snapshots the
parent before launch, binds input/evidence/configuration/task/pipeline identity,
and requires fresh credentials. It enters the same admission boundary as a new
run. Successful local checkpoint reuse is not exactly-once external billing.
Read [the recovery design](checkpoint-recovery.md) before changing this path.

API-launched workers apply bounded provider deadlines and disable hidden SDK
retries. Defaults reserve closeout time before the 30-minute watchdog:
150-second ordinary provider calls, a 240-second Reviewer window and a
60-second closeout reserve. Direct CLI runs are operator-controlled and do
not inherit the API watchdog. UI and both run endpoints distinguish terminal
reason, stop method and elapsed time.

Usage snapshots only increase. `complete`, `lower_bound` and `unavailable`
are different accounting facts; an interrupted in-flight call can have spend
that no local counter captured. Cost uses a known price basis or stays
unpriced, rather than showing an unknown model as free. Operators may set
`LLM_PRICE_PER_MTOK=input:output[:cache_read]` in USD per million tokens;
this is an estimate, not an invoice. See
[runtime terminal integrity](runtime-terminal-integrity.md).

## Deploying publicly

Configure access control **before** exposing provider-funded POST routes.
Both an assessment and PDF extraction consume paid capacity.

```dotenv
ACCESS_CODE=replace-with-a-long-random-secret
API_DAILY_PAID_OPERATION_CAP=3
API_RATE_LIMIT_PER_MINUTE=300
RUN_RETENTION_DAYS=30
```

These are example policy values, not a cost/SLO guarantee.

- `ACCESS_CODES` supports multiple comma-separated codes;
  `ACCESS_CODE_ADMIN` additionally sees combined code-owned history.
  Histories are partitioned by hashed owner tags, not separate deployments.
- `API_DAILY_PAID_OPERATION_CAP` is per validated code and UTC day, including
  admin. A PDF followed by an assessment consumes two units. BYOK is exempt
  from operator-funded daily quota but not host capacity. Zero disables the
  cap; legacy `API_DAILY_RUN_CAP` is a fallback when the new name is unset.
- Counts are atomically persisted in
  `outputs/.paid-operation-ledger.json`; restart does not reset that day's
  budget. Unreadable accounting fails closed before paid work.
- `API_MAX_CONCURRENT` bounds the shared run/PDF pool (default two).
  `API_BYOK_MAX_CONCURRENT` bounds the BYOK share and normally reserves a
  slot for code holders. Inspect `/health` for the actual configured values.
- HTTP rate limits are separate from paid-operation counts. Arbitrary code
  text and raw forwarded headers are not trusted bucket identities; proxy
  trust must be configured at the ASGI/deployment boundary.
- Leaving all access-code variables unset disables the gate for local use.
  It is not a safe default for an operator-funded public demo.

### Run links, BYOK and retention

A run ID contains 128 bits of randomness and acts as a read capability.
Code-owned cancel/delete/resume also needs its owner/admin code. Ownerless
BYOK has no second server-side identity, so its run ID is a mutation capability
as well; recovery still needs fresh complete credentials.

BYOK credentials are passed to the individual child environment, not merged
into the operator environment or persisted in run artifacts. Empty sentinels
prevent import-time dotenv loading from restoring operator keys. PDF extraction
uses the same isolated credential contract. The client keeps BYOK history in
session storage; closing a tab removes that client history, **not** an already
running server job or the persisted report.

Raw uploaded PDFs are deleted after successful extraction; unsuccessful uploads
without an accepted paper ID are discarded. Derived metadata and reports remain
subject to retention. Retention uses run timestamps rather than directory mtime,
does not delete live runs, and is visible in the UI. Avoid sharing capability
links or extracted private material unintentionally.

Strict CSP and security headers constrain the static client and report rendering.
They do not replace source validation, access control or retention.

### Docker and Railway

```bash
docker compose up --build
```

Set up the `outputs/` bind mount and runtime `.env` first. API keys must
not be baked into an image. The image uses embedded CJK-compatible TrueType
fonts verified during build, `tini` for process supervision and one Uvicorn
worker. The entrypoint fixes mounted output ownership then drops privileges;
it also sets the non-root HOME needed by dependencies.

On Railway use a persistent volume at `/app/outputs`. The image respects
the platform PORT with a local default of 8000. Its entrypoint and Dockerfile
preserve the deployment workarounds documented in their comments; do not
replace them with a generic multi-worker command.

**Use one replica.** The process registry, task ownership, checkpoint writes
and paid ledger are not distributed transactions. More replicas require shared
transactional state and coordinated ownership before concurrency settings change.
See [Dockerfile](../Dockerfile), [entrypoint](../docker-entrypoint.sh) and
[compose configuration](../docker-compose.yml).

### Optional tracing

OpenTelemetry/OpenInference emits a redacted trace through retrieval, tasks,
providers and post-run screens. Phoenix is an optional collector, not the source
of run truth. Collector errors degrade observability rather than discarding a
paid report; disabled and degraded states remain visible.

The trace contract excludes raw topic/content, prompts, secrets and capability-
bearing run IDs. Tracing adds no model or search requests. Configure the correct
tenant/Space endpoint using [observability.md](observability.md), not an
account-root endpoint copied from an unrelated example.

## Benchmark

The ten advertised topics are identical in [English](../README.md#benchmark)
and [Chinese](../README.zh-CN.md#基准主题), with contracts against
`benchmark.TOPICS` and the committed baseline CSV. Start with the offline
scheduler preview:

```bash
uv run python benchmark.py --dry-run
```

Commands without `--dry-run` can incur search and model costs. A frozen
`--fixtures` evidence replay still calls the model; it is not a free offline
test. Confirm dataset, revision, provider, output destination and budget before
any authorized experiment. Do not overwrite the committed 30-run baseline.

For separately authorized batches, `--only`, `--repeat`, `--concurrency`
and `--force` control selection, repetitions, subprocess parallelism and
reruns. Review `--help` before running: `--force` deliberately disables
completed-run reuse. Benchmark resume is batch scheduling; it is distinct from
a production checkpoint-recovery child.

Evidence varies between live searches. Repeated observations are necessary to
separate output spread from an intervention, but repetition on consumed cases
is not fresh validation. Processes avoid CrewAI global-state cross-talk; more
parallelism can multiply provider RPM and does not guarantee a proportional
speedup. Inspect rate-limit counts before increasing concurrency.
`benchmark_check.py` aggregates formula, structure, TRL and numeric-citation
proxies; none is a substitute for source truth or user value.

## Scoring

The topic-selected profile is persisted with the source registry and displayed
in the scorecard. Domain matching prioritizes biomedical, material science,
clean tech, software/AI, then the industrial default. The exact markers and
rubrics live in [evidence.py](../src/academic_agent/evidence.py).

| Profile | Market | TRL | MRL | Patent | Evidence |
|---|---|---|---|---|---|
| industrial | 35% | 20% | 15% | 20% | 10% |
| biomedical | 25% | 20% | 30% | 15% | 10% |
| material_science | 20% | 30% | 20% | 20% | 10% |
| clean_tech | 25% | 30% | 20% | 15% | 10% |
| software_ai | 40% | 30% | 10% | 10% | 10% |

TRL is on a 1–9 scale, MRL 1–10, and the patent/market/evidence dimensions
1–5. Code recalculates the weighted total on a 100-point scale and retains
supporting source IDs. These profiles express project assumptions, not
independently validated investment utility. The confidence floor is knowingly
asymmetric. Do not change formula, floor or rubrics without confronting the
[measured exclusions](../AGENTS.md#do-not-redo-these).

## Development checks

Use [CONTRIBUTING.md](../CONTRIBUTING.md) for the exact test, Ruff, narrow
Pylint and optional browser commands. If local pytest temporary-root permissions
fail before a fixture can run, use a fresh writable `--basetemp`; do not
ignore warnings, skip assertions or mistake an environment failure for a pass.
