"""Offline explicit relation instructions around the frozen claim executor.

Only the detached system message changes. Callback entry is not HTTP delivery
or semantic verification; arbitrary injected callback code is not sandboxed.
No fixtures, reference labels, provider adapters or persistence are loaded.
"""

from collections.abc import Callable
from copy import deepcopy
import hashlib
import inspect
import json

from academic_agent import report_evidence_claim_relation as claim_relation
from academic_agent import report_evidence_followup as core
from academic_agent.report_evidence_snapshot import FrozenModel, ReportEvidenceSnapshot

POLICY_ID = "report_evidence_relation_policy_v1"
POLICY_APPEND = (
    "\nExplicit claim-relation policy v1: Retain the caller proposition verbatim. "
    "Assess its subject, conditions, time, scope and negation; do not rephrase a physical-value "
    "claim into a claim that a record reports that value. "
    "With no usable delivered read, declare unavailable, not absence of relevant literature. "
    "With usable text, supported requires the same proposition established by that text. "
    "Refuted requires an incompatible proposition under the same subject and conditions; "
    "a different subject or condition is not refutation. "
    "No measurement, no mention or lack of support for a physical property does not show it "
    "is false. Use insufficient when neither side is established, including unresolved scope ambiguity. "
    "An explicit statement that a record contains no measurement may refute a claim that this "
    "record reports that measurement. Mere omission from a saved excerpt does not prove the "
    "complete source lacks it. Honor claim negation; negative answer wording alone does not "
    "determine the relation. Metadata and titles are not evidence. "
    "Supported/refuted require exactly one actual usable read receipt. Insufficient requires "
    "a usable read and no supporting IDs; unavailable requires no usable read and no IDs. "
    "Keep the four-field JSON contract unchanged. Semantic correctness remains unverified."
)
POLICY_HASH = hashlib.sha256(POLICY_APPEND.encode("utf-8")).hexdigest()
MAX_CALLBACK_BYTES = claim_relation.MAX_CALLBACK_BYTES
MAX_CALLBACK_REQUESTS = claim_relation.MAX_CALLBACK_REQUESTS


def _encoded(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


class PolicyCallbackEntry(FrozenModel):
    """Facts captured immediately before entering the public callback."""

    ordinal: int
    request_hash: str
    request_bytes: int
    policy_hash: str
    delivered_read_ids: tuple[str, ...]
    usable_read_ids: tuple[str, ...]
    read_result_reason: str | None


class PolicyAudit(FrozenModel):
    configured_policy_id: str = POLICY_ID
    configured_policy_hash: str = POLICY_HASH
    callback_entries: tuple[PolicyCallbackEntry, ...]
    blocked_reason: str | None
    blocked_callback_bytes: int | None
    callback_exception_type: str | None


class PolicyResult(FrozenModel):
    """Inner counters describe entry into the bridge, not the final callback.

    In particular, inner served evidence can exist when the policy layer
    blocks the second request. Only this layer's entries describe its delivery.
    """

    inner: claim_relation.ClaimRelationFollowupResult
    audit: PolicyAudit


class _PolicyRefusal(RuntimeError):
    pass


class _PolicyBridge:
    def __init__(self, claim: str, callback: Callable[[dict], object]):
        self.claim = claim
        self.callback = callback
        self.entries: list[PolicyCallbackEntry] = []
        self.blocked_reason: str | None = None
        self.blocked_callback_bytes: int | None = None
        self.callback_exception_type: str | None = None

    def _reject(self, reason: str, size: int | None = None) -> None:
        self.blocked_reason = reason
        self.blocked_callback_bytes = size
        raise _PolicyRefusal(reason)

    def _read_facts(self, messages: list) -> tuple[tuple[str, ...], tuple[str, ...], str | None]:
        if messages[-1].get("role") != "tool":
            return (), (), None
        try:
            result = core._strict_json(messages[-1]["content"])
            status = result["status"]
            if status not in {"ok", "missing_text", "empty_window", "offset_out_of_range"}:
                raise ValueError("invalid status")
            if status != "ok":
                return (), (), status
            evidence_id, text = result["evidence_id"], result["text"]
            if type(evidence_id) is not str or type(text) is not str:
                raise ValueError("invalid receipt")
        except (KeyError, TypeError, ValueError, RecursionError):
            self._reject("tool_result_invalid")
        delivered = (evidence_id,)
        return delivered, delivered if text.strip() else (), status

    def __call__(self, **request: object) -> object:
        outgoing = deepcopy(request)
        messages = outgoing.get("messages")
        if type(messages) is not list or len(messages) < 2:
            self._reject("request_contract_mismatch")
        if messages[1] != {"role": "user", "content": self.claim}:
            self._reject("claim_identity_mismatch")
        system = messages[0]
        if (type(system) is not dict or system.get("role") != "system"
                or type(system.get("content")) is not str
                or system["content"].count(claim_relation._NEW_FINAL) != 1):
            self._reject("instruction_contract_mismatch")
        original_system = system["content"]
        system["content"] += POLICY_APPEND
        encoded = _encoded(outgoing)
        size = len(encoded)
        if size > MAX_CALLBACK_BYTES:
            self._reject("callback_budget_exceeded", size)
        if len(self.entries) >= MAX_CALLBACK_REQUESTS:
            self._reject("callback_budget_exhausted", size)
        # No read is attributed to this boundary until all transformed-request
        # checks pass. Facts precede entry so exceptions/mutation cannot erase them.
        delivered, usable, reason = self._read_facts(messages)
        self.entries.append(PolicyCallbackEntry(
            ordinal=len(self.entries) + 1, request_hash=hashlib.sha256(encoded).hexdigest(), request_bytes=size,
            policy_hash=hashlib.sha256(system["content"][len(original_system):].encode("utf-8")).hexdigest(),
            delivered_read_ids=delivered, usable_read_ids=usable, read_result_reason=reason,
        ))
        try:
            return self.callback(outgoing)
        except Exception as exc:  # noqa: BLE001 -- retain only type, never private callback details.
            self.callback_exception_type = type(exc).__name__
            raise _PolicyRefusal("callback_error") from None


def run_relation_policy_followup(
    snapshot: ReportEvidenceSnapshot, claim: str, *, callback: Callable[[dict], object],
) -> PolicyResult:
    """Run at most two detached single-object callbacks and one frozen read.

    Signature preflight excludes directly wired old keyword-only native
    adapters before the inner executor runs. It does not attest that arbitrary
    callbacks are offline. Construction errors raise; execution faults remain
    in the nested result and boundary-specific audit without answer rewriting.
    """
    try:
        inspect.signature(callback).bind({})
    except (TypeError, ValueError):
        raise TypeError("callback must accept one positional request object") from None
    bridge = _PolicyBridge(claim, callback)
    inner = claim_relation.run_claim_relation_followup(snapshot, claim, transport=bridge)
    return PolicyResult(inner=inner, audit=PolicyAudit(
        callback_entries=tuple(bridge.entries), blocked_reason=bridge.blocked_reason,
        blocked_callback_bytes=bridge.blocked_callback_bytes, callback_exception_type=bridge.callback_exception_type,
    ))
