"""An answer with no text is asked for again, recorded as what it is, and named when it persists.

A model sometimes ends an answer without having written one. The wrapper
returned it like any other and recorded the attempt as "returned". CrewAI
raised "Invalid response from LLM call - None or empty." and ran the node
again, up to twice (the re-execution #388 otherwise stops), so three billed
calls could go by with a record of three answers. When all three were empty
the run failed as "unknown": "The analysis failed. Retry or contact the
operator with the run ID."

The asking again is worth keeping: it is the only retry such an answer has.
It moves into the wrapper, where the attempt record and the run's time budget
can see it. A streamed node asks at most three times in all, as before, each
empty attempt is recorded as "empty", and a node that never gets text fails
by name. A plain call returns an empty answer as it always did: the paper
extractor has its own handling for one.

The provider objects are the real ones, built with made-up keys. Each HTTP
request is counted and answered here; nothing is sent.
"""

from __future__ import annotations

import json

import httpx
import pytest
from crewai import Agent, Crew, Task

from academic_agent import llm_config
from academic_agent.llm_config import AnswerCutError, EmptyAnswerError, _wrap_with_retry, create_llm
from academic_agent.llm_config import set_attempt_observer

MESSAGES = [{"role": "user", "content": "Write the report."}]
ANSWER = "The report."


def _stream(body: dict, text: str) -> bytes:
    def chunk(delta, reason, **more):
        return {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": body["model"],
                "choices": [{"index": 0, "delta": delta, "finish_reason": reason}], **more}

    usage = {"prompt_tokens": 100, "completion_tokens": 3 if text.strip() else 0, "total_tokens": 103}
    events = [chunk({"role": "assistant", "content": text}, None), chunk({}, "stop"),
              {**chunk({}, None), "choices": [], "usage": usage}]
    return ("".join("data: " + json.dumps(event) + "\n\n" for event in events) + "data: [DONE]\n\n").encode()


@pytest.fixture
def provider(monkeypatch):
    """Answers each request with the next text of `provider.texts`; the last repeats."""
    class Answering:
        texts: list[str] = [ANSWER]
        requests = 0
        waits: list[float] = []

    Answering.waits = []

    def answer(client, request, **_):
        text = Answering.texts[min(Answering.requests, len(Answering.texts) - 1)]
        Answering.requests += 1
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              content=_stream(json.loads(request.content), text), request=request)

    monkeypatch.setattr(httpx.Client, "send", answer)
    monkeypatch.setattr(llm_config.time, "sleep", Answering.waits.append)
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
    llm = create_llm(provider="qwen", api_key="made-up-key-never-sent", model="deepseek-v4.1-flash-1017", stream=True)
    agent = Agent(role="Report writer", goal="Write the report.", backstory="Writes reports.", llm=llm, verbose=False)
    task = Task(description="Write the report.", expected_output="A report.", agent=agent)
    return Crew(agents=[agent], tasks=[task], verbose=False).kickoff()


class TestThroughCrewAI:

    def test_an_empty_answer_is_asked_for_again_inside_the_call(self, provider, attempts):
        provider.texts = ["", ANSWER]

        assert ANSWER in str(run_one_node())

        assert provider.requests == 2
        assert by_call(attempts) == {1: ["empty", "returned"]}
        assert provider.waits == []

    def test_a_node_that_never_gets_text_fails_by_name_after_three_asks(self, provider, attempts):
        provider.texts = [""]

        with pytest.raises(EmptyAnswerError) as raised:
            run_one_node()

        assert "returned an answer with no text" in str(raised.value)
        assert "3 times in a row" in str(raised.value)
        # Three asks, as there always were, and CrewAI does not start the node over for three more.
        assert provider.requests == llm_config._EMPTY_ANSWER_ASKS == 3
        assert by_call(attempts) == {1: ["empty", "empty", "empty"]}

    def test_an_answer_of_blank_space_is_no_text_either(self, provider, attempts):
        provider.texts = ["  \n\t ", ANSWER]

        assert ANSWER in str(run_one_node())

        assert by_call(attempts) == {1: ["empty", "returned"]}


