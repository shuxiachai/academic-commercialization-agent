"""Zero-network seams for the frozen role-slot consensus v6 preflight."""

from __future__ import annotations

from datetime import date
import json
import socket
from pathlib import Path

import pytest

import academic_agent.evidence as evidence_module
import openalex_role_slot_unseen as unseen


def test_development_dry_run_expands_all_identities_without_live_authority():
    result = unseen.dry_run("development")

    assert result["fixture_sha256"] == unseen.EXPECTED_FIXTURE_SHA256
    assert result["case_count"] == 8
    assert [item["case_id"] for item in result["cases"]] == [
        f"Y{index:02d}" for index in range(1, 9)
    ]
    for key in (
        "case_spec_sha256",
        "collection_sha256",
        "plan_sha256",
        "profile_sha256",
        "case_contract_sha256",
        "provider_idempotency_key",
    ):
        assert len({item[key] for item in result["cases"]}) == 8
    template_ids = [
        identity
        for item in result["cases"]
        for identity in item["judge_request_template_sha256s"]
    ]
    assert len(template_ids) == 24
    assert len(set(template_ids)) == 24
    assert {item["result_limit"] for item in result["cases"]} == {8}
    assert result["maximum_search_request_count"] == 8
    assert result["maximum_judge_call_count"] == 24
    assert result["provider_contract"] == {
        "provider": "anonymous_openalex",
        "requests_per_case": 1,
        "result_limit": 8,
        "require_abstract": True,
        "allow_redirects": False,
        "allow_retries": False,
    }
    assert result["judge_contract"] == {
        "provider": "qwen",
        "model": "qwen3.5-plus",
        "passes_per_case": 3,
        "candidate_orders": [
            "provider_order",
            "reverse_provider_order",
            "candidate_sha256_order",
        ],
        "temperature": 0.0,
        "allow_retries": False,
        "allow_repair": False,
        "allow_fallback": False,
        "minimum_verified_passes_per_role": 2,
    }
    assert result["real_network_calls_performed"] is False
    assert result["real_model_calls_performed"] is False
    assert result["private_labels_opened"] is False
    assert result["live_provider_requests_authorized"] is False
    assert result["live_model_calls_authorized"] is False
    assert result["production_connected"] is False
    assert result["report_workflow_connected"] is False
    assert result["planner_trigger_connected"] is False


def test_frozen_preflight_is_valid_on_the_earlier_utc_calendar_date(monkeypatch):
    """A Sydney freeze must not become future-dated on the UTC CI runner."""

    class FrozenUtcDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 8, 31)

    # Patch the validator clock, not the preflight constant.  This recreates
    # the client boundary that failed after local Sydney tests had passed.
    monkeypatch.setattr(evidence_module, "date", FrozenUtcDate)

    result = unseen.dry_run("development")

    assert result["case_count"] == 8


def test_unseen_cohort_has_distinct_frozen_identities_but_no_live_authority():
    development = unseen.dry_run("development")
    challenge = unseen.dry_run("unseen")

    assert [item["case_id"] for item in challenge["cases"]] == [
        f"Z{index:02d}" for index in range(1, 9)
    ]
    assert {
        item["case_contract_sha256"] for item in development["cases"]
    }.isdisjoint(
        item["case_contract_sha256"] for item in challenge["cases"]
    )
    assert challenge["real_network_calls_performed"] is False
    assert challenge["real_model_calls_performed"] is False
    assert challenge["live_provider_requests_authorized"] is False
    assert challenge["live_model_calls_authorized"] is False


def test_fixture_byte_drift_fails_before_case_expansion(tmp_path, monkeypatch):
    fixture = tmp_path / "drifted.json"
    fixture.write_bytes(unseen.DEFAULT_FIXTURE_PATH.read_bytes() + b" ")

    def must_not_expand(*args, **kwargs):
        raise AssertionError("case expansion ran before the raw hash check")

    monkeypatch.setattr(unseen, "build_case", must_not_expand)
    with pytest.raises(
        unseen.OpenAlexRoleSlotPreflightError,
        match="fixture byte identity drifted",
    ):
        unseen.load_frozen_cases("development", fixture)


def test_case_order_drift_is_rejected_with_a_matching_test_hash(tmp_path):
    payload = json.loads(unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["development_cases"][0], payload["development_cases"][1] = (
        payload["development_cases"][1],
        payload["development_cases"][0],
    )
    fixture = tmp_path / "reordered.json"
    fixture.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    fixture_hash = unseen._sha256_bytes(fixture.read_bytes())  # noqa: SLF001

    with pytest.raises(ValueError, match="Y01 through Y08"):
        unseen.load_frozen_cases(
            "development",
            fixture,
            expected_fixture_sha256=fixture_hash,
        )


def test_judge_order_or_call_count_drift_fails_closed(tmp_path):
    payload = json.loads(unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["judge_contract"]["candidate_orders"][2] = "provider_order"
    fixture = tmp_path / "judge-drift.json"
    fixture.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    fixture_hash = unseen._sha256_bytes(fixture.read_bytes())  # noqa: SLF001

    with pytest.raises(ValueError, match="judge pass orders drifted"):
        unseen.load_frozen_cases(
            "development",
            fixture,
            expected_fixture_sha256=fixture_hash,
        )


def test_role_drift_changes_role_bound_identities_but_not_provider_plan(tmp_path):
    payload = json.loads(unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["development_cases"][0]["roles"]["scope"][0][
        "description"
    ] += " under documented end-of-life conditions"
    fixture = tmp_path / "role-drift.json"
    fixture.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    fixture_hash = unseen._sha256_bytes(fixture.read_bytes())  # noqa: SLF001

    original = unseen.dry_run("development")
    drifted = unseen.dry_run(
        "development",
        fixture,
        expected_fixture_sha256=fixture_hash,
    )

    assert drifted["cases"][0]["profile_sha256"] != (
        original["cases"][0]["profile_sha256"]
    )
    assert drifted["cases"][0]["case_contract_sha256"] != (
        original["cases"][0]["case_contract_sha256"]
    )
    assert drifted["cases"][0]["judge_request_template_sha256s"] != (
        original["cases"][0]["judge_request_template_sha256s"]
    )
    assert drifted["cases"][0]["plan_sha256"] == (
        original["cases"][0]["plan_sha256"]
    )


def test_dry_run_opens_no_socket_even_when_socket_creation_is_blocked(monkeypatch):
    def block_socket(*args, **kwargs):
        raise AssertionError("preflight attempted to create a socket")

    monkeypatch.setattr(socket, "socket", block_socket)

    result = unseen.dry_run("development")

    assert result["case_count"] == 8
    assert result["real_network_calls_performed"] is False


def test_preflight_imports_no_provider_model_or_execution_client():
    source = Path("openalex_role_slot_unseen.py").read_text(encoding="utf-8")

    assert "anonymous_openalex_search" not in source
    assert "qwen_evidence_judge" not in source
    assert "execute_gap_plan" not in source
    assert "litellm" not in source
    assert "crewai" not in source
    assert "urllib" not in source
