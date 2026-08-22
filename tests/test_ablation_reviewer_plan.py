"""Tests for the correction-level audit artifact in future ablations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import ablation


def _attempt(raw: str, *, passed: bool) -> ablation.GuardrailAttempt:
    return ablation.GuardrailAttempt(
        task_name="report_review_task",
        passed=passed,
        before_chars=len(raw),
        after_chars=100,
        before_sha256_16="before",
        after_sha256_16="after",
        failure="" if passed else "invalid plan",
        raw_before=raw,
    )


def test_persist_successful_reviewer_plan_keeps_exact_applied_edits(
    tmp_path: Path,
) -> None:
    """Regression: counts and final prose cannot recover patch boundaries."""

    failed = '{"corrections": ['
    successful = json.dumps(
        {
            "corrections": [
                {
                    "find": "unsupported claim",
                    "replace": "qualified claim [A1]",
                    "reason": "Qualify and support the statement.",
                },
                {
                    "find": "already supported [A1]",
                    "replace": "already supported [A1]",
                    "reason": "No change required.",
                },
            ]
        }
    )
    recorder = ablation.GuardrailRecorder()
    recorder.attempts["report_review_task"] = [
        _attempt(failed, passed=False),
        _attempt(successful, passed=True),
    ]

    path = ablation.persist_successful_reviewer_plan(tmp_path, recorder, 1)

    assert path == tmp_path / "reviewer_correction_plan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["corrections"] == [json.loads(successful)["corrections"][0]]
    assert failed not in path.read_text(encoding="utf-8")


def test_persist_successful_reviewer_plan_rejects_count_mismatch(
    tmp_path: Path,
) -> None:
    plan = json.dumps(
        {
            "corrections": [
                {"find": "old", "replace": "new", "reason": "Correct it."}
            ]
        }
    )
    recorder = ablation.GuardrailRecorder()
    recorder.attempts["report_review_task"] = [_attempt(plan, passed=True)]

    with pytest.raises(RuntimeError, match="count mismatch"):
        ablation.persist_successful_reviewer_plan(tmp_path, recorder, 2)


def test_persist_successful_reviewer_plan_distinguishes_no_plan_from_empty_plan(
    tmp_path: Path,
) -> None:
    recorder = ablation.GuardrailRecorder()

    assert ablation.persist_successful_reviewer_plan(tmp_path, recorder, 0) is None
    with pytest.raises(RuntimeError, match="without a persisted JSON plan"):
        ablation.persist_successful_reviewer_plan(tmp_path, recorder, 1)