class _StandIn:
    """Each call pops the next step: (stop reason, result). An exception as the result is raised."""

    def __init__(self, steps, stream=True):
        self.base_url, self.model = "https://provider.example/v1", "some-model"
        self.stream, self.timeout, self.temperature, self.max_tokens = stream, 60.0, None, None
        self.steps, self.asked, self.rebuilt = list(steps), 0, 0

    def _build_sync_client(self):
        self.rebuilt += 1
        return object()

    def _emit_call_completed_event(self, response=None, call_type=None, **fields):
        pass

    def call(self, messages):
        self.asked += 1
        reason, result = self.steps.pop(0)
        self._emit_call_completed_event(response=result, call_type="llm_call", finish_reason=reason)
        if isinstance(result, BaseException):
            raise result
        return result


class TestTheWrapperItself:

    @pytest.fixture(autouse=True)
    def waits(self, monkeypatch):
        slept: list[float] = []
        monkeypatch.setattr(llm_config.time, "sleep", slept.append)
        monkeypatch.setattr(llm_config.random, "uniform", lambda low, high: 0.0)
        return slept

    @pytest.mark.parametrize("nothing", ["", None, " ", "\n\n", "\t \r\n"])
    def test_what_counts_as_no_text(self, attempts, nothing):
        llm = _wrap_with_retry(_StandIn([("stop", nothing), ("stop", "the answer")]))

        assert llm.call(MESSAGES) == "the answer"
        assert by_call(attempts) == {1: ["empty", "returned"]}

    @pytest.mark.parametrize("answer", ["0", "{}", "[]", "no", " . ", [{"name": "a_tool_call"}], {"parsed": True}, 0])
    def test_anything_else_is_an_answer(self, attempts, answer):
        provider = _StandIn([("stop", answer), ("stop", "never asked for")])
        llm = _wrap_with_retry(provider)

        assert llm.call(MESSAGES) == answer
        assert provider.asked == 1 and by_call(attempts) == {1: ["returned"]}

    def test_the_error_names_the_node_and_the_count_and_carries_nothing_else(self, attempts):
        llm = _wrap_with_retry(_StandIn([("stop", ""), ("stop", None), ("stop", " ")]))
        llm_config.set_llm_stage(llm, "Technology Commercialization\n  Report Writer\n")

        with pytest.raises(EmptyAnswerError) as raised:
            llm.call(MESSAGES)

        assert str(raised.value) == ("Technology Commercialization Report Writer: the model returned an answer "
                                     "with no text, 3 times in a row; there was nothing to use.")
        assert [(row["attempt"], row["outcome"], row["retry"], row["error_type"]) for row in attempts] == [
            (1, "empty", True, None), (2, "empty", True, None), (3, "empty", False, None)]

    def test_the_node_is_not_asked_again_after_that(self, attempts):
        provider = _StandIn([("stop", "")] * 3 + [("stop", "never asked for")])
        llm = _wrap_with_retry(provider)
        with pytest.raises(EmptyAnswerError) as first:
            llm.call(MESSAGES)

        with pytest.raises(EmptyAnswerError) as second:
            llm.call(MESSAGES)

        assert second.value is first.value and provider.asked == 3

    def test_asking_again_is_immediate_on_the_same_connection_and_says_so(self, waits, capsys):
        provider = _StandIn([("stop", ""), ("stop", "the answer")])
        llm = _wrap_with_retry(provider)
        llm_config.set_llm_stage(llm, "Report Writer")

        llm.call(MESSAGES)

        assert waits == [] and provider.rebuilt == 0
        assert "[llm] Report Writer: empty answer on attempt 1/5; asking again" in capsys.readouterr().err

    def test_an_empty_answer_that_was_cut_is_a_cut(self, attempts):
        """A thinking model can spend its whole output limit reasoning. That is the more exact name."""
        provider = _StandIn([("length", ""), ("stop", "never asked for")])
        llm = _wrap_with_retry(provider)

        with pytest.raises(AnswerCutError):
            llm.call(MESSAGES)

        assert provider.asked == 1 and by_call(attempts) == {1: ["cut"]}

    def test_empty_answers_and_broken_connections_share_the_five_attempts(self, attempts):
        timed_out = TimeoutError("Request timed out.")
        provider = _StandIn([("stop", ""), (None, timed_out), ("stop", ""), (None, timed_out), ("stop", ""),
                             ("stop", "never asked for")])
        llm = _wrap_with_retry(provider)

        with pytest.raises(EmptyAnswerError, match="3 times"):
            llm.call(MESSAGES)

        assert provider.asked == 5
        assert by_call(attempts) == {1: ["empty", "timeout", "empty", "timeout", "empty"]}

    def test_the_fifth_attempt_is_the_last_even_when_it_is_the_first_empty_one(self, attempts):
        timed_out = TimeoutError("Request timed out.")
        provider = _StandIn([(None, timed_out)] * 4 + [("stop", ""), ("stop", "never asked for")])
        llm = _wrap_with_retry(provider)

        with pytest.raises(EmptyAnswerError, match="with no text, once; there was"):
            llm.call(MESSAGES)

        assert provider.asked == 5

    def test_a_plain_call_returns_an_empty_answer_as_it_always_did(self, attempts):
        """The paper extractor reads `raw or "{}"` and reports the invalid result its own way."""
        provider = _StandIn([("stop", ""), ("stop", "never asked for")], stream=False)
        llm = _wrap_with_retry(provider)

        assert llm.call(MESSAGES) == ""
        assert provider.asked == 1 and by_call(attempts) == {1: ["returned"]}

    def test_text_after_an_empty_answer_leaves_the_node_usable(self, attempts):
        provider = _StandIn([("stop", ""), ("stop", "a draft"), ("stop", ""), ("stop", ""), ("stop", "a second draft")])
        llm = _wrap_with_retry(provider)

        assert llm.call(MESSAGES) == "a draft"
        # A guardrail's second call gets its own three asks.
        assert llm.call(MESSAGES) == "a second draft"
        assert by_call(attempts) == {1: ["empty", "returned"], 2: ["empty", "empty", "returned"]}


