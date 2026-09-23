"""Default-OFF production successor through real admission, stores and HTTP wire."""

import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import replace
from decimal import Decimal
import json
import sqlite3
import threading
import time
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api import main, runs
from api import saved_source_accounting as accounting
from api import saved_source_production as production
from api import saved_source_production_policy as policy
from api.maintenance import MaintenanceDeferred
from api.saved_source_receipts import ReceiptError
from tests.test_saved_source_controller import CODE, QUESTION, RUN_ID, TEXT, key
from tests.test_saved_source_receipt_app import boundary as boundary, count, headers
from tests.test_saved_source_usage_app import FAKE_KEY, native as native

URL = production.POST_PATH.replace("{run_id}", RUN_ID)
SETTINGS = production.Settings(True, True, 2, Decimal("0.03"), Decimal("1"))


def consent(receipt_key=None, code=CODE):
    return headers(receipt_key or key(), code, **{"X-Source-Locator-Consent": "question-catalog-v1"})


def app_for(runtime):
    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            if runtime is not None:
                await runtime.close()
    app = FastAPI(lifespan=lifespan)
    production.register_routes(app, runtime)
    return app


@pytest.fixture
def prepared(native, monkeypatch):
    """Use the existing actual-native HTTP interception and synthetic owner files."""
    native.key_reads = []
    native.clock = time.time_ns()
    monkeypatch.setattr(policy.time, "time_ns", lambda: native.clock)

    def key_loader():
        native.key_reads.append(threading.get_ident())
        return FAKE_KEY

    def build(settings=SETTINGS, **kwargs):
        return production.build_runtime(settings=settings, output_root=native.root,
                                        key_loader=kwargs.pop("key_loader", key_loader), **kwargs)
    native.build = build
    return native


def test_default_configuration_has_no_routes_storage_or_key_lookup(tmp_path, monkeypatch):
    """Import/construction/disabled maintenance must not initialize locator state."""
    for name in ("ENABLED", "EXECUTION_ENABLED", "DAILY_REQUEST_CAP", "DAILY_USD_CAP", "MIN_INTERVAL_SECONDS"):
        monkeypatch.delenv("SOURCE_LOCATOR_" + name, raising=False)
    forbidden = Mock(side_effect=AssertionError("Disabled locator touched a key or source"))
    runtime = production.build_runtime(output_root=tmp_path, key_loader=forbidden, load_snapshot=forbidden)
    assert runtime is None
    with TestClient(app_for(runtime)) as client:
        for path in (production.PAGE_PATH, production.GET_PATH, "/source-locator-static/receipt.js"):
            assert client.get(path).status_code == 404
        assert client.post(URL, json={"question": QUESTION}, headers=consent()).status_code == 404
    forbidden.assert_not_called()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("value,enabled", [("true", True), ("1", True), ("false", False), ("TRUE", False), ("yes", False)])
def test_exact_env_flags_and_explicit_budget_requirement(monkeypatch, value, enabled):
    """No permissive boolean parse or zero-as-unlimited can activate this feature."""
    monkeypatch.setenv("SOURCE_LOCATOR_ENABLED", value)
    monkeypatch.setenv("SOURCE_LOCATOR_EXECUTION_ENABLED", "true")
    for suffix in ("DAILY_REQUEST_CAP", "DAILY_USD_CAP", "MIN_INTERVAL_SECONDS"):
        monkeypatch.setenv("SOURCE_LOCATOR_" + suffix, "0")
    configured = production.Settings.from_env()
    assert configured.enabled is enabled and not configured.execution_allowed
    monkeypatch.setenv("SOURCE_LOCATOR_DAILY_REQUEST_CAP", "2")
    monkeypatch.setenv("SOURCE_LOCATOR_DAILY_USD_CAP", "0.03")
    monkeypatch.setenv("SOURCE_LOCATOR_MIN_INTERVAL_SECONDS", "1")
    assert production.Settings.from_env().execution_allowed is enabled


