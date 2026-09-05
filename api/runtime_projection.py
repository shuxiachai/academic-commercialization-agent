"""Read-only runtime summary contracts, after immutable snapshot selection.

These do not validate checkpoint manifests or authorize recovery. Their job is
to keep malformed persisted display data from crashing HTTP/JavaScript or
looking like a zero bill or a successful cache hit. Do not use them to repair
writer artifacts or substitute mutable usage for an invalid terminal snapshot.
"""

from collections.abc import Callable
import json
import sys
from typing import Any


_NODES = {"retrieval", "academic", "patent", "market", "writer", "reviewer", "scorer"}
_COUNTERS = ("total_tokens", "total_requests", "requests", "prompt_tokens",
             "completion_tokens", "cached_prompt_tokens", "cache_creation_tokens", "reasoning_tokens")


def _count(value: Any) -> bool:
    # JavaScript cannot faithfully display integers beyond this boundary.
    # bool-as-int, truncation and numeric-string coercion would invent facts.
    return type(value) is int and 0 <= value <= 2**53 - 1


def _price(value: Any) -> bool:
    # Comparisons also reject NaN/Infinity without float(huge_int) overflow.
    return value is None or (type(value) in (int, float) and 0 <= value <= sys.float_info.max)


def _strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _nodes(value: Any) -> bool:
    return _strings(value) and all(node in _NODES for node in value) and len(value) == len(set(value))


def _one_of(*choices: str) -> Callable[[Any], bool]:
    return lambda value: isinstance(value, str) and value in choices


def _fields(value: Any, checks: dict[str, Callable[[Any], bool]], required=()) -> bool:
    if not isinstance(value, dict):
        return False
    # Broad dict response models permit extension fields. Preserve valid ones,
    # but not non-standard JSON numbers which make Starlette fail to serialize
    # even when they occur in a currently unconsumed diagnostic subfield.
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        return False
    return all(key in value for key in required) and all(
        check(value[key]) for key, check in checks.items() if key in value
    )


def _agent(value: Any) -> bool:
    return _fields(value, {
        **{key: _count for key in _COUNTERS}, "cost_usd": _price,
        "role": lambda item: isinstance(item, str),
    }, required=("role", "total_tokens"))


def _usage(value: Any) -> bool:
    # Optional fields stay optional for historical totals. Do not require the
    # current collector's entire schema or infer totals by summing agent rows.
    # A legacy collector failure may contain only its diagnostic, without any
    # observed counters. Preserve that explicit failure instead of labelling
    # it malformed or supplying a fabricated zero-token observation.
    diagnostic_only_allowed = (
        isinstance(value, dict) and isinstance(value.get("collection_error"), str)
        and bool(value["collection_error"])
    )
    return _fields(value, {
        **{key: _count for key in _COUNTERS}, "cost_usd": _price,
        "cost_complete": lambda item: type(item) is bool,
        "price_basis": lambda item: isinstance(item, str),
        "collection_error": lambda item: item is None or isinstance(item, str),
        "unpriced_models": _strings,
        "agents": lambda items: isinstance(items, list) and all(_agent(item) for item in items),
    }, required=() if diagnostic_only_allowed else ("total_tokens",))


def _accounting(value: Any) -> bool:
    if not _fields(value, {
        "state": _one_of("complete", "lower_bound", "unavailable"),
        "run_complete": lambda item: type(item) is bool,
        "in_flight_request_may_have_spent": lambda item: type(item) is bool,
        "snapshot_at": lambda item: item is None or isinstance(item, str),
        "through_stage": lambda item: isinstance(item, str),
    }, required=("state",)):
        return False
    # Legacy state-only projections are readable; explicit contradictory flags
    # are not. Immutable terminal timing is validated by its own contract.
    if value["state"] == "complete":
        return value.get("run_complete") is not False and value.get("in_flight_request_may_have_spent") is not True
    return not (value["state"] == "lower_bound" and value.get("run_complete") is True)


def _checkpointing(value: Any) -> bool:
    return _fields(value, {
        "state": _one_of("partial", "complete", "degraded"),
        "committed_nodes": _nodes, "errors": _strings,
    }, required=("state",))


def _recovery(value: Any) -> bool:
    if not _fields(value, {
        "state": _one_of("not_requested", "cold_start", "reused", "unavailable"),
        "reused_nodes": _nodes,
        "source_run_id": lambda item: item is None or isinstance(item, str),
        "next_node": lambda item: item is None or (isinstance(item, str) and item in _NODES),
    }, required=("state",)):
        return False
    return value["state"] != "reused" or bool(value.get("reused_nodes"))


def _uncertain_accounting(state: str, previous: dict | None) -> dict:
    # Only retain already validated observations. Never put reader wall-clock
    # time into an execution snapshot or derive an exact final bill from it.
    return {
        "state": state, "snapshot_at": previous.get("snapshot_at") if previous else None,
        "through_stage": previous.get("through_stage", "") if previous else "",
        # Losing counters does not negate separately readable completion facts.
        # An invalid accounting object, in contrast, supplies neither flag.
        "run_complete": previous.get("run_complete", False) if previous and state == "unavailable" else False,
        "in_flight_request_may_have_spent": previous.get("in_flight_request_may_have_spent", True) if previous else True,
    }


def project_runtime_metadata(values: dict) -> tuple[dict, list[str]]:
    """Isolate selected bad summaries; keep valid sibling facts and original bytes."""
    projected = dict(values)
    unreadable = []
    checks = {"usage": _usage, "usage_accounting": _accounting,
              "checkpointing": _checkpointing, "recovery": _recovery}
    for field, check in checks.items():
        value = projected.get(field)
        if value is not None and not check(value):
            projected[field] = None
            unreadable.append(field)

    usage, accounting = projected.get("usage"), projected.get("usage_accounting")
    trustworthy = usage is not None and not usage.get("collection_error")
    if "usage" in unreadable:
        projected["usage_accounting"] = _uncertain_accounting("unavailable", accounting)
    elif "usage_accounting" in unreadable:
        projected["usage_accounting"] = _uncertain_accounting("lower_bound" if trustworthy else "unavailable", None)
    elif accounting and accounting["state"] in ("complete", "lower_bound") and not trustworthy:
        # A mutable status can claim complete without a measurement. Keep a
        # real collector-error diagnostic, but never certify its default zero.
        unreadable.append("usage_accounting")
        projected["usage_accounting"] = _uncertain_accounting("unavailable", accounting)
    elif usage and usage.get("collection_error") and accounting is None:
        # This is a readable failure, not a read fault. Older writers did not
        # always emit an accounting object next to their diagnostic.
        projected["usage_accounting"] = _uncertain_accounting("unavailable", None)
    return projected, unreadable
