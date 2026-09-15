"""Offline policy -> native HTTPX bytes -> durable journal boundary controls."""

import asyncio
from copy import deepcopy
from decimal import Decimal
import hashlib
import json

import httpx
import pytest

from academic_agent import report_evidence_followup as core
from academic_agent.report_evidence_guarded_followup import run_policy_followup
import academic_agent.report_evidence_qwen_canary as frozen
import academic_agent.report_evidence_qwen_transport as frozen_transport
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource
from academic_agent.report_evidence_stage_qwen_transport import (
    StageQwenFollowupTransport, StageQwenLedger, TRANSPORT_IDENTITY, stage_configuration,
)

KEY = "sk-offline-secret"
USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}


def final(ids=(), status="answered", answer="Synthetic answer"):
    return {"role": "assistant", "content": json.dumps({
        "answer": answer, "status": status, "evidence_ids": list(ids),
    })}


def call(name="read_source", args=None, call_id="native_read"):
    if args is None:
        args = {"source_id": "A17", "offset": 0, "length": 1500}
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": call_id, "type": "function", "function": {
            "name": name, "arguments": args if isinstance(args, str) else json.dumps(args),
        },
    }]}


def payload(message=None, **overrides):
    message = final() if message is None else message
    return {"model": frozen.MODEL, "usage": deepcopy(USAGE), "choices": [{
        "index": 0, "message": message,
        "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
    }], **overrides}


def response(value, status=200, headers=None):
    raw = value if isinstance(value, bytes) else json.dumps(value).encode()
    return httpx.Response(status, stream=httpx.ByteStream(raw), headers=headers)


def request_kwargs(mode="none"):
    return {"messages": [{"role": "user", "content": "Synthetic question"}],
            "tools": [] if mode == "none" else core.tool_definitions(), "tool_choice": mode}


def read_tools(ids=None):
    tools = [core.tool_definitions()[1]]
    tools[0]["function"]["parameters"]["properties"]["source_id"]["enum"] = ["A17"] if ids is None else ids
    return tools


def events(ledger):
    return [json.loads(line) for line in (ledger.output_dir / "events.jsonl").read_text().splitlines()]


@pytest.fixture
def ledger(tmp_path):
    return StageQwenLedger(tmp_path / "stage")


@pytest.fixture(autouse=True)
def mock_http(monkeypatch):
    state = {"requests": [], "transport_options": [], "client_options": [], "handler": None}
    real_client = httpx.AsyncClient

    def forbid_network(*args, **kwargs):
        pytest.fail("network is forbidden in the stage transport tests")

    async def dispatch(request):
        state["requests"].append(request)
        if state["handler"] is None:
            pytest.fail("unexpected intercepted HTTP request")
        result = state["handler"](request)
        return await result if asyncio.iscoroutine(result) else result

    def make_transport(**kwargs):
        state["transport_options"].append(kwargs)
        return httpx.MockTransport(dispatch)

    def make_client(**kwargs):
        state["client_options"].append(kwargs)
        # Windows ProactorEventLoop needs a real internal socketpair. Block
        # provider HTTP at construction instead of breaking its self-pipe.
        if (not isinstance(kwargs.get("transport"), httpx.MockTransport)
                or kwargs.get("trust_env") is not False
                or kwargs.get("proxy") is not None or kwargs.get("mounts")):
            forbid_network()
        return real_client(**kwargs)

    monkeypatch.setattr(httpx, "Client", forbid_network)
    monkeypatch.setattr(httpx, "HTTPTransport", forbid_network)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", make_transport)
    monkeypatch.setattr(httpx, "AsyncClient", make_client)
    return state


@pytest.fixture
def snapshot():
    return ReportEvidenceSnapshot(report_ref="stage-wire-offline", sources=tuple(
        SnapshotSource(source_id=source_id, group=group, title=title, summary=summary,
                       origin=origin, publisher="Invented control", source_type=group,
                       accessed_date="2026-09-15")
        for source_id, group, title, summary, origin in (
            ("A17", "academic", "Invented greenhouse probe", "The invented probe read 18 units. No field trials. 🙂", "abstract"),
            ("A19", "academic", "Unrelated control", "A separate invented record.", "search_snippet"),
            ("M8", "market", "Invented market record", None, "unknown"),
        )
    ))


