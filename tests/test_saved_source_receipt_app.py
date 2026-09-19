"""HTTP/real-controller/durable-journal seams, using only synthetic callbacks."""

import asyncio
from contextlib import suppress
from copy import deepcopy
import hashlib
import json
import socket
import sqlite3
import threading
from unittest.mock import Mock

from fastapi.testclient import TestClient
import httpx
import pytest

from academic_agent import report_evidence_source_locator as locator
from academic_agent.saved_source_loader import SavedSourceLoader
from api import access, runs
from api import saved_source_controller as controller
from api import saved_source_receipt_app as api
from api import saved_source_receipts as receipts
from tests.test_saved_source_app import _production_absence_probe
from tests.test_saved_source_controller import CODE, QUESTION, RUN_ID, TEXT, key, saved_registry, select

URL = f"/api/runs/{RUN_ID}/saved-source-location"
LOOKUP = "/api/saved-source-receipts"


def headers(receipt_key, code=CODE, **extra):
    return {"Idempotency-Key": receipt_key, "X-Access-Code": code, **extra}


def count():
    return runs._daily_counts.get(access.owner_id(CODE), 0)


@pytest.fixture
def boundary(tmp_path, monkeypatch):
    """Actual owner marker, journal and paid pool; no mocked authorization."""
    for name in ("_registry", "_stop_claims", "_inline_paid_operations", "_daily_counts"):
        monkeypatch.setattr(runs, name, {})
    monkeypatch.setattr(runs, "_daily_date", None)
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(runs, "MAX_CONCURRENT", 1)
    monkeypatch.setattr(runs, "DAILY_CAP", 50)
    monkeypatch.setattr(access, "ACCESS_CODE", CODE)
    monkeypatch.setattr(access, "ACCESS_CODES", "synthetic-other-code")
    monkeypatch.setattr(access, "ADMIN_CODE", "synthetic-admin-code")
    forbidden = Mock(side_effect=AssertionError("No native provider/network requests"))
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    root = tmp_path / RUN_ID
    root.mkdir()
    (root / ".owner").write_text(access.owner_id(CODE), encoding="utf-8")
    path = root / "validated_sources.json"
    path.write_text(json.dumps(saved_registry(), ensure_ascii=False), encoding="utf-8")

    def make(selector=select, load=None):
        return api.create_saved_source_receipt_app(
            load_snapshot=load or SavedSourceLoader(tmp_path), journal_root=tmp_path,
            selector=selector, selector_identity="synthetic-receipt-http-v1" if selector else None)

    yield make, path, tmp_path
    assert runs.active_paid_operation_count() == 0
    forbidden.assert_not_called()


def assert_error(reply, status, code):
    assert reply.status_code == status
    assert reply.json() == {"detail": "Saved-source receipt request could not be completed.", "error_code": code}
    for name, value in api._HEADERS.items():
        assert reply.headers[name] == value
    assert "set-cookie" not in reply.headers
    assert "access-control-allow-origin" not in reply.headers


async def observed(event):
    assert await asyncio.to_thread(event.wait, 5), "Scripted thread did not reach boundary"


def test_full_controller_and_frozen_result_fields_reach_both_endpoints(boundary, monkeypatch):
    """A success-shaped subset must not replace the original controller reply."""
    make, _, root = boundary
    calls = Mock(side_effect=select)
    originals = []
    original = controller.SavedSourceController._observe
    def observe(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        originals.append(deepcopy(result))
        return result
    monkeypatch.setattr(controller.SavedSourceController, "_observe", observe)
    receipt_key = key()
    app = make(calls)
    for route in app.routes:
        if getattr(route, "path", None) in {LOOKUP, URL.replace(RUN_ID, "{run_id}")}:
            assert route.response_model is None
    with TestClient(app) as client:
        first = client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key))
        second = client.get(LOOKUP, headers=headers(receipt_key))
    expected = json.loads(locator.render_locator_result(locator.locate_saved_source(
        SavedSourceLoader(root)(RUN_ID), QUESTION, selector=select)))
    for response, original in zip((first, second), originals, strict=True):
        assert response.status_code == 200
        assert response.json() == {**original, "receipt_key_sha256": hashlib.sha256(receipt_key.encode()).hexdigest()}
        assert len(response.json()) == 14
        assert response.json()["result"] == expected
        assert response.json()["expires_at"] == int(receipt_key.split(".")[1]) + 86400
        assert len(response.content) <= 128 * 1024
        assert receipt_key not in response.text and CODE not in response.text
    assert first.json()["delivery_source_reads"] == first.json()["delivery_snapshot_reads"] == 0
    assert second.json()["delivery_source_reads"] == second.json()["delivery_snapshot_reads"] == 1
    assert calls.call_args[0][0]["messages"][1]["content"] == QUESTION
    assert calls.call_count == count() == 1


