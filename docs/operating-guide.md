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

The composer permits one in-flight submission and one serial PDF extraction,
never both at once. It preserves an existing topic when a paper is attached;
only an empty topic is auto-filled. A second upload during extraction is rejected
locally without another paid POST. Clearing a selection invalidates its response
but does not cancel provider work or release the lock before the request settles.
These are tab-local protections, not cross-tab/server idempotency. Requests are
not automatically retried; a lost acknowledgement does not prove no run started.

An accepted BYOK run opens even if its optional session-history write fails;
the UI asks the user to bookmark the capability URL. Resume exclusion is keyed
by parent run across language/poll re-renders in that tab. Transport loss or a
truncated successful paid response is explicitly an unknown acknowledgement,
not evidence that no billable operation began; BYOK history may lack that run.

Missing Decision Context does not reject a topic. The immutable RunSpec
derives its applicability mode and carries threshold provenance. An exploratory
report must not be presented as an owner-authorized GO/NO_GO instruction.
At save time, the code-owned applicability paragraph is reasserted from that
gate; a marker in model text cannot suppress it. Legacy reports with no gate
are not relabelled. This protects the reserved metadata paragraph, not the
semantic correctness of all report prose; see the
[delivery regression and limits](results-2026-09-06-report-applicability-authority.md).

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
| DELETE | `/api/runs/{id}?intent=cancel` or `?intent=delete` | Only the requested operation, subject to state and ownership rules |
| POST | `/api/runs/{id}/resume` | New immutable recovery child, not mutation of the old result |

Readiness performs an isolated real-file write per request; concurrent probes
do not share a filename. A cleanup-only failure is named separately from a
write failure. This is local readiness, not provider connectivity or model
quality verification. See the [maintenance contract](results-2026-09-06-maintenance-readiness-query-audit.md).

`/health.maintenance` separately reports the managed background task and its
last timeout/paper/retention checks. Initial `not_checked` is not success;
`running` describes task liveness, not a complete artifact audit. Each stage
recovers only after its next successful cycle. A cleanup exception is logged
and advisory; it does not remove timeout supervision or trigger unhealthy
readiness on its own. A failed managed watchdog or failed timeout stage makes
`/health/ready` return 503. Offline `readiness()` has no ASGI task prerequisite.
Shutdown attempts worker cleanup even if awaiting the supervisor raises.

Process waits and cleanup run off the ASGI loop, one maintenance stage at a
time. Graceful shutdown drains the current stage, including after repeated
cancellation, before stopping remaining workers. No later stage is dispatched
after that cancellation. A stuck filesystem can still delay this drain and
the next watchdog cycle: neither shutdown duration nor check freshness has an
SLO. See the [offline scheduling verification](results-2026-09-06-maintenance-event-loop.md).

Both HTTP health endpoints expose `maintenance.observed_at` (snapshot UTC time)
and per-stage `timings`. `current_started_at`/`current_elapsed_seconds` describe
an unfinished dispatch, including queueing/drain; `last_started_at`,
`last_finished_at`, `last_duration_seconds` and `last_finished_age_seconds`
describe its last completed attempt. `checks` keeps that completed result
while a new attempt is in flight. Unknown facts are null, not zero; UTC labels
can shift with clock corrections, while durations/ages use monotonic time.
Use task state and observation age together: a past `ok` is not proof of current
freshness. There is no new stale cutoff or automatic readiness failure based
on age. Standalone configuration-only `readiness()` leaves maintenance null.
See the [exact field meanings and verification](results-2026-09-07-maintenance-observation-age.md).

Concurrent PDF uploads share a process-wide PDFium parsing/closure mutex;
their subsequent LLM calls remain under normal paid admission, not that mutex.
PDF export uses a bounded per-run striped lock and sibling-file atomic publication.
Failed renders do not become downloadable caches; obvious old header/trailer-
incomplete caches are rebuilt on demand. This does not establish arbitrary PDF
validity, distributed locking or interruption of a stuck native parser. See the
[maintenance verification](results-2026-09-06-maintenance-runtime-paid-delivery.md).

The LLM readiness check validates the selected supported provider and its effective
non-empty credential using the same resolver as operator LLM construction. It
preserves legacy `OPENAI_API_KEY` fallback for Qwen/DeepSeek and does not expose
key values. It cannot verify balance, endpoint connectivity or report quality.

Admission errors retain their HTTP 429 and string `detail` for existing clients.
An additive `X-Error-Code` distinguishes `concurrency_limit` (wait for capacity),
`daily_quota_exceeded` (00:00 UTC reset), and `rate_limited` (short wait, existing
`Retry-After` guidance). The first two cover run, recovery and paper endpoints.
The browser translates known reasons and keeps the original detail for unknown
or legacy errors rather than calling every 429 a full slot. See the
[composer/configuration regression](results-2026-09-06-composer-paid-operation-integrity.md).

For a local, ungated deployment, a JSON POST starts paid work:

```bash
curl -X POST http://localhost:8000/api/runs   -H "Content-Type: application/json"   -d '{"topic":"solid-state batteries for electric vehicles"}'
```

Read `run_id` from the actual response and use it in later requests; example
IDs are not credentials for real runs. On gated deployments, supply an
`X-Access-Code` header or the supported BYOK fields, never put keys or codes
in URLs. Consult the local OpenAPI schemas for exact field validation.

Always specify mutation intent. `intent=cancel` never deletes a report:
an inactive retained run returns 409, so refresh its status. `intent=delete`
never cancels a live run: that conflict also returns 409. Invalid explicit
values return 422; a missing run remains 404. For compatibility, omitting
intent still uses the legacy cancel-or-delete behaviour, so older callers
must adopt the parameter to avoid stale clicks changing the operation.

Starting or already-stopping runs also return 409 to a Cancel request; refresh
status instead of issuing a competing stop. A failed process stop returns a
sanitized 503 and retains the run and its capacity slot. Active counts include
launch reservations and stop finalization, not just executing subprocesses.
While external termination/terminal publication is owned, status stays Running,
progress stays unfinished, and Delete/retention cannot remove the artifacts.
This is single-process ownership, not provider cancellation or guaranteed audit
durability during a storage fault. See the
[stop-ownership contract](results-2026-09-06-run-stop-ownership.md).
Unknown or not-yet-read states do not expose mutation buttons in the shipped
client; a BYOK history read error is Unknown, not a failed worker.
See the [request and browser verification](results-2026-09-06-run-mutation-intent.md).

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

The PDF-domain market prelude shares the ordinary query path's previous/current
calendar-year window. This avoids stale hard-coded years, not stale results in
general. The report-audit detail tab displays individual coverage counts and
abstention reasons; missing or malformed detail is unreadable, not a clean
report. Its read-only validation neither repairs the artifact nor blocks report
access. The heuristic remains English-only even when the UI is Chinese.

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

The status/progress read projection isolates malformed reliability summaries
through `audit_metadata_unreadable`: the affected panel row says it cannot be
read, while a valid committed outcome and saved report remain available.
Absent historical fields remain distinct from a corrupt summary. This does
not rewrite artifacts or validate every nested schema; see the
[exact read contract](results-2026-09-05-nested-audit-metadata-integrity.md).

Likewise, `runtime_metadata_unreadable` identifies unreadable selected usage,
accounting, checkpoint or recovery summaries in the run header. Bad usage
shows unavailable, not a zero bill; readable usage with bad accounting is only
a lower bound. A malformed recovery list cannot be counted as reused stages
or used to display Resume. This does not repair storage or establish actual
recovery eligibility; see the [runtime-summary contract](results-2026-09-05-runtime-summary-read-integrity.md).

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
