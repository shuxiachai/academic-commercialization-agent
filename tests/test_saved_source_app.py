"""Real isolated ASGI/load/locator/serialization seams; no provider traffic."""

import asyncio
from contextlib import suppress
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from unittest.mock import Mock

from fastapi.testclient import TestClient
import httpx
import pytest

from academic_agent import report_evidence_source_locator as locator
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot
from academic_agent.saved_source_loader import (
    SavedSourceLoader, SavedSourceMissing, SavedSourceUnavailable, snapshot_from_saved_bytes,
)
from api import saved_source_app as api

RUN_ID = "20260919T123456Z-0123456789abcdef0123456789abcdef"
URL = f"/api/runs/{RUN_ID}/saved-source-location"
RAW_TEXT = "  测试🙂e\u0301\r\n<script>not executable</script>\t "


def registry(text=RAW_TEXT):
    return {"academic_sources": [{
        "source_id": "A1", "title": "<script>hostile title</script>", "publisher": " Saved publisher ",
        "source_type": "academic_paper", "url": "javascript:alert(1)", "doi": "exact DOI",
        "published_date": "2099-01-01", "accessed_date": "exact old string",
        "evidence_summary": text, "summary_source": "abstract",
    }], "patent_sources": [], "market_sources": []}


def snapshot(text=RAW_TEXT):
    return snapshot_from_saved_bytes(json.dumps(registry(text)).encode(), RUN_ID)


def select(_request):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": "selection", "type": "function", "function": {
            "name": "read_source", "arguments": '{"source_id":"A1"}',
        },
    }]}


def make_app(*, text=RAW_TEXT, selector=select, load_snapshot=None):
    return api.create_saved_source_app(load_snapshot=load_snapshot or (lambda _run_id: snapshot(text)),
                                       selector=selector)


def assert_error(reply, status, code):
    assert reply.status_code == status
    assert reply.json() == {"detail": api._ERRORS[code][1], "error_code": code}
    assert reply.headers["cache-control"] == "no-store"
    assert reply.headers["x-content-type-options"] == "nosniff"
    assert reply.headers["x-frame-options"] == "DENY"


def test_real_loader_to_response_model_preserves_all_fields(tmp_path):
    """Every nested frozen field must reach HTTP, not only a hand-picked subset."""
    path = tmp_path / RUN_ID
    path.mkdir()
    raw = json.dumps(registry(), ensure_ascii=False).encode()
    (path / "validated_sources.json").write_bytes(raw)
    expected = json.loads(locator.render_locator_result(locator.locate_saved_source(
        snapshot_from_saved_bytes(raw, RUN_ID), "  exact question \r\n", selector=select)))
    calls = []
    def observed(request):
        calls.append(request)
        return select(request)
    app = make_app(load_snapshot=SavedSourceLoader(tmp_path), selector=observed)
    route = next(route for route in app.routes if getattr(route, "path", None) == URL.replace(RUN_ID, "{run_id}"))
    assert route.response_model is api.SavedSourceEnvelope
    with TestClient(app) as client:
        reply = client.post(URL, json={"question": "  exact question \r\n"})
    assert reply.status_code == 200
    assert reply.json() == {"schema_version": 1, "selector_mode": "injected_callback",
                            "billing_integration": "not_implemented", "result": expected}
    result = reply.json()["result"]
    assert set(result) == set(locator.LocatorResult.model_fields)
    assert set(result["catalog"]) == set(locator.LocatorCatalog.model_fields)
    assert set(result["source"]) == set(locator.LocatorSource.model_fields)
    assert set(result["saved_text"]) == set(locator.LocatorText.model_fields)
    assert result["saved_text"]["text"] == RAW_TEXT
    assert calls[0]["messages"][1]["content"] == "  exact question \r\n"
    assert len(calls) == 1


@pytest.mark.parametrize("text,state,reason", [
    (None, "missing_text", "saved_text_missing"), ("", "missing_text", "saved_text_missing"),
    (" \t\r\n", "blank_text", "saved_text_blank"), ("🙂" * 1500, "excerpt", "saved_text"),
    ("x" * 1501, "out_of_scope", "selected_text_too_long"),
])
def test_domain_outcomes_are_200_and_never_clipped(text, state, reason):
    with TestClient(make_app(text=text)) as client:
        reply = client.post(URL, json={"question": "Where?"})
    assert reply.status_code == 200
    result = reply.json()["result"]
    assert (result["state"], result["reason"]) == (state, reason)
    assert result["semantic_support"] == result["selection_relevance"] == "not_assessed"
    if state in {"excerpt", "blank_text"}:
        assert result["saved_text"]["text"] == text
        assert result["saved_text"]["window_truncated"] is False
    else:
        assert result["saved_text"] is None
    assert result["read_attempts"] == int(state != "out_of_scope")


