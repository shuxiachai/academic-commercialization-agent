"""Mock HTTP at the real client/ledger seam; never authorize a provider request."""

import asyncio
from decimal import Decimal
import hashlib
import json

import httpx
import pytest

from academic_agent.report_evidence_followup import tool_definitions
import academic_agent.report_evidence_qwen_canary as canary
import academic_agent.report_evidence_qwen_transport as transport_module
from academic_agent.report_evidence_qwen_transport import QwenFollowupTransport

KEY = "synthetic-dedicated-key-never-real"


def assistant(content="Synthetic answer."):
    return {"role": "assistant", "content": json.dumps({"answer": content, "status": "answered", "evidence_ids": []})}


def payload(message=None, **overrides):
    message = message or assistant()
    return {"model": canary.MODEL,
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}, **overrides}


def wire_response(value, status=200, headers=None):
    raw = value if isinstance(value, bytes) else json.dumps(value).encode()
    return httpx.Response(status, stream=httpx.ByteStream(raw), headers=headers)


def request_kwargs():
    return {"messages": [{"role": "user", "content": "Synthetic question"}],
            "tools": tool_definitions(), "tool_choice": "auto"}


@pytest.fixture
def ledger(tmp_path):
    return canary.CanaryLedger(tmp_path / "batch", {"mode": "offline_test", "configuration": canary.configuration()})


@pytest.fixture
def mock_http(monkeypatch):
    state = {"requests": [], "transport_options": [], "client_options": [], "handler": None}
    real_client = httpx.AsyncClient

    async def dispatch(request):
        state["requests"].append(request)
        if state["handler"] is None:
            pytest.fail("unexpected HTTP dispatch")
        result = state["handler"](request)
        return await result if asyncio.iscoroutine(result) else result

    def make_transport(**kwargs):
        state["transport_options"].append(kwargs)
        return httpx.MockTransport(dispatch)

    def make_client(**kwargs):
        state["client_options"].append(kwargs)
        return real_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", make_transport)
    monkeypatch.setattr(httpx, "AsyncClient", make_client)
    return state


def test_native_post_is_pinned_reserved_and_secret_free(ledger, mock_http, monkeypatch):
    """Global gateways/keys cannot alter the actual destination or leak into the ledger."""
    for name in ("LLM_PROVIDER", "QWEN_MODEL", "QWEN_API_BASE", "OPENAI_API_KEY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(name, "unrelated-private-value")
    supplied = request_kwargs()

    def respond(request):
        events = [json.loads(line) for line in (ledger.output_dir / "events.jsonl").read_text().splitlines()]
        assert events[-1]["event"] == "request_reserved"
        assert events[-1]["request_sha256"] == hashlib.sha256(request.content).hexdigest()
        assert events[-1]["request"] == json.loads(request.content)
        return wire_response(payload())

    mock_http["handler"] = respond
    message = QwenFollowupTransport(KEY, ledger)(**supplied)
    request = mock_http["requests"][0]
    assert str(request.url) == canary.ENDPOINT and request.method == "POST"
    assert request.headers["Authorization"] == "Bearer " + KEY
    body = json.loads(request.content)
    assert body == {**supplied, "model": "qwen3.5-plus", "stream": False, "enable_thinking": False,
                    "parallel_tool_calls": False, "temperature": 0, "max_tokens": 512}
    assert mock_http["transport_options"] == [{"retries": 0, "verify": True, "trust_env": False}]
    options = mock_http["client_options"][0]
    assert options["follow_redirects"] is False and options["trust_env"] is False and options["verify"] is True
    assert options["timeout"].connect == 10 and options["timeout"].read == 60
    message["content"] = "caller mutation"
    supplied["messages"].clear()
    assert ledger.records[0]["assistant_message"] == assistant()
    assert ledger.records[0]["response_model_matches_authorized"] is True
    assert len(ledger.records[0]["request"]["messages"]) == 1
    assert ledger.summary()["known_usage_estimated_usd"] == "0.0001261"
    disk = (ledger.output_dir / "events.jsonl").read_text()
    assert KEY not in disk and "unrelated-private-value" not in disk and "Authorization" not in disk


@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": 1},
    {"prompt_tokens": True, "completion_tokens": 1, "total_tokens": 2},
    {"prompt_tokens": -1, "completion_tokens": 1, "total_tokens": 0},
    {"prompt_tokens": "1", "completion_tokens": 1, "total_tokens": 2},
    {"prompt_tokens": 1.0, "completion_tokens": 1, "total_tokens": 2},
    {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 3},
])
def test_missing_or_contradictory_usage_stops_and_keeps_reservation(ledger, mock_http, usage):
    """Unknown billing must neither become zero cost nor release budget for another call."""
    mock_http["handler"] = lambda request: wire_response(payload(usage=usage))
    transport = QwenFollowupTransport(KEY, ledger)
    with pytest.raises(canary.CanaryStopped, match="usage_unknown_or_contradictory"):
        transport(**request_kwargs())
    summary = ledger.summary()
    assert summary["request_count"] == summary["unknown_usage_requests"] == 1
    assert Decimal(summary["budget_consumed_usd"]) == canary.RESERVATION_USD
    assert summary["cost_coverage"] == "lower_bound"
    assert summary["known_usage_estimated_usd"] == "0"
    with pytest.raises(canary.CanaryStopped, match="batch_already_stopped"):
        transport(**request_kwargs())
    assert len(mock_http["requests"]) == 1


