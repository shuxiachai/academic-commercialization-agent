"""A model that refuses one of our optional parameters gets the shape it asks for, not a failed run."""

from __future__ import annotations

import io
import json
import os
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from academic_agent import language
from academic_agent import llm_parameter_fallback as fallback
from academic_agent.llm_config import _wrap_with_retry, configure_llm_deadline
from api.runs import _public_failure_reason

BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# The reply qwen3.7-max-preview gave every production call on 2026-10-23.
THINKING_ONLY = ("BadRequestError: Error code: 400 - {'error': {'message': '<400> InternalError.Algo.InvalidParameter: "
                 "The value of the enable_thinking parameter is restricted to True.', 'type': 'invalid_request_error', "
                 "'code': 'invalid_parameter_error'}}")


def refusal(text: str) -> str:
    return f"Error code: 400 - {{'error': {{'message': '{text}', 'code': 'invalid_parameter_error'}}}}"


@pytest.fixture(autouse=True)
def nothing_learned():
    fallback.reset()
    yield
    fallback.reset()


@pytest.mark.parametrize("message,sent,expected", [
    (THINKING_ONLY, {"enable_thinking": False}, ("enable_thinking", True)),
    (refusal("parameter.enable_thinking must be set to false for non-streaming calls"),
     {"enable_thinking": True}, ("enable_thinking", False)),
    (refusal("enable_thinking is not supported for this model"), {"enable_thinking": False},
     ("enable_thinking", fallback.OMIT)),
    (refusal("response_format type json_object is not supported by this model"),
     {"response_format": {"type": "json_object"}}, ("response_format", fallback.OMIT)),
    (refusal("Unsupported value: temperature does not support 0.0 with this model"), {"temperature": 0.0},
     ("temperature", fallback.OMIT)),
    # Values we already send, parameters we did not send, and other failures change nothing.
    (refusal("parameter.enable_thinking must be set to false for non-streaming calls"),
     {"enable_thinking": False}, None),
    (THINKING_ONLY, {}, None),
    (refusal("Range of input length should be [1, 30720]"), {"enable_thinking": False}, None),
    ("Error code: 429 - rate limit reached for enable_thinking requests", {"enable_thinking": False}, None),
    ("Connection reset by peer", {"enable_thinking": False}, None),
])
def test_each_refusal_asks_for_one_change_or_none(message, sent, expected):
    assert fallback.adjustment(message, sent) == expected


class _Provider:
    """Stands in for the CrewAI provider instance: the attributes it builds each request from."""

    def __init__(self, model="qwen3.7-max-preview", refuse=lambda shape: None):
        self.base_url, self.model = BASE, model
        self.timeout = 150.0
        self._client = _Client(150.0)
        self.additional_params = {"extra_body": {"enable_thinking": False}}
        self.response_format = {"type": "json_object"}
        self.temperature = 0.0
        self.sent: list[dict] = []
        self._refuse = refuse

    def call(self, messages):
        shape = {"enable_thinking": (self.additional_params.get("extra_body") or {}).get("enable_thinking"),
                 "response_format": self.response_format, "temperature": self.temperature}
        self.sent.append(shape)
        error = self._refuse(shape)
        if error:
            raise RuntimeError(error)
        return "ok"


class _Client:
    """The OpenAI SDK client's with_options, which copies a client with new options."""

    def __init__(self, timeout):
        self.timeout = timeout

    def with_options(self, *, timeout):
        return _Client(timeout)


def thinking_only(shape):
    return THINKING_ONLY if shape["enable_thinking"] is False else None


MESSAGES = [{"role": "user", "content": "hi"}]


def test_a_thinking_only_model_is_answered_with_thinking_on_and_that_is_remembered():
    first = _Provider(refuse=thinking_only)
    assert _wrap_with_retry(first).call(MESSAGES) == "ok"
    assert [s["enable_thinking"] for s in first.sent] == [False, True]
    assert fallback.learned(BASE, "qwen3.7-max-preview") == {"enable_thinking": True}

    # The next agent's LLM sends the accepted shape at once: one request, no refusal.
    second = _Provider(refuse=thinking_only)
    assert _wrap_with_retry(second).call(MESSAGES) == "ok"
    assert second.sent == [{"enable_thinking": True, "response_format": {"type": "json_object"}, "temperature": 0.0}]


def test_a_thinking_only_model_gets_twice_the_per_call_time_once():
    provider = _Provider(refuse=thinking_only)
    llm = configure_llm_deadline(_wrap_with_retry(provider), deadline_monotonic=None, stage="Writer",
                                 request_timeout_seconds=150)
    llm.call(MESSAGES)
    llm.call(MESSAGES)
    assert (provider.timeout, provider._client.timeout) == (300.0, 300.0)
    assert llm._academic_agent_call_budget.request_timeout_seconds == 300

    # A later agent's LLM starts from what was learned, and gets the time at once.
    later = _Provider(refuse=thinking_only)
    _wrap_with_retry(later).call(MESSAGES)
    assert (later.timeout, later._client.timeout, len(later.sent)) == (300.0, 300.0, 1)


