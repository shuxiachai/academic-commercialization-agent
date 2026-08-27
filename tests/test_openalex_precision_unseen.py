"""Zero-network seams for the frozen precision-v2 unseen preflight."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import openalex_precision_unseen as unseen


def test_dry_run_expands_exact_unseen_contract_without_live_authority():
    result = unseen.dry_run()

    assert result["fixture_sha256"] == unseen.EXPECTED_FIXTURE_SHA256
    assert result["correction_sha256"] == unseen.EXPECTED_CORRECTION_SHA256
    assert result["case_count"] == 8
    assert [case["case_id"] for case in result["cases"]] == [
        f"U{index:02d}" for index in range(1, 9)
    ]
    assert len({case["collection_sha256"] for case in result["cases"]}) == 8
    assert len({case["plan_sha256"] for case in result["cases"]}) == 8
    assert len({case["profile_sha256"] for case in result["cases"]}) == 8
    assert len({case["idempotency_key"] for case in result["cases"]}) == 8
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
        unseen.OpenAlexPrecisionUnseenError,
        match="fixture byte identity drifted",
    ):
        unseen.load_frozen_cases(fixture)


def test_correction_byte_drift_fails_before_case_expansion(tmp_path):
    correction = tmp_path / "drifted-correction.json"
    correction.write_bytes(unseen.DEFAULT_CORRECTION_PATH.read_bytes() + b" ")

    with pytest.raises(
        unseen.OpenAlexPrecisionUnseenError,
        match="correction byte identity drifted",
    ):
        unseen.load_frozen_cases(correction_path=correction)


def test_semantic_case_order_drift_is_rejected_even_with_matching_raw_hash(
    tmp_path,
):
    payload = json.loads(
        unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8")
    )
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

    with pytest.raises(ValueError, match="ordered U01 through U08"):
        unseen.load_frozen_cases(
            fixture,
            expected_fixture_sha256=fixture_hash,
        )


def test_correction_refuses_to_retarget_when_expected_phrases_drift(tmp_path):
    payload = json.loads(
        unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8")
    )
    payload["challenge_cases"][1]["profile"]["supporting_groups"][0][
        "phrases"
    ][0] = "different phrase"
    fixture = tmp_path / "retargeted.json"
    fixture.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    fixture_hash = unseen._sha256_bytes(fixture.read_bytes())  # noqa: SLF001
    correction_payload = json.loads(
        unseen.DEFAULT_CORRECTION_PATH.read_text(encoding="utf-8")
    )
    correction_payload["source_fixture_sha256"] = fixture_hash
    correction = tmp_path / "retargeted-correction.json"
    correction.write_text(
        json.dumps(correction_payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    correction_hash = unseen._sha256_bytes(  # noqa: SLF001
        correction.read_bytes()
    )

    with pytest.raises(
        unseen.OpenAlexPrecisionUnseenError,
        match="correction target phrases drifted",
    ):
        unseen.load_frozen_cases(
            fixture,
            expected_fixture_sha256=fixture_hash,
            correction_path=correction,
            expected_correction_sha256=correction_hash,
        )


def test_preflight_source_does_not_import_provider_or_live_runner():
    source = Path("openalex_precision_unseen.py").read_text(encoding="utf-8")

    assert "anonymous_openalex_search" not in source
    assert "evidence_gap_openalex_live" not in source
    assert "execute_gap_plan" not in source