@pytest.mark.parametrize("field,value", [
    ("daily_request_cap", 0), ("daily_usd_cap", Decimal("0")), ("daily_usd_cap", Decimal("NaN")),
    ("daily_usd_cap", Decimal("0.001")), ("min_interval_seconds", Decimal("0")),
    ("min_interval_seconds", Decimal("Infinity")), ("execution_enabled", False),
])
def test_zero_or_invalid_budget_keeps_get_but_creates_no_store(prepared, field, value):
    """Exposure is not execution and cannot turn a missing budget into unlimited use."""
    runtime = prepared.build(replace(SETTINGS, **{field: value}))
    with TestClient(app_for(runtime)) as client:
        reply = client.post(URL, json={"question": QUESTION}, headers=consent())
        assert reply.status_code == 503 and reply.json()["error_code"] == "selector_disabled"
        assert client.get(production.GET_PATH, headers=headers(key())).status_code == 404
    assert not runtime.root.exists()
    assert prepared.key_reads == prepared.requests == [] and count() == 0


@pytest.mark.parametrize("mode,expected", [("missing", 403), ("wrong", 403), ("duplicate", 422), ("oversize", 431)])
def test_consent_is_bounded_and_rejected_before_claim(prepared, mode, expected):
    """Consent outside the legacy critical-header cap could bypass ingress bounds."""
    runtime = prepared.build()
    supplied = list(consent().items())
    if mode == "missing":
        supplied = supplied[:-1]
    elif mode == "wrong":
        supplied[-1] = ("X-Source-Locator-Consent", "true")
    elif mode == "duplicate":
        supplied.append(("x-source-locator-consent", "question-catalog-v1"))
    else:
        supplied[-1] = ("X-Source-Locator-Consent", "x" * 8192)
    with TestClient(app_for(runtime)) as client:
        assert client.post(URL, json={"question": QUESTION}, headers=supplied).status_code == expected
    assert not runtime.root.exists()
    assert prepared.key_reads == prepared.requests == [] and count() == 0


@pytest.mark.parametrize("code", ["wrong-code", "synthetic-other-code", "synthetic-admin-code"])
def test_even_admin_cannot_execute_another_owners_report(prepared, code):
    """Receipt observation authority must never choose a different payer."""
    runtime = prepared.build()
    with TestClient(app_for(runtime)) as client:
        assert client.post(URL, json={"question": QUESTION}, headers=consent(code=code)).status_code == 401
    assert not runtime.root.exists()
    assert prepared.key_reads == prepared.requests == [] and count() == 0


def test_native_factory_binds_real_request_and_recovery_never_reads_key(prepared):
    """POST -> durable native usage -> GET must preserve the full old envelope."""
    runtime = prepared.build()
    receipt_key = key()
    with TestClient(app_for(runtime)) as client:
        first = client.post(URL, json={"question": QUESTION}, headers=consent(receipt_key))
        assert first.status_code == 200, first.text
        delivered = first.json()
        assert delivered["receipt"]["result"]["saved_text"]["text"] == TEXT
        assert delivered["accounting"]["usage"]["status"] == "reported_complete"
        assert delivered["accounting"]["cost"]["estimated_usd"] == "0.000126100"
        again = client.post(URL, json={"question": QUESTION}, headers=consent(receipt_key))
        assert again.json()["accounting"] == delivered["accounting"]
        runtime.stop_accepting()
        assert client.post(URL, json={"question": QUESTION}, headers=consent()).status_code == 503
        replay = client.get(production.GET_PATH, headers=headers(receipt_key))
        assert replay.json()["receipt"]["result"] == delivered["receipt"]["result"]
        assert replay.json()["accounting"] == delivered["accounting"]
    assert len(prepared.requests) == len(prepared.key_reads) == count() == 1
    assert prepared.key_reads[0] != threading.get_ident()
    wire = prepared.requests[0]
    assert str(wire.url) == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert json.loads(wire.content)["model"] == "qwen3.5-plus"
    assert TEXT.encode() not in wire.content and CODE.encode() not in wire.content
    assert production._CURRENT.get() is None
    readonly = prepared.build(replace(SETTINGS, execution_enabled=False))
    with TestClient(app_for(readonly)) as client:
        assert client.get(production.GET_PATH, headers=headers(receipt_key)).json()["accounting"] == delivered["accounting"]
    assert len(prepared.key_reads) == 1


