"""Per-run token accounting and cost estimation.

Every run spends real money across six agents, and until now the system
recorded none of it: not how many tokens a run cost, not which agent was
expensive, not whether a failed run burned a full budget before dying.

Two things this module keeps separate on purpose.

**Tokens are measured; cost is estimated.** Token counts come from the
provider's own usage reporting and are facts. Turning them into dollars needs
a price the program cannot verify, and published prices change. So tokens are
always reported, cost only when a price is available, and every cost carries
the basis it was computed from. A cost of $0.00 for a model with no known
price would be the worst possible output: a confident number that reads as
"this run was free".

**`prompt_tokens` does not mean the same thing across providers.** CrewAI
merges every provider into one UsageMetrics shape, but fills it from APIs that
disagree:

    OpenAI / DeepSeek / Kimi
                        prompt_tokens is the whole input, and
                        cached_prompt_tokens is a *subset* of it
    Anthropic           input_tokens *excludes* cache reads and cache writes,
                        which are reported as separate disjoint counters

Billing both at full rate under the OpenAI reading, or subtracting cache reads
under the Anthropic one, produces a wrong number in the direction nobody
checks — cache hits are cheap, so the error is small per request and
compounds silently across a long run. `_billable_prompt_tokens` is where that
distinction lives.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

# USD per 1,000,000 tokens: (input, cached_input, output).
#
# NOT AUTHORITATIVE. Provider prices change, and a stale entry here reports a
# confident wrong number rather than failing — the exact failure mode this
# module exists to avoid. Most estimates are stamped with PRICES_AS_OF; models
# added after that shared census carry their own date rather than falsely
# restamping every older row. LLM_PRICE_PER_MTOK overrides the table without a
# code change. Verify against the provider's pricing page before quoting a
# figure from this project.
PRICES_AS_OF = "2026-05"

_PRICING: dict[str, tuple[float, float, float]] = {
    "deepseek-chat":      (0.27, 0.07, 1.10),
    "deepseek-reasoner":  (0.55, 0.14, 2.19),
    # DeepSeek V4 pricing varies by time. Use published peak rates so a fixed
    # soft stop never understates a request made during the expensive window.
    "deepseek-v4-flash":  (0.44, 0.014, 1.32),
    "kimi-k3":              (3.00, 0.30, 15.00),
    "gpt-4o":             (2.50, 1.25, 10.00),
    "gpt-4o-mini":        (0.15, 0.075, 0.60),
    "gpt-4.1":            (2.00, 0.50, 8.00),
    "gpt-4.1-mini":       (0.40, 0.10, 1.60),
    "claude-opus-4":      (15.00, 1.50, 75.00),
    "claude-sonnet-4":    (3.00, 0.30, 15.00),
    "claude-haiku-4":     (0.80, 0.08, 4.00),
}

_PRICING_BASIS_OVERRIDES = {
    "deepseek-v4-flash": "built-in DeepSeek peak table (as of 2026-08-30)",
    "kimi-k3": "built-in Kimi K3 table (as of 2026-08-30)",
}

# Anthropic bills a cache *write* above the normal input rate. Cache reads are
# already covered by the cached_input column above.
_CACHE_WRITE_MULTIPLIER = 1.25


class _Price:
    __slots__ = ("input", "cached", "output", "basis")

    def __init__(self, input_: float, cached: float, output: float, basis: str) -> None:
        self.input = input_
        self.cached = cached
        self.output = output
        self.basis = basis


def _normalize_model(model: str) -> str:
    """Strip the provider prefix and any trailing date or version suffix.

    Model ids arrive as "deepseek/deepseek-chat", "claude-sonnet-4-20250514",
    or a bare name depending on how the LLM was configured, and all three
    should find the same price row.
    """
    name = (model or "").strip().lower()
    if "/" in name:
        name = name.rsplit("/", 1)[1]
    return name


def _price_from_env() -> _Price | None:
    """LLM_PRICE_PER_MTOK as "input:output" or "input:output:cached"."""
    raw = os.getenv("LLM_PRICE_PER_MTOK", "").strip()
    if not raw:
        return None
    parts = raw.split(":")
    if len(parts) not in (2, 3):
        return None
    try:
        values = [float(p) for p in parts]
    except ValueError:
        return None
    if any(v < 0 for v in values):
        return None
    input_, output = values[0], values[1]
    # Default the cache-read rate to the full input rate rather than to zero:
    # guessing that cache reads are free would understate the bill, and a
    # deployer who cares about the distinction can pass the third field.
    cached = values[2] if len(values) == 3 else input_
    return _Price(input_, cached, output, "env LLM_PRICE_PER_MTOK")


def price_for(
    model: str,
    *,
    allow_env_override: bool = True,
) -> _Price | None:
    """Rates for `model`, or None when the model is not priced.

    None is a real answer here, not an error: it makes the caller report
    tokens without a dollar figure instead of inventing one.
    """
    if allow_env_override:
        env = _price_from_env()
        if env is not None:
            return env
    name = _normalize_model(model)
    if name in _PRICING:
        basis = _PRICING_BASIS_OVERRIDES.get(
            name,
            f"built-in table (as of {PRICES_AS_OF})",
        )
        return _Price(*_PRICING[name], basis=basis)
    # Longest prefix wins so "claude-sonnet-4-20250514" prefers the
    # "claude-sonnet-4" row over a hypothetical shorter "claude" one.
    for key in sorted(_PRICING, key=len, reverse=True):
        if name.startswith(key):
            basis = _PRICING_BASIS_OVERRIDES.get(
                key,
                f"built-in table (as of {PRICES_AS_OF})",
            )
            return _Price(*_PRICING[key], basis=basis)
    return None


def _is_anthropic_shaped(model: str, llm: Any = None) -> bool:
    """Whether cache tokens are reported *outside* prompt_tokens."""
    if llm is not None:
        module = type(llm).__module__ or ""
        if "anthropic" in module or "bedrock" in module:
            return True
    return "claude" in _normalize_model(model)


def _billable_prompt_tokens(
    prompt_tokens: int, cached_tokens: int, *, anthropic_shaped: bool
) -> int:
    """Input tokens charged at the full rate, cache reads excluded.

    See the module docstring: subtracting under the wrong convention is the
    silent error this function exists to prevent.
    """
    if anthropic_shaped:
        return max(prompt_tokens, 0)
    return max(prompt_tokens - cached_tokens, 0)


@dataclass(frozen=True)
class AgentUsage:
    """What one agent spent. `cost_usd` is None when the model has no price."""

    role: str
    model: str
    prompt_tokens: int = 0
    cached_prompt_tokens: int = 0
    cache_creation_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    requests: int = 0
    cost_usd: float | None = None

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "role": self.role,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "requests": self.requests,
            "cost_usd": self.cost_usd,
        }
        # Omitted when zero so the common case stays readable; a reader who
        # sees no cache line can conclude there was no caching.
        if self.cached_prompt_tokens:
            data["cached_prompt_tokens"] = self.cached_prompt_tokens
        if self.cache_creation_tokens:
            data["cache_creation_tokens"] = self.cache_creation_tokens
        if self.reasoning_tokens:
            data["reasoning_tokens"] = self.reasoning_tokens
        return data


@dataclass(frozen=True)
class RunUsage:
    """What a whole run spent, per agent and in total."""

    agents: tuple[AgentUsage, ...] = ()
    total_tokens: int = 0
    total_requests: int = 0
    cost_usd: float | None = None
    #: False when at least one agent's model had no price. The cost above is
    #: then a partial sum, and presenting it as the total would understate the
    #: bill by an unknown amount.
    cost_complete: bool = True
    unpriced_models: tuple[str, ...] = ()
    price_basis: str = ""
    collection_error: str | None = field(default=None)

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "total_tokens": self.total_tokens,
            "total_requests": self.total_requests,
            "cost_usd": self.cost_usd,
            "cost_complete": self.cost_complete,
            "agents": [a.as_dict() for a in self.agents],
        }
        if self.price_basis:
            data["price_basis"] = self.price_basis
        if self.unpriced_models:
            data["unpriced_models"] = list(self.unpriced_models)
        if self.collection_error:
            data["collection_error"] = self.collection_error
        return data


def cost_for(
    model: str,
    metrics: Any,
    *,
    llm: Any = None,
    allow_env_override: bool = True,
) -> float | None:
    """USD for one agent's usage, or None when the model has no price."""
    price = price_for(model, allow_env_override=allow_env_override)
    if price is None:
        return None

    prompt = int(getattr(metrics, "prompt_tokens", 0) or 0)
    cached = int(getattr(metrics, "cached_prompt_tokens", 0) or 0)
    created = int(getattr(metrics, "cache_creation_tokens", 0) or 0)
    completion = int(getattr(metrics, "completion_tokens", 0) or 0)
    # Reasoning tokens are billed as output and are already inside
    # completion_tokens for every provider CrewAI supports, so adding them
    # again would double-charge the most expensive category.

    billable = _billable_prompt_tokens(
        prompt, cached, anthropic_shaped=_is_anthropic_shaped(model, llm)
    )
    usd = (
        billable * price.input
        + cached * price.cached
        + created * price.input * _CACHE_WRITE_MULTIPLIER
        + completion * price.output
    ) / 1_000_000
    return round(usd, 6)


