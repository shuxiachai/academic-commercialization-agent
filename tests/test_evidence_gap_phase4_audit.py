"""Frozen Phase 4 domain-adapter preflight and isolation tests."""

from __future__ import annotations

import inspect
import json

import pytest
from pydantic import ValidationError

from evidence_gap_phase4_audit import (
    DEFAULT_MANIFEST_PATH,
    EXPECTED_FIXTURE_SHA256,
    Phase4AuditError,
    Phase4Manifest,
    dry_run,
    load_frozen_cases,
)


def test_dry_run_exposes_all_frozen_identities_without_network_adapter_import():
    result = dry_run()

    assert result["mode"] == "phase4_domain_adapter_dry_run"
    assert result["production_connected"] is False
    assert result["report_workflow_connected"] is False
    assert result["real_network_calls_performed"] is False
    assert result["fixture_sha256"] == EXPECTED_FIXTURE_SHA256
    assert result["case_count"] == 8
    assert result["maximum_request_count"] == 8
    assert [case["case_id"] for case in result["cases"]] == [
        "D01",
        "D02",
        "D03",
        "D04",
        "D05",
        "D06",
        "D07",
        "D08",
    ]
    assert [case["provider"] for case in result["cases"]] == [
        "openalex",
        "openalex",
        "openalex",
        "openalex",
        "lens",
        "lens",
        "lens",
        "lens",
    ]
    assert all(len(case["idempotency_key"]) == 64 for case in result["cases"])


def test_raw_fixture_identity_drift_fails_before_manifest_validation(
    tmp_path,
    monkeypatch,
):
    changed = tmp_path / "phase4-changed.json"
    changed.write_bytes(DEFAULT_MANIFEST_PATH.read_bytes() + b"\n")

    def forbidden_validation(*args, **kwargs):
        raise AssertionError(f"manifest parsing must not run: {args!r} {kwargs!r}")

    monkeypatch.setattr(Phase4Manifest, "model_validate_json", forbidden_validation)

    with pytest.raises(Phase4AuditError, match="fixture byte identity drifted"):
        load_frozen_cases(changed)


def test_manifest_rejects_unknown_fields_and_provider_tool_drift():
    payload = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    payload["unregistered_override"] = True
    with pytest.raises(ValidationError):
        Phase4Manifest.model_validate(payload)

    payload.pop("unregistered_override")
    payload["cases"][0]["tool"] = "patent_search"
    with pytest.raises(ValidationError, match="must remain bound"):
        Phase4Manifest.model_validate(payload)


def test_expanded_cases_have_one_validated_call_bound_to_frozen_provider():
    _, cases = load_frozen_cases()

    for case in cases:
        assert case.plan.decision == "search"
        assert len(case.plan.calls) == 1
        assert case.plan.calls[0].tool == case.spec.tool
        assert case.plan.calls[0].query == case.spec.query
        assert case.plan.calls[0].result_limit == 5
        assert len(case.collection_sha256) == 64
        assert len(case.plan_sha256) == 64


def test_phase4_executor_and_domain_adapters_remain_disconnected_from_worker():
    from academic_agent import pipeline_worker

    source = inspect.getsource(pipeline_worker)
    assert "academic_agent.evidence_gap_execution" not in source
    assert "domain_evidence_search" not in source
    assert "OpenAlexEvidenceSearchAdapter" not in source
    assert "LensEvidenceSearchAdapter" not in source
    assert "execute_gap_plan" not in source
    assert "evidence_gap_phase4_live" not in source
    assert "evidence_gap_phase4_review" not in source
