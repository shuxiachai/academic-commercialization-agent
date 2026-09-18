"""Fresh fake-key engineering controls; no live Qwen or selection-quality claims."""

from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from academic_agent import report_evidence_qwen_canary as base
from academic_agent import report_evidence_source_locator as locator
from academic_agent import report_evidence_source_locator_qwen_transport as adapter
from academic_agent.report_evidence_catalog_followup import build_catalog
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource

KEY = "sk-locator-offline-fictional-credential"
QUESTION = " \nLocate the synthetic spool note 🌿.\t "
USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}


def snapshot(text="  Synthetic saved spool text 🌿 e\u0301 <b>inert</b>\n", *, count=1, title="Synthetic spool 界"):
    return ReportEvidenceSnapshot(report_ref="private-synthetic-locator-reference", sources=tuple(
        SnapshotSource(source_id=f"A{index + 101}", group="academic", title=title,
                       publisher="Private synthetic publisher", source_type="control",
                       accessed_date="2026-09-18", summary=text)
        for index in range(count)))


def request_for(snap=None, question=QUESTION):
    return locator._request(question, build_catalog(snapshot() if snap is None else snap))


def call(arguments='{"source_id":"A101"}', *, content=None, name="read_source"):
    return {"role": "assistant", "content": content, "tool_calls": [{
        "id": "fictional_locator_call", "type": "function",
        "function": {"name": name, "arguments": arguments},
    }]}


def payload(message=None):
    message = call() if message is None else message
    return {"model": "qwen3.5-plus", "usage": dict(USAGE), "choices": [{
        "index": 0, "message": message,
        "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
    }]}


def events(ledger):
    return [json.loads(line) for line in (ledger.output_dir / "events.jsonl").read_text().splitlines()]


def journal_text(ledger):
    return "".join(path.read_text() for path in ledger.output_dir.iterdir())


def make_transport(state, snap=None, question=QUESTION):
    return adapter.LocatorQwenTransport(KEY, state.ledger, snapshot=snapshot() if snap is None else snap, question=question)


def run(state, snap=None, question=QUESTION):
    snap = snapshot() if snap is None else snap
    transport = make_transport(state, snap, question)
    result = locator.locate_saved_source(snap, question, selector=transport)
    return result, transport


@pytest.fixture
def offline(monkeypatch, tmp_path):
    """Intercept the inherited HTTP primitive; preserve real fsync and real read."""
    state = SimpleNamespace(requests=[], reads=[], client_options=[], transport_options=[],
                            fsynced=[], intents=[], response=payload(), raw=None,
                            status=200, headers={}, exception=None)
    state.ledger = adapter.LocatorQwenLedger(tmp_path / "locator")
    real_client, real_read, real_fsync = httpx.AsyncClient, locator.read_source, os.fsync

    def fsync(fd):
        real_fsync(fd)
        state.fsynced.append(deepcopy(events(state.ledger)))

    def dispatch(request):
        state.requests.append(request)
        # Record observations instead of asserting the expected ordinal here:
        # a cap-bypass mutation must reach a valid second intercepted reply.
        state.intents.append((deepcopy(events(state.ledger)), deepcopy(state.fsynced)))
        if state.exception is not None:
            raise state.exception
        raw = adapter._encoded(state.response) if state.raw is None else state.raw
        return httpx.Response(state.status, headers=state.headers, stream=httpx.ByteStream(raw))

    def transport(**kwargs):
        state.transport_options.append(kwargs)
        return httpx.MockTransport(dispatch)

    def client(**kwargs):
        assert isinstance(kwargs["transport"], httpx.MockTransport)
        state.client_options.append(kwargs)
        return real_client(**kwargs)

    def read(*args, **kwargs):
        state.reads.append((args, kwargs))
        return real_read(*args, **kwargs)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setattr(locator, "read_source", read)
    return state


