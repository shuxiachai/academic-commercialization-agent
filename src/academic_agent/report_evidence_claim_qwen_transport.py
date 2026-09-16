"""Independent claim-bound native wire contract; no live or production authority.

One instance owns one single-owner conversation. History comparisons establish
consistency with a detached trusted snapshot, not proof that an arbitrary Python
caller ran a tool. The frozen claim wrapper owns receipt delivery, strict final
parsing and relation-to-state mapping; none establishes semantic correctness.
Imports read no keys and dispatch nothing. This network-capable adapter must
only be used with intercepted HTTP until separately authorized by a new protocol.
"""

import asyncio
from copy import deepcopy
import hashlib

import httpx

from academic_agent import report_evidence_claim_relation as claim_policy
from academic_agent import report_evidence_followup as core
from academic_agent.report_evidence_catalog_followup import (
    MAX_CALLBACK_REQUESTS, MAX_CATALOG_ENTRIES, MAX_CATALOG_BYTES,
    MAX_TITLE_CODEPOINTS, build_catalog,
)
from academic_agent.report_evidence_catalog_qwen_transport import (
    JSON_KEYWORD, _contains_secret, _system_content as _catalog_system_content,
)
from academic_agent.report_evidence_qwen_canary import (
    CanaryLedger, CanaryStopped, INPUT_RESERVATION, MAX_TOKENS, MODEL,
    REQUEST_BYTES, _encoded, configuration,
)
from academic_agent.report_evidence_qwen_transport import (
    QwenFollowupTransport, _project_message, _usage,
)
from academic_agent.report_evidence_snapshot import (
    CONTENT_WARNING, ReadArguments, ReportEvidenceSnapshot, content_hash,
)
from academic_agent.report_evidence_stage_qwen_transport import _admit_reply

