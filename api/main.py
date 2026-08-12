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
import os
import threading
import time
from collections.abc import AsyncIterator
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

# Load .env before anything reads os.environ. The Gradio entry point gets this
# for free because importing crewai pulls it in, but that is a side effect to
# rely on, not a contract — an API server should be explicit about its config.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from academic_agent.pdf_extractor import extract_paper_contribution  # noqa: E402
from api import access, papers, runs  # noqa: E402  — must follow load_dotenv
from api.models import (  # noqa: E402
    HealthStatus,
    PaperExtraction,
    RunAccepted,
    RunList,
    RunProgress,
    RunRequest,
    RunStatus,
    StepEvent,
)

_REAP_INTERVAL_SECONDS = 30


async def _reaper() -> None:
    """Kill runs that exceed the deadline.

    The Gradio path enforces its timeout inside the polling loop; the API has
    no such loop, so the check runs here instead.
    """
    while True:
        await asyncio.sleep(_REAP_INTERVAL_SECONDS)
        for run_id in runs.reap_timeouts():
            print(f"[api] run {run_id} killed: exceeded {runs.TIMEOUT_SECONDS}s")
        # Uploaded PDFs that were never run would otherwise accumulate; they
        # are only useful until the run that consumes them starts.
        removed = papers.prune_old()
        if removed:
            print(f"[api] pruned {removed} expired paper upload(s)")


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
        "scorecard. Each run executes the same six-agent pipeline used by the "
        "Gradio UI."
    ),
    version="1.0.0",
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
# Distinct from the concurrency cap and the daily run cap, which both count
# *runs*: this counts *requests*, and exists because the endpoints that cost
# nothing to serve are the ones an unauthenticated caller can reach. A run id
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

    Prefers the access code over the address: several people behind one
    campus or corporate NAT share an IP, and throttling them as one client
    would penalise the exact audience this deployment is for. A code holder
    is charged individually; everyone else falls back to the peer address.

    X-Forwarded-For is read because the app sits behind Railway's proxy, and
    only its first entry — the rest are appendable by the caller.
    """
    code = request.headers.get("x-access-code")
    if code:
        return f"code:{access.owner_id(code)}"
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
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

    /health is exempt: platform health checks poll it on their own schedule
    and must never be throttled into reporting the service as down.
    """
    if request.url.path != "/health" and _rate_limit_exceeded(_client_key(request)):
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
    - POST /api/runs — authorizes itself (see submit_run) with either the code
      or complete bring-your-own-key credentials in the body. That decision
      needs the parsed body, which a middleware does not cheaply have.
    - GET/DELETE /api/runs/{id}/... — a specific run, addressed by its id, is
      a capability URL: the id itself (40 bits of randomness, see
      create_run_id) is the credential, the same trust model already used for
      sharing a finished report's link. Reading or cancelling one run costs
      nothing further, unlike GET /api/runs (no id), which lists every run on
      the deployment and stays gated.
    """
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)
    if path == "/api/runs" and request.method == "POST":
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


def _authorize_destructive(run_id: str, http_request: Request) -> None:
    """Require the code that owns this run before cancelling or deleting it.

    The access-gate middleware exempts /api/runs/{id}/... so a report link
    can be shared without handing over the access code. That exemption is
    right for reads and wrong for destructive calls, which is why this check
    lives in the handler rather than the middleware.

    Raises 404 rather than 403 on a mismatch: a distinct "forbidden" would
    confirm to a caller probing ids that a given run exists, which is the one
    thing a 40-bit id cannot afford to leak.
    """
    if not access.gate_enabled():
        return                      # nothing configured to authorize against

    matched = access.matching_code(http_request.headers.get("x-access-code"))
    if matched is not None and access.is_admin(matched):
        return

    owner = runs.owner_of(run_id)
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
    """Liveness check, current capacity, and the resolved LLM provider.

    `llm_provider` is null when no key is configured — a run submitted in that
    state will start but fail inside the worker, so check this first.
    """
    # Reuse the pipeline's own resolution so this never disagrees with what a
    # run would actually use (it handles LLM_PROVIDER and the legacy
    # OPENAI_API_BASE-pointing-at-DeepSeek setup).
    from academic_agent.llm_config import _detect_provider

    try:
        provider = _detect_provider()
    except RuntimeError:
        provider = None

    return HealthStatus(
        status="ok",
        active_runs=runs.active_count(),
        max_concurrent=runs.MAX_CONCURRENT,
        llm_provider=provider,
    )


@app.post(
    "/api/runs",
    response_model=RunAccepted,
    status_code=202,
    tags=["runs"],
    responses={
        401: {"description": "Neither the access code nor complete bring-your-own-key credentials were provided"},
        429: {"description": "Concurrency limit or daily run cap reached"},
    },
)
def submit_run(request: RunRequest, http_request: Request) -> RunAccepted:
    """Queue an assessment. Returns immediately with a run_id to poll.

    A full run takes roughly 2.5–4 minutes. Authorized either by the
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
    owner = access.owner_id(matched) if matched else None

    paper_json_path: str | None = None
    if request.paper_id:
        try:
            paper_json_path = str(papers.extraction_path_for_run(request.paper_id))
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
            byok=byok,
            owner=owner,
        )
    except runs.ConcurrencyLimitReached as exc:
        raise HTTPException(
            status_code=429,
            detail=f"{exc}. Retry once a run finishes.",
        ) from exc
    except runs.DailyCapReached as exc:
        raise HTTPException(
            status_code=429,
            detail=f"{exc}. The daily run budget resets at 00:00 UTC.",
        ) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start worker: {exc}") from exc

    return RunAccepted(run_id=run_id, state="running", topic=request.topic)


