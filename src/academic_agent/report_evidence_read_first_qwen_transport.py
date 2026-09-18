"""Read-first native transform around the frozen RP executor, never a runner.

Named choice is forced admission, not autonomous selection. Callback entry,
wire reservation and delivered read are separate observations. Only the base
key/HTTP/accounting primitives and pure comparison helpers are reused; no old
adapter's __call__ or closed batch is invoked. Explicit keys confer no authority.
"""

import asyncio
from copy import deepcopy
import hashlib

import httpx

from academic_agent import report_evidence_claim_relation as claim_policy
from academic_agent import report_evidence_followup as core
from academic_agent import report_evidence_relation_policy as policy
from academic_agent.report_evidence_catalog_followup import build_catalog
from academic_agent.report_evidence_catalog_qwen_transport import (
    JSON_KEYWORD, _contains_secret, _system_content,
)
from academic_agent.report_evidence_qwen_canary import (
    CanaryLedger, CanaryStopped, INPUT_RESERVATION, MAX_TOKENS, MODEL,
    REQUEST_BYTES, _encoded, configuration as base_configuration,
)
from academic_agent.report_evidence_qwen_transport import QwenFollowupTransport, _project_message, _usage
from academic_agent.report_evidence_snapshot import (
    CONTENT_WARNING, ReadArguments, ReportEvidenceSnapshot, content_hash,
)

TRANSPORT_IDENTITY = "report_evidence_read_first_qwen_transport_v1"
TRANSFORM_IDENTITY = "report_evidence_read_first_native_transform_v1"
FROZEN_POLICY_SHA256 = "61dfb78cb81435850dd8adc9cf9990833a87c75dd756e3f22b18ede5cee14ea4"
NAMED_CHOICE = {"type": "function", "function": {"name": "read_source"}}
FROZEN_DEPENDENCY_COUPLING = (
    "src/academic_agent/report_evidence_relation_policy.py",
    "src/academic_agent/report_evidence_claim_relation.py",
    "src/academic_agent/report_evidence_catalog_followup.py",
    "src/academic_agent/report_evidence_catalog_qwen_transport.py",
    "src/academic_agent/report_evidence_followup.py",
    "src/academic_agent/report_evidence_snapshot.py",
    "src/academic_agent/report_evidence_qwen_transport.py",
    "src/academic_agent/report_evidence_qwen_canary.py",
    "src/academic_agent/report_evidence_stage_qwen_transport.py",
    "pyproject.toml", "uv.lock",
)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def configuration() -> dict:
    config = base_configuration()
    del config["tool_choice"]
    return {**config, "transport_identity": TRANSPORT_IDENTITY, "transform_identity": TRANSFORM_IDENTITY,
            "policy_id": policy.POLICY_ID, "policy_sha256": FROZEN_POLICY_SHA256,
            "max_sources": 1, "max_saved_codepoints": 1500, "max_conversation_requests": 2,
            "max_conversation_reads": 1, "initial_nonempty_choice": deepcopy(NAMED_CHOICE),
            "final_choice": "none", "final_tools": "omitted", "final_format": {"type": "json_object"},
            "message_representation": "projected_native_assistant_message_not_raw_http"}


def admitted_snapshot(snapshot):
    if (policy.POLICY_ID != "report_evidence_relation_policy_v1"
            or digest(policy.POLICY_APPEND.encode("utf-8")) != FROZEN_POLICY_SHA256
            or policy.POLICY_HASH != FROZEN_POLICY_SHA256):
        raise CanaryStopped("policy_identity_mismatch")
    if type(snapshot) is not ReportEvidenceSnapshot:
        raise CanaryStopped("invalid_snapshot")
    checked = ReportEvidenceSnapshot.model_validate(snapshot.model_dump(warnings="error"))
    catalog = build_catalog(checked)
    if (len(checked.sources) > 1 or any(source.stored_length > 1500 for source in checked.sources)
            or catalog["coverage"] != "complete" or catalog["omitted_count"]
            or catalog["returned_count"] != len(checked.sources) or catalog["title_truncation_count"]):
        raise CanaryStopped("out_of_scope")
    return checked


