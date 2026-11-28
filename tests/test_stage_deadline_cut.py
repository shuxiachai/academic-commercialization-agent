"""A model call already under way is cut at its stage's deadline.

Production, 2026-11-25 22:39 UTC, run 078e0d09 on qwen3.8-2.4t-a95b, a model
that cannot turn thinking off. The review began with 846 s left of 1,800, 606
before the reviewer's deadline, so the budget let it begin. Its one attempt
was still streaming 853 s later, and the watchdog killed the run at 30:07: the
validated draft, the evidence and the scorer's window went with one call.
``_CallBudget.require_window`` decides whether an attempt may begin. Nothing
ended one that had begun, except sixty silent seconds (120 on such a model),
and a model that is thinking is not silent: every reasoning chunk resets that
bound. The reviewer's fallback (deliver the validated draft, then score) and
the 60-second closeout reserve were both there, and neither was reached.

Held here:

- A streamed attempt is cut at the first chunk that arrives after its node's
  deadline, reasoning chunks included, and its response is closed so the
  provider stops. The cut is the budget's own ``RunDeadlineExceeded``: never
  retried, the node not asked again.
- A review cut there takes the existing path: the draft unchanged, marked as
  not reviewed, then the scorer, which still has its whole window. On a model
  that cannot turn thinking off the scorer's window is 300 s, so the
  reviewer's deadline moves back by the 150 s that window grew; on any other
  model it is where it was.
- What the cut does not touch: an answer that ends before the deadline, a run
  with no watchdog (the CLI), and a plain request, whose whole wait is already
  bounded by a window that has to fit before the deadline.
- A writer or scorer cut there fails the run as ``run_time_limit``, which now
  says a step can be stopped as well as not begun.

The provider objects are the real ones (CrewAI 1.14.7, the OpenAI SDK, httpx),
built with a made-up key. Each request is answered here at the transport, so
httpx's own hooks run, and nothing is sent. The clock is llm_config's, moved by
the answers instead of waited for.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from crewai import Agent, Crew, Task

from academic_agent import llm_config, pipeline_worker
from academic_agent import llm_parameter_fallback as parameter_fallback
from academic_agent.llm_config import (
    RunDeadlineExceeded,
    configure_llm_deadline,
    create_llm,
    set_attempt_observer,
    set_llm_stage,
)
from academic_agent.runtime_budget import (
    FINALIZATION_RESERVE_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    REVIEWER_RESERVE_SECONDS,
    RuntimeBudget,
)
from api import runs

ROOT = Path(__file__).resolve().parents[1]
RUN_JS = (ROOT / "web" / "static" / "js" / "run.js").read_text(encoding="utf-8")

MODEL = "qwen3.8-2.4t-a95b"
ROLES = ["Academic Evidence Analyst", "Patent Evidence Analyst", "Market Evidence Analyst",
         "Report Writer", "Quality Reviewer", "Commercialization Readiness Scorer"]
WRITER, REVIEWER, SCORER = ROLES[3], ROLES[4], ROLES[5]
DRAFT = "The validated draft of the report."
SCORECARD = "The scorecard."
#: Seconds between two reasoning chunks of the review that never ends.
STEP = 5.0
#: Scoring times read on production 2026-11-28: the median on the production
#: model, and the one recorded for another model (qwen3.7-max-2026-06-08).
SCORING_THINKING, SCORING_OTHER = 218.0, 168.0
MESSAGES = [{"role": "user", "content": "Review the report."}]


class WatchdogKill(BaseException):
    """The API's watchdog: past the hard limit the worker process is killed."""


class Clock:
    """llm_config's clock. The answers below move it; no real second is waited."""

    def __init__(self) -> None:
        self.now = 10_000.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _sse(payload: object) -> bytes:
    data = payload if isinstance(payload, str) else json.dumps(payload)
    return f"data: {data}\n\n".encode()


