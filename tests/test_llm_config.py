"""Tests for LLM provider auto-detection and LLM object construction."""
from unittest.mock import MagicMock, patch

import pytest

from academic_agent.llm_config import _detect_provider, create_deepseek_llm, create_llm


# ---------------------------------------------------------------------------
# _detect_provider — auto-detection from environment variables
# ---------------------------------------------------------------------------

def test_detect_deepseek_explicit():
    with patch.dict("os.environ", {"LLM_PROVIDER": "deepseek"}, clear=False):
        assert _detect_provider() == "deepseek"


def test_detect_anthropic_explicit():
    with patch.dict("os.environ", {"LLM_PROVIDER": "anthropic"}, clear=False):
        assert _detect_provider() == "anthropic"


def test_detect_openai_explicit():
    with patch.dict("os.environ", {"LLM_PROVIDER": "openai"}, clear=False):
        assert _detect_provider() == "openai"


def test_detect_deepseek_from_api_key():
    env = {"DEEPSEEK_API_KEY": "sk-fake", "ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}
    with patch.dict("os.environ", env, clear=False):
        assert _detect_provider() == "deepseek"


def test_detect_anthropic_from_api_key():
    env = {"DEEPSEEK_API_KEY": "", "ANTHROPIC_API_KEY": "sk-ant-fake", "OPENAI_API_KEY": ""}
    with patch.dict("os.environ", env, clear=False):
        assert _detect_provider() == "anthropic"


def test_detect_openai_from_api_key():
    env = {
        "DEEPSEEK_API_KEY": "", "ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": "sk-fake",
        "OPENAI_API_BASE": "", "OPENAI_MODEL_NAME": "",
    }
    with patch.dict("os.environ", env, clear=False):
        assert _detect_provider() == "openai"


def test_detect_deepseek_priority_over_openai():
    """DEEPSEEK_API_KEY takes priority even when OPENAI_API_KEY is also set."""
    env = {"DEEPSEEK_API_KEY": "sk-ds", "OPENAI_API_KEY": "sk-oai"}
    with patch.dict("os.environ", env, clear=False):
        assert _detect_provider() == "deepseek"


# ---------------------------------------------------------------------------
# Legacy setup: OPENAI_* variables pointing at DeepSeek endpoint
# ---------------------------------------------------------------------------

def test_detect_legacy_deepseek_via_base_url():
    """Old .env using OPENAI_API_KEY + OPENAI_API_BASE=api.deepseek.com → deepseek."""
    env = {
        "DEEPSEEK_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "OPENAI_API_KEY": "sk-legacy-deepseek",
        "OPENAI_API_BASE": "https://api.deepseek.com",
        "OPENAI_MODEL_NAME": "",
    }
    with patch.dict("os.environ", env, clear=False):
        assert _detect_provider() == "deepseek"


def test_detect_legacy_deepseek_via_model_name():
    """Old .env using OPENAI_MODEL_NAME=deepseek-chat → deepseek."""
    env = {
        "DEEPSEEK_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "OPENAI_API_KEY": "sk-legacy-deepseek",
        "OPENAI_API_BASE": "",
        "OPENAI_MODEL_NAME": "deepseek-chat",
    }
    with patch.dict("os.environ", env, clear=False):
        assert _detect_provider() == "deepseek"


def test_detect_real_openai_not_confused_with_deepseek():
    """Genuine OPENAI_API_KEY with no DeepSeek hints → openai."""
    env = {
        "DEEPSEEK_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "OPENAI_API_KEY": "sk-openai-real",
        "OPENAI_API_BASE": "",
        "OPENAI_MODEL_NAME": "",
    }
    with patch.dict("os.environ", env, clear=False):
        assert _detect_provider() == "openai"


def test_detect_raises_when_no_key_set():
    env = {"DEEPSEEK_API_KEY": "", "ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": "", "LLM_PROVIDER": ""}
    with patch.dict("os.environ", env, clear=False):
        with pytest.raises(RuntimeError, match="No LLM API key"):
            _detect_provider()


def test_detect_raises_on_unknown_explicit_provider():
    with patch.dict("os.environ", {"LLM_PROVIDER": "llama"}, clear=False):
        with pytest.raises(RuntimeError, match="Unknown LLM_PROVIDER"):
            # _detect_provider returns "llama"; create_llm raises on it
            from academic_agent.llm_config import create_llm as _create
            _create()


# ---------------------------------------------------------------------------
# create_llm — LLM object construction
# ---------------------------------------------------------------------------

def _make_llm(env: dict, **kwargs):
    """Helper: patch env + LLM constructor, call create_llm, return mock call kwargs."""
    with patch.dict("os.environ", env, clear=False):
        with patch("academic_agent.llm_config.LLM") as mock_llm:
            mock_llm.return_value = MagicMock()
            create_llm(**kwargs)
            assert mock_llm.called
            return mock_llm.call_args.kwargs


def test_deepseek_default_model():
    env = {"DEEPSEEK_API_KEY": "sk-ds", "DEEPSEEK_MODEL": "", "OPENAI_MODEL_NAME": ""}
    kw = _make_llm(env)
    assert kw["model"] == "deepseek-chat"
    assert kw["provider"] == "deepseek"


def test_deepseek_custom_model():
    env = {"DEEPSEEK_API_KEY": "sk-ds", "DEEPSEEK_MODEL": "deepseek-reasoner"}
    kw = _make_llm(env)
    assert kw["model"] == "deepseek-reasoner"


def test_deepseek_strips_prefix():
    env = {"DEEPSEEK_API_KEY": "sk-ds", "DEEPSEEK_MODEL": "deepseek/deepseek-chat"}
    kw = _make_llm(env)
    assert kw["model"] == "deepseek-chat"


def test_deepseek_json_mode_sets_response_format():
    env = {"DEEPSEEK_API_KEY": "sk-ds"}
    kw = _make_llm(env, json_mode=True)
    assert kw.get("response_format") == {"type": "json_object"}


def test_deepseek_no_json_mode_skips_response_format():
    env = {"DEEPSEEK_API_KEY": "sk-ds"}
    kw = _make_llm(env, json_mode=False)
    assert "response_format" not in kw


def test_openai_default_model():
    env = {
        "DEEPSEEK_API_KEY": "", "ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": "sk-oai",
        "OPENAI_MODEL": "", "OPENAI_API_BASE": "", "OPENAI_MODEL_NAME": "",
    }
    kw = _make_llm(env)
    assert kw["model"] == "gpt-4o"
    assert kw["provider"] == "openai"


def test_openai_json_mode_sets_response_format():
    env = {
        "DEEPSEEK_API_KEY": "", "ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": "sk-oai",
        "OPENAI_API_BASE": "", "OPENAI_MODEL_NAME": "",
    }
    kw = _make_llm(env, json_mode=True)
    assert kw.get("response_format") == {"type": "json_object"}


def test_anthropic_default_model():
    env = {"DEEPSEEK_API_KEY": "", "ANTHROPIC_API_KEY": "sk-ant", "ANTHROPIC_MODEL": ""}
    kw = _make_llm(env)
    assert kw["model"] == "claude-sonnet-5"
    assert kw["provider"] == "anthropic"


def test_anthropic_json_mode_does_not_set_response_format():
    """Anthropic does not support response_format; guardrail handles JSON validation."""
    env = {"DEEPSEEK_API_KEY": "", "ANTHROPIC_API_KEY": "sk-ant"}
    kw = _make_llm(env, json_mode=True)
    assert "response_format" not in kw


def test_temperature_is_passed_when_set():
    env = {"DEEPSEEK_API_KEY": "sk-ds"}
    kw = _make_llm(env, temperature=0.0)
    assert kw["temperature"] == 0.0


def test_temperature_omitted_when_none():
    env = {"DEEPSEEK_API_KEY": "sk-ds"}
    kw = _make_llm(env, temperature=None)
    assert "temperature" not in kw


# ---------------------------------------------------------------------------
# create_deepseek_llm — backward-compatible alias
# ---------------------------------------------------------------------------

def test_backward_compat_alias():
    """create_deepseek_llm delegates to create_llm unchanged."""
    env = {"DEEPSEEK_API_KEY": "sk-ds"}
    with patch.dict("os.environ", env, clear=False):
        with patch("academic_agent.llm_config.LLM") as mock_llm:
            mock_llm.return_value = MagicMock()
            create_deepseek_llm(json_mode=True, temperature=0.0)
            assert mock_llm.called
            kw = mock_llm.call_args.kwargs
            assert kw["provider"] == "deepseek"
            assert kw.get("response_format") == {"type": "json_object"}
            assert kw["temperature"] == 0.0
