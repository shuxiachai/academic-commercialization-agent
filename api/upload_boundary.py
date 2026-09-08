"""Bound untrusted upload transport before FastAPI parses multipart files."""

from __future__ import annotations

import asyncio
import threading
import time

from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api import papers

# UploadFile has already been parsed/spooled before endpoint validation. Bound
# the complete request, including extra files, fields and multipart overhead.
# BYOK still needs no access-code header; authentication is not a byte limit.
MAX_MULTIPART_OVERHEAD_BYTES = 1024 * 1024
MAX_UPLOAD_PARSERS = 2
UPLOAD_IDLE_SECONDS = 30.0
UPLOAD_TOTAL_SECONDS = 120.0
_RELEASE_KEY = "academic_agent.upload_release"


class _RejectedBody(MultiPartException):
    """Use the parser's cleanup path, then replace its generic 400 code."""


def release_upload_slot(scope: Scope) -> None:
    """Release after parsing/local copy; model latency is not upload time."""
    release = scope.get(_RELEASE_KEY)
    if release is not None:
        release()


class PaperUploadBoundary:
    """Process-local byte/time/parser limits, independent of paid admission.

    No second body copy, trusted Content-Length or draining rejected bodies.
    MultiPartException closes spooled files; the send seam retains 413/408
    instead of FastAPI's generic parser 400. Proxies may impose stricter limits;
    this is not a distributed DoS defence or a provider execution timeout.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._lock = threading.Lock()
        self._active = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (scope["type"] != "http" or scope["method"] != "POST"
                or scope["path"].rstrip("/") != "/api/papers"):
            await self.app(scope, receive, send)
            return

        limit = papers.MAX_UPLOAD_BYTES + MAX_MULTIPART_OVERHEAD_BYTES
        lengths = [v for k, v in scope["headers"] if k.lower() == b"content-length"]
        if lengths and (len(lengths) != 1 or not lengths[0].isdigit() or len(lengths[0]) > 20):
            await JSONResponse({"detail": "Invalid upload Content-Length."}, 400)(scope, receive, send)
            return
        if lengths and int(lengths[0]) > limit:
            await self._response(413, "upload_too_large")(scope, receive, send)
            return

        with self._lock:
            admitted = self._active < MAX_UPLOAD_PARSERS
            if admitted:
                self._active += 1
        if not admitted:
            await self._response(429, "upload_capacity")(scope, receive, send)
            return

        released = False

        def release() -> None:
            nonlocal released
            with self._lock:
                if not released:
                    released = True
                    self._active -= 1

        scope[_RELEASE_KEY] = release
        received = 0
        deadline = time.monotonic() + UPLOAD_TOTAL_SECONDS
        rejected: tuple[int, str] | None = None
        rejection_sent = False

        async def bounded_receive() -> Message:
            nonlocal received, rejected
            # Disconnect listeners can outlive parsing while an LLM runs. The
            # receive timeout must never become a paid operation's deadline.
            if released:
                return await receive()
            remaining = deadline - time.monotonic()
            try:
                if remaining <= 0:
                    raise TimeoutError
                message = await asyncio.wait_for(receive(), min(UPLOAD_IDLE_SECONDS, remaining))
            except TimeoutError as exc:
                rejected = (408, "upload_timeout")
                raise _RejectedBody("Upload receive deadline exceeded.") from exc
            if message["type"] == "http.disconnect":
                rejected = (400, "upload_disconnected")
                raise _RejectedBody("Upload disconnected before parsing completed.")
            received += len(message.get("body", b""))
            if received > limit:
                rejected = (413, "upload_too_large")
                raise _RejectedBody("Upload request exceeded its byte limit.")
            return message

        async def bounded_send(message: Message) -> None:
            nonlocal rejection_sent
            if rejected is not None:
                if not rejection_sent:
                    rejection_sent = True
                    await self._response(*rejected)(scope, receive, send)
                return
            await send(message)

        try:
            await self.app(scope, bounded_receive, bounded_send)
        finally:
            # Auth/validation failure may never enter the endpoint. Both this
            # cleanup and successful parsing handoff are idempotent.
            release()

    @staticmethod
    def _response(status: int, code: str) -> JSONResponse:
        detail = {
            "upload_too_large": "Upload request is too large; reduce the PDF or multipart data.",
            "upload_capacity": "Upload parsing capacity is full. Wait for another upload to finish.",
            "upload_timeout": "Upload transfer timed out before extraction began.",
            "upload_disconnected": "Upload disconnected before extraction began.",
        }[code]
        headers = {"X-Error-Code": code}
        if status == 429:
            headers["Retry-After"] = "10"
        return JSONResponse({"detail": detail}, status, headers=headers)
