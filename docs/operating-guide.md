# Operating guide

[Project overview](../README.md) · [中文概览](../README.zh-CN.md) · [Evidence status](evidence-status.md)

This guide describes the shipped interfaces, not permission to run a paid
experiment. Frozen experiments have separate identities and authorization gates.

## Local setup and provider selection

Uploaded PDF `candidate_doi` / `candidate_url` fields are unverified locators,
not the document's public identity. A1 uses a synthetic upload identifier until
independent manuscript verification exists. Known extraction failures are
queryable through the receipt even after disconnection; receipt storage failure
still means unresolved, never permission for automatic resend. See the
[PDF/quantity/receipt contract](results-2026-09-11-pdf-numeric-receipt-seams.md).

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
| `anthropic` | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODEL`, `ANTHROPIC_API_BASE` |
| `openai` | `OPENAI_API_KEY` | `OPENAI_MODEL`, `OPENAI_API_BASE` |

Auto-selection is DeepSeek → Qwen → Anthropic → OpenAI; unused keys do not
force extra model calls, but they can change the selected provider if
`LLM_PROVIDER` is absent. Remove unused template placeholders. Qwen's
`enable_thinking=false` and JSON Object settings are code-owned pipeline
contracts, not optional prompt tweaks.

The factory and auxiliary planning/translation share model, key and endpoint
resolution. Endpoints require HTTPS without credentials/query/fragment; a known
vendor endpoint cannot contradict the selected provider. Explicit BYOK ignores
operator model/base settings, including SDK base defaults. Auxiliary requests
refuse redirects and keep their visible untranslated fallback on failure.
The installed CrewAI Anthropic extra is required for that advertised provider.
See [the routing regression](results-2026-09-10-provider-and-log-boundaries.md).

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

The scorecard explicitly labels market-estimate comparability as not assessed.
Fresh/restored score artifacts include `market_comparison`; the raw
`market_uncertainty` string remains a legacy untyped diagnostic, not verified
USD data. A missing or null flag must not be called a comparison pass. The
historical numeric cap and existing report prose are unchanged. See the
[delivery contract](results-2026-09-11-market-score-delivery-disclosure.md).

New production-validated scores additionally carry `market_cap_audit`: the
normalized pre/post market score, actual market-point deduction, trigger and
reason. Triggered at an original 3.0 remains 3.0, with zero deduction; triggered
at 5.0 becomes 3.5, with 1.5 deducted. These are arithmetic observations, not
verified comparable market estimates or overall-score point deductions.
The browser validates the receipt against the saved score and flag. Historical
missing/inconsistent receipts remain unavailable; no old score is migrated or
recalculated. See [numeric/cap provenance](results-2026-09-12-numeric-token-and-cap-provenance.md).

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

In the **Sources** tab, enter a whole source ID such as `A1` or `[A1]` for
an exact match, or a literal keyword to search saved titles, publishers and
text. Search is case-insensitive and stays in this panel; it does not call a
model or search provider. Clear restores the list. Expand a source to read its
complete saved `evidence_summary`, including preserved whitespace. That field
may be a cleaned or truncated abstract, search snippet or fallback description:
it is **not paper full text or proof that a report claim is supported**.

Missing files, failed reads, empty lists and no keyword matches are distinct.
Malformed or oversized records leave an incomplete-search warning while healthy
records remain available. The display examines at most 1,000 records, admits at
most 16,384 UTF-16 units per text field and 2 Mi UTF-16 units in total, and shows
50 matches per page. These are post-JSON display limits, not HTTP-byte or JSON
parsing memory limits; search covers all admitted records, not only one page.
The existing run-read capability and artifact endpoint are unchanged. This
read-only viewer neither enables experimental Tool Calling nor rewrites saved
reports, citations or evidence.

The [saved-source entry lab](saved-source-entry.md) is separate from this shipped
viewer. It uses an explicit independent app factory and new assets, defaults to
disabled selection, and is not mounted or advertised by the production app.
Its scripted browser test has no native provider; billing and durable locator
receipts are not implemented. Do not configure keys or expose it as a paid route.

The [prepared backend controller](saved-source-paid-controller.md) has separate
shared-admission and locator-receipt logic, but is not connected to this lab or
the deployed application. It does not enable model calls, accept BYOK credentials
or provide a new public endpoint. Existing run/PDF receipt APIs are unchanged.

Its separate [receipt entry](saved-source-receipt-entry.md) is also an unmounted
factory, with its own browser and explicit GET recovery after a lost response.
It stores a random receipt key before submission, not the code or report text;
uncertain responses do not unlock another POST. The closed RQ experiment used a
fixed-case native adapter, not a generally configured provider or public feature
flag to activate on Railway.

The separate [usage delivery entry](saved-source-usage.md) adds an opt-in,
operation-bound accounting envelope and isolated page. It retains reported token
counts, unknown observations, estimate basis and reservation as separate facts.
It does not mount new production routes, discover provider keys or reopen RQ.
These original lab routes remain absent from the public application. A distinct,
default-off production wrapper is described below; it does not mount those apps.

### Optional saved-source locator

The production wrapper has a separate page, `/source-locator`, and separate
routes: `POST /api/runs/{run_id}/source-locator` and
`GET /api/source-locator/receipts`. They are absent with the default configuration.
Enabling the entry and allowing new executions are separate controls; receipt-only
mode retains manual recovery without starting another selection. Shipping this
code does **not** enable the feature or authorize a new provider experiment.

The sidebar entry follows the current report through client-side navigation,
including switching between reports; leaving the report clears its old ID.
Only a valid run ID is carried in the URL fragment, never an access code or
receipt key. This prefill is a convenience, not ownership or consent. A browser
history-write failure must not leave the link pointing at the previous report.

This is a source locator, not a question-answering agent. One bounded Qwen
request chooses at most one source ID from the saved title catalog or declines.
The catalog admits at most 32 entries, 256 Unicode code points per title and
6,144 ASCII JSON bytes. Returned/omitted counts and clipped-title counts remain
visible; a decline is not proof that the complete report has no relevant source.
The server then returns the exact saved excerpt, at most 1,500 Unicode code
points. It does not search, supplement evidence, modify the report, judge support
or generate a second answer. The existing Sources keyword/ID search remains free.

Execution requires both a currently valid access code and a readable report-owner
marker matching that code. A shared report URL, admin read privilege, historical
ownerless report or BYOK report cannot select operator funding. Owners are not
backfilled to make old examples eligible. The initial feature does not accept
BYOK, arbitrary providers, model names or endpoints.

The page explicitly asks before sending the unchanged question and saved source
IDs/titles to `qwen3.5-plus`. Report prose, saved excerpts and the access code are
not sent to that model. Native request journals contain question/title text and
therefore have bounded retention; they must not be described as hash-only logs.
The POST also requires `X-Source-Locator-Consent: question-catalog-v1`, alongside
`X-Access-Code` and `Idempotency-Key`. GET observes an existing receipt without
the consent header, key discovery, another admission or another model request.

Only the random receipt key is saved in tab-session storage before POST. Missing
consent or disabled execution creates no local intent. Refresh does not resend;
the user re-enters the code and explicitly queries the existing receipt. Unknown
delivery keeps resubmission blocked. Input changes invalidate consent and late
results. A changed, missing or unreadable saved registry cannot silently select
again to repair an old receipt.

The new entry preserves the strict `saved_source_receipt_usage_v1` envelope.

After receipt validation, the production page displays a fixed, readable reason
for a failed receipt without requiring expansion of its JSON. The explanation
does not override terminal state, clear an unresolved intent, alter accounting
or claim the failure was free. Reset/new observations clear stale explanations;
provider exception text is never interpolated into this notice.

Unknown usage is not zero; reservations, frozen-rate estimates and provider
invoices remain separate. Accounting damage does not hide an otherwise valid
saved excerpt. Report relevance and semantic support are still not assessed by
the runtime. Earlier RUQ's four-case observation remains a development result,
not independent accuracy, user benefit or public activation.

Use the explicit disabled settings in [.env.example](../.env.example) as the
configuration reference. New execution also requires valid finite feature
budgets and the existing shared paid-operation limits. Disabling execution is
the rollback path: retain the entry for authorized receipt GETs, drain actual
threads and preserve journals. Do not delete a ledger to enable a retry.
The deployment remains single-process/single-replica, with no provider-level
exactly-once, distributed quota or hard shutdown-time guarantee.

`SOURCE_LOCATOR_ENABLED` controls route/page registration;
`SOURCE_LOCATOR_EXECUTION_ENABLED` permits new attempts only when
`SOURCE_LOCATOR_DAILY_REQUEST_CAP`, `SOURCE_LOCATOR_DAILY_USD_CAP` and
`SOURCE_LOCATOR_MIN_INTERVAL_SECONDS` are valid and positive. Both switches
default false and all three limits default zero. Limits are global to this
single-process locator; unknown attempts retain their reservations. The USD
ceiling is an engineering reservation policy, not a provider-side spending cap.
Changing deployment environment requires a fresh process. No flag is enabled
by this implementation or its intercepted browser tests.

For TLS-terminating deployments where the backend sees HTTP, explicitly set
`SOURCE_LOCATOR_PUBLIC_ORIGIN` to the single browser-facing origin, for example
`https://academic-commercialization-agent.up.railway.app`. This setting affects
only the production locator routes, page and whitelisted assets. It does not
change Uvicorn, global proxy trust or the frozen lab helpers. Unset or exactly
empty retains ASGI-scheme + Host origin comparison; an invalid nonempty value
fails closed rather than reverting to that mode. Invalid configuration disables
execution and returns `503 execution_unavailable` for otherwise valid locator
requests, including page/asset and receipt-only access. Correct the pin while
keeping execution off; do not erase a receipt to work around this error.

