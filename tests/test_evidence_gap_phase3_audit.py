"""Frozen Phase-3 provider pilot and public artifact seam tests."""

from __future__ import annotations

import csv
import inspect
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import evidence_gap_phase3_audit as phase3
from academic_agent.tools.evidence_search import (
    ProviderResultRejection,
    ToolAdapterFailure,
    ToolAdapterResponse,
    ToolEvidenceCandidate,
    ToolProviderUsage,
)
from evidence_gap_phase3_audit import (
    DEFAULT_MANIFEST_PATH,
    Phase3AuditError,
    Phase3ExecutionArtifact,
    Phase3Manifest,
    Phase3ManifestArtifact,
    dry_run,
    execute_live_pilot,
    load_frozen_cases,
    write_artifacts,
)


class FixtureAdapter:
    """Offline adapter that returns one policy-valid row for every capability."""

    def __init__(self, *, credits: float = 1.0, reject_one_row: bool = False):
        self.calls = []
        self.credits = credits
        self.reject_one_row = reject_one_row

    def __call__(self, call):
        self.calls.append(call)
        request_number = len(self.calls)
        if call.tool == "academic_search":
            url = f"https://openalex.org/W900000{request_number}"
        elif call.tool == "patent_search":
            url = (
                "https://patents.google.com/patent/"
                f"US202600000{request_number}A1"
            )
        elif call.tool == "market_search":
            url = (
                "https://www.reuters.com/technology/"
                f"phase3-market-{request_number}/"
            )
        elif "clinical" in call.query.casefold():
            url = f"https://clinicaltrials.gov/study/NCT9000000{request_number}"
        else:
            url = (
                "https://www.fda.gov/medical-devices/"
                f"phase3-regulatory-{request_number}"
            )
        candidate = ToolEvidenceCandidate(
            title=f"{call.query} validated evidence record",
            url=url,
            publisher="Frozen Provider Fixture",
            evidence_summary=(
                f"{call.query} is documented in this frozen provider response "
                "with enough topic detail for deterministic relevance checking."
            ),
            summary_source="search_snippet",
            provider_result_index=0,
        )
        rejections = ()
        result_count = 1
        if self.reject_one_row and request_number == 1:
            rejections = (
                ProviderResultRejection(
                    provider_result_index=1,
                    code="provider_result_not_object",
                    detail="provider result must be a JSON object",
                ),
            )
            result_count = 2
        request_id = f"tavily-fixture-{request_number}"
        return ToolAdapterResponse(
            tool=call.tool,
            idempotency_key=call.idempotency_key,
            candidates=(candidate,),
            search_cost_usd=self.credits * 0.008,
            provider_request_id=request_id,
            provider_usage=ToolProviderUsage(
                provider="tavily",
                request_id=request_id,
                result_count=result_count,
                credit_count=self.credits,
                usd_per_credit=0.008,
            ),
            provider_rejections=rejections,
        )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_dry_run_validates_five_frozen_identities_without_constructing_adapter(
    monkeypatch,
):
    def forbidden_adapter():
        raise AssertionError("dry-run must not construct a network adapter")

    monkeypatch.setattr(phase3, "TavilyEvidenceSearchAdapter", forbidden_adapter)

    result = dry_run()

    assert result["mode"] == "phase3_dry_run"
    assert result["case_count"] == 5
    assert result["maximum_request_count"] == 5
    assert result["production_connected"] is False
    assert result["real_network_calls_performed"] is False
    assert [case["case_id"] for case in result["cases"]] == [
        "L01",
        "L02",
        "L03",
        "L04",
        "L05",
    ]


def test_manifest_identity_drift_fails_before_any_adapter_is_needed(tmp_path):
    payload = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    payload["cases"][0]["topic"] += " changed"
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(Phase3AuditError, match="source collection identity drifted"):
        load_frozen_cases(changed)


def test_manifest_and_execution_schemas_reject_unknown_fields():
    payload = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    payload["unregistered_override"] = True
    with pytest.raises(ValidationError):
        Phase3Manifest.model_validate(payload)

    artifact = {
        "fixture_sha256": "a" * 64,
        "soft_stop_usd": 0.04,
        "request_count": 0,
        "credit_state": "known",
        "credit_count": 0,
        "cost_state": "known",
        "conservative_cost_usd": 0,
        "completed_case_count": 0,
        "stopped_reason": "completed",
        "cases": [],
        "unregistered_override": True,
    }
    with pytest.raises(ValidationError):
        Phase3ExecutionArtifact.model_validate(artifact)

    with pytest.raises(ValidationError):
        Phase3ManifestArtifact.model_validate(
            {
                "fixture_sha256": "a" * 64,
                "cases": [],
                "unregistered_override": True,
            }
        )


