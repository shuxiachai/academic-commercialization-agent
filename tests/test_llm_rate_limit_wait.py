"""A node waits out a rate limit instead of failing on it.

A rate limit is the one refusal that passes by itself, and until 2026-11-12
it was the one the wrapper did nothing about: _is_retryable sent a 429
straight back, and the only second chance it got was CrewAI running the node
again at once, twice, with no wait (#388 left that in place for this reason).

What the rules rest on. No model call in the runs saved on the maintainer's
machine was ever refused with a rate limit, so none could be looked at, and
provoking one with someone's key is not a test. The rules are from the
providers' own pages, read 2026-11-12:

- Anthropic sends `retry-after`, the seconds to wait.
- Model Studio names no such header. Its 429s are of two kinds. One passes:
  requests or tokens per minute, a burst, concurrency, overload
  (Throttling, Throttling.RateQuota, Throttling.AllocationQuota,
  Throttling.BurstRate, Throttling.Concurrency, ...), for which it says to
  retry later, "a few minutes" at most. The other does not pass by waiting:
  the free quota of a model used up ("Free allocated quota exceeded."), a
  budget exhausted, a bill overdue, a product not bought.

So a streamed node that is rate-limited waits what the provider said, or 15,
30, 60 and 60 seconds before its second to fifth attempts when it said
nothing, inside the five attempts and the run's time it already had. A 429
that waiting cannot cure fails at once, as before. A plain call does not
wait: the paper extractor runs inside a web request.

The provider objects are the real ones, built with made-up keys. Each HTTP
request is counted and answered here; nothing is sent, and no wait is slept.
"""

from __future__ import annotations

import json

import httpx
import pytest
from crewai import Agent, Crew, Task

from academic_agent import llm_config
from academic_agent.llm_config import RunDeadlineExceeded, _wrap_with_retry, create_llm, set_attempt_observer
from tests.test_llm_cut_answer import _anthropic

MESSAGES = [{"role": "user", "content": "Write the report."}]
ANSWER = "The report."
#: Model Studio's wording for a limit on requests per minute, and for a model's free quota used up.
PER_MINUTE = {"error": {"code": "Throttling.RateQuota", "type": "Throttling.RateQuota",
                        "message": "Requests rate limit exceeded, please try again later."}}
FREE_QUOTA_GONE = {"error": {"code": "Throttling.AllocationQuota", "type": "Throttling.AllocationQuota",
                             "message": "Free allocated quota exceeded."}}
BILL_OVERDUE = {"error": {"code": "PostpaidBillOverdue", "message": "The postpaid bill is overdue."}}
BUDGET_SPENT = {"error": {"code": "BudgetLimitExceeded",
                          "message": "The budget configured in Budget Management has been exhausted."}}
#: Anthropic's 429 body. Its `retry-after` header says how many seconds to wait.
ANTHROPIC_LIMIT = {"type": "error", "error": {"type": "rate_limit_error",
                                              "message": "This request would exceed your rate limit."}}


def _stream(body: dict) -> bytes:
    def chunk(delta, reason, **more):
        return {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": body["model"],
                "choices": [{"index": 0, "delta": delta, "finish_reason": reason}], **more}

    usage = {"prompt_tokens": 100, "completion_tokens": 3, "total_tokens": 103}
    events = [chunk({"role": "assistant", "content": ANSWER}, None), chunk({}, "stop"),
              {**chunk({}, None), "choices": [], "usage": usage}]
    return ("".join("data: " + json.dumps(event) + "\n\n" for event in events) + "data: [DONE]\n\n").encode()


