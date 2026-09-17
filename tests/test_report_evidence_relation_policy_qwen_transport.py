"""Real frozen RP -> claim/catalog/core executor -> intercepted HTTP -> intent.

No provider keys, saved private reports or adapter-callback simulations. Proxies
only capture/tamper requests before forwarding to the real native transport.
"""

import asyncio
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import inspect
import socket

import httpx
import pytest

from academic_agent import report_evidence_claim_relation as claim_policy
from academic_agent import report_evidence_followup as core
from academic_agent import report_evidence_relation_policy as policy
from academic_agent import report_evidence_relation_policy_qwen_transport as adapter
from academic_agent import report_evidence_qwen_canary as frozen
from academic_agent import report_evidence_qwen_transport as base
from academic_agent.report_evidence_catalog_followup import build_catalog
from academic_agent.report_evidence_catalog_qwen_transport import (
    CatalogQwenFollowupTransport, CatalogQwenLedger, _system_content,
)
from academic_agent.report_evidence_relation_policy_qwen_transport import (
    RelationPolicyQwenFollowupTransport, RelationPolicyQwenLedger, FROZEN_DEPENDENCY_COUPLING,
    TRANSPORT_IDENTITY, relation_policy_qwen_configuration,
)
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource

KEY = "sk-fictional-offline-key"
CLAIM = "The fictional pump has 12 L/min flow."
USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def make_snapshot(count=6, *, title="Fictional pump", summary="Flow is 12 L/min. No lifetime test. 🙂"):
    return ReportEvidenceSnapshot(report_ref="fictional-claim-wire", sources=tuple(
        SnapshotSource(source_id=f"A{i}", group="academic", title=f"{title} {i}", summary=summary,
                       publisher="Invented", source_type="control", origin="abstract", accessed_date="2026-09-16")
        for i in range(1, count + 1)
    ))


def final(relation="unavailable", *, ids=(), answer="Synthetic answer", caveats=("Saved text only.",)):
    return {"role": "assistant", "content": json.dumps({
        "claim_relation": relation, "answer": answer, "supporting_evidence_ids": list(ids), "caveats": list(caveats),
    })}


def read(source_id="A6", *, offset=0, length=1500, name="read_source", args=None, call_id="claim_read"):
    args = {"source_id": source_id, "offset": offset, "length": length} if args is None else args
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": call_id, "type": "function", "function": {
            "name": name, "arguments": args if isinstance(args, str) else json.dumps(args),
        },
    }]}


def read_final(relation="supported", answer="Flow is 12 L/min.\n"):
    def reply(body):
        tool = json.loads(body["messages"][-1]["content"])
        return final(relation, ids=[tool["evidence_id"]] if relation in {"supported", "refuted"} else (), answer=answer)
    return reply


def payload(message=None, **overrides):
    message = final() if message is None else message
    return {"model": frozen.MODEL, "usage": deepcopy(USAGE), "choices": [{
        "index": 0, "message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
    }], **overrides}


def response(value, status=200, headers=None):
    return httpx.Response(status, stream=httpx.ByteStream(value if isinstance(value, bytes) else encoded(value)), headers=headers)


def events(ledger):
    return [json.loads(line) for line in (ledger.output_dir / "events.jsonl").read_text().splitlines()]


@pytest.fixture
def ledger(tmp_path):
    return RelationPolicyQwenLedger(tmp_path / "claim-wire")


@pytest.fixture
def snapshot():
    return make_snapshot()


@pytest.fixture(autouse=True)
def mock_http(monkeypatch):
    state = {"requests": [], "intents": [], "transport_options": [], "client_options": [], "handler": None}
    real_client = httpx.AsyncClient
    real_pair, real_connect = socket.socketpair, socket.socket.connect
    creating_pair = False

    def forbidden(*args, **kwargs):
        pytest.fail("real HTTP is forbidden")

    def self_pipe(*args, **kwargs):
        # Windows asyncio's owned self-pipe uses the stdlib loopback socketpair
        # fallback. Blocking that internal IPC breaks loop construction before
        # HTTP and yields misleading unawaited-coroutine warnings. Permit only
        # that synchronous stdlib operation, not arbitrary loopback networking.
        nonlocal creating_pair
        creating_pair = True
        try:
            return real_pair(*args, **kwargs)
        finally:
            creating_pair = False

    def guarded_connect(sock, address):
        if creating_pair and isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return real_connect(sock, address)
        forbidden()

    async def dispatch(request):
        state["requests"].append(request)
        if state["handler"] is None:
            pytest.fail("unexpected intercepted HTTP")
        result = state["handler"](request)
        return await result if asyncio.iscoroutine(result) else result

    def make_transport(**kwargs):
        state["transport_options"].append(kwargs)
        return httpx.MockTransport(dispatch)

    def make_client(**kwargs):
        state["client_options"].append(kwargs)
        if (not isinstance(kwargs.get("transport"), httpx.MockTransport)
                or kwargs.get("trust_env") is not False or kwargs.get("proxy") is not None or kwargs.get("mounts")):
            forbidden()
        return real_client(**kwargs)

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "socketpair", self_pipe)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(httpx, "Client", forbidden)
    monkeypatch.setattr(httpx, "HTTPTransport", forbidden)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", make_transport)
    monkeypatch.setattr(httpx, "AsyncClient", make_client)
    return state


@pytest.fixture
def tool_spy(monkeypatch):
    calls = []
    for name in ("lookup_sources", "read_source"):
        original = getattr(core, name)

        def observe(*args, _name=name, _original=original, **kwargs):
            calls.append((_name, deepcopy(kwargs)))
            return _original(*args, **kwargs)

        monkeypatch.setattr(core, name, observe)
    return calls


def script(mock_http, ledger, *replies):
    remaining = iter(replies)

    def handle(request):
        mock_http["intents"].append(events(ledger)[-1])
        item = next(remaining)
        return response(payload(item(json.loads(request.content)) if callable(item) else item))

    mock_http["handler"] = handle


def run_rp(snapshot, ledger, *, claim=CLAIM, proxy=None):
    transport = RelationPolicyQwenFollowupTransport(KEY, ledger, snapshot=snapshot, claim=claim)

    def forward(request):
        if proxy:
            proxy(request)
        return transport(request)

    return policy.run_relation_policy_followup(snapshot, claim, callback=forward), transport


def run(snapshot, ledger, *, claim=CLAIM, proxy=None):
    """Compatibility in test helpers only; every scenario traverses actual RP."""
    result, transport = run_rp(snapshot, ledger, claim=claim, proxy=proxy)
    return result.inner, transport


def initial_request(snapshot, claim=CLAIM):
    """Independent expected callback template; integration tests use the real wrapper."""
    catalog = build_catalog(snapshot)
    tools = [core.tool_definitions()[1]] if catalog["entries"] else []
    if tools:
        tools[0]["function"]["parameters"]["properties"]["source_id"]["enum"] = [item["source_id"] for item in catalog["entries"]]
    return {"messages": [
        {"role": "system", "content": _system_content(snapshot, bool(tools)).replace(claim_policy._OLD_FINAL, claim_policy._NEW_FINAL, 1) + policy.POLICY_APPEND},
        {"role": "user", "content": claim}, {"role": "user", "content": encoded(catalog).decode()},
    ], "tools": tools, "tool_choice": "auto" if tools else "none"}


def outer_body(request):
    body = {**deepcopy(request), "model": "qwen3.5-plus", "stream": False, "enable_thinking": False,
            "parallel_tool_calls": False, "temperature": 0, "max_tokens": 512}
    if request["tool_choice"] == "none":
        del body["tools"]
        body["response_format"] = {"type": "json_object"}
    return body