def test_each_actual_header_key_binds_its_own_response(boundary):
    """A constant/stale digest can attach another intent's result to the browser."""
    make, _, _ = boundary
    with TestClient(make()) as client:
        for receipt_key in (key(), key()):
            reply = client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key))
            assert reply.status_code == 200
            assert reply.json()["receipt_key_sha256"] == hashlib.sha256(receipt_key.encode("ascii")).hexdigest()
            recovered = client.get(LOOKUP, headers=headers(receipt_key))
            assert recovered.status_code == 200
            assert recovered.json()["receipt_key_sha256"] == reply.json()["receipt_key_sha256"]
    assert count() == 2


@pytest.mark.parametrize("text,response,state", [
    (None, None, "missing_text"), ("", None, "missing_text"), (" \t\r\n", None, "blank_text"),
    ("\U0001f642" * 1500, None, "excerpt"), ("x" * 1501, None, "out_of_scope"),
    (TEXT, {"role": "assistant", "content": '{"action":"decline"}'}, "declined"),
    (TEXT, {"role": "assistant", "content": None, "refusal": "PRIVATE refusal"}, "declined"),
    (TEXT, {"malformed": "PRIVATE callback"}, "failed"),
])
def test_receipt_completion_does_not_relabel_inner_result(boundary, text, response, state):
    """Domain failure/absence stays complete with its entire original result."""
    make, path, _ = boundary
    path.write_text(json.dumps(saved_registry(text)), encoding="utf-8")
    calls = Mock(side_effect=select if response is None else lambda _: response)
    receipt_key = key()
    with TestClient(make(calls)) as client:
        first = client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key))
        replay = client.get(LOOKUP, headers=headers(receipt_key))
    for reply in (first, replay):
        assert reply.status_code == 200
        data = reply.json()
        assert (data["state"], data["delivery"], data["result"]["state"]) == ("completed", "available", state)
        assert data["provider_cost"] == data["provider_usage"] == "not_observed"
        assert data["result"]["semantic_support"] == "not_assessed"
        if state in {"blank_text", "excerpt"}:
            assert data["result"]["saved_text"]["text"] == text
    assert replay.json()["result"] == first.json()["result"]
    assert calls.call_count == count() == 1


def test_selector_exception_is_complete_unavailable_not_http_failure(boundary):
    make, _, _ = boundary
    with TestClient(make(Mock(side_effect=RuntimeError("PRIVATE callback")))) as client:
        response = client.post(URL, json={"question": QUESTION}, headers=headers(key()))
    assert response.status_code == 200
    assert response.json()["state"] == "completed"
    assert response.json()["result"]["state"] == "unavailable"
    assert "PRIVATE" not in response.text
    assert count() == 1


@pytest.mark.parametrize("body", [
    b"null", b"[]", b"{}", b'{"question":true}', b'{"question":1}', b'{"question":" "}',
    b'{"question":"x","question":"y"}', b'{"question":"x","model":"PRIVATE"}',
    b'{"question":NaN}', b'{"question":Infinity}', b'{"question":"\\ud800"}', b'\xff',
    json.dumps({"question": "x" * 4097}).encode(), b"[" * 1200,
])
def test_invalid_schema_never_enters_controller_or_echoes_content(boundary, body):
    make, _, root = boundary
    calls = Mock(side_effect=select)
    with TestClient(make(calls)) as client:
        reply = client.post(URL, content=body, headers=headers(key(), **{"Content-Type": "application/json"}))
    assert_error(reply, 422, "invalid_request")
    assert not (root / receipts.FILENAME).exists()
    assert calls.call_count == count() == 0


@pytest.mark.parametrize("name", ["Idempotency-Key", "X-Access-Code", "Content-Type", "Content-Length", "Origin", "Host",
                                  "Content-Encoding", "Transfer-Encoding"])
@pytest.mark.parametrize("method", ["POST", "GET"])
def test_duplicate_critical_headers_rejected_before_any_lookup(boundary, name, method):
    make, _, root = boundary
    values = [("Idempotency-Key", key()), ("X-Access-Code", CODE), ("Content-Type", "application/json")]
    values = [(key, value) for key, value in values if key.lower() != name.lower()]
    values += [(name, "PRIVATE"), (name.lower(), "PRIVATE")]
    with TestClient(make()) as client:
        reply = client.request(method, URL if method == "POST" else LOOKUP, headers=values)
    assert_error(reply, 422, "invalid_request")
    assert not (root / receipts.FILENAME).exists()
    assert count() == 0


