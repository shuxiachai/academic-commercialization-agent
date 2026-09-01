"""Zero-network seams for the frozen role-directed retrieval v7 preflight."""

from __future__ import annotations

import json
from pathlib import Path
import socket

import pytest

import openalex_role_directed_unseen as unseen


def _write_fixture(tmp_path: Path, payload: dict[str, object]) -> tuple[Path, str]:
    fixture = tmp_path / "challenge.json"
    fixture.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return fixture, unseen._sha256_bytes(fixture.read_bytes())  # noqa: SLF001


def test_development_dry_run_expands_two_unique_calls_per_case_without_authority():
    result = unseen.dry_run("development")

    assert result["fixture_sha256"] == unseen.EXPECTED_FIXTURE_SHA256
    assert result["case_count"] == 8
    assert [item["case_id"] for item in result["cases"]] == [
        f"AA{index:02d}" for index in range(1, 9)
    ]
    for key in (
        "case_spec_sha256",
        "collection_sha256",
        "plan_sha256",
        "profile_sha256",
        "case_contract_sha256",
    ):
        assert len({item[key] for item in result["cases"]}) == 8

    lanes = [lane for case in result["cases"] for lane in case["lanes"]]
    assert len(lanes) == 16
    assert len({lane["idempotency_key"] for lane in lanes}) == 16
    assert len({lane["lane_contract_sha256"] for lane in lanes}) == 16
    assert {lane["result_limit"] for lane in lanes} == {6}
    assert [
        tuple(lane["lane_id"] for lane in case["lanes"])
        for case in result["cases"]
    ] == [("technology_scope", "technology_evidence")] * 8

    assert result["maximum_search_request_count"] == 16
    assert result["maximum_provider_row_count"] == 96
    assert result["maximum_model_call_count"] == 0
    assert result["provider_contract"] == {
        "provider": "anonymous_openalex",
        "requests_per_case": 2,
        "result_limit_per_request": 6,
        "require_abstract": True,
        "allow_redirects": False,
        "allow_retries": False,
    }
    assert result["portfolio_contract"] == {
        "lane_order": ["technology_scope", "technology_evidence"],
        "deduplicate_by": ["normalized_doi", "canonical_openalex_url"],
        "preserve_lane_memberships": True,
        "preserve_provider_rank": True,
        "maximum_unique_candidates_per_case": 12,
        "maximum_cover_sources_per_case": 3,
        "semantic_filter_before_human_qualification": False,
    }
    assert result["qualification_contract"] == {
        "minimum_cases_with_relevant_novel_candidate": 6,
        "minimum_human_coverable_cases": 6,
        "minimum_candidate_pool_precision": 0.25,
        "minimum_cases_with_unique_evidence_lane_value": 4,
        "minimum_coverability_gain_over_scope_lane": 2,
    }
    for flag in (
        "production_connected",
        "report_workflow_connected",
        "planner_trigger_connected",
        "recovery_connected",
        "real_network_calls_performed",
        "real_model_calls_performed",
        "private_labels_opened",
        "human_qualification_performed",
        "live_provider_requests_authorized",
        "live_model_calls_authorized",
    ):
        assert result[flag] is False


