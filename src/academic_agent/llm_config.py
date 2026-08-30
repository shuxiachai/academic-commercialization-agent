"""LLM provider configuration for DeepSeek, Kimi, OpenAI, and Anthropic.

Provider resolution order:
  1. LLM_PROVIDER env var (explicit provider selection)
  2. First matching API key found:
       DEEPSEEK_API_KEY  -> deepseek
       MOONSHOT_API_KEY  -> kimi
       ANTHROPIC_API_KEY -> anthropic
       OPENAI_API_KEY    -> endpoint/model-aware legacy detection, then openai
"""

import functools
import os
import random
import time
from typing import Any

from crewai import LLM

_SUPPORTED_PROVIDERS = ("deepseek", "kimi", "openai", "anthropic")

# Kimi K3 exposes an OpenAI-compatible chat endpoint, but it is still a
# logically separate provider here. Keeping that distinction is what lets the
# API scrub and inject the official MOONSHOT_API_KEY name, omit unsupported
# request fields, and apply the provider's cache pricing without pretending
# that a Moonshot request was billed by OpenAI.
_KIMI_MODEL = "kimi-k3"
_KIMI_API_BASE = "https://api.moonshot.ai/v1"
_KIMI_REASONING_EFFORT = "low"
_KIMI_REASONING_EFFORTS = frozenset({"low", "high", "max"})

# Providers that support response_format={"type": "json_object"}.
# Anthropic relies on prompt instructions plus guardrail validation.
_JSON_MODE_PROVIDERS = {"deepseek", "kimi", "openai"}


def _detect_provider() -> str:
    explicit = os.getenv("LLM_PROVIDER", "").lower().strip()
    if explicit:
        return explicit
    if os.getenv("DEEPSEEK_API_KEY"):
        return "deepseek"
    if os.getenv("MOONSHOT_API_KEY"):
        return "kimi"
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
        if "moonshot" in base or "kimi" in model:
            return "kimi"
        return "openai"
    raise RuntimeError(
        "No LLM API key found. Set one of:\n"
        "  DEEPSEEK_API_KEY  -> DeepSeek  (default model: deepseek-chat)\n"
        "  MOONSHOT_API_KEY  -> Kimi      (default model: kimi-k3)\n"
        "  ANTHROPIC_API_KEY -> Anthropic (default model: claude-sonnet-5)\n"
        "  OPENAI_API_KEY    -> OpenAI    (default model: gpt-4o)\n"
        "Or set LLM_PROVIDER explicitly to override auto-detection."
    )


def _kimi_reasoning_effort() -> str:
    """Return a K3 reasoning level, failing before any provider request."""

    value = (
        os.getenv("KIMI_REASONING_EFFORT") or _KIMI_REASONING_EFFORT
    ).lower().strip()
    if value not in _KIMI_REASONING_EFFORTS:
        allowed = ", ".join(sorted(_KIMI_REASONING_EFFORTS))
        raise RuntimeError(
            f"Unknown KIMI_REASONING_EFFORT: {value!r}. "
            f"Supported values: {allowed}."
        )
    return value


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
    if any(
        marker in text
        for marker in (
            "429",
            "rate limit",
            "quota",
            "invalid api key",
            "authentication",
            "401",
            "403",
            "400",
        )
    ):
        return False
    return any(
        marker in text
        for marker in (
            "connection",
            "timed out",
            "timeout",
            "temporarily unavailable",
            "reset by peer",
            "502",
            "503",
            "504",
        )
    )


def _wrap_with_retry(llm):
    """Add retry to an LLM instance by replacing its bound call method.

    This is not a subclass: crewai.LLM defines __new__ and acts as a factory,
    so LLM(...) returns a concrete provider class. Wrapping that instance keeps
    the provider behaviour CrewAI selected.
    """

    inner = llm.call

    @functools.wraps(inner)
    def call_with_retry(*args, **kwargs):
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return inner(*args, **kwargs)
            except BaseException as exc:  # noqa: BLE001 - re-raised below
                if attempt == _MAX_ATTEMPTS or not _is_retryable(exc):
                    raise
                # Jitter so six agents recovering from one outage do not all
                # return at the same instant.
                delay = _BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                delay += random.uniform(0, delay * 0.25)
                print(
                    f"[llm] {type(exc).__name__} on attempt "
                    f"{attempt}/{_MAX_ATTEMPTS}; retrying in {delay:.1f}s",
                    flush=True,
                )
                time.sleep(delay)

    llm.call = call_with_retry
    return llm


def _wrap_kimi_usage(llm):
    """Translate Kimi's top-level cached token count into CrewAI metrics.

    CrewAI 1.14.7 reads OpenAI's nested
    prompt_tokens_details.cached_tokens field. Kimi K3 returns cached_tokens
    directly on usage. If the field is absent, leave CrewAI's conservative
    full-input accounting unchanged instead of guessing a cache discount.
    """

    inner = getattr(llm, "_extract_openai_token_usage", None)
    if not callable(inner):
        return llm

    @functools.wraps(inner)
    def extract_kimi_usage(response) -> dict[str, Any]:
        metrics = inner(response)
        usage = getattr(response, "usage", None)
        if usage is None:
            return metrics
        if isinstance(usage, dict):
            cached_tokens = usage.get("cached_tokens")
        else:
            cached_tokens = getattr(usage, "cached_tokens", None)
        if cached_tokens is not None:
            metrics["cached_prompt_tokens"] = int(cached_tokens or 0)
        return metrics

    llm._extract_openai_token_usage = extract_kimi_usage
    return llm