@pytest.mark.parametrize("media", [None, "text/plain", "application/json; charset=utf-8", "application/problem+json"])
def test_media_is_exact_json(boundary, media):
    make, _, _ = boundary
    values = headers(key())
    if media is not None:
        values["Content-Type"] = media
    with TestClient(make()) as client:
        reply = client.post(URL, content=b'{"question":"PRIVATE"}', headers=values)
    assert_error(reply, 415, "unsupported_media_type")
    assert count() == 0


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_query_and_get_body_not_an_alternate_credential_channel(boundary, method):
    make, _, _ = boundary
    with TestClient(make()) as client:
        reply = client.request(method, (LOOKUP if method == "GET" else URL) + "?key=PRIVATE",
                               headers=headers(key()), json={"question": QUESTION})
        assert_error(reply, 422, "invalid_request")
        reply = client.request("GET", LOOKUP, headers=headers(key()), content=b"PRIVATE")
        assert_error(reply, 422, "invalid_request")
    assert count() == 0


@pytest.mark.parametrize("origin", ["https://evil.invalid", "null", "http://testserver/", "http://u@testserver",
                                    "http://testserver:81", "http://testserver:0", "http://testserver#x", "http://testserver?x"])
def test_origin_must_be_actual_not_forwarded(boundary, origin):
    make, _, _ = boundary
    with TestClient(make()) as client:
        reply = client.post(URL, json={"question": QUESTION}, headers=headers(key(), **{
            "Origin": origin, "X-Forwarded-Host": "evil.invalid", "X-Forwarded-Proto": "https"}))
    assert_error(reply, 403, "origin_denied")
    assert count() == 0


def test_same_origin_and_absent_origin_supported(boundary):
    make, _, _ = boundary
    with TestClient(make()) as client:
        for origin in (None, "http://testserver", "http://testserver:80"):
            value = headers(key(), **({"Origin": origin} if origin else {}))
            reply = client.post(URL, json={"question": QUESTION}, headers=value)
            assert reply.status_code == 200
    assert count() == 3


def test_header_code_and_aggregate_bounds(boundary, monkeypatch):
    """A valid 4096-byte code fits alongside the 78-byte receipt key."""
    make, path, _ = boundary
    long_code = "x" * 4096
    monkeypatch.setattr(access, "ACCESS_CODE", long_code)
    (path.parent / ".owner").write_text(access.owner_id(long_code), encoding="utf-8")
    with TestClient(make()) as client:
        receipt_key = key()
        assert len(receipt_key) == 78
        reply = client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key, long_code))
        assert reply.status_code == 200
        assert_error(client.get(LOOKUP, headers=headers(receipt_key, long_code + "x")), 431, "headers_too_large")
        assert_error(client.get(LOOKUP, headers=headers(receipt_key, long_code, Origin="x" * 8192)),
                     431, "headers_too_large")


@pytest.mark.parametrize("receipt_key,code,status,error", [
    ("PRIVATE", CODE, 400, "invalid_receipt_key"), ("", CODE, 400, "invalid_receipt_key"),
    (None, "", 401, "access_denied"), (None, "PRIVATE wrong code", 401, "access_denied"),
])
def test_required_headers_safe_errors(boundary, receipt_key, code, status, error):
    make, _, _ = boundary
    with TestClient(make()) as client:
        reply = client.get(LOOKUP, headers=headers(key() if receipt_key is None else receipt_key, code))
    assert_error(reply, status, error)
    assert count() == 0


def test_actual_stream_cap_ignores_false_content_length_and_ingress_timeout(boundary, monkeypatch):
    """Bound streamed bytes and a stalled ingress before reserving any intent."""
    make, _, root = boundary
    app = make()
    async def request(chunks):
        scope = {"type": "http", "http_version": "1.1", "method": "POST", "path": URL,
                 "raw_path": URL.encode(), "root_path": "", "query_string": b"", "scheme": "http",
                 "server": ("test", 80), "client": ("127.0.0.1", 1), "headers": [
                     (b"idempotency-key", key().encode()), (b"x-access-code", CODE.encode()),
                     (b"content-type", b"application/json"), (b"content-length", b"1")]}
        messages = []
        async def receive():
            if chunks is None:
                await asyncio.Event().wait()
            return chunks.pop(0)
        async def send(message):
            messages.append(message)
        async with app.router.lifespan_context(app):
            await app(scope, receive, send)
        return messages
    messages = asyncio.run(request([{"type": "http.request", "body": b"x" * (65536 + 1), "more_body": True}]))
    assert messages[0]["status"] == 413
    assert json.loads(messages[1]["body"])["error_code"] == "body_too_large"
    monkeypatch.setattr(api, "BODY_READ_SECONDS", 0.01)
    messages = asyncio.run(request(None))
    assert messages[0]["status"] == 422
    assert not (root / receipts.FILENAME).exists()
    assert count() == 0