@pytest.fixture
def provider(monkeypatch):
    """Answers each request with the next of `provider.answers` (the last repeats) and records the waits."""
    class Answering:
        answers: list = ["ok"]
        requests = 0
        waits: list[float] = []

    Answering.waits = []

    def answer(client, request, **_):
        kind = Answering.answers[min(Answering.requests, len(Answering.answers) - 1)]
        Answering.requests += 1
        if kind == "ok" and "anthropic" in request.url.host:
            return _anthropic(json.loads(request.content), "end_turn", request)
        if kind == "ok":
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  content=_stream(json.loads(request.content)), request=request)
        refusal, headers = kind if isinstance(kind, tuple) else (kind, {})
        return httpx.Response(429, json=refusal, headers=headers, request=request)

    monkeypatch.setattr(httpx.Client, "send", answer)
    monkeypatch.setattr(llm_config.time, "sleep", Answering.waits.append)
    monkeypatch.setattr(llm_config.random, "uniform", lambda low, high: 0.0)
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


def run_one_node(provider_name="qwen", model="deepseek-v4.1-flash-1017"):
    llm = create_llm(provider=provider_name, api_key="made-up-key-never-sent", model=model, stream=True)
    agent = Agent(role="Report writer", goal="Write the report.", backstory="Writes reports.", llm=llm, verbose=False)
    task = Task(description="Write the report.", expected_output="A report.", agent=agent)
    return Crew(agents=[agent], tasks=[task], verbose=False).kickoff()


class TestThroughCrewAI:

    def test_a_limit_that_passes_is_waited_out_and_the_run_completes(self, provider, attempts):
        provider.answers = [PER_MINUTE, PER_MINUTE, "ok"]

        assert ANSWER in str(run_one_node())

        assert provider.requests == 3
        # One call, as the wrapper's own retries are; not CrewAI starting the node over.
        assert by_call(attempts) == {1: ["rate_limited", "rate_limited", "returned"]}
        assert provider.waits == [15.0, 30.0]

    def test_the_provider_s_own_wait_is_the_one_used(self, provider, attempts):
        provider.answers = [(PER_MINUTE, {"retry-after": "7"}), "ok"]

        assert ANSWER in str(run_one_node())

        assert provider.waits == [7.0]

    def test_anthropic_s_stated_wait_reaches_the_wrapper_through_its_own_provider(self, provider, attempts):
        provider.answers = [(ANTHROPIC_LIMIT, {"retry-after": "9"}), "ok"]

        assert "A report" in str(run_one_node("anthropic", "claude-sonnet-5-5"))

        assert provider.requests == 2
        assert by_call(attempts) == {1: ["rate_limited", "returned"]}
        assert provider.waits == [9.0]

    def test_a_limit_that_never_lifts_ends_the_node_after_its_five_attempts(self, provider, attempts):
        provider.answers = [PER_MINUTE]

        with pytest.raises(Exception, match="Requests rate limit exceeded"):
            run_one_node()

        # Five attempts and the four waits between them, and CrewAI does not start the node over.
        assert provider.requests == 5
        assert by_call(attempts) == {1: ["rate_limited"] * 5}
        assert provider.waits == [15.0, 30.0, 60.0, 60.0]

    @pytest.mark.parametrize("refusal", [FREE_QUOTA_GONE, BILL_OVERDUE, BUDGET_SPENT],
                             ids=["free-quota", "bill", "budget"])
    def test_a_429_that_waiting_cannot_cure_fails_at_once(self, provider, attempts, refusal):
        provider.answers = [refusal]

        with pytest.raises(Exception, match=refusal["error"]["message"][:20]):
            run_one_node()

        assert provider.requests == 1
        assert provider.waits == []
        assert by_call(attempts) == {1: ["error"]}


class _Refused(Exception):
    """What an SDK raises for a 429: a message, and the response with its headers."""

    def __init__(self, message="Error code: 429 - Requests rate limit exceeded, please try again later.", **headers):
        super().__init__(message)
        self.response = type("Response", (), {"headers": headers})()


class _StandIn:
    def __init__(self, steps, stream=True):
        self.base_url, self.model = "https://provider.example/v1", "some-model"
        self.stream, self.timeout, self.temperature, self.max_tokens = stream, 60.0, None, None
        self.steps, self.asked, self.rebuilt = list(steps), 0, 0

    def _build_sync_client(self):
        self.rebuilt += 1
        return object()

    def call(self, messages):
        self.asked += 1
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step


