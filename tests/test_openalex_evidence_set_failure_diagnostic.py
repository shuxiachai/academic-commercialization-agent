"""Regression seams for the sealed v5 post-outcome failure diagnostic."""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import cast

import pytest

import openalex_evidence_set_failure_diagnostic as diagnostic
from academic_agent.openalex_evidence_set import (
    EvidenceSetCaseAudit,
)
from openalex_evidence_set_development import (
    DevelopmentExecution,
    DevelopmentManifest,
    DevelopmentPacketRow,
)


def _sha(value: int) -> str:
    return f"{value:064x}"


def _valid_pass(
    case_id: str,
    pass_number: int,
    candidate_ids: tuple[str, ...],
) -> dict[str, object]:
    ordered = candidate_ids if pass_number == 1 else tuple(reversed(candidate_ids))
    return {
        "pass_number": pass_number,
        "state": "valid",
        "raw_response_sha256": _sha(800 + pass_number),
        "input_sha256": _sha(900 + pass_number),
        "error_code": None,
        "response": {
            "case_id": case_id,
            "candidate_order": ordered,
            "decisions": [
                {
                    "candidate_sha256": candidate_id,
                    "action": "ABSTAIN",
                    "role_quotes": [],
                }
                for candidate_id in ordered
            ],
        },
    }


def _stable_abstain_case(case_number: int) -> EvidenceSetCaseAudit:
    case_id = f"W{case_number:02d}"
    candidate_ids = tuple(_sha(case_number * 100 + index) for index in range(8))
    return EvidenceSetCaseAudit.model_validate(
        {
            "case_id": case_id,
            "topic": f"Synthetic diagnostic topic for frozen case number {case_number}",
            "action": "ABSTAIN",
            "profile_sha256": _sha(1),
            "selection_contract_sha256": _sha(2),
            "production_connected": False,
            "report_workflow_connected": False,
            "planner_trigger_connected": False,
            "provider_candidate_count": 8,
            "first_pass": _valid_pass(case_id, 1, candidate_ids),
            "second_pass": _valid_pass(case_id, 2, candidate_ids),
            "candidate_decisions": [
                {
                    "candidate_sha256": candidate_id,
                    "provider_result_index": index,
                    "action": "ABSTAIN",
                    "first_action": "ABSTAIN",
                    "second_action": "ABSTAIN",
                    "judge_agreement": True,
                    "required_role_ids": [],
                    "scope_role_ids": [],
                    "supporting_role_ids": [],
                    "title_anchor_role_ids": [],
                    "verified_role_quotes": [],
                    "abstention_reasons": ["judge_abstained"],
                }
                for index, candidate_id in enumerate(candidate_ids)
            ],
            "selected_sources": [],
            "covered_required_role_ids": [],
            "covered_scope_role_ids": [],
            "covered_supporting_role_ids": [],
            "judge_agreement_numerator": 8,
            "judge_agreement_denominator": 8,
            "judge_disposition_agreement": 1.0,
            "abstention_reasons": ["no_valid_candidates"],
        }
    )


def _snapshots() -> tuple[diagnostic.MechanicalSnapshot, diagnostic.HumanSnapshot]:
    cases = tuple(_stable_abstain_case(index) for index in range(1, 9))
    labels: dict[tuple[str, str], diagnostic.HumanLabel] = {}
    row_number = 0
    for case in cases:
        for candidate in case.candidate_decisions:
            row_number += 1
            relevant = row_number <= 28
            labels[(case.case_id, candidate.candidate_sha256)] = diagnostic.HumanLabel(
                case_id=case.case_id,
                provider_result_index=candidate.provider_result_index,
                candidate_sha256=candidate.candidate_sha256,
                direct_relevance="YES" if relevant else "NO",
                semantic_scope_link="YES" if row_number <= 5 else (
                    "NO" if relevant else "N/A"
                ),
                baseline_novelty="YES" if relevant else "N/A",
                abstract_sufficient="YES",
            )
    mechanical = diagnostic.MechanicalSnapshot(
        source_sha256={"execution.json": _sha(10)},
        manifest=cast(DevelopmentManifest, None),
        execution=cast(DevelopmentExecution, None),
        cases=cases,
        calls={},
    )
    human = diagnostic.HumanSnapshot(
        source_sha256={"labels.csv": _sha(11)},
        declaration={
            "reviewed_all": "YES",
            "generative_ai_use": "NONE",
            "external_sources_checked": "NONE",
        },
        packet_rows=(),
        labels=labels,
    )
    return mechanical, human


def _pass(action: str, candidate_id: str, roles: tuple[str, ...] = ()):
    return SimpleNamespace(
        state="valid",
        response=SimpleNamespace(
            decisions=(
                SimpleNamespace(
                    candidate_sha256=candidate_id,
                    action=action,
                    role_quotes=tuple(
                        SimpleNamespace(role_id=role_id) for role_id in roles
                    ),
                ),
            )
        ),
    )


