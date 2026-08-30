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


# ---------------------------------------------------------------------------
# Qwen3.5 Plus — logical provider over CrewAI's OpenAI-compatible transport
# ---------------------------------------------------------------------------

def test_detect_qwen_explicit():
    with patch.dict("os.environ", {"LLM_PROVIDER": "qwen"}, clear=False):
        assert _detect_provider() == "qwen"


def test_detect_qwen_from_official_api_key():
    env = {
        "DEEPSEEK_API_KEY": "",
        "DASHSCOPE_API_KEY": "sk-qwen",
        "ANTHROPIC_API_KEY": "",
        "OPENAI_API_KEY": "",
    }
    with patch.dict("os.environ", env, clear=False):
        assert _detect_provider() == "qwen"


def test_detect_qwen_before_anthropic_and_openai():
    """Stale fallback keys must not steal an explicitly configured Qwen deployment."""

    env = {
        "DASHSCOPE_API_KEY": "sk-qwen",
        "ANTHROPIC_API_KEY": "sk-ant",
        "OPENAI_API_KEY": "sk-openai",
    }
    with patch.dict("os.environ", env, clear=False):
        assert _detect_provider() == "qwen"


@pytest.mark.parametrize(
    ("base", "model"),
    [
        ("https://dashscope.aliyuncs.com/compatible-mode/v1", ""),
        ("https://dashscope-intl.aliyuncs.com/compatible-mode/v1", ""),
        ("https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1", ""),
        ("", "qwen3.5-plus"),
    ],
)
def test_detect_legacy_qwen_from_openai_compatible_settings(base, model):
    env = {
        "DEEPSEEK_API_KEY": "",
        "DASHSCOPE_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "OPENAI_API_KEY": "sk-legacy",
        "OPENAI_API_BASE": base,
        "OPENAI_MODEL_NAME": model,
    }
    with patch.dict("os.environ", env, clear=False):
        assert _detect_provider() == "qwen"


def test_qwen_default_contract_uses_official_endpoint_and_non_thinking_mode():
    kw = _make_llm(
        {
            "DASHSCOPE_API_KEY": "sk-qwen",
            "QWEN_MODEL": "",
            "QWEN_API_BASE": "",
        }
    )
    assert kw["provider"] == "openai"
    assert kw["model"] == "qwen3.5-plus"
    assert kw["api_key"] == "sk-qwen"
    assert kw["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert kw["additional_params"] == {
        "extra_body": {"enable_thinking": False}
    }


def test_qwen_custom_endpoint_and_model_keep_the_json_contract():
    env = {
        "DASHSCOPE_API_KEY": "sk-qwen",
        "QWEN_MODEL": "qwen3.5-plus-2026-02-15",
        "QWEN_API_BASE": (
            "https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
        ),
    }
    kw = _make_llm(env, json_mode=True, temperature=0.0)
    assert kw["model"] == "qwen3.5-plus-2026-02-15"
    assert kw["base_url"].startswith("https://workspace.cn-beijing.maas.aliyuncs.com")
    assert kw["additional_params"] == {
        "extra_body": {"enable_thinking": False}
    }
    assert kw["response_format"] == {"type": "json_object"}
    assert kw["temperature"] == 0.0


def test_qwen_byok_ignores_operator_endpoint_and_model():
    env = {
        "QWEN_API_BASE": "https://operator.invalid/v1",
        "QWEN_MODEL": "operator-model",
    }
    with patch.dict("os.environ", env, clear=False):
        with patch("academic_agent.llm_config.LLM") as mock_llm:
            mock_llm.return_value = MagicMock()
            create_llm(
                provider="qwen",
                api_key="guest-qwen",
                json_mode=True,
                temperature=0.0,
            )
            kw = mock_llm.call_args.kwargs
    assert kw["provider"] == "openai"
    assert kw["api_key"] == "guest-qwen"
    assert kw["model"] == "qwen3.5-plus"
    assert kw["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert kw["additional_params"] == {
        "extra_body": {"enable_thinking": False}
    }
    assert kw["response_format"] == {"type": "json_object"}
    assert kw["temperature"] == 0.0
    assert "operator" not in str(kw)


def test_qwen_extension_reaches_the_real_crewai_chat_request_body():
    """Pin the config-to-SDK seam, not merely our constructor dictionary.

    CrewAI expands additional_params into OpenAI SDK arguments. Putting
    enable_thinking directly at that level would make the SDK reject the paid
    request; Alibaba requires it under extra_body.
    """

    llm = create_llm(
        provider="qwen",
        api_key="not-a-real-key",
        json_mode=True,
        temperature=0.0,
    )
    params = llm._prepare_completion_params(
        [{"role": "user", "content": "offline request-body probe"}]
    )
    assert params["extra_body"] == {"enable_thinking": False}
    assert "enable_thinking" not in params
    assert params["response_format"] == {"type": "json_object"}
    assert params["temperature"] == 0.0