@pytest.fixture
def tool_spy(monkeypatch):
    observed = []
    for name in ("lookup_sources", "read_source"):
        original = getattr(core, name)

        def spy(*args, _name=name, _original=original, **kwargs):
            observed.append((_name, deepcopy(kwargs)))
            return _original(*args, **kwargs)

        monkeypatch.setattr(core, name, spy)
    return observed


def script(mock_http, ledger, *replies):
    pending = iter(replies)
    intents = []

    def handle(request):
        # Capture the disk view AT dispatch; assertions below are outside the
        # adapter's deliberate exception-suppression boundary.
        intents.append(events(ledger)[-1])
        item = next(pending)
        message = item(json.loads(request.content)) if callable(item) else item
        return response(payload(message))

    mock_http["handler"] = handle
    return intents


def answer_read(body):
    result = json.loads(body["messages"][-1]["content"])
    return final([result["evidence_id"]], answer=result["text"])


def assert_wire_records(mock_http, ledger, intents):
    assert len(intents) == len(ledger.records) == len(mock_http["requests"])
    for request, intent, record in zip(mock_http["requests"], intents, ledger.records, strict=True):
        assert intent["event"] == "request_reserved"
        assert intent["request"] == record["request"] == json.loads(request.content)
        assert intent["request_sha256"] == record["request_sha256"] == hashlib.sha256(request.content).hexdigest()
        assert intent["usage_status"] == "unknown"
        assert record["usage_status"] == "complete" and record["reported_usage"] == USAGE
    finished = [event for event in events(ledger) if event["event"] == "request_finished"]
    assert [{key: value for key, value in event.items() if key != "event"} for event in finished] == ledger.records


def assert_stopped(transport, ledger, mock_http, reason, count=1, known=True):
    assert ledger.stop_reason == reason and len(mock_http["requests"]) == count
    record = ledger.records[-1]
    assert record["usage_status"] == ("complete" if known else "unknown")
    assert record["protocol_accepted"] is False and "assistant_message" not in record
    if known:
        assert Decimal(ledger.summary()["known_usage_estimated_usd"]) > 0
    else:
        assert Decimal(ledger.summary()["budget_consumed_usd"]) >= frozen.RESERVATION_USD
    with pytest.raises(frozen.CanaryStopped, match="batch_already_stopped"):
        transport(**request_kwargs())
    assert len(mock_http["requests"]) == count


def test_lookup_read_final_preserves_none_wire_schema_ids_and_durable_hash(snapshot, ledger, mock_http, tool_spy):
    """A cooperative final answer cannot hide none -> auto or post-reservation byte mutation."""
    lookup = call("lookup_sources", {"query": "greenhouse"}, "native_lookup")
    native_read = call()
    intents = script(mock_http, ledger, lookup, native_read, answer_read)
    supplied = []
    transport = StageQwenFollowupTransport(KEY, ledger)

    def bridge(**kwargs):
        supplied.append(deepcopy(kwargs))
        return transport(**kwargs)

    result = run_policy_followup(snapshot, "Inspect the invented greenhouse probe", transport=bridge)
    bodies = [json.loads(request.content) for request in mock_http["requests"]]
    assert len(bodies) == 3
    assert bodies[-1]["tool_choice"] == "none"
    assert "tools" not in bodies[-1]
    assert supplied[-1]["tools"] == [] and supplied[-1]["tool_choice"] == "none"
    assert_wire_records(mock_http, ledger, intents)
    assert [body["tools"] for body in bodies[:2]] == [core.tool_definitions(), read_tools()]
    for body, original in zip(bodies, supplied, strict=True):
        expected = {key: value for key, value in original.items() if key != "tools" or original["tool_choice"] != "none"}
        assert {key: body[key] for key in expected} == expected
    assert [body["tool_choice"] for body in bodies] == ["auto", "auto", "none"]
    assert bodies[2]["messages"][2:4] == bodies[1]["messages"][2:4]
    assert bodies[2]["messages"][2] == lookup and bodies[2]["messages"][4] == native_read
    assert [item["tool_call_id"] for item in bodies[2]["messages"] if item["role"] == "tool"] == [
        "native_lookup", "native_read",
    ]
    delivered = json.loads(bodies[2]["messages"][-1]["content"])
    assert result.state == "answered_with_evidence" and result.answer == snapshot.sources[0].summary
    assert delivered["text"] == result.served_evidence[0].text == snapshot.sources[0].summary
    assert delivered["text_sha256"] == result.served_evidence[0].text_sha256
    assert result.evidence_ids == result.audit.forwarded_read_ids == (delivered["evidence_id"],)
    assert [name for name, _ in tool_spy] == ["lookup_sources", "read_source"]
    assert result.audit.core.tool_executions == 2 and result.audit.downstream_calls == 3
    assert result.semantic_support == "not_assessed" and result.answer_verification == "not_verified"
    assert ledger.stop_reason is None and ledger.pending is None