def assert_journal(mock_http, ledger):
    assert len(mock_http["intents"]) == len(ledger.records) == len(mock_http["requests"])
    for request, intent, record in zip(mock_http["requests"], mock_http["intents"], ledger.records, strict=True):
        assert intent["event"] == "request_reserved"
        assert intent["request_sha256"] == record["request_sha256"] == hashlib.sha256(request.content).hexdigest()
        assert intent["request"] == record["request"] == json.loads(request.content)
        assert intent["usage_status"] == "unknown" and intent["provider_response_received"] is False
        assert record["usage_status"] == "complete" and record["reported_usage"] == USAGE
        assert record["provider_response_received"] is True
    finishes = [event for event in events(ledger) if event["event"] == "request_finished"]
    assert [{key: value for key, value in row.items() if key != "event"} for row in finishes] == ledger.records


def assert_stopped(transport, ledger, mock_http, reason, *, count=1, known=True, received=True):
    assert ledger.stop_reason == reason and len(mock_http["requests"]) == count
    if ledger.records:
        row = ledger.records[-1]
        assert row["usage_status"] == ("complete" if known else "unknown")
        assert row["provider_response_received"] is received
        assert row["protocol_accepted"] is False and "assistant_message" not in row
        assert Decimal(ledger.summary()["budget_consumed_usd"]) >= frozen.RESERVATION_USD * count
        if known:
            assert Decimal(ledger.summary()["known_usage_estimated_usd"]) > 0
    with pytest.raises(frozen.CanaryStopped, match="batch_already_stopped"):
        transport({"messages": [], "tools": [], "tool_choice": "none"})
    assert len(mock_http["requests"]) == count


@pytest.mark.parametrize("claim,relation,summary", [
    (CLAIM, "supported", "Flow is 12 L/min."),
    (CLAIM, "refuted", "Flow is 8 L/min, not 12."),
    ("The pump does not have 12 L/min flow.", "supported", "Flow is 8 L/min."),
    (" \n虚构泵不具备 12 L/min 流量。\n ", "refuted", "Flow is 12 L/min."),
    (CLAIM, "insufficient", "Only casing colour was measured."),
    (CLAIM, "unavailable", None),
])
def test_relations_native_content_and_serialized_receipts(ledger, mock_http, tool_spy, claim, relation, summary):
    """All relations and negative propositions survive real HTTP without rewriting native content."""
    snapshot = make_snapshot(32, summary=summary)
    native = read("A32")
    script(mock_http, ledger, native, read_final(relation, "原始 answer.\n"))
    callbacks = []
    result, _ = run(snapshot, ledger, claim=claim, proxy=lambda request: callbacks.append(deepcopy(request)))
    data = json.loads(result.model_dump_json())
    assert claim_policy.ClaimRelationFollowupResult.model_validate_json(result.model_dump_json()) == result
    assert data["state"] == ("answered_with_evidence" if relation in {"supported", "refuted"} else "abstained")
    assert data["claim"] == claim and data["answer"] == "原始 answer.\n"
    assert data["model_assessment"] == json.loads(ledger.records[-1]["assistant_message"]["content"])
    assert data["model_assessment"]["claim_relation"] == relation
    assert data["model_assessment"]["caveats"] == ["Saved text only."]
    assert data["semantic_support"] == "not_assessed" and data["answer_verification"] == "not_verified"
    assert data["assessment_origin"] == "injected_transport_unverified"
    assert data["audit"]["callback_bytes"] == [
        len(encoded({**item, "messages": [
            {**item["messages"][0], "content": item["messages"][0]["content"].removesuffix(policy.POLICY_APPEND)},
            *item["messages"][1:],
        ]})) for item in callbacks
    ]
    assert data["audit"]["downstream_calls"] == 2 and data["audit"]["catalog"]["core"]["tool_executions"] == 1
    assert tool_spy == [("read_source", {"source_id": "A32", "offset": 0, "length": 1500})]
    assert_journal(mock_http, ledger)
    bodies = [json.loads(item.content) for item in mock_http["requests"]]
    assert bodies == [outer_body(item) for item in callbacks]
    assert len(bodies[0]["messages"]) == 3 and len(bodies[1]["messages"]) == 5
    assert bodies[0]["tool_choice"] == "auto" and "response_format" not in bodies[0]
    assert bodies[1]["tool_choice"] == "none" and "tools" not in bodies[1]
    assert bodies[1]["response_format"] == {"type": "json_object"}
    assert bodies[0]["tools"][0]["function"]["parameters"]["properties"]["source_id"]["enum"] == [f"A{i}" for i in range(1, 33)]
    for body in bodies:
        assert body["messages"][1] == {"role": "user", "content": claim}
        assert body["messages"][2]["content"] == encoded(build_catalog(snapshot)).decode()
        assert claim_policy._NEW_FINAL in body["messages"][0]["content"]
        assert body["messages"][0]["content"].endswith(policy.POLICY_APPEND)
        assert body["messages"][0]["content"].count(policy.POLICY_APPEND) == 1
        assert claim_policy._OLD_FINAL not in body["messages"][0]["content"]
    assert bodies[1]["messages"][3] == native
    delivered = json.loads(bodies[1]["messages"][4]["content"])
    assert bodies[1]["messages"][4]["tool_call_id"] == "claim_read"
    assert data["audit"]["delivered_read_ids"] == [item["evidence_id"] for item in data["served_evidence"]]
    assert data["read_status"] == ("no_usable_text" if summary is None else "usable_text")
    if summary is not None:
        assert data["served_evidence"][0]["text"] == summary == delivered["text"]
    assert ledger.stop_reason is None and ledger.pending is None


@pytest.mark.parametrize("summary,offset,length,reason", [
    ("", 10, 1, "missing_text"), (" \t\n", 0, 1500, "ok"),
    ("abc", 3, 1, "empty_window"), ("abc", 4, 1, "offset_out_of_range"),
    ("a🙂中bc", 1, 2, "ok"),
])
def test_absence_whitespace_and_unicode_windows(ledger, mock_http, tool_spy, summary, offset, length, reason):
    """A whitespace receipt is delivered but unusable; offsets count Unicode code points, not wire bytes."""
    snapshot = make_snapshot(1, summary=summary)
    usable = bool(summary[offset:offset + length].strip())
    script(mock_http, ledger, read("A1", offset=offset, length=length), read_final("insufficient" if usable else "unavailable"))
    result, _ = run(snapshot, ledger)
    assert result.state == "abstained" and result.audit.read_result_reason == reason
    assert result.read_status == ("usable_text" if usable else "no_usable_text")
    assert len(tool_spy) == result.audit.catalog.core.tool_executions == 1
    assert len(result.served_evidence) == int(reason == "ok")
    if reason == "ok":
        assert result.served_evidence[0].text == summary[offset:offset + length]
    assert_journal(mock_http, ledger)


@pytest.mark.parametrize("mode", ["empty", "early", "refusal"])
def test_no_read_final_and_closed_conversation(ledger, mock_http, tool_spy, mode):
    """Early finals/refusals issue no receipt and cannot reopen the session under a six-call ledger."""
    snapshot = make_snapshot(0 if mode == "empty" else 6)
    script(mock_http, ledger, {"role": "assistant", "refusal": "Cannot judge"} if mode == "refusal" else final())
    result, transport = run(snapshot, ledger)
    assert result.state == "abstained" and result.read_status == "not_checked" and not result.served_evidence
    assert not tool_spy and result.audit.downstream_calls == 1
    assert_journal(mock_http, ledger)
    body = json.loads(mock_http["requests"][0].content)
    if mode == "empty":
        assert "tools" not in body and body["response_format"] == {"type": "json_object"}
    with pytest.raises(frozen.CanaryStopped, match="conversation_closed"):
        transport(initial_request(snapshot))
    assert len(mock_http["requests"]) == 1