@pytest.mark.parametrize(
    ("first", "second", "first_roles", "second_roles", "final", "expected"),
    [
        ("ABSTAIN", "ABSTAIN", (), (), "ABSTAIN", "stable_abstain"),
        ("KEEP", "ABSTAIN", ("role_a",), (), "ABSTAIN", "action_instability"),
        ("KEEP", "KEEP", ("role_a",), ("role_b",), "ABSTAIN", "role_instability"),
        (
            "KEEP",
            "KEEP",
            ("role_a",),
            ("role_a",),
            "ABSTAIN",
            "post_consensus_rejection",
        ),
        ("KEEP", "KEEP", ("role_a",), ("role_a",), "KEEP", "stable_keep"),
    ],
)
def test_classification_is_mutually_exclusive_at_the_candidate_seam(
    first,
    second,
    first_roles,
    second_roles,
    final,
    expected,
):
    candidate_id = _sha(99)
    case = SimpleNamespace(
        first_pass=_pass(first, candidate_id, first_roles),
        second_pass=_pass(second, candidate_id, second_roles),
    )
    candidate = SimpleNamespace(candidate_sha256=candidate_id, action=final)

    observed, _, _ = diagnostic.classify_candidate(case, candidate)

    assert observed == expected


def test_invalid_pass_shape_cannot_reclassify_the_persisted_candidate():
    candidate_id = _sha(100)
    invalid = SimpleNamespace(state="malformed", response=None)
    case = SimpleNamespace(
        first_pass=invalid,
        second_pass=_pass("KEEP", candidate_id, ("role_a",)),
    )
    candidate = SimpleNamespace(candidate_sha256=candidate_id, action="ABSTAIN")
    raw = {
        "case_id": "W01",
        "candidate_order": [candidate_id],
        "decisions": [
            {
                "candidate_sha256": candidate_id,
                "action": "KEEP",
                "role_quotes": [
                    {"field": "title", "quote": "one", "role_id": "role_a"},
                    {"field": "abstract", "quote": "two", "role_id": "role_a"},
                ],
            }
        ],
    }
    call = SimpleNamespace(
        case_id="W01",
        pass_number=1,
        response=SimpleNamespace(raw_content=json.dumps(raw)),
    )

    failure_class, first_action, _ = diagnostic.classify_candidate(case, candidate)
    shape = diagnostic._shape_probe(call, (candidate_id,))

    assert failure_class == "invalid_pass_exposure"
    assert first_action is None
    assert shape["duplicate_role_id_candidate_count"] == 1
    assert shape["duplicate_role_quote_count"] == 1


def test_indexed_byte_drift_fails_before_semantic_parsing(tmp_path):
    file_hashes: dict[str, str] = {}
    for relative_path in diagnostic._expected_mechanical_files():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"frozen:{relative_path}\n", encoding="utf-8")
        file_hashes[relative_path] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "artifact-index.json").write_text(
        json.dumps(
            {
                "mode": "openalex_evidence_set_v5_development_artifact_index",
                "files": file_hashes,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "judge-calls" / "W01-pass-1.json").write_text(
        "changed after indexing\n",
        encoding="utf-8",
    )

    with pytest.raises(
        diagnostic.EvidenceSetFailureDiagnosticError,
        match="bytes drifted",
    ):
        diagnostic._validate_indexed_files(
            tmp_path,
            {
                name: file_hashes[name]
                for name in diagnostic.EXPECTED_MECHANICAL_KEY_SHA256
            },
        )


def test_label_context_drift_is_rejected_even_when_identity_matches():
    packet_row = DevelopmentPacketRow(
        baseline_sources_json="[]",
        candidate_sha256=_sha(200),
        case_id="W01",
        declared_gap="Frozen synthetic academic evidence gap",
        doi=None,
        evidence_summary="A complete synthetic abstract for the diagnostic seam.",
        identity_sha256=_sha(201),
        provider="openalex",
        provider_result_index=0,
        published_date="2026-01-01",
        publisher="Synthetic Publisher",
        query="synthetic frozen query for diagnostic source",
        summary_source="abstract",
        title="Synthetic frozen candidate title",
        topic="Synthetic frozen commercialization topic",
        url="https://openalex.org/W1",
    )
    row = {
        **diagnostic._expected_context(packet_row),
        "direct_relevance": "YES",
        "semantic_scope_link": "YES",
        "baseline_novelty": "YES",
        "abstract_sufficient": "YES",
        "review_note": "This note grounds the complete synthetic judgment.",
    }
    row["title"] = "A different title with the same candidate identity"

    with pytest.raises(
        diagnostic.EvidenceSetFailureDiagnosticError,
        match="context drifted",
    ):
        diagnostic._validated_human_label(row, packet_row)


def test_every_computed_class_reaches_private_and_public_aggregate_boundaries():
    mechanical, human = _snapshots()

    result = diagnostic.build_failure_diagnostic(mechanical, human)
    public = diagnostic.public_projection(result)

    assert len(result["rows"]) == 64
    assert {row["failure_class"] for row in result["rows"]} == {
        "stable_abstain"
    }
    assert result["metrics"]["failure_class_counts"] == {"stable_abstain": 64}
    assert public["metrics"]["failure_class_counts"] == {"stable_abstain": 64}
    assert "rows" not in public
    assert "private_source_sha256" not in public
    assert "review_method" not in public


def test_public_projection_refuses_a_silent_zero_denominator():
    with pytest.raises(
        diagnostic.EvidenceSetFailureDiagnosticError,
        match="complete 64-row",
    ):
        diagnostic.public_projection(
            {"protocol_status": "complete", "rows": [], "metrics": {}}
        )


def test_production_worker_cannot_import_the_failure_diagnostic():
    worker = (
        diagnostic.Path("src/academic_agent/pipeline_worker.py")
        .read_text(encoding="utf-8")
        .casefold()
    )
    assert "openalex_evidence_set_failure_diagnostic" not in worker
