"""Offline claim-relation wrapper over the immutable catalog callback executor.

This is deliberately a callback-only engineering seam.  It changes neither
the catalog/core loops nor their native read pairing, and does not attest that
the scripted relation is semantically correct.
"""

from collections.abc import Callable
from copy import deepcopy
import json
from typing import Literal

from pydantic import Field, field_validator

from academic_agent import report_evidence_catalog_followup as catalog
from academic_agent import report_evidence_followup as core
from academic_agent.report_evidence_snapshot import FrozenModel, ReportEvidenceSnapshot

METHOD_ID = "report_evidence_claim_relation_v1"
MAX_CALLBACK_BYTES = catalog.MAX_CALLBACK_BYTES
MAX_CALLBACK_REQUESTS = catalog.MAX_CALLBACK_REQUESTS


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


class ClaimAssessment(FrozenModel):
    """The model declaration, retained but never promoted to semantic proof."""

    claim_relation: Literal["supported", "refuted", "insufficient", "unavailable"]
    answer: str = Field(min_length=1, max_length=8000)
    supporting_evidence_ids: list[str] = Field(max_length=1)
    caveats: list[str] = Field(max_length=8)

    @field_validator("caveats")
    @classmethod
    def _bounded_caveats(cls, value: list[str]) -> list[str]:
        if any(type(item) is not str or not 1 <= len(item) <= 512 for item in value):
            raise ValueError("caveats must contain 1..512-character strings")
        return value


class ClaimRelationAudit(FrozenModel):
    """Actual callback facts; nested catalog/core facts precede this boundary."""

    method_id: Literal["report_evidence_claim_relation_v1"] = METHOD_ID
    catalog: catalog.CatalogAudit
    callback_bytes: tuple[int, ...]
    blocked_callback_bytes: int | None
    downstream_calls: int
    delivered_read_ids: tuple[str, ...]
    usable_read_ids: tuple[str, ...]
    read_result_reason: str | None
    refusal: str | None
    downstream_exception_type: str | None


class ClaimRelationFollowupResult(FrozenModel):
    claim: str
    state: Literal["answered_with_evidence", "abstained", "failed"]
    answer: str | None
    model_assessment: ClaimAssessment | None
    served_evidence: tuple[core.ServedEvidence, ...]
    read_status: Literal["not_checked", "no_usable_text", "usable_text"]
    semantic_support: Literal["not_assessed"] = "not_assessed"
    answer_verification: Literal["not_verified"] = "not_verified"
    assessment_origin: Literal["injected_transport_unverified"] = "injected_transport_unverified"
    audit: ClaimRelationAudit


class _ClaimRefusal(RuntimeError):
    pass


_OLD_FINAL = (
    "Return a JSON object with exactly answer (string), status (answered or abstained), "
    "and evidence_ids (array). Cite only evidence IDs returned by successful reads, "
    "not source IDs or lookup hits. Use an empty array if no read supports your answer. "
    "This protocol does not assess semantic support. "
)
_NEW_FINAL = (
    "The caller-owned proposition is the verbatim user message. Return a JSON object with exactly "
    "claim_relation (supported, refuted, insufficient, or unavailable), answer (1..8000 characters), "
    "supporting_evidence_ids (array, at most one), and caveats (0..8 strings, each 1..512 characters). "
    "Supported means evidence supports that same claim, conditions and scope. Refuted means evidence "
    "supports a conclusion incompatible with that claim. Both require one cited usable read receipt "
    "supporting the declared relation. Insufficient means usable evidence establishes neither support "
    "nor refutation, and requires a usable read with no IDs. Unavailable means no usable read reached "
    "this callback, and requires no IDs; it does not establish absence in all literature. "
    "Usable means a successful nonblank saved-text read, not semantic relevance or entailment. "
    "Relations concern the original proposition, not positive or negative answer wording. "
    "Cite only IDs returned by actual usable reads, never source IDs or catalog metadata. "
    "Do not supply status. This protocol does not verify semantic support or refutation. "
)