TRANSPORT_IDENTITY = "report_evidence_claim_qwen_transport_v1"
FROZEN_DEPENDENCY_COUPLING = (
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


def claim_qwen_configuration() -> dict:
    """Frozen accounting ceilings describe limits, never a new live allowance."""
    result = configuration()
    del result["tool_choice"]
    return {
        **result, "method_id": claim_policy.METHOD_ID,
        "max_conversation_requests": MAX_CALLBACK_REQUESTS,
        "max_conversation_reads": 1, "max_catalog_entries": MAX_CATALOG_ENTRIES,
        "max_catalog_bytes": MAX_CATALOG_BYTES, "max_title_codepoints": MAX_TITLE_CODEPOINTS,
        "claim_binding": "verbatim_at_construction_including_first_request",
        "final_declaration_owner": "claim_wrapper",
        "tool_choice_by_stage": {"initial_nonempty": "auto", "initial_empty": "none", "final": "none"},
        "final_tools_wire": "omitted",
        "response_format_by_stage": {
            "initial_nonempty": "omitted", "initial_empty": {"type": "json_object"},
            "final": {"type": "json_object"},
        },
        "final_json_keyword_guard": {
            "roles": ["system", "user"], "pattern": r"\bJSON\b",
            "flags": ["ASCII", "IGNORECASE"], "repair": False,
        },
    }


class ClaimQwenLedger(CanaryLedger):
    """Separate code-owned offline manifest with unchanged reserve/finish rules."""

    def __init__(self, output_dir):
        super().__init__(output_dir, {
            "transport_identity": TRANSPORT_IDENTITY, "method_id": claim_policy.METHOD_ID,
            "scope": "offline_contract_no_live_authorization", "live_authorization": False,
            "configuration": claim_qwen_configuration(),
            # Paths disclose coupling, not verified source hashes or authority.
            "frozen_dependency_coupling": list(FROZEN_DEPENDENCY_COUPLING),
        })


class ClaimQwenFollowupTransport(QwenFollowupTransport):
    """Inherit only key validation and pinned _post, not catalog orchestration.

    The caller supplies explicit credentials, trusted snapshot and verbatim
    claim. No environment lookup, retry, repair, runner or allowance is added.
    Like the inherited journal, this session is single-owner, not thread-safe.
    """

    def __init__(self, api_key: str, ledger: ClaimQwenLedger, *, snapshot: ReportEvidenceSnapshot, claim: str):
        if type(ledger) is not ClaimQwenLedger:
            raise CanaryStopped("claim_ledger_required")
        super().__init__(api_key, ledger)
        if type(claim) is not str or not 1 <= len(claim) <= 4096:
            ledger.stop("invalid_claim")
            raise CanaryStopped("invalid_claim")
        self._claim = claim
        try:
            if type(snapshot) is not ReportEvidenceSnapshot:
                raise ValueError("invalid snapshot type")
            self._snapshot = ReportEvidenceSnapshot.model_validate(snapshot.model_dump(warnings="error"))
            self._catalog = build_catalog(self._snapshot)
            self._catalog_json = _encoded(self._catalog).decode("ascii")
            self._visible_ids = tuple(item["source_id"] for item in self._catalog["entries"])
            self._systems = {}
            for state in (False, True):
                expected = _catalog_system_content(self._snapshot, state)
                if expected.count(claim_policy._OLD_FINAL) != 1:
                    raise ValueError("frozen system contract changed")
                # Comparison template ONLY: never replace instructions in the
                # caller's outgoing payload or run another wrapper/tool read.
                self._systems[state] = expected.replace(claim_policy._OLD_FINAL, claim_policy._NEW_FINAL, 1)
        except (ValueError, TypeError, RecursionError):
            ledger.stop("invalid_snapshot")
            raise CanaryStopped("invalid_snapshot") from None
        self._previous = None
        self._requests = 0
        self._closed = False

    def _expected_result(self, args):
        """Finite frozen-format comparison, not a second tool execution.

        Keep full-result comparison: snapshot/source hashes and an issued ID
        alone do not bind a supplied text window or a claim of missing text.
        Preserve absence precedence, code-point offsets and receipt identity.
        """
        source = next(item for item in self._snapshot.sources if item.source_id == args.source_id)
        expected = {
            "source_id": source.source_id, "origin": source.origin, "stored_length": source.stored_length,
            "content_warning": CONTENT_WARNING, "text_scope": "saved_summary_only",
        }
        if not source.summary:
            return {**expected, "status": "missing_text"}
        if args.offset > source.stored_length:
            return {**expected, "status": "offset_out_of_range"}
        end = min(args.offset + args.length, source.stored_length)
        text = source.summary[args.offset:end]
        expected.update(
            status="ok" if text else "empty_window", start=args.offset, end=end, text=text,
            window_truncated=args.offset > 0 or end < source.stored_length,
            snapshot_hash=self._snapshot.snapshot_hash, source_hash=self._snapshot.source_hash(source),
            summary_hash=content_hash(source.summary), text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
        if text:
            payload = {key: expected[key] for key in core.ServedEvidence.model_fields if key != "evidence_id"}
            expected["evidence_id"] = "ev_" + content_hash(payload)
        return expected

    def _validate_result(self, message):
        call = self._previous["tool_calls"][0]
        if (set(message) != {"role", "tool_call_id", "content"} or message["role"] != "tool"
                or message["tool_call_id"] != call["id"] or type(message["content"]) is not str):
            raise CanaryStopped("tool_result_identity_mismatch")
        result = core._strict_json(message["content"])
        if type(result) is not dict:
            raise CanaryStopped("invalid_tool_result")
        if result.get("status") == "error":
            raise CanaryStopped("local_tool_error_no_repair")
        args = ReadArguments.model_validate(core._strict_json(call["function"]["arguments"]))
        if result.get("source_id") != args.source_id:
            raise CanaryStopped("tool_result_scope_mismatch")
        if result.get("status") not in {"ok", "missing_text", "empty_window", "offset_out_of_range"}:
            raise CanaryStopped("invalid_tool_result")
        # Canonical equality also distinguishes numeric values from booleans.
        if _encoded(result) != _encoded(self._expected_result(args)):
            raise CanaryStopped("tool_result_payload_mismatch")

    def _admit_request(self, messages, tools, tool_choice):
        if self._closed or self._requests >= MAX_CALLBACK_REQUESTS:
            raise CanaryStopped("conversation_closed")
        if type(messages) is not list or any(type(item) is not dict for item in messages):
            raise CanaryStopped("invalid_request_history")
        initial = self._requests == 0
        if len(messages) != (3 if initial else 5):
            raise CanaryStopped("invalid_request_history")
        can_read = initial and bool(self._visible_ids)
        for message in messages[:3]:
            if set(message) != {"role", "content"} or type(message["content"]) is not str:
                raise CanaryStopped("invalid_request_history")
        if messages[0] != {"role": "system", "content": self._systems[can_read]}:
            raise CanaryStopped("system_history_mismatch")
        if messages[1] != {"role": "user", "content": self._claim}:
            raise CanaryStopped("claim_history_mismatch")
        if messages[2] != {"role": "user", "content": self._catalog_json}:
            raise CanaryStopped("catalog_history_mismatch")
        if not initial:
            if self._previous is None or _encoded(messages[3]) != _encoded(self._previous):
                raise CanaryStopped("assistant_history_mismatch")
            self._validate_result(messages[4])
        if type(tool_choice) is not str or tool_choice != ("auto" if can_read else "none"):
            raise CanaryStopped("invalid_tool_choice")
        expected = []
        if can_read:
            if not 1 <= len(self._visible_ids) <= MAX_CATALOG_ENTRIES:
                raise CanaryStopped("invalid_catalog_toolset")
            expected = [core.tool_definitions()[1]]
            expected[0]["function"]["parameters"]["properties"]["source_id"]["enum"] = list(self._visible_ids)
        if type(tools) is not list or _encoded(tools) != _encoded(expected):
            raise CanaryStopped("invalid_catalog_toolset")
        return {"read_source"} if can_read else set()

    def __call__(self, *, messages, tools, tool_choice):
        if self.ledger.stop_reason is not None:
            raise CanaryStopped("batch_already_stopped")
        try:
            body = {"model": MODEL, "messages": deepcopy(messages), "tools": deepcopy(tools),
                    "tool_choice": tool_choice, "stream": False, "enable_thinking": False,
                    "parallel_tool_calls": False, "temperature": 0, "max_tokens": MAX_TOKENS}
            # Bound scanner work. JSON mode below enlarges this envelope, so
            # this precheck cannot substitute for the actual final wire bound.
            if len(_encoded(body)) > REQUEST_BYTES:
                raise CanaryStopped("request_too_large")
            if _contains_secret(body, self._api_key):
                raise CanaryStopped("secret_in_request")
            allowed = self._admit_request(body["messages"], body["tools"], body["tool_choice"])
            if tool_choice == "none":
                del body["tools"]
                body["response_format"] = {"type": "json_object"}
                if not any(item["role"] in ("system", "user") and JSON_KEYWORD.search(item["content"])
                           for item in body["messages"][:3]):
                    raise CanaryStopped("final_json_keyword_required")
            # Both reservation and HTTP bind these exact final encoded bytes.
            wire = _encoded(body)
            if len(wire) > REQUEST_BYTES:
                raise CanaryStopped("request_too_large")
        except CanaryStopped as exc:
            self.ledger.stop(str(exc))
            raise
        except (KeyError, TypeError, ValueError, RecursionError):
            self.ledger.stop("invalid_request_body")
            raise CanaryStopped("invalid_request_body") from None
        ordinal = self.ledger.reserve(body)
        self._requests += 1
        observation = {"received": False}
        usage = message = None
        model_matches = None
        error = None
        try:
            raw = asyncio.run(self._post(wire, observation))
            payload = core._strict_json(raw.decode("utf-8"))
            if type(payload) is not dict:
                raise CanaryStopped("invalid_response_protocol")
            model_matches = payload.get("model") == MODEL
            usage = _usage(payload)
            if usage is None:
                raise CanaryStopped("usage_unknown_or_contradictory")
            if not model_matches:
                raise CanaryStopped("unexpected_response_model")
            if usage["prompt_tokens"] > INPUT_RESERVATION or usage["completion_tokens"] > MAX_TOKENS:
                raise CanaryStopped("token_reservation_exceeded")
            if self._api_key.encode("utf-8") in raw:
                raise CanaryStopped("secret_in_response")
            projected = _project_message(payload)
            if _contains_secret(projected, self._api_key):
                raise CanaryStopped("secret_in_response")
            _admit_reply(projected, allowed, set(self._visible_ids), body["messages"])
            message = projected
        except CanaryStopped as exc:
            error = str(exc)
        except (TimeoutError, httpx.TimeoutException):
            error = "request_timeout"
        except Exception:  # noqa: BLE001 -- exception details can contain credentials or saved text.
            error = "response_or_transport_failed"
        self.ledger.finish(ordinal, received=observation["received"], usage=usage, error=error, message=message,
                           response_model_matches_authorized=model_matches)
        if error is not None:
            raise CanaryStopped(error) from None
        self._previous = deepcopy(message)
        self._closed = not bool(message.get("tool_calls"))
        # Leave native content unchanged, even an invalid/contradictory final.
        # Wire admission is not claim-wrapper admission or semantic success.
        return deepcopy(message)
