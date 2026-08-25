"""Contracts for precision-first official-source title recovery.

The important assertions sit at two seams: the frozen challenge must persist
every baseline/candidate decision, and `_web_source` must place the recovered
label on the final EvidenceSource rather than merely calculating it in a helper.
"""

from __future__ import annotations

import csv
import json
import socket
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

import regulator_title_audit
import regulator_title_recovery_candidate
from academic_agent.evidence import EvidenceSource
from academic_agent.source_pipeline import SourceCollection, _web_source
from academic_agent.source_title_recovery import recover_official_source_title


_ROOT = Path(__file__).resolve().parent.parent
_CHALLENGE = (
    _ROOT
    / "evals"
    / "regulator_title_quality"
    / "recovery-challenge-v1.json"
)
_CHALLENGE_SHA256 = "417f6429cbbc251b2c8923761b1cf1362f5e3d744bbf1170b3d1dc5a98c0cb13"
_FDA_URL = "https://www.accessdata.fda.gov/CDRH510K/K222658.pdf"
_FDA_BAD_TITLE = "'b, , 4 , I 'b, I - accessdata.fda.gov"


def _result(title: str, url: str) -> dict[str, str]:
    return {
        "title": title,
        "link": url,
        "snippet": (
            "The official record describes a regulated product or registered "
            "study and provides enough context for the evidence model."
        ),
    }


def _source_collection() -> SourceCollection:
    source = EvidenceSource(
        source_id="A1",
        title="Deterministic academic control title",
        url="https://doi.org/10.1000/recovery-control",
        publisher="Control Publisher",
        accessed_date=date(2026, 8, 25),
        source_type="academic_paper",
        credibility_tier="high",
        credibility_reason="Deterministic local fixture for discovery testing.",
        evidence_summary=(
            "This local evidence summary is deliberately long enough to meet "
            "the production model contract without any network access."
        ),
        summary_source="abstract",
        doi="10.1000/recovery-control",
    )
    return SourceCollection(
        topic="official source title recovery",
        display_topic="official source title recovery",
        collected_at=datetime(2026, 8, 25, tzinfo=UTC),
        academic_sources=[source],
        patent_sources=[],
        market_sources=[],
        academic_queries=["control query"],
        patent_queries=["control query"],
        market_queries=["control query"],
    )


def test_frozen_candidate_improves_only_disclosed_development_controls() -> None:
    with mock.patch.object(
        socket,
        "create_connection",
        side_effect=AssertionError("candidate attempted network access"),
    ):
        first, first_rows = regulator_title_recovery_candidate.evaluate_candidate(
            _CHALLENGE
        )
        second, second_rows = regulator_title_recovery_candidate.evaluate_candidate(
            _CHALLENGE
        )

    assert first == second
    assert first_rows == second_rows
    assert first["challenge_sha256"] == _CHALLENGE_SHA256
    assert first["case_count"] == 29
    assert first["baseline"] == {
        "matched_expectation_count": 25,
        "mismatched_expectation_count": 4,
    }
    assert first["candidate"] == {
        "state": "accepted_for_production_integration",
        "matched_expectation_count": 29,
        "mismatched_expectation_count": 0,
    }
    assert first["contract_checks_passed"] is True
    assert first["network_calls"] == 0
    assert first["llm_calls"] == 0
    assert first["production_mutations"] == 0


def test_every_frozen_clean_control_is_byte_preserved(subtests) -> None:
    payload = json.loads(_CHALLENGE.read_text(encoding="utf-8"))
    clean_cases = [
        case
        for case in payload["cases"]
        if case["label_provenance"] == "official_api_clean_control"
    ]
    assert len(clean_cases) == 23
    for case in clean_cases:
        with subtests.test(case_id=case["case_id"]):
            scope = regulator_title_audit.authority_scope_for_url(case["url"])
            decision = recover_official_source_title(
                case["input_title"],
                case["url"],
                authority_category=scope,
            )
            assert decision.action == "preserve"
            assert decision.title == case["input_title"]
            assert decision.reason_codes == ()


def test_observed_encoding_failures_receive_only_identifier_labels(subtests) -> None:
    cases = (
        (
            "MitraClip\u0099 G5 Steerable Guide Catheter; TriClip\u0099 G5",
            "https://www.accessdata.fda.gov/CDRH510K/K243224.pdf",
            "FDA 510(k) record K243224",
            "unicode_control_character",
        ),
        (
            _FDA_BAD_TITLE,
            _FDA_URL,
            "FDA 510(k) record K222658",
            "fragmented_single_letter_tokens",
        ),
    )
    for title, url, expected, reason in cases:
        with subtests.test(url=url):
            decision = recover_official_source_title(
                title,
                url,
                authority_category="regulatory",
            )
            assert decision.action == "recover"
            assert decision.title == expected
            assert reason in decision.reason_codes


