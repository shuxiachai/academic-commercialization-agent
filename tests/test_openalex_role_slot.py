"""Zero-network seams for candidate-local role-slot consensus v6."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from academic_agent.openalex_claim_scope import (
    OpenAlexAboutnessSignal,
    OpenAlexClaimScopeCandidate,
)
from academic_agent.openalex_evidence_set import (
    EvidenceSetRoleProfile,
    EvidenceSetSelectionContract,
)
from academic_agent.openalex_role_slot import (
    RoleSlotCaseAudit,
    build_role_slot_inputs,
    build_role_slot_prompts,
    evaluate_role_slot_case,
    parse_role_slot_pass,
)
from academic_agent.tools.evidence_search import ToolEvidenceCandidate


_ROOT = Path(__file__).resolve().parents[1]
_TOPIC = (
    "Lignin-derived carbon fibres for recyclable automotive structural "
    "composites"
)


def _profile() -> EvidenceSetRoleProfile:
    return EvidenceSetRoleProfile.model_validate(
        {
            "required_roles": [
                {
                    "role_id": "lignin_precursor",
                    "description": "lignin used as the material precursor or feedstock",
                },
                {
                    "role_id": "carbon_fibre",
                    "description": "production or evaluation of carbon fibre materials",
                },
            ],
            "scope_roles": [
                {
                    "role_id": "automotive_composite",
                    "description": "an automotive or structural composite application",
                }
            ],
            "supporting_roles": [
                {
                    "role_id": "mechanical_performance",
                    "description": "strength, modulus, toughness, or mechanical performance",
                },
                {
                    "role_id": "recyclable_composite",
                    "description": "recycling, reuse, or circularity of the composite",
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


def _candidate(index: int, *, title: str, abstract: str) -> OpenAlexClaimScopeCandidate:
    return OpenAlexClaimScopeCandidate(
        evidence=ToolEvidenceCandidate(
            title=title,
            url=f"https://openalex.org/W46000000{index}",
            publisher="Frozen Test Journal",
            evidence_summary=abstract,
            summary_source="abstract",
            provider_result_index=index,
        ),
        aboutness=(),
    )


def _lignin_candidate(index: int = 0) -> OpenAlexClaimScopeCandidate:
    return _candidate(
        index,
        title="Lignin-derived precursor for automotive composites",
        abstract=(
            "The lignin feedstock formed a structural automotive composite "
            "with high tensile strength."
        ),
    )


def _fibre_candidate(index: int = 1) -> OpenAlexClaimScopeCandidate:
    return _candidate(
        index,
        title="Carbon fibre with recyclable composite performance",
        abstract=(
            "The carbon fibre retained modulus after composite recycling and "
            "reuse."
        ),
    )


def _assignments() -> dict[str, dict[str, tuple[str, str]]]:
    lignin = _lignin_candidate()
    fibre = _fibre_candidate()
    return {
        lignin.sha256(): {
            "lignin_precursor": ("title", "Lignin-derived precursor"),
            "automotive_composite": ("title", "automotive composites"),
            "mechanical_performance": ("abstract", "high tensile strength"),
        },
        fibre.sha256(): {
            "carbon_fibre": ("title", "Carbon fibre"),
            "recyclable_composite": (
                "title",
                "recyclable composite performance",
            ),
        },
    }


def _raw_response(
    batch,
    assignments: dict[str, dict[str, tuple[str, str]]],
) -> str:
    rows = []
    for candidate in batch.candidates:
        candidate_assignments = assignments.get(candidate.candidate_sha256, {})
        slots = []
        for role in batch.roles:
            evidence = candidate_assignments.get(role.role_id)
            slots.append(
                {
                    "slot_index": role.slot_index,
                    "state": "ABSTAIN" if evidence is None else "SUPPORTED",
                    "field": None if evidence is None else evidence[0],
                    "quote": None if evidence is None else evidence[1],
                }
            )
        rows.append(
            {
                "candidate_sha256": candidate.candidate_sha256,
                "slots": slots,
            }
        )
    return json.dumps(
        {"case_id": batch.case_id, "candidates": rows},
        ensure_ascii=True,
    )


def _responses(
    candidates: tuple[OpenAlexClaimScopeCandidate, ...],
    assignments_by_pass: tuple[
        dict[str, dict[str, tuple[str, str]]],
        dict[str, dict[str, tuple[str, str]]],
        dict[str, dict[str, tuple[str, str]]],
    ]
    | None = None,
) -> tuple[str, str, str]:
    inputs = build_role_slot_inputs(
        case_id="Y01",
        topic=_TOPIC,
        profile=_profile(),
        candidates=candidates,
    )
    chosen = assignments_by_pass or (
        _assignments(),
        _assignments(),
        _assignments(),
    )
    return tuple(
        _raw_response(batch, assignments)
        for batch, assignments in zip(inputs, chosen, strict=True)
    )


def _evaluate(
    candidates: tuple[OpenAlexClaimScopeCandidate, ...],
    raw_responses: tuple[str, str, str] | None = None,
    *,
    contract: EvidenceSetSelectionContract | None = None,
) -> RoleSlotCaseAudit:
    return evaluate_role_slot_case(
        case_id="Y01",
        topic=_TOPIC,
        profile=_profile(),
        selection_contract=contract or _contract(),
        candidates=candidates,
        raw_responses=raw_responses or _responses(candidates),
    )


def _payloads(
    candidates: tuple[OpenAlexClaimScopeCandidate, ...],
) -> tuple[dict, dict, dict]:
    return tuple(json.loads(item) for item in _responses(candidates))


def _row(payload: dict, candidate_sha256: str) -> dict:
    return next(
        item
        for item in payload["candidates"]
        if item["candidate_sha256"] == candidate_sha256
    )


def test_inputs_send_three_orders_and_hide_provider_metadata_and_role_ids():
    signal = OpenAlexAboutnessSignal(
        kind="topic",
        provider_id="https://openalex.org/T999",
        display_name="Secret provider topic",
        score=0.99,
    )
    first_candidate = _lignin_candidate()
    second_candidate = _fibre_candidate()
    second_candidate = second_candidate.model_copy(update={"aboutness": (signal,)})

    inputs = build_role_slot_inputs(
        case_id="Y01",
        topic=_TOPIC,
        profile=_profile(),
        candidates=(second_candidate, first_candidate),
    )

    provider_order = tuple(item.candidate_sha256 for item in inputs[0].candidates)
    assert tuple(item.pass_number for item in inputs) == (1, 2, 3)
    assert tuple(item.candidate_sha256 for item in inputs[1].candidates) == tuple(
        reversed(provider_order)
    )
    assert tuple(item.candidate_sha256 for item in inputs[2].candidates) == tuple(
        sorted(provider_order)
    )
    system_prompt, user_prompt = build_role_slot_prompts(inputs[0])
    assert "Secret provider topic" not in user_prompt
    assert "https://openalex.org" not in user_prompt
    assert "lignin_precursor" not in user_prompt
    assert '"action"' not in user_prompt
    assert "Do not decide source" in system_prompt
    assert "admission" in system_prompt


def test_three_valid_passes_select_a_complementary_evidence_set():
    result = _evaluate((_fibre_candidate(), _lignin_candidate()))

    assert result.action == "SELECT"
    assert [item.provider_result_index for item in result.selected_sources] == [0, 1]
    assert result.local_valid_row_rate == 1.0
    assert result.provisional_disposition_unanimity == 1.0
    assert all(len(item.role_consensus) == 5 for item in result.candidate_decisions)
    assert result.production_connected is False
    assert result.report_workflow_connected is False
    assert result.planner_trigger_connected is False


def test_one_malformed_candidate_row_does_not_erase_a_valid_neighbour():
    candidates = (_lignin_candidate(), _fibre_candidate())
    payloads = _payloads(candidates)
    broken = _row(payloads[0], _fibre_candidate().sha256())
    # v5 failed the complete pass for this class of local schema error.  v6
    # rejects the row because the model has no authority to emit an action,
    # while preserving the neighbouring candidate and the later two passes.
    broken["action"] = "KEEP"
    raw = tuple(json.dumps(item) for item in payloads)

    result = _evaluate(candidates, raw)

    first_by_id = {
        item.candidate_sha256: item for item in result.passes[0].candidate_rows
    }
    assert first_by_id[_lignin_candidate().sha256()].row_state == "valid"
    assert first_by_id[_fibre_candidate().sha256()].row_state == "malformed"
    assert result.local_valid_row_numerator == 5
    assert result.action == "SELECT"
    assert len(result.selected_sources) == 2


def test_one_malformed_slot_preserves_other_slots_in_the_same_row():
    candidates = (_lignin_candidate(), _fibre_candidate())
    payloads = _payloads(candidates)
    lignin_row = _row(payloads[0], _lignin_candidate().sha256())
    lignin_row["slots"][3]["unexpected"] = "not allowed"
    raw = tuple(json.dumps(item) for item in payloads)

    result = _evaluate(candidates, raw)

    first_lignin = next(
        item
        for item in result.passes[0].candidate_rows
        if item.candidate_sha256 == _lignin_candidate().sha256()
    )
    assert first_lignin.row_state == "partial"
    assert first_lignin.slots[0].state == "supported"
    assert first_lignin.slots[3].state == "malformed"
    assert result.action == "SELECT"


def test_invented_quotes_never_authorize_a_role():
    candidate = _lignin_candidate()
    payloads = _payloads((candidate,))
    for payload in payloads:
        row = _row(payload, candidate.sha256())
        row["slots"][0]["quote"] = "invented lignin pilot result"
    raw = tuple(json.dumps(item) for item in payloads)

    result = _evaluate((candidate,), raw)

    role = result.candidate_decisions[0].role_consensus[0]
    assert role.support_count == 0
    assert role.consensus_supported is False
    assert all(item.state == "invalid_quote" for item in role.observations)
    assert result.action == "ABSTAIN"


def test_one_pass_support_is_visible_but_cannot_authorize_a_role():
    candidate = _lignin_candidate()
    supported = _assignments()
    empty = {candidate.sha256(): {}}
    raw = _responses((candidate,), (supported, empty, empty))

    result = _evaluate((candidate,), raw)

    role = result.candidate_decisions[0].role_consensus[0]
    assert role.support_count == 1
    assert role.consensus_supported is False
    assert result.action == "ABSTAIN"


def test_two_different_exact_quotes_can_form_role_consensus():
    candidate = _lignin_candidate()
    first = {
        candidate.sha256(): {
            "lignin_precursor": ("title", "Lignin-derived precursor"),
            "automotive_composite": ("title", "automotive composites"),
        }
    }
    second = {
        candidate.sha256(): {
            "lignin_precursor": ("abstract", "lignin feedstock"),
            "automotive_composite": ("title", "automotive composites"),
        }
    }
    third = {candidate.sha256(): {}}

    result = _evaluate((candidate,), _responses((candidate,), (first, second, third)))

    lignin = result.candidate_decisions[0].role_consensus[0]
    assert lignin.support_count == 2
    assert lignin.consensus_supported is True
    assert {item.quote for item in lignin.observations if item.quote} == {
        "Lignin-derived precursor",
        "lignin feedstock",
    }


def test_one_top_level_failure_can_be_audited_without_hiding_two_valid_passes():
    candidates = (_lignin_candidate(), _fibre_candidate())
    raw = _responses(candidates)
    raw = ("not-json", raw[1], raw[2])

    result = _evaluate(candidates, raw)

    assert result.passes[0].state == "malformed"
    assert result.passes[0].error_code == "json_invalid"
    assert all(
        item.row_state == "pass_unavailable"
        for item in result.passes[0].candidate_rows
    )
    assert result.action == "SELECT"
    assert result.local_valid_row_numerator == 4


def test_unknown_and_duplicate_candidate_rows_are_explicit_and_local():
    candidates = (_lignin_candidate(), _fibre_candidate())
    payloads = _payloads(candidates)
    duplicate = deepcopy(_row(payloads[0], _lignin_candidate().sha256()))
    unknown = deepcopy(_row(payloads[0], _fibre_candidate().sha256()))
    unknown["candidate_sha256"] = "f" * 64
    payloads[0]["candidates"].extend([duplicate, unknown, {"bad": "row"}])

    audit = parse_role_slot_pass(
        json.dumps(payloads[0]),
        build_role_slot_inputs(
            case_id="Y01",
            topic=_TOPIC,
            profile=_profile(),
            candidates=candidates,
        )[0],
        _contract(),
    )

    rows = {item.candidate_sha256: item for item in audit.candidate_rows}
    assert rows[_lignin_candidate().sha256()].row_state == "duplicate"
    assert rows[_fibre_candidate().sha256()].row_state == "valid"
    assert audit.unknown_candidate_sha256s == ("f" * 64,)
    assert audit.malformed_unidentified_row_count == 1


def test_duplicate_and_out_of_order_slots_cannot_authorize_the_affected_roles():
    candidate = _lignin_candidate()
    payloads = _payloads((candidate,))
    row = _row(payloads[0], candidate.sha256())
    row["slots"].append(deepcopy(row["slots"][0]))
    row["slots"][1], row["slots"][2] = row["slots"][2], row["slots"][1]

    audit = parse_role_slot_pass(
        json.dumps(payloads[0]),
        build_role_slot_inputs(
            case_id="Y01",
            topic=_TOPIC,
            profile=_profile(),
            candidates=(candidate,),
        )[0],
        _contract(),
    )

    candidate_row = audit.candidate_rows[0]
    assert candidate_row.row_state == "partial"
    assert candidate_row.slots[0].state == "duplicate"
    assert candidate_row.slots[1].state == "order_mismatch"
    assert candidate_row.slots[2].state == "order_mismatch"


def test_unknown_extra_slot_is_counted_without_erasing_expected_slots():
    candidate = _lignin_candidate()
    payloads = _payloads((candidate,))
    row = _row(payloads[0], candidate.sha256())
    row["slots"].append(
        {
            "slot_index": 99,
            "state": "ABSTAIN",
            "field": None,
            "quote": None,
        }
    )

    audit = parse_role_slot_pass(
        json.dumps(payloads[0]),
        build_role_slot_inputs(
            case_id="Y01",
            topic=_TOPIC,
            profile=_profile(),
            candidates=(candidate,),
        )[0],
        _contract(),
    )

    candidate_row = audit.candidate_rows[0]
    assert candidate_row.row_state == "partial"
    assert candidate_row.unknown_slot_count == 1
    assert candidate_row.slots[0].state == "supported"


def test_serialization_cannot_drop_a_computed_selected_role():
    result = _evaluate((_lignin_candidate(), _fibre_candidate()))
    payload = result.model_dump(mode="json")
    payload["selected_sources"][0]["role_ids"].pop()

    with pytest.raises(
        ValidationError,
        match="deliver every deterministic KEEP role",
    ):
        RoleSlotCaseAudit.model_validate(payload)


def test_three_source_ceiling_abstains_when_four_sources_are_required():
    profile_payload = _profile().model_dump(mode="json")
    profile_payload["required_roles"].extend(
        [
            {"role_id": "required_three", "description": "third required role"},
            {"role_id": "required_four", "description": "fourth required role"},
        ]
    )
    profile = EvidenceSetRoleProfile.model_validate(profile_payload)
    candidates = tuple(
        _candidate(
            index,
            title=f"Role source {index} with title evidence",
            abstract="A distinct context measurement supports this source.",
        )
        for index in range(4)
    )
    required_ids = tuple(role.role_id for role in profile.required_roles)
    assignments = {
        candidate.sha256(): {
            required_ids[index]: ("title", f"Role source {index}"),
            "mechanical_performance": ("abstract", "context measurement"),
        }
        for index, candidate in enumerate(candidates)
    }
    inputs = build_role_slot_inputs(
        case_id="Y01",
        topic=_TOPIC,
        profile=profile,
        candidates=candidates,
    )
    raw = tuple(_raw_response(item, assignments) for item in inputs)

    result = evaluate_role_slot_case(
        case_id="Y01",
        topic=_TOPIC,
        profile=profile,
        selection_contract=_contract(),
        candidates=candidates,
        raw_responses=raw,
    )

    assert all(item.action == "KEEP" for item in result.candidate_decisions)
    assert result.action == "ABSTAIN"
    assert result.abstention_reasons == ("no_covering_set",)


def test_production_entrypoints_do_not_import_v6():
    for path in (
        _ROOT / "src" / "academic_agent" / "pipeline_worker.py",
        _ROOT / "api" / "main.py",
    ):
        assert "openalex_role_slot" not in path.read_text(encoding="utf-8")