@pytest.mark.parametrize("response,reason", [
    ({"role": "assistant", "content": '{"action":"decline"}'}, "selector_declined"),
    ({"role": "assistant", "content": None, "refusal": "PRIVATE REFUSAL"}, "selector_refused"),
])
def test_decline_and_refusal_do_not_echo_model_prose(response, reason):
    with TestClient(make_app(selector=lambda _request: response)) as client:
        reply = client.post(URL, json={"question": "Where?"})
    assert reply.status_code == 200
    assert reply.json()["result"]["reason"] == reason
    assert reply.json()["result"]["read_attempts"] == 0
    assert "PRIVATE" not in reply.text


def test_empty_snapshot_has_no_callback_and_explicit_coverage():
    callback = Mock(side_effect=AssertionError("must not call"))
    empty = ReportEvidenceSnapshot(report_ref=RUN_ID, sources=())
    with TestClient(make_app(selector=callback, load_snapshot=lambda _: empty)) as client:
        reply = client.post(URL, json={"question": "Where?"})
    assert reply.status_code == 200
    assert reply.json()["result"]["state"] == "no_sources"
    assert reply.json()["result"]["catalog"]["total_count"] == 0
    callback.assert_not_called()


def test_partial_catalog_and_callback_budget_survive_http():
    source = snapshot().sources[0]
    many = ReportEvidenceSnapshot(report_ref=RUN_ID, sources=tuple(
        source.model_copy(update={"source_id": f"A{i}"}) for i in range(1, 41)))
    callback = Mock(side_effect=select)
    with TestClient(make_app(load_snapshot=lambda _: many, selector=callback)) as client:
        result = client.post(URL, json={"question": "Where?"}).json()["result"]
        assert result["catalog"]["coverage"] == "partial"
        assert result["catalog"]["omitted_count"] > 0
        # 4096 Unicode code points are valid input, but the frozen callback
        # ASCII-wire budget may independently refuse entry.
        reply = client.post(URL, json={"question": "🙂" * 4096})
    assert reply.status_code == 200
    assert reply.json()["result"]["reason"] == "callback_budget_exceeded"
    assert callback.call_count == 1


def test_disabled_is_before_loader_and_never_enabled_by_headers(monkeypatch):
    load = Mock(side_effect=AssertionError("must not load"))
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-private-sentinel")
    monkeypatch.setenv("QWEN_API_KEY", "ambient-private-sentinel")
    monkeypatch.setenv("ACCESS_CODE", "ambient-private-sentinel")
    with TestClient(api.create_saved_source_app(load_snapshot=load)) as client:
        reply = client.post(URL, json={"question": "Where?"}, headers={
            "X-Access-Code": "ambient-private-sentinel", "Authorization": "Bearer ambient-private-sentinel",
        })
    assert_error(reply, 503, "selector_disabled")
    assert "ambient-private" not in reply.text
    load.assert_not_called()


@pytest.mark.parametrize("header", [{}, {"X-Access-Code": "invalid"}, {"X-Access-Code": "owner"}])
def test_run_capability_read_does_not_require_or_select_a_payer(header):
    load = Mock(return_value=snapshot())
    with TestClient(make_app(load_snapshot=load)) as client:
        reply = client.post(URL, json={"question": "Where?"}, headers=header)
    assert reply.status_code == 200
    load.assert_called_once_with(RUN_ID)


@pytest.mark.parametrize("value", [
    {}, [], None, {"question": None}, {"question": 12}, {"question": True},
    {"question": ""}, {"question": " \r\n\t"}, {"question": "x" * 4097},
    {"question": "x", "api_key": "PRIVATE KEY"}, {"question": "x", "source_id": "A1"},
    {"question": "x", "model": "private model"}, {"question": "x", "endpoint": "private endpoint"},
])
def test_invalid_inputs_are_fixed_non_echoing_errors(value):
    load = Mock()
    with TestClient(make_app(load_snapshot=load)) as client:
        reply = client.post(URL, content=json.dumps(value))
    assert_error(reply, 422, "invalid_request")
    load.assert_not_called()


