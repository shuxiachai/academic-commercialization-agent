"""The model preflight passes a model every path can use and fails one that a path refuses."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_llm_model.py"
_spec = importlib.util.spec_from_file_location("check_llm_model", SCRIPT)
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


class _LLM:
    def __init__(self, reply):
        self._reply = reply

    def call(self, messages):
        if isinstance(self._reply, Exception):
            raise self._reply
        return self._reply


PLAN = ("SEARCH_TOPIC: perovskite solar cells for building-integrated photovoltaics\n"
        "ALIAS: building-integrated perovskite solar cells\n"
        "ALIAS: perovskite photovoltaics for building integration")


def helper(plan_reply=PLAN):
    """The language helper answering each stage as a working model would."""
    return lambda prompt, *, stage="language_helper", **k: {
        "search_planning": plan_reply, "translation": "perovskite solar cells"}.get(stage, "")


@pytest.fixture
def qwen(monkeypatch):
    for name, value in {"LLM_PROVIDER": "qwen", "QWEN_MODEL": "qwen3.7-max-preview",
                        "DASHSCOPE_API_KEY": "sk-test"}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr("academic_agent.language._llm_call", helper())
    # The developer's own .env must not reach the check under test.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)


@pytest.fixture
def agents_work(monkeypatch):
    monkeypatch.setattr("academic_agent.llm_config.create_llm",
                        lambda json_mode=False, **k: _LLM('{"ok": true}' if json_mode else "ok"))


def test_a_model_every_path_can_use_passes(qwen, agents_work, capsys):
    assert check.main([]) == 0
    out = capsys.readouterr().out
    assert "PASS  search planner (real prompt)" in out and "+ 2 alias(es)" in out
    assert "PASS  language helper, translation" in out
    assert "OK: the pipeline can use this model." in out


@pytest.mark.parametrize("plan_reply", [
    "",       # the call failed: the planner searched the typed topic, as production did on 2026-10-23
    "ready",  # the old 20-token ping's answer, which passed the check while production fell back
], ids=["failed-call", "not-a-plan"])
def test_a_planner_that_falls_back_to_the_typed_topic_fails(qwen, agents_work, monkeypatch, capsys, plan_reply):
    monkeypatch.setattr("academic_agent.language._llm_call", helper(plan_reply))
    assert check.main([]) == 1
    out = capsys.readouterr().out
    assert "FAIL  search planner (real prompt)" in out and "drops every alias query" in out
    assert "1 path(s) failed." in out


def test_a_refused_agent_path_fails_and_says_what_to_check(qwen, monkeypatch, capsys):
    refused = RuntimeError("Error code: 404 - {'error': {'code': 'model_not_found', 'message': 'The model "
                           "does not exist or you do not have access to it.'}}")
    monkeypatch.setattr("academic_agent.llm_config.create_llm", lambda **k: _LLM(refused))
    assert check.main([]) == 1
    out = capsys.readouterr().out
    assert "FAIL  agent LLM, JSON mode" in out and "not available to this deployment's key" in out