def test_unsupported_and_attacker_urls_fail_closed() -> None:
    unsupported = recover_official_source_title(
        "�",
        "https://www.fda.gov/medical-devices/example",
        authority_category="regulatory",
    )
    attacker = recover_official_source_title(
        "�",
        "https://accessdata.fda.gov.attacker.example/CDRH510K/K241852.pdf",
        authority_category=None,
    )
    assert unsupported.action == "reject"
    assert unsupported.title is None
    assert attacker.action == "out_of_scope"
    assert attacker.title is None


def test_recovered_title_reaches_final_evidence_source_seam() -> None:
    source, reason = _web_source(
        _result(_FDA_BAD_TITLE, _FDA_URL),
        "M7",
        "market",
        date(2026, 8, 25),
        lambda _url: (True, ""),
    )
    assert reason == ""
    assert source is not None
    assert source.title == "FDA 510(k) record K222658"
    assert "identifier from the validated official URL" in source.credibility_reason
    assert _FDA_BAD_TITLE not in source.model_dump_json()


def test_empty_title_recovers_only_from_a_supported_official_identifier() -> None:
    """Guard the early-title-check move at the final source-model seam.

    Empty search titles used to be rejected before authority validation.  The
    recovery path intentionally delays that rejection, but only a validated
    official URL with a supported identifier may turn the absence into a
    neutral label.  Asserting the final ``EvidenceSource`` prevents a helper-
    only test from missing a future transport regression.
    """

    source, reason = _web_source(
        _result("", _FDA_URL),
        "M8",
        "market",
        date(2026, 8, 25),
        lambda _url: (True, ""),
    )
    assert reason == ""
    assert source is not None
    assert source.title == "FDA 510(k) record K222658"
    assert "empty_title" in source.credibility_reason


def test_unsupported_broken_official_title_is_rejected_at_source_seam() -> None:
    source, reason = _web_source(
        _result("�", "https://www.fda.gov/medical-devices/example"),
        "M1",
        "market",
        date(2026, 8, 25),
        lambda _url: (True, ""),
    )
    assert source is None
    assert "structurally unusable" in reason
    assert "no supported identifier" in reason


def test_mixed_audit_root_prefers_run_artifacts_over_unrelated_json() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        run = root / "20260825T000000Z-control"
        run.mkdir()
        (run / "validated_sources.json").write_text(
            _source_collection().model_dump_json(indent=2),
            encoding="utf-8",
        )
        (root / ".paid-operation-ledger.json").write_text(
            '{"schema_version": 1, "counts": {}}\n',
            encoding="utf-8",
        )

        discovered = regulator_title_audit.discover_collections(root)
        result, _ = regulator_title_audit.evaluate_audit(root, expected_count=1)

    assert discovered == [run / "validated_sources.json"]
    assert result["collection_count"] == 1


def test_flat_only_audit_input_remains_strict() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "not-a-source-collection.json").write_text("{}\n", encoding="utf-8")
        with pytest.raises(
            regulator_title_audit.RegulatorTitleAuditError,
            match="could not load",
        ):
            regulator_title_audit.evaluate_audit(root, expected_count=1)


def test_candidate_writer_persists_every_decision_and_refuses_overwrite() -> None:
    result, rows = regulator_title_recovery_candidate.evaluate_candidate(_CHALLENGE)
    with TemporaryDirectory() as temp:
        output = Path(temp) / "candidate"
        regulator_title_recovery_candidate.write_candidate(output, result, rows)
        persisted = json.loads((output / "result.json").read_text(encoding="utf-8"))
        with (output / "cases.csv").open(encoding="utf-8", newline="") as handle:
            case_rows = list(csv.DictReader(handle))
        with pytest.raises(
            regulator_title_recovery_candidate.RecoveryCandidateError,
            match="refusing to overwrite",
        ):
            regulator_title_recovery_candidate.write_candidate(output, result, rows)

    assert persisted["candidate"]["state"] == "accepted_for_production_integration"
    assert len(case_rows) == 29
    known = next(
        row for row in case_rows if row["case_id"] == "production-fda-fragmented-k222658"
    )
    assert known["baseline_matches_expectation"] == "False"
    assert known["candidate_matches_expectation"] == "True"
    assert known["candidate_title"] == "FDA 510(k) record K222658"
