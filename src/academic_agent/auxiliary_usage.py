"""Operation-local helper observations, separate from Crew and terminal v1.

This is accounting, never admission or retry authority. A pending call may
have spent. SDK counters are a lower bound: project and SDK retries are hidden.
Only fixed categories, exact known model names and validated numbers cross
this boundary. No prompt, response, endpoint, credential or exception is saved.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import copy
import json
import logging
import math
import os
from pathlib import Path
import threading
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from academic_agent.token_usage import price_for

FILE_NAME = "auxiliary_usage.json"
MAX_BYTES = 256_000
MAX_CALLS = 256
Stage = Literal["search_planning", "translation", "heading_translation", "synonyms", "language_helper", "pdf_extraction"]
MODELS = {
    "deepseek-chat": "deepseek", "deepseek-reasoner": "deepseek",
    "deepseek-v4-flash": "deepseek", "qwen3.5-plus": "qwen",
    "qwen3.7-plus": "qwen", "qwen3.8-max": "qwen", "qwen3.8-27b": "qwen",
    "gpt-4o": "openai", "gpt-4o-mini": "openai", "gpt-4.1": "openai",
    "gpt-4.1-mini": "openai", "claude-sonnet-5": "anthropic",
    "claude-opus-4": "anthropic", "claude-sonnet-4": "anthropic", "claude-haiku-4": "anthropic",
}


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class Tokens(_Strict):
    prompt_tokens: int = Field(ge=0, le=10**12)
    completion_tokens: int = Field(ge=0, le=10**12)
    cached_prompt_tokens: int = Field(default=0, ge=0, le=10**12)
    cache_creation_tokens: int = Field(default=0, ge=0, le=10**12)


class Call(_Strict):
    sequence: int = Field(ge=0, lt=MAX_CALLS)
    stage: Stage
    unit: Literal["http_attempt", "llm_invocation"]
    model: str | None = None
    state: Literal["pending", "settled"] = "pending"
    outcome: Literal["returned", "call_failed", "response_invalid"] | None = None
    tokens: Tokens | None = None

    @model_validator(mode="after")
    def facts(self):
        if self.model is not None and self.model not in MODELS:
            raise ValueError("Unknown model identity")
        if (self.state == "pending") != (self.outcome is None):
            raise ValueError("Invalid settlement")
        if (self.stage == "pdf_extraction") != (self.unit == "llm_invocation"):
            raise ValueError("Invalid invocation unit")
        if self.state == "pending" and self.tokens is not None:
            raise ValueError("Pending usage is unavailable")
        if self.tokens is not None:
            if self.model is None:
                raise ValueError("Unknown token convention")
            if MODELS[self.model] != "anthropic" and (
                self.tokens.cached_prompt_tokens > self.tokens.prompt_tokens
                or self.tokens.cache_creation_tokens != 0
            ):
                raise ValueError("Invalid cache counters")
        return self


def unavailable(state="not_recorded") -> dict:
    return {
        "schema_version": 1, "record_state": state, "coverage": "unavailable",
        "accounting_scope": "auxiliary_llm", "end_to_end_cost_complete": False,
        "call_count": None, "provider_attempt_count": None, "total_tokens": None,
        "observed_tokens": None, "observed_cost_usd": None, "cost_complete": False,
        "calls": [], "pdf_reference": None,
    }


class Ledger(_Strict):
    schema_version: int = Field(default=1, ge=1, le=1)
    storage_failed: bool = False
    operation_complete: bool = False
    calls: list[Call] = Field(default_factory=list, max_length=MAX_CALLS)
    # The API freezes only this independent PDF ledger, not the parent's
    # helper calls, before child launch. No paper/run capability is published.
    pdf_reference: dict | None = None

    @model_validator(mode="after")
    def unique_calls(self):
        if [c.sequence for c in self.calls] != list(range(len(self.calls))):
            raise ValueError("Invalid call sequence")
        if self.pdf_reference is not None:
            validate_reference(self.pdf_reference)
        return self


def validate_reference(value: dict) -> dict | None:
    if set(value) != {"relation", "observation"} or value["relation"] != "reference_only":
        raise ValueError("Invalid PDF reference")
    obs = value["observation"]
    if obs is None:
        return None
    # Persist the strict source ledger, not an arbitrary nested public dict.
    if not isinstance(obs, dict) or obs.get("pdf_reference") is not None:
        raise ValueError("Invalid PDF observation")
    ledger = Ledger.model_validate(obs)
    if len(ledger.calls) > 1 or any(c.stage != "pdf_extraction" for c in ledger.calls):
        raise ValueError("Not a PDF observation")
    return ledger.model_dump()


def _cost(call: Call) -> float | None:
    if call.tokens is None or call.model is None:
        return None
    price = price_for(call.model, allow_env_override=False)
    if price is None:
        return None
    t = call.tokens
    prompt = t.prompt_tokens if MODELS[call.model] == "anthropic" else t.prompt_tokens - t.cached_prompt_tokens
    amount = (prompt * price.input + t.cached_prompt_tokens * price.cached
              + t.cache_creation_tokens * price.input * 1.25 + t.completion_tokens * price.output) / 1_000_000
    return round(amount, 6) if math.isfinite(amount) and amount >= 0 else None


def project(ledger: Ledger) -> dict:
    result = unavailable("write_failed" if ledger.storage_failed else "recorded")
    rows = []
    for call in ledger.calls:
        tokens = call.tokens
        total = None if tokens is None else tokens.prompt_tokens + tokens.completion_tokens
        if total is not None and MODELS[call.model] == "anthropic":
            total += tokens.cached_prompt_tokens + tokens.cache_creation_tokens
        price = price_for(call.model, allow_env_override=False) if call.model else None
        rows.append({
            **call.model_dump(), "provider_attempt_count": 1 if call.unit == "http_attempt" else None,
            "total_tokens": total, "observed_cost_usd": _cost(call),
            "price_basis": price.basis if price else None,
        })
    complete = (ledger.operation_complete and not ledger.storage_failed
                and all(c.state == "settled" and c.tokens is not None and c.unit == "http_attempt" for c in ledger.calls))
    observed = [r["total_tokens"] for r in rows if r["total_tokens"] is not None]
    costs = [r["observed_cost_usd"] for r in rows if r["observed_cost_usd"] is not None]
    result.update(
        coverage="complete" if complete else "partial" if ledger.operation_complete else "pending",
        call_count=len(rows),
        provider_attempt_count=len(rows) if all(c.unit == "http_attempt" for c in ledger.calls) else None,
        total_tokens=sum(observed) if complete else None,
        observed_tokens=sum(observed) if observed or complete else None,
        observed_cost_usd=round(sum(costs), 6) if costs or complete and not rows else None,
        cost_complete=complete and len(costs) == len(rows), calls=rows,
    )
    if ledger.pdf_reference is not None:
        saved = validate_reference(ledger.pdf_reference)
        result["pdf_reference"] = {"relation": "reference_only", "observation":
                                   project(Ledger.model_validate(saved)) if saved is not None else unavailable()}
    return result


def read_ledger(path: Path) -> Ledger | None:
    """Bounded read; absence is distinct from malformed/unavailable storage."""
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return None
    if len(data) > MAX_BYTES:
        raise ValueError("Auxiliary record too large")
    raw = json.loads(data)
    if not isinstance(raw, dict) or type(raw.get("schema_version")) is not int:
        raise ValueError("Invalid auxiliary schema")
    return Ledger.model_validate(raw)


def reconcile(first: Ledger | None, second: Ledger | None) -> Ledger | None:
    """Join immutable call facts by sequence, never add duplicate snapshots.

    A status fallback may be newer than a pending sidecar after a failed
    replacement. Conflicting finalized facts are unreadable, not a maximum
    invented from two different observations. No read writes either source.
    """
    if first is None or second is None:
        value = first if first is not None else second
        return value.model_copy(deep=True) if value is not None else None
    result = first.model_copy(deep=True)
    for incoming in second.calls:
        if incoming.sequence == len(result.calls):
            result.calls.append(incoming.model_copy(deep=True))
            continue
        saved = result.calls[incoming.sequence]
        if (saved.stage, saved.unit, saved.model) != (incoming.stage, incoming.unit, incoming.model):
            raise ValueError("Conflicting auxiliary call identity")
        if saved.state == incoming.state == "settled" and saved != incoming:
            raise ValueError("Conflicting auxiliary settlement")
        if saved.state == "pending" and incoming.state == "settled":
            result.calls[incoming.sequence] = incoming.model_copy(deep=True)
    if first.pdf_reference is not None and second.pdf_reference is not None and first.pdf_reference != second.pdf_reference:
        raise ValueError("Conflicting auxiliary PDF association")
    result.pdf_reference = copy.deepcopy(first.pdf_reference if first.pdf_reference is not None else second.pdf_reference)
    result.storage_failed = first.storage_failed or second.storage_failed
    result.operation_complete = any(
        value.operation_complete and len(value.calls) == len(result.calls) for value in (first, second)
    )
    return Ledger.model_validate(result.model_dump())


def read_observation(path: Path, *, fallback=None) -> Ledger | None:
    failed = False
    try:
        primary = read_ledger(path)
    except (OSError, ValueError, TypeError, RecursionError):
        primary, failed = None, True
    secondary = None
    if fallback is not None:
        try:
            secondary = Ledger.model_validate(fallback)
        except (ValueError, TypeError, RecursionError):
            failed = True
    result = reconcile(primary, secondary)
    if result is None:
        if failed:
            raise ValueError("Auxiliary observations unavailable")
        return None
    if failed or (primary is None and secondary is not None):
        result.storage_failed = True
    return result


def read_summary(path: Path, *, storage_failed=False, fallback=None) -> dict:
    try:
        ledger = read_observation(path, fallback=fallback)
        if ledger is None:
            return unavailable("write_failed" if storage_failed is True else "not_recorded")
        ledger.storage_failed |= storage_failed is True
        return project(ledger)
    except (OSError, ValueError, TypeError, RecursionError):
        return unavailable("unreadable")


def run_reference(directory: Path) -> dict | None:
    """Resume copies only the reconciled association, not the parent's calls."""
    fallback = None
    try:
        with (directory / "status.json").open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
        if len(raw) <= MAX_BYTES:
            status = json.loads(raw)
            if isinstance(status, dict):
                fallback = status.get("auxiliary_usage_snapshot")
    except (OSError, ValueError, TypeError, RecursionError):
        pass  # The independent sidecar may still have a valid association.
    try:
        ledger = read_observation(directory / FILE_NAME, fallback=fallback)
        return copy.deepcopy(ledger.pdf_reference) if ledger is not None else None
    except (OSError, ValueError, TypeError, RecursionError):
        return {"relation": "reference_only", "observation": Ledger(storage_failed=True).model_dump()}


