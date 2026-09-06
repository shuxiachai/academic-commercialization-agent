"""FastAPI application exposing the analysis pipeline over HTTP.

Serves both the JSON API and the web client (web/) from one process, and
launches each run as a `pipeline_worker` subprocess writing to its own run
directory — so the API, the browser and the CLI all observe the same run
through the same files rather than through shared memory.

    uv run uvicorn api.main:app --reload
    → http://localhost:8000       (web client)
    → http://localhost:8000/docs  (OpenAPI)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import threading
import time
from collections.abc import AsyncIterator
from pathlib import Path

from dotenv import load_dotenv
from fastapi import (
    FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

# Load .env before anything reads os.environ. Some dependency imports also
# happen to load it, but that is a side effect to observe, not a configuration
# contract — an API server should be explicit about when its settings exist.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from academic_agent.llm_config import _detect_provider  # noqa: E402
from academic_agent.pdf_extractor import (  # noqa: E402
    PaperContribution,
    extract_paper_contribution,
)
from api import access, papers, runs  # noqa: E402  — must follow load_dotenv
from api.models import (  # noqa: E402
    BYOK_PROVIDERS,
    HealthStatus,
    PaperExtraction,
    ReadinessStatus,
    ResumeRunRequest,
    RunAccepted,
    RunList,
    RunProgress,
    RunRequest,
    RunStatus,
    StepEvent,
)

_LOGGER = logging.getLogger(__name__)
_REAP_INTERVAL_SECONDS = 30


async def _reaper() -> None:
    """Kill runs that exceed the deadline.

    No request remains open for the lifetime of a run, so timeout enforcement
    belongs to this application-level loop rather than to a polling endpoint.
    """
    while True:
        await asyncio.sleep(_REAP_INTERVAL_SECONDS)
        for run_id in runs.reap_timeouts():
            print(f"[api] run {run_id} killed: exceeded {runs.TIMEOUT_SECONDS}s")
        # Pending paper records would otherwise accumulate independently of
        # run retention. Raw PDFs are already removed after extraction; this
        # bounds the lifetime of the short-lived extraction capability.
        removed = papers.prune_old()
        if removed:
            print(f"[api] pruned {removed} expired paper upload(s)")
        expired = runs.prune_expired_runs()
        if expired:
            print(f"[api] deleted {len(expired)} run(s) past the "
                  f"{runs.RUN_RETENTION_DAYS}-day retention window: "
                  f"{', '.join(expired[:5])}"
                  + (" ..." if len(expired) > 5 else ""))


@contextlib.asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(_reaper())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        # Never leave orphaned workers burning API credits.
        runs.shutdown_all()


app = FastAPI(
    title="Academic Commercialization Assessment API",
    description=(
        "Submit a research topic, poll for progress, retrieve the report and "
        "scorecard. The web client and CLI execute the same six-agent pipeline."
    ),
    version="2.0.0",
    lifespan=_lifespan,
)


# Response headers applied to everything this app serves.
#
# The web client makes a strict policy affordable: it has no inline <script>,
# no inline <style>, no on* attributes, and loads every asset from its own
# origin — so none of the usual 'unsafe-inline' escape hatches are needed, and
# adding one later would be a signal that something regressed. Report text is
# model output plus third-party titles and URLs reaching innerHTML, so this is
# the layer that limits what a missed escape could do.
#
# style-src stays strict deliberately: the client sets individual properties
# (el.style.height = ...), which CSSOM permits under CSP; only cssText and
# style attributes would need an exception, and neither is used.
_SECURITY_HEADERS = {
    "Content-Security-Policy": "; ".join((
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",          # data: covers the inline SVG favicon
        "connect-src 'self'",
        "form-action 'self'",
        "base-uri 'none'",
        "frame-ancestors 'none'",        # clickjacking, and supersedes X-Frame-Options
        "object-src 'none'",
    )),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # Reports link out to third-party sources; keep those tabs from reaching back.
    "Cross-Origin-Opener-Policy": "same-origin",
}


# Per-client request budget, refilled continuously (token bucket).
#
# Distinct from the paid-operation concurrency and daily caps: this counts
# *requests*, and exists because the endpoints that cost nothing to serve are
# the ones an unauthenticated caller can reach. A run id
# is a capability URL, so anyone holding one can poll a run as fast as they
# like; the gate itself (/api/access/check) is likewise open by construction,
# since rejecting a wrong code is what it is for. Neither is expensive per
# call, and both are unbounded without this.
#
# Generous on purpose. The client polls progress every 1.2-4s during a run and
# capacity once a second, so a person with two tabs open is already near 100
# requests/minute through normal use; this is sized to stop scripted abuse
# without ever touching that.
_RATE_LIMIT_REQUESTS = int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "300"))
_RATE_LIMIT_WINDOW = 60.0

_rate_buckets: dict[str, tuple[float, float]] = {}   # client -> (tokens, last refill)
_rate_lock = threading.Lock()


def _client_key(request: Request) -> str:
    """Who to charge for this request.

    A *validated* access code gets its own bucket so people behind one campus
    NAT do not throttle each other. Arbitrary header text must never become an
    identity: changing an invalid code would otherwise mint a fresh bucket.

    The address comes from request.client, after any trusted-proxy handling by
    the ASGI server. Reading X-Forwarded-For again here would bypass that trust
    decision and let a direct caller choose a new address on every request.
    """
    matched = access.matching_code(request.headers.get("x-access-code"))
    if matched:
        return f"code:{access.owner_id(matched)}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


def _rate_limit_exceeded(key: str) -> bool:
    """Spend one token for `key`; True when the bucket is empty.

    A bucket refills continuously rather than resetting on a fixed boundary,
    so a caller cannot save up a burst by waiting for the top of a window.
    """
    if _RATE_LIMIT_REQUESTS <= 0:            # 0 disables the limit entirely
        return False
    now = time.monotonic()
    rate = _RATE_LIMIT_REQUESTS / _RATE_LIMIT_WINDOW
    with _rate_lock:
        tokens, last = _rate_buckets.get(key, (float(_RATE_LIMIT_REQUESTS), now))
        tokens = min(float(_RATE_LIMIT_REQUESTS), tokens + (now - last) * rate)
        if tokens < 1.0:
            _rate_buckets[key] = (tokens, now)
            return True
        _rate_buckets[key] = (tokens - 1.0, now)

        # Drop buckets that have refilled completely; they carry no state a
        # new one would not reproduce. Without this the dict is a slow leak
        # keyed by every address that ever called.
        if len(_rate_buckets) > 2048:
            full = _RATE_LIMIT_REQUESTS - 0.5
            for k, (t, seen) in list(_rate_buckets.items()):
                if k != key and t + (now - seen) * rate >= full:
                    del _rate_buckets[k]
    return False


@app.middleware("http")
async def _rate_limit(request: Request, call_next):
    """Bound request volume per client.

    The /health endpoints are exempt: platform health checks poll them on
    their own schedule and must never be throttled into reporting the service
    as down. Matched by prefix so /health/ready is covered — it is the one the
    container healthcheck actually polls, and a 429 there would restart a
    perfectly healthy container.
    """
    if not request.url.path.startswith("/health") and _rate_limit_exceeded(_client_key(request)):
        return JSONResponse(
            {"detail": "Too many requests. Slow down and retry shortly."},
            status_code=429,
            headers={"Retry-After": "10"},
        )
    return await call_next(request)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    """Attach the response headers above to every response.

    Deliberately not HSTS: that is the platform's to set. Railway terminates
    TLS ahead of this process and already redirects http→https, and an app
    that sends max-age on a host it does not control can outlive its own
    certificate story.
    """
    response = await call_next(request)
    for name, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


@app.middleware("http")
async def _access_gate(request: Request, call_next):
    """Reject ungated requests before they reach any endpoint.

    Runs ahead of routing, so a missing/wrong code never gets as far as
    starting a worker or spending a search-API call. Three exceptions:

    - /health — costs nothing; platform load balancers poll it without a header.
    - POST /api/runs and POST /api/papers — both authorize themselves with
      either the code or bring-your-own-key credentials in the body. That
      decision needs the parsed body, which a middleware does not cheaply
      have — for /api/papers the body is a multipart upload, less cheaply
      still.
    - /api/runs/{id}/... routes bypass this global list gate because reads
      use the run id as a capability. Their mutating handlers independently
      verify ownership before cancellation, deletion, or a paid child resume.
      Keeping that decision in the handler also lets resume parse fresh BYOK
      credentials without consuming and rebuilding the request body here.
      GET /api/runs itself stays gated because it lists deployment history.
    """
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)
    if path in ("/api/runs", "/api/papers") and request.method == "POST":
        return await call_next(request)
    if path.startswith("/api/runs/"):
        return await call_next(request)

    matched = access.matching_code(request.headers.get("x-access-code"))
    if access.gate_enabled() and matched is None:
        return JSONResponse({"detail": "Missing or invalid access code."}, status_code=401)
    # Which code answered, if any — GET /api/runs uses this to show each
    # code holder only the runs made under their own code. None means
    # "don't filter": with the gate disabled there is no code to scope by
    # (matching the single-tenant behaviour from before multiple codes
    # existed), and the admin code deliberately opts out of scoping so its
    # holder sees every code's history at once.
    request.state.is_admin = matched is not None and access.is_admin(matched)
    if request.state.is_admin:
        request.state.owner = None
    else:
        request.state.owner = access.owner_id(matched) if matched else None
    return await call_next(request)


def _authorize_run_mutation(run_id: str, http_request: Request) -> None:
    """Require proof of ownership before mutating or restarting a run.

    The access-gate middleware exempts /api/runs/{id}/... so a report link
    can be shared without an access code. That exemption is right for reads
    and insufficient for cancellation, deletion, or a paid recovery child,
    which is why each mutating handler calls this check explicitly.

    Raises 404 rather than 403 on a mismatch: a distinct "forbidden" would
    confirm to a caller probing ids that a given run exists. Capability URLs
    are credentials, but their entropy is not a reason to leak their validity.
    """
    if not access.gate_enabled():
        return                      # nothing configured to authorize against

    matched = access.matching_code(http_request.headers.get("x-access-code"))
    if matched is not None and access.is_admin(matched):
        return

    try:
        owner = runs.owner_of(run_id)
    except runs.OwnerMarkerUnreadable as exc:
        # Missing means an intentionally ownerless capability; unreadable means
        # authorization could not be established. Returning 503 keeps those
        # states distinct without reflecting the filesystem error or marker.
        _LOGGER.exception("Run ownership metadata could not be read for %s", run_id)
        raise HTTPException(
            status_code=503,
            detail="Run authorization is temporarily unavailable. Retry later.",
        ) from exc
    if owner is None:
        # A BYOK run carries no owner tag by design, and its submitter holds
        # no code to prove ownership with — the id is the only credential
        # that exists for it, so it stays the credential here too. Nothing
        # else in the deployment references these runs.
        return

    if matched is None or access.owner_id(matched) != owner:
        raise HTTPException(status_code=404, detail=f"No run with id {run_id}")


@app.get("/api/access/check", include_in_schema=False)
def access_check() -> dict:
    """No-op the frontend calls to validate a code before storing it.

    Reaching this handler at all means the middleware already accepted the
    header — there is nothing left to verify here.
    """
    return {"ok": True}


_WEB_ROOT = Path(__file__).resolve().parents[1] / "web"

# Mounted before the API routes are declared below only in source order; the
# router matches /api/* first regardless, because StaticFiles is mounted at a
# sub-path rather than at "/". The SPA entry point is served explicitly.
if _WEB_ROOT.is_dir():
    app.mount("/static", StaticFiles(directory=_WEB_ROOT / "static"), name="static")

    @app.get("/", include_in_schema=False)
    @app.get("/history", include_in_schema=False)
    @app.get("/run/{run_id}", include_in_schema=False)
    def _spa(run_id: str = "") -> FileResponse:
        """Serve the single page for every client-side route.

        Routing happens in the browser, so a deep link must return the same
        document rather than a 404 — the client reads the path and renders the
        matching view.
        """
        return FileResponse(_WEB_ROOT / "index.html", media_type="text/html")


@app.get("/health", response_model=HealthStatus, tags=["meta"])
def health() -> HealthStatus:
    """Liveness, shared paid-operation capacity, and resolved LLM provider.

    `llm_provider` is null when no key is configured — a run submitted in that
    state will start but fail inside the worker, so check this first.
    """
    # Reuse the pipeline's own resolution so this never disagrees with what a
    # run would actually use (it handles LLM_PROVIDER and the legacy
    # OPENAI_API_BASE-pointing-at-DeepSeek setup).
    try:
        provider = _detect_provider()
    except RuntimeError:
        provider = None

    # One locked snapshot prevents a worker finishing between two reads from
    # producing the impossible-looking state
    # active_paid_operations < active_runs.
    active_runs, active_paid_operations = runs.capacity_counts()
    return HealthStatus(
        status="ok",
        # Keep active_runs for clients and operators that specifically care
        # about subprocesses. Capacity indicators must use the broader value:
        # an inline PDF extraction holds the same slot even though it has no
        # run id and never appears in the worker registry.
        active_runs=active_runs,
        active_paid_operations=active_paid_operations,
        max_concurrent=runs.MAX_CONCURRENT,
        retention_days=runs.RUN_RETENTION_DAYS,
        llm_provider=provider,
    )


def readiness() -> ReadinessStatus:
    """Everything a submitted run needs before it can get past its first minute.

    Split out of the endpoint so the checks can be exercised without HTTP, and
    so each one is a named string rather than a count — an operator staring at
    a deploy that will not go healthy needs to know which check failed.
    """
    # _detect_provider is imported at module scope, not here. Importing
    # llm_config pulls in crewai, which calls load_dotenv() as a side effect —
    # so a lazy import inside this function would repopulate os.environ from
    # .env part-way through the very checks that are reading it, and report
    # keys the running process does not actually have.
    checks: dict[str, str] = {}

    try:
        provider = _detect_provider()
        checks["llm"] = "ok"
    except RuntimeError as exc:
        provider = None
        checks["llm"] = str(exc).splitlines()[0]

    # Retrieval has no fallback: without a web search key the pipeline raises
    # SourceCollectionError before the first agent runs. Which of the two is
    # configured decides who is billed and how results are shaped, so it is
    # reported rather than reduced to a boolean.
    search = ("tavily" if os.getenv("TAVILY_API_KEY")
              else "serper" if os.getenv("SERPER_API_KEY") else None)
    checks["search"] = "ok" if search else (
        "no web search key: set SERPER_API_KEY or TAVILY_API_KEY")

    # A read-only outputs volume is the failure this catches that the other two
    # cannot: every key is right, the page loads, and each run dies at its
    # first write. Probed with a real file rather than os.access, which reports
    # the permission bits and not what the filesystem will actually allow.
    try:
        runs.DEFAULT_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        probe = runs.DEFAULT_OUTPUT_ROOT / ".readiness"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        checks["outputs"] = "ok"
    except OSError as exc:
        checks["outputs"] = f"outputs directory is not writable: {exc}"

    # A malformed paid-operation ledger makes every operator-funded request
    # fail closed at admission. Treating that state as ready would route users
    # to an instance that cannot do its primary job. The check is conditional:
    # when the daily cap is disabled there is no ledger contract to satisfy.
    if runs.DAILY_CAP:
        try:
            runs.validate_paid_ledger()
            checks["paid_accounting"] = "ok"
        except runs.PaidLedgerUnavailable:
            # Do not expose the output path or parser details. Operators need
            # the failed boundary; clients do not need filesystem internals.
            checks["paid_accounting"] = (
                "paid-operation accounting is unavailable; paid work is blocked"
            )

    return ReadinessStatus(
        ready=all(v == "ok" for v in checks.values()),
        checks=checks,
        llm_provider=provider,
        search_provider=search,
    )


@app.get(
    "/health/ready",
    response_model=ReadinessStatus,
    tags=["meta"],
    responses={503: {"description": "The container is running but cannot complete an assessment"}},
)
def health_ready(response: Response) -> ReadinessStatus:
    """Readiness, as distinct from liveness — 503 when a run would fail.

    /health answers "is this process alive", which a load balancer needs, and
    it returns 200 for a container that serves every page and fails every run.
    That gap was real: the Docker healthcheck asserted in a comment that such a
    container would be reported unhealthy, and it was not, because it only
    checked that /health returned at all.
    """
    status = readiness()
    if not status.ready:
        response.status_code = 503
    return status


@app.post(
    "/api/runs",
    response_model=RunAccepted,
    status_code=202,
    tags=["runs"],
    responses={
        401: {"description": "Neither the access code nor complete bring-your-own-key credentials were provided"},
        429: {"description": "Concurrency or daily paid-operation limit reached"},
    },
)
def submit_run(request: RunRequest, http_request: Request) -> RunAccepted:
    """Queue an assessment. Returns immediately with a run_id to poll.

    Run time is provider-bound and may take several minutes; the 30-minute
    watchdog is the hard availability boundary. Authorized either by the
    X-Access-Code header (billed to the deployment) or by supplying
    llm_provider/llm_api_key/serper_api_key in the body (billed to the
    caller) — not gated by the middleware because that choice needs the
    parsed body.
    """
    matched = access.matching_code(http_request.headers.get("x-access-code"))
    # matched is None both when no code was configured at all (nothing to
    # check against — must not block) and when one was configured but this
    # request's code was missing/wrong (must block unless BYOK) — gate_enabled()
    # is what tells those two apart.
    if matched is None and not request.byok and access.gate_enabled():
        raise HTTPException(
            status_code=401,
            detail="Provide the access code, or your own llm_provider/llm_api_key/serper_api_key.",
        )
    # BYOK runs get no owner tag at all — never recorded in anyone's history,
    # billed to the requester, gone once the tab closes (frontend keeps its
    # own session-only list; see web/static/js/app.js).
    owner = access.owner_id(matched) if matched and not request.byok else None

    paper_json_path: str | None = None
    if request.paper_id:
        try:
            paper_json_path = str(
                papers.extraction_path_for_run(request.paper_id, owner=owner)
            )
        except papers.PaperNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    byok = (
        runs.BYOKCredentials(request.llm_provider, request.llm_api_key, request.serper_api_key)
        if request.byok else None
    )

    try:
        run_id, _ = runs.start_run(
            topic=request.topic,
            language=request.language,
            weight_profile=request.weight_profile,
            paper_json_path=paper_json_path,
            decision_context=request.decision_context,
            byok=byok,
            owner=owner,
        )
    except runs.ConcurrencyLimitReached as exc:
        raise HTTPException(
            status_code=429,
            detail=f"{exc}. Retry once another paid operation finishes.",
        ) from exc
    except runs.DailyCapReached as exc:
        raise HTTPException(
            status_code=429,
            detail=f"{exc}. The daily paid-operation budget resets at 00:00 UTC.",
        ) from exc
    except runs.PaidLedgerUnavailable as exc:
        _LOGGER.exception("Paid-operation accounting blocked run admission")
        raise HTTPException(
            status_code=503,
            detail=(
                "Paid-operation accounting is temporarily unavailable. "
                "No provider call was started; retry later."
            ),
        ) from exc
    except OSError as exc:
        _LOGGER.exception("Failed to start analysis worker")
        raise HTTPException(
            status_code=500,
            detail="The analysis worker could not be started. Retry later.",
        ) from exc

    return RunAccepted(
        run_id=run_id,
        state="running",
        topic=request.topic,
        assessment_mode=request.assessment_mode,
    )

@app.post(
    "/api/runs/{run_id}/resume",
    response_model=RunAccepted,
    status_code=202,
    tags=["runs"],
    responses={
        401: {"description": "Fresh access-code or BYOK credentials are required"},
        404: {"description": "Unknown run_id or caller does not own the source run"},
        409: {"description": "Run is active, completed, or has no resumable checkpoint"},
        429: {"description": "Concurrency or daily paid-operation limit reached"},
    },
)
def resume_run(
    run_id: str,
    request: ResumeRunRequest,
    http_request: Request,
) -> RunAccepted:
    """Start an immutable child that reuses only validated source checkpoints.

    A resume is a new paid operation, not an in-place process restart. The
    failed source remains untouched for audit, fresh credentials cross the
    subprocess boundary, and the worker independently validates every content
    hash before skipping a node. A stale or corrupt prefix therefore falls
    back to execution rather than becoming an unearned successful recovery.
    """
    _authorize_run_mutation(run_id, http_request)
    matched = access.matching_code(http_request.headers.get("x-access-code"))
    if matched is None and not request.byok and access.gate_enabled():
        raise HTTPException(
            status_code=401,
            detail="Provide the access code, or fresh BYOK credentials to resume.",
        )
    owner = access.owner_id(matched) if matched and not request.byok else None
    byok = (
        runs.BYOKCredentials(
            request.llm_provider, request.llm_api_key, request.serper_api_key
        )
        if request.byok
        else None
    )

    try:
        child_id, child_directory = runs.resume_run(
            run_id, byok=byok, owner=owner
        )
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except runs.RunNotResumable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except runs.ConcurrencyLimitReached as exc:
        raise HTTPException(
            status_code=429,
            detail=f"{exc}. Retry once another paid operation finishes.",
        ) from exc
    except runs.DailyCapReached as exc:
        raise HTTPException(
            status_code=429,
            detail=f"{exc}. The daily paid-operation budget resets at 00:00 UTC.",
        ) from exc
    except runs.PaidLedgerUnavailable as exc:
        _LOGGER.exception(
            "Paid-operation accounting blocked resume for run %s", run_id
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "Paid-operation accounting is temporarily unavailable. "
                "No provider call was started; retry later."
            ),
        ) from exc
    except OSError as exc:
        _LOGGER.exception("Failed to resume analysis worker for run %s", run_id)
        raise HTTPException(
            status_code=500,
            detail="The analysis worker could not be resumed. Retry later.",
        ) from exc

    # Read from the child's frozen contract rather than trusting status.json;
    # the worker may not have produced its first status write before this 202.
    child_spec = runs.RunSpec.load(child_directory)
    return RunAccepted(
        run_id=child_id,
        state="running",
        topic=child_spec.topic,
        assessment_mode=child_spec.assessment_mode,
        resumed_from=run_id,
    )



@app.get("/api/runs", response_model=RunList, tags=["runs"])
def list_runs(http_request: Request, limit: int = Query(default=50, ge=1, le=200)) -> RunList:
    """List runs, newest first — scoped to the calling code's own history.

    `request.state.owner`/`.is_admin` were set by the access-gate
    middleware, which ran ahead of this handler for every path that isn't
    POST /api/runs or /api/runs/{id}/...; this path falls into neither, so
    both are always set (owner to None when the gate is disabled entirely,
    meaning no filter).
    """
    try:
        summaries, total = runs.list_runs(
            limit=limit, owner=http_request.state.owner
        )
    except runs.OwnerMarkerUnreadable as exc:
        # Omitting the affected entry would make a protected run look absent;
        # labelling it ownerless would expose it to the admin view incorrectly.
        # Fail the snapshot explicitly and preserve the storage detail in logs.
        _LOGGER.exception("Run history ownership metadata could not be read")
        raise HTTPException(
            status_code=503,
            detail="Run history is temporarily unavailable. Retry later.",
        ) from exc
    if http_request.state.is_admin:
        # An unlabelled merge of everyone's history answers "what ran" but
        # not "who ran it" — the entire reason to hold the admin code
        # rather than just leaving the gate unfiltered for everyone.
        for summary in summaries:
            summary["owner_label"] = access.label_for_owner(summary.pop("_owner", None))
    else:
        for summary in summaries:
            summary.pop("_owner", None)
    return RunList(runs=summaries, total=total)


@app.get(
    "/api/runs/{run_id}",
    response_model=RunStatus,
    tags=["runs"],
    responses={404: {"description": "Unknown run_id"}},
)
def get_run(run_id: str) -> RunStatus:
    """Current stage and state. Poll this while `state` is `running`."""
    try:
        return RunStatus(**runs.get_state(run_id))
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete(
    "/api/runs/{run_id}",
    tags=["runs"],
    responses={
        404: {"description": "Unknown run_id"},
        409: {"description": "Run is mid-cancellation from a concurrent request — retry"},
    },
)
def delete_run(run_id: str, http_request: Request) -> dict:
    """Stop a live run, or permanently delete a finished one's record.

    A live run is only terminated (kept, marked cancelled) so its partial
    progress stays inspectable — call this again once it has stopped to
    actually remove it. A run that is already completed, failed, cancelled,
    or timed out is deleted immediately: its directory, report, and every
    other artifact are gone for good, not just hidden from the list.

    Unlike the read endpoints on this same path prefix, this one is NOT a
    capability URL. Knowing a run_id is enough to read a run — that is the
    deliberate report-sharing model — but it must not be enough to destroy
    one: run ids travel through browser history, screenshots and forwarded
    links, and a reader who was handed a report link should not thereby be
    able to delete it out from under its owner.
    """
    _authorize_run_mutation(run_id, http_request)

    try:
        runs.cancel_run(run_id)
        return {"run_id": run_id, "action": "cancelled"}
    except runs.RunNotFound:
        pass  # not live — fall through to an actual delete

    try:
        runs.delete_run(run_id)
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except runs.RunStillActive as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        _LOGGER.exception("Failed to delete run %s", run_id)
        raise HTTPException(
            status_code=500,
            detail="The run could not be deleted. Retry later.",
        ) from exc
    return {"run_id": run_id, "action": "deleted"}


@app.get(
    "/api/runs/{run_id}/report",
    response_class=PlainTextResponse,
    tags=["artifacts"],
    responses={
        200: {"content": {"text/markdown": {}}},
        409: {"description": "Run has not produced a report yet"},
    },
)
def get_report(run_id: str) -> PlainTextResponse:
    """The final Markdown report."""
    try:
        state = runs.get_state(run_id)
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    path = runs.artifact_path(run_id, "report")
    if path is None:
        raise HTTPException(
            status_code=409,
            detail=f"No report available; run state is '{state['state']}'.",
        )
    return PlainTextResponse(
        path.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
    )


@app.get(
    "/api/runs/{run_id}/progress",
    response_model=RunProgress,
    tags=["runs"],
    responses={404: {"description": "Unknown run_id"}},
)
def get_progress(run_id: str, since: int = Query(default=0, ge=0)) -> RunProgress:
    """Status plus new step events, for a client polling during a run.

    `since` is the number of step events the client already has; only later
    ones are returned. Without it a client would re-receive the whole log on
    every tick, which grows to hundreds of lines over a run.

    Registered before /api/runs/{run_id}/{artifact} because that route would
    otherwise match "progress" as an artifact name.
    """
    try:
        state = runs.get_state(run_id)
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return RunProgress(
        run_id=run_id,
        state=state["state"],
        status_record_state=state.get("status_record_state"),
        audit_metadata_unreadable=state.get("audit_metadata_unreadable", []),
        runtime_metadata_unreadable=state.get("runtime_metadata_unreadable", []),
        stage=state.get("stage", ""),
        topic=state.get("topic", ""),
        pipeline_revision=state.get("pipeline_revision"),
        # Unknown is retryable, not evidence that execution finished.
        done=state["state"] in {"completed", "failed", "cancelled", "timeout"},
        error=state.get("error"),
        elapsed_seconds=state.get("elapsed_seconds"),
        source_counts=state.get("source_counts"),
        evidence_incomplete=state.get("evidence_incomplete", False),
        failed_domains=state.get("failed_domains", []),
        output_language=state.get("output_language", "English"),
        # Threaded explicitly, like every other field here. That is the flaw
        # this pair of lines is fixing: RunStatus builds itself with
        # RunStatus(**get_state(...)) and picks up new keys automatically,
        # while this constructor names each one, so a field added to
        # get_state() reaches one endpoint and silently not the other.
        # test_api_contract.py now fails when they diverge.
        usage=state.get("usage"),
        usage_accounting=state.get("usage_accounting"),
        runtime_budget=state.get("runtime_budget"),
        terminal=state.get("terminal"),
        claim_grounding=state.get("claim_grounding"),
        authority_coverage=state.get("authority_coverage"),
        component_coverage=state.get("component_coverage"),
        evidence_gap_shadow=state.get("evidence_gap_shadow"),
        decision_gate=state.get("decision_gate"),
        report_audit=state.get("report_audit"),
        quality_review=state.get("quality_review"),
        consistency=state.get("consistency"),
        observability=state.get("observability"),
        checkpointing=state.get("checkpointing"),
        recovery=state.get("recovery"),
        steps=[StepEvent(**s) for s in runs.read_steps(run_id, since=since)],
        artifacts=state.get("artifacts", []),
    )


#: Read the body in pieces so an oversized upload is refused partway rather
#: than after it is entirely in memory. The previous code did `await
#: file.read()` and only then compared the length, so a 2 GB body was
#: allocated in full before being rejected — the check ran, but only once the
#: damage it was meant to prevent had already happened.
_UPLOAD_CHUNK = 1024 * 1024


async def _read_capped(file: UploadFile, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise papers.PaperTooLarge(
                f"Upload exceeds the {limit // 1024 // 1024} MB limit"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _extract_paper_with_paid_reservation(
    pdf_path: str,
    *,
    owner: str | None,
    byok: bool,
    llm_provider: str | None,
    llm_api_key: str | None,
) -> PaperContribution:
    """Extract while the actual worker thread owns the paid-operation slot.

    asyncio cancellation stops awaiting ``to_thread`` but cannot stop its
    underlying thread. Keeping the reservation in the request coroutine would
    therefore publish a free slot while the provider call was still running.
    The worker thread instead releases it only when extraction really exits.
    """
    with runs.reserve_inline_paid_operation(owner=owner, byok=byok):
        return extract_paper_contribution(
            pdf_path,
            llm_provider=llm_provider if byok else None,
            llm_api_key=llm_api_key if byok else None,
        )


@app.post(
    "/api/papers",
    response_model=PaperExtraction,
    tags=["papers"],
    responses={
        413: {"description": "File exceeds the size limit"},
        429: {"description": "Concurrency or daily paid-operation limit reached"},
        422: {"description": "PDF could not be parsed into a contribution"},
    },
)
async def upload_paper(
    http_request: Request,
    file: UploadFile = File(...),
    llm_provider: str | None = Form(default=None),
    llm_api_key: str | None = Form(default=None),
) -> PaperExtraction:
    """Extract a paper's contribution from an uploaded PDF.

    Returns the extraction and a paper_id. Pass that id to POST /api/runs to
    anchor a run on the paper; the fields are editable first, since the topic
    the model derives is a starting point rather than an answer.

    Authorized like POST /api/runs and for the same reason: by the access code
    header, or by bringing your own key. This endpoint makes an LLM call, so it
    cannot simply be opened — but leaving it gated by the code alone meant a
    visitor using their own keys could run a topic assessment and not attach a
    paper, which is half of an advertised path. Supplying the two credentials
    bills the extraction to whoever supplied them.

    Runs the extractor in a worker thread: it makes an LLM call and would
    otherwise block the event loop for several seconds.
    """
    credential_fields = (llm_provider, llm_api_key)
    if any(credential_fields) and not all(credential_fields):
        raise HTTPException(
            status_code=422,
            detail="llm_provider and llm_api_key must be provided together or both omitted.",
        )
    if llm_provider is not None and llm_provider not in BYOK_PROVIDERS:
        raise HTTPException(
            status_code=422,
            detail=f"llm_provider must be one of {BYOK_PROVIDERS}.",
        )
    byok = bool(llm_provider)
    matched = access.matching_code(http_request.headers.get("x-access-code"))
    if matched is None and not byok and access.gate_enabled():
        raise HTTPException(
            status_code=401,
            detail="Provide the access code, or your own llm_provider/llm_api_key.",
        )
    owner = access.owner_id(matched) if matched and not byok else None

    try:
        data = await _read_capped(file, papers.MAX_UPLOAD_BYTES)
    except papers.PaperTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    try:
        paper_id, pdf_path = papers.save_upload(data, owner=owner)
    except papers.PaperTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except papers.PaperNotAPdf as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    try:
        contribution = await asyncio.to_thread(
            _extract_paper_with_paid_reservation,
            str(pdf_path),
            owner=owner,
            byok=byok,
            llm_provider=llm_provider,
            llm_api_key=llm_api_key,
        )
    except runs.ConcurrencyLimitReached as exc:
        papers.discard(paper_id)
        raise HTTPException(
            status_code=429,
            detail=f"{exc}. Retry once another paid operation finishes.",
        ) from exc
    except runs.DailyCapReached as exc:
        papers.discard(paper_id)
        raise HTTPException(
            status_code=429,
            detail=f"{exc}. The daily paid-operation budget resets at 00:00 UTC.",
        ) from exc
    except runs.PaidLedgerUnavailable as exc:
        papers.discard(paper_id)
        _LOGGER.exception("Paid-operation accounting blocked paper %s", paper_id)
        raise HTTPException(
            status_code=503,
            detail=(
                "Paid-operation accounting is temporarily unavailable. "
                "No provider call was started; retry later."
            ),
        ) from exc
    except Exception as exc:  # noqa: BLE001 - provider failures vary by SDK
        # The upload is unreachable from here on — no paper_id reaches the
        # client, so no run can name it — and it is somebody's unpublished
        # paper. Deleted now rather than left for the day-long pruner.
        papers.discard(paper_id)
        _LOGGER.exception("Paper contribution extraction failed for %s", paper_id)
        raise HTTPException(
            status_code=422,
            detail=(
                "The paper could not be converted into a structured contribution. "
                "Retry or use another PDF."
            ),
        ) from exc

    payload = contribution.model_dump()
    try:
        papers.save_extraction(paper_id, payload)
    except OSError as exc:
        # A successful response promises the raw PDF has been deleted. If the
        # atomic extraction write or privacy cleanup failed, remove the whole
        # capability instead of returning an id with ambiguous retention.
        papers.discard(paper_id)
        _LOGGER.exception("Paper extraction storage failed for %s", paper_id)
        raise HTTPException(
            status_code=500, detail="Could not safely store the paper extraction."
        ) from exc
    return PaperExtraction(paper_id=paper_id, **payload)


@app.get(
    "/api/runs/{run_id}/report.pdf",
    tags=["artifacts"],
    responses={
        200: {"content": {"application/pdf": {}}},
        409: {"description": "Run has not produced a report yet"},
    },
)
def get_report_pdf(run_id: str) -> FileResponse:
    """The report as a PDF, with CJK glyphs embedded.

    Generated on first request and cached beside the report: rendering takes a
    second or two, and most runs are never exported. The embedded font matters
    here — a reader without a CJK typeface installed would otherwise see blank
    boxes, which is why the image build verifies one resolves.
    """
    try:
        state = runs.get_state(run_id)
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    markdown_path = runs.artifact_path(run_id, "report")
    if markdown_path is None:
        raise HTTPException(
            status_code=409,
            detail=f"No report available; run state is '{state['state']}'.",
        )

    pdf_path = markdown_path.parent / "commercialization_report.pdf"
    if not pdf_path.exists():
        from ui.pdf_export import _generate_pdf

        try:
            _generate_pdf(
                markdown_path.read_text(encoding="utf-8"),
                markdown_path.parent,
                output_language=state.get("output_language", "English"),
            )
        except Exception as exc:  # noqa: BLE001 - renderer failures vary by backend
            _LOGGER.exception("Report PDF rendering failed for run %s", run_id)
            raise HTTPException(
                status_code=500,
                detail=(
                    "The report PDF could not be rendered. "
                    "The Markdown report is still available."
                ),
            ) from exc

    if not pdf_path.exists():
        raise HTTPException(status_code=500, detail="PDF rendering produced no file.")

    return FileResponse(
        pdf_path, media_type="application/pdf", filename=f"{run_id}.pdf"
    )


@app.get(
    "/api/runs/{run_id}/{artifact}",
    tags=["artifacts"],
    responses={
        404: {"description": "Unknown run_id or artifact name"},
        409: {"description": "Artifact not produced by this run"},
    },
)
def get_artifact(run_id: str, artifact: str) -> FileResponse:
    """Fetch a named run artifact advertised by the status endpoint."""
    try:
        state = runs.get_state(run_id)
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    path = runs.artifact_path(run_id, artifact)
    if path is None:
        known = runs.artifact_names()
        if artifact not in known:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown artifact '{artifact}'. Available names: {known}",
            )
        raise HTTPException(
            status_code=409,
            detail=(
                f"Run produced no '{artifact}'; state is '{state['state']}'. "
                f"Available: {state['artifacts']}"
            ),
        )

    media = "application/json" if path.suffix == ".json" else "text/plain; charset=utf-8"
    return FileResponse(path, media_type=media, filename=path.name)
