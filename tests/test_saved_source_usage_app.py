"""Native interception -> real controller/store -> strict POST/GET -> shipped DOM."""

from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
import uuid

from fastapi.testclient import TestClient
import httpx
import pytest

from academic_agent.saved_source_accounted_qwen import AccountedQwenSelector
from academic_agent.saved_source_loader import SavedSourceLoader
from academic_agent.saved_source_usage import UsageProjectionV1
from api import saved_source_controller as controller
from api.saved_source_accounting import AccountingStore
from api.saved_source_receipt_app import _HEADERS, _REPLY_FIELDS, create_saved_source_receipt_app
from api.saved_source_usage_app import CONTRACT, GET_PATH, POST_PATH, _wire_usage_reply, create_saved_source_usage_app
from tests.test_saved_source_app import _production_absence_probe
from tests.test_saved_source_controller import CODE, QUESTION, RUN_ID, TEXT, key, select
from tests.test_saved_source_receipt_app import boundary as boundary, count, headers
from tests.test_saved_source_receipt_web import browser_fixtures
from tests.test_saved_source_usage_web import run_usage_node

URL = POST_PATH.replace("{run_id}", RUN_ID)
FAKE_KEY = "sk-isolated-usage-fake-key-only"


@pytest.fixture
def native(boundary, monkeypatch):
    """Intercept only the real native HTTP transport; no success callback stub."""
    _, _, root = boundary
    state = SimpleNamespace(requests=[], usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
                            model="qwen3.5-plus", stores=[])
    real_client = httpx.AsyncClient

    def dispatch(request):
        state.requests.append(request)
        assert request.method == "POST" and request.headers["authorization"] == "Bearer " + FAKE_KEY
        assert TEXT.encode() not in request.content
        assert CODE.encode() not in request.content
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps({
            "model": state.model, "usage": state.usage,
            "choices": [{"index": 0, "message": select(None), "finish_reason": "tool_calls"}],
        }).encode()))

    def transport(**kwargs):
        assert kwargs == {"retries": 0, "verify": True, "trust_env": False}
        return httpx.MockTransport(dispatch)

    def client(**kwargs):
        assert isinstance(kwargs["transport"], httpx.MockTransport)
        assert kwargs["trust_env"] is kwargs["follow_redirects"] is False
        return real_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    monkeypatch.setattr(httpx, "AsyncClient", client)

    def make(*, enabled=True):
        loader = SavedSourceLoader(root)
        store = AccountingStore(root)
        state.stores.append(store)
        selector = AccountedQwenSelector(FAKE_KEY, snapshot=loader(RUN_ID), question=QUESTION,
                                         ledger_dir=root / ("native-" + uuid.uuid4().hex)) if enabled else None
        return create_saved_source_usage_app(load_snapshot=loader, journal_root=root, accounted_selector=selector,
                                             selector_identity="fake-http-usage-v1" if enabled else None,
                                             accounting_store=store)

    state.make = make
    state.root = root
    return state


def test_actual_native_fields_survive_both_http_endpoints_and_shipped_dom(native, monkeypatch):
    """Response-model projection or another receipt's accounting loses this seam."""
    originals = []
    original = controller.SavedSourceController._observe

    def observe(self, *args, **kwargs):
        value = original(self, *args, **kwargs)
        originals.append(deepcopy(value))
        return value

    monkeypatch.setattr(controller.SavedSourceController, "_observe", observe)
    receipt_key = key()
    with TestClient(native.make()) as client:
        first = client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key))
        replay = client.get(GET_PATH, headers=headers(receipt_key))
    for reply, observed in zip((first, replay), originals, strict=True):
        assert reply.status_code == 200, reply.text
        p = reply.json()
        assert set(p) == {"contract", "receipt", "accounting"} and p["contract"] == CONTRACT
        assert p["receipt"] == {**{k: v for k, v in observed.items() if k != "accounting"},
                                "receipt_key_sha256": hashlib.sha256(receipt_key.encode()).hexdigest()}
        assert set(p["receipt"]) == _REPLY_FIELDS | {"receipt_key_sha256"}
        assert p["accounting"] == observed["accounting"]
        assert UsageProjectionV1.model_validate(p["accounting"]).model_dump(mode="json") == p["accounting"]
        assert p["receipt"]["result"]["saved_text"]["text"] == TEXT
        assert p["accounting"]["usage"] == {"status": "reported_complete", **native.usage}
        assert p["accounting"]["cost"]["estimated_usd"] == "0.000126100"
        assert len(reply.content) <= 128 * 1024
        for name, value in _HEADERS.items():
            assert reply.headers[name] == value
        fixtures = browser_fixtures()
        fixtures.update(actual_key=receipt_key, actual_reply=p)
        run_usage_node("actual", fixtures)
    assert replay.json()["receipt"]["delivery_source_reads"] == 1
    assert len(native.requests) == count() == 1