@pytest.mark.parametrize("body", [
    b"\xff", b"{malformed-private", b'{"question":"a","question":"b"}',
    b'{"question":NaN}', b'{"question":"\\ud800"}', b"[" * 1100 + b"]" * 1100,
])
def test_strict_request_parser_rejects_duplicate_nonfinite_or_invalid_unicode(body):
    load = Mock()
    with TestClient(make_app(load_snapshot=load)) as client:
        reply = client.post(URL, content=body)
    assert_error(reply, 422, "invalid_request")
    load.assert_not_called()


def test_4096_codepoint_question_is_not_trimmed():
    callback = Mock(side_effect=select)
    question = " " + "x" * 4094 + " "
    with TestClient(make_app(selector=callback)) as client:
        reply = client.post(URL, json={"question": question})
    assert reply.status_code == 200
    assert callback.call_args.args[0]["messages"][1]["content"] == question


async def raw_post(app, chunks, *, headers=(), disconnect=False):
    messages = []
    parts = iter(chunks)
    async def receive():
        try:
            chunk = next(parts)
            return {"type": "http.request", "body": chunk, "more_body": True}
        except StopIteration:
            return {"type": "http.disconnect"} if disconnect else {
                "type": "http.request", "body": b"", "more_body": False}
    async def send(message):
        messages.append(message)
    await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
               "method": "POST", "scheme": "http", "path": URL, "raw_path": URL.encode(),
               "query_string": b"", "headers": list(headers), "client": ("test", 1),
               "server": ("test", 80)}, receive, send)
    start = next(item for item in messages if item["type"] == "http.response.start")
    body = b"".join(item.get("body", b"") for item in messages if item["type"] == "http.response.body")
    return start["status"], json.loads(body)


@pytest.mark.parametrize("headers", [(), ((b"content-length", b"1"),)])
def test_actual_streamed_body_is_bounded_before_json_parsing(headers):
    """Absent or dishonest Content-Length cannot bypass the accumulated bound."""
    load = Mock()
    app = make_app(load_snapshot=load)
    status, body = asyncio.run(raw_post(app, [b" " * 32768, b" " * 32768, b"x"], headers=headers))
    assert (status, body["error_code"]) == (413, "body_too_large")
    load.assert_not_called()


def test_exact_body_bound_and_midbody_disconnect():
    app = make_app()
    raw = b'{"question":"Where?"}'
    status, body = asyncio.run(raw_post(app, [raw, b" " * (api.MAX_BODY_BYTES - len(raw))]))
    assert status == 200 and body["result"]["state"] == "excerpt"
    load = Mock()
    status, body = asyncio.run(raw_post(make_app(load_snapshot=load), [b'{"question":'], disconnect=True))
    assert (status, body["error_code"]) == (422, "invalid_request")
    load.assert_not_called()


@pytest.mark.parametrize("error,code,status", [
    (SavedSourceMissing(), "saved_source_missing", 404),
    (SavedSourceUnavailable(), "saved_source_unavailable", 503),
    (PermissionError("PRIVATE PATH"), "execution_unavailable", 503),
])
def test_loader_errors_are_safe(error, code, status):
    with TestClient(make_app(load_snapshot=Mock(side_effect=error))) as client:
        reply = client.post(URL, json={"question": "PRIVATE QUESTION"})
    assert_error(reply, status, code)
    assert "PRIVATE" not in reply.text


def test_selector_contract_and_execution_failures_are_not_domain_success():
    with TestClient(make_app(selector=lambda _: {"private": "model prose"})) as client:
        assert_error(client.post(URL, json={"question": "Where?"}), 502, "selector_contract_error")
    with TestClient(make_app(selector=Mock(side_effect=RuntimeError("PRIVATE KEY")))) as client:
        reply = client.post(URL, json={"question": "Where?"})
    assert_error(reply, 503, "execution_unavailable")
    assert "PRIVATE" not in reply.text


def test_forged_result_cannot_bypass_frozen_renderer(monkeypatch):
    """model_copy can forge nested text, so serialization must reconstruct it."""
    result = locator.locate_saved_source(snapshot(), "Where?", selector=select)
    forged = result.model_copy(update={"saved_text": result.saved_text.model_copy(update={"text": "forged"})})
    monkeypatch.setattr(api, "locate_saved_source", lambda *_a, **_k: forged)
    with TestClient(make_app()) as client:
        assert_error(client.post(URL, json={"question": "Where?"}), 503, "execution_unavailable")