@pytest.mark.parametrize("source_id,missing", [("A17", False), ("M8", True)])
def test_direct_read_and_missing_text_finalize_without_lookup(snapshot, ledger, mock_http, tool_spy, source_id, missing):
    """A missing summary reaches none as explicit absence, never as a successful receipt."""
    native_read = call(args={"source_id": source_id, "offset": 0, "length": 1500})
    intents = script(mock_http, ledger, native_read, final(status="abstained") if missing else answer_read)
    result = run_policy_followup(snapshot, "Inspect a registered synthetic record", transport=StageQwenFollowupTransport(KEY, ledger))
    assert_wire_records(mock_http, ledger, intents)
    body = json.loads(mock_http["requests"][1].content)
    assert body["tool_choice"] == "none" and "tools" not in body
    assert body["messages"][-1]["tool_call_id"] == "native_read"
    assert [name for name, _ in tool_spy] == ["read_source"]
    assert result.state == ("abstained" if missing else "answered_with_evidence")
    delivered = json.loads(body["messages"][-1]["content"])
    if missing:
        assert delivered["status"] == "missing_text" and "evidence_id" not in delivered
        assert not result.evidence_ids and not result.served_evidence
    else:
        assert result.evidence_ids == (delivered["evidence_id"],)


def test_zero_literal_hit_reaches_none_abstention(snapshot, ledger, mock_http, tool_spy):
    """A noncontiguous phrase is still a literal miss, not a fresh lookup opportunity."""
    script(mock_http, ledger, call("lookup_sources", {"query": "greenhouse invented"}, "miss"), final(status="abstained"))
    result = run_policy_followup(snapshot, "Inspect the control", transport=StageQwenFollowupTransport(KEY, ledger))
    body = json.loads(mock_http["requests"][1].content)
    assert "tools" not in body and body["tool_choice"] == "none"
    assert json.loads(body["messages"][-1]["content"])["hits"] == []
    assert result.state == "abstained" and not result.served_evidence
    assert [name for name, _ in tool_spy] == ["lookup_sources"]


@pytest.mark.parametrize("name", ["read_source", "lookup_sources", "fetch_url"])
def test_none_model_toolcall_is_accounted_stopped_before_local_execution(snapshot, ledger, mock_http, tool_spy, name):
    """Rejecting a final-only tool response preserves usage and already-forwarded evidence."""
    script(mock_http, ledger, call(), call(name, {}, "forbidden"))
    transport = StageQwenFollowupTransport(KEY, ledger)
    result = run_policy_followup(snapshot, "Inspect A17", transport=transport)
    assert result.state == "failed" and result.answer is None and not result.evidence_ids
    assert len(result.served_evidence) == 1 and result.audit.forwarded_read_ids
    assert [name for name, _ in tool_spy] == ["read_source"]
    assert_stopped(transport, ledger, mock_http, "unadvertised_tool", count=2)


