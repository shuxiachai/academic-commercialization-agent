"""Pinned, one-shot native HTTP adapter; no SDK, ambient keys or production hooks."""

import asyncio
from copy import deepcopy
import json

import httpx

from academic_agent.report_evidence_followup import _assistant_message, _strict_json
from academic_agent.report_evidence_qwen_canary import (
    CanaryLedger, CanaryStopped, CONNECT_SECONDS, ENDPOINT, INPUT_RESERVATION,
    MAX_TOKENS, MODEL, REQUEST_BYTES, RESPONSE_BYTES, TOTAL_SECONDS,
)


def validate_key(api_key: str) -> None:
    if type(api_key) is not str or not 1 <= len(api_key) <= 512 or any(char.isspace() for char in api_key):
        raise CanaryStopped("invalid_dedicated_key")


def _usage(payload: dict) -> dict | None:
    usage = payload.get("usage")
    if type(usage) is not dict:
        return None
    fields = ("prompt_tokens", "completion_tokens", "total_tokens")
    if any(type(usage.get(key)) is not int or not 0 <= usage[key] <= 1_000_000_000 for key in fields):
        return None
    if usage["prompt_tokens"] + usage["completion_tokens"] != usage["total_tokens"]:
        return None
    return {key: usage[key] for key in fields}


def _project_message(payload: dict) -> dict:
    choices = payload.get("choices")
    if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
        raise CanaryStopped("invalid_response_protocol")
    choice = choices[0]
    if type(choice.get("index")) is not int or choice["index"] != 0:
        raise CanaryStopped("invalid_response_protocol")
    raw = choice.get("message")
    if type(raw) is not dict:
        raise CanaryStopped("invalid_response_protocol")
    # Drop provider-only metadata, not tool identities, arguments or content.
    projected = {key: raw[key] for key in ("role", "content", "tool_calls", "refusal") if key in raw}
    calls = projected.get("tool_calls")
    if type(calls) is list and len(calls) <= 1:
        clean_calls = []
        for call in calls:
            if type(call) is not dict or set(call) - {"id", "type", "function", "index"}:
                raise CanaryStopped("invalid_response_protocol")
            if "index" in call and (type(call["index"]) is not int or call["index"] != 0):
                raise CanaryStopped("invalid_response_protocol")
            clean_calls.append({key: call[key] for key in ("id", "type", "function") if key in call})
        projected["tool_calls"] = clean_calls
    message = _assistant_message(projected)
    expected = "tool_calls" if message.get("tool_calls") else "stop"
    if choice.get("finish_reason") != expected:
        raise CanaryStopped("invalid_response_protocol")
    return message


def _contains_secret(value: object, key: str) -> bool:
    if isinstance(value, str):
        if key in value:
            return True
        # Content/final envelopes and tool arguments may themselves be JSON
        # strings. Decode those layers before persisting a recoverable secret.
        try:
            decoded = _strict_json(value)
        except (ValueError, TypeError, RecursionError):
            return False
        return decoded != value and _contains_secret(decoded, key)
    if isinstance(value, dict):
        return any(_contains_secret(item, key) for pair in value.items() for item in pair)
    if isinstance(value, list):
        return any(_contains_secret(item, key) for item in value)
    return False


class QwenFollowupTransport:
    def __init__(self, api_key: str, ledger: CanaryLedger):
        validate_key(api_key)
        self._api_key = api_key
        self.ledger = ledger

    async def _post(self, body: bytes, observation: dict) -> bytes:
        # Async cancellation owns the HTTP operation. There is no orphaned
        # worker thread; the deadline is still not hard process preemption.
        async with asyncio.timeout(TOTAL_SECONDS):
            async with httpx.AsyncClient(
                transport=httpx.AsyncHTTPTransport(retries=0, verify=True, trust_env=False),
                follow_redirects=False, trust_env=False, verify=True,
                timeout=httpx.Timeout(TOTAL_SECONDS, connect=CONNECT_SECONDS),
            ) as client:
                async with client.stream("POST", ENDPOINT, content=body, headers={
                    "Authorization": "Bearer " + self._api_key,
                    "Content-Type": "application/json", "Accept-Encoding": "identity",
                }) as response:
                    observation["received"] = True
                    if response.status_code != 200:
                        raise CanaryStopped("http_status_rejected")
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise CanaryStopped("response_encoding_rejected")
                    chunks = bytearray()
                    async for chunk in response.aiter_raw():
                        if len(chunks) + len(chunk) > RESPONSE_BYTES:
                            raise CanaryStopped("response_too_large")
                        chunks.extend(chunk)
                    return bytes(chunks)

    def __call__(self, *, messages, tools, tool_choice):
        # Phase-1 can recover from local argument/name errors; this frozen live
        # protocol cannot spend another paid turn repairing such an error.
        for previous in messages:
            if previous.get("role") == "tool" and _strict_json(previous["content"]).get("status") == "error":
                self.ledger.stop("local_tool_error_no_repair")
                raise CanaryStopped("local_tool_error_no_repair")
        if tool_choice != "auto":
            self.ledger.stop("invalid_tool_choice")
            raise CanaryStopped("invalid_tool_choice")
        body = {"model": MODEL, "messages": deepcopy(messages), "tools": deepcopy(tools), "tool_choice": "auto",
                "stream": False, "enable_thinking": False, "parallel_tool_calls": False,
                "temperature": 0, "max_tokens": MAX_TOKENS}
        try:
            wire = json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")
        except (TypeError, ValueError, RecursionError):
            self.ledger.stop("invalid_request_body")
            raise CanaryStopped("invalid_request_body") from None
        if len(wire) > REQUEST_BYTES:
            self.ledger.stop("request_too_large")
            raise CanaryStopped("request_too_large")
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
            message = projected
        except CanaryStopped as exc:
            error = str(exc)
        except (TimeoutError, httpx.TimeoutException):
            error = "request_timeout"
        except Exception:  # noqa: BLE001 -- neither HTTP bodies nor decoder/SDK exception chains are safe diagnostics.
            error = "response_or_transport_failed"
        self.ledger.finish(ordinal, received=observation["received"], usage=usage, error=error, message=message,
                           response_model_matches_authorized=model_matches)
        if error is not None:
            raise CanaryStopped(error) from None
        return deepcopy(message)