def test_real_wrapper_http_fsynced_intent_local_read_json(offline, monkeypatch):
    """A callback-only mock or a POST-before-reserve change cannot satisfy this seam."""
    snap = snapshot()
    monkeypatch.setenv("QWEN_API_KEY", "ambient-key-must-not-be-used")
    monkeypatch.setenv("OPENAI_API_KEY", "another-ambient-key-must-not-be-used")
    result, transport = run(offline, snap)
    delivered = json.loads(locator.render_locator_result(result))
    assert delivered["state"] == "excerpt"
    assert delivered["saved_text"]["text"] == snap.sources[0].summary
    assert delivered["selection_relevance"] == delivered["semantic_support"] == "not_assessed"
    assert delivered["callback_entries"] == delivered["read_attempts"] == delivered["read_completed"] == 1
    assert len(offline.requests) == len(offline.reads) == 1
    args, kwargs = offline.reads[0]
    assert args[1:] == ("A101", 0, 1500) and kwargs == {}
    assert args[0] is not snap and args[0].model_dump() == snap.model_dump()
    expected = {**request_for(snap), "model": "qwen3.5-plus", "stream": False,
                "enable_thinking": False, "parallel_tool_calls": False, "temperature": 0, "max_tokens": 512}
    request = offline.requests[0]
    wire = adapter._encoded(expected)
    assert request.content == wire
    assert b"\\ud83c" in wire and b"\\u754c" in wire
    assert request.url == base.ENDPOINT and request.method == "POST"
    assert request.headers["authorization"] == "Bearer " + KEY
    assert request.headers["accept-encoding"] == "identity"
    assert request.headers["content-type"] == "application/json"
    assert len(wire) <= 12288
    record = offline.ledger.records[0]
    assert record["request"] == expected
    assert record["request_sha256"] == hashlib.sha256(wire).hexdigest()
    at_post, fsync_at_post = offline.intents[0]
    assert [item["event"] for item in at_post] == ["request_reserved"]
    assert fsync_at_post == [at_post]
    assert at_post[0]["request_sha256"] == record["request_sha256"]
    assert at_post[0]["request"] == expected
    assert [event["event"] for event in events(offline.ledger)] == ["request_reserved", "request_finished"]
    assert record["reported_usage"] == USAGE and record["protocol_accepted"] is True
    assert record["provider_response_received"] is True and record["response_model_matches_authorized"] is True
    assert "assistant_message" not in record
    text = journal_text(offline.ledger)
    for private in (KEY, "private-synthetic-locator-reference", "Private synthetic publisher", "Synthetic saved spool"):
        assert private not in text
    assert transport._post.__func__ is adapter.QwenFollowupTransport._post
    assert offline.transport_options == [{"retries": 0, "verify": True, "trust_env": False}]
    options = offline.client_options[0]
    assert options["verify"] is True and options["trust_env"] is options["follow_redirects"] is False
    assert options["timeout"].connect == 10 and options["timeout"].read == 60
    assert offline.ledger.summary()["price_scope"] == "frozen_conservative_estimate_not_invoice"


@pytest.mark.parametrize(("text", "state", "reads"), [
    (None, "missing_text", 1), ("", "missing_text", 1), (" \t\n", "blank_text", 1),
    ("界" * 1500, "excerpt", 1), ("界" * 1501, "out_of_scope", 0),
])
def test_saved_text_outcomes_never_send_text_or_second_request(offline, text, state, reads):
    """Missing/blank/overlong saved data are not repaired with another model turn."""
    result, transport = run(offline, snapshot(text))
    assert result.state == state and len(offline.reads) == reads
    assert len(offline.requests) == 1
    assert result.read_attempts == result.read_completed == reads
    if state in {"blank_text", "excerpt"}:
        assert json.loads(locator.render_locator_result(result))["saved_text"]["text"] == text
    with pytest.raises(base.CanaryStopped, match="^conversation_closed$"):
        transport(request_for(snapshot(text)))
    assert len(offline.requests) == 1


