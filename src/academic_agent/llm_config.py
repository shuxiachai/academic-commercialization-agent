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
import math
import os
import random
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from crewai import LLM

from academic_agent import llm_parameter_fallback as parameter_fallback
from academic_agent.byok_model import BYOK_MODEL_PATTERN, MODEL_ENV_NAMES  # noqa: F401 - re-exported
from academic_agent.runtime_budget import (
    STREAM_IDLE_TIMEOUT_SECONDS,
    WORKER_LLM_TIMEOUT_ENV,
)

_SUPPORTED_PROVIDERS = ("deepseek", "qwen", "openai", "anthropic")
_PROVIDER_KEY_NAMES = {
    "deepseek": ("DEEPSEEK_API_KEY", "OPENAI_API_KEY"),
    "qwen": ("DASHSCOPE_API_KEY", "OPENAI_API_KEY"),
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
}

# Qwen is exposed through Alibaba Model Studio's OpenAI-compatible chat
# endpoint, but remains a logical provider here. That distinction lets the
# API use the official DASHSCOPE_API_KEY name, pin a safe BYOK endpoint, and
# apply provider-specific accounting without labelling the request OpenAI.
_QWEN_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# There is deliberately no default model. A built-in default silently ran
# qwen3.5-plus whenever QWEN_MODEL went missing, long after production had
# moved on, and a BYOK visitor's key was billed for a model they never named.
# The operator sets the provider's model variable; a BYOK caller names one.

# Anthropic's Messages API requires max_tokens, so CrewAI's Anthropic provider
# always sends one, and its default is 4096. Until 2026-11-12 nothing here set
# it. The report writer's answer is the report: of 436 saved on the
# maintainer's machine, 391 are longer than 4096 tokens by an OpenAI tokenizer
# (median 5,868, longest 13,506; Anthropic's counts run higher), and the
# current Claude models spend part of the same allowance on thinking, which
# cannot be turned off on several of them. No run had gone through Anthropic,
# so nothing had shown it. Model Studio and OpenAI send no limit and get the
# model's own; DeepSeek is below.
#
# A streamed call is bounded per chunk, so it can ask for the room; a plain
# call waits for the whole answer inside one HTTP timeout and asks for less.
# Both are Anthropic's own suggested defaults. A model whose limit is lower
# refuses the request and names its limit: llm_parameter_fallback lowers ours
# to it and the call is sent again.
ANTHROPIC_STREAM_MAX_TOKENS = 64_000
ANTHROPIC_MAX_TOKENS = 16_000

# DeepSeek's own API does not give "the model's own" limit to a request that
# names none. The first run through it since August (2026-11-12, deepseek-chat)
# had its writer stopped at exactly 8,192 output tokens, in the middle of a
# reference entry. The reference list is rebuilt from the validated sources,
# so that report came out whole; a longer body would have been cut in the
# body, and nothing names a cut answer. Of 60 saved single-request writer
# nodes on deepseek-chat, three stopped at exactly 8,192; no node on any
# Model Studio model stopped at a round number.
#
# The API accepted these values for deepseek-chat, deepseek-flash and
# deepseek-v4-pro on that day and names [1, 393216] as the valid range. The
# two thinking models report their reasoning inside the same output count. Another
# host behind DEEPSEEK_API_BASE with a smaller range refuses the request and
# names its range; llm_parameter_fallback lowers ours to the top of it.
DEEPSEEK_STREAM_MAX_TOKENS = 64_000
DEEPSEEK_MAX_TOKENS = 16_000

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
        "No LLM API key found. Set one key and its model:\n"
        "  DEEPSEEK_API_KEY  -> DeepSeek  (model: DEEPSEEK_MODEL)\n"
        "  DASHSCOPE_API_KEY -> Qwen      (model: QWEN_MODEL)\n"
        "  ANTHROPIC_API_KEY -> Anthropic (model: ANTHROPIC_MODEL)\n"
        "  OPENAI_API_KEY    -> OpenAI    (model: OPENAI_MODEL)\n"
        "Or set LLM_PROVIDER explicitly to override auto-detection."
    )