def encode_handoff(snapshot: dict) -> str:
    """Bounded parent-to-worker facts, not credentials or a new billing input.

    API launch has no helper calls yet and at most one PDF invocation reference.
    Keeping this tiny strict envelope in argv survives failure of the *first*
    auxiliary publication without adding another required disk write or gate.
    """
    ledger = Ledger.model_validate(snapshot)
    if ledger.calls:
        raise ValueError("Initial auxiliary handoff contains worker calls")
    value = json.dumps(ledger.model_dump(), ensure_ascii=True, separators=(",", ":"))
    if len(value) > 8192:
        raise ValueError("Auxiliary handoff too large")
    return value


def decode_handoff(value: str | None) -> dict | None:
    if value is None:
        return None
    try:
        if len(value) > 8192:
            raise ValueError("Auxiliary handoff too large")
        data = json.loads(value)
        encode_handoff(data)
        return data
    except (ValueError, TypeError, RecursionError):
        return Ledger(storage_failed=True).model_dump()


class Collector:
    """One operation owner; each logical call replaces its own final state."""

    def __init__(self, path: Path, *, pdf_reference=None, initial=None):
        self.path = path
        self.lock = threading.RLock()
        try:
            self.ledger = read_observation(path, fallback=initial) or Ledger(pdf_reference=pdf_reference)
        except (OSError, ValueError, TypeError, RecursionError):
            # Never overwrite corrupt history with a convincing empty ledger.
            self.ledger = Ledger(storage_failed=True)
            self.path = None
        self.ledger.operation_complete = False
        self._save()

    def _save(self):
        if self.path is None:
            return
        temporary = self.path.with_suffix(".json.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(self.ledger.model_dump(), handle, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError:
            # Sticky even if later publication works: a pre-call reservation
            # may have been lost. Accounting faults cannot retry paid work.
            self.ledger.storage_failed = True
            logging.getLogger(__name__).warning("Auxiliary usage storage unavailable; paid work was not retried")

    def begin(self, stage: Stage, unit: str, model) -> int | None:
        with self.lock:
            if len(self.ledger.calls) >= MAX_CALLS:
                self.ledger.storage_failed = True
                self._save()
                return None
            model = model if isinstance(model, str) and model in MODELS else None
            sequence = len(self.ledger.calls)
            self.ledger.calls.append(Call(sequence=sequence, stage=stage, unit=unit, model=model))
            self._save()  # Before HTTP/SDK dispatch, not after a returned body.
            return sequence

    def settle(self, sequence, tokens, outcome):
        if sequence is None:
            return
        with self.lock:
            old = self.ledger.calls[sequence]
            if old.state == "settled":
                return  # A duplicate finalizer is not another charge.
            self.ledger.calls[sequence] = Call(
                sequence=sequence, stage=old.stage, unit=old.unit, model=old.model,
                state="settled", tokens=tokens, outcome=outcome,
            )
            self._save()

    def finish(self):
        with self.lock:
            if self.ledger.operation_complete:
                return
            self.ledger.operation_complete = True
            self._save()

    def summary(self):
        with self.lock:
            return project(self.ledger)

    def snapshot(self):
        with self.lock:
            return self.ledger.model_dump()  # Detached, strictly whitelisted facts.


_CURRENT: ContextVar[Collector | None] = ContextVar("auxiliary_usage", default=None)


@contextmanager
def bind(collector):
    token = _CURRENT.set(collector)
    try:
        yield collector
    finally:
        _CURRENT.reset(token)


def current():
    return _CURRENT.get()


def parse_usage(data, model, *, sdk=False) -> Tokens | None:
    """Defaults in a nonempty SDK summary do not prove a free invocation."""
    if not isinstance(model, str) or model not in MODELS or not isinstance(data, dict):
        return None
    anthropic = MODELS[model] == "anthropic"
    try:
        if sdk or not anthropic:
            values = {"prompt_tokens": data.get("prompt_tokens"), "completion_tokens": data.get("completion_tokens")}
            details = data.get("prompt_tokens_details", {})
            if not isinstance(details, dict):
                return None
            values["cached_prompt_tokens"] = data.get("cached_prompt_tokens", data.get("prompt_cache_hit_tokens", details.get("cached_tokens", 0)))
            values["cache_creation_tokens"] = data.get("cache_creation_tokens", 0)
        else:
            values = {"prompt_tokens": data.get("input_tokens"), "completion_tokens": data.get("output_tokens"),
                      "cached_prompt_tokens": data.get("cache_read_input_tokens", 0),
                      "cache_creation_tokens": data.get("cache_creation_input_tokens", 0)}
        result = Tokens.model_validate(values)
        total = result.prompt_tokens + result.completion_tokens
        if "total_tokens" in data and (type(data["total_tokens"]) is not int or data["total_tokens"] != total):
            return None
        if not anthropic and (result.cached_prompt_tokens > result.prompt_tokens or result.cache_creation_tokens):
            return None
        if sdk and (total == 0 or type(data.get("successful_requests")) is not int or data["successful_requests"] < 1):
            return None
        return result
    except (ValidationError, TypeError, ValueError, OverflowError):
        return None


def pdf_reference(path: Path) -> dict | None:
    """Snapshot once after existing authorization, without a new extraction."""
    try:
        ledger = read_ledger(path)
        if ledger is None:
            return {"relation": "reference_only", "observation": None}
        value = {"relation": "reference_only", "observation": ledger.model_dump()}
        validate_reference(value)
        return copy.deepcopy(value)
    except (OSError, ValueError, TypeError, RecursionError):
        return {"relation": "reference_only", "observation": Ledger(storage_failed=True).model_dump()}