@pytest.mark.parametrize("kind", ["old_three", "duplicate", "wrong_field", "source_id", "forged_id", "unavailable_after_read"])
def test_native_final_not_repaired_by_transport(snapshot, ledger, mock_http, tool_spy, kind):
    """Transport success cannot hide strict claim-envelope/receipt failures or erase known usage."""
    def malformed(body):
        message = read_final()(body)
        value = json.loads(message["content"])
        if kind == "old_three":
            value = {"answer": "Old answer", "status": "answered", "evidence_ids": value["supporting_evidence_ids"]}
        elif kind == "duplicate":
            message["content"] = message["content"].replace('"claim_relation":', '"claim_relation":"refuted","claim_relation":')
            return message
        elif kind == "wrong_field":
            value["status"] = "answered"
        elif kind in {"source_id", "forged_id"}:
            value["supporting_evidence_ids"] = ["A6" if kind == "source_id" else "ev_" + "0" * 64]
        else:
            value.update(claim_relation="unavailable", supporting_evidence_ids=[])
        return {"role": "assistant", "content": json.dumps(value)}

    script(mock_http, ledger, read(), malformed)
    result, transport = run(snapshot, ledger)
    assert result.state == "failed" and result.model_assessment is None and result.answer is None
    assert len(result.served_evidence) == len(tool_spy) == 1 and result.audit.downstream_calls == 2
    assert result.audit.refusal == ("invalid_claim_relation_envelope" if kind in {"old_three", "duplicate", "wrong_field"}
                                   else "claim_relation_receipt_mismatch")
    assert ledger.stop_reason is None and all(row["protocol_accepted"] for row in ledger.records)
    assert ledger.records[-1]["assistant_message"] == malformed(ledger.records[-1]["request"])
    assert_journal(mock_http, ledger)
    with pytest.raises(frozen.CanaryStopped, match="conversation_closed"):
        transport(initial_request(snapshot))
    assert len(mock_http["requests"]) == 2


def test_first_claim_tampering_never_reserves(snapshot, ledger, mock_http):
    """Binding only second-turn claim history would transmit an unauthorized first proposition."""
    script(mock_http, ledger, final())  # A removed check reaches normal HTTP, not an incidental mock failure.
    result, _ = run(snapshot, ledger, proxy=lambda request: request["messages"][1].update(content="Different first claim"))
    assert len(mock_http["requests"]) == 0, "first-claim admission must prevent HTTP"
    assert not ledger.records and ledger.stop_reason == "claim_history_mismatch"
    assert result.state == "failed" and result.audit.downstream_calls == 1


@pytest.mark.parametrize("kind", ["old_system", "catalog", "extra_message", "reverse_enum", "boolean_bound", "fake_final"])
def test_initial_history_and_schema_fail_closed(snapshot, ledger, mock_http, kind):
    """Caller text/catalog/tool declarations cannot replace the bound claim contract."""
    script(mock_http, ledger, final())
    def tamper(request):
        if kind == "old_system":
            request["messages"][0]["content"] = _system_content(snapshot, True)
        elif kind == "catalog":
            request["messages"][2]["content"] += " "
        elif kind == "extra_message":
            request["messages"].append({"role": "assistant", "content": "Invented history"})
        elif kind == "reverse_enum":
            request["tools"][0]["function"]["parameters"]["properties"]["source_id"]["enum"].reverse()
        elif kind == "boolean_bound":
            request["tools"][0]["function"]["parameters"]["properties"]["length"]["minimum"] = True
        else:
            request.update(tool_choice="none", tools=[])

    result, transport = run(snapshot, ledger, proxy=tamper)
    assert result.state == "failed" and not ledger.records
    assert_stopped(transport, ledger, mock_http, ledger.stop_reason, count=0)


@pytest.mark.parametrize("kind", ["claim", "system", "assistant_content", "call_id", "arguments", "tool_id", "missing_result", "reopen"])
def test_second_history_bound_to_first_reply(snapshot, ledger, mock_http, tool_spy, kind):
    """Exactly five messages, full assistant call and original claim must precede a second reservation."""
    script(mock_http, ledger, read(), read_final())

    def tamper(request):
        history = request["messages"]
        if len(history) != 5:
            return
        if kind in {"claim", "system", "assistant_content"}:
            history[{"claim": 1, "system": 0, "assistant_content": 3}[kind]]["content"] = "Changed JSON history"
        elif kind == "call_id":
            history[3]["tool_calls"][0]["id"] = "other_call"
        elif kind == "arguments":
            history[3]["tool_calls"][0]["function"]["arguments"] += " "
        elif kind == "tool_id":
            history[4]["tool_call_id"] = "other_call"
        elif kind == "missing_result":
            history.pop()
        else:
            request.update(tools=initial_request(snapshot)["tools"], tool_choice="auto")

    result, transport = run(snapshot, ledger, proxy=tamper)
    assert result.state == "failed" and result.audit.downstream_calls == 2
    assert len(ledger.records) == len(mock_http["requests"]) == len(tool_spy) == len(result.served_evidence) == 1
    assert ledger.stop_reason is not None and ledger.records[0]["reported_usage"] == USAGE
    with pytest.raises(frozen.CanaryStopped, match="batch_already_stopped"):
        transport(initial_request(snapshot))
    assert len(mock_http["requests"]) == 1


@pytest.mark.parametrize("kind", ["text", "text_and_hash", "false_missing", "false_empty", "start_bool", "receipt", "source_hash", "extra"])
def test_full_result_forgery_never_reserves_second_request(snapshot, ledger, mock_http, tool_spy, kind):
    """Preserving source/snapshot hashes cannot authorize a substituted window or false absence."""
    script(mock_http, ledger, read(), final())

    def tamper(request):
        if len(request["messages"]) != 5:
            return
        message = request["messages"][4]
        value = json.loads(message["content"])
        if kind in {"text", "text_and_hash"}:
            value["text"] = "Forged pump deployment success"
            if kind == "text_and_hash":
                value["text_sha256"] = hashlib.sha256(value["text"].encode()).hexdigest()
        elif kind == "false_missing":
            value = {key: value[key] for key in ("source_id", "origin", "stored_length", "content_warning", "text_scope")}
            value["status"] = "missing_text"
        elif kind == "false_empty":
            value.update(status="empty_window", text="", end=0, text_sha256=hashlib.sha256(b"").hexdigest())
            del value["evidence_id"]
        elif kind == "start_bool":
            value["start"] = False
        elif kind == "receipt":
            value["evidence_id"] = "ev_" + "0" * 64
        elif kind == "source_hash":
            value["source_hash"] = "0" * 64
        else:
            value["untrusted_extra"] = "must reject"
        message["content"] = json.dumps(value)

    result, _ = run(snapshot, ledger, proxy=tamper)
    assert len(mock_http["requests"]) == 1, "full-result admission must prevent the second HTTP"
    assert ledger.stop_reason == "tool_result_payload_mismatch"
    assert result.state == "failed" and result.audit.downstream_calls == 2
    assert len(ledger.records) == len(tool_spy) == len(result.served_evidence) == 1
    assert result.served_evidence[0].text == snapshot.sources[-1].summary
    assert "Forged pump" not in (ledger.output_dir / "events.jsonl").read_text()