def callback_template(snapshot, claim, *, previous=None, tool_message=None):
    """Pure comparison template; never run a second wrapper or local read."""
    can_read = previous is None and bool(snapshot.sources)
    system = _system_content(snapshot, can_read)
    if system.count(claim_policy._OLD_FINAL) != 1:
        raise CanaryStopped("system_contract_changed")
    system = system.replace(claim_policy._OLD_FINAL, claim_policy._NEW_FINAL, 1) + policy.POLICY_APPEND
    messages = [{"role": "system", "content": system}, {"role": "user", "content": claim},
                {"role": "user", "content": _encoded(build_catalog(snapshot)).decode("ascii")}]
    if previous is not None:
        messages.extend((deepcopy(previous), deepcopy(tool_message)))
    tools = [core.tool_definitions()[1]] if can_read else []
    if tools:
        tools[0]["function"]["parameters"]["properties"]["source_id"]["enum"] = [snapshot.sources[0].source_id]
    return {"messages": messages, "tools": tools, "tool_choice": "auto" if can_read else "none"}


def expected_read_result(snapshot):
    """Compare the full frozen reader/receipt shape without executing a read.

    The admission scope guarantees a full [0, 1500) request. Empty text has no
    receipt; whitespace retains its receipt but is not usable claim evidence.
    """
    source = snapshot.sources[0]
    result = {"source_id": source.source_id, "origin": source.origin, "stored_length": source.stored_length,
              "content_warning": CONTENT_WARNING, "text_scope": "saved_summary_only"}
    if not source.summary:
        return {**result, "status": "missing_text"}
    result.update(status="ok", start=0, end=source.stored_length, text=source.summary, window_truncated=False,
                  snapshot_hash=snapshot.snapshot_hash, source_hash=snapshot.source_hash(source),
                  summary_hash=content_hash(source.summary), text_sha256=digest(source.summary.encode("utf-8")))
    receipt = {key: result[key] for key in core.ServedEvidence.model_fields if key != "evidence_id"}
    return {**result, "evidence_id": "ev_" + content_hash(receipt)}


def read_facts(request):
    if request["messages"][-1]["role"] != "tool":
        return {"delivered_read_ids": [], "usable_read_ids": [], "read_result_reason": None}
    result = core._strict_json(request["messages"][-1]["content"])
    delivered = [result["evidence_id"]] if result["status"] == "ok" else []
    return {"delivered_read_ids": delivered, "usable_read_ids": delivered if result.get("text", "").strip() else [],
            "read_result_reason": result["status"]}


def native_body(request):
    """Deterministic registered transform; original callback stays unchanged."""
    body = {**deepcopy(request), "model": MODEL, "stream": False, "enable_thinking": False,
            "parallel_tool_calls": False, "temperature": 0, "max_tokens": MAX_TOKENS}
    if request["tool_choice"] == "auto":
        body["tool_choice"] = deepcopy(NAMED_CHOICE)
        properties = body["tools"][0]["function"]["parameters"]["properties"]
        properties["offset"]["enum"], properties["length"]["enum"] = [0], [1500]
    else:
        del body["tools"]
        body["response_format"] = {"type": "json_object"}
    return body


def full_read_call(message, source_id):
    """Gate the actual reply before the frozen executor can execute anything."""
    calls = message.get("tool_calls") or []
    if message.get("refusal") or len(calls) != 1:
        raise CanaryStopped("full_native_read_required")
    call = calls[0]
    try:
        args = ReadArguments.model_validate(core._strict_json(call["function"]["arguments"]))
    except (KeyError, TypeError, ValueError, RecursionError):
        raise CanaryStopped("invalid_tool_arguments") from None
    if (call["function"]["name"] != "read_source" or args.source_id != source_id
            or type(args.offset) is not int or args.offset != 0 or type(args.length) is not int or args.length != 1500):
        raise CanaryStopped("full_native_read_required")
    return call