def test_current_code_lookup_and_corrupt_owner_fail_closed(boundary, monkeypatch):
    make, path, root = boundary
    calls = Mock(side_effect=select)
    receipt_key = key()
    with TestClient(make(calls)) as client:
        assert client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key)).status_code == 200
        assert_error(client.get(LOOKUP, headers=headers(receipt_key, "synthetic-other-code")), 404, "receipt_not_found")
        assert client.get(LOOKUP, headers=headers(receipt_key, "synthetic-admin-code")).status_code == 200
        monkeypatch.setattr(access, "ACCESS_CODE", None)
        assert_error(client.get(LOOKUP, headers=headers(receipt_key)), 401, "access_denied")
        monkeypatch.setattr(access, "ACCESS_CODE", CODE)
        (path.parent / ".owner").write_bytes(b"\xffPRIVATE")
        assert_error(client.post(URL, json={"question": QUESTION}, headers=headers(key())), 401, "access_denied")
        assert client.get(LOOKUP, headers=headers(receipt_key)).status_code == 200
    assert calls.call_count == count() == 1
    with sqlite3.connect(root / receipts.FILENAME) as db:
        assert db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 1


@pytest.mark.parametrize("damage,delivery,reads", [
    ("delete", "expired", 0), ("changed", "changed", 0), ("invalid_json", "unavailable", 0),
    ("reader", "unavailable", 1), ("digest", "unavailable", 1),
])
def test_failed_replay_read_observations_survive_http(boundary, monkeypatch, damage, delivery, reads):
    """A failed reconstruction still reports the actual read attempt, not zero."""
    make, path, root = boundary
    calls = Mock(side_effect=select)
    receipt_key = key()
    with TestClient(make(calls)) as client:
        assert client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key)).status_code == 200
        if damage == "delete":
            path.unlink()
        elif damage == "changed":
            path.write_text(json.dumps(saved_registry("CHANGED")), encoding="utf-8")
        elif damage == "invalid_json":
            path.write_text("PRIVATE malformed", encoding="utf-8")
        elif damage == "reader":
            monkeypatch.setattr(controller, "read_source", Mock(side_effect=OSError("PRIVATE read failed")))
        else:
            with sqlite3.connect(root / receipts.FILENAME) as db:
                value = json.loads(db.execute("SELECT projection FROM receipts").fetchone()[0])
                value["result_digest"] = "0" * 64
                db.execute("UPDATE receipts SET projection=?", (receipts.canonical(value),))
        read = Mock(wraps=controller.read_source)
        monkeypatch.setattr(controller, "read_source", read)
        reply = client.get(LOOKUP, headers=headers(receipt_key))
    assert reply.status_code == 200
    result = reply.json()
    assert (result["state"], result["delivery"], result["result"]) == ("completed", delivery, None)
    assert result["delivery_snapshot_reads"] == 1
    assert result["delivery_source_reads"] == reads == read.call_count
    assert calls.call_count == count() == 1
    assert "PRIVATE" not in reply.text


