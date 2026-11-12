"""Anthropic is asked for an answer long enough to hold a report.

The Messages API requires ``max_tokens``, so CrewAI's Anthropic provider
always sends one, and its default is 4096. Nothing here set it. The report
writer's answer is the report: of the 436 saved on the maintainer's machine,
391 (89%) are longer than 4096 tokens by an OpenAI tokenizer (median 5,868,
longest 13,506), and the current Claude models spend part of the same
allowance on thinking. No run had ever gone through Anthropic, so nothing had
shown it; the provider tests looked only at the arguments handed to a stand-in.

One class below builds the real provider with a made-up key and reads the
request it would send. Nothing is sent: no call is made.
"""

from __future__ import annotations

import pytest

from academic_agent import llm_parameter_fallback as fallback
from academic_agent.llm_config import (
    ANTHROPIC_MAX_TOKENS,
    ANTHROPIC_STREAM_MAX_TOKENS,
    _wrap_with_retry,
    create_llm,
)

BASE = "https://api.anthropic.com"
MESSAGES = [{"role": "user", "content": "hi"}]
# The longest saved report, by a tokenizer that counts fewer tokens than Anthropic's.
LONGEST_SAVED_REPORT = 13_506


def too_many(asked: int, allowed: int, model: str = "claude-opus-4-1-20250805") -> str:
    """The Messages API's refusal of an output limit above the model's own."""
    return ("BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
            f"'message': 'max_tokens: {asked} > {allowed}, which is the maximum allowed number of output tokens "
            f"for {model}'}}}}")


@pytest.fixture(autouse=True)
def nothing_learned():
    fallback.reset()
    yield
    fallback.reset()


class TestTheRequestTheRealProviderBuilds:
    """create_llm through CrewAI's own factory and Anthropic class."""

    def _built(self, **options):
        return create_llm(provider="anthropic", api_key="made-up-key-never-sent", model="claude-sonnet-5-5", **options)

    def test_a_streamed_node_asks_for_room_for_a_report_and_the_thinking_before_it(self):
        llm = self._built(stream=True)
        assert type(llm).__name__ == "AnthropicCompletion"
        assert llm.max_tokens == ANTHROPIC_STREAM_MAX_TOKENS
        sent = llm._prepare_completion_params(messages=MESSAGES, system_message=None)
        assert sent["max_tokens"] == ANTHROPIC_STREAM_MAX_TOKENS and sent["stream"] is True
        # Several times the longest report: thinking is counted against the same limit.
        assert ANTHROPIC_STREAM_MAX_TOKENS >= 4 * LONGEST_SAVED_REPORT

    def test_a_plain_call_asks_for_less_and_still_more_than_the_default(self):
        llm = self._built(json_mode=True, temperature=0.0)
        sent = llm._prepare_completion_params(messages=MESSAGES, system_message=None)
        assert sent["max_tokens"] == ANTHROPIC_MAX_TOKENS and sent["stream"] is False
        # A plain request waits for the whole answer inside one HTTP timeout.
        assert 4096 < ANTHROPIC_MAX_TOKENS < ANTHROPIC_STREAM_MAX_TOKENS

    @pytest.mark.parametrize("provider,model", [
        ("qwen", "qwen3.8-max"), ("deepseek", "deepseek-chat"), ("openai", "gpt-4o"),
    ])
    def test_the_other_providers_are_sent_no_limit_as_before(self, provider, model):
        llm = create_llm(provider=provider, api_key="made-up-key-never-sent", model=model, stream=True)
        assert llm.max_tokens is None


