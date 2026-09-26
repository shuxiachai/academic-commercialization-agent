"""Fake-key native-wire controls, not native compatibility or query-quality evidence."""

import asyncio
import builtins
from copy import deepcopy
from decimal import Decimal
import hashlib
import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import warnings

import httpx
import pytest

from academic_agent import report_evidence_followup as followup
from academic_agent import report_evidence_qwen_canary as base
from academic_agent import report_evidence_snapshot as snapshots
from academic_agent import saved_source_candidate_search as candidate
from academic_agent import saved_source_candidate_query_qwen_transport as adapter

KEY = "sk-candidate-query-fictional-offline-key"
QUESTION = " \nFind the stored thermal-material note 🌿.\t "
QUERY = "phase-change"
USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
SENTINELS = ("private-report-sentinel", "private-title-sentinel", "private-summary-sentinel",
             "private-publisher-sentinel", "https://private-path-sentinel.invalid/report")


def snapshot(*, empty=False):
    return snapshots.ReportEvidenceSnapshot(report_ref=SENTINELS[0], sources=() if empty else (
        snapshots.SnapshotSource(source_id="A913", group="academic", title=SENTINELS[1],
            summary=SENTINELS[2] + " phase change", publisher=SENTINELS[3], url=SENTINELS[4],
            source_type="synthetic", accessed_date="2026-09-26"),
        snapshots.SnapshotSource(source_id="A914", group="academic", title="phase-change note",
            summary=None, publisher="synthetic", source_type="control", accessed_date="2026-09-26"),
    ))