def test_same_question_new_receipts_never_share_accounting_and_recovery_is_read_only(native):
    """Question equality cannot authorize a mutable last-result accounting cache."""
    saved = []
    for tokens in (100, 200):
        native.usage = {"prompt_tokens": tokens, "completion_tokens": 20, "total_tokens": tokens + 20}
        receipt_key = key()
        with TestClient(native.make()) as client:
            reply = client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key))
            assert reply.status_code == 200, reply.text
            saved.append((receipt_key, reply.json()))
    with TestClient(native.make(enabled=False)) as client:
        for receipt_key, expected in reversed(saved):
            replay = client.get(GET_PATH, headers=headers(receipt_key))
            assert replay.status_code == 200
            assert replay.json()["accounting"] == expected["accounting"]
            assert replay.json()["receipt"]["result"] == expected["receipt"]["result"]
    assert saved[0][1]["accounting"]["usage"] != saved[1][1]["accounting"]["usage"]
    assert len(native.requests) == count() == 2


@pytest.mark.parametrize("fault", ["missing", "nan", "object", "extra", "nested_missing", "component_size", "binding", "cost"])
def test_invalid_accounting_degrades_without_hiding_committed_excerpt(native, monkeypatch, fault):
    """Local supplier defects are not malformed HTTP or missing saved-text delivery."""
    original = controller.SavedSourceController._observe

    def observe(self, *args, **kwargs):
        value = original(self, *args, **kwargs)
        if fault == "missing":
            value.pop("accounting")
        elif fault in {"nan", "object"}:
            value["accounting"] = float("nan") if fault == "nan" else object()
        elif fault == "extra":
            value["accounting"]["secret"] = "PRIVATE"
        elif fault == "nested_missing":
            value["accounting"]["cost"].pop("estimated_usd")
        elif fault == "component_size":
            value["accounting"]["extra"] = "x" * 5000
        elif fault == "binding":
            value["accounting"]["receipt_key_sha256"] = "0" * 64
        else:
            value["accounting"]["cost"]["estimated_usd"] = "0.000000000"
        return value

    monkeypatch.setattr(controller.SavedSourceController, "_observe", observe)
    receipt_key = key()
    with TestClient(native.make()) as client:
        first = client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key))
        second = client.get(GET_PATH, headers=headers(receipt_key))
    for reply in (first, second):
        assert reply.status_code == 200, reply.text
        p = reply.json()
        assert p["receipt"]["result"]["saved_text"]["text"] == TEXT
        assert p["accounting"]["usage"]["prompt_tokens"] is None
        assert p["accounting"]["cost"]["estimated_usd"] is None
        assert p["accounting"]["fault_codes"] == ["binding_mismatch" if fault == "binding" else "accounting_unavailable"]
        assert "PRIVATE" not in reply.text
    assert len(native.requests) == count() == 1


def test_missing_corrupt_accounting_store_keeps_receipt_and_never_refunds(native, monkeypatch):
    """Sidecar observation failure must not erase an immutable valid delivery."""
    app = native.make()
    receipt_key = key()
    with TestClient(app) as client:
        first = client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key))
        assert first.status_code == 200
        def broken(_record):
            raise ValueError("PRIVATE storage error")
        monkeypatch.setattr(native.stores[0], "observe", broken)
        replay = client.get(GET_PATH, headers=headers(receipt_key))
        assert replay.status_code == 200
        assert replay.json()["receipt"]["result"] == first.json()["receipt"]["result"]
        assert replay.json()["accounting"]["cost"]["estimated_usd"] is None
        assert "PRIVATE" not in replay.text
    assert len(native.requests) == count() == 1