def availability_audit(snapshot, result, *, records):
    """Keep execution, each callback boundary and native observations separate.

    RP expansion can reject a read already delivered to its inner bridge. A
    reserved native body can likewise exist without any POST/response. Neither
    observation proves the provider received or used the saved evidence.
    """
    audit = result.inner.audit
    executed = audit.catalog.core.tool_executions

    def delivery(delivered, usable, reason):
        state = ("no_source" if not snapshot.sources else "read_not_observed" if not executed else
                 "usable_text" if usable else "missing_text" if reason == "missing_text" else
                 "blank_text" if delivered else "read_result_not_delivered")
        return {"state": state, "read_result_reason": reason,
                "delivered_read_ids": list(delivered), "usable_read_ids": list(usable)}

    entry = result.audit.callback_entries[-1] if result.audit.callback_entries else None
    policy_delivery = delivery(entry.delivered_read_ids, entry.usable_read_ids, entry.read_result_reason) if entry else delivery((), (), None)
    native_observations = []
    for record in records:
        facts = read_facts(record["request"])
        native_observations.append({
            "request_id": record["request_id"], "reserved_body_read_result_reason": facts["read_result_reason"],
            "reserved_body_receipt_ids": facts["delivered_read_ids"],
            "reserved_body_usable_receipt_ids": facts["usable_read_ids"],
            "provider_response_received": record["provider_response_received"],
            "native_protocol_accepted": record["protocol_accepted"], "usage_status": record["usage_status"],
        })
    return {"scope": "in_scope", "source_count": len(snapshot.sources), "read_executions": executed,
            "inner_delivery": {"scope": "inner_to_relation_policy", **delivery(
                audit.delivered_read_ids, audit.usable_read_ids, audit.read_result_reason)},
            "policy_callback_delivery": {"scope": "relation_policy_to_callback", **policy_delivery,
                                         "callback_count": len(result.audit.callback_entries),
                                         "blocked_reason": result.audit.blocked_reason},
            "native_intent_response": {"scope": "reservation_and_observed_response_only",
                                       "provider_evidence_receipt": "not_attested",
                                       "requests": native_observations}}


class ReadFirstQwenLedger(CanaryLedger):
    def __init__(self, output_dir):
        super().__init__(output_dir, {
            "transport_identity": TRANSPORT_IDENTITY, "scope": "offline_contract_no_live_authorization",
            "live_authorization": False, "configuration": configuration(),
            "frozen_dependency_coupling": list(FROZEN_DEPENDENCY_COUPLING),
        })


