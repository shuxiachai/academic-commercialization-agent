"""Offline stage controls around the frozen loop, not a provider adapter.

The old core records reads before calling this wrapper. Only arguments actually
forwarded to the outer callback count as delivery here, including when that
callback raises. Neither boundary establishes provider receipt or support.
"""

from collections.abc import Callable
from copy import deepcopy
from typing import Literal

from academic_agent import report_evidence_followup as core
from academic_agent.report_evidence_snapshot import (
    FrozenModel, LookupArguments, ReadArguments, ReportEvidenceSnapshot,
)


class ToolObservation(FrozenModel):
    call_id: str
    name: str
    status: str
    evidence_id: str | None = None


class PolicyAudit(FrozenModel):
    core: core.FollowupAudit
    downstream_calls: int
    advertised_tools: tuple[tuple[str, ...], ...]
    tool_results: tuple[ToolObservation, ...]
    forwarded_read_ids: tuple[str, ...]
    refusal: str | None
    downstream_exception_type: str | None


class PolicyFollowupResult(FrozenModel):
    state: Literal["answered_with_evidence", "answered_without_evidence", "abstained", "failed"]
    answer: str | None
    evidence_ids: tuple[str, ...]
    served_evidence: tuple[core.ServedEvidence, ...]
    semantic_support: Literal["not_assessed"] = "not_assessed"
    answer_verification: Literal["not_verified"] = "not_verified"
    audit: PolicyAudit


class _PolicyRefusal(RuntimeError):
    pass


def run_policy_followup(
    snapshot: ReportEvidenceSnapshot, question: str, *, transport: Callable[..., object],
) -> PolicyFollowupResult:
    """Allow lookup/read initially, hit-only read next, then finalization only.

    A direct read must name an existing snapshot ID; the catalog does not
    enumerate those IDs. Zero literal hits end tool access, not establish
    absent literature. Final prose/abstention still uses the core's envelope.
    This callback contract includes tools=[]/tool_choice=none; the frozen
    auto-only Qwen adapter is deliberately not adapted to it.
    """
    stage = "initial"
    read_ids = {source.source_id for source in snapshot.sources}
    accepted = {}
    pending = None
    observations = []
    read_receipts = []
    forwarded = []
    advertised = []
    refusal = downstream_error = None

    def reject(reason):
        nonlocal refusal
        refusal = reason
        raise _PolicyRefusal(reason)

    def bridge(*, messages, tools, tool_choice):
        nonlocal stage, read_ids, pending, downstream_error
        if pending is not None:
            # Only a result paired with the last approved call can advance the
            # stage. Source prose and assistant declarations cannot do so.
            call_id, name, args = pending
            result_message = messages[-1]
            if (result_message.get("role") != "tool" or result_message.get("tool_call_id") != call_id
                    or messages[-2].get("tool_calls") != [accepted[call_id]]):
                reject("tool_result_identity_mismatch")
            result = core._strict_json(result_message["content"])
            if name == "lookup_sources":
                if result.get("status") != "ok":
                    reject("tool_result_failed")
                read_ids = {hit["source_id"] for hit in result["hits"]}
                if not read_ids <= {source.source_id for source in snapshot.sources}:
                    reject("tool_result_scope_mismatch")
                stage = "read" if read_ids else "final"
            else:
                if result.get("source_id") != args["source_id"]:
                    reject("tool_result_scope_mismatch")
                stage = "final"
                if result.get("status") == "ok":
                    read_receipts.append(result["evidence_id"])
            observations.append(ToolObservation(call_id=call_id, name=name, status=result["status"],
                                                evidence_id=result.get("evidence_id")))
            pending = None

        if len(advertised) + 1 >= core.MAX_TURNS or len(accepted) >= core.MAX_TOOL_REQUESTS:
            stage = "final"
        allowed = {"lookup_sources", "read_source"} if stage == "initial" else {"read_source"} if stage == "read" else set()
        selected = [deepcopy(tool) for tool in tools if tool["function"]["name"] in allowed]
        if stage == "read":
            selected[0]["function"]["parameters"]["properties"]["source_id"]["enum"] = sorted(read_ids)
        outgoing = deepcopy(messages)
        note = {
            "initial": "Use at most one literal lookup, or directly read a known registered ID. The catalog has no IDs.",
            "read": "Lookup completed. Read only a returned hit ID, or finalize. No further lookup is permitted.",
            "final": "No tools remain. Finalize or abstain. A zero literal match does not prove absent sources or literature.",
        }[stage]
        outgoing[0]["content"] += "\nStage policy: " + note
        advertised.append(tuple(tool["function"]["name"] for tool in selected))
        forwarded[:] = read_receipts
        try:
            raw = transport(messages=outgoing, tools=selected, tool_choice="auto" if allowed else "none")
        except Exception as exc:  # noqa: BLE001 -- retain the category, never downstream exception text.
            downstream_error = type(exc).__name__
            raise _PolicyRefusal("downstream_transport_error") from None
        try:
            response = core._assistant_message(raw)
        except (ValueError, TypeError, RecursionError):
            reject("invalid_assistant_message")
        calls = response.get("tool_calls") or []
        if calls:
            call = calls[0]
            name = call["function"]["name"]
            if call["id"] in accepted:
                reject("duplicate_tool_call_id")
            if name not in allowed:
                reject("unadvertised_tool")
            try:
                arguments = call["function"]["arguments"]
                if len(arguments) > core.MAX_ARGUMENT_CHARS:
                    raise ValueError("argument budget exceeded")
                schema = LookupArguments if name == "lookup_sources" else ReadArguments
                args = schema.model_validate(core._strict_json(arguments)).model_dump()
            except (ValueError, TypeError, RecursionError):
                reject("invalid_arguments")
            if name == "read_source" and args["source_id"] not in read_ids:
                reject("read_id_not_permitted")
            accepted[call["id"]] = deepcopy(call)
            pending = (call["id"], name, args)
        return response

    inner = core.run_followup(snapshot, question, transport=bridge)
    # Do not expose the inner early-recorded receipts as authoritative delivery.
    # Retain its diagnostic ledger explicitly under audit.core instead.
    served = tuple(item for item in inner.served_evidence if item.evidence_id in forwarded)
    bad_citation = any(evidence_id not in forwarded for evidence_id in inner.evidence_ids)
    failed = refusal is not None or downstream_error is not None or bad_citation
    return PolicyFollowupResult(
        state="failed" if failed else inner.state, answer=None if failed else inner.answer,
        evidence_ids=() if failed else inner.evidence_ids, served_evidence=served,
        audit=PolicyAudit(core=inner.audit, downstream_calls=len(advertised), advertised_tools=tuple(advertised),
                          tool_results=tuple(observations), forwarded_read_ids=tuple(forwarded),
                          refusal=refusal or ("undelivered_evidence_id" if bad_citation else None),
                          downstream_exception_type=downstream_error),
    )