class _ClaimTransport:
    """Detach/replace callback requests and translate only an admitted final."""

    def __init__(self, claim: str, transport: Callable[..., object]):
        self.claim = claim
        self.transport = transport
        self.callback_bytes: list[int] = []
        self.blocked_callback_bytes: int | None = None
        self.delivered: list[str] = []
        self.usable: list[str] = []
        self.read_result_reason: str | None = None
        self.refusal: str | None = None
        self.downstream_exception_type: str | None = None
        self.assessment: ClaimAssessment | None = None

    def _reject(self, reason: str) -> None:
        self.refusal = reason
        raise _ClaimRefusal(reason)

    def _record_read(self, request: dict) -> None:
        messages = request["messages"]
        if len(messages) < 2 or messages[-1].get("role") != "tool":
            return
        try:
            tool_result = core._strict_json(messages[-1]["content"])
        except (KeyError, TypeError, ValueError, RecursionError):
            self._reject("tool_result_invalid")
        if type(tool_result) is not dict or type(tool_result.get("status")) is not str:
            self._reject("tool_result_invalid")
        if tool_result["status"] == "ok":
            evidence_id = tool_result.get("evidence_id")
            text = tool_result.get("text")
            if type(evidence_id) is not str or type(text) is not str:
                self._reject("tool_result_invalid")
            self.delivered[:] = [evidence_id]
            # The frozen reader issues a receipt for whitespace too. Keep its
            # delivered bytes, but never mistake them for usable claim evidence.
            self.usable[:] = [evidence_id] if text.strip() else []
        self.read_result_reason = tool_result["status"]

    def _translate_final(self, response: object) -> object:
        try:
            message = core._assistant_message(response)
        except (ValueError, TypeError, RecursionError):
            self._reject("invalid_assistant_message")
        if message.get("refusal") or message.get("tool_calls"):
            return message
        try:
            parsed = core._strict_json(message.get("content") or "")
            assessment = ClaimAssessment.model_validate(parsed)
        except (ValueError, TypeError, RecursionError):
            self._reject("invalid_claim_relation_envelope")
        ids = assessment.supporting_evidence_ids
        usable = bool(self.usable)
        relation = assessment.claim_relation
        consistent = (
            relation in {"supported", "refuted"} and usable and ids == self.usable
        ) or (relation == "insufficient" and usable and not ids) or (
            relation == "unavailable" and not usable and not ids
        )
        if not consistent:
            self._reject("claim_relation_receipt_mismatch")
        old = {
            "answer": assessment.answer,
            "status": "answered" if relation in {"supported", "refuted"} else "abstained",
            "evidence_ids": ids,
        }
        if len(_canonical(old)) > core.MAX_MESSAGE_CHARS:
            self._reject("translated_final_budget_exceeded")
        self.assessment = assessment
        return {"role": "assistant", "content": _canonical(old)}

    def __call__(self, **request: object) -> object:
        outgoing = deepcopy(request)
        messages = outgoing.get("messages")
        if type(messages) is not list or len(messages) < 2 or messages[1] != {"role": "user", "content": self.claim}:
            self._reject("claim_identity_mismatch")
        system = messages[0]
        if type(system) is not dict or type(system.get("content")) is not str or _OLD_FINAL not in system["content"]:
            self._reject("final_instruction_not_replaceable")
        system["content"] = system["content"].replace(_OLD_FINAL, _NEW_FINAL, 1)
        size = len(_canonical(outgoing).encode("ascii"))
        if size > MAX_CALLBACK_BYTES:
            self.blocked_callback_bytes = size
            self._reject("callback_budget_exceeded")
        if len(self.callback_bytes) >= MAX_CALLBACK_REQUESTS:
            self._reject("callback_budget_exhausted")
        # This is the sole actual-delivery point: catalog preflight and this
        # transformed-request bound have both passed, immediately before entry.
        self._record_read(outgoing)
        self.callback_bytes.append(size)
        try:
            raw = self.transport(**outgoing)
        except Exception as exc:  # noqa: BLE001 -- retain only type, never callback text.
            self.downstream_exception_type = type(exc).__name__
            raise _ClaimRefusal("downstream_transport_error") from None
        return self._translate_final(raw)


def run_claim_relation_followup(
    snapshot: ReportEvidenceSnapshot, claim: str, *, transport: Callable[..., object],
) -> ClaimRelationFollowupResult:
    """Assess one verbatim caller claim through the immutable catalog callback path.

    No provider, key, persistence, retry, CLI, or semantic verification is
    introduced.  Any malformed/contradictory declaration fails closed.
    """
    if type(claim) is not str or not 1 <= len(claim) <= 4096:
        raise ValueError("claim must contain 1..4096 characters")
    snapshot = ReportEvidenceSnapshot.model_validate(snapshot.model_dump())
    bridge = _ClaimTransport(claim, transport)
    inner = catalog.run_catalog_followup(snapshot, claim, transport=bridge)
    failed = inner.state == "failed" or bridge.refusal is not None or bridge.downstream_exception_type is not None
    read_status = "usable_text" if bridge.usable else (
        "no_usable_text" if bridge.read_result_reason is not None else "not_checked"
    )
    state = "failed" if failed else (
        "answered_with_evidence" if bridge.assessment and bridge.assessment.claim_relation in {"supported", "refuted"}
        else "abstained"
    )
    served = tuple(item for item in inner.served_evidence if item.evidence_id in bridge.delivered)
    return ClaimRelationFollowupResult(
        claim=claim, state=state, answer=None if failed else inner.answer,
        model_assessment=None if failed else bridge.assessment,
        served_evidence=served, read_status=read_status,
        audit=ClaimRelationAudit(
            catalog=inner.audit, callback_bytes=tuple(bridge.callback_bytes),
            blocked_callback_bytes=bridge.blocked_callback_bytes, downstream_calls=len(bridge.callback_bytes),
            delivered_read_ids=tuple(bridge.delivered), usable_read_ids=tuple(bridge.usable),
            read_result_reason=bridge.read_result_reason,
            refusal=bridge.refusal, downstream_exception_type=bridge.downstream_exception_type,
        ),
    )
