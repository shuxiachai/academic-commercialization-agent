"""Zero-network seams for the quote-grounded evidence-set v5 kernel."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from academic_agent.openalex_claim_scope import (
    OpenAlexAboutnessSignal,
    OpenAlexClaimScopeCandidate,
)
from academic_agent.openalex_evidence_set import (
    EvidenceSetCaseAudit,
    EvidenceSetRoleProfile,
    EvidenceSetSelectionContract,
    build_judge_inputs,
    evaluate_evidence_set_case,
    parse_judge_pass,
)
from academic_agent.tools.evidence_search import ToolEvidenceCandidate


_ROOT = Path(__file__).resolve().parents[1]
_TOPIC = (
    "Redox-active polymer electrodes for electrochemical carbon dioxide "
    "capture from flue gas"
)


def _profile() -> EvidenceSetRoleProfile:
    return EvidenceSetRoleProfile.model_validate(
        {
            "required_roles": [
                {
                    "role_id": "electrochemical_capture",
                    "description": (
                        "reversible electrochemical capture or release of "
                        "carbon dioxide"
                    ),
                },
                {
                    "role_id": "redox_polymer",
                    "description": (
                        "a redox-active polymer electrode or polymer-bound carrier"
                    ),
                },
            ],
            "scope_roles": [
                {
                    "role_id": "flue_gas",
                    "description": (
                        "capture from flue gas or a dilute industrial gas stream"
                    ),
                }
            ],
            "supporting_roles": [
                {
                    "role_id": "capture_performance",
                    "description": (
                        "capacity, selectivity, rate, or separation performance"
                    ),
                },
                {
                    "role_id": "cycling_stability",
                    "description": (
                        "repeated capture-release cycling or electrode stability"
                    ),
                },
            ],
        }
    )


def _contract(**overrides: object) -> EvidenceSetSelectionContract:
    payload = {
        "required_roles_covered": "all",
        "minimum_scope_roles": 1,
        "minimum_supporting_roles": 1,
        "maximum_selected_sources_per_case": 3,
        "minimum_candidate_required_roles": 1,
        "minimum_candidate_context_roles": 1,
        "minimum_candidate_title_anchor_roles": 1,
    }
    payload.update(overrides)
    return EvidenceSetSelectionContract.model_validate(payload)


def _candidate(
    index: int,
    *,
    title: str,
    abstract: str,
    aboutness: tuple[OpenAlexAboutnessSignal, ...] = (),
) -> OpenAlexClaimScopeCandidate:
    return OpenAlexClaimScopeCandidate(
        evidence=ToolEvidenceCandidate(
            title=title,
            url=f"https://openalex.org/W45000000{index}",
            publisher="Frozen Test Journal",
            evidence_summary=abstract,
            summary_source="abstract",
            provider_result_index=index,
        ),
        aboutness=aboutness,
    )


def _capture_candidate(index: int = 0) -> OpenAlexClaimScopeCandidate:
    return _candidate(
        index,
        title="Electrochemical capture using a polymer electrode",
        abstract=(
            "The system removes carbon dioxide from flue gas with high capture "
            "capacity."
        ),
    )


def _polymer_candidate(index: int = 1) -> OpenAlexClaimScopeCandidate:
    return _candidate(
        index,
        title="Redox-active polymer electrodes with stable cycling",
        abstract=(
            "The polymer retained activity during repeated capture and release "
            "cycles."
        ),
    )


def _assignments() -> dict[str, tuple[tuple[str, str, str], ...]]:
    capture = _capture_candidate()
    polymer = _polymer_candidate()
    return {
        capture.sha256(): (
            (
                "electrochemical_capture",
                "title",
                "Electrochemical capture",
            ),
            ("flue_gas", "abstract", "flue gas"),
            (
                "capture_performance",
                "abstract",
                "high capture capacity",
            ),
        ),
        polymer.sha256(): (
            ("redox_polymer", "title", "Redox-active polymer electrodes"),
            ("cycling_stability", "title", "stable cycling"),
        ),
    }


def _raw_response(
    batch,
    assignments: dict[str, tuple[tuple[str, str, str], ...] | None],
) -> str:
    decisions = []
    for candidate in batch.candidates:
        rows = assignments[candidate.candidate_sha256]
        decisions.append(
            {
                "candidate_sha256": candidate.candidate_sha256,
                "action": "ABSTAIN" if rows is None else "KEEP",
                "role_quotes": []
                if rows is None
                else [
                    {"role_id": role_id, "field": field, "quote": quote}
                    for role_id, field, quote in rows
                ],
            }
        )
    return json.dumps(
        {
            "case_id": batch.case_id,
            "candidate_order": [
                item.candidate_sha256 for item in batch.candidates
            ],
            "decisions": decisions,
        },
        ensure_ascii=True,
    )


def _evaluate(
    candidates: tuple[OpenAlexClaimScopeCandidate, ...],
    assignments: dict[str, tuple[tuple[str, str, str], ...] | None],
    *,
    profile: EvidenceSetRoleProfile | None = None,
    contract: EvidenceSetSelectionContract | None = None,
):
    chosen_profile = profile or _profile()
    chosen_contract = contract or _contract()
    first, second = build_judge_inputs(
        case_id="X01",
        topic=_TOPIC,
        profile=chosen_profile,
        candidates=candidates,
    )
    return evaluate_evidence_set_case(
        case_id="X01",
        topic=_TOPIC,
        profile=chosen_profile,
        selection_contract=chosen_contract,
        candidates=candidates,
        first_raw_response=_raw_response(first, assignments),
        second_raw_response=_raw_response(second, assignments),
    )


def test_judge_inputs_reverse_order_and_expose_only_allowed_candidate_fields():
    signal = OpenAlexAboutnessSignal(
        kind="topic",
        provider_id="https://openalex.org/T100",
        display_name="Secret provider topic",
        score=0.99,
    )
    first_candidate = _candidate(
        1,
        title="Redox-active polymer electrodes with stable cycling",
        abstract="The polymer remained stable.",
        aboutness=(signal,),
    )
    second_candidate = _capture_candidate(0)

    first, second = build_judge_inputs(
        case_id="X01",
        topic=_TOPIC,
        profile=_profile(),
        candidates=(first_candidate, second_candidate),
    )

    first_ids = [item.candidate_sha256 for item in first.candidates]
    second_ids = [item.candidate_sha256 for item in second.candidates]
    assert first_ids == [second_candidate.sha256(), first_candidate.sha256()]
    assert second_ids == list(reversed(first_ids))
    assert first.pass_number == 1
    assert second.pass_number == 2
    for candidate in first.model_dump(mode="json")["candidates"]:
        assert set(candidate) == {"candidate_sha256", "title", "abstract"}
    serialized = first.model_dump_json()
    assert "openalex.org" not in serialized
    assert "Secret provider topic" not in serialized
    assert "provider" not in serialized


def test_two_complementary_sources_are_selected_and_reach_json_boundary():
    capture = _capture_candidate()
    polymer = _polymer_candidate()

    result = _evaluate((polymer, capture), _assignments())

    assert result.action == "SELECT"
    assert result.judge_disposition_agreement == 1.0
    assert [item.provider_result_index for item in result.selected_sources] == [0, 1]
    assert result.covered_required_role_ids == (
        "electrochemical_capture",
        "redox_polymer",
    )
    assert result.covered_scope_role_ids == ("flue_gas",)
    assert result.covered_supporting_role_ids == (
        "capture_performance",
        "cycling_stability",
    )

    payload = result.model_dump(mode="json")
    assert len(payload["candidate_decisions"]) == 2
    assert payload["selected_sources"] == [
        {
            "candidate_sha256": capture.sha256(),
            "provider_result_index": 0,
            "role_ids": [
                "electrochemical_capture",
                "flue_gas",
                "capture_performance",
            ],
        },
        {
            "candidate_sha256": polymer.sha256(),
            "provider_result_index": 1,
            "role_ids": [
                "redox_polymer",
                "cycling_stability",
            ],
        },
    ]


def test_invalid_paraphrase_abstains_and_counts_as_disagreement():
    candidate = _capture_candidate()
    assignments = {
        candidate.sha256(): (
            (
                "electrochemical_capture",
                "title",
                "electric separation of carbon",
            ),
            ("flue_gas", "abstract", "flue gas"),
        )
    }

    result = _evaluate((candidate,), assignments)

    decision = result.candidate_decisions[0]
    assert decision.action == "ABSTAIN"
    assert decision.judge_agreement is False
    assert decision.abstention_reasons == ("invalid_quote",)
    assert result.judge_disposition_agreement == 0.0
    assert result.action == "ABSTAIN"
    assert result.abstention_reasons == ("no_valid_candidates",)


def test_serialized_selected_roles_cannot_drop_a_verified_assignment():
    result = _evaluate(
        (_capture_candidate(), _polymer_candidate()),
        _assignments(),
    )
    payload = result.model_dump(mode="json")
    payload["selected_sources"][0]["role_ids"].pop()

    with pytest.raises(
        ValidationError,
        match="deliver every verified KEEP role",
    ):
        EvidenceSetCaseAudit.model_validate(payload)


def test_layout_only_whitespace_normalization_preserves_a_real_quote():
    candidate = _candidate(
        0,
        title="Electrochemical capture using a polymer electrode",
        abstract="Carbon dioxide was removed from\n   flue gas at high capacity.",
    )
    assignments = {
        candidate.sha256(): (
            ("electrochemical_capture", "title", "Electrochemical capture"),
            ("flue_gas", "abstract", "from flue gas"),
        )
    }

    result = _evaluate((candidate,), assignments)

    assert result.candidate_decisions[0].judge_agreement is True
    assert "invalid_quote" not in result.candidate_decisions[0].abstention_reasons


def test_role_disagreement_fails_closed_without_a_repair_call():
    candidate = _capture_candidate()
    first, second = build_judge_inputs(
        case_id="X01",
        topic=_TOPIC,
        profile=_profile(),
        candidates=(candidate,),
    )
    first_assignments = {
        candidate.sha256(): (
            ("electrochemical_capture", "title", "Electrochemical capture"),
            ("flue_gas", "abstract", "flue gas"),
        )
    }
    second_assignments = {
        candidate.sha256(): (
            ("electrochemical_capture", "title", "Electrochemical capture"),
            (
                "capture_performance",
                "abstract",
                "high capture capacity",
            ),
        )
    }

    result = evaluate_evidence_set_case(
        case_id="X01",
        topic=_TOPIC,
        profile=_profile(),
        selection_contract=_contract(),
        candidates=(candidate,),
        first_raw_response=_raw_response(first, first_assignments),
        second_raw_response=_raw_response(second, second_assignments),
    )

    assert result.candidate_decisions[0].abstention_reasons == (
        "judge_role_disagreement",
    )
    assert result.first_pass.state == "valid"
    assert result.second_pass.state == "valid"


def test_malformed_pass_abstains_every_row_and_keeps_every_row_in_audit():
    capture = _capture_candidate()
    polymer = _polymer_candidate()
    _, second = build_judge_inputs(
        case_id="X01",
        topic=_TOPIC,
        profile=_profile(),
        candidates=(capture, polymer),
    )

    result = evaluate_evidence_set_case(
        case_id="X01",
        topic=_TOPIC,
        profile=_profile(),
        selection_contract=_contract(),
        candidates=(capture, polymer),
        first_raw_response="not-json",
        second_raw_response=_raw_response(second, _assignments()),
    )

    assert result.first_pass.state == "malformed"
    assert result.first_pass.error_code == "schema_invalid"
    assert result.provider_candidate_count == 2
    assert len(result.candidate_decisions) == 2
    assert {item.abstention_reasons for item in result.candidate_decisions} == {
        ("judge_pass_invalid",)
    }


def test_wrong_case_or_candidate_order_is_contract_invalid():
    candidate = _capture_candidate()
    first, _ = build_judge_inputs(
        case_id="X01",
        topic=_TOPIC,
        profile=_profile(),
        candidates=(candidate,),
    )
    assignments = {
        candidate.sha256(): (
            ("electrochemical_capture", "title", "Electrochemical capture"),
            ("flue_gas", "abstract", "flue gas"),
        )
    }
    payload = json.loads(_raw_response(first, assignments))
    payload["case_id"] = "X02"

    audit = parse_judge_pass(json.dumps(payload), first)

    assert audit.state == "contract_invalid"
    assert audit.error_code == "case_id_mismatch"


def test_both_model_abstentions_agree_but_do_not_create_evidence():
    candidate = _capture_candidate()

    result = _evaluate((candidate,), {candidate.sha256(): None})

    decision = result.candidate_decisions[0]
    assert decision.judge_agreement is True
    assert decision.action == "ABSTAIN"
    assert decision.abstention_reasons == ("judge_abstained",)
    assert result.judge_disposition_agreement == 1.0


def test_candidate_without_consensus_title_anchor_cannot_enter_set_cover():
    candidate = _capture_candidate()
    first, second = build_judge_inputs(
        case_id="X01",
        topic=_TOPIC,
        profile=_profile(),
        candidates=(candidate,),
    )
    first_assignments = {
        candidate.sha256(): (
            ("electrochemical_capture", "title", "Electrochemical capture"),
            ("flue_gas", "abstract", "flue gas"),
        )
    }
    second_assignments = {
        candidate.sha256(): (
            (
                "electrochemical_capture",
                "abstract",
                "removes carbon dioxide",
            ),
            ("flue_gas", "abstract", "flue gas"),
        )
    }

    result = evaluate_evidence_set_case(
        case_id="X01",
        topic=_TOPIC,
        profile=_profile(),
        selection_contract=_contract(),
        candidates=(candidate,),
        first_raw_response=_raw_response(first, first_assignments),
        second_raw_response=_raw_response(second, second_assignments),
    )

    assert result.candidate_decisions[0].abstention_reasons == (
        "missing_title_anchor",
    )


def test_set_cover_prefers_lower_provider_index_after_minimum_size():
    capture = _capture_candidate()
    lower = _polymer_candidate(1)
    higher = _polymer_candidate(2)
    assignments = _assignments()
    assignments[higher.sha256()] = assignments.pop(_polymer_candidate().sha256())
    assignments[lower.sha256()] = (
        ("redox_polymer", "title", "Redox-active polymer electrodes"),
        ("cycling_stability", "title", "stable cycling"),
    )

    result = _evaluate((higher, capture, lower), assignments)

    assert [item.provider_result_index for item in result.selected_sources] == [0, 1]
    assert higher.sha256() not in {
        item.candidate_sha256 for item in result.selected_sources
    }


def test_three_source_ceiling_abstains_when_four_scope_roles_are_required():
    profile_payload = _profile().model_dump(mode="json")
    profile_payload["required_roles"].extend(
        [
            {"role_id": "required_three", "description": "third required role"},
            {"role_id": "required_four", "description": "fourth required role"},
        ]
    )
    profile_payload["scope_roles"] = [
        {"role_id": f"scope_{index}", "description": f"scope role number {index}"}
        for index in range(1, 5)
    ]
    profile = EvidenceSetRoleProfile.model_validate(profile_payload)
    candidates = tuple(
        _candidate(
            index,
            title=f"Required role {index + 1} with scope role {index + 1}",
            abstract="Supporting evidence was reported.",
        )
        for index in range(4)
    )
    required_ids = [role.role_id for role in profile.required_roles]
    assignments = {
        candidate.sha256(): (
            (
                required_ids[index],
                "title",
                f"Required role {index + 1}",
            ),
            (
                f"scope_{index + 1}",
                "title",
                f"scope role {index + 1}",
            ),
            (
                "capture_performance",
                "abstract",
                "Supporting evidence",
            ),
        )
        for index, candidate in enumerate(candidates)
    }

    result = _evaluate(
        candidates,
        assignments,
        profile=profile,
        contract=_contract(minimum_scope_roles=4),
    )

    assert all(item.action == "KEEP" for item in result.candidate_decisions)
    assert result.action == "ABSTAIN"
    assert result.abstention_reasons == ("no_covering_set",)


def test_duplicate_role_ids_fail_before_any_judge_input_can_be_built():
    payload = _profile().model_dump(mode="json")
    payload["scope_roles"][0]["role_id"] = (
        payload["required_roles"][0]["role_id"]
    )

    with pytest.raises(ValidationError, match="role IDs must be unique"):
        EvidenceSetRoleProfile.model_validate(payload)


def test_production_worker_and_kernel_remain_disconnected_from_live_clients():
    worker = (_ROOT / "src/academic_agent/pipeline_worker.py").read_text(
        encoding="utf-8"
    )
    kernel = (_ROOT / "src/academic_agent/openalex_evidence_set.py").read_text(
        encoding="utf-8"
    )

    assert "openalex_evidence_set" not in worker
    assert "evaluate_evidence_set_case" not in worker
    assert "anonymous_openalex_search" not in kernel
    assert "openalex_claim_scope_search" not in kernel
    assert "litellm" not in kernel
    assert "urllib" not in kernel