def _finish_llm(kwargs: dict, logical_provider: str) -> LLM:
    """Construct once, then attach provider-specific accounting and retry."""

    llm = LLM(**kwargs)
    if logical_provider == "kimi":
        llm = _wrap_kimi_usage(llm)
    return _wrap_with_retry(llm)


def create_llm(
    *,
    json_mode: bool = False,
    temperature: float | None = None,
    provider: str | None = None,
    api_key: str | None = None,
) -> LLM:
    """Create an LLM instance for the active provider.

    Provider is auto-detected from environment variables, or selected through
    LLM_PROVIDER. json_mode enables structured JSON where the provider supports
    it; Anthropic falls back to prompt JSON plus guardrail validation.

    provider/api_key override the environment entirely for inline BYOK work.
    Fixed models and official endpoints prevent an operator base URL or model
    from redirecting a visitor's key or changing what that visitor pays for.
    """

    kwargs: dict = {}

    if provider and api_key:
        logical_provider = provider.lower().strip()
        model = {
            "deepseek": "deepseek-chat",
            "kimi": _KIMI_MODEL,
            "openai": "gpt-4o",
            "anthropic": "claude-sonnet-5",
        }.get(logical_provider)
        if not model:
            supported = ", ".join(_SUPPORTED_PROVIDERS)
            raise RuntimeError(
                f"Unknown LLM provider: {logical_provider!r}. "
                f"Supported values: {supported}."
            )

        # Kimi uses an OpenAI-compatible transport inside CrewAI, while the
        # logical provider remains "kimi" for policy and accounting.
        kwargs["provider"] = (
            "openai" if logical_provider == "kimi" else logical_provider
        )
        kwargs["api_key"] = api_key
        kwargs["model"] = model
        if logical_provider == "deepseek":
            kwargs["base_url"] = "https://api.deepseek.com"
        elif logical_provider == "kimi":
            kwargs["base_url"] = _KIMI_API_BASE
            # Use additional_params deliberately. CrewAI 1.14.7 forwards its
            # first-class reasoning_effort only for OpenAI o-series models.
            kwargs["additional_params"] = {
                "reasoning_effort": _KIMI_REASONING_EFFORT
            }
        if json_mode and logical_provider in _JSON_MODE_PROVIDERS:
            kwargs["response_format"] = {"type": "json_object"}
        if temperature is not None and logical_provider != "kimi":
            kwargs["temperature"] = temperature
        return _finish_llm(kwargs, logical_provider)

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
        kwargs["api_key"] = (
            os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
        )
        kwargs["base_url"] = (
            os.getenv("DEEPSEEK_API_BASE")
            or os.getenv("OPENAI_API_BASE")
            or "https://api.deepseek.com"
        )

    elif logical_provider == "kimi":
        kwargs["provider"] = "openai"
        kwargs["model"] = (
            os.getenv("KIMI_MODEL")
            or os.getenv("OPENAI_MODEL_NAME")
            or _KIMI_MODEL
        )
        kwargs["api_key"] = (
            os.getenv("MOONSHOT_API_KEY") or os.getenv("OPENAI_API_KEY")
        )
        kwargs["base_url"] = (
            os.getenv("KIMI_API_BASE")
            or os.getenv("OPENAI_API_BASE")
            or _KIMI_API_BASE
        )
        kwargs["additional_params"] = {
            "reasoning_effort": _kimi_reasoning_effort()
        }

    elif logical_provider == "openai":
        kwargs["provider"] = "openai"
        kwargs["model"] = os.getenv("OPENAI_MODEL") or "gpt-4o"
        kwargs["api_key"] = os.getenv("OPENAI_API_KEY")
        base = os.getenv("OPENAI_API_BASE")
        if base:
            kwargs["base_url"] = base

    elif logical_provider == "anthropic":
        kwargs["provider"] = "anthropic"
        kwargs["model"] = (
            os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-5"
        )
        kwargs["api_key"] = os.getenv("ANTHROPIC_API_KEY")

    else:
        supported = ", ".join(_SUPPORTED_PROVIDERS)
        raise RuntimeError(
            f"Unknown LLM_PROVIDER: {logical_provider!r}. "
            f"Supported values: {supported}."
        )

    if json_mode and logical_provider in _JSON_MODE_PROVIDERS:
        kwargs["response_format"] = {"type": "json_object"}

    # K3's current chat contract does not expose temperature. Omitting it is
    # materially different from sending zero: forwarding a field the endpoint
    # does not accept can reject the entire paid request before inference.
    if temperature is not None and logical_provider != "kimi":
        kwargs["temperature"] = temperature

    return _finish_llm(kwargs, logical_provider)


# Backward-compatible alias: existing callers keep working while provider
# selection is now broader than the original DeepSeek-only implementation.
def create_deepseek_llm(
    *, json_mode: bool = False, temperature: float | None = None
) -> LLM:
    return create_llm(json_mode=json_mode, temperature=temperature)