def _chunk(delta: dict, finish: str | None = None) -> dict:
    return {"id": "chatcmpl-1", "object": "chat.completion.chunk", "created": 1, "model": MODEL,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


class Answer(httpx.SyncByteStream):
    """A streamed answer that ends by itself, `seconds` after it was asked for."""

    def __init__(self, clock: Clock, text: str, seconds: float, *, chunks: int = 1) -> None:
        self.clock, self.text, self.seconds, self.chunks = clock, text, seconds, chunks
        self.closed = False

    def __iter__(self):
        for _ in range(self.chunks - 1):
            self.clock.now += self.seconds / self.chunks
            yield _sse(_chunk({"reasoning_content": "Weighing the evidence. "}))
        self.clock.now += self.seconds / self.chunks
        yield _sse(_chunk({"role": "assistant", "content": self.text}))
        yield _sse(_chunk({}, "stop"))
        yield _sse({**_chunk({}), "choices": [],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140}})
        yield _sse("[DONE]")

    def close(self) -> None:
        self.closed = True


class EndlessThinking(httpx.SyncByteStream):
    """A model reasoning without end: one chunk every STEP seconds, until the watchdog.

    `signal` replaces the reasoning chunks with other bytes that carry no
    answer, such as a keep-alive comment or a ping event.
    """

    def __init__(self, clock: Clock, killed_at: float, signal: bytes | None = None) -> None:
        self.clock, self.killed_at, self.signal = clock, killed_at, signal
        self.chunks = 0
        self.closed_at: float | None = None

    def __iter__(self):
        if self.signal is None:
            yield _sse(_chunk({"role": "assistant", "content": None}))
        while True:
            self.clock.now += STEP
            if self.clock.now >= self.killed_at:
                raise WatchdogKill(f"killed by the watchdog at {self.clock.now:.0f}")
            self.chunks += 1
            yield self.signal or _sse(_chunk({"reasoning_content": "Checking the claims once more. "}))

    def close(self) -> None:
        if self.closed_at is None:
            self.closed_at = self.clock.now


