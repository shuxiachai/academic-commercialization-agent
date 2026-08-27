"""Zero-network tests for the role-structured OpenAlex scope-link gate."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from academic_agent.openalex_claim_scope import (
    OpenAlexAboutnessSignal,
    OpenAlexClaimScopeCandidate,
)
from academic_agent.openalex_scope_link import (
    OpenAlexScopeLinkProfile,
    evaluate_openalex_scope_link,
)
from academic_agent.tools.evidence_search import ToolEvidenceCandidate


_ROOT = Path(__file__).resolve().parents[1]


def _profile() -> OpenAlexScopeLinkProfile:
    return OpenAlexScopeLinkProfile.model_validate(
        {
            "required_groups": [
                {
                    "group_id": "sodium_ion_battery",
                    "text_phrases": [
                        "sodium ion battery",
                        "sodium ion batteries",
                    ],
                    "provider_terms": [
                        "sodium ion batteries",
                        "sodium battery",
                    ],
                },
                {
                    "group_id": "hard_carbon_anode",
                    "text_phrases": [
                        "hard carbon anode",
                        "hard carbon anodes",
                    ],
                    "provider_terms": ["hard carbon anodes", "hard carbon"],
                },
            ],
            "scope_groups": [
                {
                    "group_id": "agricultural_waste",
                    "text_phrases": [
                        "agricultural waste",
                        "crop residue",
                        "rice husk",
                    ],
                }
            ],
            "supporting_groups": [
                {
                    "group_id": "electrochemical_performance",
                    "text_phrases": [
                        "specific capacity",
                        "cycling stability",
                    ],
                },
                {
                    "group_id": "stationary_storage",
                    "text_phrases": ["stationary storage", "grid storage"],
                },
            ],
            "minimum_exact_required_groups": 1,
            "maximum_provider_only_required_groups": 1,
            "minimum_scope_groups": 1,
            "minimum_linked_scope_groups": 1,
            "minimum_supporting_groups": 1,
            "minimum_title_anchor_groups": 1,
            "provider_score_floor": 0.55,
        }
    )


def _candidate(
    *,
    title: str = (
        "Agricultural-waste hard-carbon anodes for sodium-ion batteries"
    ),
    summary: str = (
        "The electrodes retained high specific capacity during repeated cycles."
    ),
    aboutness: tuple[OpenAlexAboutnessSignal, ...] = (),
) -> OpenAlexClaimScopeCandidate:
    return OpenAlexClaimScopeCandidate(
        evidence=ToolEvidenceCandidate(
            title=title,
            url="https://openalex.org/W4400000001",
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
    suffix: str = "K1",
) -> OpenAlexAboutnessSignal:
    return OpenAlexAboutnessSignal(
        kind="keyword",
        provider_id=f"https://openalex.org/{suffix}",
        display_name=display_name,
        score=score,
    )


def test_same_title_scope_link_accepts_and_reaches_serialized_boundary():
    decision = evaluate_openalex_scope_link(_candidate(), _profile())

    assert decision.action == "ACCEPT"
    assert decision.exact_required_groups == (
        "sodium_ion_battery",
        "hard_carbon_anode",
    )
    assert decision.exact_scope_groups == ("agricultural_waste",)
    assert decision.linked_scope_groups == ("agricultural_waste",)
    assert decision.abstention_reasons == ()

    payload = decision.model_dump(mode="json")
    assert payload["action"] == "ACCEPT"
    assert payload["linked_scope_groups"] == ["agricultural_waste"]
    assert {
        (
            item["required_group_id"],
            item["scope_group_id"],
            item["field"],
            item["sentence_index"],
        )
        for item in payload["link_evidence"]
    } == {
        (
            "sodium_ion_battery",
            "agricultural_waste",
            "title",
            0,
        ),
        (
            "hard_carbon_anode",
            "agricultural_waste",
            "title",
            0,
        ),
    }


def test_cross_sentence_cooccurrence_abstains_instead_of_inventing_a_link():
    candidate = _candidate(
        title="Hard-carbon anodes for sodium-ion batteries",
        summary=(
            "The hard carbon anode delivered high specific capacity. "
            "Agricultural waste was used as the precursor."
        ),
    )

    decision = evaluate_openalex_scope_link(candidate, _profile())

    assert decision.exact_scope_groups == ("agricultural_waste",)
    assert decision.linked_scope_groups == ()
    assert decision.link_evidence == ()
    assert decision.action == "ABSTAIN"
    assert decision.abstention_reasons == ("missing_scope_link",)


def test_provider_aboutness_may_bridge_one_required_but_not_scope():
    candidate = _candidate(
        title="Agricultural-waste hard-carbon anode with stable cycling",
        summary="The electrode retained high specific capacity.",
        aboutness=(_signal("Sodium ion batteries"),),
    )

    decision = evaluate_openalex_scope_link(candidate, _profile())

    assert decision.action == "ACCEPT"
    assert decision.exact_required_groups == ("hard_carbon_anode",)
    assert decision.provider_only_required_groups == ("sodium_ion_battery",)
    assert decision.linked_scope_groups == ("agricultural_waste",)

    scope_only_provider = _candidate(
        title="Hard-carbon anodes for sodium-ion batteries",
        aboutness=(_signal("Agricultural waste"),),
    )
    scope_decision = evaluate_openalex_scope_link(
        scope_only_provider,
        _profile(),
    )

    assert scope_decision.exact_scope_groups == ()
    assert scope_decision.linked_scope_groups == ()
    assert scope_decision.action == "ABSTAIN"
    assert "insufficient_scope_groups" in scope_decision.abstention_reasons
    assert "missing_scope_link" in scope_decision.abstention_reasons


def test_missing_scope_records_both_coverage_and_relation_failures():
    candidate = _candidate(
        title="Hard-carbon anodes for sodium-ion batteries",
        summary="The electrodes retained high specific capacity.",
    )

    decision = evaluate_openalex_scope_link(candidate, _profile())

    assert decision.action == "ABSTAIN"
    assert decision.exact_scope_groups == ()
    assert decision.abstention_reasons == (
        "insufficient_scope_groups",
        "missing_scope_link",
    )


def test_low_score_provider_label_does_not_satisfy_required_group():
    candidate = _candidate(
        title="Agricultural-waste hard-carbon anode with stable cycling",
        aboutness=(_signal("Sodium ion batteries", score=0.54),),
    )

    decision = evaluate_openalex_scope_link(candidate, _profile())

    assert decision.action == "ABSTAIN"
    assert decision.missing_required_groups == ("sodium_ion_battery",)
    assert decision.provider_only_required_groups == ()


def test_candidate_identity_includes_provider_aboutness_score():
    first = _candidate(aboutness=(_signal("Sodium ion batteries", score=0.8),))
    second = _candidate(aboutness=(_signal("Sodium ion batteries", score=0.9),))

    first_decision = evaluate_openalex_scope_link(first, _profile())
    second_decision = evaluate_openalex_scope_link(second, _profile())

    assert first_decision.candidate_sha256 != second_decision.candidate_sha256


def test_duplicate_text_phrase_across_roles_fails_closed():
    payload = _profile().model_dump(mode="json")
    payload["scope_groups"][0]["text_phrases"][0] = (
        payload["required_groups"][0]["text_phrases"][0]
    )

    with pytest.raises(
        ValidationError,
        match="normalized text phrase appears in multiple groups",
    ):
        OpenAlexScopeLinkProfile.model_validate(payload)


def test_impossible_scope_threshold_fails_closed():
    payload = _profile().model_dump(mode="json")
    payload["minimum_linked_scope_groups"] = 2

    with pytest.raises(
        ValidationError,
        match="minimum_linked_scope_groups exceeds the scope-group count",
    ):
        OpenAlexScopeLinkProfile.model_validate(payload)


def test_production_worker_remains_disconnected():
    worker = (_ROOT / "src/academic_agent/pipeline_worker.py").read_text(
        encoding="utf-8"
    )

    assert "openalex_scope_link" not in worker
    assert "evaluate_openalex_scope_link" not in worker