@pytest.mark.parametrize("reply,reason", [
    (call("lookup_sources", {"query": "probe"}, "again"), "unadvertised_tool"),
    (call(args={"source_id": "A19", "offset": 0, "length": 1}), "read_id_not_permitted"),
    (call(call_id="lookup"), "duplicate_tool_call_id"),
    (call(args='{"source_id":"A17","offset":true,"length":1}'), "invalid_tool_arguments"),
])
def test_hit_stage_response_refusal_has_usage_no_read_or_repair(snapshot, ledger, mock_http, tool_spy, reply, reason):
    """A hit-only declaration is enforced before the real read function and any repair turn."""
    script(mock_http, ledger, call("lookup_sources", {"query": "greenhouse"}, "lookup"), reply)
    transport = StageQwenFollowupTransport(KEY, ledger)
    result = run_policy_followup(snapshot, "Inspect the control", transport=transport)
    assert result.state == "failed" and not result.served_evidence
    assert [name for name, _ in tool_spy] == ["lookup_sources"]
    assert_stopped(transport, ledger, mock_http, reason, count=2)


@pytest.mark.parametrize("mode,tools", [
    ("auto", []), ("none", core.tool_definitions()), ("required", core.tool_definitions()),
    (None, []), (True, []), ({"type": "function"}, []), ("AUTO", core.tool_definitions()),
    ("auto", [core.tool_definitions()[0]]), ("auto", [core.tool_definitions()[1]]),
    ("auto", list(reversed(core.tool_definitions()))), ("auto", None), ("none", ()),
    ("auto", read_tools([])), ("auto", read_tools(["A17", "A17"])),
    ("auto", read_tools([True])), ("auto", read_tools(["other/path"])),
    ("auto", read_tools(["A1", "A2", "A3", "A4", "A5", "A6"])),
    ("auto", read_tools("A17")), ("auto", [{"type": "function", "function": {"name": "dummy"}}]),
])
def test_invalid_mode_or_toolset_never_reserves_or_dispatches(ledger, mock_http, mode, tools):
    """Invalid combinations cannot buy a request, be downgraded to auto or acquire a dummy tool."""
    transport = StageQwenFollowupTransport(KEY, ledger)
    request = {**request_kwargs(), "tool_choice": mode, "tools": tools}
    with pytest.raises(frozen.CanaryStopped, match="invalid_(tool_choice|stage_toolset)"):
        transport(**request)
    assert ledger.stop_reason and not ledger.records and not mock_http["requests"]
    with pytest.raises(frozen.CanaryStopped, match="batch_already_stopped"):
        transport(**request_kwargs())


@pytest.mark.parametrize("kind", ["description", "boolean_bound", "extra_parameter"])
def test_modified_schema_is_not_silently_rebuilt(ledger, mock_http, kind):
    """Dropping unexpected schema fields or accepting True == 1 would broaden the declared contract."""
    tools = core.tool_definitions()
    function = tools[0]["function"]
    if kind == "description":
        function["description"] = "Call another report"
    elif kind == "boolean_bound":
        function["parameters"]["properties"]["query"]["minLength"] = True
    else:
        function["parameters"]["properties"]["url"] = {"type": "string"}
    with pytest.raises(frozen.CanaryStopped, match="invalid_stage_toolset"):
        StageQwenFollowupTransport(KEY, ledger)(**{**request_kwargs("auto"), "tools": tools})
    assert not ledger.records and not mock_http["requests"]


def test_enum_order_is_preserved_and_caller_mutation_detached(ledger, mock_http):
    """Hit IDs remain verbatim; detached history cannot be rewritten after dispatch."""
    supplied = {**request_kwargs("auto"), "tools": read_tools(["A19", "A17"])}
    before = deepcopy(supplied)
    intents = script(mock_http, ledger, final())
    result = StageQwenFollowupTransport(KEY, ledger)(**supplied)
    supplied["tools"].clear()
    supplied["messages"].clear()
    result["content"] = "caller rewrite"
    assert_wire_records(mock_http, ledger, intents)
    body = json.loads(mock_http["requests"][0].content)
    assert body["tools"] == before["tools"] and body["messages"] == before["messages"]
    assert ledger.records[0]["assistant_message"] == final()