def call(arguments=None, *, name="search_saved_candidates", content=None):
    return {"role": "assistant", "content": content, "tool_calls": [{
        "id": "synthetic_query_call", "type": "function", "function": {
            "name": name, "arguments": json.dumps({"query": QUERY}) if arguments is None else arguments,
        },
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


def make_transport(state, question=QUESTION):
    return adapter.CandidateQueryQwenTransport(KEY, state.ledger, question=question)


def invoke(transport, question=QUESTION, policy=candidate.QUERY_POLICY):
    return transport(question, policy)


def run(state, *, snap=None, question=QUESTION):
    transport = make_transport(state, question)
    result = candidate.propose_saved_candidates(snapshot() if snap is None else snap, question, proposer=transport)
    return result, transport


@pytest.fixture
def offline(tmp_path, monkeypatch):
    """Keep the actual _post, fsync and local query; replace only physical HTTP."""
    state = SimpleNamespace(requests=[], queries=[], proposals=[], intents=[], fsynced=[],
                            client_options=[], transport_options=[], response=payload(), raw=None,
                            status=200, headers={}, exception=None)
    state.ledger = adapter.CandidateQueryQwenLedger(tmp_path / "query-ledger")
    actual_client, actual_fsync = httpx.AsyncClient, os.fsync
    actual_search, actual_proposal = candidate.search_saved_candidates, adapter._proposal

    def fsync(fd):
        actual_fsync(fd)
        state.fsynced.append(deepcopy(events(state.ledger)))

    def dispatch(request):
        state.requests.append(request)
        # Observations, not a mock-side gate: a cap-bypass mutation can physically
        # send a second request, which the OUTER test must reject as a defect.
        state.intents.append((deepcopy(events(state.ledger)), deepcopy(state.fsynced)))
        if state.exception is not None:
            raise state.exception
        raw = adapter._encoded(state.response) if state.raw is None else state.raw
        return httpx.Response(state.status, headers=state.headers, stream=httpx.ByteStream(raw))

    def http_transport(**kwargs):
        state.transport_options.append(kwargs)
        return httpx.MockTransport(dispatch)

    def client(**kwargs):
        assert isinstance(kwargs["transport"], httpx.MockTransport)
        state.client_options.append(kwargs)
        return actual_client(**kwargs)

    def search(*args, **kwargs):
        state.queries.append((args, kwargs))
        return actual_search(*args, **kwargs)

    def proposal(message):
        result = actual_proposal(message)
        state.proposals.append(deepcopy(result))
        return result

    state.read = Mock(side_effect=AssertionError("candidate query must never read a source"))
    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", http_transport)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setattr(candidate, "search_saved_candidates", search)
    monkeypatch.setattr(adapter, "_proposal", proposal)
    monkeypatch.setattr(snapshots, "read_source", state.read)
    monkeypatch.setattr(followup, "read_source", state.read)
    return state


def test_wrapper_native_wire_fsynced_intent_plain_proposal_real_query_canonical_json(offline, monkeypatch):
    """A mocked callback or a reserve-after-POST implementation cannot pass this seam."""
    monkeypatch.setenv("QWEN_API_KEY", "ambient-key-never-used")
    monkeypatch.setenv("OPENAI_API_KEY", "another-ambient-key-never-used")
    snap = snapshot()
    result, transport = run(offline, snap=snap)
    rendered = candidate.render_candidate_result(result)
    delivered = json.loads(rendered)
    assert delivered == result
    assert rendered == json.dumps(result, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    assert set(delivered) == {"state", "reason", "query", "callback_entries", "query_executions",
                              "proposal_bytes", "search_result", "selection", "semantic_support", "unit_equivalence"}
    assert delivered["state"] == "completed" and delivered["reason"] == "search_completed"
    assert delivered["query"] == QUERY
    assert delivered["callback_entries"] == delivered["query_executions"] == 1
    assert delivered["proposal_bytes"] == len(adapter._encoded({"query": QUERY}))
    assert delivered["selection"] is None
    assert delivered["semantic_support"] == delivered["unit_equivalence"] == "not_assessed"
    search = delivered["search_result"]
    assert set(search) == {"literal_result", "normalized_additions", "snapshot_hash", "source_observation",
                           "selection", "semantic_support", "unit_equivalence", "literal_scope"}
    assert search["literal_result"]["total_count"] == search["normalized_additions"]["total_count"] == 1
    assert search["literal_result"]["hits"][0]["source_id"] == "A914"
    assert search["normalized_additions"]["hits"] == [{"source_id": "A913", "title": SENTINELS[1],
        "origin": "unknown", "stored_length": snap.sources[0].stored_length, "text_status": "available"}]
    assert search["snapshot_hash"] == snap.snapshot_hash
    assert search["source_observation"] == {"source_count": 2, "missing_summary_count": 1,
                                            "empty_summary_count": 0, "whitespace_only_summary_count": 0}
    assert search["selection"] is None
    assert search["semantic_support"] == search["unit_equivalence"] == "not_assessed"
    assert len(offline.requests) == len(offline.queries) == len(offline.proposals) == 1
    assert offline.proposals == [{"query": QUERY}] and type(offline.proposals[0]) is dict
    args, kwargs = offline.queries[0]
    assert args[1:] == (QUERY,) and kwargs == {}
    assert args[0] is not snap and args[0].model_dump() == snap.model_dump()
    offline.read.assert_not_called()

    request = offline.requests[0]
    body = json.loads(request.content)
    assert request.content == adapter._encoded(body) == adapter._encoded(adapter._request(QUESTION))
    assert request.method == "POST" and request.url == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer " + KEY
    assert request.headers["content-type"] == "application/json" and request.headers["accept-encoding"] == "identity"
    assert body["messages"] == [{"role": "system", "content": candidate.QUERY_POLICY},
                                {"role": "system", "content": adapter.NATIVE_POLICY},
                                {"role": "user", "content": QUESTION}]
    assert "function call" in body["messages"][1]["content"] and "Never put query JSON in content" in body["messages"][1]["content"]
    assert len(body["tools"]) == 1
    function = body["tools"][0]["function"]
    assert function["name"] == "search_saved_candidates"
    assert function["parameters"] == {"type": "object", "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 256}},
        "required": ["query"], "additionalProperties": False}
    assert body["model"] == "qwen3.5-plus" and body["tool_choice"] == "auto"
    assert body["stream"] is body["enable_thinking"] is body["parallel_tool_calls"] is False
    assert body["max_tokens"] == 512 and body["temperature"] == 0 and "response_format" not in body
    record = offline.ledger.records[0]
    assert record["request"] == body and record["request_sha256"] == hashlib.sha256(request.content).hexdigest()
    at_post, synced_at_post = offline.intents[0]
    assert [item["event"] for item in at_post] == ["request_reserved"]
    assert synced_at_post == [at_post] and at_post[0]["request"] == body
    assert at_post[0]["request_sha256"] == record["request_sha256"]
    assert [row["event"] for row in events(offline.ledger)] == ["request_reserved", "request_finished"]
    assert record["reported_usage"] == USAGE and record["protocol_accepted"] is True
    assert record["provider_response_received"] is record["response_model_matches_authorized"] is True
    assert "assistant_message" not in record
    for secret in (*SENTINELS, "A913", "A914", snap.snapshot_hash, KEY):
        assert secret not in request.content.decode("ascii") and secret not in journal_text(offline.ledger)
    assert SENTINELS[2] not in rendered.decode("ascii")
    assert transport._post.__func__ is adapter.QwenFollowupTransport._post
    assert offline.transport_options == [{"retries": 0, "verify": True, "trust_env": False}]
    options = offline.client_options[0]
    assert options["verify"] is True and options["trust_env"] is options["follow_redirects"] is False
    assert options["timeout"].connect == 10 and options["timeout"].read == 60


def test_content_query_is_valid_internal_dict_but_not_a_native_tool_call(offline):
    """Internal JSON success must not falsely certify the provider's native contract."""
    control = candidate.propose_saved_candidates(snapshot(), QUESTION, proposer=lambda *_: {"query": QUERY})
    assert control["state"] == "completed"
    offline.queries.clear()
    offline.response = payload({"role": "assistant", "content": json.dumps({"query": QUERY})})
    result, _ = run(offline)
    assert result["state"] == "callback_failure" and result["query_executions"] == 0
    assert offline.ledger.records[0]["error"] == "invalid_decline"
    assert offline.ledger.records[0]["reported_usage"] == USAGE and offline.queries == []


def test_native_no_call_decline_is_new_plain_dict_and_not_refusal(offline):
    """Legitimate abstention needs strict no-call JSON, not provider refusal prose."""
    offline.response = payload({"role": "assistant", "content": ' {"action":"decline"} ', "tool_calls": []})
    result, transport = run(offline)
    assert result["state"] == "proposal_declined" and result["callback_entries"] == 1
    assert result["query_executions"] == 0 and result["search_result"] is None
    assert offline.proposals == [{"action": "decline"}] and type(offline.proposals[0]) is dict
    assert offline.ledger.records[0]["protocol_accepted"] is True
    assert offline.queries == [] and len(offline.requests) == 1
    with pytest.raises(base.CanaryStopped, match="^conversation_closed$"):
        invoke(transport)
    assert len(offline.requests) == 1


def test_provider_refusal_is_safe_failure_not_decline(offline):
    """Provider policy refusal must not inflate the legitimate decline denominator."""
    offline.response = payload({"role": "assistant", "content": None, "refusal": "PRIVATE_REFUSAL"})
    result, _ = run(offline)
    assert result["state"] == "callback_failure" and result["query_executions"] == 0
    record = offline.ledger.records[0]
    assert record["error"] == "provider_refusal" and record["protocol_accepted"] is False
    assert record["reported_usage"] == USAGE and "PRIVATE_REFUSAL" not in journal_text(offline.ledger)


def test_empty_wrapper_never_calls_native(offline):
    """An adapter without source access must not undo the wrapper's empty suppression."""
    result, transport = run(offline, snap=snapshot(empty=True))
    assert result["state"] == "no_sources" and result["callback_entries"] == result["query_executions"] == 0
    assert not transport._attempted and offline.requests == offline.ledger.records == []
    assert events(offline.ledger) == [] and offline.ledger.stop_reason is None


def test_local_search_failure_keeps_accepted_native_accounting_without_retry(offline, monkeypatch):
    """Post-proposal local observation loss is not a refundable native protocol failure."""
    monkeypatch.setattr(candidate, "lookup_sources", Mock(side_effect=ValueError("local observation failed")))
    first, peer = make_transport(offline), make_transport(offline)
    result = candidate.propose_saved_candidates(snapshot(), QUESTION, proposer=first)
    assert result["state"] == "search_unavailable" and result["query_executions"] == 1
    assert result["search_result"]["literal_result"] is None
    assert result["search_result"]["normalized_additions"]["total_count"] is None
    assert offline.ledger.records[0]["protocol_accepted"] is True
    assert offline.ledger.records[0]["reported_usage"] == USAGE
    assert offline.ledger.stop_reason is None
    with pytest.raises(base.CanaryStopped, match="^request_limit$"):
        invoke(peer)
    assert len(offline.requests) == 1


class StringSubclass(str):
    pass


@pytest.mark.parametrize(("question", "policy"), [
    (QUESTION + "tampered", candidate.QUERY_POLICY), (QUESTION, candidate.QUERY_POLICY + "tampered"),
    (None, candidate.QUERY_POLICY), (QUESTION, {}),
    (StringSubclass(QUESTION), candidate.QUERY_POLICY), (QUESTION, StringSubclass(candidate.QUERY_POLICY)),
    ("\ud800", candidate.QUERY_POLICY), ("x" * 4097, candidate.QUERY_POLICY),
])
def test_callback_binding_failure_stops_shared_ledger_before_reserve(offline, question, policy):
    """A binding-bypass mutant must POST and fail these physical zero-call checks."""
    first, peer = make_transport(offline), make_transport(offline)
    with pytest.raises(base.CanaryStopped, match="^invalid_request_contract$"):
        invoke(first, question, policy)
    assert first._attempted and offline.ledger.stop_reason == "invalid_request_contract"
    with pytest.raises(base.CanaryStopped, match="^batch_already_stopped$"):
        invoke(peer)
    assert offline.requests == offline.ledger.records == []
    assert [row["event"] for row in events(offline.ledger)] == ["batch_stopped"]


@pytest.mark.parametrize("over", [0, 1])
def test_exact_full_wire_12288_admitted_12289_rejected(offline, over):
    """A legal character count does not replace the full canonical HTTP body limit."""
    room = 12288 - len(adapter._encoded(adapter._request("q"))) + over
    question = "q" + "界" * (room // 6) + "x" * (room % 6)
    assert len(question) <= 4096
    assert len(adapter._encoded(adapter._request(question))) == 12288 + over
    result, _ = run(offline, question=question)
    assert result["state"] == ("callback_failure" if over else "completed")
    assert len(offline.requests) == len(offline.ledger.records) == 1 - over
    if over:
        assert offline.ledger.stop_reason == "request_too_large"
    else:
        assert len(offline.requests[0].content) == 12288


def test_4096_astral_question_rejected_without_trimming_or_reservation(offline):
    """Surrogate-pair JSON escaping can exceed the body ceiling despite legal scalars."""
    question = "🌿" * 4096
    result, transport = run(offline, question=question)
    assert transport._question == question and result["state"] == "callback_failure"
    assert offline.ledger.stop_reason == "request_too_large"
    assert offline.requests == offline.ledger.records == []


def test_two_preconstructed_instances_share_single_reservation(offline):
    """Constructor-only freshness cannot prevent a second preconstructed instance POST."""
    first, peer = make_transport(offline), make_transport(offline)
    assert invoke(first) == {"query": QUERY}
    assert offline.ledger.stop_reason is offline.ledger.pending is None
    with pytest.raises(base.CanaryStopped, match="^request_limit$"):
        invoke(peer)
    assert len(offline.requests) == len(offline.ledger.records) == 1


def test_direct_second_reservation_is_not_old_six_request_allowance(offline):
    """The ledger cap is independent of the callback instance guard."""
    invoke(make_transport(offline))
    with pytest.raises(base.CanaryStopped, match="^request_limit$"):
        offline.ledger.reserve(adapter._request(QUESTION))
    assert len(offline.requests) == len(offline.ledger.records) == 1


def test_unbound_guard_cannot_reserve(offline):
    """Calling reserve before binding the explicit key cannot persist unchecked data."""
    with pytest.raises(base.CanaryStopped, match="^secret_guard_unbound$"):
        offline.ledger.reserve(adapter._request(KEY))
    assert offline.ledger.records == offline.requests == [] and KEY not in journal_text(offline.ledger)
    with pytest.raises(base.CanaryStopped, match="^fresh_candidate_query_ledger_required$"):
        make_transport(offline)


def test_key_guard_cannot_be_replaced_by_second_transport(offline):
    """A peer may share the same explicit key, never replace the ledger's scan guard."""
    first = make_transport(offline)
    before = journal_text(offline.ledger)
    with pytest.raises(base.CanaryStopped, match="^secret_guard_key_mismatch$"):
        adapter.CandidateQueryQwenTransport("different-fake-key", offline.ledger, question=QUESTION)
    assert journal_text(offline.ledger) == before and offline.ledger._guard_key == KEY
    assert invoke(first) == {"query": QUERY}


@pytest.mark.parametrize("state", ["pending", "finished", "stopped"])
def test_used_ledger_cannot_be_rebound_or_reconstructed(offline, state):
    """No new transport resets a pending/used/stopped single-owner journal."""
    make_transport(offline)
    ordinal = offline.ledger.reserve(adapter._request(QUESTION))
    if state == "finished":
        offline.ledger.finish(ordinal, received=True, usage=USAGE, error=None)
    elif state == "stopped":
        offline.ledger.stop("invalid_query")
    before = journal_text(offline.ledger)
    with pytest.raises(base.CanaryStopped, match="^fresh_candidate_query_ledger_required$"):
        make_transport(offline)
    assert journal_text(offline.ledger) == before
    if state == "pending":
        with pytest.raises(base.CanaryStopped, match="^unresolved_request$"):
            offline.ledger.reserve(adapter._request(QUESTION))
        assert offline.ledger.pending == 1


BAD_MESSAGES = [
    call('{"query":"a","query":"b"}'), call('{"query":"a","extra":1}'), call('{"action":"decline"}'),
    call('[]'), call('null'), call('NaN'), call('{"query":12}'), call('{"query":true}'),
    call('{"query":""}'), call('{"query":" \\t"}'), call(json.dumps({"query": "x" * 257})),
    call('{"query":"\\ud800"}'), call(name="read_source"), call(name="lookup_sources"),
    call(content="PRIVATE_GENERATED_ANSWER"), call(content=" "),
    {**call(), "tool_calls": call()["tool_calls"] * 2}, {**call(), "refusal": "mixed"},
    {**call(), "tool_calls": [{**call()["tool_calls"][0], "extra": True}]},
    {**call(), "tool_calls": [{**call()["tool_calls"][0], "type": "custom"}]},
    {**call(), "tool_calls": [{**call()["tool_calls"][0], "id": "bad identity"}]},
    {**call(), "tool_calls": [{**call()["tool_calls"][0], "index": True}]},
    {**call(), "tool_calls": [{**call()["tool_calls"][0], "function": {
        **call()["tool_calls"][0]["function"], "extra": "PRIVATE_FIELD"}}]},
    {"role": "assistant", "content": '{"action":"decline","extra":true}'},
    {"role": "assistant", "content": '{"action":"decline","action":"decline"}'},
    {"role": "assistant", "content": "PRIVATE_GENERATED_ANSWER"},
    {"role": "assistant", "content": ""}, {"role": "user", "content": '{"action":"decline"}'},
    {"role": "assistant", "content": 7}, {"role": "assistant", "content": "mixed", "refusal": "no"},
]


@pytest.mark.parametrize("message", BAD_MESSAGES)
def test_bad_native_response_retains_known_usage_and_never_searches(offline, message):
    """Bad protocol data must not erase coherent usage or reach local search."""
    offline.response = payload(message)
    first, peer = make_transport(offline), make_transport(offline)
    result = candidate.propose_saved_candidates(snapshot(), QUESTION, proposer=first)
    assert result["state"] == "callback_failure" and result["query_executions"] == 0
    assert len(offline.requests) == 1 and offline.queries == []
    record = offline.ledger.records[0]
    assert record["reported_usage"] == USAGE and record["usage_status"] == "complete"
    assert record["protocol_accepted"] is False and "assistant_message" not in record
    assert offline.ledger.stop_reason in adapter._SAFE_ERRORS
    with pytest.raises(base.CanaryStopped, match="^batch_already_stopped$"):
        invoke(peer)
    assert len(offline.requests) == 1 and "PRIVATE_" not in journal_text(offline.ledger)
    offline.read.assert_not_called()


@pytest.mark.parametrize("over", [0, 1])
def test_raw_arguments_cap_separate_from_canonical_proposal(offline, over):
    """Padding must count before parsing even though its canonical dict is tiny."""
    raw = json.dumps({"query": QUERY})
    raw += " " * (4096 + over - len(raw))
    assert len(raw.encode("utf-8")) == 4096 + over
    assert len(adapter._encoded(json.loads(raw))) < 4096
    offline.response = payload(call(raw))
    result, _ = run(offline)
    assert result["state"] == ("callback_failure" if over else "completed")
    assert offline.ledger.records[0]["reported_usage"] == USAGE
    if over:
        assert offline.ledger.stop_reason == "invalid_query"


@pytest.mark.parametrize("over", [0, 1])
def test_raw_utf8_byte_limit_not_character_count(offline, over):
    """A VALID scalar query with padding isolates raw bytes from chars/proposal bytes."""
    query = "🌿" * 256
    raw = json.dumps({"query": query}, ensure_ascii=False)
    raw += " " * (4096 + over - len(raw.encode("utf-8")))
    assert len(raw) < 4096 and len(raw.encode("utf-8")) == 4096 + over
    assert len(adapter._encoded(json.loads(raw))) < 4096
    offline.response = payload(call(raw))
    result, _ = run(offline)
    assert result["state"] == ("callback_failure" if over else "completed")
    assert offline.ledger.stop_reason == ("invalid_query" if over else None)
    assert offline.ledger.records[0]["reported_usage"] == USAGE


def test_256_astral_query_remains_valid_scalar_canonical_proposal(offline):
    """Astral pairs are legal; rejection must not confuse them with lone surrogates."""
    query = "🌿" * 256
    offline.response = payload(call(json.dumps({"query": query}, ensure_ascii=False)))
    proposal = invoke(make_transport(offline))
    assert proposal == {"query": query} and len(adapter._encoded(proposal)) < 4096


@pytest.mark.parametrize("usage", [None, {}, {**USAGE, "prompt_tokens": True},
    {**USAGE, "completion_tokens": -1}, {**USAGE, "total_tokens": 121},
    {**USAGE, "total_tokens": 120.0}, {**USAGE, "prompt_tokens": 1_000_000_001}])
def test_unknown_usage_is_reserved_lower_bound_not_free(offline, usage):
    """Absent/contradictory usage remains unknown, not observed zero billing."""
    offline.response["usage"] = usage
    result, _ = run(offline)
    assert result["state"] == "callback_failure"
    record = offline.ledger.records[0]
    assert record["usage_status"] == "unknown" and "reported_usage" not in record
    assert record["error"] == "usage_unknown_or_contradictory"
    summary = offline.ledger.summary()
    assert summary["unknown_usage_requests"] == 1 and summary["cost_coverage"] == "lower_bound"
    assert Decimal(summary["budget_consumed_usd"]) == base.RESERVATION_USD


@pytest.mark.parametrize("fault", ["model_suffix", "old_model", "missing_model", "input_limit", "output_limit",
                                  "finish", "truncated", "index", "choices", "scalar_metadata"])
def test_protocol_scope_failures_preserve_reported_usage_no_fallback(offline, fault):
    """Identity drift, token overrun and truncation cannot become success or retry."""
    if fault in {"model_suffix", "old_model", "missing_model"}:
        offline.response["model"] = {"model_suffix": "qwen3.5-plus-latest", "old_model": "qwen-plus",
                                     "missing_model": None}[fault]
    elif fault in {"input_limit", "output_limit"}:
        prompt, completion = (16385, 20) if fault == "input_limit" else (100, 513)
        offline.response["usage"] = {"prompt_tokens": prompt, "completion_tokens": completion,
                                      "total_tokens": prompt + completion}
    elif fault in {"finish", "truncated"}:
        offline.response["choices"][0]["finish_reason"] = "stop" if fault == "finish" else "length"
    elif fault == "index":
        offline.response["choices"][0]["index"] = True
    elif fault == "choices":
        offline.response["choices"] *= 2
    else:
        offline.response["provider_meta"] = "\ud800"
    result, _ = run(offline)
    assert result["state"] == "callback_failure" and len(offline.requests) == 1
    record = offline.ledger.records[0]
    assert record["reported_usage"] == offline.response["usage"] and record["protocol_accepted"] is False
    assert record["usage_status"] == "complete" and Decimal(record["estimated_usd"]) > 0
    assert record["response_model_matches_authorized"] is (fault not in {"model_suffix", "old_model", "missing_model"})


def escaped_key():
    return "".join(f"\\u{ord(char):04x}" for char in KEY)


@pytest.mark.parametrize("location", ["question", "direct_reserve", "arguments", "content", "refusal", "provider_meta", "usage_meta"])
@pytest.mark.parametrize("escaped", [False, True])
def test_literal_and_decodable_key_echo_never_journaled(offline, location, escaped):
    """Screen recoverable mixed-text echoes before reserve, including response metadata."""
    secret = "PRIVATE_ECHO " + (escaped_key() if escaped else KEY)
    request_side = location in {"question", "direct_reserve"}
    if location == "direct_reserve":
        make_transport(offline)
        with pytest.raises(base.CanaryStopped, match="^secret_in_request$"):
            offline.ledger.reserve(adapter._request(secret))
    else:
        if location == "arguments":
            offline.response = payload(call(json.dumps({"query": secret})))
        elif location in {"content", "refusal"}:
            offline.response = payload({"role": "assistant", location: secret})
        elif location == "provider_meta":
            offline.response["provider_meta"] = {secret: "metadata"}
        elif location == "usage_meta":
            offline.response["usage"]["details"] = secret
        result, _ = run(offline, question=secret if location == "question" else QUESTION)
        assert result["state"] == "callback_failure"
    assert offline.ledger.stop_reason == ("secret_in_request" if request_side else "secret_in_response")
    assert len(offline.requests) == len(offline.ledger.records) == int(not request_side)
    text = journal_text(offline.ledger)
    assert KEY not in text and "PRIVATE_ECHO" not in text and escaped_key() not in text
    if not request_side:
        assert offline.ledger.records[0]["reported_usage"] == USAGE


@pytest.mark.parametrize("fault", ["reserve_method", "reserve_append", "reserve_open", "reserve_fsync"])
def test_reservation_faults_always_zero_post_and_stop_peers(offline, monkeypatch, fault):
    """No reserve/persistence failure is permission to dispatch or reuse the ledger."""
    first, peer = make_transport(offline), make_transport(offline)
    targets = {"reserve_method": (offline.ledger, "reserve"), "reserve_append": (offline.ledger, "_append"),
               "reserve_open": (Path, "open"), "reserve_fsync": (os, "fsync")}
    with monkeypatch.context() as scoped:
        obj, name = targets[fault]
        scoped.setattr(obj, name, Mock(side_effect=OSError("PRIVATE_FAULT " + KEY)))
        with pytest.raises(base.CanaryStopped, match="^persistence_failed$"):
            invoke(first)
    assert offline.requests == offline.ledger.records == [] and offline.ledger.stop_reason == "persistence_failed"
    with pytest.raises(base.CanaryStopped, match="^batch_already_stopped$"):
        invoke(peer)
    assert KEY not in journal_text(offline.ledger) and "PRIVATE_FAULT" not in journal_text(offline.ledger)


@pytest.mark.parametrize("fault", ["finish_method", "finish_append", "finish_fsync", "stop_after_finish"])
@pytest.mark.parametrize("known", [False, True])
def test_finish_faults_retain_pending_intent_and_observed_usage(offline, monkeypatch, fault, known):
    """Even a finish failure before entry or after append cannot refund spent intent."""
    first, peer = make_transport(offline), make_transport(offline)
    if not known:
        offline.response["usage"] = None
    if fault == "stop_after_finish" and known:
        offline.response["model"] = "not-authorized"
    original_append, original_fsync = offline.ledger._append, os.fsync
    count = 0

    def fsync(fd):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("PRIVATE_FINISH " + KEY)
        original_fsync(fd)

    def append(event):
        fail_event = "batch_stopped" if fault == "stop_after_finish" else "request_finished"
        if event["event"] == fail_event:
            raise OSError("PRIVATE_FINISH " + KEY)
        original_append(event)

    with monkeypatch.context() as scoped:
        if fault == "finish_method":
            scoped.setattr(offline.ledger, "finish", Mock(side_effect=RuntimeError("PRIVATE_FINISH " + KEY)))
        elif fault == "finish_fsync":
            scoped.setattr(os, "fsync", fsync)
        else:
            scoped.setattr(offline.ledger, "_append", append)
        with pytest.raises(base.CanaryStopped, match="^persistence_failed$"):
            invoke(first)
    assert len(offline.requests) == 1 and offline.ledger.pending == 1
    assert offline.ledger.stop_reason == "persistence_failed"
    record = offline.ledger.records[0]
    assert record["protocol_accepted"] is False
    assert record["usage_status"] == ("complete" if known else "unknown")
    if known:
        assert record["reported_usage"] == USAGE
    else:
        assert "reported_usage" not in record
    summary = offline.ledger.summary()
    assert summary["pending_request_id"] == 1 and summary["unknown_usage_requests"] == int(not known)
    assert Decimal(summary["budget_consumed_usd"]) >= base.RESERVATION_USD
    with pytest.raises(base.CanaryStopped, match="^batch_already_stopped$"):
        invoke(peer)
    assert len(offline.requests) == 1 and "PRIVATE_FINISH" not in journal_text(offline.ledger)


@pytest.mark.parametrize(("fault", "reason"), [
    ("http302", "http_status_rejected"), ("http401", "http_status_rejected"), ("http429", "http_status_rejected"),
    ("http500", "http_status_rejected"), ("encoding", "response_encoding_rejected"),
    ("oversize", "response_too_large"), ("timeout", "request_timeout"),
    ("duplicate_json", "response_or_transport_failed"), ("invalid_utf8", "response_or_transport_failed"),
    ("scalar", "invalid_response_protocol"), ("nonfinite", "response_or_transport_failed"),
])
def test_actual_post_http_decode_failures_no_retry_no_raw_diagnostics(offline, fault, reason):
    """The actual inherited stream/parser guards must run under physical MockTransport."""
    if fault.startswith("http"):
        offline.status, offline.raw = int(fault[4:]), ("PRIVATE_HTTP " + KEY).encode()
    elif fault == "encoding":
        offline.headers = {"content-encoding": "gzip"}
    elif fault == "oversize":
        offline.raw = b"x" * 65537
    elif fault == "timeout":
        offline.exception = httpx.ReadTimeout("PRIVATE_HTTP " + KEY)
    elif fault == "duplicate_json":
        offline.raw = b'{"model":"qwen3.5-plus","model":"qwen3.5-plus"}'
    elif fault == "invalid_utf8":
        offline.raw = b"\xff"
    elif fault == "scalar":
        offline.raw = b"42"
    else:
        offline.raw = b'{"usage":NaN}'
    first, peer = make_transport(offline), make_transport(offline)
    with pytest.raises(base.CanaryStopped, match="^" + reason + "$"):
        invoke(first)
    assert len(offline.requests) == 1 and offline.ledger.stop_reason == reason
    assert offline.ledger.records[0]["usage_status"] == "unknown"
    assert Decimal(offline.ledger.summary()["budget_consumed_usd"]) == base.RESERVATION_USD
    with pytest.raises(base.CanaryStopped, match="^batch_already_stopped$"):
        invoke(peer)
    assert len(offline.requests) == 1 and "PRIVATE_HTTP" not in journal_text(offline.ledger)


def test_exact_64k_raw_response_admitted(offline):
    """The response byte ceiling is distinct from argument/proposal/body limits."""
    raw = adapter._encoded(payload())
    offline.raw = raw + b" " * (65536 - len(raw))
    assert invoke(make_transport(offline)) == {"query": QUERY}
    assert len(offline.requests) == 1 and offline.ledger.records[0]["protocol_accepted"] is True


@pytest.mark.parametrize("kind", ["canary", "runtime", "string_bomb"])
def test_malicious_error_categories_are_allowlisted_not_stringified(offline, kind):
    """Sharing CanaryStopped's type does not authorize persisting its arbitrary text."""
    class StringBomb(base.CanaryStopped):
        def __str__(self):
            raise AssertionError("never stringify exceptions")

    error_type = {"canary": base.CanaryStopped, "runtime": RuntimeError, "string_bomb": StringBomb}[kind]
    offline.exception = error_type("PRIVATE_EXCEPTION " + KEY)
    with pytest.raises(base.CanaryStopped, match="^response_or_transport_failed$") as caught:
        invoke(make_transport(offline))
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    assert "PRIVATE_EXCEPTION" not in journal_text(offline.ledger) and KEY not in journal_text(offline.ledger)


def test_direct_stop_finish_do_not_store_raw_reason_or_response(offline):
    """Inherited optional error/message inputs are not a back door for response journals."""
    make_transport(offline)
    ordinal = offline.ledger.reserve(adapter._request(QUESTION))
    offline.ledger.finish(ordinal, received=True, usage=USAGE, error="PRIVATE_REASON " + KEY,
                          message={"content": KEY})
    assert offline.ledger.records[0]["error"] == "response_or_transport_failed"
    assert "assistant_message" not in offline.ledger.records[0]
    assert KEY not in journal_text(offline.ledger) and "PRIVATE_REASON" not in journal_text(offline.ledger)


def test_running_async_loop_rejected_before_coroutine_and_post(offline):
    """Rejecting a synchronous callback in-loop must not leak an unawaited coroutine."""
    transport = make_transport(offline)

    async def caller():
        with pytest.raises(base.CanaryStopped, match="^synchronous_callback_required$"):
            invoke(transport)

    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        asyncio.run(caller())
    assert seen == [] and offline.requests == offline.ledger.records == []
    assert offline.ledger.stop_reason == "synchronous_callback_required"


def test_independent_manifest_no_old_allowance_no_constructor_config_io(offline, tmp_path, monkeypatch):
    """Global no-I/O guards stop at the operation, never leak into pytest teardown."""
    manifest = json.loads((offline.ledger.output_dir / "manifest.json").read_text())
    config = adapter.candidate_query_qwen_configuration()
    assert manifest["transport_identity"] == adapter.TRANSPORT_IDENTITY and manifest["method_id"] == adapter.METHOD_ID
    assert manifest["live_authorization"] is False and manifest["scope"] == "offline_contract_no_live_authorization"
    assert manifest["configuration"] == config and config["max_requests"] == 1
    assert "usd_soft_limit" not in config and config["max_reserved_usd"] == str(base.RESERVATION_USD)
    assert config["input_token_reservation"] == 16384 and config["max_tokens"] == 512
    assert config["max_local_reads"] == config["max_result_return_turns"] == 0
    assert config["price_scope"] == "frozen_conservative_estimate_not_invoice"
    assert manifest["frozen_dependency_coupling"] == list(adapter.FROZEN_DEPENDENCY_COUPLING)
    assert "src/academic_agent/report_evidence_stage_qwen_transport.py" in adapter.FROZEN_DEPENDENCY_COUPLING
    assert "src/academic_agent/report_evidence_catalog_followup.py" in adapter.FROZEN_DEPENDENCY_COUPLING
    before = journal_text(offline.ledger)
    with pytest.raises(base.CanaryStopped, match="^output_creation_failed_or_occupied$"):
        adapter.CandidateQueryQwenLedger(offline.ledger.output_dir)
    assert journal_text(offline.ledger) == before
    old = base.CanaryLedger(tmp_path / "old-base", {"unrelated": True})
    with pytest.raises(base.CanaryStopped, match="^candidate_query_ledger_required$"):
        adapter.CandidateQueryQwenTransport(KEY, old, question=QUESTION)
    with monkeypatch.context() as scoped:
        forbidden = Mock(side_effect=AssertionError("constructor/config I/O"))
        for name in ("open", "mkdir", "read_bytes", "read_text", "write_bytes", "write_text"):
            scoped.setattr(Path, name, forbidden)
        scoped.setattr(builtins, "open", forbidden)
        scoped.setattr(os, "getenv", forbidden)
        scoped.setattr(type(os.environ), "__getitem__", forbidden)
        scoped.setattr(httpx, "AsyncClient", forbidden)
        scoped.setattr(base, "load_cases", forbidden)
        scoped.setattr(base, "configuration", forbidden)
        scoped.setattr(base, "run_canary", forbidden)
        scoped.setattr(adapter.QwenFollowupTransport, "__call__", forbidden)
        config = adapter.candidate_query_qwen_configuration()
        make_transport(offline)
        forbidden.assert_not_called()
    assert config["transport_construction"] == "no_io" and journal_text(offline.ledger) == before


def test_module_reexecution_has_no_adapter_io(monkeypatch):
    """With dependencies loaded, module initialization must not resolve keys or configure I/O."""
    with monkeypatch.context() as scoped:
        forbidden = Mock(side_effect=AssertionError("adapter initialization I/O"))
        scoped.setattr(builtins, "open", forbidden)
        scoped.setattr(Path, "open", forbidden)
        scoped.setattr(os, "getenv", forbidden)
        scoped.setattr(httpx, "AsyncClient", forbidden)
        importlib.reload(adapter)
        forbidden.assert_not_called()


@pytest.mark.parametrize("question", [None, 1, "", " \t\n", "x" * 4097, "\ud800", StringSubclass(QUESTION)])
def test_invalid_constructor_question_no_io(offline, question):
    """Constructor rejection must not consume a ledger or journal arbitrary input."""
    before = journal_text(offline.ledger)
    with pytest.raises(base.CanaryStopped, match="^invalid_question$"):
        make_transport(offline, question)
    assert journal_text(offline.ledger) == before and offline.ledger._guard_key is None
    assert offline.requests == []


@pytest.mark.parametrize("key", [None, "", "white space", "x" * 513, StringSubclass(KEY)])
def test_invalid_key_never_uses_ambient_credentials(offline, key, monkeypatch):
    """Ambient provider keys cannot repair an invalid dedicated credential."""
    monkeypatch.setenv("QWEN_API_KEY", KEY)
    with pytest.raises(base.CanaryStopped, match="^invalid_dedicated_key$"):
        adapter.CandidateQueryQwenTransport(key, offline.ledger, question=QUESTION)
    assert offline.requests == [] and events(offline.ledger) == [] and offline.ledger._guard_key is None
