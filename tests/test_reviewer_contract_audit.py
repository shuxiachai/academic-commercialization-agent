"""The reviewer contract audit names each failure's cause and never invents one."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "reviewer_contract_audit.py"
_spec = importlib.util.spec_from_file_location("reviewer_contract_audit", SCRIPT)
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)

# Shapes of the guardrail messages persisted on 2026-10-23.
TOO_LONG = ("Reviewer patch plan is invalid JSON: 2 validation errors for ReviewerCorrectionPlan\n"
            "corrections.4.reason\n  String should have at most 300 characters [type=string_too_long, ...]\n"
            "corrections.7.reason\n  String should have at most 300 characters [type=string_too_long, ...]")
TOO_MANY = ("Reviewer patch plan is invalid JSON: 1 validation error for ReviewerCorrectionPlan\ncorrections\n"
            "  List should have at most 20 items after validation, not 27 [type=too_long, ...]")
NOT_UNIQUE = "Correction 1 target occurs 2 times; each find value must identify exactly one passage."


@pytest.mark.parametrize("message,cause", [
    (TOO_LONG, "reason_too_long"), (TOO_MANY, "too_many_corrections"),
    (NOT_UNIQUE, "find_not_unique"), ("Reviewer patch plan is invalid JSON: Expecting ',' delimiter", "other"),
])
def test_each_failure_message_gets_its_cause(message, cause):
    assert audit.failure_cause(message) == cause


def _cell(tmp_path, index, *, attempts, status="success", error="", reasons=None):
    directory = tmp_path / f"{index:03d}-full"
    directory.mkdir()
    meta = {"variant": "full", "status": status, "error": error,
            "guardrails": {"report_review_task": {"attempts": attempts}}}
    (directory / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    if reasons is not None:
        plan = {"corrections": [{"find": "a", "replace": "b", "reason": r} for r in reasons]}
        (directory / "reviewer_correction_plan.json").write_text(json.dumps(plan), encoding="utf-8")


def test_attempts_terminal_failures_and_accepted_reasons_are_counted_separately(tmp_path):
    _cell(tmp_path, 1, attempts=[{"passed": True}], reasons=["x" * 100, "y" * 260])
    _cell(tmp_path, 2, attempts=[{"passed": False, "failure": TOO_LONG}, {"passed": True}], reasons=["z" * 50])
    _cell(tmp_path, 3, attempts=[{"passed": False, "failure": TOO_MANY},
                                 {"passed": False, "failure": NOT_UNIQUE}], status="error_crew", error=NOT_UNIQUE)
    result = audit.audit(tmp_path)
    assert result["reason_max_chars"] == 300                     # read from the schema, not assumed
    assert (result["full_arm_runs"], result["first_attempt_failures"], result["terminal_failures"]) == (3, 2, 1)
    assert result["first_attempt_causes"]["reason_too_long"] == 1
    assert result["too_long_reasons_per_failed_first_attempt_lower_bound"] == [2]
    assert result["validation_errors_per_failed_first_attempt"] == [2]
    assert result["terminal_causes"]["find_not_unique"] == 1
    assert (result["accepted_plans"], result["accepted_corrections"]) == (2, 3)
    assert result["accepted_reason_chars"]["max"] == 260