def test_every_frozen_lane_reaches_the_serialized_dry_run_boundary():
    """A valid plan is useless if one lane disappears before the client seam."""

    payload = json.loads(unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    result = unseen.dry_run("development")

    expected = [
        {
            "case_id": case["case_id"],
            "lane_id": lane["lane_id"],
            "query": lane["query"],
            "target_role_ids": lane["target_role_ids"],
        }
        for case in payload["development_cases"]
        for lane in case["lanes"]
    ]
    observed = [
        {
            "case_id": case["case_id"],
            "lane_id": lane["lane_id"],
            "query": lane["query"],
            "target_role_ids": lane["target_role_ids"],
        }
        for case in result["cases"]
        for lane in case["lanes"]
    ]

    assert observed == expected
    assert all(
        len(lane["idempotency_key"]) == 64
        and len(lane["lane_contract_sha256"]) == 64
        for case in result["cases"]
        for lane in case["lanes"]
    )


def test_unseen_cohort_has_distinct_identities_and_zero_live_authority():
    development = unseen.dry_run("development")
    challenge = unseen.dry_run("unseen")

    assert [item["case_id"] for item in challenge["cases"]] == [
        f"AB{index:02d}" for index in range(1, 9)
    ]
    assert {
        item["case_contract_sha256"] for item in development["cases"]
    }.isdisjoint(item["case_contract_sha256"] for item in challenge["cases"])
    assert {
        lane["idempotency_key"]
        for case in development["cases"]
        for lane in case["lanes"]
    }.isdisjoint(
        lane["idempotency_key"]
        for case in challenge["cases"]
        for lane in case["lanes"]
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
        unseen.OpenAlexRoleDirectedPreflightError,
        match="fixture byte identity drifted",
    ):
        unseen.load_frozen_cases("development", fixture)


def test_case_order_drift_is_rejected_with_a_matching_test_hash(tmp_path):
    payload = json.loads(unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["development_cases"][0], payload["development_cases"][1] = (
        payload["development_cases"][1],
        payload["development_cases"][0],
    )
    fixture, fixture_hash = _write_fixture(tmp_path, payload)

    with pytest.raises(ValueError, match="AA01 through AA08"):
        unseen.load_frozen_cases(
            "development",
            fixture,
            expected_fixture_sha256=fixture_hash,
        )


def test_lane_order_and_role_binding_drift_fail_closed(tmp_path):
    payload = json.loads(unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["development_cases"][0]["lanes"].reverse()
    fixture, fixture_hash = _write_fixture(tmp_path, payload)

    with pytest.raises(ValueError, match="case lanes must remain"):
        unseen.load_frozen_cases(
            "development",
            fixture,
            expected_fixture_sha256=fixture_hash,
        )

    payload = json.loads(unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["development_cases"][0]["lanes"][0]["target_role_ids"] = [
        "electrochemical_phosphorus_recovery",
        "magnesium_air_cell",
        "struvite_product",
    ]
    fixture, fixture_hash = _write_fixture(tmp_path, payload)

    with pytest.raises(ValueError, match="technology_scope must target a scope role"):
        unseen.load_frozen_cases(
            "development",
            fixture,
            expected_fixture_sha256=fixture_hash,
        )


def test_query_drift_changes_only_query_bound_identities(tmp_path):
    payload = json.loads(unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["development_cases"][0]["lanes"][1]["query"] += " validation"
    fixture, fixture_hash = _write_fixture(tmp_path, payload)

    original = unseen.dry_run("development")
    drifted = unseen.dry_run(
        "development",
        fixture,
        expected_fixture_sha256=fixture_hash,
    )
    original_case = original["cases"][0]
    drifted_case = drifted["cases"][0]

    assert drifted_case["collection_sha256"] == original_case["collection_sha256"]
    assert drifted_case["profile_sha256"] == original_case["profile_sha256"]
    assert drifted_case["case_spec_sha256"] != original_case["case_spec_sha256"]
    assert drifted_case["plan_sha256"] != original_case["plan_sha256"]
    assert (
        drifted_case["case_contract_sha256"]
        != original_case["case_contract_sha256"]
    )
    assert (
        drifted_case["lanes"][0]["idempotency_key"]
        == original_case["lanes"][0]["idempotency_key"]
    )
    assert (
        drifted_case["lanes"][0]["lane_contract_sha256"]
        == original_case["lanes"][0]["lane_contract_sha256"]
    )
    assert (
        drifted_case["lanes"][1]["idempotency_key"]
        != original_case["lanes"][1]["idempotency_key"]
    )
    assert (
        drifted_case["lanes"][1]["lane_contract_sha256"]
        != original_case["lanes"][1]["lane_contract_sha256"]
    )


def test_role_drift_changes_role_bound_identities_but_not_search_plan(tmp_path):
    payload = json.loads(unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["development_cases"][0]["roles"]["scope"][0][
        "description"
    ] += " under documented plant operating conditions"
    fixture, fixture_hash = _write_fixture(tmp_path, payload)

    original = unseen.dry_run("development")
    drifted = unseen.dry_run(
        "development",
        fixture,
        expected_fixture_sha256=fixture_hash,
    )
    original_case = original["cases"][0]
    drifted_case = drifted["cases"][0]

    assert drifted_case["plan_sha256"] == original_case["plan_sha256"]
    assert drifted_case["profile_sha256"] != original_case["profile_sha256"]
    assert (
        drifted_case["case_contract_sha256"]
        != original_case["case_contract_sha256"]
    )
    assert [
        lane["idempotency_key"] for lane in drifted_case["lanes"]
    ] == [lane["idempotency_key"] for lane in original_case["lanes"]]
    assert [
        lane["lane_contract_sha256"] for lane in drifted_case["lanes"]
    ] != [lane["lane_contract_sha256"] for lane in original_case["lanes"]]


def test_dry_run_opens_no_socket_even_when_socket_creation_is_blocked(monkeypatch):
    def block_socket(*args, **kwargs):
        raise AssertionError("preflight attempted to create a socket")

    monkeypatch.setattr(socket, "socket", block_socket)

    result = unseen.dry_run("development")

    assert result["case_count"] == 8
    assert result["real_network_calls_performed"] is False


def test_preflight_imports_no_provider_model_or_execution_client():
    source = Path("openalex_role_directed_unseen.py").read_text(encoding="utf-8")

    for forbidden in (
        "anonymous_openalex_search",
        "OpenAlexEvidenceSearchAdapter",
        "execute_gap_plan",
        "qwen",
        "litellm",
        "crewai",
        "urllib",
    ):
        assert forbidden not in source
