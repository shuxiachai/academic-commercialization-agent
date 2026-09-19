"""Independent injected-callback lab; never mounted by the production app.

An injected callable is trusted Python code. Local occupancy is not paid
admission, billing, a provider credential boundary or a durable receipt.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import Future
from contextlib import asynccontextmanager
import json
from pathlib import Path
import threading
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException
from starlette.requests import ClientDisconnect

from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot
from academic_agent.report_evidence_source_locator import (
    LocatorResult, locate_saved_source, render_locator_result,
)
from academic_agent.saved_source_loader import (
    SavedSourceMissing, SavedSourceUnavailable, valid_run_id,
)

MAX_BODY_BYTES = 64 * 1024
_WEB_ROOT = Path(__file__).resolve().parents[1] / "web" / "saved-source-lab"
_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "img-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}
_ERRORS = {
    "saved_source_missing": (404, "Saved sources not found."),
    "body_too_large": (413, "Request body too large."),
    "invalid_request": (422, "Invalid request."),
    "locator_busy": (429, "Saved-source locator busy."),
    "selector_contract_error": (502, "Selector contract failed."),
    "selector_disabled": (503, "Saved-source selector disabled."),
    "locator_closing": (503, "Saved-source locator closing."),
    "saved_source_unavailable": (503, "Saved sources unavailable."),
    "execution_unavailable": (503, "Saved-source execution unavailable."),
    "not_found": (404, "Not found."),
    "method_not_allowed": (405, "Method not allowed."),
}


def _error(code: str) -> JSONResponse:
    status, detail = _ERRORS[code]
    return JSONResponse({"detail": detail, "error_code": code}, status_code=status, headers=_HEADERS)


class SavedSourceEnvelope(BaseModel):
    """Full frozen nested contract; no reduced display/status projection."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    selector_mode: Literal["injected_callback"] = "injected_callback"
    billing_integration: Literal["not_implemented"] = "not_implemented"
    result: LocatorResult


class _SecurityHeaders:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def secured(message):
            if message["type"] == "http.response.start":
                headers = [(key, value) for key, value in message.get("headers", [])
                           if key.lower() not in {name.lower().encode() for name in _HEADERS}]
                message = {**message, "headers": headers + [
                    (name.lower().encode(), value.encode()) for name, value in _HEADERS.items()]}
            await send(message)
        await self.app(scope, receive, secured)