@pytest.mark.parametrize("run_id", [
    "not-a-run", "20260919T123456Z-a%0A", "20260919T123456Z-a:stream",
    "20260919T123456Z-", "20260919T123456Z-" + "a" * 31, "20260919T123456Z-" + "a" * 33,
])
def test_invalid_capability_never_reaches_injected_loader(run_id):
    load = Mock()
    with TestClient(make_app(load_snapshot=load)) as client:
        reply = client.post(f"/api/runs/{run_id}/saved-source-location", json={"question": "Where?"})
    assert_error(reply, 422, "invalid_request")
    load.assert_not_called()


def test_page_assets_and_all_errors_are_same_origin_no_store():
    with TestClient(make_app()) as client:
        for path in ("/", "/lab-static/app.js", "/lab-static/app.css"):
            reply = client.get(path)
            assert reply.status_code == 200
            assert reply.headers["cache-control"] == "no-store"
            assert "frame-ancestors 'none'" in reply.headers["content-security-policy"]
            assert "'unsafe-inline'" not in reply.headers["content-security-policy"]
            assert reply.headers["x-content-type-options"] == "nosniff"
            assert "access-control-allow-origin" not in reply.headers
        for path in ("/api/runs", "/api/receipts", "/docs", "/openapi.json", "/static/app.js",
                     "/lab-static/../index.html", "/lab-static/%2e%2e/index.html"):
            assert_error(client.get(path), 404, "not_found")
        assert_error(client.delete(URL), 405, "method_not_allowed")


async def wait_event(event):
    assert await asyncio.to_thread(event.wait, 5), "worker event not reached"


@pytest.mark.parametrize("stage", ["loader", "selector", "read", "serialize"])
def test_physical_worker_holds_slot_after_http_cancellation(stage, monkeypatch):
    """Cancelling any HTTP waiter must not admit a replacement physical operation."""
    started, release = threading.Event(), threading.Event()
    callback_count = 0
    def block():
        started.set()
        assert release.wait(10), "test did not release worker"
    def load(_run_id):
        if stage == "loader":
            block()
        return snapshot()
    def callback(request):
        nonlocal callback_count
        callback_count += 1
        if stage == "selector":
            block()
        return select(request)
    original_read = locator.read_source
    original_render = api.render_locator_result
    def read(*args, **kwargs):
        if stage == "read":
            block()
        return original_read(*args, **kwargs)
    def render(result):
        if stage == "serialize":
            block()
        return original_render(result)
    monkeypatch.setattr(locator, "read_source", read)
    monkeypatch.setattr(api, "render_locator_result", render)
    app = make_app(load_snapshot=load, selector=callback)

    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                first = asyncio.create_task(client.post(URL, json={"question": "Where?"}))
                try:
                    await wait_event(started)
                    assert_error(await client.post(URL, json={"question": "Second?"}), 429, "locator_busy")
                    first.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await first
                    assert_error(await client.post(URL, json={"question": "Replacement?"}), 429, "locator_busy")
                    assert callback_count == int(stage != "loader")
                finally:
                    release.set()
                    with suppress(asyncio.CancelledError):
                        await first
        assert callback_count == 1
    asyncio.run(scenario())


def test_shutdown_atomically_closes_and_asynchronously_drains_actual_thread(monkeypatch):
    """A cancelled HTTP task is not an exited worker; shutdown must await join."""
    started, release, joining = threading.Event(), threading.Event(), threading.Event()
    original_join = threading.Thread.join
    def callback(request):
        started.set()
        assert release.wait(10)
        return select(request)
    def join(thread, *args, **kwargs):
        if thread.name == "saved-source-locator":
            joining.set()
        return original_join(thread, *args, **kwargs)
    monkeypatch.setattr(threading.Thread, "join", join)
    app = make_app(selector=callback)

    async def scenario():
        lifespan = app.router.lifespan_context(app)
        await lifespan.__aenter__()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            first = asyncio.create_task(client.post(URL, json={"question": "Where?"}))
            closing = None
            try:
                await wait_event(started)
                first.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await first
                closing = asyncio.create_task(lifespan.__aexit__(None, None, None))
                await wait_event(joining)
                # Reaching this coroutine and HTTP reply also proves join is
                # not blocking the ASGI loop. No polling or timing sleeps.
                assert not closing.done()
                assert_error(await client.post(URL, json={"question": "New?"}), 503, "locator_closing")
                closing.cancel()
                assert_error(await client.post(URL, json={"question": "Still closed?"}), 503, "locator_closing")
                assert not closing.done()
            finally:
                release.set()
                if closing is not None:
                    with suppress(asyncio.CancelledError):
                        await closing
                else:
                    await lifespan.__aexit__(None, None, None)
            assert not any(thread.name == "saved-source-locator" and thread.is_alive()
                           for thread in threading.enumerate())
    asyncio.run(scenario())


