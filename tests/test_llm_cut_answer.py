"""An answer the provider cut at its output limit is a named failure, not an answer.

Every provider says why an answer ended: "length" on the OpenAI-shaped APIs
(Model Studio, DeepSeek, OpenAI), "max_tokens" on Anthropic. Until
2026-11-12 nothing here read it. A cut answer came back as an ordinary
string and its attempt was recorded as "returned".

DeepSeek direct, 2026-11-12: the writer's answer stopped at exactly 8,192
output tokens, in the middle of a reference entry, and the run completed.
What the report guardrail does with a cut report, tried on that report:

- cut in the references: passes; the list is rebuilt, so nothing is lost;
- cut inside "Evidence Limitations": passes, and the section ends mid-word;
- cut anywhere earlier: blocked as "Missing required heading", after which
  the whole report is written again and cut again.

The five JSON nodes fare no better: a cut answer is invalid JSON, is asked
for again up to twice, and fails as a parse error.

The provider objects below are the real ones, built with made-up keys. Each
HTTP request is counted and answered here with a canned response; nothing is
sent. The canned streams end the way the real ones were seen to end on
2026-11-12, with a real 20-token limit: Model Studio sends the stop reason
in one chunk and the usage in the next; DeepSeek sends both in one chunk,
and CrewAI's stream reader, having taken the usage from a chunk, skips the
rest of it. On DeepSeek, streamed, the stop reason never arrives, and a cut
is known by the answer having used every output token the request allowed.
"""

from __future__ import annotations

import json

import httpx
import pytest
from crewai import Agent, Crew, Task

from academic_agent import llm_config
from academic_agent.llm_config import AnswerCutError, _wrap_with_retry, create_llm, set_attempt_observer

PART = "A report that stops in the mid"
MESSAGES = [{"role": "user", "content": "Write the report."}]
PROVIDERS = [("qwen", "qwen3.8-max"), ("deepseek", "deepseek-chat"), ("openai", "gpt-4o"),
             ("anthropic", "claude-sonnet-5-5")]
#: What each API calls an answer ended by the output limit.
CUT = {"qwen": "length", "deepseek": "length", "openai": "length", "anthropic": "max_tokens"}
#: Output tokens of an answer that ended by itself, and of a cut one when the request named no limit.
SHORT, UNASKED_LIMIT = 120, 8192


def reason_given(name: str, stream: bool) -> str:
    """The stop reason the error states for a cut answer on this path."""
    if name == "deepseek" and stream:
        return f"not reported; all {llm_config.DEEPSEEK_STREAM_MAX_TOKENS} output tokens allowed were used"
    return CUT[name]


def _events(events) -> bytes:
    lines = []
    for name, data in events:
        if name:
            lines.append(f"event: {name}")
        lines.append("data: " + (data if isinstance(data, str) else json.dumps(data)))
        lines.append("")
    return ("\n".join(lines) + "\n").encode()


def _anthropic(body: dict, stop: str, request: httpx.Request) -> httpx.Response:
    if not body.get("stream"):
        return httpx.Response(200, request=request, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": body["model"],
            "content": [{"type": "text", "text": PART}], "stop_reason": stop, "stop_sequence": None,
            "usage": {"input_tokens": 100, "output_tokens": 16000}})
    stream = _events([
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_1", "type": "message", "role": "assistant", "model": body["model"], "content": [],
            "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 100, "output_tokens": 1}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "text_delta", "text": PART}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
                           "usage": {"output_tokens": 64000}}),
        ("message_stop", {"type": "message_stop"}),
    ])
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=stream, request=request)


def _openai_shaped(body: dict, finish: str, request: httpx.Request) -> httpx.Response:
    spent = body.get("max_tokens", UNASKED_LIMIT) if finish == "length" else SHORT
    usage = {"prompt_tokens": 100, "completion_tokens": spent, "total_tokens": 100 + spent}
    if not body.get("stream"):
        return httpx.Response(200, request=request, json={
            "id": "chatcmpl-1", "object": "chat.completion", "created": 1, "model": body["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": PART}, "finish_reason": finish}],
            "usage": usage})

    def chunk(delta, reason, **more):
        return {"id": "chatcmpl-1", "object": "chat.completion.chunk", "created": 1, "model": body["model"],
                "choices": [{"index": 0, "delta": delta, "finish_reason": reason}], **more}

    if "deepseek" in request.url.host:
        ending = [(None, chunk({"content": ""}, finish, usage=usage))]
    else:
        ending = [(None, chunk({}, finish)), (None, {**chunk({}, None), "choices": [], "usage": usage})]
    stream = _events([(None, chunk({"role": "assistant", "content": PART}, None)), *ending, (None, "[DONE]")])
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=stream, request=request)


