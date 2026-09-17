"""Bounded PCQ preparation tests at the offline callback and review seams."""

from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

from pydantic import ValidationError
import pytest

from academic_agent import report_evidence_claim_contrast as contrast
from academic_agent import report_evidence_followup as core


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """A swallowed network exception must still fail this offline-only suite."""
    attempts = []

    def denied(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("PCQ must not dispatch network traffic")

    for target, name in ((socket, "create_connection"), (socket, "getaddrinfo"),
                         (socket.socket, "connect"), (socket.socket, "connect_ex")):
        monkeypatch.setattr(target, name, denied)
    yield
    assert not attempts


def _run_case(case):
    transport = contrast._ScriptedTransport(case)
    result = contrast.run_claim_relation_followup(contrast._snapshot(case), case.claim, transport=transport)
    return result, transport


def test_load_is_hash_bound_strict_and_immutable(tmp_path):
    """JSON arrays must load as frozen tuples without weakening Python strictness."""
    draft = contrast.load_draft()
    assert draft.status == "draft_before_llm_review" and type(draft.cases) is tuple and len(draft.cases) == 3
    with pytest.raises(ValidationError, match="tuple_type"):
        contrast.ContrastDraft.model_validate(json.loads(contrast.DEFAULT_FIXTURE.read_bytes()))
    with pytest.raises(ValidationError, match="frozen_instance"):
        draft.cases[0].claim = "changed"
    changed = tmp_path / "tampered.json"
    changed.write_bytes(contrast.DEFAULT_FIXTURE.read_bytes() + b" ")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        contrast.load_draft(changed)


def test_projector_is_exact_detached_allowlist():
    """Missing/changed claims and leaked author labels both break the blind seam."""
    cases = contrast.load_draft().cases
    projected = contrast.project_review_input(cases)
    assert projected == {"schema_version": 1, "cases": [
        {"case_id": case.case_id, "claim": case.claim,
         "source": {"title": case.source.title, "text": case.source.summary}}
        for case in cases
    ]}
    serialized = json.dumps(projected)
    for case in cases:
        assert case.reference_rationale not in serialized and case.scripted_answer not in serialized
    assert all(word not in serialized for word in ("expected_relation", "reference_rationale", "proposition_kind", "scripted_answer"))
    projected["cases"][0]["source"]["text"] = "changed"
    assert cases[0].source.summary != "changed"


def test_rehearsal_observes_real_reads_and_insufficient_abstention(monkeypatch):
    """The exact local read reaches callback two, including usable-but-insufficient PCQ01."""
    cases = contrast.load_draft().cases
    reads = []
    original = core.read_source

    def record_read(snapshot, **arguments):
        receipt = original(snapshot, **arguments)
        reads.append((snapshot, arguments, deepcopy(receipt)))
        return receipt

    monkeypatch.setattr(core, "read_source", record_read)
    output = contrast.rehearse(cases)
    assert output["provider_calls"] == 0 and output["semantic_accuracy"] == "not_assessed"
    assert output["rehearsal_scope"] == "hash_verified_fixture_cases"
    assert output["fixture_sha256"] == contrast.FIXTURE_SHA256
    assert output["fixture_status"] == "draft_before_llm_review" and output["freeze_record"] == contrast.FREEZE_RECORD
    assert output["mechanical_passed"] is True and len(reads) == 3
    for case, row, (snapshot, arguments, local_receipt) in zip(cases, output["cases"], reads, strict=True):
        assert arguments == {"source_id": "A1", "offset": 0, "length": 1500}
        assert snapshot.sources[0].summary == case.source.summary
        assert all(type(value) is bool and value for value in row["checks"].values())
        receipt = row["callback_receipt"]
        assert {key: value for key, value in receipt.items() if key != "evidence_id"} == local_receipt
        observed = row["observed"]
        assert observed["claim"] == case.claim and observed["answer"] == case.scripted_answer
        assert observed["read_status"] == "usable_text" and receipt["source_id"] == "A1"
        ids = [receipt["evidence_id"]]
        assert observed["audit"]["delivered_read_ids"] == observed["audit"]["usable_read_ids"] == ids
        assert observed["served_evidence"][0]["evidence_id"] == ids[0]
        assert observed["served_evidence"][0]["text"] == receipt["text"] == case.source.summary
        assessment = observed["model_assessment"]
        assert assessment["claim_relation"] == case.expected_relation
        assert assessment["supporting_evidence_ids"] == ([] if case.case_id == "PCQ01" else ids)
        assert observed["state"] == ("abstained" if case.case_id == "PCQ01" else "answered_with_evidence")


def test_false_semantic_relation_is_sent_by_callback_and_admitted_unverified(monkeypatch):
    """PCQ03's actual callback can falsely declare refutation with a valid receipt."""
    class FalseRelation(contrast._ScriptedTransport):
        def _final_reply(self, receipt):
            response = super()._final_reply(receipt)
            payload = json.loads(response["content"])
            payload["claim_relation"] = "refuted"
            response["content"] = json.dumps(payload)
            return response

    monkeypatch.setattr(contrast, "_ScriptedTransport", FalseRelation)
    output = contrast.rehearse(contrast.load_draft().cases[2:])
    row = output["cases"][0]
    observed = row["observed"]
    assert observed["state"] == "answered_with_evidence"
    assert observed["model_assessment"]["claim_relation"] == "refuted"
    assert observed["model_assessment"]["supporting_evidence_ids"] == [row["callback_receipt"]["evidence_id"]]
    assert observed["semantic_support"] == "not_assessed" and observed["answer_verification"] == "not_verified"
    assert observed["assessment_origin"] == "injected_transport_unverified"
    assert [name for name, passed in row["checks"].items() if not passed] == ["serialized_relation_matches_author_label"]
    assert output["mechanical_passed"] is False and row["label_match_observed"] is False
    assert row["semantic_accuracy"] == "not_assessed"


def test_caller_modified_or_subset_cases_do_not_inherit_freeze_identity():
    """A correct scripted rehearsal is not proof that arbitrary caller cases were frozen."""
    cases = contrast.load_draft().cases
    changed = cases[0].model_copy(update={"claim": "A different caller-owned claim."})
    for candidate in (cases[:1], (changed, *cases[1:]), ()):
        output = contrast.rehearse(candidate)
        assert output["rehearsal_scope"] == "caller_supplied_cases_not_frozen"
        assert output["fixture_sha256"] is output["fixture_status"] is output["freeze_record"] is None
    assert output["mechanical_passed"] is False


def _replace(data, path, value):
    for key in path[:-1]:
        data = data[key]
    data[path[-1]] = value


@pytest.mark.parametrize("path,value,gate", [
    (("claim",), "Changed claim", "serialized_claim"),
    (("answer",), "Changed answer", "serialized_answer"),
    (("model_assessment", "answer"), "Changed assessment", "serialized_answer"),
    (("state",), "abstained", "derived_state"),
    (("model_assessment", "supporting_evidence_ids"), [], "evidence_ids"),
    (("audit", "delivered_read_ids"), ["ev_wrong"], "read_identity"),
    (("served_evidence", 0, "evidence_id"), "ev_wrong", "read_identity"),
    (("served_evidence", 0, "text"), "Wrong source bytes", "served_text_receipt"),
    (("read_status",), "not_checked", "usable_read_propagated"),
    (("audit", "catalog", "core", "tool_executions"), 0, "read_counters"),
    (("audit", "downstream_calls"), 1, "read_counters"),
])
def test_serialized_seam_damage_fails_gate(path, value, gate):
    """Schema-valid delivery damage must not pass because the scripted label matches."""
    case = contrast.load_draft().cases[2]
    result, transport = _run_case(case)
    data = json.loads(result.model_dump_json())
    _replace(data, path, value)
    damaged = contrast.ClaimRelationFollowupResult.model_validate_json(json.dumps(data))
    row = contrast._check_result(case, damaged, transport)
    assert row["checks"][gate] is False and row["mechanical_passed"] is False
    assert row["label_match_observed"] is True
    assert all(type(value) is bool for value in row["checks"].values())


@pytest.mark.parametrize("path,value,gate", [
    (("messages", 1, "content"), "Different claim", "serialized_claim"),
    (("messages", 3, "tool_calls", 0, "function", "name"), "lookup_sources", "second_callback_pairing"),
    (("messages", 4, "tool_call_id"), "unpaired", "second_callback_pairing"),
    (("tools",), [{"name": "read_source"}], "final_only"),
    (("tool_choice",), "auto", "final_only"),
    (("messages", 4, "content"), '{"status":"ok","source_id":"A2","evidence_id":"ev_wrong"}', "second_callback_receipt"),
    (("messages", 4, "content"), "{", "second_callback_receipt"),
])
def test_captured_second_callback_damage_fails_gate(path, value, gate):
    """Offering tools and a successful result alone do not prove a paired final-only read."""
    case = contrast.load_draft().cases[2]
    result, transport = _run_case(case)
    _replace(transport.requests[1], path, value)
    row = contrast._check_result(case, result, transport)
    assert row["checks"][gate] is False and row["mechanical_passed"] is False


def test_serialized_boolean_counter_cannot_masquerade_as_one():
    """A serializer-normalized bool must not pass the integer read-counter gate."""
    case = contrast.load_draft().cases[2]
    result, transport = _run_case(case)
    damaged_core = result.audit.catalog.core.model_copy(update={"tool_executions": True})
    damaged_catalog = result.audit.catalog.model_copy(update={"core": damaged_core})
    damaged_audit = result.audit.model_copy(update={"catalog": damaged_catalog})
    row = contrast._check_result(case, result.model_copy(update={"audit": damaged_audit}), transport)
    assert row["checks"]["read_counters"] is False and row["mechanical_passed"] is False


def _cli(*args, force_failure=False):
    root = Path(__file__).resolve().parents[1]
    # A subprocess does not inherit pytest's guards. Supply only OS plumbing and
    # dummy provider values, and assert even a swallowed dispatch is detected.
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "PATH") if key in os.environ}
    env.update(PYTHONPATH=str(root / "src"), PYTHONDONTWRITEBYTECODE="1",
               OPENAI_API_KEY="dummy-offline-only", DASHSCOPE_API_KEY="dummy-offline-only", LLM_PROVIDER="qwen")
    program = '''
import runpy, socket, sys
attempts = []
def denied(*args, **kwargs):
    attempts.append(True)
    raise AssertionError("PCQ network dispatch attempted")
socket.create_connection = socket.getaddrinfo = denied
socket.socket.connect = socket.socket.connect_ex = denied
if sys.argv.pop(1) == "fail":
    import academic_agent.report_evidence_claim_contrast as contrast
    contrast.rehearse = lambda cases: {"mechanical_passed": False, "provider_calls": 0}
sys.argv[0] = "report_evidence_contrast_check.py"
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
finally:
    assert not attempts, "PCQ attempted network dispatch"
'''
    return subprocess.run([sys.executable, "-c", program, "fail" if force_failure else "normal", *args],
                          cwd=root, env=env, check=False, text=True, capture_output=True, timeout=30)


def test_cli_json_and_blind_review_are_offline():
    """Both public CLI modes succeed with dispatch guards and dummy credentials only."""
    completed = _cli()
    assert completed.returncode == 0, completed.stderr
    output = json.loads(completed.stdout)
    assert output["provider_calls"] == 0 and output["mechanical_passed"] is True
    review = _cli("--review-input")
    assert review.returncode == 0, review.stderr
    assert json.loads(review.stdout) == contrast.project_review_input(contrast.load_draft().cases)


def test_cli_nonpass_exits_nonzero_and_has_no_live_flag():
    """Printing a failed JSON result must not signal successful validation to a caller."""
    failed = _cli(force_failure=True)
    assert failed.returncode == 1 and json.loads(failed.stdout)["mechanical_passed"] is False
    unknown = _cli("--live")
    assert unknown.returncode == 2 and "unrecognized arguments: --live" in unknown.stderr
