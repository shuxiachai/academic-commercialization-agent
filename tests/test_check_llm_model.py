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


@pytest.fixture
def qwen(monkeypatch):
    for name, value in {"LLM_PROVIDER": "qwen", "QWEN_MODEL": "qwen3.7-max-preview",
                        "DASHSCOPE_API_KEY": "sk-test"}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr("academic_agent.language._llm_call", lambda *a, **k: "ready")
    # The developer's own .env must not reach the check under test.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)


def test_a_model_every_path_can_use_passes(qwen, monkeypatch, capsys):
    monkeypatch.setattr("academic_agent.llm_config.create_llm",
                        lambda json_mode=False, **k: _LLM('{"ok": true}' if json_mode else "ok"))
    assert check.main([]) == 0
    assert "OK: the pipeline can use this model." in capsys.readouterr().out


def test_a_refused_agent_path_fails_and_says_what_to_check(qwen, monkeypatch, capsys):
    refused = RuntimeError("Error code: 404 - {'error': {'code': 'model_not_found', 'message': 'The model "
                           "does not exist or you do not have access to it.'}}")
    monkeypatch.setattr("academic_agent.llm_config.create_llm", lambda **k: _LLM(refused))
    assert check.main([]) == 1
    out = capsys.readouterr().out
    assert "FAIL  agent LLM, JSON mode" in out and "not available to this deployment's key" in out