@pytest.mark.parametrize("model", ["qwen-plus", "qwen3.5-plus-latest", None, "QWEN3.5-PLUS"])
def test_wrong_response_model_stops_but_retains_valid_usage(ledger, mock_http, model):
    """An alias is not the authorized exact response identity, even when it has usage."""
    mock_http["handler"] = lambda request: wire_response(payload(model=model))
    with pytest.raises(canary.CanaryStopped, match="unexpected_response_model"):
        QwenFollowupTransport(KEY, ledger)(**request_kwargs())
    assert ledger.records[0]["usage_status"] == "complete"
    assert Decimal(ledger.summary()["known_usage_estimated_usd"]) > 0
    assert ledger.records[0]["protocol_accepted"] is False
    assert ledger.records[0]["response_model_matches_authorized"] is False


@pytest.mark.parametrize("prompt,completion", [(16385, 20), (100, 513)])
def test_reserved_token_overage_is_charged_then_stops(ledger, mock_http, prompt, completion):
    """The byte-to-token reservation is an estimate; an observed overage is not hidden."""
    usage = {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}
    mock_http["handler"] = lambda request: wire_response(payload(usage=usage))
    with pytest.raises(canary.CanaryStopped, match="token_reservation_exceeded"):
        QwenFollowupTransport(KEY, ledger)(**request_kwargs())
    assert ledger.records[0]["reported_usage"] == usage
    expected = (Decimal(prompt) * canary.INPUT_RATE + Decimal(completion) * canary.OUTPUT_RATE) / 1_000_000
    assert Decimal(ledger.summary()["known_usage_estimated_usd"]) == expected


def test_redirect_is_rejected_without_second_request(ledger, mock_http):
    """A redirected POST would leak a billed intent outside the frozen single destination."""
    def respond(request):
        if len(mock_http["requests"]) == 1:
            return wire_response(b"private redirect body", 307, {"location": "https://outside.invalid/capture"})
        return wire_response(payload())

    mock_http["handler"] = respond
    with pytest.raises(canary.CanaryStopped, match="http_status_rejected"):
        QwenFollowupTransport(KEY, ledger)(**request_kwargs())
    assert len(mock_http["requests"]) == 1
    assert ledger.summary()["unknown_usage_requests"] == 1
    assert "private redirect body" not in (ledger.output_dir / "events.jsonl").read_text()


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_failures_do_not_retry_or_log_body(ledger, mock_http, status):
    """Auth/rate/server errors remain one uncertain dispatch, never a free retry."""
    mock_http["handler"] = lambda request: wire_response(b"sensitive error body", status)
    with pytest.raises(canary.CanaryStopped, match="http_status_rejected"):
        QwenFollowupTransport(KEY, ledger)(**request_kwargs())
    assert len(mock_http["requests"]) == 1 and ledger.summary()["unknown_usage_requests"] == 1
    assert "sensitive" not in (ledger.output_dir / "events.jsonl").read_text()


def test_socket_timeout_is_sanitized_and_not_retried(ledger, mock_http):
    """Transport exception details can contain credentials and cannot become diagnostics."""
    def timeout(request):
        raise httpx.ReadTimeout("sensitive " + KEY)

    mock_http["handler"] = timeout
    with pytest.raises(canary.CanaryStopped, match="request_timeout") as exc:
        QwenFollowupTransport(KEY, ledger)(**request_kwargs())
    assert len(mock_http["requests"]) == 1 and ledger.stop_reason == "request_timeout"
    assert "sensitive" not in str(exc.value) and KEY not in (ledger.output_dir / "events.jsonl").read_text()