class _Execution:
    """Track actual threads independently of asyncio/HTTP waiter lifetime."""

    def __init__(self, load_snapshot, selector):
        self.load_snapshot = load_snapshot
        self.selector = selector
        self._gate = threading.Lock()
        self._occupied = False
        self._closing = False
        self._threads: set[threading.Thread] = set()

    def unavailable(self):
        with self._gate:
            if self._closing:
                return "locator_closing"
            if self.selector is None:
                return "selector_disabled"
        return None

    def _operate(self, run_id, question):
        # Admission and closing share one gate. Only this synchronous owner
        # releases operation occupancy after load/read/serialization. Physical
        # thread admission remains reserved until run() observes actual exit.
        with self._gate:
            if self._closing:
                return _error("locator_closing")
            if self._occupied:
                return _error("locator_busy")
            self._occupied = True
        try:
            try:
                snapshot = self.load_snapshot(run_id)
            except SavedSourceMissing:
                return _error("saved_source_missing")
            except SavedSourceUnavailable:
                return _error("saved_source_unavailable")
            result = locate_saved_source(snapshot, question, selector=self.selector)
            # The frozen renderer reconstructs nested values and checks all
            # counters/hashes. Round-trip its JSON, not an arbitrary dictionary.
            checked = LocatorResult.model_validate_json(render_locator_result(result), strict=True)
            if checked.state == "failed":
                return _error("selector_contract_error")
            if checked.state == "unavailable":
                return _error("execution_unavailable")
            envelope = SavedSourceEnvelope(result=checked)
            # Serialize here, while occupied. Returning a Response avoids an
            # extra potentially lossy FastAPI model projection after release.
            return Response(envelope.model_dump_json().encode("utf-8"),
                            media_type="application/json", headers=_HEADERS)
        except Exception:  # noqa: BLE001 -- no saved content, callback prose or exception detail escapes.
            return _error("execution_unavailable")
        finally:
            with self._gate:
                self._occupied = False

    async def run(self, run_id, question):
        result: Future = Future()

        def worker():
            try:
                reply = self._operate(run_id, question)
            except BaseException:  # Worker exit must settle an abandoned waiter even for trusted-code SystemExit.
                reply = _error("execution_unavailable")
            result.set_result(reply)

        with self._gate:
            if self._closing:
                return _error("locator_closing")
            self._threads = {thread for thread in self._threads if thread.is_alive()}
            # An operation flag misses both pre-entry and post-result thread
            # windows. Registration and start stay under this same gate, so a
            # peer cannot prune a registered thread before start has completed.
            if self._threads:
                return _error("locator_busy")
            thread = threading.Thread(target=worker, name="saved-source-locator")
            self._threads.add(thread)
            try:
                thread.start()
            except RuntimeError:
                self._threads.remove(thread)
                return _error("execution_unavailable")
        # Shield the result bridge, not merely the operation. Cancelling the
        # HTTP task cannot cancel this concurrent Future or free its thread.
        return await asyncio.shield(asyncio.wrap_future(result))

    async def close(self):
        with self._gate:
            self._closing = True
            threads = tuple(self._threads)

        def drain():
            for thread in threads:
                thread.join()

        # A stuck trusted callback has no safe kill and no bounded drain.
        # Shield and finish draining even if lifespan shutdown is cancelled.
        waiter = asyncio.create_task(asyncio.to_thread(drain))
        cancelled = False
        while not waiter.done():
            try:
                await asyncio.shield(waiter)
            except asyncio.CancelledError:
                cancelled = True
        waiter.result()
        if cancelled:
            raise asyncio.CancelledError


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("invalid_constant")


async def _question(request):
    body = bytearray()
    try:
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_BODY_BYTES:
                return _error("body_too_large")
            body.extend(chunk)
        value = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_invalid_constant)
        if type(value) is not dict or set(value) != {"question"}:
            return _error("invalid_request")
        question = value["question"]
        if type(question) is not str or not 1 <= len(question) <= 4096 or not question.strip():
            return _error("invalid_request")
        question.encode("utf-8")
        return question
    except (ValueError, TypeError, RecursionError, ClientDisconnect):
        return _error("invalid_request")


def create_saved_source_app(
    *, load_snapshot: Callable[[str], ReportEvidenceSnapshot], selector: Callable[[dict], object] | None = None,
) -> FastAPI:
    """Create a default-disabled app without environment, provider or key discovery."""
    if not callable(load_snapshot) or (selector is not None and not callable(selector)):
        raise ValueError("invalid_saved_source_factory")
    execution = _Execution(load_snapshot, selector)

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            await execution.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(_SecurityHeaders)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, _exc):
        return _error("invalid_request")

    @app.exception_handler(HTTPException)
    async def http_error(_request, exc):
        return _error("method_not_allowed" if exc.status_code == 405 else "not_found")

    @app.exception_handler(Exception)
    async def unexpected_error(_request, _exc):
        return _error("execution_unavailable")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(_WEB_ROOT / "index.html")

    app.mount("/lab-static", StaticFiles(directory=_WEB_ROOT, check_dir=False), name="lab-static")

    @app.post("/api/runs/{run_id}/saved-source-location", response_model=SavedSourceEnvelope)
    async def locate(run_id: str, request: Request):
        unavailable = execution.unavailable()
        if unavailable:
            return _error(unavailable)
        if not valid_run_id(run_id):
            return _error("invalid_request")
        question = await _question(request)
        if isinstance(question, Response):
            return question
        return await execution.run(run_id, question)

    return app
