"""Bounded offline preparation for fresh claim-proposition contrast controls.

The fixture's author labels stay outside blind-review inputs and are not
semantic proof. This module only rehearses the existing callback seam with scripted
responses; it has no provider, credential, persistence, or production path.
"""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from academic_agent.report_evidence_claim_relation import (
    ClaimRelationFollowupResult,
    run_claim_relation_followup,
)
from academic_agent.report_evidence_snapshot import (
    CONTENT_WARNING, FrozenModel, ReportEvidenceSnapshot, SnapshotSource, content_hash,
)


FIXTURE_SHA256 = "bfc9347b28a7d284b8d959c93a038a14f1c15c9adb0d3394c9c6463012141c78"
FIXTURE_STATUS = "draft_before_llm_review"
# The bytes were frozen after the separate blind review.  Keep the original
# provenance status inside the immutable fixture rather than rewriting it.
FREEZE_RECORD = "fixture_bytes_frozen_after_blind_review"
DEFAULT_FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "report_evidence_claim_contrast.json"


class ContrastSource(FrozenModel):
    source_id: Literal["A1"]
    group: Literal["academic"]
    title: str = Field(min_length=1, max_length=1024)
    summary: str = Field(min_length=1, max_length=1499)
    publisher: str = Field(min_length=1, max_length=512)
    source_type: str = Field(min_length=1, max_length=64)
    accessed_date: str = Field(min_length=1, max_length=32)

    @field_validator("summary")
    @classmethod
    def _summary_is_usable(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("summary must be nonblank")
        return value


class ContrastCase(FrozenModel):
    case_id: Literal["PCQ01", "PCQ02", "PCQ03"]
    claim: str = Field(min_length=1, max_length=4096)
    source: ContrastSource
    expected_relation: Literal["supported", "refuted", "insufficient"]
    proposition_kind: Literal["physical_value", "record_contents"]
    reference_rationale: str = Field(min_length=1, max_length=2000)
    scripted_answer: str = Field(min_length=1, max_length=8000)


class ContrastDraft(FrozenModel):
    schema_version: Literal[1]
    cohort_id: Literal["claim_proposition_contrast_v1"]
    origin: Literal["author_generated_synthetic"]
    status: Literal["draft_before_llm_review"]
    cases: tuple[ContrastCase, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def _control_shape_is_fixed(self) -> "ContrastDraft":
        if tuple(case.case_id for case in self.cases) != ("PCQ01", "PCQ02", "PCQ03"):
            raise ValueError("PCQ cases must be ordered PCQ01..PCQ03")
        if self.cases[0].source.model_dump() != self.cases[1].source.model_dump():
            raise ValueError("PCQ01 and PCQ02 must retain the same source by value")
        return self


def load_draft(path: Path = DEFAULT_FIXTURE) -> ContrastDraft:
    """Load only the exact hash-bound repository fixture, detached from disk."""
    path = Path(path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
        raise ValueError("claim contrast fixture SHA256 mismatch")
    # JSON arrays validate as immutable tuples through the JSON entry point;
    # Python-mode strict validation correctly rejects a decoded mutable list.
    return ContrastDraft.model_validate_json(raw)


def project_review_input(cases: Sequence[ContrastCase]) -> dict:
    """Project only blind-review inputs; labels and rationales never cross this seam."""
    projected = {
        "schema_version": 1,
        "cases": [
            {"case_id": case.case_id, "claim": case.claim,
             "source": {"title": case.source.title, "text": case.source.summary}}
            for case in cases
        ],
    }
    # JSON round-tripping prevents a caller receiving model-owned references.
    return json.loads(json.dumps(projected, ensure_ascii=True, allow_nan=False))


def _snapshot(case: ContrastCase) -> ReportEvidenceSnapshot:
    source = SnapshotSource(**case.source.model_dump())
    return ReportEvidenceSnapshot(report_ref=f"offline-{case.case_id}", sources=(source,))


class _ScriptedTransport:
    """Two native-shaped callback replies, recording the requests actually received."""

    def __init__(self, case: ContrastCase):
        self.case = case
        self.requests: list[dict] = []
        self.responses: list[dict] = []

    def __call__(self, **request: object) -> dict:
        captured = deepcopy(request)
        self.requests.append(captured)
        if len(self.requests) == 1:
            response = {"role": "assistant", "content": None, "tool_calls": [{
                "id": f"{self.case.case_id}_read", "type": "function",
                "function": {"name": "read_source", "arguments": json.dumps({
                    "source_id": self.case.source.source_id, "offset": 0, "length": 1500,
                })},
            }]}
        elif len(self.requests) == 2:
            response = self._final_reply(json.loads(captured["messages"][-1]["content"]))
        else:
            raise AssertionError("scripted callback exceeded two requests")
        self.responses.append(deepcopy(response))
        return response

    def _final_reply(self, receipt: dict) -> dict:
        relation = self.case.expected_relation
        ids = [receipt["evidence_id"]] if relation in {"supported", "refuted"} else []
        return {"role": "assistant", "content": json.dumps({
            "claim_relation": relation, "answer": self.case.scripted_answer,
            "supporting_evidence_ids": ids, "caveats": ["Scripted offline transport; semantic accuracy is not assessed."],
        })}


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _json_object(raw: object) -> dict:
    """Malformed captured messages are failed checks, not an empty successful read."""
    try:
        value = json.loads(raw) if type(raw) is str else None
    except ValueError:
        return {}
    return value if type(value) is dict else {}


def _expected_evidence(case: ContrastCase) -> dict:
    """Bind the full saved window without issuing an extra read for the oracle."""
    snapshot = _snapshot(case)
    source = snapshot.sources[0]
    payload = {
        "source_id": source.source_id, "snapshot_hash": snapshot.snapshot_hash,
        "source_hash": snapshot.source_hash(source), "summary_hash": content_hash(source.summary),
        "origin": source.origin, "start": 0, "end": len(source.summary),
        "stored_length": len(source.summary), "text": source.summary,
        "text_sha256": hashlib.sha256(source.summary.encode("utf-8")).hexdigest(),
        "window_truncated": False, "text_scope": "saved_summary_only",
    }
    return {**payload, "evidence_id": "ev_" + content_hash(payload)}


def _check_result(case: ContrastCase, result: ClaimRelationFollowupResult, transport: _ScriptedTransport) -> dict:
    """Check observed delivery and scripted label agreement, never semantic truth.

    A wrong but receipt-valid relation can pass the immutable wrapper. Only the
    reference comparison catches that rehearsal mismatch; it is not a verifier.
    """
    encoded = result.model_dump_json()
    serialized = ClaimRelationFollowupResult.model_validate_json(encoded)
    observed = json.loads(encoded)
    requests, responses = transport.requests, transport.responses
    first = requests[0] if requests else {}
    second = requests[1] if len(requests) >= 2 else {}
    first_reply = responses[0] if responses else {}
    calls = first_reply.get("tool_calls") or []
    call = calls[0] if len(calls) == 1 else {}
    function = call.get("function", {})
    messages = second.get("messages", [])
    tool = messages[-1] if messages else {}
    receipt = _json_object(tool.get("content"))
    final = _json_object(responses[1].get("content")) if len(responses) >= 2 else {}
    expected = _expected_evidence(case)
    read_ids = [receipt["evidence_id"]] if type(receipt.get("evidence_id")) is str else []
    assessment = serialized.model_assessment
    relation = assessment.claim_relation if assessment else None
    ids = list(assessment.supporting_evidence_ids) if assessment else None
    # State/citation consistency follows the OBSERVED declaration, separately
    # from its match to the author reference. Neither check infers entailment.
    answered = relation in {"supported", "refuted"}
    audit = serialized.audit
    catalog, core = audit.catalog, audit.catalog.core
    # The serializer can emit 1 for a model_copy-injected True in an int field.
    # Check runtime counter types too, before that normalization hides damage.
    raw_core = result.audit.catalog.core
    counter_types = all(type(value) is int for value in (
        result.audit.downstream_calls, result.audit.catalog.downstream_calls,
        raw_core.transport_turns, raw_core.observed_tool_requests,
        raw_core.tool_attempts, raw_core.tool_executions, raw_core.tool_errors,
    )) and raw_core.no_tools is False
    checks = {
        "two_callbacks": len(requests) == len(responses) == 2,
        "serialized_claim": serialized.claim == case.claim and all(
            request.get("messages", [])[1:2] == [{"role": "user", "content": case.claim}]
            for request in requests
        ),
        "serialized_answer": assessment is not None and serialized.answer == assessment.answer == case.scripted_answer,
        "serialized_assessment": assessment is not None and assessment.model_dump() == final,
        "native_read_request": len(calls) == 1 and call.get("type") == "function"
        and type(call.get("id")) is str and function.get("name") == "read_source"
        and _canonical(_json_object(function.get("arguments"))) == _canonical({
            "source_id": case.source.source_id, "offset": 0, "length": 1500,
        }),
        "second_callback_pairing": len(messages) == 5 and messages[-2] == first_reply
        and messages[1:3] == first.get("messages", [])[1:3]
        and tool.get("role") == "tool" and tool.get("tool_call_id") == call.get("id"),
        "final_only": second.get("tools") == [] and second.get("tool_choice") == "none",
        "second_callback_receipt": _canonical(receipt) == _canonical({
            **expected, "status": "ok", "content_warning": CONTENT_WARNING,
        }),
        "serialized_relation_matches_author_label": relation == case.expected_relation,
        "derived_state": relation in {"supported", "refuted", "insufficient"}
        and serialized.state == ("answered_with_evidence" if answered else "abstained"),
        "evidence_ids": ids == (read_ids if answered else []),
        "usable_read_propagated": serialized.read_status == "usable_text" and audit.read_result_reason == "ok"
        and list(audit.usable_read_ids) == read_ids and len(read_ids) == 1,
        "read_identity": len(read_ids) == 1 and list(audit.delivered_read_ids)
        == list(catalog.forwarded_read_ids) == list(core.delivered_read_ids)
        == [item.evidence_id for item in serialized.served_evidence] == read_ids,
        "served_text_receipt": [item.model_dump() for item in serialized.served_evidence] == [expected],
        "read_counters": counter_types and audit.downstream_calls == catalog.downstream_calls == core.transport_turns == 2
        and core.observed_tool_requests == core.tool_attempts == core.tool_executions == 1
        and core.tool_errors == 0 and core.no_tools is False and list(core.call_ids) == [call.get("id")],
        "catalog_observation": [item.model_dump() for item in catalog.tool_results] == [{
            "call_id": call.get("id"), "status": "ok", "evidence_id": receipt.get("evidence_id"),
        }] and catalog.advertised_tools == (("read_source",), ()),
        "callback_bytes": list(audit.callback_bytes) == [len(_canonical(request).encode("ascii")) for request in requests],
        "no_refusals": audit.refusal is None and catalog.refusal is None
        and audit.downstream_exception_type is None and catalog.downstream_exception_type is None
        and audit.blocked_callback_bytes is None and catalog.blocked_callback_bytes is None
        and core.exception_type is None and core.terminal_reason == ("final_answer" if answered else "model_abstained"),
        "invariants": serialized.semantic_support == "not_assessed" and serialized.answer_verification == "not_verified"
        and serialized.assessment_origin == "injected_transport_unverified",
    }
    return {
        "case_id": case.case_id, "mechanical_passed": all(checks.values()),
        "label_match_observed": checks["serialized_relation_matches_author_label"],
        "semantic_accuracy": "not_assessed", "origin": "scripted", "checks": checks,
        "observed": observed, "callback_receipt": receipt,
    }


def rehearse(cases: Sequence[ContrastCase]) -> dict:
    """Run the immutable wrapper against scripted callbacks and report offline observations."""
    cases = tuple(cases)
    # A subset or caller-modified control can exercise the seam, but cannot
    # inherit the complete hash-verified cohort's review/freeze provenance.
    frozen_match = cases == load_draft().cases
    observations = []
    for case in cases:
        transport = _ScriptedTransport(case)
        result = run_claim_relation_followup(_snapshot(case), case.claim, transport=transport)
        observations.append(_check_result(case, result, transport))
    return {
        "mode": "offline_scripted_rehearsal",
        "rehearsal_scope": "hash_verified_fixture_cases" if frozen_match else "caller_supplied_cases_not_frozen",
        "fixture_status": FIXTURE_STATUS if frozen_match else None,
        "fixture_sha256": FIXTURE_SHA256 if frozen_match else None,
        "freeze_record": FREEZE_RECORD if frozen_match else None, "provider_calls": 0,
        "semantic_accuracy": "not_assessed", "origin": "scripted",
        "cases": observations, "mechanical_passed": bool(observations) and all(item["mechanical_passed"] for item in observations),
    }
