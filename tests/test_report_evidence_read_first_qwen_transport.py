"""Real RP/read/HTTP seams for the new transform; no provider or ambient keys."""

from copy import deepcopy
import json
from types import SimpleNamespace

import httpx
import pytest

from academic_agent import report_evidence_followup as core
from academic_agent import report_evidence_relation_policy as policy
from academic_agent import report_evidence_read_first_qwen_transport as adapter
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource

KEY = "sk-read-first-offline-fictional-key"
CLAIM = "The fictional sample has conductivity 2.4 W/(m K)."
USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}


def snapshot(text="Conductivity is 2.4 W/(m K).", count=1, title="Fictional record"):
    return ReportEvidenceSnapshot(report_ref="read-first-test", sources=tuple(
        SnapshotSource(source_id=f"A{i}", group="academic", title=title, publisher="Synthetic",
                       source_type="control", accessed_date="2026-09-18", summary=text)
        for i in range(1, count + 1)))


def read(**args):
    arguments = {"source_id": "A1", "offset": 0, "length": 1500, **args}
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": "rf_read", "type": "function",
        "function": {"name": "read_source", "arguments": json.dumps(arguments, indent=1)}}]}


def final(body, relation=None):
    result = json.loads(body["messages"][-1]["content"]) if body["messages"][-1]["role"] == "tool" else {}
    relation = relation or ("supported" if result.get("text", "").strip() else "unavailable")
    return {"role": "assistant", "content": json.dumps({
        "claim_relation": relation, "answer": "Scripted control, not provider judgment.",
        "supporting_evidence_ids": [result["evidence_id"]] if relation in {"supported", "refuted"} else [],
        "caveats": ["Saved text only."]})}


def payload(message, **overrides):
    return {"model": "qwen3.5-plus", "usage": dict(USAGE), "choices": [{
        "index": 0, "message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
    }], **overrides}


def policy_expansion_snapshot(snap, claim):
    """Select a real bounded read whose inner callback fits but RP append does not."""
    for length in range(1000, 1501, 50):
        candidate = snap.model_copy(update={"sources": (
            snap.sources[0].model_copy(update={"summary": "界" * length}),)})
        message = {"role": "tool", "tool_call_id": "rf_read",
                   "content": core._json(adapter.expected_read_result(candidate))}
        request = adapter.callback_template(candidate, claim, previous=read(), tool_message=message)
        after = len(adapter._encoded(request))
        request["messages"][0]["content"] = request["messages"][0]["content"].removesuffix(policy.POLICY_APPEND)
        if len(adapter._encoded(request)) <= policy.MAX_CALLBACK_BYTES < after:
            return candidate
    raise AssertionError("no policy-expansion boundary control fits the frozen bounds")


