"""Assert ingress limits at HTTP/parser seams, before auth or paid admission."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from starlette import formparsers
from starlette.requests import Request
from starlette.responses import Response

# Match the ordinary test bootstrap: main loads the operator's .env, while
# runs snapshots quota defaults at import. Importing main first would make
# unrelated offline admission tests inherit the developer's wallet setting.
from api import access, papers, runs, upload_boundary
from api import main
from tests.scripted_waits import SCENARIO, STEP


def multipart(size=64, count=1):
    head = b'--audit\r\nContent-Disposition: form-data; name="file"; filename="p.pdf"\r\nContent-Type: application/pdf\r\n\r\n'
    return b''.join(head + b'%PDF-' + b'x' * (size - 5) + b'\r\n' for _ in range(count)) + b'--audit--\r\n'


@pytest.fixture
def ingress(monkeypatch):
    monkeypatch.setattr(papers, "MAX_UPLOAD_BYTES", 1024)
    monkeypatch.setattr(upload_boundary, "MAX_MULTIPART_OVERHEAD_BYTES", 512)
    monkeypatch.setattr(access, "ACCESS_CODE", "offline-fixture")
    provider = MagicMock(side_effect=AssertionError("No provider may be reached"))
    monkeypatch.setattr(main, "extract_paper_contribution", provider)
    files = []
    original = formparsers.SpooledTemporaryFile

    def tracked(*args, **kwargs):
        file = original(*args, **kwargs)
        files.append(file)
        return file

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", tracked)
    yield files
    provider.assert_not_called()
    assert runs.active_paid_operation_count() == 0
    assert all(file.closed for file in files), "Rejected multipart files must be closed"


async def post(content, headers=None):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(main.app), base_url="http://offline") as client:
        return await client.post("/api/papers", content=content,
            headers={"Content-Type": "multipart/form-data; boundary=audit", **(headers or {})})


@pytest.mark.parametrize("declared", [None, "1"])
def test_streamed_or_understated_body_stops_before_spooling_all_bytes(ingress, declared):
    """Endpoint caps used to accept the entire unauthenticated multipart body."""
    consumed = 0
    body = multipart(4096)

    async def chunks():
        nonlocal consumed
        for start in range(0, len(body), 128):
            part = body[start:start + 128]
            consumed += len(part)
            yield part

    response = asyncio.run(post(chunks(), {"Content-Length": declared} if declared else None))
    assert response.status_code == 413
    assert response.headers["X-Error-Code"] == "upload_too_large"
    assert 0 < consumed <= 1536 + 128 < len(body)
    assert ingress, "Exercise actual parser cleanup, not only header rejection"


@pytest.mark.parametrize("length,status", [("1537", 413), ("-1", 400), ("garbage", 400), ("9" * 100, 400)])
def test_invalid_or_oversized_length_is_rejected_without_reading(ingress, length, status):
    """Declared excessive size needs no body read, temporary file, or wallet slot."""
    reads = []

    async def forbidden():
        reads.append(True)
        yield multipart()

    response = asyncio.run(post(forbidden(), {"Content-Length": length}))
    assert response.status_code == status
    assert reads == []
    assert ingress == []


def test_extra_files_share_one_total_request_limit(ingress):
    """Individually small extra files must not multiply the request byte budget."""
    async def chunks():
        body = multipart(400, count=5)
        for offset in range(0, len(body), 128):
            yield body[offset:offset + 128]

    response = asyncio.run(post(chunks()))
    assert response.status_code == 413
    assert ingress


def test_valid_sized_upload_preserves_authentication(ingress):
    """The ingress guard must not mistake a bounded body for authorization."""
    response = asyncio.run(post(multipart(1024)))
    assert response.status_code == 401
    assert len(ingress) == 1


@pytest.mark.parametrize("kind", ["idle", "total"])
def test_upload_deadline_closes_parser_files(ingress, monkeypatch, kind):
    """Expire after an actual file opens, not before scheduling reaches parsing."""
    monkeypatch.setattr(upload_boundary, "MAX_UPLOAD_PARSERS", 1)
    clock = [0.0]
    waits, cancelled = [], []
    original_open = formparsers.SpooledTemporaryFile

    def opened(*args, **kwargs):
        file = original_open(*args, **kwargs)
        if kind == "total":
            clock[0] = upload_boundary.UPLOAD_TOTAL_SECONDS + 1
        return file

    async def chunks():
        # Reproduce the old fixture failure deterministically: its 20ms limit
        # could expire before there was any parser file to test for cleanup.
        await asyncio.sleep(0.05)
        yield multipart(256)[:-13]
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)
        yield b"--audit--\r\n"

    async def wait_receive(awaitable, timeout):
        waits.append(timeout)
        # Only the already-opened parser gets a deliberately expiring real
        # asyncio timeout. The first read has a test watchdog, not a synthetic
        # 20ms precondition. The module-local proxy leaves ASGI/httpx clocks
        # and global asyncio scheduling untouched.
        return await asyncio.wait_for(awaitable, 0.02 if ingress else 5)

    async def exercise():
        # Missing rejection or a bypassed wait must fail, never hang the suite.
        return await asyncio.wait_for(post(chunks()), SCENARIO)

    # Keep the production 30s/120s constants and assert their chosen wait at
    # the seam. Total expiry jumps only this module's clock after file-open;
    # idle expiry uses actual await cancellation on the next body receive.
    # All injected dependencies end before the single-slot capacity probe.
    with monkeypatch.context() as deadline:
        deadline.setattr(formparsers, "SpooledTemporaryFile", opened)
        deadline.setattr(upload_boundary, "time", SimpleNamespace(monotonic=lambda: clock[0]))
        deadline.setattr(upload_boundary, "asyncio", SimpleNamespace(wait_for=wait_receive))
        response = asyncio.run(exercise())
        assert response.status_code == 408
        assert response.headers["X-Error-Code"] == "upload_timeout"
        assert ingress
        assert all(file.closed for file in ingress)
        expected = min(upload_boundary.UPLOAD_IDLE_SECONDS, upload_boundary.UPLOAD_TOTAL_SECONDS)
        assert waits == [expected] * (2 if kind == "idle" else 1)
        assert cancelled == ([True] if kind == "idle" else [])

    # One slot makes a retained parser observable as 429 rather than allowing
    # the next request into a second slot. Keep the slow valid transfer as a
    # positive control under the ordinary clock, receive and deadline limits.
    async def legitimate_chunks():
        body = multipart()
        yield body[:-13]
        await asyncio.sleep(0.05)
        yield body[-13:]

    assert asyncio.run(post(legitimate_chunks())).status_code == 401


def test_parser_capacity_rejects_before_receive_and_recovers(ingress, monkeypatch):
    """Slow unauthenticated uploads need a host limit separate from LLM slots."""
    monkeypatch.setattr(upload_boundary, "MAX_UPLOAD_PARSERS", 1)

    async def exercise():
        started, release = asyncio.Event(), asyncio.Event()

        async def held():
            started.set()
            await release.wait()
            yield multipart()

        first = asyncio.create_task(post(held()))
        try:
            await asyncio.wait_for(started.wait(), STEP)
            response = await post(multipart())
            assert response.status_code == 429
            assert response.headers["X-Error-Code"] == "upload_capacity"
            assert ingress == []
        finally:
            release.set()
            await first
        assert (await post(multipart())).status_code == 401

    asyncio.run(exercise())


def test_parser_slot_is_released_before_paid_work(monkeypatch, tmp_path):
    """Keep parser capacity independent of paid latency, without a 200ms precondition."""
    monkeypatch.setattr(papers, "PAPERS_ROOT", tmp_path / "papers")
    monkeypatch.setattr(access, "ACCESS_CODE", "offline-fixture")
    monkeypatch.setattr(upload_boundary, "MAX_UPLOAD_PARSERS", 1)
    assert (upload_boundary.UPLOAD_TOTAL_SECONDS, upload_boundary.UPLOAD_IDLE_SECONDS) == (120, 30)
    clock = [0.0]
    monkeypatch.setattr(upload_boundary, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    provider = MagicMock(side_effect=AssertionError("No provider may be reached"))
    monkeypatch.setattr(main, "extract_paper_contribution", provider)
    # A finite observation produced 408 before paid entry with an expired
    # ingress clock; it did NOT establish the historical failed POST's status.
    # Keep real receive waits at production limits, not the former 200ms.
    # Only this boundary's clock advances, at actual paid-mock entry. The
    # separate ASGI test below explicitly exercises receive after that handoff.

    async def exercise():
        started, release = asyncio.Event(), asyncio.Event()
        contribution = main.PaperContribution(
            title="Offline paper", core_contribution="x" * 25,
            application_domain="energy storage", delta_from_prior="y" * 15,
            commercialization_topic="z" * 15, search_keywords=["a", "b", "c"],
        )

        async def process(paper_id, *_args, **_kwargs):
            clock[0] = upload_boundary.UPLOAD_TOTAL_SECONDS + 1
            started.set()
            await release.wait()
            papers.save_extraction(paper_id, contribution.model_dump())
            return contribution

        monkeypatch.setattr(main, "_process_uploaded_paper", process)
        first = asyncio.create_task(post(multipart(), {"X-Access-Code": "offline-fixture"}))
        waiter = asyncio.create_task(started.wait())
        tasks = {first, waiter}
        primary_error = None

        def task_state(task):
            # Never include response bodies, exception strings or request data.
            if not task.done():
                return "pending"
            if task.cancelled():
                return "cancelled"
            error = task.exception()
            if error is not None:
                return "exception_type=" + type(error).__name__
            response = task.result()
            code = response.headers.get("X-Error-Code")
            safe_code = code if code in {None, "upload_timeout", "upload_capacity", "rate_limited"} else "other"
            return f"status={response.status_code},code={safe_code}"

        try:
            done, _ = await asyncio.wait(tasks, timeout=STEP, return_when=asyncio.FIRST_COMPLETED)
            assert waiter in done and first not in done, "paid entry not observed; first=" + task_state(first)
            second = asyncio.create_task(post(multipart()))
            tasks.add(second)
            done, _ = await asyncio.wait({second}, timeout=STEP)
            assert second in done and not second.cancelled(), "second=" + task_state(second)
            assert second.exception() is None, "second=" + task_state(second)
            assert second.result().status_code == 401, "second=" + task_state(second)
        except BaseException as exc:  # Preserve the first failure across cleanup, including cancellation.
            primary_error = exc
            raise
        finally:
            release.set()
            waiter.cancel()
            cleanup_errors = []
            # Each drain phase has its own STEP watchdog (tests/scripted_waits.py). wait()
            # does not silently extend it while waiting for cancellation.
            try:
                _, pending = await asyncio.wait(tasks, timeout=STEP)
            except BaseException as exc:
                cleanup_errors.append("drain_type=" + type(exc).__name__)
                pending = {task for task in tasks if not task.done()}
            for task in pending:
                task.cancel()
            if pending:
                cleanup_errors.append("drain_required_cancellation")
                try:
                    _, pending = await asyncio.wait(pending, timeout=STEP)
                except BaseException as exc:
                    cleanup_errors.append("cancel_drain_type=" + type(exc).__name__)
            if pending:
                cleanup_errors.append("tasks_still_pending")
            for task in tasks:
                if task is not waiter and task.done():
                    if task.cancelled() or task.exception() is not None:
                        cleanup_errors.append(task_state(task))
            if primary_error is not None:
                primary_error.add_note("first POST after drain: " + task_state(first))
            if cleanup_errors:
                detail = "upload cleanup: " + ";".join(cleanup_errors)
                if primary_error is not None:
                    primary_error.add_note(detail)
                else:
                    raise AssertionError(detail)
        assert first.result().status_code == 200, "first=" + task_state(first)
        assert list(papers.PAPERS_ROOT.glob("*/paper.pdf")) == []

    asyncio.run(exercise())
    provider.assert_not_called()


@pytest.mark.parametrize("released", [True, False], ids=["released", "unreleased"])
def test_upload_deadline_after_parser_handoff(ingress, monkeypatch, released):
    """Same-scope late receive bypasses ingress time only after genuine release."""
    assert (upload_boundary.UPLOAD_TOTAL_SECONDS, upload_boundary.UPLOAD_IDLE_SECONDS) == (120, 30)
    monkeypatch.setattr(upload_boundary, "MAX_UPLOAD_PARSERS", 1)
    clock, waits, received, sent = [0.0], [], [], []
    real_wait_for = asyncio.wait_for

    async def wait_receive(awaitable, timeout):
        waits.append(timeout)
        return await real_wait_for(awaitable, timeout)  # Observe, never replace the production budget.

    monkeypatch.setattr(upload_boundary, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(upload_boundary, "asyncio", SimpleNamespace(wait_for=wait_receive))
    scope = {"type": "http", "method": "POST", "path": "/api/papers",
             "headers": [(b"content-type", b"multipart/form-data; boundary=audit")]}
    disconnect = {"type": "http.disconnect"}
    messages = [{"type": "http.request", "body": multipart(), "more_body": False}, disconnect]
    late_message = None

    async def receive():
        message = messages[len(received)]
        received.append(message)
        return message

    async def send(message):
        sent.append(message)

    async def parsed_app(actual_scope, bounded_receive, bounded_send):
        nonlocal late_message
        assert actual_scope is scope
        # Parse actual multipart bytes and close the actual spooled files. A
        # direct ASGI message source avoids httpx's response/disconnect wait
        # dependency; this is a boundary test, not network delivery evidence.
        async with Request(actual_scope, bounded_receive).form() as form:
            assert form["file"].size == 64
            assert ingress and all(not file.closed for file in ingress)
            assert waits == [30]
            if released:
                upload_boundary.release_upload_slot(actual_scope)
            clock[0] = upload_boundary.UPLOAD_TOTAL_SECONDS + 1
            try:
                late_message = await bounded_receive()
            except formparsers.MultiPartException:
                # The downstream parser's generic response is NOT our expected
                # 408: the real bounded_send must perform that conversion.
                response = Response(status_code=400)
            else:
                response = Response(status_code=200)
        await response(actual_scope, bounded_receive, bounded_send)

    async def exercise():
        boundary = upload_boundary.PaperUploadBoundary(parsed_app)
        await asyncio.wait_for(boundary(scope, receive, send), SCENARIO)

    asyncio.run(exercise())
    starts = [message for message in sent if message["type"] == "http.response.start"]
    assert len(starts) == 1
    status = starts[0]["status"]
    code = dict(starts[0]["headers"]).get(b"x-error-code")
    assert (status, code) == ((200, None) if released else (408, b"upload_timeout"))
    assert late_message is (disconnect if released else None)
    assert len(received) == (2 if released else 1)
    assert waits == [30], "Crossing the deadline must not introduce another timed wait"
    assert ingress and all(file.closed for file in ingress)