@pytest.mark.parametrize("message,sent,expected", [
    (too_many(64000, 32000), {"max_tokens": 64000}, ("max_tokens", 32000)),
    (too_many(64000, 8192, "claude-3-5-haiku-20241022"), {"max_tokens": 64000}, ("max_tokens", 8192)),
    # The model's name is full of digits; none of them is the limit.
    (too_many(64000, 64000), {"max_tokens": 64000}, None),
    (too_many(64000, 64000, "claude-test-8192"), {"max_tokens": 64000}, None),
    # Two numbers under what was asked: the larger. Lowering further than told
    # would cut answers the model could have given.
    ("Error code: 400 - {'error': {'type': 'invalid_request_error', 'message': 'max_tokens: 64000 > 32000 "
     "(of which 2048 may be thinking)'}}", {"max_tokens": 64000}, ("max_tokens", 32000)),
    ("BadRequestError: Error code: 400 - {'error': {'type': 'invalid_request_error', 'message': "
     "'max_tokens is too large for claude-opus-4-1-20250805'}}", {"max_tokens": 64000}, None),
    # A limit we did not send, a limit already at or under what is allowed, and other failures.
    (too_many(64000, 32000), {}, None),
    (too_many(64000, 32000), {"max_tokens": 16000}, None),
    (too_many(64000, 32000), {"max_tokens": 32000}, None),
    ("Error code: 429 - rate limit: max_tokens: 64000 > 32000", {"max_tokens": 64000}, None),
    ("Connection reset by peer", {"max_tokens": 64000}, None),
    # Too small to be an output limit: a count of something else.
    ("Error code: 400 - {'error': {'type': 'invalid_request_error', 'message': 'max_tokens: 64000 exceeds the "
     "limit after 3 attempts'}}", {"max_tokens": 64000}, None),
])
def test_a_refused_limit_is_lowered_to_the_one_the_model_allows(message, sent, expected):
    assert fallback.adjustment(message, sent) == expected


class _Provider:
    """Stands in for the Anthropic provider instance: the fields a request is built from."""

    def __init__(self, model="claude-opus-4-1-20250805", max_tokens=ANTHROPIC_STREAM_MAX_TOKENS, allowed=32000):
        self.base_url, self.model = BASE, model
        self.timeout = 60.0
        self.stream = True
        self.max_tokens = max_tokens
        self.temperature = None
        self.sent: list[int] = []
        self._allowed = allowed

    def call(self, messages):
        self.sent.append(self.max_tokens)
        if self.max_tokens > self._allowed:
            raise RuntimeError(too_many(self.max_tokens, self._allowed, self.model))
        return "ok"


def test_an_older_model_is_resent_at_its_own_limit_and_that_is_remembered():
    first = _Provider()
    assert _wrap_with_retry(first).call(MESSAGES) == "ok"
    assert first.sent == [ANTHROPIC_STREAM_MAX_TOKENS, 32000]
    assert fallback.learned(BASE, first.model) == {"max_tokens": 32000}

    # The next node's LLM asks for the accepted limit at once: one request, no refusal.
    second = _Provider()
    assert _wrap_with_retry(second).call(MESSAGES) == "ok"
    assert second.sent == [32000]


def test_what_was_learned_lowers_a_limit_and_never_raises_one():
    _wrap_with_retry(_Provider()).call(MESSAGES)
    # A plain call of the same model asks for less than was learned, and keeps asking for that.
    plain = _Provider(max_tokens=ANTHROPIC_MAX_TOKENS)
    assert _wrap_with_retry(plain).call(MESSAGES) == "ok"
    assert plain.sent == [ANTHROPIC_MAX_TOKENS]
    # So does the language helper's request body, which asks for a few hundred tokens.
    body = {"model": plain.model, "max_tokens": 300}
    fallback.apply_to_payload(body, fallback.learned(BASE, plain.model))
    assert body["max_tokens"] == 300
    large = {"model": plain.model, "max_tokens": 50000}
    fallback.apply_to_payload(large, fallback.learned(BASE, plain.model))
    assert large["max_tokens"] == 32000
    # A body that names no limit is not given one.
    bare = {"model": plain.model}
    fallback.apply_to_payload(bare, fallback.learned(BASE, plain.model))
    assert bare == {"model": plain.model}


def test_a_model_that_accepts_the_limit_is_asked_once_and_nothing_is_learned():
    provider = _Provider(model="claude-sonnet-5-5", allowed=128000)
    assert _wrap_with_retry(provider).call(MESSAGES) == "ok"
    assert provider.sent == [ANTHROPIC_STREAM_MAX_TOKENS]
    assert fallback.learned(BASE, "claude-sonnet-5-5") == {}


def test_a_limit_the_model_keeps_refusing_is_not_resent_in_a_loop():
    """A provider that names the limit we already send fails as any other refusal does."""
    provider = _Provider()
    provider._allowed = -1  # refuses whatever it is sent
    refusals = iter([too_many(64000, 32000), too_many(32000, 32000)])
    provider.call = lambda messages: (_ for _ in ()).throw(RuntimeError(next(refusals)))
    with pytest.raises(RuntimeError, match="maximum allowed"):
        _wrap_with_retry(provider).call(MESSAGES)
    assert provider.max_tokens == 32000