@pytest.mark.parametrize("problem", ["missing", "quota", "corrupt_journal", "finalization"])
def test_failed_unknown_and_unavailable_are_distinct_observations(boundary, monkeypatch, problem):
    make, path, root = boundary
    calls = Mock(side_effect=select)
    receipt_key = key()
    if problem == "missing":
        path.unlink()
    elif problem == "quota":
        monkeypatch.setattr(runs, "DAILY_CAP", 1)
        with runs.reserve_inline_paid_operation(owner=access.owner_id(CODE), byok=False):
            pass
    elif problem == "corrupt_journal":
        (root / receipts.FILENAME).write_bytes(b"PRIVATE broken journal")
    else:
        monkeypatch.setattr(receipts.Ticket, "complete", Mock(side_effect=receipts.ReceiptError("receipt_unavailable")))
    with TestClient(make(calls)) as client:
        reply = client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key))
        if problem in {"corrupt_journal", "finalization"}:
            assert_error(reply, 503, "receipt_unavailable")
        else:
            assert reply.status_code == 200
            assert reply.json()["state"] == "failed"
            assert reply.json()["error_code"] == ("saved_source_missing" if problem == "missing" else "daily_quota_exceeded")
    with TestClient(make(selector=None)) as client:
        replay = client.get(LOOKUP, headers=headers(receipt_key))
    if problem == "corrupt_journal":
        assert_error(replay, 503, "receipt_unavailable")
    else:
        assert replay.status_code == 200
        assert replay.json()["state"] == ("unknown" if problem == "finalization" else "failed")
    assert calls.call_count == int(problem == "finalization")
    assert count() == int(problem in {"quota", "finalization"})


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("schema_version", 1.0), ("expires_at", True), ("expires_at", 1),
    ("expires_at", float("inf")), ("delivery_source_reads", True), ("delivery_snapshot_reads", 1.0),
    ("provider_cost", 0), ("provider_usage", None), ("operation", "run"), ("run_id", "a" * 32),
    ("run_id", "20260919T123456Z-" + "f" * 32), ("admission_state", "unknown"),
    ("admission_state", "not_admitted"), ("error_code", "access_denied"), ("state", "pending"),
    ("delivery", "not_ready"), ("delivery", "expired"), ("result", None),
])
def test_malformed_controller_reply_fails_without_projection(boundary, monkeypatch, field, value):
    make, _, _ = boundary
    original = controller.SavedSourceController._observe
    def broken(self, *args, **kwargs):
        return {**original(self, *args, **kwargs), field: value}
    monkeypatch.setattr(controller.SavedSourceController, "_observe", broken)
    with TestClient(make()) as client:
        reply = client.post(URL, json={"question": QUESTION}, headers=headers(key()))
    assert_error(reply, 503, "execution_unavailable")
    assert count() == 1


@pytest.mark.parametrize("damage", ["missing", "extra", "nested_missing", "nested_extra", "nested_bool", "text_hash", "cap"])
def test_no_defaults_no_nested_coercion_and_actual_response_cap(boundary, monkeypatch, damage):
    make, _, _ = boundary
    original = controller.SavedSourceController._observe
    def broken(self, *args, **kwargs):
        reply = original(self, *args, **kwargs)
        if damage == "missing":
            del reply["provider_cost"]
        elif damage == "extra":
            reply["private_extra"] = "PRIVATE"
        elif damage == "nested_missing":
            del reply["result"]["saved_text"]["start"]
        elif damage == "nested_extra":
            reply["result"]["saved_text"]["private_extra"] = "PRIVATE"
        elif damage == "nested_bool":
            reply["result"]["callback_entries"] = True
        elif damage == "text_hash":
            reply["result"]["saved_text"]["text_sha256"] = "0" * 64
        return reply
    monkeypatch.setattr(controller.SavedSourceController, "_observe", broken)
    if damage == "cap":
        monkeypatch.setattr(api, "MAX_RESPONSE_BYTES", 64)
    with TestClient(make()) as client:
        reply = client.post(URL, json={"question": QUESTION}, headers=headers(key()))
    assert_error(reply, 503, "execution_unavailable")
    assert count() == 1


def test_default_off_safe_headers_errors_and_lookup_survives_disable(boundary, tmp_path, monkeypatch):
    make, _, _ = boundary
    receipt_key = key()
    with TestClient(make()) as client:
        first = client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key)).json()
    # Only this test's assets are written; frontend files belong to another owner.
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index.html").write_text("<p>synthetic page</p>", encoding="utf-8")
    (assets / "app.js").write_text("// synthetic asset", encoding="utf-8")
    monkeypatch.setattr(api, "_WEB_ROOT", assets)
    load = Mock(wraps=SavedSourceLoader(tmp_path))
    with TestClient(make(selector=None, load=load)) as client:
        assert_error(client.post(URL, json={"question": QUESTION}, headers=headers(key())), 503, "selector_disabled")
        load.assert_not_called()
        reply = client.get(LOOKUP, headers=headers(receipt_key))
        assert reply.status_code == 200
        assert reply.json()["result"] == first["result"]
        assert_error(client.post(LOOKUP), 405, "method_not_allowed")
        assert_error(client.options(URL), 405, "method_not_allowed")
        assert_error(client.get("/unknown"), 404, "not_found")
        for path in ("/", "/receipt-static/app.js"):
            page = client.get(path)
            assert page.status_code == 200
            for name, value in api._HEADERS.items():
                assert page.headers[name] == value
            assert "set-cookie" not in page.headers
    assert count() == 1


