"""Final-only JSON Object wire contract; isolated from every production path.

Reuse frozen HTTP, accounting and stage-admission primitives, never their fixed
request builders or canary identities. JSON Object is not JSON Schema: the
unchanged core still rejects prose, fences, bad envelopes and invented evidence.
This module grants no live permission. Only the separately frozen parent-run
canary may exercise its network-capable adapter under the registered authority.
The ledger remains single-owner, not production admission or exactly-once.
"""

import asyncio
from copy import deepcopy
import re

import httpx

from academic_agent.report_evidence_followup import (
    _strict_json,
)
from academic_agent.report_evidence_qwen_canary import (
    CanaryLedger, CanaryStopped, INPUT_RESERVATION, MAX_TOKENS, MODEL,
    REQUEST_BYTES, _encoded,
)
from academic_agent.report_evidence_qwen_transport import (
    QwenFollowupTransport, _contains_secret, _project_message, _usage,
)
from academic_agent.report_evidence_stage_qwen_transport import (
    FROZEN_DEPENDENCY_COUPLING as STAGE_DEPENDENCIES,
    _admit_reply, _permitted_tools, stage_configuration,
)

TRANSPORT_IDENTITY = "report_evidence_final_json_qwen_transport_v1"
FROZEN_DEPENDENCY_COUPLING = (
    *STAGE_DEPENDENCIES, "src/academic_agent/report_evidence_stage_qwen_transport.py",
)
JSON_KEYWORD = re.compile(r"\bJSON\b", re.ASCII | re.IGNORECASE)


def final_json_configuration() -> dict:
    """Declare final-only JSON and its precondition without modifying old config."""
    return {
        **stage_configuration(),
        "response_format_by_stage": {
            "initial": "omitted", "read": "omitted", "final": {"type": "json_object"},
        },
        "final_json_keyword_guard": {
            "roles": ["system", "user"], "pattern": r"\bJSON\b",
            "flags": ["ASCII", "IGNORECASE"], "repair": False,
        },
    }


class FinalJsonQwenLedger(CanaryLedger):
    """Fresh code-owned identity; reserve/finish are the unchanged frozen methods."""

    def __init__(self, output_dir):
        super().__init__(output_dir, {
            "transport_identity": TRANSPORT_IDENTITY,
            "scope": "offline_contract_no_live_authorization",
            "live_authorization": False,
            "configuration": final_json_configuration(),
            # Coupling paths are not verified hashes or permission to spend.
            "frozen_dependency_coupling": list(FROZEN_DEPENDENCY_COUPLING),
        })


class FinalJsonQwenFollowupTransport(QwenFollowupTransport):
    """Pinned final-only JSON adapter, with no ambient key lookup.

    Inherits only credential validation and the one-shot _post primitive. Tests
    intercept that primitive at httpx.MockTransport, not at this callback. No
    network execution is authorized by constructing this network-capable class.
    """

    def __init__(self, api_key: str, ledger: FinalJsonQwenLedger):
        if type(ledger) is not FinalJsonQwenLedger:
            raise CanaryStopped("final_json_ledger_required")
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
                # Add JSON mode before encoding AND reservation. Keep native
                # history unchanged; JSON-only is not a schema or parser repair.
                del body["tools"]
                body["response_format"] = {"type": "json_object"}
            if _contains_secret(body, self._api_key):
                raise CanaryStopped("secret_in_request")
            # The same canonical encoding underlies reserve's SHA256. Do not
            # edit wire or body after reservation, including none -> auto.
            wire = _encoded(body)
            if len(wire) > REQUEST_BYTES:
                raise CanaryStopped("request_too_large")
            if tool_choice == "none" and not any(
                previous.get("role") in ("system", "user")
                and type(previous.get("content")) is str
                and JSON_KEYWORD.search(previous["content"])
                for previous in body["messages"]
            ):
                # Source/tool/assistant text cannot satisfy the instruction
                # prerequisite. Missing JSON never buys a repair request.
                raise CanaryStopped("final_json_keyword_required")
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
