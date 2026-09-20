"""Real ASGI/controller/receipt/native primitive; all provider HTTP is intercepted.

These are not browser facts or live results. Browser completion is tested by the
separately opt-in actual Chromium journey, never fabricated in this ASGI helper.
"""

from copy import deepcopy
import json
import os
import subprocess
import sys
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from academic_agent import saved_source_receipt_qwen_canary as runner
from academic_agent.report_evidence_qwen_canary import CanaryStopped, ENDPOINT
from academic_agent.saved_source_receipt_qwen_adapter import BatchGate, BoundCaseSelector
from e2e.saved_source_receipt_qwen_canary import FAKE_KEY


@pytest.fixture
def http_boundary(tmp_path, monkeypatch):
    cases = runner.load_cases()
    bindings = runner.bindings_for(cases)
    batch = BatchGate(tmp_path / "batch", runner.batch_manifest(bindings, {"offline": True}))
    state = SimpleNamespace(cases=cases, bindings=bindings, batch=batch, requests=[], change=None,
                            identities=0, identity_failure=None, ledgers=[], transport_options=[], client_options=[])

    def identity():
        state.identities += 1
        if state.identities == state.identity_failure:
            raise CanaryStopped("runtime_identity_changed")

    state.identity = identity

    def dispatch(request):
        body = json.loads(request.content)
        case = next(case for case in cases if case["question"] == body["messages"][1]["content"])
        assert request.url == ENDPOINT and request.method == "POST"
        assert request.headers["authorization"] == "Bearer " + FAKE_KEY
        assert request.headers["accept-encoding"] == "identity"
        journal = batch.output_dir / case["case_id"] / "events.jsonl"
        reserved = json.loads(journal.read_text(encoding="utf-8"))
        assert reserved["event"] == "request_reserved"
        assert reserved["request_sha256"] == runner.digest(request.content)
        events = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(batch.output_dir.glob("event-*.json"))]
        assert any(event["event"] == "runner_pre_post_intent" for event in events)
        assert any(event["event"] == "aggregate_reserved" for event in events)
        state.requests.append(request)
        source_id = case["reference"]["source_id"]
        message = {"role": "assistant", "content": '{"action":"decline"}'}
        if source_id:
            message = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "offline-call", "type": "function", "function": {
                    "name": "read_source", "arguments": json.dumps({"source_id": source_id})}}]}
        reply = {"model": "qwen3.5-plus", "usage": {
            "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "tool_calls" if source_id else "stop"}]}
        if state.change:
            state.change(reply)
        return httpx.Response(200, stream=httpx.ByteStream(runner._encoded(reply)))

    real_client = httpx.AsyncClient

    def transport(**kwargs):
        state.transport_options.append(kwargs)
        return httpx.MockTransport(dispatch)

    def client(**kwargs):
        state.client_options.append(kwargs)
        return real_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    return state


def execute(state, *, change_get=None):
    from api.saved_source_receipt_app import create_saved_source_receipt_app

    case, binding = state.cases[0], state.bindings[0]
    ledger = runner.native.LocatorQwenLedger(state.batch.output_dir / case["case_id"])
    state.ledgers.append(ledger)
    selector = BoundCaseSelector(FAKE_KEY, binding, state.batch, ledger, check_identity=state.identity)
    with runner.isolated_runtime(state.batch.output_dir / "synthetic", state.cases) as (loader, owner, runs):
        execution = runner.CaseExecution(binding, selector, loader)
        key = "v1." + str(int(time.time())) + "." + "c" * 64
        state.batch.bind_http_intent(case["case_id"], runner.digest(key.encode()), owner)
        app = create_saved_source_receipt_app(load_snapshot=execution.load,
            journal_root=state.batch.output_dir / "synthetic", selector=execution.callback,
            selector_identity=binding.selector_identity)
        headers = {"X-Access-Code": runner.CODE, "Idempotency-Key": key}
        with execution.observe_reads(), TestClient(app) as client:
            post = client.post(f"/api/runs/{binding.run_id}/saved-source-location",
                               json={"question": binding.question}, headers=headers)
            before = deepcopy(state.batch.summary())
            replay = client.get("/api/saved-source-receipts", headers=headers)
            assert state.batch.summary() == before
            assert runs._daily_counts.get(owner, 0) == 1
            if change_get:
                replay = change_get(replay)
        execution.drain()
        assert runs.active_paid_operation_count() == 0
        return post, replay, execution, key


def test_real_http_native_single_read_and_receipt_get_no_second_call(http_boundary):
    """A real controller receipt must reconstruct exact code points with no callback replay."""
    state = http_boundary
    post, replay, execution, key = execute(state)
    checked = runner.audit_http(state.cases[0], execution, post.content, replay.content, key)
    assert checked["mechanical_passed"] and checked["reference_passed"]
    assert len(state.requests) == len(state.ledgers[0].records) == 1
    assert state.identities == 2
    assert len(execution.callbacks) == len(execution.local_reads) == len(execution.delivery_reads) == 1
    assert post.json()["result"] == replay.json()["result"]
    assert len(post.json()) == len(replay.json()) == 14
    assert replay.json()["provider_usage"] == replay.json()["provider_cost"] == "not_observed"
    assert state.transport_options == [{"retries": 0, "verify": True, "trust_env": False}]
    options = state.client_options[0]
    assert options["follow_redirects"] is options["trust_env"] is False
    assert options["verify"] is True and options["timeout"].connect == 10 and options["timeout"].read == 60
    raw = state.requests[0].content.decode("ascii")
    for source in state.cases[0]["sources"]:
        assert json.dumps(source["summary"], ensure_ascii=True)[1:-1] not in raw
    assert key not in raw and runner.CODE not in raw
    assert state.batch.summary()["case_gates"] == {"RQ01": False, "RQ02": False}
    # HTTP success cannot counterfeit actual browser/drain completion for RQ02.
    with pytest.raises(CanaryStopped, match="case_order"):
        state.batch.bind_http_intent("RQ02", "a" * 64, "b" * 16)


@pytest.mark.parametrize("when,requests", [(1, 0), (2, 1)])
def test_identity_drift_before_and_after_actual_native_preserves_usage(http_boundary, when, requests):
    """Pre-dispatch drift blocks HTTP; post-dispatch drift cannot erase observed accounting."""
    state = http_boundary
    state.identity_failure = when
    post, _, execution, _ = execute(state)
    assert len(state.requests) == requests and not execution.local_reads
    assert post.json()["result"]["reason"] == "selector_error"
    assert state.batch.stop_reason == "source_identity_mismatch"
    if requests:
        assert state.ledgers[0].records[0]["usage_status"] == "complete"
        assert state.batch.summary()["known_usage_estimated_usd"] != "0"
    with pytest.raises(CanaryStopped):
        state.batch.bind_http_intent("RQ02", "a" * 64, "b" * 16)


def test_unknown_usage_not_free_and_next_case_cannot_start(http_boundary):
    """A received response without usage consumes reservation and stops the whole batch."""
    state = http_boundary
    state.change = lambda reply: reply.pop("usage")
    _, _, execution, _ = execute(state)
    assert len(state.requests) == 1 and not execution.local_reads
    assert state.batch.summary()["unknown_usage_requests"] == 1
    assert state.batch.summary()["budget_consumed_usd"] == "0.011149312"
    with pytest.raises(CanaryStopped):
        state.batch.bind_http_intent("RQ02", "a" * 64, "b" * 16)


def test_visible_wrong_selection_is_reference_failure_not_mechanical(http_boundary):
    """A legal A11 read is delivered correctly but cannot match the frozen A12 reference."""
    state = http_boundary

    def wrong(reply):
        reply["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = '{"source_id":"A11"}'

    state.change = wrong
    post, replay, execution, key = execute(state)
    checked = runner.audit_http(state.cases[0], execution, post.content, replay.content, key)
    assert checked["mechanical_passed"] is True and checked["reference_passed"] is False
    assert checked["result"]["source"]["source_id"] == "A11"


def test_native_durable_pair_matches_real_wire_then_rejects_missing_finish(http_boundary):
    """Deleting a finish event cannot hide behind a still-complete in-memory ledger."""
    state = http_boundary
    execute(state)
    ledger = state.ledgers[0]
    checked = runner.audit_native_journal(state.bindings[0], ledger)
    assert checked["durable_reservations"] == checked["durable_finishes"] == 1
    assert checked["wire_sha256"] == runner.digest(state.requests[0].content)
    path = ledger.output_dir / "events.jsonl"
    first = path.read_bytes().splitlines(keepends=True)[0]
    path.write_bytes(first)
    with pytest.raises(CanaryStopped, match="native_audit_failed"):
        runner.audit_native_journal(state.bindings[0], ledger)


def test_standalone_refusal_is_delivered_but_not_explicit_decline_reference(http_boundary):
    """Provider refusal is a mechanical no-read disposition, never RQ's explicit-decline label."""
    state = http_boundary

    def refusal(reply):
        reply["choices"][0].update(message={"role": "assistant", "content": None,
                                           "refusal": "OFFLINE_REFUSAL_NOT_FOR_PUBLICATION"}, finish_reason="stop")

    state.change = refusal
    post, replay, execution, key = execute(state)
    checked = runner.audit_http(state.cases[0], execution, post.content, replay.content, key)
    assert checked["mechanical_passed"] and not checked["reference_passed"]
    assert checked["result"]["reason"] == "selector_refused"
    assert not execution.local_reads and not execution.delivery_reads
    assert "OFFLINE_REFUSAL" not in runner._encoded(checked).decode()


@pytest.mark.parametrize("defect", ["key", "field", "text", "read_count"])
def test_receipt_response_tampering_fails_exact_audit(http_boundary, defect):
    """Hashes, full fields, exact text and actual replay counters are delivery gates."""
    state = http_boundary
    post, replay, execution, key = execute(state)
    payload = replay.json()
    if defect == "key":
        payload["receipt_key_sha256"] = "0" * 64
    elif defect == "field":
        payload.pop("provider_cost")
    elif defect == "text":
        payload["result"]["saved_text"]["text"] += "normalized"
    else:
        payload["delivery_source_reads"] = 0
    raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    with pytest.raises((CanaryStopped, ValueError)):
        runner.audit_http(state.cases[0], execution, post.content, raw, key)


def test_changed_saved_source_does_not_redispatch_or_invent_replay(http_boundary):
    """Actual loader drift after execution makes delivery unavailable, not a new intent."""
    state = http_boundary
    from api.saved_source_receipt_app import create_saved_source_receipt_app

    binding = state.bindings[0]
    ledger = runner.native.LocatorQwenLedger(state.batch.output_dir / "RQ01")
    selector = BoundCaseSelector(FAKE_KEY, binding, state.batch, ledger, check_identity=state.identity)
    with runner.isolated_runtime(state.batch.output_dir / "synthetic", state.cases) as (loader, owner, _runs):
        key = "v1." + str(int(time.time())) + "." + "c" * 64
        state.batch.bind_http_intent("RQ01", runner.digest(key.encode()), owner)
        app = create_saved_source_receipt_app(load_snapshot=loader,
            journal_root=state.batch.output_dir / "synthetic", selector=selector,
            selector_identity=binding.selector_identity)
        headers = {"X-Access-Code": runner.CODE, "Idempotency-Key": key}
        with TestClient(app) as client:
            post = client.post(f"/api/runs/{binding.run_id}/saved-source-location",
                               json={"question": binding.question}, headers=headers)
            assert post.json()["state"] == "completed"
            path = state.batch.output_dir / "synthetic" / binding.run_id / "validated_sources.json"
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["academic_sources"][1]["evidence_summary"] += " drift"
            path.write_text(json.dumps(raw), encoding="utf-8")
            reply = client.get("/api/saved-source-receipts", headers=headers)
        assert reply.json()["delivery"] == "changed" and reply.json()["result"] is None
        assert len(state.requests) == 1 and selector.audit()["callback_entries"] == 1


def test_child_key_absence_explicit_http_key_and_restoration_after_drained_error(http_boundary, monkeypatch):
    """The explicit key reaches HTTP, not child env; local failure restores env only after drain."""
    state = http_boundary
    sentinel = "sk-fake-parent-sentinel-not-native-key"
    monkeypatch.setenv("DASHSCOPE_API_KEY", sentinel)
    monkeypatch.setenv("RQ_UNRELATED_SETTING", "preserved")
    with pytest.raises(RuntimeError, match="after_drained"):
        with runner.without_provider_environment():
            assert "DASHSCOPE_API_KEY" not in os.environ
            child = subprocess.run([sys.executable, "-c",
                "import os; assert 'DASHSCOPE_API_KEY' not in os.environ; print(os.environ['RQ_UNRELATED_SETTING'])"],
                capture_output=True, text=True, timeout=10)
            assert child.returncode == 0 and child.stdout.strip() == "preserved"
            _, _, execution, _ = execute(state)
            assert state.requests[0].headers["authorization"] == "Bearer " + FAKE_KEY
            assert all(not thread.is_alive() for thread in execution.threads)
            raise RuntimeError("after_drained")
    assert os.environ["DASHSCOPE_API_KEY"] == sentinel
    assert os.environ["RQ_UNRELATED_SETTING"] == "preserved"


def test_missing_key_environment_remains_missing_after_scope(monkeypatch):
    """An offline no-key parent must not gain an environment credential on cleanup."""
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with runner.without_provider_environment():
        assert "DASHSCOPE_API_KEY" not in os.environ
    assert "DASHSCOPE_API_KEY" not in os.environ