class TestWhatTheRunSays:

    def _raw(self, stage="Technology Commercialization Report Writer") -> str:
        from academic_agent.pipeline_worker import _error_text
        return _error_text(EmptyAnswerError(stage, 3))

    def test_each_reader_is_told_the_model_wrote_nothing(self):
        from api import runs
        for funded_by, phrase in ((None, "use another model"), ("deployment", "use another model"),
                                  ("own_keys", "under API keys")):
            code, sentence = runs._public_failure(self._raw(), funded_by=funded_by)
            assert code == "provider_empty_answer", funded_by
            assert "returned no text" in sentence and phrase in sentence, funded_by

    def test_crewai_s_own_sentence_for_it_is_read_the_same_way(self):
        """What a run made before this change recorded, and what any path without the wrapper still does."""
        from api import runs
        assert runs._public_failure("Invalid response from LLM call - None or empty.")[0] == "provider_empty_answer"

    def test_no_other_category_claims_it_first(self):
        from api import runs
        for raw in (self._raw(stage="Guardrail timeout checker"),
                    self._raw(stage="invalid json rate limit validated sources"),
                    "Task failed guardrail validation: " + self._raw()):
            assert runs._public_failure(raw)[0] == "provider_empty_answer", raw

    def test_another_failure_that_mentions_missing_text_is_not_this_one(self):
        from api import runs
        for raw in ("ValueError: the uploaded page had no text to extract",
                    "The reviewer returned an answer with no corrections"):
            assert runs._public_failure(raw)[0] == "unknown", raw

    def test_a_cut_answer_is_still_read_first(self):
        from api import runs
        cut = str(AnswerCutError("Report Writer", "length"))
        assert runs._public_failure(cut + " " + self._raw())[0] == "provider_output_limit"

    def test_nobody_is_told_their_request_was_not_the_cause(self):
        """An empty answer can be the model's response to what it was asked. The operator-side
        wording says nothing in the request caused the failure, and that is not known here."""
        from api import runs
        assert "provider_empty_answer" not in runs.OPERATOR_FAILURE_CODES

    def test_the_wording_s_count_is_the_wrapper_s(self):
        from api import runs
        category = next(c for c in runs._PUBLIC_FAILURE_CATEGORIES if c.code == "provider_empty_answer")
        assert llm_config._EMPTY_ANSWER_ASKS == 3
        assert "three times" in category.message and "three times" in category.own_keys

    def test_the_step_field_documents_the_outcome(self):
        from api import models
        assert "empty" in models.StepEvent.model_fields["outcome"].description