class TestTheWrapperItself:

    @pytest.fixture(autouse=True)
    def waits(self, monkeypatch):
        slept: list[float] = []
        monkeypatch.setattr(llm_config.time, "sleep", slept.append)
        monkeypatch.setattr(llm_config.random, "uniform", lambda low, high: 0.0)
        return slept

    @pytest.mark.parametrize("stated,waited", [
        ("7", 7.0), ("0.5", 0.5), ("60", 60.0),
        ("600", 60.0),                               # longer than this run will wait for one attempt
        ("0", 15.0), ("-3", 15.0), ("soon", 15.0), ("", 15.0),
        ("Wed, 12 Nov 2026 09:00:00 GMT", 15.0),     # the header's other form is not read
        ("nan", 15.0), ("inf", 15.0),
    ])
    def test_the_wait_is_what_the_provider_said_when_it_said_a_usable_number(self, waits, stated, waited):
        llm = _wrap_with_retry(_StandIn([_Refused(**{"retry-after": stated}), "the answer"]))

        assert llm.call(MESSAGES) == "the answer"
        assert waits == [waited]

    def test_the_wait_grows_and_stops_growing_at_a_minute(self, waits):
        llm = _wrap_with_retry(_StandIn([_Refused(), _Refused(), _Refused(), _Refused(), "the answer"]))

        assert llm.call(MESSAGES) == "the answer"
        assert waits == [15.0, 30.0, 60.0, 60.0]

    def test_waits_are_spread_so_parallel_nodes_do_not_return_together(self, monkeypatch, waits):
        monkeypatch.setattr(llm_config.random, "uniform", lambda low, high: high)
        llm = _wrap_with_retry(_StandIn([_Refused(), _Refused(**{"retry-after": "8"}), "the answer"]))

        assert llm.call(MESSAGES) == "the answer"
        # Up to a quarter more, on the provider's figure as on ours: never less than it asked.
        assert waits == [15.0 * 1.25, 8.0 * 1.25]

    def test_a_rate_limit_is_recognised_by_status_by_words_or_by_class(self, waits, attempts):
        for refusal in (RuntimeError("Error code: 429 - Too many requests."),
                        RuntimeError("The rate limit for requests per minute was reached."),
                        type("RateLimitError", (Exception,), {})("Too many requests.")):
            llm = _wrap_with_retry(_StandIn([refusal, "the answer"]))
            assert llm.call(MESSAGES) == "the answer"
        assert waits == [15.0, 15.0, 15.0]
        assert by_call(attempts) == {1: ["rate_limited", "returned"] * 3}

    @pytest.mark.parametrize("message", [
        "Error code: 429 - {'code': 'Throttling.AllocationQuota', 'message': 'Free allocated quota exceeded.'}",
        "Error code: 429 - {'code': 'AllocationQuota.FreeTierOnly', 'message': 'This model is no longer free.'}",
        "Error code: 429 - {'code': 'BudgetLimitExceeded', 'message': 'The budget configured in Budget Management "
        "has been exhausted.'}",
        "Error code: 429 - {'code': 'PrepaidBillOverdue', 'message': 'The prepaid bill is overdue.'}",
        "Error code: 429 - {'code': 'Arrearage', 'message': 'Access denied, please make sure your account is in "
        "good standing.'}",
        "Error code: 429 - {'code': 'CommodityNotPurchased', 'message': 'Commodity has not purchased yet.'}",
    ])
    def test_what_waiting_cannot_cure_is_not_waited_for(self, waits, attempts, message):
        provider = _StandIn([RuntimeError(message), "never asked for"])
        llm = _wrap_with_retry(provider)

        with pytest.raises(RuntimeError):
            llm.call(MESSAGES)

        assert waits == [] and provider.asked == 1
        assert [(row["outcome"], row["retry"]) for row in attempts] == [("error", False)]

    def test_a_token_rate_limit_in_openai_s_words_is_waited_for(self, waits):
        """Model Studio words its tokens-per-minute limit the way OpenAI words an empty account.
        The two cannot be told apart here, and a wait that proves useless costs time and no money."""
        refusal = RuntimeError("Error code: 429 - {'code': 'insufficient_quota', 'message': 'You exceeded your "
                               "current quota, please check your plan and billing details.'}")
        llm = _wrap_with_retry(_StandIn([refusal, "the answer"]))

        assert llm.call(MESSAGES) == "the answer"
        assert waits == [15.0]

    def test_a_plain_call_does_not_wait(self, waits, attempts):
        """The paper extractor runs inside a web request; a minute's wait there is the visitor's."""
        provider = _StandIn([_Refused(), "never asked for"], stream=False)
        llm = _wrap_with_retry(provider)

        with pytest.raises(_Refused):
            llm.call(MESSAGES)

        assert waits == [] and provider.asked == 1
        assert [(row["outcome"], row["retry"]) for row in attempts] == [("rate_limited", False)]

    def test_each_refused_attempt_is_recorded_as_rate_limited(self, attempts):
        llm = _wrap_with_retry(_StandIn([_Refused(), "the answer"]))

        llm.call(MESSAGES)

        assert [(row["attempt"], row["outcome"], row["retry"], row["error_type"]) for row in attempts] == [
            (1, "rate_limited", True, "_Refused"), (2, "returned", False, None)]

    def test_the_notice_says_how_long_and_no_new_connection_is_opened(self, capsys):
        provider = _StandIn([_Refused(**{"retry-after": "7"}), "the answer"])
        llm = _wrap_with_retry(provider)
        llm_config.set_llm_stage(llm, "Report Writer")

        llm.call(MESSAGES)

        assert "[llm] Report Writer: rate limited on attempt 1/5; asking again in 7.0s" in capsys.readouterr().err
        # A rate limit says nothing against the connection it arrived on.
        assert provider.rebuilt == 0

    def test_a_connection_failure_is_still_retried_on_its_own_schedule(self, waits, capsys):
        provider = _StandIn([TimeoutError("Request timed out."), TimeoutError("Request timed out."), "the answer"])
        llm = _wrap_with_retry(provider)

        assert llm.call(MESSAGES) == "the answer"
        assert waits == [2.0, 4.0]
        assert provider.rebuilt == 2
        assert "on a new connection" in capsys.readouterr().err

    def test_a_run_without_time_for_the_wait_stops_with_the_rate_limit_as_its_cause(self, waits, attempts):
        provider = _StandIn([_Refused(), "never asked for"])
        llm = _wrap_with_retry(provider)
        # Room for one more attempt, and not for fifteen seconds before it.
        llm_config.configure_llm_deadline(
            llm, deadline_monotonic=llm_config.time.monotonic() + 70.0, stage="Report Writer",
            request_timeout_seconds=60.0)

        with pytest.raises(RunDeadlineExceeded) as raised:
            llm.call(MESSAGES)

        assert isinstance(raised.value.__cause__, _Refused)
        assert waits == [] and provider.asked == 1
        assert [(row["outcome"], row["retry"]) for row in attempts] == [("rate_limited", False)]

    def test_a_limit_that_outlasts_the_attempts_is_given_up_on_like_any_other_failure(self, attempts):
        provider = _StandIn([_Refused() for _ in range(5)] + ["never asked for"])
        llm = _wrap_with_retry(provider)
        with pytest.raises(_Refused) as first:
            llm.call(MESSAGES)

        with pytest.raises(_Refused) as second:
            llm.call(MESSAGES)

        assert second.value is first.value and provider.asked == 5


def test_the_step_field_documents_the_outcome():
    from api import models
    assert "rate_limited" in models.StepEvent.model_fields["outcome"].description