@pytest.fixture
def provider(monkeypatch):
    """Answers every provider request here. `provider.cut` chooses how the answer ends."""
    class Answering:
        cut = True
        requests = 0

    def answer(client, request, **_):
        Answering.requests += 1
        body = json.loads(request.content)
        if "anthropic" in request.url.host:
            return _anthropic(body, "max_tokens" if Answering.cut else "end_turn", request)
        return _openai_shaped(body, "length" if Answering.cut else "stop", request)

    monkeypatch.setattr(httpx.Client, "send", answer)
    for name, value in (("CREWAI_DISABLE_TELEMETRY", "true"), ("OTEL_SDK_DISABLED", "true"),
                        ("CREWAI_TRACING_ENABLED", "false")):
        monkeypatch.setenv(name, value)
    return Answering


@pytest.fixture
def attempts():
    records: list[dict] = []
    previous = set_attempt_observer(records.append)
    yield records
    set_attempt_observer(previous)


def built(name: str, model: str, stream: bool):
    return create_llm(provider=name, api_key="made-up-key-never-sent", model=model, stream=stream)


@pytest.mark.parametrize("stream", [True, False], ids=["streamed", "plain"])
@pytest.mark.parametrize("name,model", PROVIDERS)
class TestEveryProviderPath:

    def test_a_cut_answer_is_raised_by_name_and_not_returned(self, provider, attempts, name, model, stream):
        llm = built(name, model, stream)

        with pytest.raises(AnswerCutError) as raised:
            llm.call(MESSAGES)

        message = str(raised.value)
        assert "answer was cut at the model's output limit" in message
        assert f"(stop reason: {reason_given(name, stream)})" in message
        # The part that did arrive is not an answer and is not carried anywhere.
        assert PART not in message
        assert [(row["outcome"], row["retry"], row["error_type"]) for row in attempts] == [("cut", False, None)]
        # Asking again would be cut again at the same place: one request, one bill.
        assert provider.requests == 1

    def test_an_answer_that_ended_by_itself_is_returned_as_before(self, provider, attempts, name, model, stream):
        provider.cut = False

        assert built(name, model, stream).call(MESSAGES) == PART

        assert [row["outcome"] for row in attempts] == ["returned"]
        assert provider.requests == 1


class TestANodeWhoseAnswerWasCut:

    def test_it_is_not_asked_again_and_another_node_still_is(self, provider, attempts):
        writer = built("deepseek", "deepseek-chat", True)
        with pytest.raises(AnswerCutError):
            writer.call(MESSAGES)

        # CrewAI re-executes a task whose agent raised, up to twice. The same
        # prompt at the same limit is the same cut answer, billed again.
        with pytest.raises(AnswerCutError) as again:
            writer.call(MESSAGES)
        assert f"(stop reason: {reason_given('deepseek', True)})" in str(again.value)
        assert provider.requests == 1
        assert [row["outcome"] for row in attempts] == ["cut"]

        provider.cut = False
        assert built("deepseek", "deepseek-chat", True).call(MESSAGES) == PART
        assert provider.requests == 2

    def test_crewai_sends_one_request_for_it_and_the_run_fails_with_the_name(self, provider, attempts):
        llm = built("deepseek", "deepseek-chat", True)
        agent = Agent(role="Report writer", goal="Write the report.", backstory="Writes reports.",
                      llm=llm, verbose=False)
        task = Task(description="Write the report.", expected_output="A report.", agent=agent)

        with pytest.raises(AnswerCutError, match="answer was cut at the model's output limit"):
            Crew(agents=[agent], tasks=[task], verbose=False).kickoff()

        assert provider.requests == 1
        assert [row["outcome"] for row in attempts] == ["cut"]

    def test_the_error_names_the_node(self, provider):
        llm = built("anthropic", "claude-sonnet-5-5", True)
        # A stage is the agent's role as configured: a YAML block, ending in a newline.
        llm_config.set_llm_stage(llm, "Technology Commercialization\n  Report Writer\n")

        with pytest.raises(AnswerCutError) as raised:
            llm.call(MESSAGES)
        assert str(raised.value).startswith("Technology Commercialization Report Writer: the answer was cut")
        assert "\n" not in str(raised.value)


NO_EVENT = object()


class _StandIn:
    """A provider reduced to what the wrapper touches, for sequences no real one produces on demand.

    Each step is (stop reason, result) or (stop reason, result, usage). The
    completed-call event goes out with them, as a real provider's does, unless
    the reason is NO_EVENT. A result that is an exception is raised.
    """

    def __init__(self, script, max_tokens=None):
        self.base_url, self.model = "https://provider.example/v1", "some-model"
        self.stream, self.timeout, self.temperature, self.max_tokens = True, 60.0, None, max_tokens
        self._script = list(script)

    def _emit_call_completed_event(self, response=None, call_type=None, **fields):
        self.emitted = fields.get("finish_reason")

    def call(self, messages):
        reason, result, *usage = self._script.pop(0)
        if reason is not NO_EVENT:
            self._emit_call_completed_event(response=result, call_type="llm_call", finish_reason=reason,
                                            usage=usage[0] if usage else None)
        if isinstance(result, BaseException):
            raise result
        return result


