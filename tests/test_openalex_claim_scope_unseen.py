"""Zero-network seams for the frozen claim-scope v3 unseen preflight."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import openalex_claim_scope_unseen as unseen


def test_dry_run_expands_the_exact_unseen_contract_without_live_authority():
    result = unseen.dry_run()

    assert result["fixture_sha256"] == unseen.EXPECTED_FIXTURE_SHA256
    assert result["case_count"] == 8
    assert [case["case_id"] for case in result["cases"]] == [
        f"V{index:02d}" for index in range(1, 9)
    ]
    assert len({case["collection_sha256"] for case in result["cases"]}) == 8
    assert len({case["plan_sha256"] for case in result["cases"]}) == 8
    assert len({case["profile_sha256"] for case in result["cases"]}) == 8
    assert len({case["idempotency_key"] for case in result["cases"]}) == 8
    assert {case["result_limit"] for case in result["cases"]} == {8}
    assert result["request_contract"] == {
        "result_limit": 8,
        "filter": "has_abstract:true",
        "aboutness_fields": ["topics", "keywords"],
        "redirects": False,
        "internal_retries": False,
    }
    assert result["development_observation"]["source_truth_state"] == (
        "not_evaluated"
    )
    assert result["development_observation"]["precision_v2_abstains"] == 18
    assert result["source_value_gates"] == {
        "accepted_case_count_min": 6,
        "novel_relevant_case_count_min": 6,
        "wrong_source_rate_max": 0.05,
        "all_attempted_sources_reviewed": True,
        "substantive_generative_ai_allowed": False,
    }
    assert result["real_network_calls_performed"] is False
    assert result["live_provider_requests_authorized"] is False
    assert result["production_connected"] is False
    assert result["report_workflow_connected"] is False


def test_fixture_byte_drift_fails_before_case_expansion(tmp_path):
    fixture = tmp_path / "drifted.json"
    fixture.write_bytes(unseen.DEFAULT_FIXTURE_PATH.read_bytes() + b" ")

    with pytest.raises(
        unseen.OpenAlexClaimScopePreflightError,
        match="fixture byte identity drifted",
    ):
        unseen.load_frozen_cases(fixture)


def test_semantic_case_order_drift_is_rejected_even_with_matching_raw_hash(
    tmp_path,
):
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

    with pytest.raises(ValueError, match="ordered V01 through V08"):
        unseen.load_frozen_cases(
            fixture,
            expected_fixture_sha256=fixture_hash,
        )


def test_request_contract_cannot_silently_drop_the_abstract_filter(tmp_path):
    payload = json.loads(unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["request_contract"]["filter"] = ""
    fixture = tmp_path / "unfiltered.json"
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


def test_preflight_source_imports_neither_provider_nor_live_runner():
    source = Path("openalex_claim_scope_unseen.py").read_text(encoding="utf-8")

    assert "openalex_claim_scope_search" not in source
    assert "anonymous_openalex_search" not in source
    assert "execute_gap_plan" not in source
    assert "urllib" not in source