async def _exercise_physical_thread_window(monkeypatch, *, window, cancel_waiter):
    """Hold a real thread outside its target, never fake is_alive or occupancy."""
    reached, release, joining = threading.Event(), threading.Event(), threading.Event()
    workers = []
    original_start = threading.Thread.start
    original_run = threading.Thread.run
    original_join = threading.Thread.join

    def start(thread, *args, **kwargs):
        if thread.name == "saved-source-locator":
            workers.append(thread)
        return original_start(thread, *args, **kwargs)

    def hold():
        reached.set()
        assert release.wait(10), "test did not release physical worker"

    def run(thread):
        first = bool(workers) and thread is workers[0]
        if first and window == "pre_operate":
            hold()
        original_run(thread)
        if first and window == "post_target":
            hold()

    def join(thread, *args, **kwargs):
        if workers and thread is workers[0]:
            joining.set()
        return original_join(thread, *args, **kwargs)

    monkeypatch.setattr(threading.Thread, "start", start)
    monkeypatch.setattr(threading.Thread, "run", run)
    monkeypatch.setattr(threading.Thread, "join", join)
    load = Mock(return_value=snapshot())
    callback = Mock(side_effect=select)
    app = make_app(load_snapshot=load, selector=callback)
    delivery_reached, deliver = asyncio.Event(), asyncio.Event()

    async def transport_app(scope, receive, send):
        # Keep the first HTTP waiter cancellable even after its worker target
        # published a result. This models a response awaiting client delivery;
        # subsequent requests still traverse the unmodified app normally.
        async def deliver_response(message):
            if ((b"x-test-hold-delivery", b"yes") in scope.get("headers", [])
                    and message["type"] == "http.response.start"):
                delivery_reached.set()
                await deliver.wait()
            await send(message)
        await app(scope, receive, deliver_response)

    lifespan = app.router.lifespan_context(app)
    await lifespan.__aenter__()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(transport_app), base_url="http://test") as client:
        first = asyncio.create_task(client.post(URL, json={"question": "First?"},
                                                headers={"x-test-hold-delivery": "yes"}))
        closing = None
        try:
            await wait_event(reached)
            if window == "post_target":
                await asyncio.wait_for(delivery_reached.wait(), 5)
            expected_calls = int(window == "post_target")
            assert workers[0].is_alive()
            assert load.call_count == callback.call_count == expected_calls
            assert_error(await client.post(URL, json={"question": "Second?"}), 429, "locator_busy")
            assert len(workers) == 1
            assert load.call_count == callback.call_count == expected_calls

            if cancel_waiter:
                first.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await first
                assert_error(await client.post(URL, json={"question": "Replacement?"}), 429, "locator_busy")
                assert len(workers) == 1
                assert workers[0].is_alive()
                assert load.call_count == callback.call_count == expected_calls

            closing = asyncio.create_task(lifespan.__aexit__(None, None, None))
            await wait_event(joining)
            assert not closing.done()
            # A responsive ASGI request while join waits proves asynchronous
            # drain; closing has priority over the still-occupied thread.
            assert_error(await client.post(URL, json={"question": "After closing?"}), 503, "locator_closing")
            assert len(workers) == 1
            assert load.call_count == callback.call_count == expected_calls
            assert not closing.done()
        finally:
            release.set()
            deliver.set()
            if closing is None:
                await lifespan.__aexit__(None, None, None)
            else:
                await closing
            with suppress(asyncio.CancelledError):
                await first
        assert len(workers) == 1
        assert not workers[0].is_alive()
        # Pre-entry shutdown must prevent the pending loader/callback entirely.
        assert load.call_count == callback.call_count == int(window == "post_target")
        if not cancel_waiter:
            if window == "pre_operate":
                assert_error(first.result(), 503, "locator_closing")
            else:
                assert first.result().status_code == 200


@pytest.mark.parametrize("cancel_waiter", [False, True], ids=["waiting", "cancelled"])
def test_registered_thread_blocks_admission_before_operate(monkeypatch, cancel_waiter):
    """A started but not-yet-entered worker cannot admit a second physical thread."""
    asyncio.run(_exercise_physical_thread_window(monkeypatch, window="pre_operate", cancel_waiter=cancel_waiter))