def spent(tokens) -> dict:
    return {"prompt_tokens": 100, "completion_tokens": tokens, "total_tokens": 100}


class TestTheStopReasonBelongsToItsOwnAttempt:

    @pytest.mark.parametrize("first", [("length", None), (None, spent(64_000))], ids=["reason", "usage"])
    def test_what_was_seen_before_a_failed_attempt_does_not_mark_the_next_one(self, monkeypatch, attempts, first):
        monkeypatch.setattr(llm_config.time, "sleep", lambda seconds: None)
        reason, usage = first
        # Attempt 1 reports a cut and then breaks; attempt 2 returns and reports nothing.
        llm = _wrap_with_retry(_StandIn(
            [(reason, TimeoutError("Request timed out."), usage), (NO_EVENT, "the answer")], max_tokens=64_000))

        assert llm.call(MESSAGES) == "the answer"
        assert [row["outcome"] for row in attempts] == ["timeout", "returned"]

    @pytest.mark.parametrize("reason", ["stop", "end_turn", "tool_calls", "content_filter", None, 7])
    def test_any_other_reason_is_an_answer(self, attempts, reason):
        llm = _wrap_with_retry(_StandIn([(reason, "the answer")]))

        assert llm.call(MESSAGES) == "the answer"
        assert [row["outcome"] for row in attempts] == ["returned"]
        # Reading the reason does not keep the event from whoever else listens for it.
        assert llm.emitted == reason

    def test_the_providers_own_event_still_goes_out_when_the_answer_was_cut(self):
        llm = _wrap_with_retry(_StandIn([("length", PART)]))

        with pytest.raises(AnswerCutError):
            llm.call(MESSAGES)
        assert llm.emitted == "length"

    def test_a_provider_that_reports_no_reason_at_all_works_as_before(self, attempts):
        class Silent:
            base_url, model, stream, timeout, temperature, max_tokens = "https://x.example", "m", False, 60.0, None, None

            def call(self, messages):
                return "the answer"

        assert _wrap_with_retry(Silent()).call(MESSAGES) == "the answer"
        assert [row["outcome"] for row in attempts] == ["returned"]


class TestAnAnswerWhoseStopReasonNeverArrived:
    """DeepSeek direct, streamed. The limit the request named is the only evidence there is."""

    @pytest.mark.parametrize("tokens", [64_000, 64_001])
    def test_using_every_output_token_the_request_allowed_is_a_cut(self, attempts, tokens):
        llm = _wrap_with_retry(_StandIn([(None, PART, spent(tokens))], max_tokens=64_000))

        with pytest.raises(AnswerCutError) as raised:
            llm.call(MESSAGES)
        assert "(stop reason: not reported; all 64000 output tokens allowed were used)" in str(raised.value)
        assert [row["outcome"] for row in attempts] == ["cut"]

    @pytest.mark.parametrize("limit,usage", [
        (64_000, spent(63_999)),            # one token short of the limit: it ended by itself
        (64_000, spent(12_573)),            # the longest report so far
        (None, spent(8_192)),               # no limit was sent, so there is nothing to compare with
        (None, spent(64_000)),
        (64_000, None),                     # no usage arrived
        (64_000, {"total_tokens": 0}),      # CrewAI's placeholder when the stream carried none
        (64_000, spent(None)),
        (64_000, spent("64000")),
        (64_000, spent(True)),
        (True, spent(1)),
        (64_000, "64000"),
    ])
    def test_anything_less_is_an_answer(self, attempts, limit, usage):
        llm = _wrap_with_retry(_StandIn([(None, "the answer", usage)], max_tokens=limit))

        assert llm.call(MESSAGES) == "the answer"
        assert [row["outcome"] for row in attempts] == ["returned"]

    def test_a_reason_that_is_not_text_counts_as_none(self, attempts):
        # What a stand-in or an unusual provider type may hand over in place of a string.
        llm = _wrap_with_retry(_StandIn([(7, PART, spent(64_000))], max_tokens=64_000))

        with pytest.raises(AnswerCutError, match="not reported"):
            llm.call(MESSAGES)

    def test_a_reason_that_did_arrive_is_believed_over_the_count(self, attempts):
        llm = _wrap_with_retry(_StandIn([("stop", "the answer", spent(64_000))], max_tokens=64_000))

        assert llm.call(MESSAGES) == "the answer"
        assert [row["outcome"] for row in attempts] == ["returned"]

    def test_a_limit_lowered_for_a_smaller_host_is_the_one_compared(self, attempts):
        llm = _wrap_with_retry(_StandIn([(None, PART, spent(8_192))], max_tokens=64_000))
        llm.max_tokens = 8_192   # what llm_parameter_fallback does after a range refusal

        with pytest.raises(AnswerCutError, match="all 8192 output tokens allowed were used"):
            llm.call(MESSAGES)
