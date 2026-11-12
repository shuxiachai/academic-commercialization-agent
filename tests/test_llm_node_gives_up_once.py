"""A node whose call the wrapper gave up on is not run again by the framework.

CrewAI re-executes a task whose agent raised: `Agent.max_retry_limit` is 2 and
the count is never reset, so any exception from a node's model call starts the
node over, up to twice in a run. The wrapper here did not know. It makes up to
five attempts on a streamed call (llm_config._STREAM_MAX_ATTEMPTS, chosen in
#364 as what a run's time affords) and then raises, and CrewAI called it
again. Measured on 2026-11-12 with one node and canned answers:

    a rejected key (401)                   3 requests, for an answer that cannot change
    a refused request (400)                3 requests
    a connection that times out each time  15 attempts, three times the five intended

On a silent link each call is about five and a half minutes (five waits of 60
seconds and the backoff between them), so a run could take sixteen minutes to
say what it knew after five. The production run of 2026-11-09 that was
cancelled at 728 seconds had made seven attempts on its writer.

Two things stay as they were. An answer with no text is not an error to the
wrapper; CrewAI raises on it and runs the node again, and that is the only
retry such an answer has. A rate limit (429) is not retried by the wrapper at
all, so CrewAI's re-execution is the only second chance it gets; it is left
alone until the wrapper has a wait of its own for it.

The provider objects are the real ones, built with made-up keys. Each HTTP
request is counted and answered here; nothing is sent, and no backoff is slept.
"""

from __future__ import annotations

import json

import httpx
import pytest
from crewai import Agent, Crew, Task

from academic_agent import llm_config
from academic_agent.llm_config import RunDeadlineExceeded, _wrap_with_retry, create_llm, set_attempt_observer

MESSAGES = [{"role": "user", "content": "Write the report."}]
ANSWER = "The report."


def _stream(body: dict, text: str) -> bytes:
    def chunk(delta, reason, **more):
        return {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": body["model"],
                "choices": [{"index": 0, "delta": delta, "finish_reason": reason}], **more}

    usage = {"prompt_tokens": 100, "completion_tokens": 3 if text else 0, "total_tokens": 103}
    events = [chunk({"role": "assistant", "content": text}, None), chunk({}, "stop"),
              {**chunk({}, None), "choices": [], "usage": usage}]
    return ("".join("data: " + json.dumps(event) + "\n\n" for event in events) + "data: [DONE]\n\n").encode()


@pytest.fixture
def provider(monkeypatch):
    """Answers every request as `provider.answers` says: one entry per request, the last repeated."""
    class Answering:
        answers: list[str] = ["ok"]
        requests = 0

    def answer(client, request, **_):
        kind = Answering.answers[min(Answering.requests, len(Answering.answers) - 1)]
        Answering.requests += 1
        body = json.loads(request.content)
        if kind == "auth":
            refusal = {"error": {"message": "made-up key", "type": "authentication_error"}}
            return httpx.Response(401, json=refusal, request=request)
        if kind == "refused":
            refusal = {"error": {"message": "The request was refused.", "type": "invalid_request_error"}}
            return httpx.Response(400, json=refusal, request=request)
        if kind == "rate":
            refusal = {"error": {"message": "Rate limit reached.", "type": "rate_limit_error"}}
            return httpx.Response(429, json=refusal, request=request)
        if kind == "dead":
            raise httpx.ReadTimeout("timed out", request=request)
        text = "" if kind == "empty" else ANSWER
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=_stream(body, text),
                              request=request)

    monkeypatch.setattr(httpx.Client, "send", answer)
    monkeypatch.setattr(llm_config.time, "sleep", lambda seconds: None)
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


def by_call(attempts) -> dict[int, list[str]]:
    calls: dict[int, list[str]] = {}
    for row in attempts:
        calls.setdefault(row["call"], []).append(row["outcome"])
    return calls


def run_one_node():
    """One agent, one task, through CrewAI's own executor; returns the crew's result."""
    llm = create_llm(provider="qwen", api_key="made-up-key-never-sent", model="deepseek-v4.1-flash-1017", stream=True)
    agent = Agent(role="Report writer", goal="Write the report.", backstory="Writes reports.", llm=llm, verbose=False)
    task = Task(description="Write the report.", expected_output="A report.", agent=agent)
    return Crew(agents=[agent], tasks=[task], verbose=False).kickoff()