@pytest.mark.parametrize("cancel_waiter", [False, True], ids=["waiting", "cancelled"])
def test_target_return_keeps_admission_until_physical_exit(monkeypatch, cancel_waiter):
    """Target completion/result delivery is earlier than physical thread exit."""
    asyncio.run(_exercise_physical_thread_window(monkeypatch, window="post_target", cancel_waiter=cancel_waiter))


def test_thread_start_failure_rolls_back_registration(monkeypatch):
    """A never-started thread must not poison future admission or shutdown join."""
    original_start = threading.Thread.start
    attempts = []
    callback = Mock(side_effect=select)
    def start(thread, *args, **kwargs):
        if thread.name == "saved-source-locator":
            attempts.append(thread)
            if len(attempts) == 1:
                raise RuntimeError("PRIVATE start failure")
        return original_start(thread, *args, **kwargs)
    monkeypatch.setattr(threading.Thread, "start", start)
    with TestClient(make_app(selector=callback)) as client:
        assert_error(client.post(URL, json={"question": "First?"}), 503, "execution_unavailable")
        callback.assert_not_called()
        assert client.post(URL, json={"question": "After failed start?"}).status_code == 200
        callback.assert_called_once()
    assert len(attempts) == 2
    assert all(not thread.is_alive() for thread in attempts)


def test_slot_releases_after_success_and_failure():
    callback = Mock(side_effect=[RuntimeError("private"), select({}), select({})])
    with TestClient(make_app(selector=callback)) as client:
        assert_error(client.post(URL, json={"question": "Where?"}), 503, "execution_unavailable")
        assert client.post(URL, json={"question": "Where?"}).status_code == 200
        assert client.post(URL, json={"question": "Where?"}).status_code == 200
    assert callback.call_count == 3


def test_factory_import_is_inert_and_production_has_no_new_route():
    """Fresh process guards forbid provider/retrieval/dotenv imports or key lookup."""
    script = '''
import builtins, os, sys
import fastapi
original = builtins.__import__
forbidden = ("dotenv", "crewai", "openai", "academic_agent.evidence", "academic_agent.source_pipeline",
             "academic_agent.llm_config", "api.main", "api.access", "api.runs", "api.receipts")
def guarded(name, *args, **kwargs):
    if any(name == item or name.startswith(item + ".") for item in forbidden):
        raise AssertionError("forbidden import")
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
original_environment_read = type(os.environ).__getitem__
def no_environment(self, name):
    # Pydantic itself consults its plugin switch for every model class. This
    # framework setting is not provider/app configuration; every other lookup
    # remains forbidden, including direct environ access as well as getenv.
    if name == "PYDANTIC_DISABLE_PLUGINS":
        return original_environment_read(self, name)
    raise AssertionError("environment lookup")
type(os.environ).__getitem__ = no_environment
for key in ("OPENAI_API_KEY", "DASHSCOPE_API_KEY", "ACCESS_CODE"):
    try:
        os.getenv(key)
    except AssertionError:
        pass
    else:
        raise AssertionError("credential guard failed")
from api import saved_source_app
assert not hasattr(saved_source_app, "app")
app = saved_source_app.create_saved_source_app(load_snapshot=lambda _: None)
assert app is not None
assert not any(name in sys.modules for name in forbidden)
'''
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    production = (Path(__file__).resolve().parents[1] / "api" / "main.py").read_text(encoding="utf-8")
    assert "saved_source_app" not in production
    assert "saved-source-location" not in production
    assert "saved-source-lab" not in production