@pytest.fixture
def offline(monkeypatch, tmp_path):
    state = SimpleNamespace(requests=[], reads=[], callbacks=[], first=None, change_payload=None,
                            status=200, relation=None, client_options=[], transport_options=[])
    real_client, real_read = httpx.AsyncClient, core.read_source

    def dispatch(request):
        state.requests.append(request)
        body = json.loads(request.content)
        # Tolerate auto in the script: the test must detect a reverted choice,
        # not pass because an unexpected mock invocation happened to crash.
        initial = body["messages"][-1]["role"] != "tool" and bool(body.get("tools"))
        message = (deepcopy(state.first) if state.first is not None else read()) if initial else final(body, state.relation)
        result = payload(message)
        if state.change_payload:
            state.change_payload(result)
        return httpx.Response(state.status, stream=httpx.ByteStream(adapter._encoded(result)))

    def transport(**kwargs):
        state.transport_options.append(kwargs)
        return httpx.MockTransport(dispatch)

    def client(**kwargs):
        assert isinstance(kwargs["transport"], httpx.MockTransport)
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        state.client_options.append(kwargs)
        return real_client(**kwargs)

    def observed_read(*args, **kwargs):
        state.reads.append((args, kwargs))
        return real_read(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setattr(core, "read_source", observed_read)
    state.ledger = adapter.ReadFirstQwenLedger(tmp_path / "read-first")
    return state


def run(state, snap=None, proxy=None):
    snap = snapshot() if snap is None else snap
    transport = adapter.ReadFirstQwenFollowupTransport(KEY, state.ledger, snapshot=snap, claim=CLAIM)

    def forward(request):
        state.callbacks.append(deepcopy(request))
        if proxy:
            proxy(request)
        return transport(request)

    result = policy.run_relation_policy_followup(snap, CLAIM, callback=forward)
    return result, transport


@pytest.mark.parametrize(("text", "count", "relation", "reads", "receipts", "usable", "availability"), [
    ("unused", 0, "unavailable", 0, 0, 0, "no_source"),
    (None, 1, "unavailable", 1, 0, 0, "missing_text"),
    ("", 1, "unavailable", 1, 0, 0, "missing_text"),
    (" \t\n", 1, "unavailable", 1, 1, 0, "blank_text"),
    ("Saved text. 🙂", 1, "supported", 1, 1, 1, "usable_text"),
    ("Saved text.", 1, "refuted", 1, 1, 1, "usable_text"),
    ("Saved text.", 1, "insufficient", 1, 1, 1, "usable_text"),
])
def test_actual_wire_read_and_availability(offline, text, count, relation, reads, receipts, usable, availability):
    """A named-choice regression must fail even with valid downstream replies."""
    offline.relation = relation
    snap = snapshot(text, count)
    result, transport = run(offline, snap)
    assert result.inner.state != "failed"
    assert result.inner.model_assessment.claim_relation == relation
    assert len(offline.reads) == reads
    assert len(offline.requests) == 1 + reads
    audit = adapter.availability_audit(snap, result, records=offline.ledger.records)
    assert audit["read_executions"] == reads
    for boundary in ("inner_delivery", "policy_callback_delivery"):
        assert audit[boundary]["state"] == availability
        assert len(audit[boundary]["delivered_read_ids"]) == receipts
        assert len(audit[boundary]["usable_read_ids"]) == usable
    assert len(audit["native_intent_response"]["requests"]) == 1 + reads
    if count:
        first = json.loads(offline.requests[0].content)
        assert first["tool_choice"] == {"type": "function", "function": {"name": "read_source"}}
        props = first["tools"][0]["function"]["parameters"]["properties"]
        assert props["offset"]["enum"] == [0] and props["length"]["enum"] == [1500]
        assert first["tools"][0]["function"]["parameters"]["additionalProperties"] is False
        assert "response_format" not in first
        assert offline.callbacks[0]["tool_choice"] == "auto"
        assert "enum" not in offline.callbacks[0]["tools"][0]["function"]["parameters"]["properties"]["offset"]
        last = json.loads(offline.requests[-1].content)
        assert last["messages"][3] == read()  # No argument re-encoding or null-content repair.
        tool = json.loads(last["messages"][4]["content"])
        assert tool == adapter.expected_read_result(snap)
    last = json.loads(offline.requests[-1].content)
    assert last["tool_choice"] == "none" and "tools" not in last
    assert last["response_format"] == {"type": "json_object"}
    for request, entry, rp, record in zip(
            offline.requests, transport.exchanges, result.audit.callback_entries, offline.ledger.records, strict=True):
        assert request.content == adapter._encoded(record["request"]) == adapter._encoded(adapter.native_body(entry["request"]))
        assert entry["native_body_hash"] == record["request_sha256"] == adapter.digest(request.content)
        assert entry["native_body_bytes"] == len(request.content) <= 12 * 1024
        assert rp.request_hash == entry["request_hash"] == adapter.digest(adapter._encoded(entry["request"]))
        assert rp.request_bytes == entry["request_bytes"]
        assert entry["transform_identity"] == adapter.TRANSFORM_IDENTITY
        assert request.url == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert offline.transport_options == [{"retries": 0, "verify": True, "trust_env": False}] * (1 + reads)
    assert offline.ledger.summary()["unknown_usage_requests"] == 0


@pytest.mark.parametrize("snap", [snapshot(count=2), snapshot("x" * 1501), snapshot(title="x" * 257)])
def test_scope_is_not_unavailable(offline, snap):
    with pytest.raises(adapter.CanaryStopped, match="^out_of_scope$"):
        run(offline, snap)
    assert not offline.requests and not offline.reads and not offline.ledger.records
    assert offline.ledger.stop_reason == "out_of_scope"


@pytest.mark.parametrize("message", [
    {"role": "assistant", "content": '{"claim_relation":"unavailable","answer":"No read","supporting_evidence_ids":[],"caveats":[]}'},
    {"role": "assistant", "refusal": "No"},
    read(source_id="A2"), read(offset=1), read(length=1), read(length=1499),
    read(offset=False), read(offset=0.0), read(offset="0"), read(length=True), read(extra=1),
    {"role": "assistant", "content": None, "tool_calls": [*read()["tool_calls"], *read()["tool_calls"]]},
])
def test_first_reply_gate_precedes_local_read_and_second_post(offline, message):
    """Valid scripted finals remain available if a broken gate leaks onward."""
    offline.first = message
    result, _ = run(offline)
    assert result.inner.state == "failed"
    assert len(offline.requests) == 1 and not offline.reads
    assert offline.ledger.stop_reason is not None
    assert offline.ledger.records[0]["reported_usage"] == USAGE
    assert offline.ledger.summary()["unknown_usage_requests"] == 0


@pytest.mark.parametrize("field", ["text", "status", "start", "end", "stored_length", "source_hash",
                                 "summary_hash", "text_sha256", "window_truncated", "origin",
                                 "content_warning", "evidence_id", "history", "tool_call_id"])
def test_full_tool_result_and_history_before_second_post(offline, field):
    """Dropping full-result comparison leaks a forged payload into a valid final."""
    def forge(request):
        if len(request["messages"]) != 5:
            return
        if field == "history":
            request["messages"][3]["content"] = "Forged native history."
        elif field == "tool_call_id":
            request["messages"][4]["tool_call_id"] = "other"
        else:
            result = json.loads(request["messages"][4]["content"])
            result[field] = True if field == "window_truncated" else False if field in {"start", "end", "stored_length"} else "forged"
            request["messages"][4]["content"] = json.dumps(result)
    result, _ = run(offline, proxy=forge)
    assert len(offline.reads) == 1 and len(offline.requests) == 1
    assert result.inner.state == "failed"
    assert len(result.audit.callback_entries) == 2  # Callback delivery is not HTTP.


@pytest.mark.parametrize("field", ["system", "claim", "catalog", "choice", "schema", "extra"])
def test_original_callback_admission(offline, field):
    def forge(request):
        if field in {"system", "claim", "catalog"}:
            request["messages"][{"system": 0, "claim": 1, "catalog": 2}[field]]["content"] += " changed"
        elif field == "choice":
            request["tool_choice"] = deepcopy(adapter.NAMED_CHOICE)
        elif field == "schema":
            request["tools"][0]["function"]["parameters"]["properties"]["offset"]["enum"] = [0]
        else:
            request["response_format"] = {"type": "json_object"}
    result, _ = run(offline, proxy=forge)
    assert result.inner.state == "failed" and not offline.requests and not offline.reads


@pytest.mark.parametrize("fault", ["model", "usage_bool", "usage_sum", "tokens", "secret_metadata",
                                 "secret_arguments", "index_bool", "finish", "status"])
def test_rejected_protocol_and_whole_payload_secrets_retain_usage(offline, fault):
    def change(value):
        if fault == "model":
            value["model"] = "different-model"
        elif fault == "usage_bool":
            value["usage"]["prompt_tokens"] = True
        elif fault == "usage_sum":
            value["usage"]["total_tokens"] += 1
        elif fault == "tokens":
            value["usage"] = {"prompt_tokens": 100, "completion_tokens": 513, "total_tokens": 613}
        elif fault == "secret_metadata":
            value["discarded_metadata"] = "Echo: " + "".join(f"\\u{ord(c):04x}" for c in KEY)
        elif fault == "secret_arguments":
            value["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = KEY
        elif fault == "index_bool":
            value["choices"][0]["index"] = False
        elif fault == "finish":
            value["choices"][0]["finish_reason"] = "length"
    offline.change_payload = change
    if fault == "status":
        offline.status = 429
    result, _ = run(offline)
    assert result.inner.state == "failed" and len(offline.requests) == 1 and not offline.reads
    unknown = fault in {"usage_bool", "usage_sum", "status"}
    assert offline.ledger.summary()["unknown_usage_requests"] == int(unknown)
    assert float(offline.ledger.summary()["budget_consumed_usd"]) >= 0.011149312
    stored = (offline.ledger.output_dir / "events.jsonl").read_text()
    assert KEY not in stored and "discarded_metadata" not in stored
    if fault.startswith("secret"):
        assert offline.ledger.stop_reason == "secret_in_response"
        assert "assistant_message" not in offline.ledger.records[0]


def test_complete_transformed_wire_bound(offline, monkeypatch):
    original = adapter.native_body

    def inflated(request):
        return {**original(request), "padding": "x" * adapter.REQUEST_BYTES}
    monkeypatch.setattr(adapter, "native_body", inflated)
    result, _ = run(offline)
    assert result.inner.state == "failed" and not offline.requests
    assert offline.ledger.stop_reason == "request_too_large"


@pytest.mark.parametrize("stage", ["reserve", "callback", "finish"])
def test_journal_failure_never_retries_or_loses_known_usage(offline, monkeypatch, stage):
    original = offline.ledger._append
    selected = {"reserve": "request_reserved", "callback": "read_first_callback", "finish": "request_finished"}[stage]

    def fail(event):
        if event["event"] == selected:
            offline.ledger.stop_reason = "persistence_failed"
            raise adapter.CanaryStopped("persistence_failed")
        original(event)
    monkeypatch.setattr(offline.ledger, "_append", fail)
    result, _ = run(offline)
    assert result.inner.state == "failed" and not offline.reads
    assert len(offline.requests) == int(stage == "finish")
    if stage == "finish":
        assert offline.ledger.records[0]["reported_usage"] == USAGE
        assert offline.ledger.pending == 1


@pytest.mark.parametrize("key", [None, True, 123, "", "has whitespace"])
def test_exact_key_types_only(offline, key):
    with pytest.raises(adapter.CanaryStopped, match="invalid_dedicated_key"):
        adapter.ReadFirstQwenFollowupTransport(key, offline.ledger, snapshot=snapshot(), claim=CLAIM)
    assert not offline.requests