The pin accepts one ASCII HTTP(S) origin, with an optional port in 1..65535.
Scheme/DNS case, IPv6 address spelling and omitted/default ports are compared
canonically. The production parser deliberately rejects URL-repair ambiguities:
userinfo, paths (including a trailing slash), even empty `?`/`#` delimiters,
whitespace/control characters, lists/commas, wildcard hosts, trailing DNS dots,
IPv6 zone IDs and malformed/abbreviated numeric addresses. This stricter syntax
is intentional; it is not a claim that every frozen parser decision is identical.
The original raw Host must match the configured hostname and effective public
port. A present Origin must match the configured scheme, hostname and effective
port. Missing Origin remains supported for existing non-browser/receipt clients,
but never removes the configured Host check. Duplicate critical headers, header
budgets, exact JSON media/body rules, explicit POST consent and current-code/
owner authorization remain enforced before paid admission. `Forwarded` and
`X-Forwarded-*` values cannot select either authority, even if they claim HTTPS.

Keep this valid pin during receipt-only rollback. It is configuration, not proof
of TLS or authentication: the operator still owns the HTTPS edge and backend
exposure, and non-browser callers can supply Host/Origin themselves. No access
code, budget or execution permission follows from a matching origin. Only the
locator page's trailing-slash route has an explicit relative
`307 Location: /source-locator`, so a backend HTTP scheme cannot downgrade that
page redirect; unrelated application's redirects remain unchanged.