def test_expiry_bound_to_issued_epoch_conflict_and_no_duplicate_charge(boundary, monkeypatch):
    make, _, _ = boundary
    receipt_key = key()
    issued = int(receipt_key.split(".")[1])
    with TestClient(make()) as client:
        reply = client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key))
        assert reply.status_code == 200
        assert reply.json()["expires_at"] == issued + 86400
        assert_error(client.post(URL, json={"question": QUESTION.strip()}, headers=headers(receipt_key)),
                     409, "receipt_conflict")
        assert_error(client.get(LOOKUP, headers=headers(key())), 404, "receipt_not_found")
        with monkeypatch.context() as scoped:
            scoped.setattr(receipts.time, "time", lambda: issued + 86400)
            assert_error(client.get(LOOKUP, headers=headers(receipt_key)), 410, "receipt_expired")
            assert_error(client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key)), 410, "receipt_expired")
    assert count() == 1


@pytest.mark.parametrize("hold", ["pending", "completed_ack"])
def test_durable_lost_ack_recovery_with_fresh_controller_never_redispatches(boundary, hold):
    """Disconnect after admission cannot erase intent, ownership or saved result."""
    make, _, _ = boundary
    entered, release = threading.Event(), threading.Event()
    sent = asyncio.Event()
    calls = Mock(side_effect=select)
    def selector(request):
        if hold == "pending":
            entered.set()
            assert release.wait(8)
        return calls(request)
    first_app, fresh_app = make(selector), make(selector=None)
    receipt_key = key()
    async def held_ack(scope, receive, send):
        async def intercept(message):
            if hold == "completed_ack" and message["type"] == "http.response.start":
                sent.set()
                await asyncio.Event().wait()
            await send(message)
        await first_app(scope, receive, intercept)
    async def scenario():
        async with first_app.router.lifespan_context(first_app), fresh_app.router.lifespan_context(fresh_app):
            async with (httpx.AsyncClient(transport=httpx.ASGITransport(held_ack), base_url="http://test") as first,
                        httpx.AsyncClient(transport=httpx.ASGITransport(first_app), base_url="http://test") as current,
                        httpx.AsyncClient(transport=httpx.ASGITransport(fresh_app), base_url="http://test") as fresh):
                task = asyncio.create_task(first.post(URL, json={"question": QUESTION}, headers=headers(receipt_key)))
                try:
                    if hold == "pending":
                        await observed(entered)
                    else:
                        await asyncio.wait_for(sent.wait(), 5)
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                    # Explicit GET with newly supplied credentials; no original
                    # question/run ID is necessary to locate the durable receipt.
                    recovered = await fresh.get(LOOKUP, headers=headers(receipt_key))
                    assert recovered.status_code == 200
                    if hold == "pending":
                        assert recovered.json()["state"] == "unknown"
                        assert runs.active_paid_operation_count() == 1
                        active = await current.get(LOOKUP, headers=headers(receipt_key))
                        assert active.status_code == 200 and active.json()["state"] == "pending"
                        duplicate = await current.post(URL, json={"question": QUESTION}, headers=headers(receipt_key))
                        assert duplicate.status_code == 200 and duplicate.json()["state"] == "pending"
                        assert_error(await current.post(URL, json={"question": QUESTION}, headers=headers(key())),
                                     429, "locator_busy")
                    else:
                        assert recovered.json()["state"] == "completed"
                        assert recovered.json()["result"]["saved_text"]["text"] == TEXT
                finally:
                    release.set()
                    if not task.done():
                        task.cancel()
                        with suppress(asyncio.CancelledError):
                            await task
        # Lifespan drained the actual thread before a later explicit recovery.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(make(selector=None)), base_url="http://test") as fresh:
            reply = await fresh.get(LOOKUP, headers=headers(receipt_key))
            assert reply.status_code == 200
            assert reply.json()["result"]["saved_text"]["text"] == TEXT
            assert reply.json()["run_id"] == RUN_ID
            assert reply.json()["state"] == "completed"
    asyncio.run(asyncio.wait_for(scenario(), 15))
    assert calls.call_count == count() == 1