def test_a_model_that_accepts_the_default_keeps_thinking_off():
    provider = _Provider(model="qwen3.8-27b")
    assert _wrap_with_retry(provider).call(MESSAGES) == "ok"
    assert [s["enable_thinking"] for s in provider.sent] == [False]
    assert fallback.learned(BASE, "qwen3.8-27b") == {}
    assert (provider.timeout, provider._client.timeout) == (150.0, 150.0)


def test_what_one_model_learns_does_not_change_another():
    _wrap_with_retry(_Provider(refuse=thinking_only)).call(MESSAGES)
    other = _Provider(model="qwen3.8-27b")
    _wrap_with_retry(other).call(MESSAGES)
    assert other.sent[0]["enable_thinking"] is False


def test_json_mode_and_temperature_are_dropped_only_when_refused():
    def refuse(shape):
        if shape["response_format"] is not None:
            return refusal("response_format type json_object is not supported by this model")
        if shape["temperature"] is not None:
            return refusal("Unsupported value: temperature does not support 0.0 with this model")
        return None

    provider = _Provider(model="strict-model", refuse=refuse)
    assert _wrap_with_retry(provider).call(MESSAGES) == "ok"
    assert [(s["response_format"], s["temperature"]) for s in provider.sent] == [
        ({"type": "json_object"}, 0.0), (None, 0.0), (None, None)]
    assert provider.sent[-1]["enable_thinking"] is False


def test_a_refusal_naming_nothing_we_can_change_fails_at_once():
    provider = _Provider(refuse=lambda shape: refusal("Range of input length should be [1, 30720]"))
    with pytest.raises(RuntimeError, match="input length"):
        _wrap_with_retry(provider).call(MESSAGES)
    assert len(provider.sent) == 1


def test_a_provider_insisting_on_what_we_already_send_is_not_resent_in_a_loop():
    provider = _Provider(refuse=lambda shape: refusal(
        "parameter.enable_thinking must be set to false for non-streaming calls"))
    with pytest.raises(RuntimeError):
        _wrap_with_retry(provider).call(MESSAGES)
    assert len(provider.sent) == 1


class _Resp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


@pytest.mark.allow_llm
def test_the_language_helper_adapts_the_same_way_and_shares_what_it_learned():
    bodies, timeouts = [], []

    def fake_urlopen(request, timeout=None):
        body = json.loads(request.data)
        bodies.append(body)
        timeouts.append(timeout)
        if body.get("enable_thinking") is False:
            reply = {"error": {"message": "<400> InternalError.Algo.InvalidParameter: The value of the "
                                          "enable_thinking parameter is restricted to True.",
                               "code": "invalid_parameter_error"}}
            raise HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(json.dumps(reply).encode()))
        return _Resp({"choices": [{"message": {"content": "ready"}}]})

    env = {"LLM_PROVIDER": "qwen", "QWEN_MODEL": "qwen3.7-max-preview", "DASHSCOPE_API_KEY": "sk-test"}
    with patch.dict(os.environ, env), patch("academic_agent.language.urlopen", fake_urlopen):
        assert language._llm_call("plan this", system="s") == "ready"
        assert language._llm_call("plan that", system="s") == "ready"
    assert [b["enable_thinking"] for b in bodies] == [False, True, True]
    # A slow refusal must arrive inside the bound, and thinking takes longer still.
    assert timeouts == [60, 120, 120]
    assert fallback.learned(BASE, "qwen3.7-max-preview") == {"enable_thinking": True}

    # The agents' LLMs in the same process start from what the helper learned.
    provider = _Provider(refuse=thinking_only)
    _wrap_with_retry(provider).call(MESSAGES)
    assert [s["enable_thinking"] for s in provider.sent] == [True]


@pytest.mark.parametrize("raw,expected", [
    ("BadRequestError: Error code: 403 - {'error': {'code': 'AllocationQuota.FreeTierOnly', 'message': "
     "'The free tier of the model has been exhausted.'}}", "free quota"),
    ("BadRequestError: Error code: 400 - {'error': {'message': 'Access denied, please make sure your account "
     "is in good standing.'}}", "account"),
    ("NotFoundError: Error code: 404 - {'error': {'code': 'model_not_found', 'message': 'The model `x` does "
     "not exist or you do not have access to it.'}}", "not available"),
    (refusal("Range of input length should be [1, 30720]"), "rejected the request"),
])
def test_a_model_the_deployment_cannot_use_says_what_to_check(raw, expected):
    assert expected in _public_failure_reason(raw)