def test_total_async_deadline_cancels_owned_request(ledger, mock_http, monkeypatch):
    """A slow HTTP coroutine is cancelled and drained, not abandoned in a background thread."""
    cancelled = []

    async def slow(request):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)
        return wire_response(payload())

    monkeypatch.setattr(transport_module, "TOTAL_SECONDS", 0.01)
    mock_http["handler"] = slow
    with pytest.raises(canary.CanaryStopped, match="request_timeout"):
        QwenFollowupTransport(KEY, ledger)(**request_kwargs())
    assert cancelled == [True] and len(mock_http["requests"]) == 1


@pytest.mark.parametrize("kind", ["oversized", "compressed", "bad_json", "duplicate_key", "nonfinite"])
def test_bounded_response_and_strict_json_fail_closed(ledger, mock_http, kind):
    """Oversized/compressed or ambiguous JSON bodies cannot bypass the bounded read."""
    raw, headers = {
        "oversized": (b"x" * (canary.RESPONSE_BYTES + 1), {}),
        "compressed": (b"not decoded", {"content-encoding": "gzip"}),
        "bad_json": (b"{", {}), "duplicate_key": (b'{"model":"x","model":"y"}', {}),
        "nonfinite": (b'{"usage":NaN}', {}),
    }[kind]
    mock_http["handler"] = lambda request: wire_response(raw, headers=headers)
    with pytest.raises(canary.CanaryStopped):
        QwenFollowupTransport(KEY, ledger)(**request_kwargs())
    assert ledger.summary()["unknown_usage_requests"] == 1 and len(mock_http["requests"]) == 1
    assert ledger.records[0]["response_model_matches_authorized"] is None


def test_request_size_is_checked_before_intent_or_http(ledger, mock_http):
    """An oversized caller request must not consume a paid dispatch or persist its content."""
    request = request_kwargs()
    request["messages"][0]["content"] = "x" * canary.REQUEST_BYTES
    with pytest.raises(canary.CanaryStopped, match="request_too_large"):
        QwenFollowupTransport(KEY, ledger)(**request)
    assert not mock_http["requests"] and not ledger.records


@pytest.mark.parametrize("index", [0, False, -1, 1, "0"])
def test_provider_tool_index_is_validated_then_projected(ledger, mock_http, index):
    """A native provider index is metadata; malformed identities must still fail closed."""
    message = {"role": "assistant", "content": None, "reasoning_content": "provider metadata", "tool_calls": [{
        "index": index, "id": "native_read", "type": "function",
        "function": {"name": "read_source", "arguments": '{"source_id":"A1","offset":0,"length":1500}'},
    }]}
    mock_http["handler"] = lambda request: wire_response(payload(message))
    if type(index) is int and index == 0:
        result = QwenFollowupTransport(KEY, ledger)(**request_kwargs())
        assert "index" not in result["tool_calls"][0] and "reasoning_content" not in result
        assert result["tool_calls"][0]["id"] == "native_read"
    else:
        with pytest.raises(canary.CanaryStopped, match="invalid_response_protocol"):
            QwenFollowupTransport(KEY, ledger)(**request_kwargs())
        assert ledger.records[0]["usage_status"] == "complete"


@pytest.mark.parametrize("kind", ["no_choices", "multi_choices", "wrong_index", "boolean_index", "length", "multi_tools"])
def test_bad_native_shape_keeps_usage_without_accepting_answer(ledger, mock_http, kind):
    """Malformed choices and parallel calls cannot be silently repaired or marked free."""
    response = payload()
    if kind == "no_choices":
        response["choices"] = []
    elif kind == "multi_choices":
        response["choices"] *= 2
    elif kind in {"wrong_index", "boolean_index"}:
        response["choices"][0]["index"] = 1 if kind == "wrong_index" else False
    elif kind == "length":
        response["choices"][0]["finish_reason"] = "length"
    else:
        response["choices"][0]["message"]["tool_calls"] = [{}, {}]
    mock_http["handler"] = lambda request: wire_response(response)
    with pytest.raises(canary.CanaryStopped):
        QwenFollowupTransport(KEY, ledger)(**request_kwargs())
    assert ledger.records[0]["usage_status"] == "complete" and ledger.stop_reason


