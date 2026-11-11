"""Measure, from this host, whether the provider's endpoint carries a writer-sized request.

2026-11-09, the first production run after every crew node began streaming
with a 60-second per-chunk bound and a rebuilt connection before each retry:
the writer's request failed on eight fresh connections in a row, each silent
for 60 seconds, two of them with a connection error; the three evidence
agents' smaller requests mostly got through. The same 22,000-token request
sent from the maintainer's machine, outside the host's network, to the same
endpoint got its first chunk in 6.9 seconds and finished in 22.7. The model was not slow. The path
from the host (Railway, Singapore) to dashscope.aliyuncs.com (Beijing) was
not carrying a 100 KB request, at least not that afternoon.

Nothing could be measured from the host. The shell is not reachable from the
operator's working machine, and the attempt rows say only that no chunk came
in 60 seconds, which a stalled upload and a silent server look alike in. So
this is the measurement, from the host, on demand from the console:

  • chat requests of 1, 10, 30 and 100 KB, the last the size of the writer's,
    posted with no key to the configured endpoint and, for Bailian, to its
    sibling on the other side of the border (dashscope-intl.aliyuncs.com,
    which sits in the host's own region). Both servers read the whole body
    before they answer 401, checked by hand on 2026-11-09, so the time to
    that answer is the time the path takes to carry the request;
  • each reading on a new connection, like the worker's rebuilt pool, with
    the transport's own trace marking when the socket connected, TLS came
    up, the body was sent and the first response byte arrived;
  • a 30-second bound per reading: a 100 KB upload that needs longer has
    already failed the writer, whose first chunk must arrive within 60.

Nothing is billed: no key is sent and the servers answer before any model is
asked. No host comes from the caller: the targets are the configured endpoint
and a fixed sibling, so the console is not a way to make this server post to
an address of the caller's choosing.

What a reading can and cannot say. A 401 inside a few seconds on both sizes
means the path carried a writer-sized request at that moment. An upload
that never completes on the configured host while the sibling answers says
the problem is the border, and an international Bailian account (the
operator's decision) would move the traffic to the host's own region. A
clean reading does not clear the path for the next run: the 2026-11-09 run
that finished in 343 seconds and the one that failed were four hours apart
on the same code.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx

from academic_agent.llm_config import resolve_provider_config

#: The writer's request on 2026-11-09 was 22,010 prompt tokens: about 100 KB
#: on the wire. The small body is the size of a short question.
SMALL_BYTES = 1_000
LARGE_BYTES = 100_000
#: Half the per-chunk bound a production attempt gets, so the console answer
#: stays under three minutes with every size on both hosts.
TIMEOUT_SECONDS = 30
#: The first production readings (2026-11-09 09:08 UTC, from the host): 1 KB in
#: 0.75 s; 100 KB uploaded in 25.7 s once and not at all the next time; the
#: international host 40-57 ms for either. Whether a smaller writer request
#: would pass the border needs readings between those two, the evidence
#: agents' size (about 30 KB, which mostly passed that afternoon) among them.
SIZES = (SMALL_BYTES, 10_000, 30_000, LARGE_BYTES)
#: One reading of each size, two of the writer-sized one: the second large
#: reading tells a one-off from a path that drops every large request.
_READINGS = ((SMALL_BYTES, 1), (10_000, 1), (30_000, 1), (LARGE_BYTES, 2))

# Bailian's two front doors. The mainland host is the one a mainland account
# must use; the international host is the one the host's own region reaches
# without crossing the border. Each is probed beside the other.
_SIBLINGS = {
    "dashscope.aliyuncs.com": ("intl", "dashscope-intl.aliyuncs.com"),
    "dashscope-intl.aliyuncs.com": ("mainland", "dashscope.aliyuncs.com"),
}

# The trace events httpcore emits, in the order a request passes them.
_MARKS = {
    "connect_ms": "connection.connect_tcp.complete",
    "tls_ms": "connection.start_tls.complete",
    "upload_ms": "http11.send_request_body.complete",
    "first_byte_ms": "http11.receive_response_headers.complete",
}


class NoEndpoint(RuntimeError):
    """No provider is configured on this deployment, so there is no path to measure."""


class Busy(RuntimeError):
    """A probe is already running; two at once would measure each other."""


@dataclass(frozen=True)
class Target:
    name: str
    url: str

    @property
    def host(self) -> str:
        return urlsplit(self.url).hostname or ""


@dataclass
class Reading:
    """Milliseconds since the request started; null where the request never got."""

    body_bytes: int
    connect_ms: int | None = None
    tls_ms: int | None = None
    upload_ms: int | None = None
    first_byte_ms: int | None = None
    total_ms: int = 0
    status: int | None = None
    error: str | None = None


def targets() -> list[Target]:
    """The configured endpoint's request path and, for Bailian, its sibling's."""
    try:
        config = resolve_provider_config()
    except RuntimeError as exc:
        raise NoEndpoint("No provider endpoint is configured on this deployment.") from exc
    path = "/v1/messages" if config.provider == "anthropic" else "/chat/completions"
    found = [Target("configured", config.base_url + path)]
    host = urlsplit(config.base_url).hostname or ""
    sibling = _SIBLINGS.get(host)
    if sibling is not None:
        name, other = sibling
        found.append(Target(name, config.base_url.replace(host, other, 1) + path))
    return found


def _body(size: int) -> bytes:
    """A chat request of exactly `size` bytes that any OpenAI-compatible server will parse."""
    frame = json.dumps({"model": "link-probe", "messages": [{"role": "user", "content": ""}]}).encode()
    return json.dumps({"model": "link-probe",
                       "messages": [{"role": "user", "content": "x" * max(0, size - len(frame))}]}).encode()


def reading_from(events: dict[str, float], *, started: float, finished: float,
                 status: int | None, error: str | None, body_bytes: int) -> Reading:
    """Turn the trace marks of one request into its timeline."""
    marks = {field: (round((events[name] - started) * 1000) if name in events else None)
             for field, name in _MARKS.items()}
    return Reading(body_bytes=body_bytes, total_ms=round((finished - started) * 1000),
                   status=status, error=error, **marks)


def probe_once(target: Target, size: int, *, timeout: float = TIMEOUT_SECONDS,
               transport: httpx.BaseTransport | None = None) -> Reading:
    """One request of `size` bytes to `target` on a new connection, with no key."""
    events: dict[str, float] = {}

    def trace(name: str, info: dict) -> None:
        events.setdefault(name, time.monotonic())

    status = error = None
    started = time.monotonic()
    # A client per reading: a new connection every time, like the worker's
    # rebuilt pool, so the connect and TLS marks are always present.
    with httpx.Client(timeout=timeout, transport=transport) as client:
        try:
            response = client.post(target.url, content=_body(size),
                                   headers={"Content-Type": "application/json"},
                                   extensions={"trace": trace})
            status = response.status_code
        except httpx.HTTPError as exc:
            error = type(exc).__name__
    return reading_from(events, started=started, finished=time.monotonic(),
                        status=status, error=error, body_bytes=size)


_running = threading.Lock()


def run(*, timeout: float = TIMEOUT_SECONDS) -> dict:
    """Every target, the two sizes in order, targets in parallel; a plain dict for the API."""
    found = targets()
    if not _running.acquire(blocking=False):
        raise Busy("A link probe is already running.")
    try:
        results: list[dict | None] = [None] * len(found)

        def work(index: int, target: Target) -> None:
            readings = [asdict(probe_once(target, size, timeout=timeout))
                        for size, count in _READINGS for _ in range(count)]
            results[index] = {"name": target.name, "host": target.host, "readings": readings}

        threads = [threading.Thread(target=work, args=(i, t), daemon=True, name=f"link-probe-{t.name}")
                   for i, t in enumerate(found)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        _running.release()
    return {
        "taken_at": datetime.now(UTC).isoformat(),
        "timeout_seconds": timeout,
        "small_bytes": SMALL_BYTES,
        "large_bytes": LARGE_BYTES,
        "sizes": list(SIZES),
        "targets": results,
    }