def test_lifespan_owns_physical_post_target_exit_and_cancellation_drain(boundary, monkeypatch):
    """Returning HTTP 200 cannot free the actual thread's shared lease."""
    make, _, _ = boundary
    exited, release = threading.Event(), threading.Event()
    original = threading.Thread
    class DelayedExit(original):
        def run(self):
            super().run()
            if self.name == "saved-source-controller":
                exited.set()
                assert release.wait(8)
    monkeypatch.setattr(threading, "Thread", DelayedExit)
    app = make()
    async def scenario():
        lifespan = app.router.lifespan_context(app)
        await lifespan.__aenter__()
        closer = None
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            try:
                response = await client.post(URL, json={"question": QUESTION}, headers=headers(key()))
                assert response.status_code == 200
                await observed(exited)
                assert runs.active_paid_operation_count() == 1
                assert_error(await client.post(URL, json={"question": QUESTION}, headers=headers(key())), 429, "locator_busy")
                with pytest.raises(runs.ConcurrencyLimitReached), runs.reserve_inline_paid_operation(owner=access.owner_id(CODE), byok=False):
                    pytest.fail("Physical thread still owns shared capacity")
                closed = threading.Event()
                original_close = controller.SavedSourceController.close
                async def close(self):
                    closed.set()
                    return await original_close(self)
                monkeypatch.setattr(controller.SavedSourceController, "close", close)
                closer = asyncio.create_task(lifespan.__aexit__(None, None, None))
                await observed(closed)
                assert not closer.done()
                closer.cancel()
                await asyncio.sleep(0)
                assert not closer.done()
            finally:
                release.set()
                if closer is None:
                    await lifespan.__aexit__(None, None, None)
                else:
                    with suppress(asyncio.CancelledError):
                        await closer
            assert runs.active_paid_operation_count() == 0
            assert_error(await client.post(URL, json={"question": QUESTION}, headers=headers(key())), 503, "controller_closed")
    asyncio.run(asyncio.wait_for(scenario(), 15))


def test_production_actual_router_absent_and_negative_control(tmp_path):
    """Reuse the credential-free fresh-process probe, not a source grep claim."""
    absent = tmp_path / "absent"
    negative = tmp_path / "negative"
    absent.mkdir()
    negative.mkdir()
    checked = _production_absence_probe(absent)
    assert checked.returncode == 0, checked.stderr
    assert "production ASGI absence verified" in checked.stdout
    injected = _production_absence_probe(negative, inject_post=True)
    assert injected.returncode != 0
    assert "injected POST handler reached" in injected.stdout
    assert "AssertionError: production POST status: 200" in injected.stderr


@pytest.mark.parametrize("error,status", list(api._ERROR_STATUS.items()) + [("PRIVATE exception", 503)])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_fixed_error_mapping_never_echoes_raw_exception(boundary, monkeypatch, error, status, method):
    """Both controller entrances use the same closed safe error vocabulary."""
    make, _, _ = boundary
    async def fail(*_args):
        raise receipts.ReceiptError(error)
    monkeypatch.setattr(controller.SavedSourceController, "execute" if method == "POST" else "lookup", fail)
    with TestClient(make()) as client:
        reply = client.request(method, URL if method == "POST" else LOOKUP, headers=headers(key()),
                               **({"json": {"question": QUESTION}} if method == "POST" else {}))
    assert_error(reply, status, "receipt_unavailable" if error == "PRIVATE exception" else error)
    assert count() == 0


@pytest.mark.parametrize("run_id", ["a" * 32, "20260919T123456Z-" + "A" * 32,
                                    "20260919T123456Z-" + "a" * 31, "20260919T123456Z-" + "a" * 33])
def test_strict_run_capability_format_before_execution(boundary, run_id):
    make, _, root = boundary
    with TestClient(make()) as client:
        reply = client.post(f"/api/runs/{run_id}/saved-source-location", json={"question": QUESTION}, headers=headers(key()))
    assert_error(reply, 422, "invalid_request")
    assert not (root / receipts.FILENAME).exists()


@pytest.mark.parametrize("empty", [True, False])
def test_no_callback_outcomes_have_no_paid_admission(boundary, empty):
    """Empty catalog and exact 4096-code-point budget refusal are valid results."""
    make, path, _ = boundary
    if empty:
        path.write_text('{"academic_sources":[],"patent_sources":[],"market_sources":[]}', encoding="utf-8")
    calls = Mock(side_effect=AssertionError("Pre-entry result cannot select"))
    with TestClient(make(calls)) as client:
        receipt_key = key()
        reply = client.post(URL, json={"question": QUESTION if empty else "\U0001f642" * 4096}, headers=headers(receipt_key))
        replay = client.get(LOOKUP, headers=headers(receipt_key))
    assert reply.status_code == replay.status_code == 200
    assert reply.json()["result"] == replay.json()["result"]
    assert reply.json()["admission_state"] == "not_admitted"
    assert reply.json()["result"]["reason"] == ("empty_snapshot" if empty else "callback_budget_exceeded")
    assert calls.call_count == count() == 0