The [2026-09-23 qualified origin repair](results-2026-09-23-source-locator-public-origin.md)
records the original rejected pilot separately from offline engineering checks.
For the new browser seam, run
`uv run --group e2e python -m e2e.source_locator_production_smoke --proxy`.
The original command without `--proxy` retains the direct same-origin journey.
The proxy journey uses a real Chromium HTTPS origin with intercepted loopback
HTTP upstream requests, not a real TLS proxy or a paid provider validation.

The separate [2026-09-26 production acceptance](results-2026-09-26-production-source-locator-acceptance.md)
observed one native selection, exact saved-text delivery and unchanged receipt
accounting after execution closure and redeployment. New paid execution was
closed again with zero feature budgets. This prepared case is not a general
accuracy claim or permission to keep the feature enabled; original POST-body
capture was unavailable, while the delivered DOM and actual GET were compared.

Both health endpoints expose optional `source_locator` configuration observations,
separate from the existing maintenance result enum. These are not checks of the
provider credential, remaining allowance or model connectivity. When an active
operation defers cleanup, `deferred_maintenance` records that observation without
erasing the prior failure or refreshing its completion time. Cleanup advances a
durable clock watermark separately from admission spacing, so pruning cannot
reopen a consumed day after clock rollback or indefinitely delay the next call.

