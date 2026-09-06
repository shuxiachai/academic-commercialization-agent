"""Readiness and operator construction must agree without contacting a provider."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient
import pytest

from api import main, runs
from academic_agent import llm_config


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(runs, "DAILY_CAP", 0)
    monkeypatch.setenv("SERPER_API_KEY", "offline-search")
    # Do not start the application's retention/reaper lifespan in a seam test.
    instance = TestClient(main.app)
    yield instance
    instance.close()


@pytest.mark.parametrize("provider", ["qwen", "deepseek", "openai", "anthropic", "unknown"])
def test_explicit_provider_without_usable_key_is_not_ready(client, monkeypatch, provider):
    """An explicit selector used to bypass missing-key and unknown-provider checks."""
    monkeypatch.setenv("LLM_PROVIDER", provider)
    constructor = MagicMock(side_effect=AssertionError("Readiness must never construct an SDK"))
    monkeypatch.setattr(llm_config, "LLM", constructor)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["ready"] is False
    assert response.json()["checks"]["llm"] != "ok"
    with pytest.raises(RuntimeError):
        llm_config.create_llm()
    constructor.assert_not_called()
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("provider,key_name", [
    ("qwen", "DASHSCOPE_API_KEY"), ("qwen", "OPENAI_API_KEY"),
    ("deepseek", "DEEPSEEK_API_KEY"), ("deepseek", "OPENAI_API_KEY"),
    ("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY"),
])
def test_readiness_preserves_the_actual_transport_key_alias(client, monkeypatch, provider, key_name):
    """Reject missing credentials without breaking the legacy OPENAI_* setup."""
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv(key_name, "offline-credential-do-not-return")
    constructor = MagicMock()
    monkeypatch.setattr(llm_config, "LLM", constructor)
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["llm_provider"] == provider
    assert "offline-credential" not in response.text
    constructor.assert_not_called()
    llm_config.create_llm()
    assert constructor.call_args.kwargs["api_key"] == "offline-credential-do-not-return"


@pytest.mark.parametrize("value", ["", " ", "\t\n"])
def test_empty_selected_key_cannot_be_rescued_by_unrelated_provider(client, monkeypatch, value):
    """A leftover Anthropic key does not make an explicitly selected Qwen usable."""
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("DASHSCOPE_API_KEY", value)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "unrelated-offline-key")
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert "unrelated-offline-key" not in response.text