def test_code_revocation_during_loader_prevents_http_paid_entry(boundary, monkeypatch):
    """A formerly valid code cannot authorize a callback after slow loading."""
    make, _, root = boundary
    entered, release = threading.Event(), threading.Event()
    calls = Mock(side_effect=select)
    def load(run_id):
        entered.set()
        assert release.wait(5)
        return SavedSourceLoader(root)(run_id)
    app = make(calls, load)
    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                receipt_key = key()
                task = asyncio.create_task(client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key)))
                try:
                    await observed(entered)
                    monkeypatch.setattr(access, "ACCESS_CODE", None)
                finally:
                    release.set()
                reply = await task
                assert reply.status_code == 200
                assert (reply.json()["state"], reply.json()["error_code"], reply.json()["admission_state"]) == (
                    "failed", "access_denied", "not_admitted")
                assert_error(await client.get(LOOKUP, headers=headers(receipt_key)), 401, "access_denied")
    asyncio.run(asyncio.wait_for(scenario(), 10))
    assert calls.call_count == count() == 0


@pytest.mark.parametrize("state,mutation", [
    ("pending", {"error_code": "access_denied"}), ("unknown", {"result": {}}),
    ("failed", {"error_code": None}), ("failed", {"error_code": "unknown"}),
    ("pending", {"delivery": "available"}), ("unknown", {"delivery_snapshot_reads": 1}),
    ("failed", {"delivery_source_reads": True}), ("failed", {"admission_state": "admitted"}),
])
def test_uncompleted_receipt_invariants_fail_closed(boundary, monkeypatch, state, mutation):
    """A malformed pending/failed observation must not become permission to reset."""
    make, _, _ = boundary
    receipt_key = key()
    async def malformed(*_args):
        return {
            "schema_version": 1, "operation": receipts.OPERATION, "state": state,
            "run_id": RUN_ID, "expires_at": int(receipt_key.split(".")[1]) + 86400,
            "admission_state": "not_admitted", "provider_usage": "not_observed", "provider_cost": "not_observed",
            "error_code": "access_denied" if state == "failed" else None,
            "delivery": "not_ready", "delivery_snapshot_reads": 0, "delivery_source_reads": 0, "result": None,
            **mutation,
        }
    monkeypatch.setattr(controller.SavedSourceController, "lookup", malformed)
    with TestClient(make()) as client:
        assert_error(client.get(LOOKUP, headers=headers(receipt_key)), 503, "execution_unavailable")
    assert count() == 0


def test_maximum_valid_metadata_preserved_with_actual_serialized_byte_bound(boundary, monkeypatch):
    """Largest field lengths with 12-byte JSON escapes cannot be silently clipped."""
    make, path, _ = boundary
    value = saved_registry("\U0001f642" * 1500)
    source = value["academic_sources"][0]
    for field, maximum in {"title": 1024, "publisher": 512, "source_type": 64, "url": 4096,
                           "doi": 512, "published_date": 32, "accessed_date": 32}.items():
        source[field] = "\U0001f642" * maximum
    path.write_text(json.dumps(value), encoding="utf-8")
    receipt_key = key()
    calls = Mock(side_effect=select)
    with TestClient(make(calls)) as client:
        reply = client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key))
        assert reply.status_code == 200
        assert 90000 < len(reply.content) < 128 * 1024
        data = reply.json()
        assert data["result"]["saved_text"]["text"] == source["evidence_summary"]
        for field in ("title", "publisher", "source_type", "url", "doi", "published_date", "accessed_date"):
            assert data["result"]["source"][field] == source[field]
        monkeypatch.setattr(api, "MAX_RESPONSE_BYTES", len(reply.content))
        exact = client.get(LOOKUP, headers=headers(receipt_key))
        assert exact.status_code == 200
        assert len(exact.content) == len(reply.content)
        monkeypatch.setattr(api, "MAX_RESPONSE_BYTES", len(reply.content) - 1)
        assert_error(client.get(LOOKUP, headers=headers(receipt_key)), 503, "execution_unavailable")
        monkeypatch.setattr(api, "MAX_RESPONSE_BYTES", 128 * 1024)
        assert client.get(LOOKUP, headers=headers(receipt_key)).json()["result"] == data["result"]
    assert count() == calls.call_count == 1


@pytest.mark.parametrize("mode", ["check", "get", "static"])
def test_new_receipt_routes_and_assets_have_actual_production_negative_controls(tmp_path, mode):
    """GET and static mounts must each falsify the guarded production predicate."""
    result = _production_absence_probe(tmp_path, receipt_probe=mode)
    if mode == "check":
        assert result.returncode == 0, result.stderr
        assert "production ASGI absence verified" in result.stdout
    else:
        assert result.returncode != 0
        if mode == "get":
            assert "injected receipt GET reached" in result.stdout
            assert "AssertionError: production receipt GET status: 200" in result.stderr
        else:
            assert "injected receipt static mounted" in result.stdout
            assert "AssertionError: production receipt asset status: 200" in result.stderr
        assert "production ASGI absence verified" not in result.stdout