class Provider:
    """Answers each node's request at the transport; `plan` says how, by role."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.killed_at = float("inf")
        self.plan: dict[str, object] = {}
        self.requests: list[tuple[str, float]] = []
        self.streams: dict[str, list[object]] = {}

    def role_of(self, body: dict) -> str:
        first = str((body.get("messages") or [{}])[0].get("content") or "")
        for role in ROLES:
            if f"You are {role}." in first:
                return role
        return "caller"

    def handle(self, transport, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        role = self.role_of(body)
        self.requests.append((role, self.clock.now))
        plan = self.plan.get(role, self.plan.get("*"))
        answer = plan(body) if callable(plan) else plan
        if isinstance(answer, BaseException):
            raise answer
        self.streams.setdefault(role, []).append(answer)
        if not body.get("stream"):
            text = b"".join(answer)
            return httpx.Response(200, headers={"content-type": "application/json"},
                                  stream=httpx.ByteStream(text), request=request)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=answer,
                              request=request)

    def sent(self, role: str) -> int:
        return sum(1 for name, _ in self.requests if name == role)


@pytest.fixture
def clock(monkeypatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(llm_config, "time", SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep))
    return clock


@pytest.fixture
def provider(monkeypatch, clock) -> Provider:
    provider = Provider(clock)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request",
                        lambda transport, request: provider.handle(transport, request))
    for name, value in (("CREWAI_DISABLE_TELEMETRY", "true"), ("OTEL_SDK_DISABLED", "true"),
                        ("CREWAI_TRACING_ENABLED", "false")):
        monkeypatch.setenv(name, value)
    parameter_fallback.reset()
    yield provider
    parameter_fallback.reset()


@pytest.fixture
def attempts():
    records: list[dict] = []
    previous = set_attempt_observer(records.append)
    yield records
    set_attempt_observer(previous)


def built(*, stream: bool = True):
    return create_llm(provider="qwen", api_key="made-up-key-never-sent", model=MODEL, stream=stream)


def thinking_only(llm) -> None:
    """What the worker learns on its first call of a model that refuses non-thinking mode."""
    parameter_fallback.learn(llm.base_url.rstrip("/"), llm.model, "enable_thinking", True)


# ── The run: a review that never returns ─────────────────────────────────────


def _crew() -> Crew:
    agents = [Agent(role=role, goal="Do the step.", backstory="Does the step.", llm=built(),
                    verbose=False, allow_delegation=False) for role in ROLES]
    evidence = [Task(description=f"Assess the {role.split()[0].lower()} evidence.",
                     expected_output="Findings.", agent=agent) for role, agent in zip(ROLES[:3], agents[:3], strict=True)]
    writer = Task(description="Write the report.", expected_output="A report.", agent=agents[3],
                  context=evidence)
    review = Task(description="Review the report.", expected_output="A reviewed report.",
                  agent=agents[4], context=[writer])
    scoring = Task(description="Score the evidence.", expected_output="A scorecard.", agent=agents[5],
                   context=evidence)
    return Crew(agents=agents, tasks=[*evidence, writer, review, scoring], verbose=False)


@pytest.mark.parametrize("thinking,hard_seconds,left_at_review,reviewer_reserve,scoring", [
    # 2026-11-25 as it would run now: 40 minutes, the review begins with 1,446 s left.
    (True, 2400, 1446.0, REVIEWER_RESERVE_SECONDS + REQUEST_TIMEOUT_SECONDS, SCORING_THINKING),
    # Any other model: 30 minutes, the reviewer's deadline where it always was.
    (False, 1800, 846.0, REVIEWER_RESERVE_SECONDS, SCORING_OTHER),
], ids=["thinking-only model, 40 min", "other model, 30 min"])
def test_a_review_that_never_returns_is_cut_at_its_deadline_and_the_scorer_still_runs(
        provider, clock, attempts, thinking, hard_seconds, left_at_review, reviewer_reserve, scoring):
    crew = _crew()
    if thinking:
        thinking_only(crew.agents[0].llm)
    hard = clock.now + hard_seconds
    budget = RuntimeBudget(hard_deadline_monotonic=hard, hard_deadline_epoch=1.0e9 + hard_seconds,
                           hard_timeout_seconds=hard_seconds)
    review_starts = hard - left_at_review
    review = EndlessThinking(clock, killed_at=hard)
    provider.killed_at = hard
    provider.plan = {
        "*": lambda body: Answer(clock, "Findings.", 60.0),
        WRITER: lambda body: Answer(clock, DRAFT, review_starts - clock.now),
        REVIEWER: review,
        SCORER: lambda body: Answer(clock, SCORECARD, scoring, chunks=20),
    }

    pipeline_worker._configure_node_deadlines(crew.agents, budget)
    try:
        crew.kickoff()
    except WatchdogKill as killed:
        pytest.fail(f"the review was not cut; the run was {killed}, {clock.now - review_starts:.0f} s into it")
    except RunDeadlineExceeded as cut:
        error = cut
    else:
        pytest.fail("the endless review returned")

    deadline = hard - reviewer_reserve
    assert review.closed_at is not None, "the review's response must be closed so the provider stops"
    assert deadline <= review.closed_at < deadline + STEP
    assert provider.sent(REVIEWER) == 1, "a cut attempt is not sent again"
    reviewer_rows = [row for row in attempts if row["stage"] == REVIEWER]
    assert [(row["outcome"], row["error_type"], row["retry"]) for row in reviewer_rows] == [
        ("timeout", "RunDeadlineExceeded", False)]

    # The worker's own path from here: the draft unchanged, then the scorer.
    recovered = pipeline_worker._recover_from_reviewer_failure(crew, error)
    assert recovered is not None
    outputs, quality = recovered
    assert (quality["status"], quality["failure_type"]) == ("fallback", "RunDeadlineExceeded")
    assert outputs[4].raw == DRAFT
    assert outputs[5].raw == SCORECARD
    scorer_sent = [at for role, at in provider.requests if role == SCORER]
    assert len(scorer_sent) == 1 and scorer_sent[0] >= review.closed_at
    # The scorer began with its whole window before the closeout reserve, and
    # the run ends with that reserve still in hand: the worker writes its own end.
    window = REQUEST_TIMEOUT_SECONDS * (2 if thinking else 1)
    assert hard - FINALIZATION_RESERVE_SECONDS - scorer_sent[0] >= window
    assert clock.now < hard - FINALIZATION_RESERVE_SECONDS


# ── One node, one call ────────────────────────────────────────────────────────


def _reviewer(provider: Provider, clock: Clock, *, left: float = 600.0, stream: bool = True):
    llm = built(stream=stream)
    configure_llm_deadline(llm, deadline_monotonic=clock.now + left, stage=REVIEWER,
                           request_timeout_seconds=REQUEST_TIMEOUT_SECONDS)
    return llm, clock.now + left


def test_a_cut_is_the_budgets_own_failure_and_the_node_is_not_asked_again(provider, clock, attempts):
    llm, deadline = _reviewer(provider, clock)
    endless = EndlessThinking(clock, killed_at=deadline + 3600)
    provider.plan = {"caller": endless}

    with pytest.raises(RunDeadlineExceeded) as cut:
        llm.call(MESSAGES)
    with pytest.raises(RunDeadlineExceeded) as again:
        llm.call(MESSAGES)

    assert again.value is cut.value
    assert provider.sent("caller") == 1
    assert deadline <= endless.closed_at < deadline + STEP
    assert len(attempts) == 1
    assert pipeline_worker._error_text(cut.value) == (
        f"{REVIEWER}: the attempt in progress was cut at the stage's deadline; "
        "a bounded provider attempt requires its answer before that deadline")


@pytest.mark.parametrize("name,model,signal", [
    ("qwen", MODEL, None),
    ("deepseek", "deepseek-chat", b": keep-alive\n\n"),
    ("anthropic", "claude-sonnet-5-5", b'event: ping\ndata: {"type": "ping"}\n\n'),
], ids=["qwen reasoning chunks", "deepseek keep-alive comments", "anthropic pings"])
def test_bytes_that_carry_no_answer_still_meet_the_deadline(provider, clock, attempts, name, model, signal):
    """Every chunk counts, whatever it carries. CrewAI's reader drops reasoning
    chunks without an event, and the SDKs drop SSE comments and pings before
    CrewAI sees anything; a connection kept alive that way never trips the
    per-chunk bound either."""
    llm = create_llm(provider=name, api_key="made-up-key-never-sent", model=model, stream=True)
    deadline = clock.now + 600.0
    configure_llm_deadline(llm, deadline_monotonic=deadline, stage=REVIEWER,
                           request_timeout_seconds=REQUEST_TIMEOUT_SECONDS)
    endless = EndlessThinking(clock, killed_at=deadline + 3600, signal=signal)
    provider.plan = {"caller": endless}

    with pytest.raises(RunDeadlineExceeded):
        llm.call(MESSAGES)

    assert provider.sent("caller") == 1
    assert deadline <= endless.closed_at < deadline + STEP
    assert [(row["outcome"], row["error_type"]) for row in attempts] == [("timeout", "RunDeadlineExceeded")]


def test_a_cut_is_not_read_as_a_rate_limit_whatever_the_topic(provider, clock, attempts):
    """The scorer's role carries the topic, and the cut's sentence carries the
    role. A topic about rate limits must not make a cut look like a 429 that
    passes by waiting, which a streamed node asks again for."""
    llm, deadline = _reviewer(provider, clock)
    set_llm_stage(llm, "Commercialization Readiness Scorer for API rate limit gateways (HTTP 429)")
    provider.plan = {"caller": lambda body: EndlessThinking(clock, killed_at=deadline + 3600)}

    with pytest.raises(RunDeadlineExceeded):
        llm.call(MESSAGES)

    assert provider.sent("caller") == 1
    assert [(row["outcome"], row["retry"]) for row in attempts] == [("timeout", False)]


def test_an_answer_that_ends_before_the_deadline_comes_back_as_before(provider, clock, attempts):
    llm, deadline = _reviewer(provider, clock)
    provider.plan = {"caller": lambda body: Answer(clock, DRAFT, 500.0, chunks=50)}

    assert llm.call(MESSAGES) == DRAFT
    assert clock.now < deadline
    assert [row["outcome"] for row in attempts] == ["returned"]


def test_a_run_with_no_watchdog_is_never_cut(provider, clock, attempts):
    """The CLI configures no deadline; a long answer there is the reader's to wait for."""
    llm = built()
    set_llm_stage(llm, REVIEWER)
    provider.plan = {"caller": lambda body: Answer(clock, DRAFT, 7200.0, chunks=500)}

    assert llm.call(MESSAGES) == DRAFT
    assert [row["outcome"] for row in attempts] == ["returned"]