@pytest.mark.parametrize("message", [
    {"role": "assistant", "content": '{"action":"decline"}'},
    {"role": "assistant", "content": None, "refusal": "Arbitrary refusal PROSE_DO_NOT_PERSIST 界"},
])
def test_decline_and_refusal_stay_no_read_no_prose_journal(offline, message):
    """A valid refusal may return in memory but its free prose must never be saved."""
    offline.response = payload(message)
    result, _ = run(offline)
    assert result.state == "declined" and result.read_attempts == 0
    assert len(offline.requests) == 1 and offline.reads == []
    assert offline.ledger.records[0]["protocol_accepted"] is True
    assert "PROSE_DO_NOT_PERSIST" not in journal_text(offline.ledger)
    assert "assistant_message" not in offline.ledger.records[0]


def test_refusal_return_is_unchanged_in_memory(offline):
    """Safe return data are not replaced by an invented canonical refusal."""
    message = {"role": "assistant", "refusal": "Standalone arbitrary refusal.", "content": None}
    offline.response = payload(message)
    assert make_transport(offline)(request_for()) == message
    assert message["refusal"] not in journal_text(offline.ledger)


def test_empty_snapshot_no_callback_and_direct_empty_entry_stops(offline):
    """The empty catalog cannot become a native-call opportunity."""
    snap = snapshot(count=0)
    result, transport = run(offline, snap)
    assert result.state == "no_sources" and result.callback_entries == 0
    with pytest.raises(base.CanaryStopped, match="^empty_catalog$"):
        transport(request_for(snap))
    assert offline.requests == [] and offline.ledger.records == []
    assert offline.ledger.stop_reason == "empty_catalog"


@pytest.mark.parametrize("part", ["system", "question", "catalog", "enum", "schema", "choice", "model", "extra", "type"])
def test_request_identity_tamper_stops_before_any_reservation(offline, part):
    """Bypassing complete request identity must dispatch and turn this test red."""
    transport = make_transport(offline)
    peer = make_transport(offline)
    request = request_for()
    if part in {"system", "question", "catalog"}:
        request["messages"][{"system": 0, "question": 1, "catalog": 2}[part]]["content"] += " changed"
    elif part == "enum":
        request["tools"][0]["function"]["parameters"]["properties"]["source_id"]["enum"] = ["A102"]
    elif part == "schema":
        request["tools"][0]["function"]["parameters"]["additionalProperties"] = 0  # False != JSON 0.
    elif part == "choice":
        request["tool_choice"] = "required"
    elif part in {"model", "extra"}:
        request[part] = "unbound"
    else:
        request = []
    with pytest.raises(base.CanaryStopped):
        transport(request)
    assert transport._attempted is True
    assert offline.requests == [] and offline.ledger.records == []
    assert [event["event"] for event in events(offline.ledger)] == ["batch_stopped"]
    with pytest.raises(base.CanaryStopped, match="^batch_already_stopped$"):
        peer(request_for())
    with pytest.raises(base.CanaryStopped, match="^fresh_locator_ledger_required$"):
        make_transport(offline)
    assert offline.requests == []


def test_binding_detaches_before_caller_mutation(offline):
    """A frozen model is not enough: object-level mutation must not change binding."""
    snap = snapshot()
    expected = request_for(snap)
    transport = make_transport(offline, snap)
    object.__setattr__(snap.sources[0], "title", "Changed after construction")
    assert transport(expected) == call()
    assert json.loads(offline.requests[0].content)["messages"] == expected["messages"]
    assert transport._snapshot.sources[0] is not snap.sources[0]


