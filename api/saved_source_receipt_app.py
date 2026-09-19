"""Isolated receipt HTTP boundary; never mounted in production or the old lab.

Injected callbacks are trusted Python, not native-provider configuration. The
existing controller alone owns admission, durable intent and physical threads.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.requests import ClientDisconnect

from academic_agent.report_evidence_source_locator import (
    LocatorCatalog, LocatorResult, LocatorSource, LocatorText,
)
from academic_agent.saved_source_loader import valid_run_id
from api.saved_source_controller import SavedSourceController
from api.saved_source_receipts import OPERATION, RETENTION_SECONDS, ReceiptError

MAX_BODY_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 128 * 1024
MAX_ACCESS_CODE_BYTES = 4096
# Include names and values of critical headers; leave room for a full 4 KiB
# access code plus its receipt, media and origin headers. Not a server-wide cap.
MAX_CRITICAL_HEADER_BYTES = 8192
BODY_READ_SECONDS = 5
_WEB_ROOT = Path(__file__).resolve().parents[1] / "web" / "saved-source-receipts"
_KEY = re.compile(r"v1\.([0-9]{10})\.[0-9a-f]{64}")
_CRITICAL = {b"host", b"origin", b"idempotency-key", b"x-access-code", b"content-type",
             b"content-length", b"transfer-encoding", b"content-encoding"}
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
_ERROR_STATUS = {
    "invalid_receipt_key": 400, "access_denied": 401, "origin_denied": 403,
    "receipt_not_found": 404, "not_found": 404, "method_not_allowed": 405,
    "receipt_conflict": 409, "receipt_expired": 410, "body_too_large": 413,
    "unsupported_media_type": 415, "invalid_request": 422, "locator_busy": 429,
    "headers_too_large": 431, "selector_disabled": 503, "controller_closed": 503,
    "receipt_capacity": 503, "receipt_unavailable": 503, "execution_unavailable": 503,
    "request_abandoned": 503,
}
_DETAIL = "Saved-source receipt request could not be completed."
_REPLY_FIELDS = {
    "schema_version", "operation", "state", "run_id", "expires_at", "admission_state",
    "provider_usage", "provider_cost", "error_code", "delivery",
    "delivery_snapshot_reads", "delivery_source_reads", "result",
}
_RECEIPT_ERRORS = {
    "saved_source_missing", "saved_source_unavailable", "execution_unavailable",
    "concurrency_limit", "daily_quota_exceeded", "paid_ledger_unavailable",
    "access_denied", "request_abandoned",
}


def _error(code):
    if code not in _ERROR_STATUS:
        code = "receipt_unavailable"
    return JSONResponse({"detail": _DETAIL, "error_code": code},
                        status_code=_ERROR_STATUS[code], headers=_HEADERS)


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


def _origin(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
            or any(ord(char) <= 32 or ord(char) >= 127 for char in value)):
        raise ValueError("invalid_origin")
    return parsed.scheme, parsed.hostname, parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)


def _request_headers(request):
    if request.scope.get("query_string"):
        raise ReceiptError("invalid_request")
    critical = [(key.lower(), value) for key, value in request.scope["headers"] if key.lower() in _CRITICAL]
    if sum(len(key) + len(value) for key, value in critical) > MAX_CRITICAL_HEADER_BYTES:
        raise ReceiptError("headers_too_large")
    headers = {}
    for name, raw in critical:
        if name in headers:
            raise ReceiptError("invalid_request")
        headers[name] = raw.decode("latin-1")
    code = headers.get(b"x-access-code", "")
    if len(code) > MAX_ACCESS_CODE_BYTES:
        raise ReceiptError("headers_too_large")
    if not code or any(ord(char) < 32 or ord(char) >= 127 for char in code):
        raise ReceiptError("access_denied")
    key = headers.get(b"idempotency-key", "")
    if _KEY.fullmatch(key) is None:
        raise ReceiptError("invalid_receipt_key")
    if b"origin" in headers:
        try:
            # The actual ASGI scheme and Host define this app's origin. Never
            # use client-supplied Forwarded/X-Forwarded-* as authority.
            expected = _origin(f"{request.scope['scheme']}://{headers.get(b'host', '')}")
            if _origin(headers[b"origin"]) != expected:
                raise ValueError("different_origin")
        except ValueError:
            raise ReceiptError("origin_denied") from None
    if b"content-encoding" in headers:
        raise ReceiptError("unsupported_media_type")
    if b"content-length" in headers:
        length = headers[b"content-length"]
        if not length.isascii() or not length.isdecimal() or len(length) > 20:
            raise ReceiptError("invalid_request")
        if b"transfer-encoding" in headers:
            raise ReceiptError("invalid_request")
        if int(length) > MAX_BODY_BYTES:
            raise ReceiptError("body_too_large")
    if request.method == "POST" and headers.get(b"content-type", "").lower() != "application/json":
        raise ReceiptError("unsupported_media_type")
    return key, code


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("invalid_constant")


async def _body(request):
    body = bytearray()
    try:
        # Bound only ingress, never admitted execution or its HTTP waiter.
        async with asyncio.timeout(BODY_READ_SECONDS):
            async for chunk in request.stream():
                if len(body) + len(chunk) > MAX_BODY_BYTES:
                    raise ReceiptError("body_too_large")
                body.extend(chunk)
                if request.method == "GET" and body:
                    raise ReceiptError("invalid_request")
    except (TimeoutError, ClientDisconnect):
        raise ReceiptError("invalid_request") from None
    return body


def _question(body):
    try:
        value = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_invalid_constant)
        if type(value) is not dict or set(value) != {"question"}:
            raise ValueError("invalid_request")
        question = value["question"]
        if type(question) is not str or not 1 <= len(question) <= 4096 or not question.strip():
            raise ValueError("invalid_request")
        question.encode("utf-8")
        return question
    except (ValueError, TypeError, RecursionError):
        raise ReceiptError("invalid_request") from None


def _full_fields(value, model):
    if type(value) is not dict or set(value) != set(model.model_fields):
        raise ValueError("incomplete_result")


def _wire_reply(reply, key, *, run_id=None):
    """Validate, then serialize the ORIGINAL full reply, never a model projection."""
    if type(reply) is not dict or set(reply) != _REPLY_FIELDS:
        raise ValueError("invalid_receipt_fields")
    if (type(reply["schema_version"]) is not int or reply["schema_version"] != 1
            or reply["operation"] != OPERATION or not valid_run_id(reply["run_id"])
            or (run_id is not None and reply["run_id"] != run_id)
            or type(reply["expires_at"]) is not int
            or reply["expires_at"] != int(_KEY.fullmatch(key)[1]) + RETENTION_SECONDS
            or reply["provider_usage"] != "not_observed" or reply["provider_cost"] != "not_observed"):
        raise ValueError("invalid_receipt_identity")
    state, delivery, admission = reply["state"], reply["delivery"], reply["admission_state"]
    if (state not in {"pending", "unknown", "completed", "failed"}
            or admission not in {"not_admitted", "unknown", "admitted"}
            or delivery not in {"not_ready", "available", "expired", "changed", "unavailable"}):
        raise ValueError("invalid_receipt_state")
    snapshot_reads, source_reads = reply["delivery_snapshot_reads"], reply["delivery_source_reads"]
    if any(type(value) is not int or value not in {0, 1} for value in (snapshot_reads, source_reads)):
        raise ValueError("invalid_delivery_reads")
    error, result = reply["error_code"], reply["result"]
    if state != "completed":
        if (delivery != "not_ready" or result is not None or snapshot_reads or source_reads
                or (state == "failed" and error not in _RECEIPT_ERRORS)
                or (state != "failed" and error is not None)):
            raise ValueError("invalid_uncompleted_receipt")
        if (error in {"saved_source_missing", "saved_source_unavailable", "concurrency_limit",
                      "daily_quota_exceeded", "access_denied", "request_abandoned"}
                and admission != "not_admitted"):
            raise ValueError("invalid_failed_admission")
    else:
        if error is not None or admission == "unknown" or delivery == "not_ready":
            raise ValueError("invalid_completed_receipt")
        if delivery != "available":
            if (result is not None or snapshot_reads != 1
                    or (delivery in {"expired", "changed"} and source_reads != 0)):
                raise ValueError("invalid_unavailable_delivery")
        else:
            _full_fields(result, LocatorResult)
            _full_fields(result["catalog"], LocatorCatalog)
            for field, model in (("source", LocatorSource), ("saved_text", LocatorText)):
                if result[field] is not None:
                    _full_fields(result[field], model)
            checked = LocatorResult.model_validate(result, strict=True)
            # JSON comparison distinguishes bool from int and forbids accidental
            # normalization/default filling, even where Python equality would not.
            if json.dumps(checked.model_dump(), sort_keys=True, allow_nan=False) != json.dumps(
                    result, sort_keys=True, allow_nan=False):
                raise ValueError("changed_result")
            if (admission != ("admitted" if checked.callback_entries else "not_admitted")
                    or source_reads != int(snapshot_reads == 1 and checked.state in {
                        "excerpt", "blank_text", "missing_text"})):
                raise ValueError("invalid_completed_delivery_facts")
    payload = {**reply, "receipt_key_sha256": hashlib.sha256(key.encode("ascii")).hexdigest()}
    raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("response_too_large")
    return Response(raw, media_type="application/json", headers=_HEADERS)


def create_saved_source_receipt_app(*, load_snapshot, journal_root, selector=None, selector_identity=None):
    """Own one controller and drain it on shutdown; execution defaults disabled."""
    controller = SavedSourceController(load_snapshot, journal_root, selector, selector_identity)

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            await controller.close()

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

    app.mount("/receipt-static", StaticFiles(directory=_WEB_ROOT, check_dir=False), name="receipt-static")

    async def handle(request, run_id=None):
        try:
            key, code = _request_headers(request)
            if run_id is not None and not valid_run_id(run_id):
                raise ReceiptError("invalid_request")
            body = await _body(request)
            if run_id is None:
                reply = await controller.lookup(key, code)
            else:
                reply = await controller.execute(key, run_id, _question(body), code)
            return _wire_reply(reply, key, run_id=run_id)
        except ReceiptError as exc:
            return _error(exc.code)
        except Exception:  # noqa: BLE001 -- never echo rejected values, controller details or private paths.
            return _error("execution_unavailable")

    @app.post("/api/runs/{run_id}/saved-source-location", response_model=None)
    async def locate(run_id: str, request: Request):
        return await handle(request, run_id)

    @app.get("/api/saved-source-receipts", response_model=None)
    async def lookup(request: Request):
        return await handle(request)

    return app