The implementation's Windows/Python 3.12 whole-tree regression passed 6,916 tests
and 1,619 subtests with 90.32% coverage, against the unchanged 85% floor. Seven
zero-provider Chromium journeys passed. The new main-app journey checked both
health endpoints, transfer consent before intent, one intercepted native POST
and paid admission, lost acknowledgement, then exact-text/accounting recovery
by GET after execution was closed. Independent review and defect reinjection
covered the health, clock, deferred-maintenance, malformed-code and consent
seams. These are offline engineering observations, not another native experiment,
provider exactly-once proof or production activation; CI/deployment are separate
release checks.

PDF extraction responses and stored metadata include `input_coverage` with the
actual scanned/included/truncated/omitted pages and character budget. This is
sampling visibility, not full-paper reading or section-level understanding.
`locator_status` describes a text candidate or conflict, not a verified paper
identity; reachable upload locators no longer imply high credibility. See the
[input and identity contract](results-2026-09-10-evidence-pdf-terminal-boundaries.md).

The composer permits one in-flight submission and one serial PDF extraction,
never both at once. It preserves an existing topic when a paper is attached;
only an empty topic is auto-filled. A second upload during extraction is rejected
locally without another paid POST. Clearing a selection invalidates its response
but does not cancel provider work or release the lock before the request settles.
These composer locks are tab-local. First-party paid requests additionally use
the durable receipt contract below. Requests are not automatically retried; a
lost acknowledgement does not prove no run started.

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
| GET | `/api/receipts` | Read an acceptance receipt using the `Idempotency-Key` header; never dispatches work |
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
last timeout/paper/retention/receipt checks. Initial `not_checked` is not success;
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

Read `maintenance.cleanup.papers` and `maintenance.cleanup.retention` for
the last attempt's scanned/deleted/skipped/failed counts and fixed reason
categories. Legacy `checks=ok` means the operation returned normally, not
that every directory was deleted. Detail states distinguish complete, partial,
disabled, absent, not_checked and unavailable. No scan has null counts;
an empty completed scan has zero counts. Interrupted enumeration retains
observed lower-bound counts with `scan_complete=false`; a root failure is not
counted as an invented failed entry. Results remain paired with the last
completion clock while another attempt is running. Per-entry failures do not
abort peers or evict paid workers. See [cleanup counts and limits](results-2026-09-07-cleanup-outcome-observability.md).

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

Progress readers should pass `steps_next_cursor` back as `since`: it counts
complete physical log lines, including rejected rows, not returned events.
`steps_read_state=partial/unavailable` warns about the optional log without
changing task completion or blocking the report. Incomplete trailing rows are
held until newline publication. See the [delivery contract](results-2026-09-08-client-delivery-seams.md).

Score, grounding and consistency tabs validate downloaded display fields rather
than defaulting missing data to zero or agreement. This neither rewrites stored
artifacts nor changes scoring/heuristics. Healthy report tabs remain usable.
Normalized dimensions accept fractions in 1..maximum, not just rubric integers.

If browser storage is denied, credentials can be held only in page memory and
preferences use safe defaults. Bookmark accepted run links. A failed persistent
logout returns to the gate without reloading stale credentials; clear site data
before reopening when prompted. This does not erase inaccessible storage, revoke
capability URLs, or stop work on the server.

Malformed saved BYOK requires explicit credential selection before any paid
request; a residual access code is not an automatic fallback payer. Logout waits
for run, resume and PDF acknowledgements, then clears old attachment/context.
Do not treat closing a tab or aborting a request as provider cancellation.