@pytest.mark.parametrize("over", [False, True])
def test_exact_complete_wire_size_and_callback_gap(offline, over):
    """A callback below 12 KiB must still fail when fixed native controls exceed it."""
    snap = snapshot()
    base_request = request_for(snap, "q")
    controls = {"model": "qwen3.5-plus", "stream": False, "enable_thinking": False,
                "parallel_tool_calls": False, "temperature": 0, "max_tokens": 512}
    remaining = 12288 - len(adapter._encoded({**base_request, **controls})) + int(over)
    question = "q" + "界" * (remaining // 6) + "x" * (remaining % 6)
    request = request_for(snap, question)
    assert len(question) <= 4096 and len(adapter._encoded(request)) <= 12288
    assert len(adapter._encoded({**request, **controls})) == 12288 + int(over)
    result, _ = run(offline, snap, question)
    assert result.callback_entries == 1
    assert result.state == ("unavailable" if over else "excerpt")
    assert len(offline.requests) == int(not over)
    if over:
        assert offline.ledger.stop_reason == "request_too_large" and offline.ledger.records == []
    else:
        assert len(offline.requests[0].content) == 12288


def test_shared_ledger_cap_independent_of_constructor(offline):
    """Two preconstructed transports expose a ledger cap bypass, not a ctor check."""
    first, second = make_transport(offline), make_transport(offline)
    assert first(request_for()) == call()
    assert offline.ledger.stop_reason is None and offline.ledger.pending is None
    with pytest.raises(base.CanaryStopped, match="^request_limit$"):
        second(request_for())
    assert len(offline.requests) == len(offline.ledger.records) == 1
    assert offline.ledger.stop_reason == "request_limit"


def test_ledger_reserve_itself_rejects_second_request(offline):
    """Direct reservation cannot reuse the inherited six-request allowance."""
    transport = make_transport(offline)
    transport(request_for())
    with pytest.raises(base.CanaryStopped, match="^request_limit$"):
        offline.ledger.reserve(offline.ledger.records[0]["request"])
    assert len(offline.ledger.records) == 1


@pytest.mark.parametrize("failure", ["invalid_response", "timeout", "invalid_request"])
def test_shared_ledger_failure_cannot_be_repaired(offline, failure):
    """A stopped ledger rejects an already constructed peer after any first failure."""
    first, second = make_transport(offline), make_transport(offline)
    request = request_for()
    if failure == "invalid_response":
        offline.response = payload(call('{"source_id":"A999"}'))
    elif failure == "timeout":
        offline.exception = httpx.ReadTimeout("private error " + KEY)
    else:
        request["messages"][1]["content"] += " tampered"
    with pytest.raises(base.CanaryStopped):
        first(request)
    count = len(offline.requests)
    with pytest.raises(base.CanaryStopped, match="^batch_already_stopped$"):
        second(request_for())
    with pytest.raises(base.CanaryStopped, match="^fresh_locator_ledger_required$"):
        make_transport(offline)
    assert len(offline.requests) == count == int(failure != "invalid_request")
    assert KEY not in journal_text(offline.ledger)


def test_reserve_fsync_failure_means_zero_dispatch(offline, monkeypatch):
    """POST-before-reserve must be observable even when fsync fails before dispatch."""
    transport = make_transport(offline)
    with monkeypatch.context() as scoped:
        scoped.setattr(os, "fsync", Mock(side_effect=OSError("unsafe fsync " + KEY)))
        with pytest.raises(base.CanaryStopped, match="^persistence_failed$"):
            transport(request_for())
    assert offline.requests == [] and offline.ledger.records == []
    assert offline.ledger.stop_reason == "persistence_failed"
    with pytest.raises(base.CanaryStopped):
        make_transport(offline)
    assert KEY not in journal_text(offline.ledger)


def test_finish_fsync_failure_remains_spent_pending(offline, monkeypatch):
    """Finalization loss must not refund an observed request or drop valid usage."""
    first, second = make_transport(offline), make_transport(offline)
    real_fsync = os.fsync
    count = 0

    def fail_finish(fd):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("unsafe finalization " + KEY)
        real_fsync(fd)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "fsync", fail_finish)
        with pytest.raises(base.CanaryStopped, match="^persistence_failed$"):
            first(request_for())
    assert len(offline.requests) == 1 and offline.ledger.pending == 1
    assert offline.ledger.stop_reason == "persistence_failed"
    assert offline.ledger.records[0]["reported_usage"] == USAGE
    summary = offline.ledger.summary()
    assert summary["pending_request_id"] == 1
    assert Decimal(summary["budget_consumed_usd"]) >= base.RESERVATION_USD
    with pytest.raises(base.CanaryStopped):
        second(request_for())
    assert len(offline.requests) == 1