def test_pinned_wire_options_and_separate_manifest_identity(ledger, mock_http, monkeypatch):
    """Old auto-only metadata and ambient settings cannot become the new final-only identity."""
    for name in ("LLM_PROVIDER", "QWEN_MODEL", "QWEN_API_BASE", "OPENAI_API_KEY", "DASHSCOPE_API_KEY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(name, "unrelated-synthetic-value")
    mock_http["handler"] = lambda request: response(payload())
    StageQwenFollowupTransport(KEY, ledger)(**request_kwargs())
    request = mock_http["requests"][0]
    assert str(request.url) == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert request.method == "POST" and request.headers["Authorization"] == "Bearer " + KEY
    expected = request_kwargs()
    del expected["tools"]
    assert json.loads(request.content) == {**expected, "model": "qwen3.5-plus", "stream": False,
        "enable_thinking": False, "parallel_tool_calls": False, "temperature": 0, "max_tokens": 512}
    assert mock_http["transport_options"] == [{"retries": 0, "verify": True, "trust_env": False}]
    options = mock_http["client_options"][0]
    assert options["follow_redirects"] is False and options["trust_env"] is False and options["verify"] is True
    assert options["timeout"].connect == 10 and options["timeout"].read == 60
    manifest = json.loads((ledger.output_dir / "manifest.json").read_text())
    assert manifest["transport_identity"] == TRANSPORT_IDENTITY and manifest["live_authorization"] is False
    assert manifest["scope"] == "offline_contract_no_live_authorization"
    config = manifest["configuration"]
    assert "tool_choice" not in config
    assert config["tool_choice_by_stage"] == {"initial": "auto", "read": "auto", "final": "none"}
    original = frozen.configuration()
    assert original.pop("tool_choice") == "auto"
    assert config["final_tools_wire"] == "omitted"
    assert {key: value for key, value in config.items() if key not in {"tool_choice_by_stage", "final_tools_wire"}} == original
    changed = stage_configuration()
    changed["tool_choice_by_stage"]["final"] = "auto"
    assert stage_configuration()["tool_choice_by_stage"]["final"] == "none"
    assert "src/academic_agent/report_evidence_qwen_transport.py" in manifest["frozen_dependency_coupling"]
    disk = (ledger.output_dir / "events.jsonl").read_text()
    assert KEY not in disk and "unrelated-synthetic-value" not in disk and "Authorization" not in disk


@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": 1},
    {"prompt_tokens": True, "completion_tokens": 1, "total_tokens": 2},
    {"prompt_tokens": -1, "completion_tokens": 1, "total_tokens": 0},
    {"prompt_tokens": "1", "completion_tokens": 1, "total_tokens": 2},
    {"prompt_tokens": 1.0, "completion_tokens": 1, "total_tokens": 2},
    {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 3},
])
def test_none_unknown_usage_keeps_reservation_and_stops(ledger, mock_http, usage):
    """Final-only is not a free turn when billing usage is missing or contradictory."""
    mock_http["handler"] = lambda request: response(payload(usage=usage))
    transport = StageQwenFollowupTransport(KEY, ledger)
    with pytest.raises(frozen.CanaryStopped, match="usage_unknown_or_contradictory"):
        transport(**request_kwargs())
    assert_stopped(transport, ledger, mock_http, "usage_unknown_or_contradictory", known=False)


@pytest.mark.parametrize("model", [None, "qwen3.5-plus-latest", "different-provider-model"])
def test_none_wrong_model_retains_accepted_http_usage(ledger, mock_http, model):
    """HTTP 200 from an unauthorized model is accounted, not accepted or retried."""
    mock_http["handler"] = lambda request: response(payload(model=model))
    transport = StageQwenFollowupTransport(KEY, ledger)
    with pytest.raises(frozen.CanaryStopped, match="unexpected_response_model"):
        transport(**request_kwargs())
    assert_stopped(transport, ledger, mock_http, "unexpected_response_model")
    assert ledger.records[0]["response_model_matches_authorized"] is False


