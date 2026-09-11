"""Assert ingress limits at HTTP/parser seams, before auth or paid admission."""

import asyncio
from unittest.mock import MagicMock

import httpx
import pytest
from starlette import formparsers

# Match the ordinary test bootstrap: main loads the operator's .env, while
# runs snapshots quota defaults at import. Importing main first would make
# unrelated offline admission tests inherit the developer's wallet setting.
from api import access, papers, runs, upload_boundary
from api import main


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
    """A slow body cannot retain a parser slot indefinitely before paid admission."""
    monkeypatch.setattr(upload_boundary, "MAX_UPLOAD_PARSERS", 1)

    async def chunks():
        yield multipart(256)[:-13]
        await asyncio.sleep(1)
        yield b"--audit--\r\n"

    # Scope the artificial fault to the rejected request. Keeping its 20ms
    # limit for the capacity probe made Windows scheduling look like a leak:
    # a correct next request timed out (408) before reaching authentication.
    # Do not relax 408/auth assertions or change the production timeouts.
    with monkeypatch.context() as deadline:
        deadline.setattr(upload_boundary, "UPLOAD_IDLE_SECONDS", 0.02 if kind == "idle" else 1)
        deadline.setattr(upload_boundary, "UPLOAD_TOTAL_SECONDS", 1 if kind == "idle" else 0.02)
        response = asyncio.run(post(chunks()))
        assert response.status_code == 408
        assert response.headers["X-Error-Code"] == "upload_timeout"
        assert ingress
        assert all(file.closed for file in ingress)

    # One slot makes a retained parser observable as 429 rather than allowing
    # the next request into a second slot. A 50ms valid transfer also makes
    # failure to restore the ordinary deadline deterministic, not host-speed
    # dependent. The normal request must still reach auth and return 401.
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
            await asyncio.wait_for(started.wait(), 2)
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
    """Ingress time/capacity must not be extended across a paid model request."""
    monkeypatch.setattr(papers, "PAPERS_ROOT", tmp_path / "papers")
    monkeypatch.setattr(access, "ACCESS_CODE", "offline-fixture")
    monkeypatch.setattr(upload_boundary, "MAX_UPLOAD_PARSERS", 1)
    monkeypatch.setattr(upload_boundary, "UPLOAD_TOTAL_SECONDS", 0.2)

    async def exercise():
        started, release = asyncio.Event(), asyncio.Event()
        contribution = main.PaperContribution(
            title="Offline paper", core_contribution="x" * 25,
            application_domain="energy storage", delta_from_prior="y" * 15,
            commercialization_topic="z" * 15, search_keywords=["a", "b", "c"],
        )

        async def process(paper_id, *_args, **_kwargs):
            started.set()
            await release.wait()
            papers.save_extraction(paper_id, contribution.model_dump())
            return contribution

        monkeypatch.setattr(main, "_process_uploaded_paper", process)
        first = asyncio.create_task(post(multipart(), {"X-Access-Code": "offline-fixture"}))
        try:
            await asyncio.wait_for(started.wait(), 2)
            assert (await post(multipart())).status_code == 401
        finally:
            release.set()
        assert (await first).status_code == 200
        assert list(papers.PAPERS_ROOT.glob("*/paper.pdf")) == []

    asyncio.run(exercise())
