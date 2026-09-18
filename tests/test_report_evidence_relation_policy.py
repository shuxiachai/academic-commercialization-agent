"""Consumed development controls test delivery, never native semantic accuracy."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket

import httpx
import pytest

from academic_agent import report_evidence_claim_relation as frozen
from academic_agent import report_evidence_relation_policy as policy
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource

FIXTURE = Path(__file__).parent / "fixtures" / "report_evidence_relation_policy.json"
FIXTURE_HASH = "a39622a3f2fd1f40da3d1f112e8d989e78ed25ccef4d369f8b714bde58fadf4c"


def controls():
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FIXTURE_HASH
    return json.loads(raw)["cases"]


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def snapshot(text="The fictional control measured exactly 3 V."):
    return ReportEvidenceSnapshot(report_ref="relation-policy-offline", sources=(SnapshotSource(
        source_id="A1", group="academic", title="Fictional saved control", summary=text,
        publisher="Synthetic", source_type="control", accessed_date="2026-09-17",
    ),))


def read(source_id="A1", offset=0, padding=0):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": "policy_read", "type": "function", "function": {"name": "read_source", "arguments": json.dumps({
            "source_id": source_id, "offset": offset, "length": 1500,
        }) + " " * padding},
    }]}


def final(relation="unavailable", ids=(), answer="Scripted control, not model judgment."):
    return {"role": "assistant", "content": json.dumps({
        "claim_relation": relation, "answer": answer, "supporting_evidence_ids": list(ids),
        "caveats": ["Saved text only; semantic correctness not verified."],
    })}


def assessed(relation):
    def reply(request):
        tool = json.loads(request["messages"][-1]["content"])
        ids = [tool["evidence_id"]] if relation in {"supported", "refuted"} else []
        return final(relation, ids)
    return reply


class Script:
    def __init__(self, *replies):
        self.replies = iter(replies)
        self.requests = []

    def __call__(self, request, /):
        self.requests.append(deepcopy(request))
        reply = next(self.replies)
        return reply(request) if callable(reply) else deepcopy(reply)


@pytest.fixture(autouse=True)
def forbid_http(monkeypatch):
    """Every new test fails on attempted HTTP, even with explicit fake credentials."""
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("HTTP is forbidden in relation-policy tests")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    yield
    assert not attempts


def serialized(result, script):
    """Compare real callback entry with JSON, keeping inner delivery separate."""
    encoded = result.model_dump_json()
    data = json.loads(encoded)
    assert policy.PolicyResult.model_validate_json(encoded) == result
    assert set(data) == {"inner", "audit"}
    assert data["audit"]["configured_policy_id"] == policy.POLICY_ID
    assert data["audit"]["configured_policy_hash"] == hashlib.sha256(policy.POLICY_APPEND.encode()).hexdigest()
    entries = data["audit"]["callback_entries"]
    assert len(entries) == len(script.requests) <= 2
    for ordinal, (entry, request) in enumerate(zip(entries, script.requests, strict=True), 1):
        assert entry["ordinal"] == ordinal
        assert entry["request_hash"] == hashlib.sha256(canonical(request)).hexdigest()
        assert entry["request_bytes"] == len(canonical(request)) <= 12 * 1024
        assert entry["policy_hash"] == policy.POLICY_HASH
        assert request["messages"][0]["content"].endswith(policy.POLICY_APPEND)
        delivered, usable, reason = [], [], None
        if request["messages"][-1]["role"] == "tool":
            tool = json.loads(request["messages"][-1]["content"])
            reason = tool["status"]
            if reason == "ok":
                delivered = [tool["evidence_id"]]
                usable = delivered if tool["text"].strip() else []
        assert entry["delivered_read_ids"] == delivered
        assert entry["usable_read_ids"] == usable
        assert entry["read_result_reason"] == reason
    inner = data["inner"]
    assert inner["audit"]["catalog"]["core"]["tool_executions"] <= 1
    assert inner["audit"]["downstream_calls"] <= 2
    assert inner["semantic_support"] == "not_assessed"
    assert inner["answer_verification"] == "not_verified"
    assert inner["assessment_origin"] == "injected_transport_unverified"
    return data


@pytest.mark.parametrize("case", controls(), ids=lambda case: case["case_id"])
def test_all_eight_controls_deliver_policy_both_stages_only_system_changes(case):
    """A configured policy must reach both actual callbacks without leaking labels."""
    saved = snapshot(case["text"])
    script = Script(read(), assessed(case["expected_relation"]))
    result = policy.run_relation_policy_followup(saved, case["claim"], callback=script)
    base = Script(read(), assessed(case["expected_relation"]))
    baseline = frozen.run_claim_relation_followup(saved, case["claim"], transport=lambda **request: base(request))
    assert result.inner == baseline
    for delivered, original in zip(script.requests, base.requests, strict=True):
        expected = deepcopy(original)
        expected["messages"][0]["content"] += policy.POLICY_APPEND
        assert canonical(delivered) == canonical(expected)
        assert delivered["messages"][1]["content"].encode() == case["claim"].encode()
        assert delivered["messages"][0]["content"].count(frozen._NEW_FINAL) == 1
        assert case["reference_rationale"] not in canonical(delivered).decode()
        assert "expected_relation" not in canonical(delivered).decode()
    assert script.requests[1]["tools"] == [] and script.requests[1]["tool_choice"] == "none"
    data = serialized(result, script)
    assert data["inner"]["model_assessment"]["claim_relation"] == case["expected_relation"]
    assert set(data["inner"]["model_assessment"]) == {"claim_relation", "answer", "supporting_evidence_ids", "caveats"}
    assert data["inner"]["state"] == ("answered_with_evidence" if case["expected_relation"] in {"supported", "refuted"} else "abstained")
    assert data["audit"]["blocked_reason"] is None and data["audit"]["callback_exception_type"] is None


def test_fixture_is_consumed_development_seven_semantic_refs_one_unavailable():
    """Eight dependent scripted controls must not become eight accuracy samples."""
    cases = controls()
    assert [case["case_id"] for case in cases] == [f"RP{index:02}" for index in range(1, 9)]
    assert sum(case["text"] is not None for case in cases) == 7
    assert cases[-1]["expected_relation"] == "unavailable"


def test_wrong_but_valid_refuted_is_not_repaired_or_verified():
    """The failed physical-value semantic pattern stays mechanically admissible."""
    case = controls()[0]
    assert case["expected_relation"] == "insufficient"
    script = Script(read(), assessed("refuted"))
    result = policy.run_relation_policy_followup(snapshot(case["text"]), case["claim"], callback=script)
    data = serialized(result, script)
    assert data["inner"]["state"] == "answered_with_evidence"
    assert data["inner"]["model_assessment"]["claim_relation"] == "refuted"


def padded_claim(base_size, target):
    extra = target - base_size
    assert extra >= 0
    return "q" + "陶" * (extra // 6) + "q" * (extra % 6)


@pytest.mark.parametrize("stage", [1, 2])
@pytest.mark.parametrize("text", ["Saved control text.", None])
@pytest.mark.parametrize("over", [0, 1])
def test_transformed_budget_old_preflight_passes_exact_limit_or_blocks_callback(stage, text, over):
    """Only the final transformed budget rejects +1, including after a real read."""
    replies = [read(padding=1200), assessed("insufficient" if text else "unavailable")] if stage == 2 else [final()]
    probe = Script(*replies)
    policy.run_relation_policy_followup(snapshot(text), "q", callback=probe)
    claim = padded_claim(len(canonical(probe.requests[stage - 1])), policy.MAX_CALLBACK_BYTES + over)
    base = Script(*replies)
    baseline = frozen.run_claim_relation_followup(snapshot(text), claim, transport=lambda **request: base(request))
    assert baseline.state != "failed" and len(base.requests) == stage
    assert all(len(canonical(request)) <= policy.MAX_CALLBACK_BYTES for request in base.requests)
    script = Script(*replies)
    result = policy.run_relation_policy_followup(snapshot(text), claim, callback=script)
    data = serialized(result, script)
    audit = data["audit"]
    assert data["inner"]["audit"]["callback_bytes"] == baseline.model_dump(mode="json")["audit"]["callback_bytes"]
    if over:
        assert data["inner"]["state"] == "failed"
        assert len(script.requests) == stage - 1
        assert audit["blocked_reason"] == "callback_budget_exceeded"
        assert audit["blocked_callback_bytes"] == 12 * 1024 + 1
        assert all(entry["read_result_reason"] is None for entry in audit["callback_entries"])
        assert all(not entry["delivered_read_ids"] for entry in audit["callback_entries"])
        if stage == 2:
            assert data["inner"]["audit"]["read_result_reason"] == ("ok" if text else "missing_text")
            assert bool(data["inner"]["served_evidence"]) is bool(text)
    else:
        assert data["inner"]["state"] == "abstained"
        assert len(script.requests) == stage
        assert audit["callback_entries"][-1]["request_bytes"] == 12 * 1024
        assert audit["blocked_reason"] is None and audit["blocked_callback_bytes"] is None


def test_configured_policy_does_not_claim_delivery_when_inner_blocks():
    """Old preflight rejection leaves configured policy but no entry or read facts."""
    script = Script()
    result = policy.run_relation_policy_followup(snapshot(), "陶" * 4096, callback=script)
    data = serialized(result, script)
    assert data["inner"]["state"] == "failed"
    assert data["inner"]["audit"]["catalog"]["refusal"] == "callback_budget_exceeded"
    assert data["audit"]["callback_entries"] == []
    assert data["audit"]["blocked_reason"] is None and data["audit"]["blocked_callback_bytes"] is None


@pytest.mark.parametrize("with_read", [False, True])
def test_callback_exception_preserves_entry_and_read_facts_not_message(with_read):
    """Entry survives a downstream exception without exposing its private message."""
    def explode(_request):
        raise RuntimeError("PRIVATE callback data must never escape")

    script = Script(*([read()] if with_read else []), explode)
    result = policy.run_relation_policy_followup(snapshot(), "Control.", callback=script)
    data = serialized(result, script)
    assert data["inner"]["state"] == "failed" and data["inner"]["answer"] is None
    assert data["audit"]["callback_exception_type"] == "RuntimeError"
    assert data["audit"]["blocked_reason"] is None
    assert bool(data["audit"]["callback_entries"][-1]["usable_read_ids"]) is with_read
    assert "PRIVATE callback" not in result.model_dump_json()


@pytest.mark.parametrize("text,offset,reason", [
    (None, 0, "missing_text"), ("", 0, "missing_text"), ("text", 4, "empty_window"),
    ("text", 99, "offset_out_of_range"), (" \t\n\u3000", 0, "ok"),
])
def test_no_usable_text_keeps_read_reason_without_promoting_receipt(text, offset, reason):
    """Whitespace receipts remain delivered, not usable; absence retains its cause."""
    script = Script(read(offset=offset), final())
    result = policy.run_relation_policy_followup(snapshot(text), "Control.", callback=script)
    data = serialized(result, script)
    entry = data["audit"]["callback_entries"][-1]
    assert data["inner"]["state"] == "abstained" and data["inner"]["read_status"] == "no_usable_text"
    assert entry["read_result_reason"] == reason and not entry["usable_read_ids"]
    assert bool(entry["delivered_read_ids"]) is (reason == "ok")


@pytest.mark.parametrize("with_read", [False, True])
def test_refusal_has_no_invented_assessment_or_extra_callback(with_read):
    """Early refusal must not fabricate a read or an unavailable model declaration."""
    script = Script(*([read()] if with_read else []), {"role": "assistant", "refusal": "No assessment."})
    data = serialized(policy.run_relation_policy_followup(snapshot(), "Control.", callback=script), script)
    assert data["inner"]["state"] == "abstained" and data["inner"]["model_assessment"] is None
    assert data["inner"]["answer"] == "No assessment."
    assert len(script.requests) == 1 + with_read


@pytest.mark.parametrize("content", [
    "{", '{"claim_relation":"unavailable","claim_relation":"supported"}',
    json.dumps({"claim_relation": "unavailable", "answer": "x", "supporting_evidence_ids": [], "caveats": [], "status": "abstained"}),
    json.dumps({"claim_relation": "unavailable", "answer": 3, "supporting_evidence_ids": [], "caveats": []}),
    json.dumps({"claim_relation": "unavailable", "answer": "x", "supporting_evidence_ids": [], "caveats": [3]}),
])
def test_malformed_final_is_not_relaxed(content):
    """A new prompt does not admit malformed/extra/coerced fields into frozen parsing."""
    script = Script({"role": "assistant", "content": content})
    data = serialized(policy.run_relation_policy_followup(snapshot(), "Control.", callback=script), script)
    assert data["inner"]["state"] == "failed" and data["inner"]["model_assessment"] is None
    assert data["inner"]["audit"]["refusal"] == "invalid_claim_relation_envelope"


@pytest.mark.parametrize("text,relation,ids,with_read", [
    ("text", "supported", ["ev_forged"], True), ("text", "refuted", ["A1"], True),
    ("text", "supported", [], False), ("text", "insufficient", [], False),
    ("text", "unavailable", [], True), (" \n\t", "insufficient", [], True),
])
def test_forged_ids_and_relation_receipt_mismatch_are_not_relaxed(text, relation, ids, with_read):
    """Legal JSON alone cannot manufacture delivery or usable text."""
    script = Script(*([read()] if with_read else []), final(relation, ids))
    data = serialized(policy.run_relation_policy_followup(snapshot(text), "Control.", callback=script), script)
    assert data["inner"]["state"] == "failed" and data["inner"]["model_assessment"] is None
    assert data["inner"]["audit"]["refusal"] == "claim_relation_receipt_mismatch"


@pytest.mark.parametrize("second", [False, True])
def test_unknown_source_and_second_read_do_not_buy_repair_turn(second):
    """The frozen one-read/visible-ID fence still terminates without another entry."""
    script = Script(*([read()] if second else []), read(source_id="A99"))
    data = serialized(policy.run_relation_policy_followup(snapshot(), "Control.", callback=script), script)
    assert data["inner"]["state"] == "failed"
    assert data["inner"]["audit"]["catalog"]["refusal"] == ("duplicate_tool_call_id" if second else "read_id_not_permitted")
    assert data["inner"]["audit"]["catalog"]["core"]["tool_executions"] == int(second)


@pytest.mark.parametrize("changed,reason", [
    ("claim", "claim_identity_mismatch"), ("instructions", "instruction_contract_mismatch"),
    ("duplicate_instructions", "instruction_contract_mismatch"), ("system_role", "instruction_contract_mismatch"),
])
def test_changed_claim_or_instruction_contract_blocks_at_actual_callback(monkeypatch, changed, reason):
    """A change between the frozen layer and policy bridge must fail before entry."""
    execute = frozen.run_claim_relation_followup
    observed = []

    def intercept(saved, claim, *, transport):
        def alter(**request):
            request = deepcopy(request)
            if changed == "claim":
                request["messages"][1]["content"] = claim.strip()
            elif changed == "instructions":
                request["messages"][0]["content"] = "Changed contract"
            elif changed == "duplicate_instructions":
                request["messages"][0]["content"] += frozen._NEW_FINAL
            else:
                request["messages"][0]["role"] = "user"
            return transport(**request)
        inner = execute(saved, claim, transport=alter)
        observed.append(inner)
        return inner

    monkeypatch.setattr(frozen, "run_claim_relation_followup", intercept)
    script = Script(final())
    result = policy.run_relation_policy_followup(snapshot(), " \n原始 proposition。\n ", callback=script)
    data = serialized(result, script)
    assert result.inner is observed[0]
    assert script.requests == []
    assert data["inner"]["state"] == "failed" and data["audit"]["blocked_reason"] == reason


def test_callback_mutation_cannot_rewrite_claim_history_receipts_or_audit():
    """Detached callback data and entry hashes survive malicious caller mutations."""
    saved = snapshot()
    claim = " \n虚构 control does not measure 5 V。\n "
    first_reply = read()

    def first(request):
        object.__setattr__(saved.sources[0], "summary", "Changed after admission")
        request["messages"][1]["content"] = "forged"
        request["messages"][0]["content"] = "forged system"
        request["messages"][2]["content"] = "forged catalog"
        request["tools"].clear()
        return first_reply

    def second(request):
        first_reply["tool_calls"][0]["function"]["arguments"] = "forged"
        assert request["messages"][1]["content"].encode() == claim.encode()
        assert request["messages"][-2]["tool_calls"][0]["function"]["arguments"] != "forged"
        tool = json.loads(request["messages"][-1]["content"])
        assert tool["text"] == "The fictional control measured exactly 3 V."
        tool.update(evidence_id="ev_forged", text="Forged text")
        request["messages"][-1]["content"] = json.dumps(tool)
        return final("supported", ["ev_forged"])

    script = Script(first, second)
    result = policy.run_relation_policy_followup(saved, claim, callback=script)
    data = serialized(result, script)
    assert data["inner"]["state"] == "failed"
    assert data["inner"]["audit"]["refusal"] == "claim_relation_receipt_mismatch"
    assert data["audit"]["callback_entries"][-1]["usable_read_ids"]
    assert data["inner"]["served_evidence"][0]["text"] == "The fictional control measured exactly 3 V."
    assert "ev_forged" not in result.model_dump_json()


def test_private_bridge_count_limit_cannot_record_third_read():
    """The policy layer's own count guard runs before recording a blocked read."""
    base = Script(read(), assessed("insufficient"))
    frozen.run_claim_relation_followup(snapshot(), "Control.", transport=lambda **request: base(request))
    script = Script(final(), final())
    bridge = policy._PolicyBridge("Control.", script)
    bridge(**base.requests[0])
    bridge(**base.requests[0])
    with pytest.raises(policy._PolicyRefusal, match="^callback_budget_exhausted$"):
        bridge(**base.requests[1])
    assert len(bridge.entries) == len(script.requests) == 2
    assert all(not entry.delivered_read_ids and entry.read_result_reason is None for entry in bridge.entries)


