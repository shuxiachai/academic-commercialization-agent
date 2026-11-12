"""A node's request asks the provider to write no prompt cache.

CrewAI marks the system message and the task message of every agent call as
the end of a cacheable prefix, and its Anthropic provider turns each mark into
``cache_control``. Anthropic bills a cache write at 1.25 times the input rate
and a later read at a fraction of it, so the marks pay when the same prefix is
sent again. In this pipeline it is not:

- a node is one call (no tool loop), so nothing follows the marked messages;
- the system message begins with the topic, so no two topics share a prefix;
- when a guardrail sends a node back, CrewAI replaces the task message's
  context with the failure and the previous answer, so the task message is new.

The first run through Anthropic (2026-11-12, ``claude-sonnet-5-5``) wrote
124,953 tokens to the cache across its six calls and read none back: $0.0625
of a $0.619 bill, a tenth of it, for nothing. CrewAI 1.14.7 has no setting
that turns the marks off, so a before-call hook removes them.

Nothing is sent by these tests. The provider objects are the real ones, built
with a made-up key; every HTTP request is recorded and answered here.
"""

from __future__ import annotations

import json

import httpx
import pytest
from crewai import Agent, Crew, Task
from crewai.hooks import (
    get_before_llm_call_hooks,
    register_before_llm_call_hook,
    unregister_before_llm_call_hook,
)
from crewai.hooks.llm_hooks import LLMCallHookContext
from crewai.llms.cache import mark_cache_breakpoint

from academic_agent import prompt_cache_marks
from academic_agent.crew import AcademicAgent
from academic_agent.llm_config import create_llm
from tests.test_crew_wiring import _make_collection

BACKSTORY = "A careful analyst who reads every source before writing. " * 20
TASK = "Summarise what the evidence says about the topic. " * 40


@pytest.fixture(autouse=True)
def hooks_as_found():
    """Each test starts without the hook and leaves the registry as it found it."""
    registered = prompt_cache_marks.drop_cache_marks in get_before_llm_call_hooks()
    while unregister_before_llm_call_hook(prompt_cache_marks.drop_cache_marks):
        pass
    yield
    while unregister_before_llm_call_hook(prompt_cache_marks.drop_cache_marks):
        pass
    if registered:
        register_before_llm_call_hook(prompt_cache_marks.drop_cache_marks)


@pytest.fixture
def sent(monkeypatch):
    """The JSON body of every request a provider client tries to make; none leaves."""
    bodies: list[dict] = []

    def answer(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content or b"{}"))
        refusal = {"type": "error", "error": {"type": "authentication_error", "message": "made-up key"}}
        return httpx.Response(401, json=refusal, request=request)

    async def answer_async(self, request, **_):
        return answer(request)

    monkeypatch.setattr(httpx.Client, "send", lambda self, request, **_: answer(request))
    monkeypatch.setattr(httpx.AsyncClient, "send", answer_async)
    for name, value in (("CREWAI_DISABLE_TELEMETRY", "true"), ("OTEL_SDK_DISABLED", "true"),
                        ("CREWAI_TRACING_ENABLED", "false")):
        monkeypatch.setenv(name, value)
    return bodies


@pytest.fixture
def build_the_crew(monkeypatch):
    """Builds the six-node crew the way a run does. It needs a provider to be configured."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "made-up-key-never-sent")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    return lambda: AcademicAgent(_make_collection())


def run_one_node(provider: str, model: str) -> None:
    """One agent, one task, through CrewAI's own executor, as a node of the crew runs."""
    llm = create_llm(provider=provider, api_key="made-up-key-never-sent", model=model, stream=True)
    agent = Agent(role="Analyst for a made-up topic", goal="Answer the task.", backstory=BACKSTORY,
                  llm=llm, verbose=False)
    task = Task(description=TASK, expected_output="One paragraph.", agent=agent)
    with pytest.raises(Exception, match="made-up key"):
        Crew(agents=[agent], tasks=[task], verbose=False).kickoff()


def text_of(content) -> str:
    """A message's text, whether the provider sent it as a string or as blocks."""
    if isinstance(content, str):
        return content
    return "".join(block.get("text", "") for block in content)


class TestTheRequestANodeSends:

    def test_crewai_alone_asks_anthropic_to_write_the_whole_prompt_to_its_cache(self, sent):
        """What the hook is for. If this stops holding, CrewAI changed and the hook may go."""
        run_one_node("anthropic", "claude-sonnet-5-5")

        body = sent[0]
        assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert body["messages"][-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
        # The mark on the last message covers everything before it: the whole prompt.
        assert len(body["messages"]) == 1

    def test_a_node_of_this_crew_asks_for_no_cache_write(self, sent, build_the_crew):
        run_one_node("anthropic", "claude-sonnet-5-5")
        marked = sent[0]
        sent.clear()

        build_the_crew()
        run_one_node("anthropic", "claude-sonnet-5-5")

        assert sent, "the node made no request"
        for body in sent:
            assert "cache_control" not in json.dumps(body)
        # The marks went and nothing else: the same words, the same limits.
        plain = sent[0]
        assert text_of(plain["system"]) == text_of(marked["system"])
        assert BACKSTORY.strip() in text_of(plain["system"])
        assert [text_of(m["content"]) for m in plain["messages"]] == [
            text_of(m["content"]) for m in marked["messages"]]
        assert TASK.strip() in text_of(plain["messages"][0]["content"])
        rest = {k: v for k, v in plain.items() if k not in ("system", "messages")}
        assert rest == {k: v for k, v in marked.items() if k not in ("system", "messages")}

    @pytest.mark.parametrize("provider,model", [("qwen", "qwen3.8-max"), ("deepseek", "deepseek-chat")])
    def test_the_other_providers_requests_are_what_they_were(self, sent, build_the_crew, provider, model):
        """They never sent the mark: their request is the same with the hook and without."""
        run_one_node(provider, model)
        before = sent[0]
        sent.clear()

        build_the_crew()
        run_one_node(provider, model)

        assert sent[0] == before
        assert "cache" not in json.dumps(before)


class TestTheHook:

    def test_building_the_crew_registers_it_once_however_often_the_crew_is_built(self, build_the_crew):
        assert prompt_cache_marks.drop_cache_marks not in get_before_llm_call_hooks()

        build_the_crew()
        build_the_crew()

        assert get_before_llm_call_hooks().count(prompt_cache_marks.drop_cache_marks) == 1

    def test_it_takes_the_mark_off_every_message_and_leaves_the_message(self):
        messages = [
            mark_cache_breakpoint({"role": "system", "content": "who you are"}),
            mark_cache_breakpoint({"role": "user", "content": "the task"}),
            {"role": "assistant", "content": "an answer"},
            mark_cache_breakpoint({"role": "user", "content": "a second task"}),
        ]
        same_list = messages

        allowed = prompt_cache_marks.drop_cache_marks(LLMCallHookContext(messages=messages))

        # CrewAI stops the call on False and keeps only a list changed in place.
        assert allowed is None
        assert messages is same_list
        assert messages == [
            {"role": "system", "content": "who you are"},
            {"role": "user", "content": "the task"},
            {"role": "assistant", "content": "an answer"},
            {"role": "user", "content": "a second task"},
        ]