@pytest.mark.parametrize("limit", ["requests", "usd", "interval"])
def test_persistent_caps_survive_new_runtime_and_new_receipt(prepared, limit):
    """A restart or a fresh native ledger cannot reset a consumed aggregate limit."""
    settings = replace(SETTINGS, daily_request_cap=1) if limit == "requests" else SETTINGS
    if limit == "usd":
        settings = replace(SETTINGS, daily_usd_cap=Decimal("0.02"))
    for attempt in range(2):
        runtime = prepared.build(settings)
        with TestClient(app_for(runtime)) as client:
            reply = client.post(URL, json={"question": QUESTION}, headers=consent())
            assert reply.status_code == 200, reply.text
            if attempt == 0:
                assert reply.json()["receipt"]["result"]["state"] == "excerpt"
            else:
                assert reply.json()["receipt"]["result"]["state"] == "unavailable"
                assert reply.json()["receipt"]["result"]["reason"] == "selector_error"
        if limit != "interval":
            prepared.clock += 2_000_000_000
    assert len(prepared.requests) == len(prepared.key_reads) == 1


def test_new_request_uses_current_question_not_cached_factory(prepared):
    """Two intents must not share an already bound native transport or usage slot."""
    runtime = prepared.build()
    with TestClient(app_for(runtime)) as client:
        for question in (QUESTION, QUESTION + " Another exact question."):
            reply = client.post(URL, json={"question": question}, headers=consent())
            assert reply.json()["receipt"]["result"]["state"] == "excerpt"
            prepared.clock += 2_000_000_000
    assert len(prepared.requests) == len(prepared.key_reads) == 2
    assert prepared.requests[0].content != prepared.requests[1].content


def test_corrupt_budget_history_cannot_reset_admission(prepared):
    """Schema damage must refuse key lookup, never recreate an empty allowance."""
    runtime = prepared.build()
    with TestClient(app_for(runtime)) as client:
        assert client.post(URL, json={"question": QUESTION}, headers=consent()).status_code == 200
    path = runtime.root / policy.FILENAME
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=99")
    prepared.clock += 2_000_000_000
    with TestClient(app_for(prepared.build())) as client:
        assert client.post(URL, json={"question": QUESTION}, headers=consent()).status_code == 503
    assert len(prepared.requests) == len(prepared.key_reads) == 1


def test_bound_factory_rejects_changed_callback_before_key(prepared, monkeypatch):
    """Full request comparison cannot be replaced by trusting catalog IDs alone."""
    runtime = prepared.build()
    original = runtime.select

    def changed(request, *, operation, observation):
        request["messages"][-1]["content"] += " changed"
        return original(request, operation=operation, observation=observation)
    monkeypatch.setattr(runtime, "select", changed)
    with TestClient(app_for(runtime)) as client:
        reply = client.post(URL, json={"question": QUESTION}, headers=consent())
        assert reply.json()["receipt"]["result"]["state"] == "unavailable"
        assert reply.json()["receipt"]["result"]["reason"] == "selector_error"
    assert prepared.requests == prepared.key_reads == []


def test_key_discovery_observes_committed_budget_and_precedes_native_files(prepared):
    """Key discovery must follow durable budget admission, not an in-memory reservation."""
    observations = []

    def checked_key():
        root = prepared.root / ".source-locator-v1"
        with sqlite3.connect(root / policy.FILENAME) as db:
            rows = db.execute("SELECT key_hash, reservation FROM operations").fetchall()
        assert len(rows) == 1 and rows[0][1] == policy.RESERVATION_NANODOLLARS
        assert not (root / "native" / rows[0][0]).exists()
        observations.append(rows[0])
        return FAKE_KEY

    runtime = prepared.build(key_loader=checked_key)
    with TestClient(app_for(runtime)) as client:
        response = client.post(URL, json={"question": QUESTION}, headers=consent())
        assert response.json()["receipt"]["result"]["state"] == "excerpt"
    assert len(observations) == len(prepared.requests) == count() == 1


@pytest.mark.parametrize("identity", ["ownerless", "revoked", "invalid_utf8"])
def test_production_identity_failures_never_initialize_budget_or_discover_key(prepared, monkeypatch, identity):
    """Production's outer prepare must not run before the inherited owner/code gate."""
    from api import access

    owner = prepared.root / RUN_ID / ".owner"
    if identity == "ownerless":
        owner.unlink()
    elif identity == "invalid_utf8":
        owner.write_bytes(b"\xff")
    else:
        monkeypatch.setattr(access, "ACCESS_CODE", None)
        monkeypatch.setattr(access, "ACCESS_CODES", None)
        monkeypatch.setattr(access, "ADMIN_CODE", None)
    runtime = prepared.build()
    with TestClient(app_for(runtime)) as client:
        response = client.post(URL, json={"question": QUESTION}, headers=consent())
        assert response.status_code == 401
    assert not runtime.root.exists()
    assert prepared.key_reads == prepared.requests == [] and count() == 0