@pytest.mark.parametrize("fault", ["usage_missing", "model"])
def test_native_usage_fault_remains_visible_and_never_becomes_zero(native, fault):
    """A paid protocol failure can retain unknown spending or known unpriced use."""
    if fault == "usage_missing":
        native.usage = None
    else:
        native.model = "different-authorized-model"
    receipt_key = key()
    with TestClient(native.make()) as client:
        first = client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key))
        second = client.get(GET_PATH, headers=headers(receipt_key))
    assert first.status_code == second.status_code == 200
    for reply in (first, second):
        a = reply.json()["accounting"]
        assert a["cost"]["estimated_usd"] is None
        assert a["cost"]["reservation_usd"] != "0.000000000"
        if fault == "usage_missing":
            assert a["usage"]["prompt_tokens"] is None
        else:
            assert a["usage"]["prompt_tokens"] == 100 and "model_mismatch" in a["fault_codes"]
    assert len(native.requests) == count() == 1


def test_old_contract_default_disabled_and_authorization_unchanged(native):
    """A read-capability URL cannot enable selection, old accounting or code bypass."""
    receipt_key = key()
    with TestClient(native.make(enabled=False)) as client:
        denied = client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key, code="wrong"))
        assert denied.status_code == 401
        assert client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key)).json()["error_code"] == "selector_disabled"
        assert client.get(GET_PATH, headers=headers(receipt_key)).status_code == 404
        assert client.get(GET_PATH, headers=headers(receipt_key, code="wrong")).status_code == 401
        assert client.get("/").status_code == 200
        for path in ("/usage-static/app.js", "/usage-static/accounting.js", "/usage-static/app.css", "/receipt-static/app.js", "/receipt-static/result.js", "/receipt-static/app.css"):
            asset = client.get(path)
            assert asset.status_code == 200 and asset.headers["Cache-Control"] == "no-store"
        assert client.get("/receipt-static/index.html").status_code == 404
    with TestClient(create_saved_source_receipt_app(load_snapshot=SavedSourceLoader(native.root), journal_root=native.root,
                                                   selector=select, selector_identity="scripted-old")) as client:
        reply = client.post(f"/api/runs/{RUN_ID}/saved-source-location", json={"question": QUESTION}, headers=headers(key()))
        assert reply.status_code == 200
        assert set(reply.json()) == _REPLY_FIELDS | {"receipt_key_sha256"}
        assert reply.json()["provider_usage"] == reply.json()["provider_cost"] == "not_observed"
    assert len(native.requests) == 0 and count() == 1


@pytest.mark.parametrize("fault", ["receipt_missing", "extra", "whole_limit"])
def test_receipt_identity_and_whole_response_limits_remain_fail_closed(native, fault):
    """Component fallback cannot accept malformed receipt fields or whole overflow."""
    receipt_key = key()
    with TestClient(native.make()) as client:
        reply = client.post(URL, json={"question": QUESTION}, headers=headers(receipt_key)).json()
    raw = {**reply["receipt"], "accounting": reply["accounting"]}
    raw.pop("receipt_key_sha256")
    if fault == "receipt_missing":
        raw.pop("result")
    elif fault == "extra":
        raw["extra"] = None
    else:
        raw["accounting"] = "x" * (128 * 1024)
    with pytest.raises(ValueError):
        _wire_usage_reply(raw, receipt_key, run_id=RUN_ID)


@pytest.mark.parametrize("probe", ["check", "post", "get", "static"])
def test_production_usage_absence_and_negative_controls(tmp_path, probe):
    """New GET and assets need actual router absence, with defaults still guarded."""
    result = _production_absence_probe(tmp_path, receipt_probe="check", usage_probe=probe)
    if probe == "check":
        assert result.returncode == 0, result.stderr
        assert "production ASGI absence verified" in result.stdout
    else:
        assert result.returncode != 0
        assert "AssertionError: production usage" in result.stderr, result.stderr
        assert "production ASGI absence verified" not in result.stdout