@app.get("/api/runs", response_model=RunList, tags=["runs"])
def list_runs(http_request: Request, limit: int = Query(default=50, ge=1, le=200)) -> RunList:
    """List runs, newest first — scoped to the calling code's own history.

    `request.state.owner`/`.is_admin` were set by the access-gate
    middleware, which ran ahead of this handler for every path that isn't
    POST /api/runs or /api/runs/{id}/...; this path falls into neither, so
    both are always set (owner to None when the gate is disabled entirely,
    meaning no filter).
    """
    summaries, total = runs.list_runs(limit=limit, owner=http_request.state.owner)
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
    _authorize_destructive(run_id, http_request)

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
        raise HTTPException(status_code=500, detail=f"Could not delete run: {exc}") from exc
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
        stage=state.get("stage", ""),
        topic=state.get("topic", ""),
        done=state["state"] != "running",
        error=state.get("error"),
        elapsed_seconds=state.get("elapsed_seconds"),
        source_counts=state.get("source_counts"),
        evidence_incomplete=state.get("evidence_incomplete", False),
        output_language=state.get("output_language", "English"),
        steps=[StepEvent(**s) for s in runs.read_steps(run_id, since=since)],
        artifacts=state.get("artifacts", []),
    )


@app.post(
    "/api/papers",
    response_model=PaperExtraction,
    tags=["papers"],
    responses={
        413: {"description": "File exceeds the size limit"},
        422: {"description": "PDF could not be parsed into a contribution"},
    },
)
async def upload_paper(file: UploadFile = File(...)) -> PaperExtraction:
    """Extract a paper's contribution from an uploaded PDF.

    Returns the extraction and a paper_id. Pass that id to POST /api/runs to
    anchor a run on the paper; the fields are editable first, since the topic
    the model derives is a starting point rather than an answer.

    Runs the extractor in a worker thread: it makes an LLM call and would
    otherwise block the event loop for several seconds.
    """
    data = await file.read()
    try:
        paper_id, pdf_path = papers.save_upload(file.filename or "paper.pdf", data)
    except papers.PaperTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    try:
        contribution = await asyncio.to_thread(extract_paper_contribution, str(pdf_path))
    except Exception as exc:  # noqa: BLE001 - surface the reason to the client
        raise HTTPException(
            status_code=422,
            detail=f"Could not extract a contribution from this PDF: {exc}",
        ) from exc

    payload = contribution.model_dump()
    papers.save_extraction(paper_id, payload)
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
        except Exception as exc:  # noqa: BLE001 - report the reason
            raise HTTPException(
                status_code=500, detail=f"Could not render the PDF: {exc}"
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
    """Fetch a run artifact: `scores`, `sources`, `notes`, or `steps`."""
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