@pytest.mark.parametrize("method", ["POST", "GET"])
def test_real_main_nonascii_code_reaches_safe_denial_without_paid_activity(prepared, monkeypatch, method):
    """Main's rate-limit HMAC ran before critical-header rejection and raised on Latin-1 codes."""
    runtime = prepared.build()
    monkeypatch.setattr(main, "_source_locator", runtime)
    monkeypatch.setattr(main.app.router, "routes", list(main.app.routes))
    production.register_routes(main.app, runtime)
    monkeypatch.setattr(runs, "shutdown_all", Mock())
    supplied = [(b"x-access-code", b"\xff"), (b"idempotency-key", key().encode()),
                (b"x-source-locator-consent", b"question-catalog-v1")]
    with TestClient(main.app, raise_server_exceptions=False) as client:
        reply = (client.post(URL, json={"question": QUESTION}, headers=supplied) if method == "POST"
                 else client.get(production.GET_PATH, headers=supplied))
        assert reply.status_code == 401, reply.text
        assert reply.json()["error_code"] == "access_denied"
        assert set(main._rate_buckets) == {"ip:testclient"}
    assert not runtime.root.exists()
    assert prepared.key_reads == prepared.requests == [] and count() == 0


def test_shutdown_drains_actual_native_owner_after_waiter_cancellation(prepared):
    """Cancelling an HTTP-equivalent waiter cannot free the slot or skip close."""
    entered, release = threading.Event(), threading.Event()

    def held_key():
        entered.set()
        assert release.wait(10)
        return FAKE_KEY
    runtime = prepared.build(key_loader=held_key)

    async def scenario():
        request = asyncio.create_task(runtime.controller.execute(key(), RUN_ID, QUESTION, CODE))
        close = None
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            request.cancel()
            with suppress(asyncio.CancelledError):
                await request
            assert runs.active_paid_operation_count() == 1
            close = asyncio.create_task(runtime.close())
            await asyncio.sleep(0)
            assert not close.done()
            with pytest.raises(MaintenanceDeferred):
                runtime.prune_native()
        finally:
            release.set()
            if close is not None:
                await close
            else:
                await runtime.close()
    asyncio.run(scenario())
    assert runs.active_paid_operation_count() == 0
    assert len(prepared.requests) == 1


def test_accounting_and_native_expiry_are_independent_stages(prepared, monkeypatch):
    """Expired private native bytes need their own inventoried cleanup, not GET."""
    runtime = prepared.build()
    with TestClient(app_for(runtime)) as client:
        reply = client.post(URL, json={"question": QUESTION}, headers=consent()).json()
    expires = reply["receipt"]["expires_at"]
    assert len(list((runtime.root / "native").iterdir())) == 1
    prepared.clock = (expires + 1) * 1_000_000_000
    monkeypatch.setattr(production.time, "time", lambda: expires + 1)
    assert runtime.prune_accounting() == 1
    assert runtime.prune_native() == 1
    assert runtime.prune_receipts() == 1
    assert list((runtime.root / "native").iterdir()) == []


def test_accounting_corruption_is_not_erased_by_pruning(prepared):
    """Cleanup must validate the full sidecar before deleting even expired rows."""
    runtime = prepared.build()
    with TestClient(app_for(runtime)) as client:
        client.post(URL, json={"question": QUESTION}, headers=consent())
    with sqlite3.connect(runtime.root / accounting.FILENAME) as db:
        db.execute("UPDATE accounting SET value='{}'")
    with pytest.raises(ReceiptError):
        runtime.prune_accounting()
    with sqlite3.connect(runtime.root / accounting.FILENAME) as db:
        assert db.execute("SELECT COUNT(*) FROM accounting").fetchone()[0] == 1


def test_main_owns_advisory_stages_and_failed_supervisor_still_drains(prepared, monkeypatch):
    """A subapp mount would omit close; a dead reaper cannot bypass either owner."""
    runtime = prepared.build()
    monkeypatch.setattr(main, "_source_locator", runtime)
    shutdown = Mock()
    monkeypatch.setattr(runs, "shutdown_all", shutdown)

    async def broken():
        raise RuntimeError("synthetic supervisor failure")
    monkeypatch.setattr(main, "_reaper", broken)

    async def scenario():
        async with main._lifespan(main.app):
            assert set(name for name, _ in runtime.maintenance_stages()) <= main._maintenance_checks.keys()
            await asyncio.sleep(0)
        assert runtime.controller._closed
        shutdown.assert_called_once_with()
    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["absent", "disabled", "enabled", "stopped"])
