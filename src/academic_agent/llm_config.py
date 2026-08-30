"""LLM provider configuration for DeepSeek, Qwen, OpenAI, and Anthropic.

Provider resolution order:
  1. LLM_PROVIDER env var (explicit provider selection)
  2. First matching API key found:
       DEEPSEEK_API_KEY  -> deepseek
       DASHSCOPE_API_KEY -> qwen
       ANTHROPIC_API_KEY -> anthropic
       OPENAI_API_KEY    -> endpoint/model-aware legacy detection, then openai
"""

import functools
import os
import random
import time

from crewai import LLM

_SUPPORTED_PROVIDERS = ("deepseek", "qwen", "openai", "anthropic")

# Qwen3.5 Plus is exposed through Alibaba Model Studio's OpenAI-compatible
# chat endpoint, but remains a logical provider here. That distinction lets
# the API use the official DASHSCOPE_API_KEY name, pin a safe BYOK endpoint,
# and apply provider-specific accounting without labelling the request OpenAI.
_QWEN_MODEL = "qwen3.5-plus"
_QWEN_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# Providers that support response_format={"type": "json_object"}.
# Anthropic does not — it relies on prompt instructions + guardrail validation.
_JSON_MODE_PROVIDERS = {"deepseek", "qwen", "openai"}


def _detect_provider() -> str:
    explicit = os.getenv("LLM_PROVIDER", "").lower().strip()
    if explicit:
        return explicit
    if os.getenv("DEEPSEEK_API_KEY"):
        return "deepseek"
    if os.getenv("DASHSCOPE_API_KEY"):
        return "qwen"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        # Older deployments expressed OpenAI-compatible providers entirely
        # through OPENAI_* variables. Preserve that path while still assigning
        # the logical provider needed for request and cost policy.
        base = os.getenv("OPENAI_API_BASE", "").lower()
        model = os.getenv("OPENAI_MODEL_NAME", "").lower()
        if "deepseek" in base or "deepseek" in model:
            return "deepseek"
        if (
            "dashscope" in base
            or ".maas.aliyuncs.com" in base
            or "qwen" in model
        ):
            return "qwen"
        return "openai"
    raise RuntimeError(
        "No LLM API key found. Set one of:\n"
        "  DEEPSEEK_API_KEY  -> DeepSeek  (default model: deepseek-chat)\n"
        "  DASHSCOPE_API_KEY -> Qwen      (default model: qwen3.5-plus)\n"
        "  ANTHROPIC_API_KEY -> Anthropic (default model: claude-sonnet-5)\n"
        "  OPENAI_API_KEY    -> OpenAI    (default model: gpt-4o)\n"
        "Or set LLM_PROVIDER explicitly to override auto-detection."
    )


def _qwen_additional_params() -> dict[str, object]:
    """Return a fresh OpenAI SDK extension body for Qwen JSON calls.

    Qwen3.5 Plus enables thinking by default. Alibaba's Chat Completions
    contract requires non-thinking mode for reliable JSON Object output, and
    ``enable_thinking`` is not an OpenAI SDK keyword. CrewAI 1.14.7 expands
    ``additional_params`` into ``chat.completions.create`` arguments, so the
    provider extension must sit under ``extra_body`` rather than at top level.
    """

    return {"extra_body": {"enable_thinking": False}}


# Retry only failures that a retry can fix.
#
# A run drives six LLM calls over roughly three minutes. Without this, one
# dropped connection discards everything before it: a real run died at 2:16
# having already retrieved and validated 24 sources across seven APIs, because
# the network changed underneath it. Source retrieval has had backoff since
# early on; the LLM calls did not, which is the asymmetry this closes.
#
# Deliberately narrow. A 4xx is not a transport problem — retrying an invalid
# key or a malformed request cannot succeed, and against a billed API it may be
# charged per attempt. Rate limits (429) are excluded too: the provider is
# asking for less traffic, and the pipeline's concurrency cap is where that
# belongs.
_RETRYABLE = (ConnectionError, TimeoutError, OSError)
_MAX_ATTEMPTS = 3
_BASE_DELAY_SECONDS = 2.0


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, _RETRYABLE):
        return True
    # CrewAI wraps provider errors in its own types, so the class is often
    # uninformative. The message is what separates a dropped socket from a
    # rejected request.
    text = f"{type(exc).__name__}: {exc}".lower()
    if any(m in text for m in ("429", "rate limit", "quota", "invalid api key",
                               "authentication", "401", "403", "400")):
        return False
    return any(m in text for m in ("connection", "timed out", "timeout",
                                   "temporarily unavailable", "reset by peer",
                                   "502", "503", "504"))


