"""Zero-network tests for the provider-assisted claim-scope gate."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from academic_agent.openalex_claim_scope import (
    OpenAlexAboutnessSignal,
    OpenAlexClaimScopeCandidate,
    OpenAlexClaimScopeProfile,
    evaluate_openalex_claim_scope,
)
from academic_agent.tools.evidence_search import ToolEvidenceCandidate


_ROOT = Path(__file__).resolve().parents[1]


def _profile() -> OpenAlexClaimScopeProfile:
    return OpenAlexClaimScopeProfile.model_validate(
        {
            "required_groups": [
                {
                    "group_id": "quantum_dot",
                    "text_phrases": ["quantum dot", "colloidal quantum"],
                    "provider_terms": ["colloidal quantum dots", "quantum dots"],
                },
                {
                    "group_id": "short_wave_infrared",
                    "text_phrases": ["short wave infrared", "swir"],
                    "provider_terms": [
                        "short-wave infrared photodetectors",
                        "shortwave infrared",
                    ],
                },
            ],
            "supporting_groups": [
                {
                    "group_id": "photodetector",
                    "text_phrases": ["photodetector", "photodiode"],
                    "provider_terms": ["photodetectors", "photodiodes"],
                },
                {
                    "group_id": "silicon_integration",
                    "text_phrases": ["silicon", "cmos"],
                    "provider_terms": ["silicon integration", "cmos image sensors"],
                },
                {
                    "group_id": "performance",
                    "text_phrases": ["detectivity", "responsivity"],
                    "provider_terms": ["photodetector performance", "detectivity"],
                },
            ],
            "minimum_supporting_groups": 2,
            "minimum_exact_required_groups": 1,
            "minimum_title_required_groups": 1,
            "maximum_provider_only_required_groups": 1,
            "provider_score_floor": 0.55,
        }
    )


def _candidate(
    *,
    title: str = "Integrated colloidal quantum-dot photodetector on silicon",
    summary: str = (
        "The integrated silicon photodetector reports high detectivity and "
        "responsivity across its measured spectral range."
    ),
    aboutness: tuple[OpenAlexAboutnessSignal, ...] = (),
) -> OpenAlexClaimScopeCandidate:
    return OpenAlexClaimScopeCandidate(
        evidence=ToolEvidenceCandidate(
            title=title,
            url="https://openalex.org/W4300000001",
            publisher="Frozen Test Journal",
            evidence_summary=summary,
            summary_source="abstract",
            provider_result_index=0,
        ),
        aboutness=aboutness,
    )


def _signal(
    display_name: str,
    *,
    score: float = 0.9,
    kind: str = "keyword",
    suffix: str = "K1",
) -> OpenAlexAboutnessSignal:
    return OpenAlexAboutnessSignal.model_validate(
        {
            "kind": kind,
            "provider_id": f"https://openalex.org/{suffix}",
            "display_name": display_name,
            "score": score,
        }
    )


def test_provider_aboutness_may_bridge_exactly_one_required_concept():
    candidate = _candidate(
        aboutness=(_signal("Short-wave infrared photodetectors"),)
    )

    decision = evaluate_openalex_claim_scope(candidate, _profile())

    assert decision.action == "ACCEPT"
    assert decision.exact_required_groups == ("quantum_dot",)
    assert decision.title_required_groups == ("quantum_dot",)
    assert decision.provider_only_required_groups == ("short_wave_infrared",)
    infrared = decision.required_matches[1]
    assert infrared.provider_aboutness[0].matched_term == (
        "short-wave infrared photodetectors"
    )
    assert infrared.provider_aboutness[0].score == pytest.approx(0.9)


def test_provider_labels_alone_cannot_authorize_a_source():
    candidate = _candidate(
        title="Integrated optoelectronic sensing platform",
        summary=(
            "The sensor reports detectivity and silicon integration for a "
            "general imaging platform without naming the target material."
        ),
        aboutness=(
            _signal("Colloidal quantum dots", suffix="K1"),
            _signal("Short-wave infrared photodetectors", suffix="K2"),
        ),
    )

    decision = evaluate_openalex_claim_scope(candidate, _profile())

    assert decision.action == "ABSTAIN"
    assert decision.provider_only_required_groups == (
        "quantum_dot",
        "short_wave_infrared",
    )
    assert "insufficient_exact_required_groups" in decision.abstention_reasons
    assert "missing_title_anchor" in decision.abstention_reasons
    assert (
        "too_many_provider_only_required_groups" in decision.abstention_reasons
    )


def test_low_score_provider_label_does_not_satisfy_required_scope():
    candidate = _candidate(
        aboutness=(
            _signal(
                "Short-wave infrared photodetectors",
                score=0.54,
            ),
        )
    )

    decision = evaluate_openalex_claim_scope(candidate, _profile())

    assert decision.action == "ABSTAIN"
    assert decision.missing_required_groups == ("short_wave_infrared",)
    assert decision.provider_only_required_groups == ()


def test_exact_text_path_remains_valid_without_provider_metadata():
    candidate = _candidate(
        title=(
            "Short-wave infrared colloidal quantum-dot photodetector on silicon"
        )
    )

    decision = evaluate_openalex_claim_scope(candidate, _profile())

    assert decision.action == "ACCEPT"
    assert decision.exact_required_groups == (
        "quantum_dot",
        "short_wave_infrared",
    )
    assert decision.provider_only_required_groups == ()


def test_candidate_identity_includes_provider_aboutness_score():
    first = _candidate(
        aboutness=(_signal("Short-wave infrared photodetectors", score=0.8),)
    )
    second = _candidate(
        aboutness=(_signal("Short-wave infrared photodetectors", score=0.9),)
    )

    assert first.sha256() != second.sha256()


def test_duplicate_provider_term_across_independent_groups_fails_closed():
    payload = _profile().model_dump(mode="json")
    payload["supporting_groups"][0]["provider_terms"][0] = (
        payload["required_groups"][0]["provider_terms"][0]
    )

    with pytest.raises(
        ValidationError,
        match="provider_terms phrase appears in multiple groups",
    ):
        OpenAlexClaimScopeProfile.model_validate(payload)


def test_production_worker_remains_disconnected():
    worker = (_ROOT / "src/academic_agent/pipeline_worker.py").read_text(
        encoding="utf-8"
    )

    assert "openalex_claim_scope" not in worker
    assert "openalex_claim_scope_search" not in worker
