"""Keep one over-long reviewer edit from failing a whole run.

The Reviewer returns a JSON patch plan, and evidence.py's reviewer guardrail
validates that plan as a whole. One correction whose ``find`` or ``replace``
exceeds ReviewerCorrection's 2,000-character bound therefore rejects every
correction in the plan, spends the task's retry, and, when the model repeats
the edit, fails the run with no report at all (held-out v2, V02 rep 2).

An edit that long is not local and cannot be applied safely, but the exact
corrections beside it can. evidence.py already skips a correction whose target
is absent and names it in the Reviewer Notes; this treats an over-long one the
same way. evidence.py itself is pinned byte-for-byte by frozen OpenAlex
runners, so the behaviour is added around its guardrail instead of inside it,
and ReviewerCorrectionPlan (also a frozen output contract) is unchanged.

Before the guardrail runs, each over-long correction is replaced by a no-op
(find == replace), which the guardrail already drops without effect; the
positions of the other corrections, and so their note numbers, are unchanged.
Only plans whose sole defects are over-long find/replace strings are touched;
any other defect still reaches the guardrail as is and is rejected there.
"""

# No `from __future__ import annotations`: CrewAI checks a guardrail's return
# annotation at runtime and rejects a string where it expects Tuple[bool, Any].
import json
from collections.abc import Callable
from typing import Any

from crewai import TaskOutput
from pydantic import ValidationError

from academic_agent import evidence
from academic_agent.evidence import ReviewerCorrectionPlan

OVERSIZED_NOTE_PREFIX = "Not applied (edit exceeds 2,000 characters):"
_NOTES_HEADING = "\n## Reviewer Notes\n"
_NO_CORRECTIONS = "No corrections required."
# Any one-character string works: the guardrail drops find == replace first.
_NOOP_TEXT = "-"


def _oversized_positions(error: ValidationError) -> set[int] | None:
    """Indices whose only defect is an over-long find/replace, else None."""
    positions: set[int] = set()
    for item in error.errors():
        loc = item.get("loc", ())
        if (
            item.get("type") == "string_too_long"
            and len(loc) == 3
            and loc[0] == "corrections"
            and isinstance(loc[1], int)
            and loc[2] in ("find", "replace")
        ):
            positions.add(loc[1])
        else:
            return None
    return positions or None


def neutralize_oversized_corrections(raw: str) -> tuple[str, list[str]]:
    """Return the plan with over-long corrections made no-ops, and their notes.

    Returns ``(raw, [])`` unchanged for valid plans, legacy Markdown output, or
    any plan with another defect.
    """
    text = raw.strip()
    if not text.startswith("{"):
        return raw, []
    try:
        ReviewerCorrectionPlan.model_validate_json(text)
        return raw, []
    except ValidationError as error:
        positions = _oversized_positions(error)
    if positions is None:
        return raw, []
    try:
        payload = json.loads(text)
    except ValueError:
        return raw, []
    items = payload.get("corrections") if isinstance(payload, dict) else None
    if not isinstance(items, list) or max(positions) >= len(items) or \
            not all(isinstance(items[i], dict) for i in positions):
        return raw, []
    notes = []
    for i in sorted(positions):
        reason = items[i].get("reason")
        notes.append(f"{OVERSIZED_NOTE_PREFIX} Correction {i + 1}: {' '.join(str(reason).split())}")
        items[i] = {"find": _NOOP_TEXT, "replace": _NOOP_TEXT, "reason": reason}
    rewritten = json.dumps(payload, ensure_ascii=False)
    try:
        ReviewerCorrectionPlan.model_validate_json(rewritten)
    except ValidationError:
        return raw, []
    return rewritten, notes


def _with_notes(report: str, notes: list[str]) -> str:
    """Add skipped-edit notes to the Reviewer Notes section the guardrail wrote."""
    body, marker, section = report.rpartition(_NOTES_HEADING)
    lines = [f"- {note}" for note in notes]
    if not marker:
        return report.rstrip() + "\n\n## Reviewer Notes\n\n" + "\n".join(lines)
    existing = section.strip()
    kept = [] if existing == _NO_CORRECTIONS else [existing]
    return body + marker + "\n" + "\n".join(kept + lines)


def bound_reviewer_guardrail(
    guardrail: Callable[[TaskOutput], tuple[bool, Any]],
) -> Callable[[TaskOutput], tuple[bool, Any]]:
    """Wrap evidence.make_reviewer_guardrail's validator; see the module docstring."""

    def validate_review(output: TaskOutput) -> tuple[bool, Any]:
        output.raw, notes = neutralize_oversized_corrections(output.raw)
        ok, result = guardrail(output)
        if ok and notes:
            result.raw = _with_notes(result.raw, notes)
        return ok, result

    return validate_review


def reviewer_quality_summary(report: str) -> dict[str, str | int]:
    """evidence.reviewer_quality_summary, also counting over-long skipped edits."""
    summary = evidence.reviewer_quality_summary(report)
    _body, marker, section = report.rpartition(_NOTES_HEADING)
    oversized = sum(
        line.startswith(f"- {OVERSIZED_NOTE_PREFIX} ") for line in section.splitlines()
    ) if marker else 0
    unapplied = int(summary.get("unapplied_corrections", 0)) + oversized
    if unapplied:
        return {"status": "partial", "unapplied_corrections": unapplied}
    return summary
