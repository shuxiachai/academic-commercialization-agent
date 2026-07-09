"""LLM provider configuration — supports DeepSeek, OpenAI, and Anthropic.

Provider resolution order:
  1. LLM_PROVIDER env var (explicit: "deepseek" | "openai" | "anthropic")
  2. First matching API key found:
       DEEPSEEK_API_KEY  → deepseek
       ANTHROPIC_API_KEY → anthropic
       OPENAI_API_KEY    → openai
"""

import os

from crewai import LLM

# Providers that support response_format={"type": "json_object"}.
# Anthropic does not — it relies on prompt instructions + guardrail validation.
_JSON_MODE_PROVIDERS = {"deepseek", "openai"}


def _detect_provider() -> str:
    explicit = os.getenv("LLM_PROVIDER", "").lower().strip()
    if explicit:
        return explicit
    if os.getenv("DEEPSEEK_API_KEY"):
        return "deepseek"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        # Legacy setup: OPENAI_API_KEY pointing at DeepSeek via OPENAI_API_BASE
        base = os.getenv("OPENAI_API_BASE", "")
        model = os.getenv("OPENAI_MODEL_NAME", "")
        if "deepseek" in base.lower() or "deepseek" in model.lower():
            return "deepseek"
        return "openai"
    raise RuntimeError(
        "No LLM API key found. Set one of:\n"
        "  DEEPSEEK_API_KEY   → DeepSeek  (default model: deepseek-chat)\n"
        "  ANTHROPIC_API_KEY  → Anthropic (default model: claude-sonnet-5)\n"
        "  OPENAI_API_KEY     → OpenAI    (default model: gpt-4o)\n"
        "Or set LLM_PROVIDER explicitly to override auto-detection."
    )


def create_llm(*, json_mode: bool = False, temperature: float | None = None) -> LLM:
    """Create an LLM instance for the active provider.

    Provider is auto-detected from environment variables, or set explicitly
    via LLM_PROVIDER. json_mode enables structured JSON output where supported;
    Anthropic falls back to prompt-based JSON + guardrail validation.
    """
    provider = _detect_provider()
    kwargs: dict = {}

    if provider == "deepseek":
        kwargs["provider"] = "deepseek"
        kwargs["model"] = (
            os.getenv("DEEPSEEK_MODEL")
            or os.getenv("OPENAI_MODEL_NAME")
            or "deepseek-chat"
        )
        if kwargs["model"].startswith("deepseek/"):
            kwargs["model"] = kwargs["model"].split("/", 1)[1]
        kwargs["api_key"] = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
        kwargs["base_url"] = (
            os.getenv("DEEPSEEK_API_BASE")
            or os.getenv("OPENAI_API_BASE")
            or "https://api.deepseek.com"
        )

    elif provider == "openai":
        kwargs["provider"] = "openai"
        kwargs["model"] = os.getenv("OPENAI_MODEL", "gpt-4o")
        kwargs["api_key"] = os.getenv("OPENAI_API_KEY")
        base = os.getenv("OPENAI_API_BASE")
        if base:
            kwargs["base_url"] = base

    elif provider == "anthropic":
        kwargs["provider"] = "anthropic"
        kwargs["model"] = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
        kwargs["api_key"] = os.getenv("ANTHROPIC_API_KEY")

    else:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER: {provider!r}. "
            "Supported values: deepseek, openai, anthropic."
        )

    if json_mode and provider in _JSON_MODE_PROVIDERS:
        kwargs["response_format"] = {"type": "json_object"}

    if temperature is not None:
        kwargs["temperature"] = temperature

    return LLM(**kwargs)


# Backward-compatible alias — existing code that imports create_deepseek_llm keeps working
def create_deepseek_llm(
    *, json_mode: bool = False, temperature: float | None = None
) -> LLM:
    return create_llm(json_mode=json_mode, temperature=temperature)