@pytest.mark.parametrize("callback", [None, lambda: None, lambda first, second: None, lambda **kwargs: None])
def test_invalid_signature_rejected_before_inner_executor(monkeypatch, callback):
    """A shape error cannot enter the inner executor or become a transport failure."""
    def forbidden(*args, **kwargs):
        pytest.fail("inner executor must not run")

    monkeypatch.setattr(frozen, "run_claim_relation_followup", forbidden)
    with pytest.raises(TypeError, match="^callback must accept one positional request object$"):
        policy.run_relation_policy_followup(snapshot(), "Control.", callback=callback)


def test_old_native_instance_rejected_without_ledger_or_http_mutation(tmp_path, monkeypatch):
    """The real old adapter must fail signature binding before stop/reserve/HTTP."""
    from academic_agent.report_evidence_claim_qwen_transport import ClaimQwenFollowupTransport, ClaimQwenLedger

    ledger = ClaimQwenLedger(tmp_path / "offline-ledger")
    native = ClaimQwenFollowupTransport("offline-test-key", ledger, snapshot=snapshot(), claim="Control.")
    before_files = {path.name: path.read_bytes() for path in ledger.output_dir.iterdir()}
    before_state = deepcopy(vars(ledger))
    native_state = deepcopy(vars(native))

    def forbidden(*args, **kwargs):
        pytest.fail("native dispatch or inner execution must not run")

    monkeypatch.setattr(native, "_post", forbidden)
    monkeypatch.setattr(frozen, "run_claim_relation_followup", forbidden)
    with pytest.raises(TypeError, match="^callback must accept one positional request object$"):
        policy.run_relation_policy_followup(snapshot(), "Control.", callback=native)
    assert vars(ledger) == before_state
    assert {path.name: path.read_bytes() for path in ledger.output_dir.iterdir()} == before_files
    assert native._requests == native_state["_requests"] == 0
    assert native._closed is native_state["_closed"] is False
    assert native._previous is None


@pytest.mark.parametrize("claim", ["", "x" * 4097, None, True])
def test_invalid_claim_keeps_frozen_construction_error(claim):
    """Invalid caller input raises, without fabricating a failed model assessment."""
    script = Script()
    with pytest.raises(ValueError, match="claim must contain 1..4096 characters"):
        policy.run_relation_policy_followup(snapshot(), claim, callback=script)
    assert not script.requests