def test_a_plain_request_is_not_cut(provider, clock, attempts):
    """Its whole wait is bounded by its window, which had to fit before the
    deadline for it to be sent; an answer whose body lands after the deadline
    was generated and billed already, and is kept."""
    llm, deadline = _reviewer(provider, clock, left=200.0, stream=False)
    body = {"id": "chatcmpl-1", "object": "chat.completion", "created": 1, "model": MODEL,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": DRAFT}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}

    def late():
        clock.now = deadline + 30.0
        yield json.dumps(body).encode()

    provider.plan = {"caller": lambda request_body: late()}

    try:
        answer = llm.call(MESSAGES)
    except RunDeadlineExceeded as cut:
        pytest.fail(f"a plain request was cut: {cut}")
    assert answer == DRAFT


def test_the_cut_holds_on_the_new_connection_a_retry_opens(provider, clock, attempts):
    """A transport retry rebuilds the SDK client, and with it the HTTP client
    the cut is installed on (llm_config._reconnect)."""
    llm, deadline = _reviewer(provider, clock)
    endless = EndlessThinking(clock, killed_at=deadline + 3600)
    queue = [httpx.ConnectError("Connection reset by peer"), endless]
    provider.plan = {"caller": lambda body: queue.pop(0)}
    first_pool = llm._client._client

    try:
        with pytest.raises(RunDeadlineExceeded):
            llm.call(MESSAGES)
    except WatchdogKill as killed:
        pytest.fail(f"the cut did not hold on the rebuilt connection; the attempt was {killed}")

    assert llm._client._client is not first_pool
    assert provider.sent("caller") == 2
    assert deadline <= endless.closed_at < deadline + STEP
    assert [row["outcome"] for row in attempts] == ["error", "timeout"]


def test_the_cut_is_installed_once_per_http_client(provider, clock):
    llm, _ = _reviewer(provider, clock)
    provider.plan = {"caller": lambda body: Answer(clock, DRAFT, 1.0)}

    for _ in range(3):
        llm.call(MESSAGES)

    assert len(llm._client._client.event_hooks["response"]) == 1


# ── Where the reviewer's deadline is ──────────────────────────────────────────


def test_only_the_reviewer_leaves_the_scorer_a_window():
    budget = RuntimeBudget(hard_deadline_monotonic=5000.0, hard_deadline_epoch=1.0e9, hard_timeout_seconds=1800)
    assert [budget.successor_window_for_agent(index) for index in range(6)] == [0, 0, 0, 0, 150, 0]


def test_on_any_other_model_the_reviewers_deadline_is_unchanged(provider, clock):
    llm, _ = _reviewer(provider, clock)
    budget = RuntimeBudget(hard_deadline_monotonic=clock.now + 1800, hard_deadline_epoch=1.0e9,
                           hard_timeout_seconds=1800)
    configure_llm_deadline(llm, deadline_monotonic=budget.deadline_for_agent(4), stage=REVIEWER,
                           request_timeout_seconds=budget.request_timeout_for_agent(4),
                           successor_window_seconds=budget.successor_window_for_agent(4))
    provider.plan = {"caller": lambda body: Answer(clock, DRAFT, 1.0)}

    llm.call(MESSAGES)

    state = llm._academic_agent_call_budget
    assert state.deadline_monotonic == budget.hard_deadline_monotonic - REVIEWER_RESERVE_SECONDS
    assert state.request_timeout_seconds == REQUEST_TIMEOUT_SECONDS


def test_on_a_thinking_only_model_it_moves_back_by_the_scorers_extra_window_once(provider, clock):
    """The 240-s reserve leaves the closeout's 60 s, the scorer's 150 and 30 to
    hand over. Thinking doubles the scorer's window to 300, and the same 30 s
    are kept: 390 s. Every other node's deadline stays put."""
    budget = RuntimeBudget(hard_deadline_monotonic=clock.now + 2400, hard_deadline_epoch=1.0e9,
                           hard_timeout_seconds=2400)
    reviewer, scorer = built(), built()
    thinking_only(reviewer)
    for index, llm in ((4, reviewer), (5, scorer)):
        configure_llm_deadline(llm, deadline_monotonic=budget.deadline_for_agent(index), stage=ROLES[index],
                               request_timeout_seconds=budget.request_timeout_for_agent(index),
                               successor_window_seconds=budget.successor_window_for_agent(index))
    provider.plan = {"*": lambda body: Answer(clock, DRAFT, 1.0)}

    for _ in range(2):
        reviewer.call(MESSAGES)
    scorer.call(MESSAGES)

    hard = budget.hard_deadline_monotonic
    assert reviewer._academic_agent_call_budget.deadline_monotonic == hard - 390
    assert reviewer._academic_agent_call_budget.request_timeout_seconds == 300
    assert scorer._academic_agent_call_budget.deadline_monotonic == hard - FINALIZATION_RESERVE_SECONDS
    assert scorer._academic_agent_call_budget.request_timeout_seconds == 300


def test_the_worker_hands_the_reviewer_the_scorers_window():
    """The rule is worth nothing unless the worker's configuration carries it."""
    budget = RuntimeBudget(hard_deadline_monotonic=5000.0, hard_deadline_epoch=1.0e9, hard_timeout_seconds=1800)
    llms = [built() for _ in ROLES]
    agents = [SimpleNamespace(role=role, llm=llm) for role, llm in zip(ROLES, llms, strict=True)]

    pipeline_worker._configure_node_deadlines(agents, budget)

    states = [llm._academic_agent_call_budget for llm in llms]
    assert [state.successor_window_seconds for state in states] == [0, 0, 0, 0, 150, 0]
    assert [state.deadline_monotonic for state in states] == [4940.0] * 4 + [4760.0, 4940.0]


# ── What the page says when a writer or scorer is cut ─────────────────────────


def test_a_cut_writer_or_scorer_reads_as_the_time_limit_and_says_the_step_was_stopped(provider, clock):
    llm, deadline = _reviewer(provider, clock)
    set_llm_stage(llm, SCORER)
    provider.plan = {"caller": EndlessThinking(clock, killed_at=deadline + 3600)}
    with pytest.raises(RunDeadlineExceeded) as cut:
        llm.call(MESSAGES)

    for funded_by in (None, "deployment", "own_keys"):
        code, sentence = runs._public_failure(pipeline_worker._error_text(cut.value), funded_by=funded_by)
        assert code == "run_time_limit"
        assert "stopped" in sentence and "not begun" in sentence
    match = re.search(r'run_time_limit: "([^"]+)"', RUN_JS)
    assert match and "停下" in match.group(1) and "没有开始" in match.group(1)