BAD_MESSAGES = [
    call('{"source_id":"A999"}'), call('{"source_id":"A101","offset":0}'),
    call('{"source_id":"A101","source_id":"A101"}'), call('{"source_id":101}'),
    call('{"source_id":"A101"}', content="Generated PROSE_DO_NOT_PERSIST"),
    call(name="lookup_sources"), call('[]'), call('NaN'), call("x" * (adapter.MAX_ARGUMENT_CHARS + 1)),
    {"role": "assistant", "content": '{"action":"decline","reason":"PROSE_DO_NOT_PERSIST"}'},
    {"role": "assistant", "content": '{"action":"decline","action":"decline"}'},
    {"role": "assistant", "content": "An arbitrary answer PROSE_DO_NOT_PERSIST"},
    {"role": "assistant", "content": "", "tool_calls": []},
    {**call(), "refusal": "Refusal cannot accompany a call"},
    {"role": "assistant", "content": "mixed", "refusal": "refusal"},
    {**call(), "tool_calls": call()["tool_calls"] * 2},
    {**call(), "tool_calls": [{**call()["tool_calls"][0], "type": "custom"}]},
    {**call(), "tool_calls": [{**call()["tool_calls"][0], "extra": True}]},
    {**call(), "tool_calls": [{**call()["tool_calls"][0], "function": {
        **call()["tool_calls"][0]["function"], "extra": True}}]},
]


@pytest.mark.parametrize("message", BAD_MESSAGES)
def test_invalid_selection_preserves_usage_without_read_or_response_journal(offline, message):
    """Bad choices are rejected without erasing a real coherent usage observation."""
    offline.response = payload(message)
    result, _ = run(offline)
    assert result.state == "unavailable" and offline.reads == []
    assert len(offline.requests) == 1
    record = offline.ledger.records[0]
    assert record["reported_usage"] == USAGE and record["usage_status"] == "complete"
    assert record["protocol_accepted"] is False and offline.ledger.stop_reason is not None
    assert "assistant_message" not in record and "PROSE_DO_NOT_PERSIST" not in journal_text(offline.ledger)


@pytest.mark.parametrize("usage", [None, {}, {**USAGE, "prompt_tokens": True},
    {**USAGE, "completion_tokens": -1}, {**USAGE, "total_tokens": 121},
    {**USAGE, "total_tokens": 120.0}, {**USAGE, "prompt_tokens": 1_000_000_001}])
def test_invalid_usage_is_unknown_and_reserved_not_free(offline, usage):
    """Absent, boolean or contradictory token counts must never become zero cost."""
    offline.response["usage"] = usage
    result, _ = run(offline)
    assert result.state == "unavailable" and offline.reads == []
    record = offline.ledger.records[0]
    assert record["usage_status"] == "unknown" and "reported_usage" not in record
    assert record["error"] == "usage_unknown_or_contradictory"
    summary = offline.ledger.summary()
    assert summary["unknown_usage_requests"] == 1 and summary["cost_coverage"] == "lower_bound"
    assert Decimal(summary["budget_consumed_usd"]) >= base.RESERVATION_USD


@pytest.mark.parametrize("fault", ["model", "input_limit", "output_limit", "finish", "index", "choices"])
def test_native_protocol_faults_keep_known_usage(offline, fault):
    """Model, token ceilings and finish reason are independent of valid selection JSON."""
    if fault == "model":
        offline.response["model"] = "qwen3.5-plus-other"
    elif fault in {"input_limit", "output_limit"}:
        prompt, completion = (16385, 20) if fault == "input_limit" else (100, 513)
        offline.response["usage"] = {"prompt_tokens": prompt, "completion_tokens": completion,
                                     "total_tokens": prompt + completion}
    elif fault == "finish":
        offline.response["choices"][0]["finish_reason"] = "stop"
    elif fault == "index":
        offline.response["choices"][0]["index"] = True
    else:
        offline.response["choices"] *= 2
    result, _ = run(offline)
    assert result.state == "unavailable" and offline.reads == []
    assert offline.ledger.records[0]["reported_usage"] == offline.response["usage"]
    assert offline.ledger.records[0]["protocol_accepted"] is False


