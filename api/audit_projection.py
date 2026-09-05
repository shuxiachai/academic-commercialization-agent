"""Validate display-facing audit summaries without rewriting paid artifacts.

The writer's current schemas are deliberately NOT the read contract: historical
runs have count-only grounding/consistency summaries and optional newer fields.
Validate the values the reliability panel consumes, not every experimental or
producer-only field. This is shape validation, not citation truth validation.
"""

from collections.abc import Callable
from typing import Any


def _count(value: Any) -> bool:
    # bool is an int in Python; accepting it would certify a corrupt counter.
    return type(value) is int and value >= 0


def _strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _one_of(*choices: str) -> Callable[[Any], bool]:
    return lambda value: isinstance(value, str) and value in choices


def _fields(value: dict, checks: dict[str, Callable[[Any], bool]], required=()) -> bool:
    return all(key in value for key in required) and all(
        check(value[key]) for key, check in checks.items() if key in value
    )


def _summary(field: str, value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    state = value.get("status")
    if field == "source_counts":
        return bool(value) and all(_count(count) for count in value.values())
    if field == "consistency":
        return _fields(value, {
            "blockers": _count, "warnings": _count,
            "status": _one_of("completed"),
        }, required=("blockers",))
    if field == "quality_review":
        return _fields(value, {
            "status": _one_of("passed", "partial", "fallback", "unavailable"),
            "unapplied_corrections": _count,
        }, required=("status", "unapplied_corrections") if state == "partial" else ("status",))
    if field == "claim_grounding":
        # Legacy summaries have no status but do have the three counters.
        # A recorded failure legitimately lacks counters; do not manufacture
        # zero measurements to make it fit a successful-screen schema.
        required = () if state in ("failed", "unavailable", "not_applicable") else (
            "checked", "ungrounded", "unverifiable",
        )
        if state == "partial":
            required += ("unavailable_domains",)
        return _fields(value, {
            "status": _one_of("completed", "partial", "failed", "unavailable", "not_applicable"),
            "checked": _count, "ungrounded": _count, "unverifiable": _count,
            "unavailable_domains": _strings,
        }, required=required)
    if field == "report_audit":
        return _fields(value, {
            "status": _one_of("completed", "partial", "failed", "unavailable", "not_applicable"),
            "findings": _count, "citation_scope_checked": _count,
            "citation_scope_unverifiable": _count,
        }, required=("status",) if state in ("failed", "unavailable", "not_applicable")
           else ("status", "findings"))
    if field == "authority_coverage":
        return _fields(value, {
            "status": _one_of("complete", "incomplete", "not_applicable"),
            "missing_categories": _strings, "required_categories": _strings,
        }, required=("status", "missing_categories") if state == "incomplete" else ("status",))
    if field == "component_coverage":
        required = ("status",)
        if state == "incomplete":
            required += ("missing_components",)
        if state in ("partial", "unchecked"):
            required += ("unchecked_components",)
        return _fields(value, {
            "status": _one_of("complete", "incomplete", "partial", "unchecked", "not_applicable"),
            "missing_components": _strings, "unchecked_components": _strings,
        }, required=required)
    return False


_SUMMARY_FIELDS = (
    "consistency", "quality_review", "claim_grounding", "report_audit",
    "authority_coverage", "component_coverage", "source_counts",
)


def project_audit_metadata(status: dict) -> tuple[dict, list[str]]:
    """Return an isolated view and code-owned fault names for both HTTP readers.

    None/absence retains historical semantics. A present malformed summary is
    replaced only in this view and named explicitly: null alone would hide the
    read fault as an old run, while rejecting the whole status would erase valid
    neighbors and terminal/usage facts. Never expose exception text or malformed
    values in the diagnostic, and never persist this derived view to disk.
    """
    projected = dict(status)
    unreadable = []
    for field in (*_SUMMARY_FIELDS, "failed_domains", "evidence_incomplete"):
        value = status.get(field)
        if value is None:
            continue
        if field == "failed_domains":
            valid = _strings(value)
        elif field == "evidence_incomplete":
            valid = type(value) is bool
        else:
            valid = _summary(field, value)
        if not valid:
            unreadable.append(field)
            projected[field] = {"failed_domains": [], "evidence_incomplete": False}.get(field)
    return projected, unreadable