@pytest.mark.parametrize("prompt,completion", [(16385, 1), (1, 513)])
def test_observed_token_overage_is_not_hidden(ledger, mock_http, prompt, completion):
    """A reservation breach stops the next request without losing the observed tokens."""
    usage = {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}
    mock_http["handler"] = lambda request: response(payload(usage=usage))
    transport = StageQwenFollowupTransport(KEY, ledger)
    with pytest.raises(frozen.CanaryStopped, match="token_reservation_exceeded"):
        transport(**request_kwargs())
    assert_stopped(transport, ledger, mock_http, "token_reservation_exceeded")
    assert ledger.records[0]["reported_usage"] == usage


@pytest.mark.parametrize("status", [302, 307, 308, 401, 429, 500])
def test_none_redirect_and_http_failures_never_retry(ledger, mock_http, status):
    """A redirect or provider failure stays one uncertain request at the pinned destination."""
    mock_http["handler"] = lambda request: response(b"private body " + KEY.encode(), status,
                                                  {"location": "https://outside.invalid/capture"})
    transport = StageQwenFollowupTransport(KEY, ledger)
    with pytest.raises(frozen.CanaryStopped, match="http_status_rejected"):
        transport(**request_kwargs())
    assert_stopped(transport, ledger, mock_http, "http_status_rejected", known=False)
    assert "private body" not in (ledger.output_dir / "events.jsonl").read_text()


@pytest.mark.parametrize("exception,reason", [
    (httpx.ReadTimeout, "request_timeout"), (httpx.ConnectError, "response_or_transport_failed"),
    (RuntimeError, "response_or_transport_failed"),
])
def test_none_transport_exceptions_are_sanitized_not_retried(ledger, mock_http, exception, reason):
    """Transport exception strings cannot enter public exceptions or the durable transcript."""
    def fail(request):
        raise exception("private failure " + KEY)

    mock_http["handler"] = fail
    transport = StageQwenFollowupTransport(KEY, ledger)
    with pytest.raises(frozen.CanaryStopped, match=reason) as caught:
        transport(**request_kwargs())
    assert_stopped(transport, ledger, mock_http, reason, known=False)
    assert KEY not in str(caught.value) and "private failure" not in (ledger.output_dir / "events.jsonl").read_text()


def test_none_total_deadline_drains_owned_http_operation(ledger, mock_http, monkeypatch):
    """Reusing _post must retain cancellation of the HTTP coroutine, not orphan a thread."""
    drained = []

    async def slow(request):
        try:
            await asyncio.sleep(10)
        finally:
            drained.append(True)
        return response(payload())

    monkeypatch.setattr(frozen_transport, "TOTAL_SECONDS", 0.01)
    mock_http["handler"] = slow
    transport = StageQwenFollowupTransport(KEY, ledger)
    with pytest.raises(frozen.CanaryStopped, match="request_timeout"):
        transport(**request_kwargs())
    assert drained == [True]
    assert_stopped(transport, ledger, mock_http, "request_timeout", known=False)


@pytest.mark.parametrize("raw,headers", [
    (b"x" * (frozen.RESPONSE_BYTES + 1), {}), (b"not decoded", {"content-encoding": "gzip"}),
    (b"{", {}), (b'{"model":"x","model":"y"}', {}), (b'{"usage":NaN}', {}),
    (b"\xff", {}), (b"[]", {}),
], ids=["oversized", "compressed", "bad_json", "duplicate_key", "nonfinite", "invalid_utf8", "non_object"])
def test_none_bad_or_oversized_response_stops_with_unknown_usage(ledger, mock_http, raw, headers):
    """Malformed, compressed or excess response bytes cannot silently pass the bounded reader."""
    mock_http["handler"] = lambda request: response(raw, headers=headers)
    transport = StageQwenFollowupTransport(KEY, ledger)
    with pytest.raises(frozen.CanaryStopped):
        transport(**request_kwargs())
    assert_stopped(transport, ledger, mock_http, ledger.stop_reason, known=False)