Access-code selection is document-local after its first read: another tab's
login/logout does not change an open page's payer or history identity. A new
document reads the latest persisted code. A late/candidate 401 cannot clear a
newer local choice; logout preserves a different shared selection and returns
to an explicit gate instead of reloading into it. This is not global logout;
revoke credentials server-side if all open documents must lose access.
Compare-before-remove is not a storage transaction. Forced refresh/close can
still lose a paid reply. Opt-in receipt lookup can recover retained acceptances,
but losing its tab-session key or denying storage still loses lookup ability.
See the [verified identity boundary](results-2026-09-08-browser-access-identity.md).

The first-party composer now writes a constant, credential-free tab-session
warning before analysis, resume or PDF extraction. Refresh after an unconfirmed
request blocks new paid submissions and exposes a persistent warning. Check
saved receipts/history or contact the operator before explicitly acknowledging the risk; the
button only unlocks new intent and never retries or cancels. BYOK history may
not contain a lost run; PDF results can now be found through retained receipts. Read-only
navigation still works. Denied storage is explicitly memory-only; closing the
session or clearing storage can remove the warning. The warning alone is not
server idempotency or a guarantee against duplicate charges. See the
[tested refresh/settlement boundary](results-2026-09-08-paid-refresh-warning.md).

A progress read failing or exceeding its 15-second deadline shows either no
confirmed observation or a stale last state, separate from the worker outcome.
Successful polling clears the warning; 404 stops polling. Other read requests
do not acquire this deadline except receipt lookup's separately bounded GET;
browser suspension can delay timers. See the
[combined boundary contract](results-2026-09-08-client-boundary-combinations.md).

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

New usage payloads explicitly identify `accounting_scope=crew_nodes`, excluded
stages and `end_to_end_cost_complete=false`. Planning, translation, inline PDF
extraction and source retrieval are not collected here; exclusion is not proof
that a stage executed or was free. The browser displays this scope even when
the recorded nodes are fully priced; old payloads say the scope was not recorded.
Malformed/negative/nonfinite rate overrides retain the existing table fallback
but emit `invalid_price_override` without echoing configuration values. Overflow
or an entirely unpriced collection is unknown, never zero. Temporal completion
remains independent of scope and price validity. See the
[cost and benchmark contract](results-2026-09-10-cost-scope-and-benchmark-identity.md).

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

Upload preprocessing has a separate two-slot, single-process limit. Before
multipart parsing, the entire request is capped at 51 MiB (50 MiB PDF plus
1 MiB overhead), with 30-second idle and 120-second total body receive limits.
The per-file 50 MiB cap and BYOK/code authentication still apply. A 429 with
`upload_capacity` is not a daily quota charge; no extraction has started.
Preprocessing slots release after local copying, before LLM work.

Cancelling an HTTP waiter does not kill its extraction thread: that thread
still owns raw-file finalization. If cancellation arrives after successful
finalization, derived metadata may remain until the 24-hour pending-paper
expiry. Hard process death/storage failure remains a maintenance boundary;
cleanup failure is logged, not represented as successful erasure. History
refreshes are generation-bound and logout clears visible capability lists;
previously shared capability URLs are not thereby revoked. See the
[verified boundaries](results-2026-09-08-upload-history-cancellation-boundaries.md).

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

## Paid-request receipts

The shipped browser sends a new `Idempotency-Key` on each explicit analysis,
PDF extraction or recovery-child request. It stores only the random key and
operation in tab-session storage before dispatch, never the submitted topic,
PDF bytes or provider credentials. When a reply is lost or a document refreshes,
use **Find saved receipts (read only)**, then explicitly open the recovered run
or attach the recovered paper. This performs GETs only. Unknown/missing/unreadable
results are not proof of zero cost; acknowledging the warning is not a retry.

