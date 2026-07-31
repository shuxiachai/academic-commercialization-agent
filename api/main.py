"""FastAPI application exposing the analysis pipeline over HTTP.

Runs alongside the Gradio UI rather than replacing it: both launch the same
`pipeline_worker` subprocess and read the same run directory, so a run started
from one is visible to the other.

    uv run uvicorn api.main:app --reload
    → http://localhost:8000/docs
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse

# Load .env before anything reads os.environ. The Gradio entry point gets this
# for free because importing crewai pulls it in, but that is a side effect to
# rely on, not a contract — an API server should be explicit about its config.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from api import runs  # noqa: E402  — must follow load_dotenv
from api.models import (  # noqa: E402
    HealthStatus,
    RunAccepted,
    RunList,
    RunRequest,
    RunStatus,
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
    responses={429: {"description": "Concurrency limit reached"}},
)
def submit_run(request: RunRequest) -> RunAccepted:
    """Queue an assessment. Returns immediately with a run_id to poll.

    A full run takes roughly 2.5–4 minutes.
    """
    try:
        run_id, _ = runs.start_run(
            topic=request.topic,
            language=request.language,
            weight_profile=request.weight_profile,
        )
    except runs.ConcurrencyLimitReached as exc:
        raise HTTPException(
            status_code=429,
            detail=f"{exc}. Retry once a run finishes.",
        ) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start worker: {exc}") from exc

    return RunAccepted(run_id=run_id, state="running", topic=request.topic)


@app.get("/api/runs", response_model=RunList, tags=["runs"])
def list_runs(limit: int = Query(default=50, ge=1, le=200)) -> RunList:
    """List runs, newest first."""
    summaries, total = runs.list_runs(limit=limit)
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
    response_model=RunStatus,
    tags=["runs"],
    responses={404: {"description": "No live run with that id"}},
)
def cancel_run(run_id: str) -> RunStatus:
    """Terminate a running assessment. Partial artifacts are kept."""
    try:
        runs.cancel_run(run_id)
        return RunStatus(**runs.get_state(run_id))
    except runs.RunNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail=f"{exc}. Already-finished runs cannot be cancelled.",
        ) from exc


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