@pytest.mark.parametrize("endpoint", ["/health", "/health/ready"])
def test_main_health_keeps_configuration_outside_maintenance_checks(prepared, monkeypatch, mode, endpoint):
    """Enabled/disabled configuration strings caused both real health endpoints to fail validation."""
    from api.models import ReadinessStatus

    runtime = None if mode == "absent" else prepared.build(
        replace(SETTINGS, execution_enabled=mode != "disabled"))
    if mode == "stopped":
        runtime.stop_accepting()
    monkeypatch.setattr(main, "_source_locator", runtime)
    monkeypatch.setattr(main, "readiness", lambda: ReadinessStatus(ready=True, checks={"synthetic": "ok"}))
    monkeypatch.setattr(runs, "shutdown_all", Mock())
    with TestClient(main.app, raise_server_exceptions=False) as client:
        reply = client.get(endpoint)
        assert reply.status_code == 200, reply.text
        payload = reply.json()
        assert set(payload["maintenance"]["checks"].values()) == {"not_checked"}
        assert set(payload["maintenance"]["checks"]) == set(payload["maintenance"]["timings"])
        assert payload["maintenance"]["state"] == "running"
        assert payload["source_locator"] == (None if runtime is None else {
            "execution": "enabled" if mode == "enabled" else "disabled",
            "budget": "disabled" if mode == "disabled" else "configured",
            "deferred_maintenance": {},
        })
    assert prepared.key_reads == prepared.requests == [] and count() == 0
    assert not (prepared.root / ".source-locator-v1").exists()


@pytest.mark.parametrize("previous", ["not_checked", "failed", "ok"])
def test_deferred_maintenance_retains_prior_completion_and_reports_no_scan(prepared, monkeypatch, previous):
    """An active owner formerly minted a new ok and erased a failed cleanup without scanning."""
    from api.models import ReadinessStatus
    from tests.test_maintenance_timing import Clock

    runtime = prepared.build()
    clock = Clock()
    name = "source_locator_native"
    monkeypatch.setattr(main, "_source_locator", runtime)
    monkeypatch.setattr(main, "_maintenance_clock", clock)
    monkeypatch.setattr(main, "_maintenance_checks", {"timeouts": "ok", name: "not_checked"})
    monkeypatch.setattr(main, "_maintenance_timings", {})
    monkeypatch.setattr(main, "_maintenance_task", Mock(done=lambda: False))
    monkeypatch.setattr(main, "readiness", lambda: ReadinessStatus(ready=True, checks={}))
    if previous != "not_checked":
        def old_check():
            clock.advance(2)
            if previous == "failed":
                raise ReceiptError("execution_unavailable")
        asyncio.run(main._maintenance_stage(name, old_check))
    before = main._maintenance_status().model_dump(mode="json")["timings"][name]
    monkeypatch.setattr(runtime.controller, "_threads", {"synthetic-live": Mock(is_alive=lambda: True)})
    clock.advance(45)
    asyncio.run(main._maintenance_stage(name, runtime.prune_native))
    for endpoint in ("/health", "/health/ready"):
        response = TestClient(main.app).get(endpoint)
        assert response.status_code == 200
        body = response.json()
        assert body["maintenance"]["checks"][name] == previous
        timing = body["maintenance"]["timings"][name]
        assert timing["last_finished_at"] == before["last_finished_at"]
        assert timing["last_duration_seconds"] == before["last_duration_seconds"]
        assert timing["last_finished_age_seconds"] == (None if previous == "not_checked" else 45)
        assert timing["current_started_at"] is timing["current_elapsed_seconds"] is None
        assert body["source_locator"]["deferred_maintenance"] == {
            name: {"reason": "active_operation", "observed_at": clock.wall.isoformat().replace("+00:00", "Z")},
        }
    runtime.controller._threads.clear()
    clock.advance(5)
    asyncio.run(main._maintenance_stage(name, runtime.prune_native))
    after = TestClient(main.app).get("/health").json()
    assert after["maintenance"]["checks"][name] == "ok"
    assert after["source_locator"]["deferred_maintenance"] == {}
    assert not runtime.root.exists()
    assert prepared.key_reads == prepared.requests == []