class TestThroughCrewAI:

    @pytest.mark.parametrize("kind,error", [("auth", "made-up key"), ("refused", "The request was refused")])
    def test_a_refusal_that_cannot_change_is_asked_once(self, provider, attempts, kind, error):
        provider.answers = [kind]

        with pytest.raises(Exception, match=error):
            run_one_node()

        assert provider.requests == 1
        assert by_call(attempts) == {1: ["error"]}

    def test_a_dead_connection_gets_the_five_attempts_it_was_given_and_no_more(self, provider, attempts):
        provider.answers = ["dead"]

        with pytest.raises(Exception, match="timed out"):
            run_one_node()

        assert provider.requests == llm_config._STREAM_MAX_ATTEMPTS == 5
        assert by_call(attempts) == {1: ["timeout"] * 5}

    def test_a_connection_that_comes_back_inside_those_attempts_completes_the_run(self, provider, attempts):
        provider.answers = ["dead", "dead", "ok"]

        assert ANSWER in str(run_one_node())

        assert provider.requests == 3
        assert by_call(attempts) == {1: ["timeout", "timeout", "returned"]}

    def test_an_answer_with_no_text_is_still_asked_for_again_by_crewai(self, provider, attempts):
        """The only retry an empty answer has. The call returned; the wrapper gave up on nothing."""
        provider.answers = ["empty", "ok"]

        assert ANSWER in str(run_one_node())

        assert provider.requests == 2
        assert by_call(attempts) == {1: ["returned"], 2: ["returned"]}

    def test_a_rate_limit_keeps_the_second_chances_crewai_gives_it(self, provider, attempts):
        """The wrapper does not retry a 429 and has no wait for one, so this is left as it was."""
        provider.answers = ["rate", "ok"]

        assert ANSWER in str(run_one_node())

        assert provider.requests == 2
        assert by_call(attempts) == {1: ["error"], 2: ["returned"]}


class _StandIn:
    """A provider reduced to what the wrapper touches: each call pops the next step and returns or raises it."""

    def __init__(self, steps):
        self.base_url, self.model = "https://provider.example/v1", "some-model"
        self.stream, self.timeout, self.temperature, self.max_tokens = True, 60.0, None, None
        self.steps, self.asked = list(steps), 0

    def call(self, messages):
        self.asked += 1
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step


def timed_out():
    return TimeoutError("Request timed out.")


class TestTheWrapperItself:

    @pytest.fixture(autouse=True)
    def no_backoff(self, monkeypatch):
        monkeypatch.setattr(llm_config.time, "sleep", lambda seconds: None)

    def test_after_its_attempts_are_used_up_the_node_raises_the_same_error_without_asking(self, attempts, capsys):
        provider = _StandIn([timed_out() for _ in range(5)] + ["never asked for"])
        llm = _wrap_with_retry(provider)
        llm_config.set_llm_stage(llm, "Report Writer")
        with pytest.raises(TimeoutError) as first:
            llm.call(MESSAGES)
        capsys.readouterr()

        with pytest.raises(TimeoutError) as second:
            llm.call(MESSAGES)

        assert second.value is first.value
        assert provider.asked == 5
        # No attempt was made, so none is recorded.
        assert by_call(attempts) == {1: ["timeout"] * 5}
        assert "[llm] Report Writer: not asked again after TimeoutError" in capsys.readouterr().err

    def test_a_refusal_the_wrapper_does_not_retry_is_remembered_too(self, attempts):
        provider = _StandIn([RuntimeError("Error code: 401 - invalid api key"), "never asked for"])
        llm = _wrap_with_retry(provider)
        for _ in range(3):
            with pytest.raises(RuntimeError, match="401"):
                llm.call(MESSAGES)
        assert provider.asked == 1
        assert by_call(attempts) == {1: ["error"]}

    def test_a_run_out_of_time_is_remembered_with_the_error_that_used_the_time_up(self, attempts):
        provider = _StandIn([timed_out(), "never asked for"])
        llm = _wrap_with_retry(provider)
        # Room for the first attempt and not for the wait before a second.
        llm_config.configure_llm_deadline(
            llm, deadline_monotonic=llm_config.time.monotonic() + 61.0, stage="Report Writer",
            request_timeout_seconds=60.0)
        with pytest.raises(RunDeadlineExceeded) as first:
            llm.call(MESSAGES)
        assert isinstance(first.value.__cause__, TimeoutError)

        with pytest.raises(RunDeadlineExceeded) as second:
            llm.call(MESSAGES)

        # The cause is what the API reads to say the provider was unreachable.
        assert second.value is first.value and isinstance(second.value.__cause__, TimeoutError)
        assert provider.asked == 1

    @pytest.mark.parametrize("refusal", [
        RuntimeError("Error code: 429 - {'error': {'message': 'Too many requests.'}}"),
        RuntimeError("The rate limit for requests per minute was reached."),
        type("RateLimitError", (Exception,), {})("Too many requests."),
    ], ids=["status", "words", "class"])
    def test_a_rate_limit_is_not_remembered(self, attempts, refusal):
        provider = _StandIn([refusal, "the answer"])
        llm = _wrap_with_retry(provider)
        with pytest.raises(type(refusal)):
            llm.call(MESSAGES)

        assert llm.call(MESSAGES) == "the answer"
        assert by_call(attempts) == {1: ["error"], 2: ["returned"]}

    def test_a_failure_recovered_inside_the_attempts_leaves_the_node_usable(self, attempts):
        provider = _StandIn([timed_out(), "a draft", "a second draft"])
        llm = _wrap_with_retry(provider)

        assert llm.call(MESSAGES) == "a draft"
        # A guardrail sending the node back is a new call, and it is made.
        assert llm.call(MESSAGES) == "a second draft"
        assert by_call(attempts) == {1: ["timeout", "returned"], 2: ["returned"]}

    def test_one_nodes_failure_is_not_anothers(self, attempts):
        failed = _wrap_with_retry(_StandIn([RuntimeError("Error code: 400 - refused")]))
        with pytest.raises(RuntimeError):
            failed.call(MESSAGES)

        assert _wrap_with_retry(_StandIn(["the answer"])).call(MESSAGES) == "the answer"