@pytest.mark.parametrize("stage,target,unit", [
    ("initial", 12288, "x"), ("initial", 12289, "中"), ("initial", 12288, "🙂"),
    ("second", 12288, "中"), ("second", 12289, "x"), ("second", 12289, "🙂"),
])
def test_actual_wire_limit_before_reserve(ledger, tmp_path, mock_http, tool_spy, stage, target, unit):
    """Callbacks fitting 12 KiB may not fit the final HTTP envelope, including JSON-mode overhead."""
    # RP adds 1,297 instruction bytes. Use a smaller final-stage catalog so
    # its unpadded probe is valid; the measured target still remains exactly
    # 12,288/+1 actual HTTP bytes, with no assertion or limit relaxed.
    snapshot = make_snapshot(32, title="t" * (140 if stage == "initial" else 80), summary="s" * 1500)
    if stage == "initial":
        baseline = len(encoded(outer_body(initial_request(snapshot, "Q"))))
    else:
        probe = RelationPolicyQwenLedger(tmp_path / "sizing-probe")
        script(mock_http, probe, read("A1"), read_final("insufficient"))
        result, _ = run(snapshot, probe, claim="Q")
        assert result.state == "abstained" and len(mock_http["requests"]) == 2
        baseline = len(mock_http["requests"][-1].content)
        mock_http["requests"].clear()
        mock_http["intents"].clear()
        tool_spy.clear()
    padding = target - baseline
    assert padding > 0
    unit_bytes = len(encoded(unit)) - 2
    claim = "Q" + unit * (padding // unit_bytes) + "x" * (padding % unit_bytes)
    assert len(claim) <= 4096
    callbacks = []
    script(mock_http, ledger, *([read("A1"), read_final("insufficient")] if stage == "second" else [final()]))
    result, _ = run(snapshot, ledger, claim=claim, proxy=lambda request: callbacks.append(deepcopy(request)))
    assert len(callbacks) == (2 if stage == "second" else 1)
    assert len(encoded(outer_body(callbacks[-1]))) == target
    assert all(size <= 12288 for size in result.audit.callback_bytes)
    if stage == "second":
        pre_json = {**outer_body(callbacks[-1]), "tools": []}
        del pre_json["response_format"]
        assert len(encoded(pre_json)) < 12288  # Removing ONLY final-wire guard must be detected.
    expected_http = (2 if stage == "second" else 1) - int(target > 12288)
    assert len(mock_http["requests"]) == expected_http, "actual final wire bound must prevent reservation and HTTP"
    assert len(ledger.records) == expected_http
    assert len(tool_spy) == int(stage == "second")
    if target > 12288:
        assert result.state == "failed" and ledger.stop_reason == "request_too_large"
        assert len(result.served_evidence) == int(stage == "second")  # Callback entry is not HTTP dispatch.
    else:
        assert result.state == "abstained" and ledger.stop_reason is None
        assert len(mock_http["requests"][-1].content) == 12288
        assert_journal(mock_http, ledger)


@pytest.mark.parametrize("reply,reason", [
    (read("A33"), "read_id_not_permitted"),
    (read(name="lookup_sources", args={"query": "pump"}), "unadvertised_tool"),
    (read(args='{"source_id":"A1","source_id":"A2","offset":0,"length":1}'), "invalid_tool_arguments"),
    (read(args={"source_id": "A1", "offset": True, "length": 1}), "invalid_tool_arguments"),
])
def test_impossible_native_tool_calls_keep_usage(ledger, mock_http, tool_spy, reply, reason):
    """Omitted IDs, duplicate arguments and lookup calls never buy local reads or repair requests."""
    snapshot = make_snapshot(33)
    script(mock_http, ledger, reply)
    result, transport = run(snapshot, ledger)
    assert result.state == "failed" and not tool_spy and not result.served_evidence
    assert_stopped(transport, ledger, mock_http, reason)


def test_second_tool_call_cannot_execute(snapshot, ledger, mock_http, tool_spy):
    """A native second tool request fails admission even though the ledger allows more total requests."""
    script(mock_http, ledger, read(), read(call_id="second_read"))
    result, transport = run(snapshot, ledger)
    assert result.state == "failed" and len(result.served_evidence) == len(tool_spy) == 1
    assert_stopped(transport, ledger, mock_http, "unadvertised_tool", count=2)


@pytest.mark.parametrize("kind", ["wrong_model", "missing_usage", "contradictory", "over_tokens", "bad_choices", "bad_finish"])
def test_response_model_usage_and_protocol_failures(snapshot, ledger, mock_http, kind):
    """Observed usage survives wrong model/native shape; unknown usage retains reservation and stops."""
    value = payload()
    known = kind not in {"missing_usage", "contradictory"}
    if kind == "wrong_model":
        value["model"] += "-alias"
    elif kind == "missing_usage":
        del value["usage"]
    elif kind == "contradictory":
        value["usage"]["total_tokens"] += 1
    elif kind == "over_tokens":
        value["usage"] = {"prompt_tokens": 100, "completion_tokens": 513, "total_tokens": 613}
    elif kind == "bad_choices":
        value["choices"] *= 2
    else:
        value["choices"][0]["finish_reason"] = "length"
    mock_http["handler"] = lambda request: response(value)
    result, transport = run(snapshot, ledger)
    assert result.state == "failed"
    reason = {"wrong_model": "unexpected_response_model", "missing_usage": "usage_unknown_or_contradictory",
              "contradictory": "usage_unknown_or_contradictory", "over_tokens": "token_reservation_exceeded"}.get(kind, "invalid_response_protocol")
    assert_stopped(transport, ledger, mock_http, reason, known=known)
    assert ledger.records[0]["response_model_matches_authorized"] is (kind != "wrong_model")
    assert ledger.summary()["unknown_usage_requests"] == int(not known)


@pytest.mark.parametrize("kind", ["redirect", "oversize", "compressed", "duplicate_json", "timeout", "exception"])
def test_http_failures_are_bounded_and_sanitized(snapshot, ledger, mock_http, kind):
    """Redirects/timeouts/corrupt responses cannot retry, leak exception text or claim complete usage."""
    def handle(request):
        if kind == "timeout":
            raise httpx.ReadTimeout("private exception " + KEY)
        if kind == "exception":
            raise RuntimeError("private exception " + KEY)
        if kind == "redirect":
            return response(b"", status=307, headers={"location": "https://invalid.example/never-follow"})
        if kind == "oversize":
            return response(b"x" * (frozen.RESPONSE_BYTES + 1))
        if kind == "compressed":
            return response(b"not decoded", headers={"content-encoding": "gzip"})
        return response(b'{"model":"x","model":"y"}')

    mock_http["handler"] = handle
    result, transport = run(snapshot, ledger)
    assert result.state == "failed" and KEY not in result.model_dump_json()
    reason = {"redirect": "http_status_rejected", "oversize": "response_too_large", "compressed": "response_encoding_rejected",
              "timeout": "request_timeout"}.get(kind, "response_or_transport_failed")
    assert_stopped(transport, ledger, mock_http, reason, known=False, received=kind not in {"timeout", "exception"})
    assert "private exception" not in (ledger.output_dir / "events.jsonl").read_text()


def test_deadline_drains_owned_http(snapshot, ledger, mock_http, monkeypatch):
    """The inherited total deadline cancels its coroutine, not an unowned background thread."""
    drained = []

    async def slow(request):
        try:
            await asyncio.sleep(10)
        finally:
            drained.append(True)
        return response(payload())

    monkeypatch.setattr(base, "TOTAL_SECONDS", 0.01)
    mock_http["handler"] = slow
    result, transport = run(snapshot, ledger)
    assert result.state == "failed" and drained == [True]
    assert_stopped(transport, ledger, mock_http, "request_timeout", known=False, received=False)


def test_second_unknown_usage_does_not_refund_first(snapshot, ledger, mock_http, tool_spy):
    """Known first usage and unknown final reservation survive independently with one actual read."""
    mock_http["handler"] = lambda request: response(payload(read()) if len(mock_http["requests"]) == 1 else payload(usage=None))
    result, transport = run(snapshot, ledger)
    assert result.state == "failed" and len(tool_spy) == len(result.served_evidence) == 1
    assert_stopped(transport, ledger, mock_http, "usage_unknown_or_contradictory", count=2, known=False)
    assert ledger.records[0]["reported_usage"] == USAGE
    assert ledger.summary()["unknown_usage_requests"] == 1
    assert ledger.summary()["cost_coverage"] == "lower_bound"
    assert Decimal(ledger.summary()["budget_consumed_usd"]) == frozen.RESERVATION_USD * 2
    assert Decimal(ledger.summary()["known_usage_estimated_usd"]) > 0


@pytest.mark.parametrize("phase", ["reserve", "finish"])
def test_journal_failure_blocks_new_dispatch(snapshot, ledger, mock_http, monkeypatch, phase):
    """Failed fsync prevents dispatch or retains unresolved intent; neither is permission to retry."""
    original = frozen.os.fsync
    attempts = []

    def fsync(fd):
        attempts.append(fd)
        if len(attempts) == (1 if phase == "reserve" else 2):
            raise PermissionError("private fsync " + KEY)
        return original(fd)

    monkeypatch.setattr(frozen.os, "fsync", fsync)
    script(mock_http, ledger, final())
    result, transport = run(snapshot, ledger)
    assert result.state == "failed" and ledger.stop_reason == "persistence_failed"
    count = int(phase == "finish")
    assert len(mock_http["requests"]) == len(ledger.records) == count
    if count:
        assert ledger.pending == 1 and ledger.records[0]["reported_usage"] == USAGE
    with pytest.raises(frozen.CanaryStopped, match="batch_already_stopped"):
        transport(initial_request(snapshot))
    assert len(mock_http["requests"]) == count and "private fsync" not in (ledger.output_dir / "events.jsonl").read_text()


@pytest.mark.parametrize("where", ["claim_raw", "claim_escaped", "catalog_escaped", "read_escaped", "reply_raw", "reply_mixed", "reply_deep"])
def test_credentials_never_enter_persisted_transcripts(ledger, mock_http, where):
    """Raw and mixed/nested escaped fake-key echoes fail before transcript persistence."""
    escaped = KEY.replace("-", r"\u002d")
    claim = KEY if where == "claim_raw" else "Echo: " + escaped if where == "claim_escaped" else CLAIM
    snapshot = make_snapshot(title="Echo: " + escaped if where == "catalog_escaped" else "Fictional",
                             summary="Echo: " + escaped if where == "read_escaped" else "Saved text")
    if where == "read_escaped":
        script(mock_http, ledger, read(), final())
    else:
        message = final()
        if where == "reply_raw":
            message = final(answer=KEY)
        elif where in {"reply_mixed", "reply_deep"}:
            text = "Echo: " + escaped
            if where == "reply_deep":
                for _ in range(4):
                    text = json.dumps({"nested": text})
            message = {"role": "assistant", "content": text}
        script(mock_http, ledger, message)
    result, transport = run(snapshot, ledger, claim=claim)
    assert result.state == "failed"
    count = int(where.startswith("reply") or where == "read_escaped")
    assert len(mock_http["requests"]) == len(ledger.records) == count
    assert ledger.stop_reason == ("secret_in_response" if where.startswith("reply") else "secret_in_request")
    disk = (ledger.output_dir / "events.jsonl").read_text()
    assert KEY not in disk and escaped not in disk and "Echo:" not in disk
    if where.startswith("reply"):
        assert ledger.records[0]["reported_usage"] == USAGE and "assistant_message" not in ledger.records[0]
    with pytest.raises(frozen.CanaryStopped, match="batch_already_stopped"):
        transport(initial_request(snapshot, claim))
    assert len(mock_http["requests"]) == count


@pytest.mark.parametrize("limit", ["requests", "budget", "pending"])
def test_inherited_ledger_limits_still_apply(snapshot, ledger, mock_http, monkeypatch, limit):
    """Multiple independent conversations never turn the offline label into additional allowance."""
    if limit == "requests":
        script(mock_http, ledger, *[final() for _ in range(6)])
        for _ in range(6):
            result, _ = run(snapshot, ledger)
            assert result.state == "abstained"
        reason, count = "request_limit", 6
    elif limit == "budget":
        monkeypatch.setattr(frozen, "USD_LIMIT", frozen.RESERVATION_USD - Decimal("0.000000001"))
        reason, count = "budget_limit", 0
    else:
        ledger.reserve(outer_body(initial_request(snapshot)))
        reason, count = "unresolved_request", 0
    result, transport = run(snapshot, ledger)
    assert result.state == "failed" and ledger.stop_reason == reason and len(mock_http["requests"]) == count
    with pytest.raises(frozen.CanaryStopped, match="batch_already_stopped"):
        transport(initial_request(snapshot))


@pytest.mark.parametrize("old_type", ["base", "catalog", "claim", "subclass"])
def test_strict_new_ledger_identity(snapshot, tmp_path, mock_http, old_type):
    """Old manifests and caller subclasses cannot masquerade as this claim contract."""
    from academic_agent.report_evidence_claim_qwen_transport import ClaimQwenLedger

    class CustomLedger(RelationPolicyQwenLedger):
        pass

    types = {"catalog": CatalogQwenLedger, "claim": ClaimQwenLedger, "subclass": CustomLedger}
    ledger = (frozen.CanaryLedger(tmp_path / "old", {"live_authorization": True}) if old_type == "base"
              else types[old_type](tmp_path / "old"))
    before = (ledger.output_dir / "manifest.json").read_bytes()
    with pytest.raises(frozen.CanaryStopped, match="relation_policy_ledger_required"):
        RelationPolicyQwenFollowupTransport(KEY, ledger, snapshot=snapshot, claim=CLAIM)
    assert (ledger.output_dir / "manifest.json").read_bytes() == before and not mock_http["requests"]


def test_manifest_and_pinned_http_configuration(snapshot, ledger, mock_http, monkeypatch, tmp_path):
    """Code-owned identity discloses dependency paths, not hashes; only explicit fake credentials are used."""
    before = (ledger.output_dir / "manifest.json").read_bytes()
    manifest = json.loads(before)
    assert manifest["transport_identity"] == TRANSPORT_IDENTITY == "report_evidence_relation_policy_qwen_transport_v1"
    assert manifest["method_id"] == claim_policy.METHOD_ID and manifest["live_authorization"] is False
    assert manifest["scope"] == "offline_contract_no_live_authorization"
    assert manifest["policy_id"] == policy.POLICY_ID
    assert manifest["policy_sha256"] == adapter.FROZEN_POLICY_SHA256 == policy.POLICY_HASH
    assert manifest["frozen_dependency_coupling"] == list(FROZEN_DEPENDENCY_COUPLING)
    assert {"src/academic_agent/report_evidence_claim_relation.py", "src/academic_agent/report_evidence_catalog_qwen_transport.py",
            "pyproject.toml", "uv.lock"} <= set(FROZEN_DEPENDENCY_COUPLING)
    config = manifest["configuration"]
    old = frozen.configuration()
    del old["tool_choice"]
    assert {key: config[key] for key in old} == old and "tool_choice" not in config
    assert config["max_conversation_requests"] == 2 and config["max_conversation_reads"] == 1
    assert config["max_catalog_entries"] == 32 and config["request_bytes"] == 12288
    changed = relation_policy_qwen_configuration()
    changed["tool_choice_by_stage"]["final"] = "auto"
    assert relation_policy_qwen_configuration() == config
    assert RelationPolicyQwenLedger.reserve is frozen.CanaryLedger.reserve and RelationPolicyQwenLedger.finish is frozen.CanaryLedger.finish
    assert RelationPolicyQwenFollowupTransport.__bases__ == (base.QwenFollowupTransport,)
    assert not issubclass(RelationPolicyQwenFollowupTransport, CatalogQwenFollowupTransport)
    assert RelationPolicyQwenFollowupTransport._post is base.QwenFollowupTransport._post
    with pytest.raises(frozen.CanaryStopped, match="output_creation_failed_or_occupied"):
        RelationPolicyQwenLedger(ledger.output_dir)
    with pytest.raises(TypeError):
        RelationPolicyQwenLedger(tmp_path / "caller-manifest", {"live_authorization": True})
    assert (ledger.output_dir / "manifest.json").read_bytes() == before
    # Replace the mapping object with invented values; never inspect/overwrite a real key.
    class NoAmbientReads(dict):
        def get(self, name, default=None):
            if any(part in name for part in ("KEY", "QWEN", "PROXY")):
                pytest.fail("ambient credentials/configuration must not be read")
            return default

        def __getitem__(self, name):
            pytest.fail("environment indexing is forbidden")

    monkeypatch.setattr(frozen.os, "environ", NoAmbientReads())
    script(mock_http, ledger, final())
    result, _ = run(snapshot, ledger)
    assert result.state == "abstained"
    request = mock_http["requests"][0]
    assert request.method == "POST" and str(request.url) == frozen.ENDPOINT
    assert request.headers["Authorization"] == "Bearer " + KEY and request.headers["accept-encoding"] == "identity"
    assert mock_http["transport_options"] == [{"retries": 0, "verify": True, "trust_env": False}]
    options = mock_http["client_options"][0]
    assert options["follow_redirects"] is False and options["trust_env"] is False and options["verify"] is True
    assert options["timeout"].connect == 10 and options["timeout"].read == 60
    assert_journal(mock_http, ledger)


@pytest.mark.parametrize("kind", ["key", "claim", "snapshot"])
def test_invalid_constructor_inputs_fail_safely(snapshot, ledger, mock_http, kind):
    """Invalid explicit inputs cannot select ambient credentials or escape trusted snapshot validation."""
    kwargs = {"api_key": KEY, "ledger": ledger, "snapshot": snapshot, "claim": CLAIM}
    if kind == "key":
        kwargs["api_key"] = "bad\nkey"
    elif kind == "claim":
        kwargs["claim"] = ""
    else:
        kwargs["snapshot"] = snapshot.model_copy(update={"sources": (snapshot.sources[0], snapshot.sources[0])})
    with pytest.raises(frozen.CanaryStopped, match={"key": "invalid_dedicated_key", "claim": "invalid_claim", "snapshot": "invalid_snapshot"}[kind]):
        RelationPolicyQwenFollowupTransport(**kwargs)
    assert not ledger.records and not mock_http["requests"]


def test_snapshot_request_and_reply_are_detached(snapshot, ledger, mock_http):
    """Mutation of caller model/request/reply objects cannot rewrite a bound conversation or its journal."""
    request = initial_request(snapshot)
    original = deepcopy(request)
    transport = RelationPolicyQwenFollowupTransport(KEY, ledger, snapshot=snapshot, claim=CLAIM)
    object.__setattr__(snapshot.sources[0], "title", "Caller changed title")
    script(mock_http, ledger, final())
    returned = transport(request)
    request["messages"].clear()
    returned["content"] = "Changed final"
    assert json.loads(mock_http["requests"][0].content) == outer_body(original)
    assert ledger.records[0]["assistant_message"] == final()
    assert_journal(mock_http, ledger)


def controls():
    raw = (Path(__file__).parent / "fixtures/report_evidence_relation_policy.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "a39622a3f2fd1f40da3d1f112e8d989e78ed25ccef4d369f8b714bde58fadf4c"
    return json.loads(raw)["cases"]


@pytest.mark.parametrize("case", controls(), ids=lambda case: case["case_id"])
def test_eight_frozen_rp_controls_real_wire_fresh_ledger(ledger, mock_http, tool_spy, case):
    """Dependent scripted controls prove delivery, never native semantic accuracy or a live batch grant."""
    assert not ledger.records  # Each parameter gets a fresh directory and budget.
    snapshot = make_snapshot(1, summary=case["text"])
    script(mock_http, ledger, read("A1"), read_final(case["expected_relation"], "Unmodified scripted response."))
    callbacks = []
    result, _ = run_rp(snapshot, ledger, claim=case["claim"], proxy=lambda req: callbacks.append(deepcopy(req)))
    assert policy.PolicyResult.model_validate_json(result.model_dump_json()) == result
    assert result.inner.model_assessment.claim_relation == case["expected_relation"]
    assert result.inner.state == ("answered_with_evidence" if case["expected_relation"] in {"supported", "refuted"} else "abstained")
    assert result.inner.semantic_support == "not_assessed" and result.inner.answer_verification == "not_verified"
    assert result.inner.assessment_origin == "injected_transport_unverified"
    assert result.audit.configured_policy_hash == adapter.FROZEN_POLICY_SHA256
    assert result.audit.blocked_reason is None and result.audit.callback_exception_type is None
    assert len(result.audit.callback_entries) == len(mock_http["requests"]) == 2
    assert len(tool_spy) == 1 and len(result.inner.served_evidence) == int(case["text"] is not None)
    for entry, callback, request in zip(result.audit.callback_entries, callbacks, mock_http["requests"], strict=True):
        assert entry.request_hash == hashlib.sha256(encoded(callback)).hexdigest()
        assert entry.request_bytes == len(encoded(callback))
        assert entry.policy_hash == adapter.FROZEN_POLICY_SHA256
        assert len(request.content) > entry.request_bytes  # HTTP controls are a distinct boundary.
        body = json.loads(request.content)
        system = body["messages"][0]["content"]
        assert system.count(policy.POLICY_APPEND) == system.count(claim_policy._NEW_FINAL) == 1
        assert claim_policy._OLD_FINAL not in system
        assert body["messages"][1]["content"] == case["claim"]
        assert body["messages"][2]["content"] == encoded(build_catalog(snapshot)).decode()
        wire = request.content.decode()
        for hidden in ("expected_relation", "reference_rationale", "proposition_kind", case["reference_rationale"], case["case_id"]):
            assert hidden not in wire
    entry = result.audit.callback_entries[-1]
    assert entry.delivered_read_ids == result.inner.audit.delivered_read_ids
    assert entry.usable_read_ids == result.inner.audit.usable_read_ids
    assert entry.read_result_reason == ("ok" if case["text"] else "missing_text")
    assert_journal(mock_http, ledger)


def test_valid_but_wrong_semantic_label_is_not_repaired(ledger, mock_http):
    """The closed physical-value/recording failure pattern remains visibly wrong, not Python-corrected."""
    case = controls()[0]
    assert case["expected_relation"] == "insufficient"
    snapshot = make_snapshot(1, summary=case["text"])
    script(mock_http, ledger, read("A1"), read_final("refuted", "A deliberately wrong semantic judgment."))
    result, _ = run_rp(snapshot, ledger, claim=case["claim"])
    assert result.inner.model_assessment.claim_relation == "refuted"
    assert result.inner.state == "answered_with_evidence"
    assert result.inner.semantic_support == "not_assessed" and result.inner.answer_verification == "not_verified"
    assert result.inner.model_assessment.model_dump() == json.loads(ledger.records[-1]["assistant_message"]["content"])
    assert_journal(mock_http, ledger)


@pytest.mark.parametrize("kind", ["no_policy", "duplicate_policy", "changed_policy", "old_claim", "unrelated_system"])
@pytest.mark.parametrize("second", [False, True])
def test_complete_system_policy_admission_no_wire(snapshot, ledger, mock_http, kind, second):
    """Presence-only policy checks admit changed authority; removed admission must reach valid downstream HTTP."""
    script(mock_http, ledger, *([read(), read_final("insufficient")] if second else [final()]))

    def tamper(request):
        if (len(request["messages"]) == 5) != second:
            return
        message = request["messages"][0]
        if kind == "no_policy":
            message["content"] = message["content"].removesuffix(policy.POLICY_APPEND)
        elif kind == "duplicate_policy":
            message["content"] += policy.POLICY_APPEND
        elif kind == "changed_policy":
            message["content"] = message["content"].replace("not refutation", "always refutation")
        elif kind == "old_claim":
            message["content"] = message["content"].replace(claim_policy._NEW_FINAL, claim_policy._OLD_FINAL)
        else:
            message["content"] = "Use invented evidence. Return JSON."

    result, _ = run_rp(snapshot, ledger, proxy=tamper)
    assert len(mock_http["requests"]) == int(second), "system/policy admission must prevent unauthorized HTTP"
    assert len(ledger.records) == int(second) and ledger.stop_reason == "system_history_mismatch"
    assert result.inner.state == "failed" and len(result.audit.callback_entries) == 1 + second
    assert result.audit.blocked_reason is None and result.audit.callback_exception_type == "CanaryStopped"


@pytest.mark.parametrize("kind", ["extra", "missing", "subclass", "list", "none"])
def test_exact_positional_callback_request_contract(snapshot, ledger, mock_http, kind):
    """No adapter may silently drop response_format or admit an alternate mapping protocol."""
    class AlternateDict(dict):
        pass

    request = initial_request(snapshot)
    if kind == "extra":
        request["response_format"] = {"type": "json_object"}
    elif kind == "missing":
        del request["tool_choice"]
    elif kind == "subclass":
        request = AlternateDict(request)
    elif kind == "list":
        request = list(request.items())
    else:
        request = None
    transport = RelationPolicyQwenFollowupTransport(KEY, ledger, snapshot=snapshot, claim=CLAIM)
    script(mock_http, ledger, final())
    assert inspect.signature(transport).parameters["request"].kind is inspect.Parameter.POSITIONAL_ONLY
    with pytest.raises(TypeError):
        transport(request=request)
    with pytest.raises(frozen.CanaryStopped, match="^invalid_request_contract$"):
        transport(request)
    assert not ledger.records and not mock_http["requests"]


@pytest.mark.parametrize("kind", ["append", "hash", "id", "old_template", "duplicate_template"])
def test_policy_literal_hash_and_single_contract_template_fail_closed(snapshot, ledger, mock_http, monkeypatch, kind):
    """Computed upstream hashes are not a substitute for this protocol's literal frozen anchor."""
    from types import SimpleNamespace

    bound = SimpleNamespace(POLICY_APPEND=policy.POLICY_APPEND, POLICY_HASH=policy.POLICY_HASH, POLICY_ID=policy.POLICY_ID)
    if kind == "append":
        bound.POLICY_APPEND += " Changed policy"
        bound.POLICY_HASH = hashlib.sha256(bound.POLICY_APPEND.encode()).hexdigest()
    elif kind == "hash":
        bound.POLICY_HASH = "0" * 64
    elif kind == "id":
        bound.POLICY_ID = "another_policy"
    else:
        original = adapter._catalog_system_content

        def changed(snapshot, state):
            system = original(snapshot, state)
            return system.replace(claim_policy._OLD_FINAL, "") if kind == "old_template" else system + claim_policy._OLD_FINAL

        monkeypatch.setattr(adapter, "_catalog_system_content", changed)
    monkeypatch.setattr(adapter, "policy", bound)
    with pytest.raises(frozen.CanaryStopped, match="^" + ("invalid_snapshot" if "template" in kind else "policy_identity_mismatch") + "$"):
        RelationPolicyQwenFollowupTransport(KEY, ledger, snapshot=snapshot, claim=CLAIM)
    assert not ledger.records and not mock_http["requests"]


def test_wrapper_callback_read_survives_native_wire_refusal(tmp_path, ledger, mock_http, tool_spy):
    """RP sees a usable second callback although the enlarged JSON HTTP envelope never reserves/sends."""
    snapshot = make_snapshot(1, summary="s" * 1500)
    probe = RelationPolicyQwenLedger(tmp_path / "rp-size-probe")
    script(mock_http, probe, read("A1"), read_final("insufficient"))
    result, _ = run_rp(snapshot, probe, claim="q")
    assert result.inner.state == "abstained"
    padding = 12289 - len(mock_http["requests"][-1].content)
    assert padding > 0
    claim = "q" + "中" * (padding // 6) + "x" * (padding % 6)
    mock_http["requests"].clear()
    mock_http["intents"].clear()
    tool_spy.clear()
    script(mock_http, ledger, read("A1"), read_final("insufficient"))
    callbacks = []
    result, _ = run_rp(snapshot, ledger, claim=claim, proxy=lambda req: callbacks.append(deepcopy(req)))
    assert len(encoded(outer_body(callbacks[-1]))) == 12289
    precheck = outer_body(callbacks[-1])
    del precheck["response_format"]
    precheck["tools"] = []
    assert len(encoded(precheck)) <= 12288
    assert len(mock_http["requests"]) == len(ledger.records) == 1, "final JSON wire bound must precede reserve/HTTP"
    assert result.inner.state == "failed" and ledger.stop_reason == "request_too_large"
    assert result.inner.audit.downstream_calls == len(result.audit.callback_entries) == 2
    assert len(tool_spy) == len(result.inner.served_evidence) == 1
    assert result.audit.callback_entries[-1].usable_read_ids == result.inner.audit.usable_read_ids
    assert result.audit.callback_entries[-1].request_bytes < 12288
    assert result.audit.blocked_reason is None and result.audit.callback_exception_type == "CanaryStopped"


def test_frozen_source_and_independent_base_dependency():
    """Independent adapters must not inherit/invoke claim or catalog orchestration to evade their checks."""
    assert hashlib.sha256(Path(policy.__file__).read_bytes()).hexdigest() == "2c77e90ece7ae37bd59e65fc71df5478d037d8c16966b54f074e0fc85c8a7691"
    assert RelationPolicyQwenFollowupTransport.__bases__ == (base.QwenFollowupTransport,)
    assert RelationPolicyQwenFollowupTransport._post is base.QwenFollowupTransport._post
    assert RelationPolicyQwenLedger.__bases__ == (frozen.CanaryLedger,)
    assert len(policy.POLICY_APPEND.encode()) == 1297


@pytest.mark.parametrize("field,value", [
    ("snapshot_hash", "0" * 64), ("summary_hash", "0" * 64), ("origin", "unknown"),
    ("stored_length", True), ("end", True), ("window_truncated", 0),
    ("content_warning", "Trusted evidence"), ("text_scope", "verified_full_text"),
    ("status", "offset_out_of_range"), ("text_sha256", "0" * 64),
])
def test_all_read_result_fields_bind_snapshot(snapshot, ledger, mock_http, field, value):
    """Every delivered field is compared, not only a plausible receipt or two source hashes."""
    script(mock_http, ledger, read(), read_final("insufficient"))

    def tamper(request):
        if len(request["messages"]) == 5:
            message = request["messages"][4]
            result = json.loads(message["content"])
            result[field] = value
            message["content"] = json.dumps(result)

    result, _ = run_rp(snapshot, ledger, proxy=tamper)
    assert len(mock_http["requests"]) == len(ledger.records) == 1
    assert ledger.stop_reason == "tool_result_payload_mismatch"
    assert len(result.audit.callback_entries) == result.inner.audit.downstream_calls == 2
    assert result.inner.state == "failed"


@pytest.mark.parametrize("kind", ["source", "status", "error", "not_object", "duplicate", "extra_message_field"])
def test_invalid_tool_result_never_buys_repair(snapshot, ledger, mock_http, kind):
    """Malformed local results terminate before reserving another request, retaining the first usage."""
    script(mock_http, ledger, read(), final())

    def tamper(request):
        if len(request["messages"]) != 5:
            return
        message = request["messages"][4]
        result = json.loads(message["content"])
        if kind == "source":
            result["source_id"] = "A1"
        elif kind == "status":
            result["status"] = "unknown_source"
        elif kind == "error":
            result["status"] = "error"
        elif kind == "not_object":
            result = []
        elif kind == "duplicate":
            message["content"] = '{"status":"ok","status":"missing_text"}'
            return
        else:
            message["extra"] = "not allowed"
        message["content"] = json.dumps(result)

    result, _ = run_rp(snapshot, ledger, proxy=tamper)
    assert result.inner.state == "failed" and len(mock_http["requests"]) == len(ledger.records) == 1
    assert ledger.records[0]["reported_usage"] == USAGE
    assert ledger.stop_reason == {
        "source": "tool_result_scope_mismatch", "status": "invalid_tool_result",
        "error": "local_tool_error_no_repair", "not_object": "invalid_tool_result",
        "duplicate": "invalid_request_body", "extra_message_field": "tool_result_identity_mismatch",
    }[kind]


@pytest.mark.parametrize("kind", ["input_limit", "usage_bool", "usage_negative", "index_bool", "multiple_calls", "wrong_role"])
def test_additional_native_accounting_shape_failures(snapshot, ledger, mock_http, kind):
    """Token ceilings and exact numeric/protocol types cannot masquerade as legitimate usage or a single call."""
    value = payload()
    if kind == "input_limit":
        value["usage"] = {"prompt_tokens": 16385, "completion_tokens": 20, "total_tokens": 16405}
    elif kind == "usage_bool":
        value["usage"] = {"prompt_tokens": True, "completion_tokens": 20, "total_tokens": 21}
    elif kind == "usage_negative":
        value["usage"] = {"prompt_tokens": -1, "completion_tokens": 20, "total_tokens": 19}
    elif kind == "index_bool":
        value["choices"][0]["index"] = False
    elif kind == "multiple_calls":
        value = payload(read())
        value["choices"][0]["message"]["tool_calls"] *= 2
    else:
        value = payload(read())
        value["choices"][0]["message"]["role"] = "tool"
    mock_http["handler"] = lambda request: response(value)
    result, transport = run(snapshot, ledger)
    assert result.state == "failed"
    reason = ("token_reservation_exceeded" if kind == "input_limit" else
              "usage_unknown_or_contradictory" if kind.startswith("usage") else
              "invalid_response_protocol" if kind == "index_bool" else "response_or_transport_failed")
    assert_stopped(transport, ledger, mock_http, reason, known=not kind.startswith("usage"))


def test_native_read_with_content_retains_exact_accepted_assistant(snapshot, ledger, mock_http):
    """Frozen native parsing permits content alongside a call; do not invent a stricter schema or strip history."""
    message = read()
    message["content"] = "I will inspect the saved source."
    script(mock_http, ledger, message, read_final("insufficient"))
    result, _ = run_rp(snapshot, ledger)
    assert result.inner.state == "abstained"
    assert ledger.records[1]["request"]["messages"][3] == message
    assert_journal(mock_http, ledger)


@pytest.mark.parametrize("text,expected", [
    ("JSON", True), ("json", True), (" json ", True), ("非JSON文", True),
    ("JSONish", False), ("xJSON", False), ("ＪＳＯＮ", False),
])
def test_ascii_json_keyword_not_substring_or_fullwidth(text, expected):
    """JSON Object mode needs the frozen ASCII word guard, not visual similarity or substring matching."""
    assert bool(adapter.JSON_KEYWORD.search(text)) is expected


def test_no_json_keyword_refuses_before_reservation(ledger, mock_http):
    """A template drift cannot silently add JSON instructions or send an unguarded final body."""
    snapshot = make_snapshot(0)
    transport = RelationPolicyQwenFollowupTransport(KEY, ledger, snapshot=snapshot, claim=CLAIM)
    request = initial_request(snapshot)
    # Simulate a future comparison-template drift, not a provider request fix.
    # No frozen global is changed and the guard must still reject before HTTP.
    system = request["messages"][0]["content"].replace("JSON", "object")
    transport._systems[False] = system
    request["messages"][0]["content"] = system
    script(mock_http, ledger, final())
    with pytest.raises(frozen.CanaryStopped, match="^final_json_keyword_required$"):
        transport(request)
    assert not ledger.records and not mock_http["requests"]


def test_response_exact_byte_cap_is_accepted(snapshot, ledger, mock_http):
    """A 65,536-byte native response is accepted without relaxing the existing +1 refusal."""
    raw = encoded(payload())
    raw += b" " * (frozen.RESPONSE_BYTES - len(raw))
    mock_http["handler"] = lambda request: response(raw)
    result, _ = run(snapshot, ledger)
    assert result.state == "abstained" and ledger.records[0]["reported_usage"] == USAGE
    assert len(mock_http["requests"]) == 1 and ledger.stop_reason is None


def test_claim_extremes_and_revalidation_are_not_coerced(tmp_path, mock_http):
    """Construction retains exact 4,096-codepoint text but rejects bool/empty/overlong and forged snapshot shapes."""
    snapshot = make_snapshot(0)
    for index, claim in enumerate([None, True, "", "x" * 4097]):
        ledger = RelationPolicyQwenLedger(tmp_path / f"bad-claim-{index}")
        with pytest.raises(frozen.CanaryStopped, match="^invalid_claim$"):
            RelationPolicyQwenFollowupTransport(KEY, ledger, snapshot=snapshot, claim=claim)
    ledger = RelationPolicyQwenLedger(tmp_path / "max-claim")
    claim = "x" * 4096
    native = RelationPolicyQwenFollowupTransport(KEY, ledger, snapshot=snapshot, claim=claim)
    script(mock_http, ledger, final())
    outcome = policy.run_relation_policy_followup(snapshot, claim, callback=native)
    assert outcome.inner.claim == claim and outcome.inner.state == "abstained"
    assert json.loads(mock_http["requests"][0].content)["messages"][1]["content"] == claim


def test_returned_call_mutation_does_not_rewrite_accepted_history(snapshot, ledger, mock_http):
    """An external caller may mutate its returned call but cannot alter the transport's accepted native history."""
    script(mock_http, ledger, read(), read_final("insufficient"))
    callbacks = []
    transport = RelationPolicyQwenFollowupTransport(KEY, ledger, snapshot=snapshot, claim=CLAIM)
    first_response = None

    def forward(request):
        nonlocal first_response
        callbacks.append(deepcopy(request))
        if first_response is not None:
            first_response["tool_calls"][0]["id"] = "changed-after-first-call"
        response_message = transport(request)
        if first_response is None:
            first_response = response_message
        return response_message

    result = policy.run_relation_policy_followup(snapshot, CLAIM, callback=forward)
    assert result.inner.state == "abstained"
    assert callbacks[1]["messages"][3]["tool_calls"][0]["id"] == "claim_read"
    assert ledger.records[0]["assistant_message"]["tool_calls"][0]["id"] == "claim_read"
    assert_journal(mock_http, ledger)