def test_live_fixture_reaches_all_artifact_seams_without_production_connection(
    tmp_path,
):
    adapter = FixtureAdapter(reject_one_row=True)
    output = tmp_path / "phase3-live-fixture"

    artifact = execute_live_pilot(
        output_dir=output,
        soft_stop_usd=0.04,
        adapter=adapter,
    )

    assert len(adapter.calls) == 5
    assert artifact.request_count == 5
    assert artifact.credit_state == "known"
    assert artifact.credit_count == 5
    assert artifact.cost_state == "known"
    assert artifact.conservative_cost_usd == pytest.approx(0.04)
    assert artifact.stopped_reason == "completed"
    assert artifact.review_state == "not_inspected"
    assert artifact.production_connected is False
    assert artifact.report_workflow_connected is False
    assert {path.name for path in output.iterdir()} == {
        "manifest.json",
        "execution.json",
        "candidates.csv",
        "review.csv",
    }

    execution = json.loads((output / "execution.json").read_text(encoding="utf-8"))
    first_call = execution["cases"][0]["audit"]["call_audits"][0]
    assert first_call["outbound_attempt_count"] == 1
    assert first_call["provider_usage"]["request_id"] == "tavily-fixture-1"
    assert first_call["raw_candidate_count"] == 2
    assert first_call["candidate_records"][0]["provider_result_index"] == 0
    assert first_call["provider_rejections"][0]["provider_result_index"] == 1
    assert first_call["latency_ms"] >= 0
    assert first_call["trace_id"]

    candidate_rows = _read_csv(output / "candidates.csv")
    assert len(candidate_rows) == 6
    assert {row["adapter_disposition"] for row in candidate_rows} == {
        "candidate",
        "provider_rejected",
    }
    assert all(
        row["local_disposition"] != "quarantined_accepted"
        or row["accepted_source_id"]
        for row in candidate_rows
    )
    review_rows = _read_csv(output / "review.csv")
    assert len(review_rows) == 5
    assert all(row["relevant"] == row["novel"] == "" for row in review_rows)

    _, prepared = load_frozen_cases()
    with pytest.raises(FileExistsError):
        write_artifacts(prepared, artifact, output)


def test_retryable_failure_stops_after_one_uninspectable_attempt(tmp_path):
    attempts = 0

    def failing_adapter(call):
        nonlocal attempts
        attempts += 1
        raise ToolAdapterFailure(
            f"temporary failure for {call.tool}",
            retryable=True,
            failure_type="provider_timeout",
            search_cost_usd=None,
        )

    artifact = execute_live_pilot(
        output_dir=tmp_path / "uninspectable",
        soft_stop_usd=0.04,
        adapter=failing_adapter,
    )

    assert attempts == 1
    assert artifact.request_count == 1
    assert artifact.cases[0].audit.outbound_attempt_limit == 1
    assert artifact.credit_state == "uninspectable"
    assert artifact.credit_count is None
    assert artifact.cost_state == "uninspectable"
    assert artifact.conservative_cost_usd is None
    assert artifact.stopped_reason == "cost_uninspectable"


def test_observed_cost_stops_before_a_second_request(tmp_path):
    adapter = FixtureAdapter(credits=5)

    artifact = execute_live_pilot(
        output_dir=tmp_path / "soft-stop",
        soft_stop_usd=0.04,
        adapter=adapter,
    )

    assert len(adapter.calls) == 1
    assert artifact.request_count == 1
    assert artifact.credit_count == 5
    assert artifact.conservative_cost_usd == pytest.approx(0.04)
    assert artifact.stopped_reason == "soft_stop"


def test_invalid_budget_existing_output_and_missing_key_fail_before_request(
    tmp_path,
    monkeypatch,
):
    adapter = FixtureAdapter()
    with pytest.raises(Phase3AuditError, match="soft stop"):
        execute_live_pilot(
            output_dir=tmp_path / "invalid-budget",
            soft_stop_usd=0.039,
            adapter=adapter,
        )
    assert adapter.calls == []

    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        execute_live_pilot(
            output_dir=existing,
            soft_stop_usd=0.04,
            adapter=adapter,
        )
    assert adapter.calls == []

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    missing_key_output = tmp_path / "missing-key"
    with pytest.raises(ValueError, match="TAVILY_API_KEY"):
        execute_live_pilot(
            output_dir=missing_key_output,
            soft_stop_usd=0.04,
        )
    assert not missing_key_output.exists()


def test_phase3_executor_and_adapter_remain_disconnected_from_worker():
    from academic_agent import pipeline_worker

    source = inspect.getsource(pipeline_worker)
    assert "academic_agent.evidence_gap_execution" not in source
    assert "tavily_evidence_search" not in source
    assert "execute_gap_plan" not in source