@pytest.mark.parametrize("kind", ["no_choices", "multi_choices", "wrong_index", "length", "multi_tools"])
def test_bad_reply_shape_preserves_usage_and_stops(ledger, mock_http, kind):
    """A paid response's invalid native envelope cannot erase usage or permit repair."""
    value = payload()
    if kind == "no_choices":
        value["choices"] = []
    elif kind == "multi_choices":
        value["choices"] *= 2
    elif kind == "wrong_index":
        value["choices"][0]["index"] = False
    elif kind == "length":
        value["choices"][0]["finish_reason"] = "length"
    else:
        value["choices"][0]["message"]["tool_calls"] = [{}, {}]
    mock_http["handler"] = lambda request: response(value)
    transport = StageQwenFollowupTransport(KEY, ledger)
    with pytest.raises(frozen.CanaryStopped):
        transport(**request_kwargs())
    assert_stopped(transport, ledger, mock_http, ledger.stop_reason)


@pytest.mark.parametrize("kind", ["oversized", "bad_body", "local_error"])
def test_invalid_request_fails_before_durable_intent(ledger, mock_http, kind):
    """Request bounds and local-error no-repair rules apply even on a final-only callback."""
    supplied = request_kwargs()
    if kind == "oversized":
        supplied["messages"][0]["content"] = "x" * frozen.REQUEST_BYTES
        reason = "request_too_large"
    elif kind == "bad_body":
        supplied["messages"][0]["content"] = float("nan")
        reason = "invalid_request_body"
    else:
        supplied["messages"].append({"role": "tool", "tool_call_id": "bad", "content": '{"status":"error"}'})
        reason = "local_tool_error_no_repair"
    with pytest.raises(frozen.CanaryStopped, match=reason):
        StageQwenFollowupTransport(KEY, ledger)(**supplied)
    assert not ledger.records and not mock_http["requests"]


@pytest.mark.parametrize("phase", ["before", "after"])
def test_fsync_failure_refuses_dispatch_or_preserves_unresolved_usage(ledger, mock_http, monkeypatch, phase):
    """Neither failed reservation nor failed finalization may be followed by a second POST."""
    original = frozen.os.fsync
    calls = []

    def fsync(fd):
        calls.append(fd)
        if len(calls) == (1 if phase == "before" else 2):
            raise PermissionError("private persistence failure")
        return original(fd)

    monkeypatch.setattr(frozen.os, "fsync", fsync)
    mock_http["handler"] = lambda request: response(payload())
    transport = StageQwenFollowupTransport(KEY, ledger)
    with pytest.raises(frozen.CanaryStopped, match="persistence_failed"):
        transport(**request_kwargs())
    assert ledger.stop_reason == "persistence_failed"
    assert len(mock_http["requests"]) == (0 if phase == "before" else 1)
    if phase == "after":
        assert ledger.pending == 1 and ledger.records[0]["reported_usage"] == USAGE
        assert Decimal(ledger.summary()["known_usage_estimated_usd"]) > 0
    else:
        assert not ledger.records
    with pytest.raises(frozen.CanaryStopped, match="batch_already_stopped"):
        transport(**request_kwargs())
    assert len(mock_http["requests"]) == (0 if phase == "before" else 1)


def test_removed_journal_is_not_recreated_for_dispatch(ledger, mock_http):
    """A missing durable journal is unavailable, not a new empty batch."""
    (ledger.output_dir / "events.jsonl").unlink()
    with pytest.raises(frozen.CanaryStopped, match="persistence_failed"):
        StageQwenFollowupTransport(KEY, ledger)(**request_kwargs())
    assert not mock_http["requests"] and not ledger.records
    assert not (ledger.output_dir / "events.jsonl").exists()


def test_occupied_output_and_old_ledger_are_rejected(ledger, tmp_path, mock_http):
    """The new identity cannot overwrite an occupied journal or reuse an auto-only ledger."""
    before = (ledger.output_dir / "manifest.json").read_bytes()
    with pytest.raises(frozen.CanaryStopped, match="output_creation_failed_or_occupied"):
        StageQwenLedger(ledger.output_dir)
    assert (ledger.output_dir / "manifest.json").read_bytes() == before
    old = frozen.CanaryLedger(tmp_path / "old", {"configuration": frozen.configuration()})
    with pytest.raises(frozen.CanaryStopped, match="stage_ledger_required"):
        StageQwenFollowupTransport(KEY, old)
    assert not mock_http["requests"]