def escaped_key():
    return "".join(f"\\u{ord(char):04x}" for char in KEY)


@pytest.mark.parametrize("location", ["question", "title", "arguments", "refusal", "provider_metadata"])
@pytest.mark.parametrize("encoded", [False, True])
def test_secret_echo_scanned_before_journal_and_reply(offline, location, encoded):
    """Recoverable mixed-prose escapes must not leak through metadata or refusals."""
    secret = "prefix " + (escaped_key() if encoded else KEY) + " suffix"
    snap, question = snapshot(), QUESTION
    is_request = location in {"question", "title"}
    if location == "question":
        question = secret
    elif location == "title":
        snap = snapshot(title=secret)
    elif location == "arguments":
        offline.response = payload(call(json.dumps({"source_id": secret})))
    elif location == "refusal":
        offline.response = payload({"role": "assistant", "refusal": secret})
    else:
        offline.response["provider_metadata"] = secret
    result, _ = run(offline, snap, question)
    assert result.state == "unavailable" and offline.reads == []
    assert len(offline.requests) == int(not is_request)
    assert offline.ledger.stop_reason == ("secret_in_request" if is_request else "secret_in_response")
    text = journal_text(offline.ledger)
    assert KEY not in text and "prefix" not in text
    if not is_request:
        assert offline.ledger.records[0]["reported_usage"] == USAGE
    else:
        assert offline.ledger.records == []


@pytest.mark.parametrize("kind", ["stopped", "runtime", "str_bomb"])
def test_arbitrary_exception_text_never_crosses_boundary(offline, kind):
    """Even a shared stop exception is not authority to persist its message."""
    class StringBomb(base.CanaryStopped):
        def __str__(self):
            raise AssertionError("Exception stringification is forbidden")

    cls = {"stopped": base.CanaryStopped, "runtime": RuntimeError, "str_bomb": StringBomb}[kind]
    offline.exception = cls("PRIVATE_ERROR " + KEY)
    with pytest.raises(base.CanaryStopped, match="^response_or_transport_failed$") as caught:
        make_transport(offline)(request_for())
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    assert "PRIVATE_ERROR" not in journal_text(offline.ledger) and KEY not in journal_text(offline.ledger)
    assert offline.ledger.records[0]["usage_status"] == "unknown"


@pytest.mark.parametrize(("fault", "reason"), [
    ("http", "http_status_rejected"), ("encoding", "response_encoding_rejected"),
    ("oversize", "response_too_large"), ("timeout", "request_timeout"),
    ("duplicate_json", "response_or_transport_failed"), ("invalid_utf8", "response_or_transport_failed"),
])
def test_inherited_http_guards_no_retry_no_body_diagnostics(offline, fault, reason):
    """Intercepted raw HTTP still exercises the pinned stream/deadline/parser guards."""
    if fault == "http":
        offline.status, offline.raw = 302, ("PRIVATE_HTTP " + KEY).encode()
    elif fault == "encoding":
        offline.headers = {"content-encoding": "gzip"}
    elif fault == "oversize":
        offline.raw = b"x" * (65536 + 1)
    elif fault == "timeout":
        offline.exception = httpx.ConnectTimeout("PRIVATE_HTTP " + KEY)
    elif fault == "duplicate_json":
        offline.raw = b'{"model":"qwen3.5-plus","model":"qwen3.5-plus"}'
    else:
        offline.raw = b"\xff"
    with pytest.raises(base.CanaryStopped, match="^" + reason + "$"):
        make_transport(offline)(request_for())
    assert len(offline.requests) == 1 and offline.ledger.stop_reason == reason
    assert offline.ledger.records[0]["usage_status"] == "unknown"
    assert "PRIVATE_HTTP" not in journal_text(offline.ledger)