def _configured_api_key(provider: str) -> str:
    """Resolve exactly the credential the operator transport will use.

    Detection alone accepts an explicit selector without a key. Readiness
    must not certify that state, and duplicating the fallback map there would
    reject working legacy Qwen/DeepSeek setups. No key value enters errors.
    Empty BYOK environment sentinels remain empty; do not reload dotenv here.
    """
    names = _PROVIDER_KEY_NAMES.get(provider)
    if names is None:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER: {provider!r}. "
            f"Supported values: {', '.join(_SUPPORTED_PROVIDERS)}."
        )
    key = next((os.getenv(name) for name in names if os.getenv(name)), None)
    if not key or not key.strip():
        raise RuntimeError(f"No LLM API key configured for {provider}: set {' or '.join(names)}.")
    return key


@dataclass(frozen=True)
class ProviderConfig:
    """One credential/model/destination identity, never a printable secret.

    Both the CrewAI factory and the one-shot language transport consume this
    record. Sharing only provider detection left their credential and endpoint
    fallbacks different, sending an OpenAI BYOK key to DeepSeek.
    """

    provider: str
    model: str
    base_url: str
    api_key: str = field(repr=False)


def resolve_provider_config(
    *, provider: str | None = None, api_key: str | None = None,
    model: str | None = None,
) -> ProviderConfig:
    """Resolve locally; explicit BYOK ignores every operator model/base/key.

    Operator-defined HTTPS gateways remain an intentional trust decision.
    Known vendor destinations may not contradict the selected provider.
    Missing/partial credentials fail before construction, never fall back to
    the operator's account. No dotenv reload may undo the worker's sentinels.

    ``model`` is the model for an explicit BYOK caller's own key, and is
    required with explicit credentials, in the BYOK_MODEL_PATTERN shape; the
    endpoint stays the provider's. The operator's model comes from the
    provider's model variable. Neither has a fallback: a missing model fails
    here, before any request, rather than running a built-in one.
    """
    explicit = provider is not None or api_key is not None
    if explicit and (not provider or not api_key or not api_key.strip()):
        raise RuntimeError("Provider and non-empty API key must be supplied together.")
    if model is not None and not explicit:
        raise RuntimeError("A model can only be chosen together with explicit credentials.")
    if explicit and model is None:
        raise RuntimeError("A model must be named together with explicit credentials.")
    if model is not None and not BYOK_MODEL_PATTERN.fullmatch(model):
        raise RuntimeError("Model must be a plain model identifier.")
    selected = provider.lower().strip() if explicit else _detect_provider()
    bases = {
        "deepseek": "https://api.deepseek.com",
        "qwen": _QWEN_API_BASE,
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com",
    }
    if selected not in bases:
        raise RuntimeError("Unknown LLM_PROVIDER; supported: " + ", ".join(_SUPPORTED_PROVIDERS))
    base = bases[selected]
    key = api_key if explicit else _configured_api_key(selected)
    if not explicit:
        names = {
            "deepseek": (("DEEPSEEK_MODEL", "OPENAI_MODEL_NAME"), ("DEEPSEEK_API_BASE", "OPENAI_API_BASE")),
            "qwen": (("QWEN_MODEL", "OPENAI_MODEL_NAME"), ("QWEN_API_BASE", "OPENAI_API_BASE")),
            "openai": (("OPENAI_MODEL", "OPENAI_MODEL_NAME"), ("OPENAI_API_BASE",)),
            "anthropic": (("ANTHROPIC_MODEL",), ("ANTHROPIC_API_BASE",)),
        }
        model_names, base_names = names[selected]
        model = next((os.environ[n].strip() for n in model_names if os.getenv(n, "").strip()), None)
        if model is None:
            raise RuntimeError(f"No model configured for {selected}: set {' or '.join(model_names)}.")
        base = next((os.environ[n] for n in base_names if os.getenv(n)), base)
    if selected == "deepseek" and model.startswith("deepseek/"):
        model = model.split("/", 1)[1]
    base = base.rstrip("/")
    if selected == "anthropic":
        base = base.removesuffix("/v1")
    try:
        parts = urlsplit(base)
        valid = (parts.scheme == "https" and parts.hostname and not parts.username
                 and not parts.password and not parts.query and not parts.fragment)
        # Force malformed port validation without copying the endpoint to logs.
        _ = parts.port
    except ValueError:
        valid = False
    if not valid:
        raise RuntimeError("LLM endpoint must be HTTPS without credentials, query or fragment.")
    host = parts.hostname
    vendor = {
        "api.openai.com": "openai", "api.deepseek.com": "deepseek",
        "api.anthropic.com": "anthropic",
    }.get(host)
    if (host.startswith("dashscope") and host.endswith(".aliyuncs.com")) or host.endswith(".maas.aliyuncs.com"):
        vendor = "qwen"
    if vendor and vendor != selected:
        raise RuntimeError("LLM endpoint does not match the selected provider.")
    return ProviderConfig(selected, model, base, key)


