"""Tests for LLM provider auto-detection and LLM object construction."""
from unittest.mock import MagicMock, patch

import pytest

from academic_agent.llm_config import (
    _detect_provider,
    _wrap_kimi_usage,
    create_deepseek_llm,
    create_llm,
)


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


# ---------------------------------------------------------------------------
# Kimi K3 — logical provider over CrewAI's OpenAI-compatible transport
# ---------------------------------------------------------------------------

def test_detect_kimi_explicit():
    with patch.dict("os.environ", {"LLM_PROVIDER": "kimi"}, clear=False):
        assert _detect_provider() == "kimi"


def test_detect_kimi_from_official_api_key():
    env = {
        "DEEPSEEK_API_KEY": "",
        "MOONSHOT_API_KEY": "sk-kimi",
        "ANTHROPIC_API_KEY": "",
        "OPENAI_API_KEY": "",
    }
    with patch.dict("os.environ", env, clear=False):
        assert _detect_provider() == "kimi"


def test_detect_kimi_before_anthropic_and_openai():
    """Stale fallback keys must not steal an explicitly configured Kimi deployment."""

    env = {
        "MOONSHOT_API_KEY": "sk-kimi",
        "ANTHROPIC_API_KEY": "sk-ant",
        "OPENAI_API_KEY": "sk-openai",
    }
    with patch.dict("os.environ", env, clear=False):
        assert _detect_provider() == "kimi"


@pytest.mark.parametrize(
    ("base", "model"),
    [
        ("https://api.moonshot.ai/v1", ""),
        ("", "kimi-k3"),
    ],
)
def test_detect_legacy_kimi_from_openai_compatible_settings(base, model):
    env = {
        "DEEPSEEK_API_KEY": "",
        "MOONSHOT_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "OPENAI_API_KEY": "sk-legacy",
        "OPENAI_API_BASE": base,
        "OPENAI_MODEL_NAME": model,
    }
    with patch.dict("os.environ", env, clear=False):
        assert _detect_provider() == "kimi"


def test_kimi_default_contract_uses_official_endpoint_and_low_reasoning():
    kw = _make_llm({"MOONSHOT_API_KEY": "sk-kimi"})
    assert kw["provider"] == "openai"
    assert kw["model"] == "kimi-k3"
    assert kw["api_key"] == "sk-kimi"
    assert kw["base_url"] == "https://api.moonshot.ai/v1"
    assert kw["additional_params"] == {"reasoning_effort": "low"}


def test_kimi_custom_contract_is_explicit_and_json_capable():
    env = {
        "MOONSHOT_API_KEY": "sk-kimi",
        "KIMI_MODEL": "kimi-k3",
        "KIMI_API_BASE": "https://proxy.example/v1",
        "KIMI_REASONING_EFFORT": "high",
    }
    kw = _make_llm(env, json_mode=True)
    assert kw["model"] == "kimi-k3"
    assert kw["base_url"] == "https://proxy.example/v1"
    assert kw["additional_params"] == {"reasoning_effort": "high"}
    assert kw["response_format"] == {"type": "json_object"}


def test_kimi_rejects_unknown_reasoning_before_client_construction():
    env = {
        "LLM_PROVIDER": "kimi",
        "MOONSHOT_API_KEY": "sk-kimi",
        "KIMI_REASONING_EFFORT": "turbo",
    }
    with patch.dict("os.environ", env, clear=False):
        with patch("academic_agent.llm_config.LLM") as mock_llm:
            with pytest.raises(RuntimeError, match="KIMI_REASONING_EFFORT"):
                create_llm()
            mock_llm.assert_not_called()


def test_kimi_omits_temperature_instead_of_forwarding_zero():
    kw = _make_llm({"MOONSHOT_API_KEY": "sk-kimi"}, temperature=0.0)
    assert "temperature" not in kw


def test_kimi_byok_ignores_operator_endpoint_model_and_reasoning():
    env = {
        "KIMI_API_BASE": "https://operator.invalid/v1",
        "KIMI_MODEL": "operator-model",
        "KIMI_REASONING_EFFORT": "max",
    }
    with patch.dict("os.environ", env, clear=False):
        with patch("academic_agent.llm_config.LLM") as mock_llm:
            mock_llm.return_value = MagicMock()
            create_llm(provider="kimi", api_key="guest-kimi", temperature=0.0)
            kw = mock_llm.call_args.kwargs
    assert kw["provider"] == "openai"
    assert kw["api_key"] == "guest-kimi"
    assert kw["model"] == "kimi-k3"
    assert kw["base_url"] == "https://api.moonshot.ai/v1"
    assert kw["additional_params"] == {"reasoning_effort": "low"}
    assert "temperature" not in kw
    assert "operator" not in str(kw)


def test_kimi_top_level_cached_tokens_reach_crewai_metrics():
    class _Usage:
        cached_tokens = 40

    class _Response:
        usage = _Usage()

    class _LLM:
        @staticmethod
        def _extract_openai_token_usage(_response):
            return {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
            }

    llm = _wrap_kimi_usage(_LLM())
    metrics = llm._extract_openai_token_usage(_Response())
    assert metrics["cached_prompt_tokens"] == 40


def test_kimi_missing_cached_tokens_keeps_conservative_metrics():
    class _Usage:
        pass

    class _Response:
        usage = _Usage()

    class _LLM:
        @staticmethod
        def _extract_openai_token_usage(_response):
            return {"prompt_tokens": 100, "total_tokens": 100}

    llm = _wrap_kimi_usage(_LLM())
    metrics = llm._extract_openai_token_usage(_Response())
    assert "cached_prompt_tokens" not in metrics