@pytest.mark.parametrize("limit", ["requests", "budget", "pending"])
def test_request_budget_and_pending_limits_apply_before_http(ledger, mock_http, monkeypatch, limit):
    """Empty tools never bypass the shared count, conservative reservation or unresolved intent."""
    transport = StageQwenFollowupTransport(KEY, ledger)
    mock_http["handler"] = lambda request: response(payload())
    if limit == "requests":
        for _ in range(frozen.MAX_REQUESTS):
            transport(**request_kwargs())
        reason, count = "request_limit", 6
    elif limit == "budget":
        transport(**request_kwargs())
        monkeypatch.setattr(frozen, "USD_LIMIT", frozen.RESERVATION_USD)
        reason, count = "budget_limit", 1
    else:
        ledger.reserve(request_kwargs())
        reason, count = "unresolved_request", 0
    with pytest.raises(frozen.CanaryStopped, match=reason):
        transport(**request_kwargs())
    assert ledger.stop_reason == reason and len(mock_http["requests"]) == count
    with pytest.raises(frozen.CanaryStopped, match="batch_already_stopped"):
        transport(**request_kwargs())
    assert len(mock_http["requests"]) == count


@pytest.mark.parametrize("key", [None, "", " leading", "a\nb", "a\rb", "a\tb", "x" * 513])
def test_invalid_dedicated_key_never_falls_back(ledger, mock_http, key):
    """Invalid explicit credentials cannot select any ambient provider identity."""
    with pytest.raises(frozen.CanaryStopped, match="invalid_dedicated_key"):
        StageQwenFollowupTransport(key, ledger)
    assert not ledger.records and not mock_http["requests"]


@pytest.mark.parametrize("layer", ["raw", "outer_json", "final_envelope", "tool_arguments"])
def test_raw_and_escaped_secret_echo_never_reaches_core_or_journal(snapshot, ledger, mock_http, tool_spy, layer):
    """Decoded nested JSON secrets are suppressed before response persistence or local execution."""
    escaped = KEY.replace("-", r"\u002d")
    message = final(answer=KEY)
    if layer == "final_envelope":
        message["content"] = message["content"].replace(KEY, escaped)
    elif layer == "tool_arguments":
        message = call("lookup_sources", '{"query":"' + escaped + '"}')
    raw = json.dumps(payload(message)).encode()
    if layer == "outer_json":
        raw = raw.replace(KEY.encode(), escaped.encode())
    if layer != "raw":
        assert KEY.encode() not in raw
    mock_http["handler"] = lambda request: response(raw)
    transport = StageQwenFollowupTransport(KEY, ledger)
    result = run_policy_followup(snapshot, "Synthetic question", transport=transport)
    assert result.state == "failed" and not result.evidence_ids and not result.served_evidence and not tool_spy
    assert_stopped(transport, ledger, mock_http, "secret_in_response")
    assert KEY not in result.model_dump_json() and KEY not in json.dumps(ledger.records)
    disk = (ledger.output_dir / "events.jsonl").read_text()
    assert KEY not in disk and escaped not in disk


@pytest.mark.parametrize("escaped", [False, True])
def test_secret_in_request_is_refused_before_transcript_persistence(ledger, mock_http, escaped):
    """Even an accidental caller-supplied secret must not be persisted as a request intent."""
    supplied = request_kwargs()
    supplied["messages"][0]["content"] = json.dumps({"answer": KEY})
    if escaped:
        supplied["messages"][0]["content"] = supplied["messages"][0]["content"].replace(KEY, KEY.replace("-", r"\u002d"))
    with pytest.raises(frozen.CanaryStopped, match="secret_in_request"):
        StageQwenFollowupTransport(KEY, ledger)(**supplied)
    assert not ledger.records and not mock_http["requests"]
    assert KEY not in (ledger.output_dir / "events.jsonl").read_text()
