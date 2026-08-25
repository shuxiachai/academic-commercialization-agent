"""Frozen Phase-2 Tool Calling challenge and artifact-boundary tests."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from evidence_gap_phase2_audit import (
    Phase2AuditError,
    Phase2Challenge,
    run_challenge,
    write_audit_artifacts,
)


_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE = _ROOT / "tests/fixtures/evidence_gap_phase2_challenge.json"


def test_frozen_phase2_challenge_passes_exactly_at_the_audit_seam():
    result = run_challenge(_FIXTURE)

    assert result["status"] == "passed"
    assert result["case_count"] == 14
    assert result["passed_case_count"] == 14
    assert result["deterministic_replay_passed_count"] == 14
    assert result["production_connected"] is False
    assert result["real_network_calls_performed"] is False
    assert result["maximum_case_attempt_count"] == 2
    assert result["unexpected_accepted_source_count"] == 0

    # Telemetry must reach the result artifact, not merely exist inside the
    # executor model. This seam assertion caught earlier client-field drops.
    for case in result["cases"]:
        assert case["deterministic_replay"] == "passed"
        for call in case["audit"]["call_audits"]:
            assert call["latency_ms"] >= 0
            assert call["trace_id"]
            assert call["query_sha256"]
            assert "search_cost_usd" in call
            assert "rejections" in call


def test_phase2_executor_is_not_connected_to_the_production_worker():
    from academic_agent import pipeline_worker

    source = inspect.getsource(pipeline_worker)
    assert "academic_agent.evidence_gap_execution" not in source
    assert "execute_gap_plan" not in source


def test_frozen_answer_drift_fails_instead_of_rewriting_the_baseline(tmp_path):
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    payload["cases"][0]["expected"]["accepted_count"] = 0
    drifted = tmp_path / "drifted.json"
    drifted.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        Phase2AuditError,
        match="C01-valid-academic: observed disposition differs",
    ):
        run_challenge(drifted)


def test_fixture_schema_rejects_unregistered_case_fields():
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    payload["cases"][0]["unregistered_override"] = True

    with pytest.raises(ValidationError):
        Phase2Challenge.model_validate(payload)


def test_audit_artifacts_are_write_once_and_keep_the_boundary_fields(tmp_path):
    result = run_challenge(_FIXTURE)
    output = tmp_path / "phase2-result"

    write_audit_artifacts(result, output)

    summary = json.loads(
        (output / "summary.json").read_text(encoding="utf-8")
    )
    csv_text = (output / "cases.csv").read_text(encoding="utf-8")
    assert summary["fixture_sha256"] == result["fixture_sha256"]
    assert summary["case_count"] == 14
    assert "outbound_attempt_count" in csv_text
    assert "C14-input-mutation-quarantine" in csv_text

    with pytest.raises(FileExistsError):
        write_audit_artifacts(result, output)