def test_manifest_creation_freshness_and_constructor_no_io(offline, tmp_path, monkeypatch):
    """The dedicated ledger writes once; transport construction never writes or resolves keys."""
    manifest = json.loads((offline.ledger.output_dir / "manifest.json").read_text())
    assert manifest["transport_identity"] == adapter.TRANSPORT_IDENTITY
    assert manifest["live_authorization"] is False
    assert manifest["scope"] == "offline_contract_no_live_authorization"
    assert manifest["configuration"] == adapter.locator_qwen_configuration()
    assert manifest["configuration"]["max_requests"] == 1
    assert manifest["configuration"]["price_scope"] == "frozen_conservative_estimate_not_invoice"
    assert manifest["configuration"]["transport_construction"] == "no_io"
    assert manifest["frozen_dependency_coupling"] == list(adapter.FROZEN_DEPENDENCY_COUPLING)
    before = journal_text(offline.ledger)
    with pytest.raises(base.CanaryStopped, match="^output_creation_failed_or_occupied$"):
        adapter.LocatorQwenLedger(offline.ledger.output_dir)
    assert journal_text(offline.ledger) == before
    old = base.CanaryLedger(tmp_path / "old", {"old": True})
    with pytest.raises(base.CanaryStopped, match="^locator_ledger_required$"):
        adapter.LocatorQwenTransport(KEY, old, snapshot=snapshot(), question=QUESTION)
    with monkeypatch.context() as scoped:
        forbidden = Mock(side_effect=AssertionError("constructor I/O or environment lookup"))
        for name in ("open", "mkdir", "read_bytes", "read_text", "write_bytes", "write_text"):
            scoped.setattr(Path, name, forbidden)
        scoped.setattr(os, "getenv", forbidden)
        scoped.setattr(httpx, "AsyncClient", forbidden)
        make_transport(offline)
        forbidden.assert_not_called()
    assert journal_text(offline.ledger) == before


@pytest.mark.parametrize("question", [None, 1, "", " \t\n", "x" * 4097])
def test_invalid_construction_does_not_write(offline, question):
    """Construction refusal must not quietly append a stop event."""
    before = journal_text(offline.ledger)
    with pytest.raises(base.CanaryStopped, match="^invalid_question$"):
        make_transport(offline, question=question)
    assert journal_text(offline.ledger) == before and offline.requests == []


@pytest.mark.parametrize("key", [None, "", "white space", "x" * 513])
def test_invalid_explicit_key_no_ambient_fallback(offline, key, monkeypatch):
    """Invalid dedicated credentials cannot fall back to an operator environment key."""
    monkeypatch.setenv("QWEN_API_KEY", KEY)
    with pytest.raises(base.CanaryStopped, match="^invalid_dedicated_key$"):
        adapter.LocatorQwenTransport(key, offline.ledger, snapshot=snapshot(), question=QUESTION)
    assert offline.requests == [] and events(offline.ledger) == []


def test_invalid_snapshot_revalidated_and_safe(offline):
    """Bypass-constructed nested fields cannot become a trusted catalog."""
    snap = snapshot()
    object.__setattr__(snap.sources[0], "source_id", "INVALID_PRIVATE_ID")
    with pytest.raises(base.CanaryStopped, match="^invalid_snapshot$"):
        make_transport(offline, snap)
    assert events(offline.ledger) == [] and offline.requests == []


def test_used_and_pending_ledger_constructor_rejected_without_writes(offline):
    """Freshness admission must reject pending and finished journals without resetting them."""
    body = request_for()
    ordinal = offline.ledger.reserve(body)
    before = journal_text(offline.ledger)
    with pytest.raises(base.CanaryStopped, match="^fresh_locator_ledger_required$"):
        make_transport(offline)
    assert journal_text(offline.ledger) == before
    offline.ledger.finish(ordinal, received=True, usage=USAGE, error=None)
    before = journal_text(offline.ledger)
    with pytest.raises(base.CanaryStopped, match="^fresh_locator_ledger_required$"):
        make_transport(offline)
    assert journal_text(offline.ledger) == before