Direct HTTP clients may opt in with `v1.<UTC epoch seconds>.<64 random hex
characters>` (256 bits from a cryptographically secure generator). Initial
admission requires a timestamp within five minutes; replays and lookup expire
24 hours after that timestamp. Keep the same key, normalized input and BYOK
credentials for the same intent. A changed payload/operation is 409, unresolved
reservation is 409, expired key is 410, unavailable/full storage is 503. A
committed acceptance replays its original result without another worker/model
call. An original rejection retains its category, including distinct 429 causes;
`failed` does not mean unbilled. Clients omitting the header retain the legacy
non-idempotent contract. The browser never automatically retries a POST.

`GET /api/receipts` takes that same header, not a query parameter. Code-owned
receipts require the same currently valid access code (or administrator access).
Ownerless BYOK has no second server-side identity: treat the receipt key as a
private read capability like a run URL. Do not publish it in logs, links or traces.
Responses are `no-store`. `pending` means unresolved in this process;
`unknown` means its originating process is gone, not proof of execution or loss.
An intended resource ID can be present before a process was actually started.

The journal is `outputs/.paid-receipts.sqlite3`, included in the existing durable
output volume. It has a 5,000-row active bound and independent expiry maintenance;
readiness detects an existing unreadable/missing-schema journal. Do not delete,
replace or restore the live ledger as a retry mechanism. A whole lost volume or
restored old backup is outside the guarantee. Save/restore it consistently with
other run artifacts. SQLite transactions do not make quota/worker ownership
multi-process safe: keep one API process and one replica.

For the separate synthetic volume-copy/read rehearsal and the prerequisites
for an operator-led restore, see [offline volume restoration](offline-volume-restore.md).
That rehearsal is not a backup service, a latest-snapshot detector or permission
to replace live storage. A readable old copy cannot establish what was billed
after it was captured; all paid entry points must remain closed during a real
restore assessment, not only the saved-source locator.

Stored keys are hashed; input/credential identity uses a keyed fingerprint.
Accepted run responses contain the run ID/topic within the receipt lifetime.
PDF receipts contain only the paper ID and read its existing metadata store;
an expired/deleted result gives 410 and does not trigger extraction. The real
extraction thread retains completed derived metadata after HTTP abandonment;
raw PDF deletion and queued-abandonment protections remain in force. Expiry
does not control independent filesystem backups or provider retention.

Denied browser storage is visibly memory-only, so a fresh document cannot
recover those entries. Logout clears this tab's receipt keys; closing the tab,
clearing storage, losing keys or using a different origin can lose lookup
ability. This is bounded acceptance idempotency, not provider-level exactly-once,
automatic safe resend, automatic workflow recovery or a global cross-tab lock.
See the [offline result and fault coverage](results-2026-09-10-durable-paid-receipts.md).

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
fresh measurements. New assessment batches live in
`outputs/benchmark-runs/<experiment-id>/`; `--experiment-id` names a new batch,
otherwise a unique ID is generated. `--force` never overwrites an existing
batch and cannot combine with `--resume-batch`.

`--resume-batch <id>` requires the same selected cases, raw fixture bytes,
source contents, commit, dependency lock/installed versions, Python/platform,
exact provider/model and recorded runtime settings. Each worker rechecks the
identity before paid dispatch. Intact successful units are reused without
another call; occupied failed/partial/corrupt units are refused, not retried.
Unstarted units can execute. A new measurement requires a new batch. Live-mode
reuse refers to the stored evidence snapshot, not a fresh search of today's web.
Benchmark resume is batch scheduling, not a production recovery child or
provider-level exactly-once guarantee. Credentials are not in manifests;
optional source credentials/contact settings are recorded only as presence.

`uv run python benchmark_check.py --batch <id>` reads that batch and exports
a new directory under `outputs/benchmark-summaries/`, with identity columns in
the CSV. Omitting `--batch` reads the historical archive but still creates a new
summary export; it does not replace the committed calibration CSVs. Neither
summary analysis nor `--dry-run` calls providers. `--freeze` remains a separately
authorized live retrieval/capture command; it is not an immutable assessment
batch or a free operation.

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
