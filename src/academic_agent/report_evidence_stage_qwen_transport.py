"""Stage-aware wire contract, validated offline; no runner or live authorization.

This deliberately depends on the frozen canary's accounting limits and private
HTTP/JSON helpers without changing their files or identity. In particular,
QwenFollowupTransport._post owns TLS, redirects, proxies, retries, byte limits
and cancellation. Its auto-only __call__ is NOT reused. A future live protocol
must bind both these dependencies and this module; the old allowance is not
authorization. Imports resolve no credentials and perform no I/O.

The policy wrapper owns snapshot membership and stage transitions. This adapter
enforces its supplied declarations, not the truth of a caller-invented stage.
Ledger protocol_accepted describes transport admission only, not the core's
final envelope/evidence validation or semantic support. A future runner must
also stop on a failed policy/core result. The ledger is single-owner, not a
production admission service; its scope label is not network isolation.
"""

import asyncio
from copy import deepcopy

import httpx

from academic_agent.report_evidence_followup import (
    MAX_ARGUMENT_CHARS, _strict_json, tool_definitions,
)
from academic_agent.report_evidence_qwen_canary import (
    CanaryLedger, CanaryStopped, INPUT_RESERVATION, MAX_TOKENS, MODEL,
    REQUEST_BYTES, _encoded, configuration,
)
from academic_agent.report_evidence_qwen_transport import (
    QwenFollowupTransport, _contains_secret, _project_message, _usage,
)
from academic_agent.report_evidence_snapshot import MAX_HITS, LookupArguments, ReadArguments

TRANSPORT_IDENTITY = "report_evidence_stage_qwen_transport_v1"
FROZEN_DEPENDENCY_COUPLING = (
    "src/academic_agent/report_evidence_qwen_transport.py",
    "src/academic_agent/report_evidence_qwen_canary.py",
    "src/academic_agent/report_evidence_followup.py",
    "src/academic_agent/report_evidence_guarded_followup.py",
    "src/academic_agent/report_evidence_snapshot.py",
    "pyproject.toml", "uv.lock",
)


def stage_configuration() -> dict:
    """Reuse limits, not the frozen auto-only protocol's identity or allowance."""
    result = configuration()
    del result["tool_choice"]
    result["tool_choice_by_stage"] = {"initial": "auto", "read": "auto", "final": "none"}
    result["final_tools_wire"] = "omitted"
    return result


class StageQwenLedger(CanaryLedger):
    """A fresh offline-contract journal, never an old batch or caller manifest."""

    def __init__(self, output_dir):
        super().__init__(output_dir, {
            "transport_identity": TRANSPORT_IDENTITY,
            "scope": "offline_contract_no_live_authorization",
            "live_authorization": False,
            "configuration": stage_configuration(),
            # These paths document coupling, not verified source hashes.
            "frozen_dependency_coupling": list(FROZEN_DEPENDENCY_COUPLING),
        })


def _permitted_tools(tools, tool_choice):
    """Accept only the three exact policy declarations; never repair a schema."""
    if type(tool_choice) is not str or tool_choice not in {"auto", "none"}:
        raise CanaryStopped("invalid_tool_choice")
    if type(tools) is not list:
        raise CanaryStopped("invalid_stage_toolset")
    if tool_choice == "none":
        if tools:
            raise CanaryStopped("invalid_stage_toolset")
        return set(), None
    definitions = tool_definitions()
    # Canonical JSON equality distinguishes boolean/integer schema values;
    # Python equality alone would accept True in place of the bound 1.
    if _encoded(tools) == _encoded(definitions):
        return {"lookup_sources", "read_source"}, None
    if len(tools) != 1:
        raise CanaryStopped("invalid_stage_toolset")
    try:
        ids = tools[0]["function"]["parameters"]["properties"]["source_id"]["enum"]
        if (type(ids) is not list or not 1 <= len(ids) <= MAX_HITS
                or any(type(item) is not str for item in ids) or len(set(ids)) != len(ids)):
            raise ValueError("invalid hit enum")
        for source_id in ids:
            ReadArguments(source_id=source_id, offset=0, length=1)
        expected = [definitions[1]]
        expected[0]["function"]["parameters"]["properties"]["source_id"]["enum"] = ids
        if _encoded(tools) != _encoded(expected):
            raise ValueError("different declaration")
    except (KeyError, IndexError, TypeError, ValueError):
        raise CanaryStopped("invalid_stage_toolset") from None
    # Do not sort/rewrite the enum: its supplied order survives on the wire.
    return {"read_source"}, set(ids)


