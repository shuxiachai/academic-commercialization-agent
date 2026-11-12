"""Adapt the optional request parameters a model refuses, instead of failing the run.

The pipeline adds optional parameters that not every model accepts:
- Qwen's ``enable_thinking: false``, the non-thinking mode, which is faster, cheaper and the JSON default;
- ``response_format: json_object``;
- ``temperature``;
- ``max_tokens``, which Anthropic requires and which is sent large enough for a
  report (llm_config.ANTHROPIC_STREAM_MAX_TOKENS). A model whose own output
  limit is lower refuses the request and names that limit.

On 2026-10-23 production moved to qwen3.7-max-preview, a model that only runs
in thinking mode. It answered every call with HTTP 400 "The value of the
enable_thinking parameter is restricted to True", so every run failed at its
first agent call. The search planner failed the same way, but silently: it
falls back to the raw topic.

A list of models would break again with the next one. Instead, a rejection
that names one of these parameters changes that parameter as the provider
asks: thinking on, thinking off, or the parameter dropped. The call is then
sent again; a rejected request is not billed. What was learned is kept per
endpoint and model for the life of the process, so later calls send the
accepted shape at once.

A rejection that names nothing we can change still fails, as before. So does
one naming a value we already send. Each parameter is changed at most once.
"""

from __future__ import annotations

import re
import threading

# The parameters the language helper's small requests carry and may have to
# change. max_tokens is adapted too, but only on the agents' own calls: the
# helper asks for a few hundred tokens, far under any model's limit.
PARAMETERS = ("enable_thinking", "response_format", "temperature")


class _Omit:
    def __repr__(self) -> str:
        return "OMIT"


OMIT = _Omit()  # the parameter is not sent at all

# A provider's parameter rejection, not a content or quota failure.
_REJECTION_MARKERS = ("invalid_parameter", "invalidparameter", "invalid_request", "error code: 400", "<400>")
_THINKING_ON = ("restricted to true", "must be set to true", "must be true", "only supports thinking",
                "only support thinking")
_THINKING_OFF = ("restricted to false", "must be set to false", "must be false")

_learned: dict[tuple[str, str], dict[str, object]] = {}
_lock = threading.Lock()


def adjustment(message: str, sent: dict[str, object]) -> tuple[str, object] | None:
    """(parameter, new value or OMIT) that a provider's rejection asks for, or None.

    ``sent`` holds the optional parameters the refused request carried.
    """
    text = message.lower()
    if not any(marker in text for marker in _REJECTION_MARKERS):
        return None
    if "enable_thinking" in text and "enable_thinking" in sent:
        if any(marker in text for marker in _THINKING_ON):
            wanted: object = True
        elif any(marker in text for marker in _THINKING_OFF):
            wanted = False
        else:
            wanted = OMIT
        return None if wanted == sent["enable_thinking"] else ("enable_thinking", wanted)
    if ("response_format" in text or "json_object" in text) and "response_format" in sent:
        return "response_format", OMIT
    if "temperature" in text and "temperature" in sent:
        return "temperature", OMIT
    if "max_tokens" in text and "max_tokens" in sent:
        allowed = _allowed_output_tokens(text, sent["max_tokens"])
        return None if allowed is None else ("max_tokens", allowed)
    return None


# A number standing on its own, not a part of a model name or a version.
_WHOLE_NUMBER = re.compile(r"(?<![\w.-])\d+(?![\w.-])")
# Nothing smaller is an output limit; the status code and small counts are below it.
_SMALLEST_OUTPUT_LIMIT = 1024


def _allowed_output_tokens(text: str, asked: object) -> int | None:
    """The output limit a refusal names, when it is below the one asked for.

    Anthropic answers "max_tokens: 64000 > 32000, which is the maximum allowed
    number of output tokens for <model>". The limit is read as the largest
    whole number under what was asked, so another wording of the same
    refusal is understood, and a refusal naming no such number changes nothing.
    """
    if not isinstance(asked, int) or isinstance(asked, bool):
        return None
    named = [int(number) for number in _WHOLE_NUMBER.findall(text)]
    lower = [number for number in named if _SMALLEST_OUTPUT_LIMIT <= number < asked]
    return max(lower) if lower else None


def learned(base_url: str, model: str) -> dict[str, object]:
    """The parameter changes this process has learned for one endpoint and model."""
    with _lock:
        return dict(_learned.get((base_url, model), {}))


def learn(base_url: str, model: str, parameter: str, value: object) -> None:
    with _lock:
        _learned.setdefault((base_url, model), {})[parameter] = value
    change = f"omitting {parameter}" if value is OMIT else f"sending {parameter}={value!r}"
    # The model name and the parameter only; never the provider's message,
    # which can echo request content.
    print(f"[llm] {model} refused {parameter} as sent; {change} for this model from now on", flush=True)


def apply_to_payload(payload: dict, changes: dict[str, object]) -> None:
    """Apply learned changes to a JSON request body (the language helper's path)."""
    for parameter, value in changes.items():
        if value is OMIT:
            payload.pop(parameter, None)
        elif parameter == "max_tokens":
            # A learned limit is a ceiling: it lowers a larger request and
            # leaves the helper's few hundred tokens as they are.
            if isinstance(payload.get(parameter), int):
                payload[parameter] = min(payload[parameter], value)
        else:
            payload[parameter] = value


def reset() -> None:
    """Forget everything learned (tests only)."""
    with _lock:
        _learned.clear()