def test_pre_dispatch_fsync_failure_refuses_http(ledger, mock_http, monkeypatch):
    """An intent not durably committed cannot precede a paid POST."""
    def failed_fsync(fd):
        raise PermissionError("private disk error")

    monkeypatch.setattr(canary.os, "fsync", failed_fsync)
    with pytest.raises(canary.CanaryStopped, match="persistence_failed"):
        QwenFollowupTransport(KEY, ledger)(**request_kwargs())
    assert not mock_http["requests"] and ledger.stop_reason == "persistence_failed"


def test_post_response_fsync_failure_keeps_observed_usage_and_unresolved_intent(ledger, mock_http, monkeypatch):
    """Finalization failure must not erase usage already returned by the HTTP response."""
    original = canary.os.fsync
    calls = []

    def fsync(fd):
        calls.append(fd)
        if len(calls) == 2:
            raise PermissionError("private finalization error")
        return original(fd)

    monkeypatch.setattr(canary.os, "fsync", fsync)
    mock_http["handler"] = lambda request: wire_response(payload())
    with pytest.raises(canary.CanaryStopped, match="persistence_failed"):
        QwenFollowupTransport(KEY, ledger)(**request_kwargs())
    assert ledger.pending == 1 and ledger.stop_reason == "persistence_failed"
    assert ledger.records[0]["reported_usage"]["total_tokens"] == 120
    assert Decimal(ledger.summary()["known_usage_estimated_usd"]) > 0


@pytest.mark.parametrize("key", [None, "", " leading", "trailing ", "a\nb", "a\rb", "a\tb"])
def test_dedicated_key_validation_never_falls_back(ledger, mock_http, key):
    """Missing/whitespace credentials cannot select an ambient legacy key."""
    with pytest.raises(canary.CanaryStopped, match="invalid_dedicated_key"):
        QwenFollowupTransport(key, ledger)
    assert not mock_http["requests"] and not ledger.records


def test_secret_echo_is_never_saved_but_usage_is_retained(ledger, mock_http):
    """Even an unexpected response echo of the bearer secret must not enter artifacts."""
    mock_http["handler"] = lambda request: wire_response(payload(assistant(KEY)))
    with pytest.raises(canary.CanaryStopped, match="secret_in_response"):
        QwenFollowupTransport(KEY, ledger)(**request_kwargs())
    assert ledger.records[0]["usage_status"] == "complete"
    assert KEY not in (ledger.output_dir / "events.jsonl").read_text()


@pytest.mark.parametrize("layer", ["outer_json", "final_envelope", "tool_arguments"])
def test_unicode_escaped_secret_stops_before_message_persistence(ledger, mock_http, layer):
    """Checking only raw HTTP bytes misses a secret decoded from JSON escape sequences."""
    from academic_agent.report_evidence_followup import run_followup
    from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot

    key = "sk-secret"
    encoded_key = r"sk\u002dsecret"
    message = assistant(key)
    if layer == "final_envelope":
        message["content"] = message["content"].replace(key, encoded_key)
    elif layer == "tool_arguments":
        message = {"role": "assistant", "content": None, "tool_calls": [{
            "id": "escaped_key", "type": "function", "function": {
                "name": "lookup_sources", "arguments": '{"query":"' + encoded_key + '"}',
            },
        }]}
    raw = json.dumps(payload(message)).encode()
    if layer == "outer_json":
        raw = raw.replace(key.encode(), encoded_key.encode())
    assert key.encode() not in raw
    mock_http["handler"] = lambda request: wire_response(raw)
    transport = QwenFollowupTransport(key, ledger)
    result = run_followup(ReportEvidenceSnapshot(report_ref="synthetic", sources=()),
                          "Synthetic question", transport=transport)
    assert result.state == "failed" and result.answer is None and not result.evidence_ids
    assert ledger.stop_reason == "secret_in_response" and ledger.records[0]["usage_status"] == "complete"
    assert "assistant_message" not in ledger.records[0]
    assert key not in json.dumps(ledger.records) and key not in result.model_dump_json()
    assert key not in (ledger.output_dir / "events.jsonl").read_text()
    with pytest.raises(canary.CanaryStopped, match="batch_already_stopped") as exc:
        transport(**request_kwargs())
    assert key not in str(exc.value) and len(mock_http["requests"]) == 1