def _admit_reply(message, allowed, read_ids, messages):
    for call in message.get("tool_calls") or []:
        name = call["function"]["name"]
        if name not in allowed:
            raise CanaryStopped("unadvertised_tool")
        if any(call["id"] == previous_call["id"] for previous in messages
               for previous_call in previous.get("tool_calls", []) or []):
            raise CanaryStopped("duplicate_tool_call_id")
        try:
            raw = call["function"]["arguments"]
            if len(raw) > MAX_ARGUMENT_CHARS:
                raise ValueError("argument budget exceeded")
            schema = LookupArguments if name == "lookup_sources" else ReadArguments
            args = schema.model_validate(_strict_json(raw))
        except (TypeError, ValueError, RecursionError):
            raise CanaryStopped("invalid_tool_arguments") from None
        if name == "read_source" and read_ids is not None and args.source_id not in read_ids:
            raise CanaryStopped("read_id_not_permitted")


class StageQwenFollowupTransport(QwenFollowupTransport):
    """Pinned HTTP adapter for run_policy_followup, with no ambient key lookup.

    Inherits only credential validation and the one-shot _post primitive. Tests
    intercept that primitive at httpx.MockTransport, not at this callback. No
    network execution is authorized by constructing this network-capable class.
    """

    def __init__(self, api_key: str, ledger: StageQwenLedger):
        if type(ledger) is not StageQwenLedger:
            raise CanaryStopped("stage_ledger_required")
        super().__init__(api_key, ledger)

    def __call__(self, *, messages, tools, tool_choice):
        if self.ledger.stop_reason is not None:
            raise CanaryStopped("batch_already_stopped")
        try:
            allowed, read_ids = _permitted_tools(tools, tool_choice)
            if type(messages) is not list or not messages or any(type(item) is not dict for item in messages):
                raise CanaryStopped("invalid_request_body")
            for previous in messages:
                if previous.get("role") == "tool":
                    result = _strict_json(previous["content"])
                    if type(result) is not dict:
                        raise CanaryStopped("invalid_request_body")
                    if result.get("status") == "error":
                        raise CanaryStopped("local_tool_error_no_repair")
            body = {"model": MODEL, "messages": deepcopy(messages), "tools": deepcopy(tools),
                    "tool_choice": tool_choice, "stream": False, "enable_thinking": False,
                    "parallel_tool_calls": False, "temperature": 0, "max_tokens": MAX_TOKENS}
            if tool_choice == "none":
                # The callback uses []; the provider wire omits declarations.
                # Do this before encoding AND reservation so both identities
                # bind the same bytes. No exact-model live claim follows.
                del body["tools"]
            if _contains_secret(body, self._api_key):
                raise CanaryStopped("secret_in_request")
            # The same canonical encoding underlies reserve's SHA256. Do not
            # edit wire or body after reservation, including none -> auto.
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
        observation = {"received": False}
        usage = message = None
        model_matches = None
        error = None
        try:
            raw = asyncio.run(self._post(wire, observation))
            payload = _strict_json(raw.decode("utf-8"))
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
            _admit_reply(projected, allowed, read_ids, body["messages"])
            message = projected
        except CanaryStopped as exc:
            error = str(exc)
        except (TimeoutError, httpx.TimeoutException):
            error = "request_timeout"
        except Exception:  # noqa: BLE001 -- decoder/HTTP exception text can contain credentials or source content.
            error = "response_or_transport_failed"
        # Admission failure cannot erase already observed usage. A failed
        # durable finish leaves pending intent and stops the next dispatch.
        self.ledger.finish(ordinal, received=observation["received"], usage=usage, error=error, message=message,
                           response_model_matches_authorized=model_matches)
        if error is not None:
            raise CanaryStopped(error) from None
        return deepcopy(message)