def validate_llm_configuration() -> str:
    """Check local configuration, never construct an SDK or probe a paid API.

    A present key does not establish provider connectivity, balance or quality.
    Keep the returned projection non-secret for the public readiness endpoint.
    """
    return resolve_provider_config().provider


def _qwen_additional_params() -> dict[str, object]:
    """Return a fresh OpenAI SDK extension body for Qwen JSON calls.

    Qwen3 models enable thinking by default. Alibaba's Chat Completions
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
# A streamed call gets more. A failed plain attempt cost its whole window
# (150 or 300 seconds); a failed streamed attempt costs its per-chunk bound,
# about a minute, so the same run time affords more of them. The first
# production run on streamed calls (2026-11-09, 343 s) had the writer and
# the reviewer each use all three attempts; one more failure on either
# would have failed a run that was otherwise 15 seconds from done. Five
# costs at most four minutes of cut streams plus half a minute of backoff
# before the last attempt, and require_window still refuses any attempt
# the stage's remaining time does not hold.
_STREAM_MAX_ATTEMPTS = 5
_BASE_DELAY_SECONDS = 2.0


class RunDeadlineExceeded(TimeoutError):
    """The run lacks a full bounded window for another provider attempt."""


# What a provider calls an answer it ended at an output limit: "length" on the
# OpenAI-shaped APIs (Model Studio, DeepSeek, OpenAI), "max_tokens" on
# Anthropic. Every other reason is an answer the model ended itself.
_CUT_STOP_REASONS = frozenset({"length", "max_tokens"})


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _cut_reason(reason: object, usage: object, limit: object) -> str | None:
    """How a completed attempt says its answer was cut at an output limit; None if it does not.

    The provider's stop reason decides whenever there is one. There is not
    always one: DeepSeek's own API sends a streamed answer's stop reason in
    the same chunk as its usage, and CrewAI 1.14.7's stream reader takes the
    usage from a chunk and skips the rest of it. Seen on 2026-11-12 with a
    real 40-token limit: the answer was cut, 40 output tokens were billed,
    and no reason reached the completed-call event. (Model Studio sends the
    two in separate chunks, and Anthropic's reason travels another way.)

    So when no reason arrived, an answer that used every output token its
    request allowed was cut. That needs the limit to be one this code sent,
    which it is on DeepSeek and Anthropic.
    """
    if isinstance(reason, str):
        return reason if reason in _CUT_STOP_REASONS else None
    spent = usage.get("completion_tokens") if isinstance(usage, dict) else None
    if _is_count(limit) and _is_count(spent) and spent >= limit:
        return f"not reported; all {limit} output tokens allowed were used"
    return None


class AnswerCutError(RuntimeError):
    """The provider ended an answer at an output limit; what arrived is part of one.

    Until 2026-11-12 the stop reason was read by nothing and a cut answer was
    returned like any other. DeepSeek direct that day: the writer stopped at
    exactly 8,192 output tokens, in the middle of a reference entry, and the
    run completed. What happens next depends on where the cut falls. In the
    references it is harmless, because the list is rebuilt. Inside "Evidence
    Limitations" the report guardrail passes it and the section ships ending
    mid-word. Anywhere earlier the guardrail blocks it as a missing heading
    and the whole report is written, and cut, again. A JSON node's cut answer
    is invalid JSON, asked for again up to twice, and fails as a parse error.

    The message is what the status records and what api/runs.py reads to name
    the failure. It never holds the part that arrived.
    """

    def __init__(self, stage: str, stop_reason: str) -> None:
        # A stage is an agent's role as configured, which can end in a newline.
        self.stage, self.stop_reason = " ".join(str(stage).split()), stop_reason
        super().__init__(
            f"{self.stage}: the answer was cut at the model's output limit (stop reason: {stop_reason}); "
            "what arrived is part of an answer and was not used.")


@dataclass
class _CallBudget:
    """Mutable because the worker assigns a stage deadline after Crew creation."""

    deadline_monotonic: float | None = None
    stage: str = "unbounded call"
    request_timeout_seconds: float = 0.0
    #: Calls made through this node so far. A guardrail retry is a new call
    #: whose attempts start at 1 again; the sequence tells the two apart.
    calls: int = 0
    #: The error a call on this node ended with, once the wrapper gave up on
    #: one: its attempts were used up, the run had no time for another, the
    #: provider refused the request outright, or the answer was cut. The node
    #: is then not asked again. CrewAI re-executes a task whose agent raised
    #: (Agent.max_retry_limit is 2 and is never reset), and the wrapper did
    #: not know: a rejected key was sent three times, and a connection that
    #: timed out every time got fifteen attempts where _STREAM_MAX_ATTEMPTS
    #: says five, which on a silent link is sixteen minutes to report what
    #: was known after five and a half. An instance is one node of one run.
    gave_up: BaseException | None = None

    def require_window(self, *, delay_seconds: float = 0.0) -> None:
        if self.deadline_monotonic is None:
            return
        remaining = self.deadline_monotonic - time.monotonic()
        required = delay_seconds + self.request_timeout_seconds
        if remaining < required:
            raise RunDeadlineExceeded(
                f"{self.stage} has {max(0.0, remaining):.1f}s remaining; "
                f"a bounded provider attempt requires {required:.1f}s"
            )


def _max_attempts_for(llm) -> int:
    """How many provider attempts one call on this node may make."""
    return _STREAM_MAX_ATTEMPTS if getattr(llm, "stream", False) is True else _MAX_ATTEMPTS


# A rate limit is the one refusal that passes by itself. Until 2026-11-12 the
# wrapper did nothing about one: _is_retryable sends a 429 straight back, and
# its only second chance was CrewAI running the node again at once, twice,
# with no wait. A streamed node now waits and asks again, inside the attempts
# and the run's time it already had.
#
# No model call in the saved runs was ever refused this way, so the rules are
# the providers' own, read that day. Anthropic sends `retry-after`, the
# seconds to wait. Model Studio names no header and says to retry later, "a
# few minutes" at most for its per-minute limits; without a figure the waits
# before the second to fifth attempts are 15, 30, 60 and 60 seconds, which
# together outlast two of those minutes.
_RATE_LIMIT_BASE_WAIT_SECONDS = 15.0
_RATE_LIMIT_MAX_WAIT_SECONDS = 60.0

# Model Studio answers 429 to these too, and waiting cures none of them: a
# model's free quota used up, a budget exhausted, a bill overdue, a product
# not bought. They fail at once, as every 429 did. Its tokens-per-minute
# limit is worded "insufficient_quota ... check your plan and billing
# details", as OpenAI words an empty account; the two cannot be told apart
# here, and it is waited for, since a wait that proves useless costs time
# and no money.
_NOT_CURED_BY_WAITING = (
    "free allocated quota", "freetieronly", "budgetlimitexceeded", "billoverdue", "arrearage",
    "commoditynotpurchased",
)


def _is_rate_limit(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return "429" in text or "rate limit" in text or "ratelimit" in text


def _stated_wait(exc: BaseException) -> float | None:
    """The seconds a refusal's `retry-after` header asks for, when it is a usable number."""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    try:
        seconds = float(headers.get("retry-after"))
    except (AttributeError, TypeError, ValueError):
        return None
    return seconds if math.isfinite(seconds) and seconds > 0 else None


def _rate_limit_wait(exc: BaseException, attempt: int) -> float | None:
    """Seconds to wait before asking again after a rate limit; None for anything waiting does not cure."""
    if not _is_rate_limit(exc):
        return None
    text = f"{type(exc).__name__}: {exc}".lower()
    if any(marker in text for marker in _NOT_CURED_BY_WAITING):
        return None
    stated = _stated_wait(exc)
    wait = stated if stated is not None else _RATE_LIMIT_BASE_WAIT_SECONDS * (2 ** (attempt - 1))
    return min(wait, _RATE_LIMIT_MAX_WAIT_SECONDS)


def _is_retryable(exc: BaseException) -> bool:
    # This TimeoutError comes from our run budget, not the transport. Retrying
    # it can only consume the time reserved for fallback and final persistence.
    if isinstance(exc, RunDeadlineExceeded):
        return False
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


def _sent_parameters(llm) -> dict[str, object]:
    """The optional parameters llm_parameter_fallback may change, as this LLM sends them."""
    sent: dict[str, object] = {}
    body = (getattr(llm, "additional_params", None) or {}).get("extra_body") or {}
    if "enable_thinking" in body:
        sent["enable_thinking"] = body["enable_thinking"]
    if getattr(llm, "response_format", None) is not None:
        sent["response_format"] = llm.response_format
    if getattr(llm, "temperature", None) is not None:
        sent["temperature"] = llm.temperature
    limit = getattr(llm, "max_tokens", None)
    if isinstance(limit, int) and not isinstance(limit, bool):
        sent["max_tokens"] = limit
    return sent


def _apply_parameter(llm, parameter: str, value: object) -> None:
    """Change one optional parameter on a CrewAI provider instance before its next call."""
    if parameter == "enable_thinking":
        params = dict(getattr(llm, "additional_params", None) or {})
        body = dict(params.get("extra_body") or {})
        if value is parameter_fallback.OMIT:
            body.pop("enable_thinking", None)
        else:
            body["enable_thinking"] = value
        if body:
            params["extra_body"] = body
        else:
            params.pop("extra_body", None)
        llm.additional_params = params
    elif parameter == "response_format":
        llm.response_format = None
    elif parameter == "temperature":
        llm.temperature = None
    elif parameter == "max_tokens":
        # A ceiling, learned from one call of this model: it lowers a larger
        # limit and never raises a smaller one. A provider that sends none
        # (Model Studio, OpenAI) keeps sending none.
        current = getattr(llm, "max_tokens", None)
        if isinstance(current, int) and not isinstance(current, bool) and isinstance(value, int):
            llm.max_tokens = min(current, value)


# A model that cannot turn thinking off reasons before every answer. On
# qwen3.7-max-preview the report writer's answer grew from about 6,500 to
# 8,400 tokens, and its stage took 223 s against the 150-second per-call
# budget: one attempt timed out, was billed, and was retried
# (2026-10-23). Such a model gets twice the per-call time, once per LLM.
# Every other model keeps runtime_budget.REQUEST_TIMEOUT_SECONDS.
_THINKING_TIMEOUT_FACTOR = 2


def _set_transport_timeout(llm, seconds: float) -> None:
    """Make the SDK client's per-request timeout match the stage's window.

    A window that lives only in the budget is a fiction: the client built at
    construction still cuts the request at its own timeout, the attempt is
    billed, and the wrapper retries. The 2026-11-08 writer stage (282 s for
    one 6,487-token answer, usage showing one request) is what that looks
    like from outside.
    """
    current = getattr(llm, "timeout", None)
    if isinstance(current, (int, float)) and float(current) == float(seconds):
        return
    llm.timeout = seconds
    # CrewAI builds its OpenAI client once, at construction; with_options
    # is the SDK's own way to copy a client with a different timeout.
    client = getattr(llm, "_client", None)
    if client is not None and hasattr(client, "with_options"):
        llm._client = client.with_options(timeout=seconds)


def _reconnect(llm, stage: str) -> bool:
    """Replace the provider's SDK client so the next attempt opens a new connection.

    In the first production run on streamed calls (2026-11-09) three nodes
    failed the same way: a stream silent for 60 seconds was cut, the retry
    two seconds later failed with a connection error in 15-18 seconds, and
    the attempt after that returned. The retry had been sent down the pool
    that held the connection which had just died. The SDK's with_options
    copies a client but shares its HTTP pool (tests/test_llm_reconnect.py
    pins this against the vendored SDK), so the client is rebuilt from the
    provider's own fields, which carry the stage's timeout and max_retries
    0, and the old one is closed. Best effort: a provider that cannot
    rebuild keeps its client and the retry goes ahead anyway.
    """
    build = getattr(llm, "_build_sync_client", None)
    if not callable(build):
        return False
    previous = getattr(llm, "_client", None)
    try:
        llm._client = build()
    except Exception as exc:  # noqa: BLE001 - the retry matters more than the fresh pool
        print(
            f"[llm] {stage}: could not rebuild the client ({type(exc).__name__}: {exc}); "
            "the connection pool is kept",
            file=sys.stderr, flush=True,
        )
        return False
    close = getattr(previous, "close", None)
    if callable(close):
        try:
            close()
        except Exception:  # noqa: BLE001 - a pool that will not close is garbage either way
            pass
    return True


def _give_thinking_time(llm, budget: "_CallBudget") -> None:
    """Double this LLM's per-call timeout, and the window a call needs, once."""
    if getattr(llm, "_academic_agent_thinking_time", False):
        return
    llm._academic_agent_thinking_time = True
    timeout = getattr(llm, "timeout", None)
    if isinstance(timeout, (int, float)) and timeout > 0:
        _set_transport_timeout(llm, timeout * _THINKING_TIMEOUT_FACTOR)
    if budget.request_timeout_seconds > 0:
        budget.request_timeout_seconds *= _THINKING_TIMEOUT_FACTOR


# One observer for the whole worker process: every provider attempt, returned
# or not, is reported with its stage, number, outcome and duration. It exists
# because usage counts successful requests only, so an attempt the transport
# killed after 150 seconds is billed and then vanishes. The worker installs an
# observer that writes each record to steps.jsonl, where the API can show it.
_attempt_observer: Callable[[dict], None] | None = None


def set_attempt_observer(
    observer: Callable[[dict], None] | None,
) -> Callable[[dict], None] | None:
    """Install the process-wide attempt observer; returns the previous one."""
    global _attempt_observer
    previous = _attempt_observer
    _attempt_observer = observer
    return previous


def _report_attempt(record: dict) -> None:
    """Hand one attempt record to the observer; its failure is not the run's."""
    observer = _attempt_observer
    if observer is None:
        return
    try:
        observer(dict(record))
    except Exception as exc:  # noqa: BLE001 - diagnostics never fail a paid call
        print(
            f"[llm] attempt observer failed: {type(exc).__name__}: {exc}",
            file=sys.stderr, flush=True,
        )


def _is_timeout(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    text = f"{type(exc).__name__}: {exc}".lower()
    return "timed out" in text or "timeout" in text


def set_llm_stage(llm, stage: str) -> None:
    """Label a wrapped LLM with its node so attempt records can be placed.

    Separate from configure_llm_deadline: a direct CLI run has no watchdog
    and configures no deadline, but its attempts still belong to an agent.
    Tolerates objects that are not the adapter, so tests with stand-ins pass.
    """
    budget = getattr(llm, "_academic_agent_call_budget", None)
    if isinstance(budget, _CallBudget):
        budget.stage = stage


def _wrap_with_retry(llm):
    """Add retry to an LLM instance by replacing its bound `call`.

    Not a subclass: crewai.LLM defines __new__ and acts as a factory, so
    LLM(...) returns a provider class such as OpenAICompatibleCompletion —
    `isinstance(LLM(...), LLM)` is False. Subclassing it produces an object
    that bypasses the factory and lacks the provider behaviour entirely.
    Wrapping the instance the factory built leaves that behaviour intact.

    A parameter the model refuses (llm_parameter_fallback) is adapted and
    the call resent at once, remembered for the instance's endpoint and
    model. That resend does not use a transport retry: the provider billed
    nothing and asked for a different request, not for patience.
    """
    inner = llm.call
    budget = _CallBudget()
    # Why the attempt in flight ended. CrewAI hands the provider's stop reason
    # to the event it emits when a call completes and to nothing a caller can
    # read, and its event bus delivers on another thread, usually after the
    # call has returned. The provider's own emit method runs on this thread
    # before `call` returns, so the reason is noted there. An object without
    # that method reports no reason and is treated as before.
    stopped: dict[str, object] = {"reason": None, "usage": None}
    emit = getattr(llm, "_emit_call_completed_event", None)
    if callable(emit):
        @functools.wraps(emit)
        def emit_and_note(*args, **kwargs):
            stopped["reason"] = kwargs.get("finish_reason")
            stopped["usage"] = kwargs.get("usage")
            return emit(*args, **kwargs)

        llm._emit_call_completed_event = emit_and_note
    max_attempts = _max_attempts_for(llm)
    # A plain call does not wait for a rate limit: the paper extractor runs
    # inside a web request, and a minute's wait there is the visitor's.
    waits_out_rate_limits = getattr(llm, "stream", False) is True
    base, model = getattr(llm, "base_url", None), getattr(llm, "model", None)
    identity = (base.rstrip("/"), model) if isinstance(base, str) and isinstance(model, str) else None

    @functools.wraps(inner)
    def call_with_retry(*args, **kwargs):
        if budget.gave_up is not None:
            # stderr for the same reason as the retry notice below.
            print(
                f"[llm] {' '.join(budget.stage.split())}: not asked again after "
                f"{type(budget.gave_up).__name__}",
                file=sys.stderr, flush=True,
            )
            raise budget.gave_up
        if identity is not None:
            for parameter, value in parameter_fallback.learned(*identity).items():
                _apply_parameter(llm, parameter, value)
            if _sent_parameters(llm).get("enable_thinking") is True:
                _give_thinking_time(llm, budget)
        adapted = 0
        attempt = 1
        budget.calls += 1
        call_index = budget.calls

        def report(outcome: str, started: float, *, retry: bool, exc: BaseException | None) -> None:
            _report_attempt({
                "stage": budget.stage,
                "call": call_index,
                "attempt": attempt,
                "outcome": outcome,
                "duration_seconds": max(0.0, time.monotonic() - started),
                "retry": retry,
                "error_type": None if exc is None else type(exc).__name__,
            })

        while True:
            budget.require_window()
            started = time.monotonic()
            stopped["reason"] = stopped["usage"] = None
            try:
                result = inner(*args, **kwargs)
            except BaseException as exc:      # noqa: BLE001 - re-raised below
                change = (parameter_fallback.adjustment(f"{type(exc).__name__}: {exc}", _sent_parameters(llm))
                          if identity is not None else None)
                if change is not None and adapted < len(parameter_fallback.PARAMETERS):
                    adapted += 1
                    parameter_fallback.learn(*identity, *change)
                    _apply_parameter(llm, *change)
                    if change == ("enable_thinking", True):
                        _give_thinking_time(llm, budget)
                    # The provider refused a parameter and billed nothing; the
                    # resend is not a transport retry and keeps the number.
                    report("adapted", started, retry=True, exc=exc)
                    continue
                wait = _rate_limit_wait(exc, attempt)
                if wait is not None:
                    outcome, again = "rate_limited", waits_out_rate_limits
                else:
                    outcome, again = "timeout" if _is_timeout(exc) else "error", _is_retryable(exc)
                if attempt == max_attempts or not again:
                    budget.gave_up = exc
                    report(outcome, started, retry=False, exc=exc)
                    raise
                # Jitter so six agents recovering from one outage, or held
                # back by one limit, do not all return at the same instant.
                # It only adds: never less than a provider asked for.
                delay = wait if wait is not None else _BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                delay += random.uniform(0, delay * 0.25)
                try:
                    budget.require_window(delay_seconds=delay)
                except RunDeadlineExceeded as deadline_error:
                    # Keep the transport error as causal context while making
                    # the actionable failure type visible to Reviewer fallback.
                    budget.gave_up = deadline_error
                    report(outcome, started, retry=False, exc=exc)
                    raise deadline_error from exc
                report(outcome, started, retry=True, exc=exc)
                if wait is not None:
                    # A rate limit says nothing against the connection it
                    # arrived on, so the client is kept.
                    print(
                        f"[llm] {budget.stage}: rate limited on attempt "
                        f"{attempt}/{max_attempts}; asking again in {delay:.1f}s",
                        file=sys.stderr, flush=True,
                    )
                    time.sleep(delay)
                    attempt += 1
                    continue
                reconnected = _reconnect(llm, budget.stage)
                # stderr, not stdout: the API worker's stdout is discarded and
                # its stderr is kept as process.log (api/runs.py). On stdout
                # this notice was unreadable for every production run.
                print(
                    f"[llm] {budget.stage}: {type(exc).__name__} on attempt "
                    f"{attempt}/{max_attempts}; retrying in {delay:.1f}s"
                    + (" on a new connection" if reconnected else ""),
                    file=sys.stderr, flush=True,
                )
                time.sleep(delay)
                attempt += 1
            else:
                cut = _cut_reason(stopped["reason"], stopped["usage"], getattr(llm, "max_tokens", None))
                if cut is not None:
                    budget.gave_up = AnswerCutError(budget.stage, cut)
                    report("cut", started, retry=False, exc=None)
                    raise budget.gave_up
                report("returned", started, retry=False, exc=None)
                return result

    llm.call = call_with_retry
    # A private attribute is the seam between factory-time wrapping and the
    # worker, which cannot know the concrete provider subclass CrewAI returns.
    llm._academic_agent_call_budget = budget
    return llm


def configure_llm_deadline(
    llm,
    *,
    deadline_monotonic: float | None,
    stage: str,
    request_timeout_seconds: float,
):
    """Attach one code-owned stage deadline to a wrapped CrewAI provider."""

    budget = getattr(llm, "_academic_agent_call_budget", None)
    if not isinstance(budget, _CallBudget):
        raise RuntimeError("LLM was not created through the retry/deadline adapter")
    if request_timeout_seconds <= 0:
        raise ValueError("request timeout must be positive")
    budget.deadline_monotonic = deadline_monotonic
    budget.stage = stage
    budget.request_timeout_seconds = request_timeout_seconds
    # A streamed node keeps its per-chunk bound: the window says how long a
    # healthy attempt may take, not how long to wait for the next byte.
    if not getattr(llm, "stream", False):
        _set_transport_timeout(llm, request_timeout_seconds)
    return llm


def _apply_worker_transport_budget(kwargs: dict) -> None:
    """Bound SDK calls only inside an API worker, never inline PDF extraction.

    The project's wrapper remains the sole retry owner. CrewAI's compatible
    clients otherwise perform their own hidden retries inside each of our
    three visible attempts, which makes neither the time nor request count
    bounded at the orchestration layer.
    """

    raw = os.getenv(WORKER_LLM_TIMEOUT_ENV, "").strip()
    if not raw:
        return
    try:
        timeout = float(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"{WORKER_LLM_TIMEOUT_ENV} must be a positive number"
        ) from exc
    if timeout <= 0:
        raise RuntimeError(f"{WORKER_LLM_TIMEOUT_ENV} must be a positive number")
    kwargs["timeout"] = timeout
    kwargs["max_retries"] = 0


def create_llm(
    *,
    json_mode: bool = False,
    temperature: float | None = None,
    provider: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    stream: bool = False,
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
    config = resolve_provider_config(provider=provider, api_key=api_key, model=model)
    logical_provider = config.provider
    # Explicit bases also defeat SDK-specific OPENAI_BASE_URL /
    # ANTHROPIC_BASE_URL defaults inside the shared API process.
    kwargs: dict = {
        "provider": "openai" if logical_provider == "qwen" else logical_provider,
        "api_key": config.api_key,
        "model": config.model,
        "base_url": config.base_url,
    }
    if logical_provider == "qwen":
        kwargs["additional_params"] = _qwen_additional_params()

    if json_mode and logical_provider in _JSON_MODE_PROVIDERS:
        kwargs["response_format"] = {"type": "json_object"}
    if logical_provider == "anthropic":
        kwargs["max_tokens"] = ANTHROPIC_STREAM_MAX_TOKENS if stream else ANTHROPIC_MAX_TOKENS
    elif logical_provider == "deepseek":
        kwargs["max_tokens"] = DEEPSEEK_STREAM_MAX_TOKENS if stream else DEEPSEEK_MAX_TOKENS

    if temperature is not None:
        kwargs["temperature"] = temperature

    _apply_worker_transport_budget(kwargs)
    if stream:
        # The crew nodes stream. CrewAI 1.14.7 then asks for usage in the
        # final chunk, so accounting is unchanged, and the SDK timeout bounds
        # the wait for one chunk: a dead connection shows in a minute, where
        # a plain request waited out its whole window (2026-11-09: 302, 312
        # and 160 seconds, retried in 27-95). The wrapper stays the only
        # owner of a request's retries on every path, CLI included: a hidden
        # SDK resend of a stalled stream would be billed and absent from the
        # attempt record. CrewAI running the whole node again after the
        # wrapper has given up is another layer; _CallBudget.gave_up is
        # where that one is stopped.
        kwargs["stream"] = True
        kwargs["timeout"] = float(STREAM_IDLE_TIMEOUT_SECONDS)
        kwargs["max_retries"] = 0
    return _wrap_with_retry(LLM(**kwargs))


# Backward-compatible alias — existing code that imports create_deepseek_llm keeps working
def create_deepseek_llm(
    *, json_mode: bool = False, temperature: float | None = None
) -> LLM:
    return create_llm(json_mode=json_mode, temperature=temperature)