class ReadFirstQwenFollowupTransport(QwenFollowupTransport):
    """Single-owner conversation; inherit only key validation and pinned HTTP."""

    def __init__(self, api_key, ledger, *, snapshot, claim):
        if type(ledger) is not ReadFirstQwenLedger:
            raise CanaryStopped("read_first_ledger_required")
        super().__init__(api_key, ledger)
        try:
            if type(claim) is not str or not 1 <= len(claim) <= 4096:
                raise CanaryStopped("invalid_claim")
            self.snapshot = admitted_snapshot(snapshot)
        except CanaryStopped as exc:
            ledger.stop(str(exc))
            raise
        except (TypeError, ValueError, RecursionError):
            ledger.stop("invalid_snapshot")
            raise CanaryStopped("invalid_snapshot") from None
        self.claim, self.previous, self.closed = claim, None, False
        self.exchanges = []

    def _admit(self, request):
        if self.closed or len(self.exchanges) >= 2:
            raise CanaryStopped("conversation_closed")
        if type(request) is not dict or set(request) != {"messages", "tools", "tool_choice"}:
            raise CanaryStopped("invalid_request_contract")
        if self.previous is not None:
            messages = request["messages"]
            if type(messages) is not list or len(messages) != 5:
                raise CanaryStopped("invalid_request_history")
            tool = messages[4]
            call = self.previous["tool_calls"][0]
            if (type(tool) is not dict or set(tool) != {"role", "tool_call_id", "content"}
                    or tool["role"] != "tool" or tool["tool_call_id"] != call["id"] or type(tool["content"]) is not str):
                raise CanaryStopped("tool_result_identity_mismatch")
            # Receipt/hash subsets do not establish delivered text, absence or
            # window boundaries. Keep this complete comparison mutation-tested.
            if _encoded(core._strict_json(tool["content"])) != _encoded(expected_read_result(self.snapshot)):
                raise CanaryStopped("tool_result_payload_mismatch")
        else:
            tool = None
        expected = callback_template(self.snapshot, self.claim, previous=self.previous, tool_message=tool)
        if _encoded(request) != _encoded(expected):
            raise CanaryStopped("callback_contract_mismatch")

    def __call__(self, request, /):
        if self.ledger.stop_reason is not None:
            raise CanaryStopped("batch_already_stopped")
        try:
            original = _encoded(request)
            if len(original) > REQUEST_BYTES:
                raise CanaryStopped("request_too_large")
            if _contains_secret(request, self._api_key):
                raise CanaryStopped("secret_in_request")
            self._admit(request)
            detached = deepcopy(request)
            body = native_body(detached)
            if body["tool_choice"] == "none" and not any(
                    item["role"] in ("system", "user") and JSON_KEYWORD.search(item["content"])
                    for item in body["messages"][:3]):
                raise CanaryStopped("final_json_keyword_required")
            wire = _encoded(body)
            if len(wire) > REQUEST_BYTES:
                raise CanaryStopped("request_too_large")
        except CanaryStopped as exc:
            self.ledger.stop(str(exc))
            raise
        except (KeyError, IndexError, TypeError, ValueError, RecursionError):
            self.ledger.stop("invalid_request_body")
            raise CanaryStopped("invalid_request_body") from None
        ordinal = self.ledger.reserve(body)
        entry = {"ordinal": len(self.exchanges) + 1, "request": detached, "request_hash": digest(original),
                 "request_bytes": len(original), "tool_choice": detached["tool_choice"],
                 "policy_hash": FROZEN_POLICY_SHA256, **read_facts(detached),
                 "transform_identity": TRANSFORM_IDENTITY, "native_ordinal": ordinal,
                 "native_body_hash": digest(wire), "native_body_bytes": len(wire)}
        # Persist the original callback separately, not reconstructed from a
        # forced-choice wire body. A failed audit append cannot buy a POST.
        self.exchanges.append(entry)
        self.ledger._append({"event": "read_first_callback", **entry})
        if _encoded(self.ledger.records[ordinal - 1]["request"]) != wire:
            self.ledger.stop("reservation_wire_mismatch")
            raise CanaryStopped("reservation_wire_mismatch")
        observation = {"received": False}
        usage = message = model_matches = error = None
        try:
            raw = asyncio.run(self._post(wire, observation))
            payload = core._strict_json(raw.decode("utf-8"))
            if type(payload) is not dict:
                raise CanaryStopped("invalid_response_protocol")
            # Preserve strict known usage even if identity, secret or read
            # admission subsequently rejects this paid response.
            usage = _usage(payload)
            model_matches = type(payload.get("model")) is str and payload["model"] == MODEL
            if usage is None:
                raise CanaryStopped("usage_unknown_or_contradictory")
            if not model_matches:
                raise CanaryStopped("unexpected_response_model")
            if usage["prompt_tokens"] > INPUT_RESERVATION or usage["completion_tokens"] > MAX_TOKENS:
                raise CanaryStopped("token_reservation_exceeded")
            # Scan the entire parsed payload, including discarded metadata and
            # escaped echoes, but never retain the raw payload in the journal.
            if self._api_key.encode("utf-8") in raw or _contains_secret(payload, self._api_key):
                raise CanaryStopped("secret_in_response")
            message = _project_message(payload)
            if detached["tool_choice"] == "auto":
                full_read_call(message, self.snapshot.sources[0].source_id)
            elif message.get("tool_calls") or message.get("refusal"):
                raise CanaryStopped("final_only_reply_required")
        except CanaryStopped as exc:
            error = str(exc)
        except (TimeoutError, httpx.TimeoutException):
            error = "request_timeout"
        except Exception:  # noqa: BLE001 -- downstream exceptions may disclose keys or saved text.
            error = "response_or_transport_failed"
        self.ledger.finish(ordinal, received=observation["received"], usage=usage, error=error, message=message,
                           response_model_matches_authorized=model_matches)
        if error is not None:
            raise CanaryStopped(error) from None
        self.previous = deepcopy(message)
        self.closed = not bool(message.get("tool_calls"))
        return deepcopy(message)