def collect_usage(crew: Any) -> RunUsage:
    """Read per-agent token usage off a finished (or failed) crew.

    Never raises. A crash while accounting for a run must not destroy the run
    it was accounting for, and this is called on the failure path too — where
    the numbers matter most, because a run that died halfway still spent
    whatever it spent before dying.
    """
    try:
        return _collect_usage(crew)
    except Exception as exc:  # noqa: BLE001 - accounting must never fail a run
        return RunUsage(collection_error=f"{type(exc).__name__}: {exc}"[:200])


def _collect_usage(crew: Any) -> RunUsage:
    agents: list[AgentUsage] = []
    unpriced: list[str] = []
    bases: list[str] = []
    total_cost = 0.0
    complete = True

    for agent in getattr(crew, "agents", None) or ():
        llm = getattr(agent, "llm", None)
        summarize = getattr(llm, "get_token_usage_summary", None)
        if summarize is None:
            # getattr rather than attribute access throughout: `crew` is a
            # duck-typed seam in tests, and an agent whose llm cannot report
            # usage should drop out of the accounting rather than abort it.
            continue
        metrics = summarize()
        model = str(getattr(llm, "model", "") or "")
        cost = cost_for(model, metrics, llm=llm)
        if cost is None:
            complete = False
            if model not in unpriced:
                unpriced.append(model or "(unnamed model)")
        else:
            total_cost += cost
            price = price_for(model)
            if price is not None and price.basis not in bases:
                bases.append(price.basis)

        agents.append(AgentUsage(
            # Stripped: roles come from a YAML block scalar and keep its
            # trailing newline, which then lands inside a JSON string and
            # breaks every table that lines these up in a column.
            role=str(getattr(agent, "role", "") or "").strip(),
            model=model,
            prompt_tokens=int(getattr(metrics, "prompt_tokens", 0) or 0),
            cached_prompt_tokens=int(getattr(metrics, "cached_prompt_tokens", 0) or 0),
            cache_creation_tokens=int(getattr(metrics, "cache_creation_tokens", 0) or 0),
            completion_tokens=int(getattr(metrics, "completion_tokens", 0) or 0),
            reasoning_tokens=int(getattr(metrics, "reasoning_tokens", 0) or 0),
            total_tokens=int(getattr(metrics, "total_tokens", 0) or 0),
            requests=int(getattr(metrics, "successful_requests", 0) or 0),
            cost_usd=cost,
        ))

    return RunUsage(
        agents=tuple(agents),
        total_tokens=sum(a.total_tokens for a in agents),
        total_requests=sum(a.requests for a in agents),
        # A partial sum is still worth reporting -- it is a floor on the bill
        # -- but only next to the flag saying it is a floor.
        cost_usd=round(total_cost, 6) if agents else None,
        cost_complete=complete,
        unpriced_models=tuple(unpriced),
        price_basis=" + ".join(bases),
    )