def _wrap_with_retry(llm):
    """Add retry to an LLM instance by replacing its bound `call`.

    Not a subclass: crewai.LLM defines __new__ and acts as a factory, so
    LLM(...) returns a provider class such as OpenAICompatibleCompletion —
    `isinstance(LLM(...), LLM)` is False. Subclassing it produces an object
    that bypasses the factory and lacks the provider behaviour entirely.
    Wrapping the instance the factory built leaves that behaviour intact.
    """
    inner = llm.call

    @functools.wraps(inner)
    def call_with_retry(*args, **kwargs):
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return inner(*args, **kwargs)
            except BaseException as exc:      # noqa: BLE001 - re-raised below
                if attempt == _MAX_ATTEMPTS or not _is_retryable(exc):
                    raise
                # Jitter so six agents recovering from one outage do not all
                # return at the same instant.
                delay = _BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                delay += random.uniform(0, delay * 0.25)
                print(
                    f"[llm] {type(exc).__name__} on attempt {attempt}/{_MAX_ATTEMPTS}; "
                    f"retrying in {delay:.1f}s",
                    flush=True,
                )
                time.sleep(delay)

    llm.call = call_with_retry
    return llm


def create_llm(
    *,
    json_mode: bool = False,
    temperature: float | None = None,
    provider: str | None = None,
    api_key: str | None = None,
) -> LLM:
    """Create an LLM instance for the active provider.

    Provider is auto-detected from environment variables, or set explicitly
    via LLM_PROVIDER. json_mode enables structured JSON output where supported;
    Anthropic falls back to prompt-based JSON + guardrail validation.

    `provider`/`api_key` override the environment entirely, for the one caller
    that runs inside the API process rather than in a worker subprocess: the
    paper extractor. A run gets its credentials through a scrubbed subprocess
    environment (see api/runs.py), which is not available to code executing in
    the shared server process — passing them in is what lets a visitor's
    upload be billed to the visitor. When they are given, nothing from the
    environment is read: no base URL, no model name. The operator's
    OPENAI_API_BASE pointing somewhere else is exactly the redirect the
    scrubbing exists to prevent, and it would apply here too.
    """
    kwargs: dict = {}

    if provider and api_key:
        logical_provider = provider.lower().strip()
        kwargs["provider"] = (
            "openai" if logical_provider == "qwen" else logical_provider
        )
        kwargs["api_key"] = api_key
        kwargs["model"] = {
            "deepseek": "deepseek-chat",
            "qwen": _QWEN_MODEL,
            "openai": "gpt-4o",
            "anthropic": "claude-sonnet-5",
        }.get(logical_provider, "")
        if logical_provider == "deepseek":
            kwargs["base_url"] = "https://api.deepseek.com"
        elif logical_provider == "qwen":
            kwargs["base_url"] = _QWEN_API_BASE
            kwargs["additional_params"] = _qwen_additional_params()
        if not kwargs["model"]:
            supported = ", ".join(_SUPPORTED_PROVIDERS)
            raise RuntimeError(
                f"Unknown LLM provider: {logical_provider!r}. "
                f"Supported values: {supported}."
            )
        if json_mode and logical_provider in _JSON_MODE_PROVIDERS:
            kwargs["response_format"] = {"type": "json_object"}
        if temperature is not None:
            kwargs["temperature"] = temperature
        return _wrap_with_retry(LLM(**kwargs))

    logical_provider = _detect_provider()

    if logical_provider == "deepseek":
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

    elif logical_provider == "qwen":
        kwargs["provider"] = "openai"
        kwargs["model"] = (
            os.getenv("QWEN_MODEL")
            or os.getenv("OPENAI_MODEL_NAME")
            or _QWEN_MODEL
        )
        kwargs["api_key"] = (
            os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
        )
        kwargs["base_url"] = (
            os.getenv("QWEN_API_BASE")
            or os.getenv("OPENAI_API_BASE")
            or _QWEN_API_BASE
        )
        kwargs["additional_params"] = _qwen_additional_params()

    elif logical_provider == "openai":
        kwargs["provider"] = "openai"
        kwargs["model"] = os.getenv("OPENAI_MODEL") or "gpt-4o"
        kwargs["api_key"] = os.getenv("OPENAI_API_KEY")
        base = os.getenv("OPENAI_API_BASE")
        if base:
            kwargs["base_url"] = base

    elif logical_provider == "anthropic":
        kwargs["provider"] = "anthropic"
        kwargs["model"] = os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-5"
        kwargs["api_key"] = os.getenv("ANTHROPIC_API_KEY")

    else:
        supported = ", ".join(_SUPPORTED_PROVIDERS)
        raise RuntimeError(
            f"Unknown LLM_PROVIDER: {logical_provider!r}. "
            f"Supported values: {supported}."
        )

    if json_mode and logical_provider in _JSON_MODE_PROVIDERS:
        kwargs["response_format"] = {"type": "json_object"}

    if temperature is not None:
        kwargs["temperature"] = temperature

    return _wrap_with_retry(LLM(**kwargs))


# Backward-compatible alias — existing code that imports create_deepseek_llm keeps working
def create_deepseek_llm(
    *, json_mode: bool = False, temperature: float | None = None
) -> LLM:
    return create_llm(json_mode=json_mode, temperature=temperature)