def _production_absence_probe(tmp_path, *, inject_post=False, check_filesystem=False, receipt_probe="none"):
    """Import the real production app in a credential-free, disposable process."""
    script = r'''
import asyncio
import http.client
import os
from pathlib import Path
import sys
from unittest.mock import patch

import dotenv
import dotenv.main
import httpx
from starlette.routing import Match

root = Path(sys.argv[1]).resolve()
temporary = Path.cwd().resolve()
sys.path[:0] = [str(root), str(root / "src")]
url = sys.argv[2]
attempts = []

def forbidden(*args, **kwargs):
    attempts.append("network_or_worker")
    raise AssertionError("provider HTTP/network/worker forbidden")

def audit(event, args):
    if ((event.startswith("socket.") and event != "socket.__new__")
            or event == "subprocess.Popen"):
        attempts.append(event)
        frame = sys._getframe(1)
        callers = []
        while frame is not None and len(callers) < 12:
            callers.append(frame.f_code.co_name)
            frame = frame.f_back
        attempts.append(callers)
        forbidden()
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = Path(os.fsdecode(args[0])).resolve()
        # Workspace basetemp may live under outputs. Exempt only this resolved
        # case directory, never sibling production artifacts or escape aliases.
        if (path.name == ".env" or path.name.startswith(".env.")
                or (path.is_relative_to(root / "outputs") and not path.is_relative_to(temporary))):
            attempts.append("private_file")
            raise AssertionError("dotenv/production outputs forbidden")
        if args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            if not path.is_relative_to(temporary):
                attempts.append("external_write")
                raise AssertionError("write outside pytest temporary directory")
    if event == "os.mkdir" and not Path(os.fsdecode(args[0])).resolve().is_relative_to(temporary):
        attempts.append("external_directory")
        raise AssertionError("mkdir outside pytest temporary directory")

if sys.argv[3] == "filesystem":
    sys.addaudithook(audit)
    cache = temporary / "disposable-cache"
    cache.mkdir()
    canary = cache / "canary.txt"
    canary.write_bytes(b"disposable library cache")
    assert canary.read_bytes() == b"disposable library cache"
    assert not attempts, attempts
    # Opens must fail in the audit hook, even for nonexistent paths; do not
    # create or inspect real production artifacts or credential files.
    outputs = root / "outputs"
    sibling_parent = temporary.parent if temporary.is_relative_to(outputs) else outputs
    blocked = [
        outputs / "guard-probe-never-read",
        sibling_parent / (temporary.name + "-sibling") / "guard-probe-never-read",
        temporary / "repository-alias" / "outputs" / "guard-probe-never-read",
        outputs / "uncreated" / ".." / "guard-probe-never-read",
        *(directory / name for directory in (temporary, cache, root, outputs)
          for name in (".env", ".env.local")),
    ]
    for path in blocked:
        try:
            path.read_bytes()
        except AssertionError as error:
            assert str(error) == "dotenv/production outputs forbidden"
        else:
            raise AssertionError("private-file guard did not reject open")
    assert attempts == ["private_file"] * len(blocked), attempts
    print("production probe filesystem boundaries verified", flush=True)
    sys.exit(0)

async def assert_absent(app):
    # ASGITransport does not enter lifespan: no maintenance, run cleanup or
    # worker startup. This still exercises the real middleware/router/HTTP seam.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),
                                 base_url="http://test", trust_env=False) as client:
        reply = await client.post(url, json={"question": "Where?"})
        # The existing GET /api/runs/{run_id}/{artifact} is a partial match,
        # hence 405 (not 404); its handler must never execute for this POST.
        assert reply.status_code == 405, f"production POST status: {reply.status_code}"
        assert reply.json() == {"detail": "Method Not Allowed"}
        assert set(reply.headers["allow"].split(", ")) == {"GET"}
        scope = {"type": "http", "method": "POST", "path": url, "root_path": ""}
        assert not any(route.matches(scope)[0] is Match.FULL for route in app.routes)
        page = await client.get("/")
        assert page.status_code == 200
        assert page.content == (root / "web" / "index.html").read_bytes()
        assert b"/lab-static/" not in page.content
        assert b"saved-source-location" not in page.content
        for path in ("/saved-source-lab/", "/lab-static/app.js", "/lab-static/app.css"):
            reply = await client.get(path)
            assert reply.status_code == 404
            assert reply.json() == {"detail": "Not Found"}
        if sys.argv[5] != "none":
            reply = await client.get("/api/saved-source-receipts")
            assert reply.status_code == 404, f"production receipt GET status: {reply.status_code}"
            assert reply.json() == {"detail": "Not Found"}
            scope = {"type": "http", "method": "GET", "path": "/api/saved-source-receipts", "root_path": ""}
            assert not any(route.matches(scope)[0] is Match.FULL for route in app.routes)
            assert b"receipt-static" not in page.content
            for path in ("/saved-source-receipts/", "/receipt-static/index.html", "/receipt-static/app.js",
                         "/receipt-static/result.js", "/receipt-static/app.css"):
                reply = await client.get(path)
                assert reply.status_code == 404, f"production receipt asset status: {reply.status_code}"
                assert reply.json() == {"detail": "Not Found"}
            assert "api.saved_source_receipt_app" not in sys.modules
            assert "api.saved_source_controller" not in sys.modules
    assert "api.saved_source_app" not in sys.modules
    assert not any(name.startswith("academic_agent.report_evidence_source_locator_qwen") for name in sys.modules)
    assert not attempts, attempts
    print("production ASGI absence verified", flush=True)

async def scenario():
    from api.main import app

    if sys.argv[3] == "inject":
        async def fake_post():
            print("injected POST handler reached", flush=True)
            return {"fake": "registered"}
        app.add_api_route(url.replace(sys.argv[4], "{run_id}"), fake_post, methods=["POST"])
    if sys.argv[5] == "get":
        async def fake_receipt():
            print("injected receipt GET reached", flush=True)
            return {"fake": "receipt"}
        app.add_api_route("/api/saved-source-receipts", fake_receipt, methods=["GET"])
    elif sys.argv[5] == "static":
        from starlette.staticfiles import StaticFiles
        assets = temporary / "receipt-assets"
        assets.mkdir()
        for name in ("index.html", "app.js", "result.js", "app.css"):
            (assets / name).write_text("synthetic receipt asset", encoding="utf-8")
        app.mount("/receipt-static", StaticFiles(directory=assets), name="synthetic-receipt-static")
        print("injected receipt static mounted", flush=True)
    await assert_absent(app)

# Construct only asyncio's own self-pipe before blocking socket activity (the
# Windows socketpair fallback uses loopback). Every production import/request
# is guarded; no process-global guard survives into pytest or its teardown.
with asyncio.Runner() as runner:
    runner.get_loop()
    sys.addaudithook(audit)
    with (patch.object(dotenv, "load_dotenv", return_value=False),
          patch.object(dotenv.main, "load_dotenv", return_value=False),
          patch.object(http.client.HTTPConnection, "request", forbidden),
          patch.object(httpx.HTTPTransport, "handle_request", forbidden),
          patch.object(httpx.AsyncHTTPTransport, "handle_async_request", forbidden),
          # Windows appdirs uses native known-folder APIs, not APPDATA. Keep
          # CrewAI's import-time cache creation inside the pytest tmpdir too.
          patch("appdirs.user_data_dir", return_value=str(temporary / "crewai-data"))):
        # urllib3 probes IPv6 with bind() at import and swallows guard errors.
        # Prime only that dependency without this capability; never allow any
        # socket event. Restore the flag before importing the production app.
        with patch("socket.has_ipv6", False):
            import urllib3.util.connection
        runner.run(scenario())
'''
    # Never copy ambient credentials, proxies, telemetry or Python startup hooks.
    # Libraries that create import-time caches can only use this test's tmpdir.
    environment = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ}
    environment.update({key: str(tmp_path) for key in (
        "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "XDG_CACHE_HOME", "TMP", "TEMP",
    )})
    environment.update({
        "PYTHON_DOTENV_DISABLED": "1", "AGENT_OBSERVABILITY_ENABLED": "false",
        "OTEL_SDK_DISABLED": "true", "CREWAI_TELEMETRY_ENABLED": "false", "DO_NOT_TRACK": "1",
    })
    return subprocess.run(
        [sys.executable, "-I", "-B", "-X", "utf8", "-c", script, str(Path(__file__).resolve().parents[1]), URL,
         "filesystem" if check_filesystem else "inject" if inject_post else "absent", RUN_ID, receipt_probe],
        cwd=tmp_path, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=90, check=False,
    )


def test_production_probe_filesystem_guard_confines_temporary_exception(tmp_path):
    """An outputs basetemp must not block its cache or admit private siblings/dotenv."""
    root = Path(__file__).resolve().parents[1]
    alias = tmp_path / "repository-alias"
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(root), str(alias))
    else:
        alias.symlink_to(root, target_is_directory=True)
    completed = _production_absence_probe(tmp_path, check_filesystem=True)
    assert completed.returncode == 0, completed.stderr
    assert "production probe filesystem boundaries verified" in completed.stdout


def test_production_asgi_has_no_saved_source_route_or_default_page(tmp_path):
    """Source-text absence missed routes registered indirectly in production."""
    completed = _production_absence_probe(tmp_path)
    assert completed.returncode == 0, completed.stderr
    assert "production ASGI absence verified" in completed.stdout


def test_production_absence_predicate_rejects_a_registered_post(tmp_path):
    """The same HTTP predicate must go red when a child-only POST is registered."""
    completed = _production_absence_probe(tmp_path, inject_post=True)
    assert completed.returncode != 0
    assert "injected POST handler reached" in completed.stdout
    assert "AssertionError: production POST status: 200" in completed.stderr
    assert "production ASGI absence verified" not in completed.stdout
