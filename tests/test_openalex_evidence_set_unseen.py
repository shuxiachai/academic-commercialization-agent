"""Zero-network seams for the frozen evidence-set v5 unseen preflight."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import openalex_evidence_set_unseen as unseen


def test_dry_run_expands_all_frozen_identities_without_live_authority():
    result = unseen.dry_run()

    assert result["fixture_sha256"] == unseen.EXPECTED_FIXTURE_SHA256
    assert result["case_count"] == 8
    assert [case["case_id"] for case in result["cases"]] == [
        f"X{index:02d}" for index in range(1, 9)
    ]
    for key in (
        "collection_sha256",
        "plan_sha256",
        "profile_sha256",
        "case_contract_sha256",
        "idempotency_key",
    ):
        assert len({case[key] for case in result["cases"]}) == 8
    assert {case["result_limit"] for case in result["cases"]} == {8}
    assert result["maximum_search_request_count"] == 8
    assert result["maximum_judge_call_count"] == 16
    assert result["request_contract"] == {
        "result_limit": 8,
        "filter": "has_abstract:true",
        "aboutness_fields": ["topics", "keywords"],
        "aboutness_admissible_for_selection": False,
        "redirects": False,
        "internal_retries": False,
        "supplementary_fetches": False,
    }
    judge = result["semantic_judge_contract"]
    assert judge["provider"] == "deepseek"
    assert judge["requested_model"] == "deepseek-chat"
    assert judge["passes_per_case"] == 2
    assert judge["temperature"] == 0.0
    assert judge["allowed_candidate_fields"] == [
        "candidate_sha256",
        "title",
        "abstract",
    ]
    assert judge["maximum_selected_sources_per_case"] == 3
    assert result["development_observation"]["case_ids"] == [
        f"W{index:02d}" for index in range(1, 9)
    ]
    assert result["development_observation"]["reuse_for_v5_validation"] is False
    assert result["development_qualification_gates"] == {
        "candidate_disposition_agreement_min": 0.9,
        "semantic_link_rows_retained_min": 4,
        "relevant_novel_case_count_min": 6,
        "selected_directly_irrelevant_count_max": 1,
        "all_decisions_persisted": True,
    }
    assert result["unseen_value_gates"]["selected_wrong_source_rate_max"] == 0.05
    assert result["unseen_value_gates"]["all_provider_rows_reviewed"] is True
    assert result["real_network_calls_performed"] is False
    assert result["real_model_calls_performed"] is False
    assert result["private_labels_opened"] is False
    assert result["live_provider_requests_authorized"] is False
    assert result["live_model_calls_authorized"] is False
    assert result["production_connected"] is False
    assert result["report_workflow_connected"] is False
    assert result["planner_trigger_connected"] is False


def test_fixture_byte_drift_fails_before_case_expansion(tmp_path, monkeypatch):
    fixture = tmp_path / "drifted.json"
    fixture.write_bytes(unseen.DEFAULT_FIXTURE_PATH.read_bytes() + b" ")

    def must_not_expand(*args, **kwargs):
        raise AssertionError("case expansion ran before the raw hash check")

    monkeypatch.setattr(unseen, "build_case", must_not_expand)
    with pytest.raises(
        unseen.OpenAlexEvidenceSetPreflightError,
        match="fixture byte identity drifted",
    ):
        unseen.load_frozen_cases(fixture)


def test_case_order_drift_is_rejected_with_a_matching_test_hash(tmp_path):
    payload = json.loads(unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["challenge_cases"][0], payload["challenge_cases"][1] = (
        payload["challenge_cases"][1],
        payload["challenge_cases"][0],
    )
    fixture = tmp_path / "reordered.json"
    fixture.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    fixture_hash = unseen._sha256_bytes(fixture.read_bytes())  # noqa: SLF001

    with pytest.raises(ValueError, match="ordered X01 through X08"):
        unseen.load_frozen_cases(
            fixture,
            expected_fixture_sha256=fixture_hash,
        )


def test_hidden_field_or_judge_surface_drift_fails_closed(tmp_path):
    payload = json.loads(unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["semantic_judge_contract"]["allowed_candidate_fields"].append("url")
    fixture = tmp_path / "judge-leak.json"
    fixture.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    fixture_hash = unseen._sha256_bytes(fixture.read_bytes())  # noqa: SLF001

    with pytest.raises(ValueError, match="judge candidate fields drifted"):
        unseen.load_frozen_cases(
            fixture,
            expected_fixture_sha256=fixture_hash,
        )


def test_role_profile_drift_changes_only_role_bound_identities(tmp_path):
    payload = json.loads(unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["challenge_cases"][0]["role_profile"]["scope_roles"][0][
        "description"
    ] += " under saline operating conditions"
    fixture = tmp_path / "role-drift.json"
    fixture.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    fixture_hash = unseen._sha256_bytes(fixture.read_bytes())  # noqa: SLF001

    original = unseen.dry_run()
    drifted = unseen.dry_run(
        fixture,
        expected_fixture_sha256=fixture_hash,
    )

    assert drifted["cases"][0]["profile_sha256"] != (
        original["cases"][0]["profile_sha256"]
    )
    assert drifted["cases"][0]["case_contract_sha256"] != (
        original["cases"][0]["case_contract_sha256"]
    )
    assert drifted["cases"][0]["plan_sha256"] == (
        original["cases"][0]["plan_sha256"]
    )


def test_request_and_judge_caps_remain_one_search_and_two_passes_per_case(
    tmp_path,
):
    payload = json.loads(unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["maximum_live_judge_calls"] = 17
    fixture = tmp_path / "extra-call.json"
    fixture.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    fixture_hash = unseen._sha256_bytes(fixture.read_bytes())  # noqa: SLF001

    with pytest.raises(ValueError):
        unseen.load_frozen_cases(
            fixture,
            expected_fixture_sha256=fixture_hash,
        )


def test_preflight_imports_neither_provider_model_nor_execution_client():
    source = Path("openalex_evidence_set_unseen.py").read_text(encoding="utf-8")

    assert "anonymous_openalex_search" not in source
    assert "openalex_claim_scope_search" not in source
    assert "execute_gap_plan" not in source
    assert "litellm" not in source
    assert "crewai" not in source
    assert "urllib" not in source
