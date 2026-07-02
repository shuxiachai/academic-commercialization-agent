"""DeepSeek LLM configuration for JSON and free-form task outputs."""

import os

from crewai import LLM


def create_deepseek_llm(*, json_mode: bool = False) -> LLM:
    """Create a native DeepSeek provider with optional JSON Object mode."""

    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Set DEEPSEEK_API_KEY (preferred) or OPENAI_API_KEY before running."
        )

    model = (
        os.getenv("DEEPSEEK_MODEL")
        or os.getenv("OPENAI_MODEL_NAME")
        or "deepseek-chat"
    )
    if model.startswith("deepseek/"):
        model = model.split("/", maxsplit=1)[1]

    base_url = (
        os.getenv("DEEPSEEK_API_BASE")
        or os.getenv("OPENAI_API_BASE")
        or "https://api.deepseek.com"
    )
    response_format = {"type": "json_object"} if json_mode else None

    return LLM(
        model=model,
        provider="deepseek",
        api_key=api_key,
        base_url=base_url,
        response_format=response_format,
    )
