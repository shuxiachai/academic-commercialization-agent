"""Zero-network review seams for the failed role-slot v6 provider population."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from datetime import date
from pathlib import Path

import pytest

import openalex_role_slot_development as development
import openalex_role_slot_failure_review as diagnostic
from academic_agent.openalex_claim_scope import OpenAlexClaimScopeCandidate
from academic_agent.tools.evidence_search import (
    ToolEvidenceCandidate,
    ToolProviderUsage,
)
from academic_agent.tools.openalex_claim_scope_search import (
    OpenAlexClaimScopeAdapterResponse,
)
from academic_agent.tools.qwen_role_slot_judge import (
    QwenRoleSlotResponse,
    QwenRoleSlotUsage,
)
from openalex_role_slot_failure_review import (
    LABEL_FIELDS,
    RoleSlotFailureReviewError,
    create_source_lock,
    prepare_packet,
    summarize_packet,
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _implementation_hashes() -> dict[str, str]:
    return {
        name: _sha256(path.read_bytes())
        for name, path in development._IMPLEMENTATION_PATHS.items()  # noqa: SLF001
    }


def _candidate(case_id: str, index: int) -> OpenAlexClaimScopeCandidate:
    return OpenAlexClaimScopeCandidate(
        evidence=ToolEvidenceCandidate(
            title=(
                f"{case_id} candidate {index} frozen title with role evidence"
            ),
            url=f"https://openalex.org/W{case_id[1:]}{index}123456789",
            doi=f"10.5555/{case_id.casefold()}.{index}",
            publisher="Frozen OpenAlex Test Publisher",
            published_date=date(2026, 8, 31),
            evidence_summary=(
                f"This abstract for {case_id} candidate {index} contains "
                "sufficient public text for the deterministic role review seam."
            ),
            summary_source="abstract",
            citation_count=index,
            provider_result_index=index,
        ),
        aboutness=(),
    )


class _ProviderAdapter:
    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, call):  # noqa: ANN001, ANN204
        self.call_count += 1
        case_id = f"Y{self.call_count:02d}"
        request_id = f"client-openalex-v6-review-{case_id.casefold()}"
        usage = ToolProviderUsage(
            provider="openalex",
            request_id=request_id,
            request_id_source="client_generated",
            result_count=8,
            cost_basis="reported_usd",
            reported_cost_usd=0.001,
        )
        return OpenAlexClaimScopeAdapterResponse(
            idempotency_key=call.idempotency_key,
            candidates=tuple(_candidate(case_id, index) for index in range(8)),
            provider_rejections=(),
            search_cost_usd=0.001,
            provider_request_id=request_id,
            provider_usage=usage,
        )


def _prompt_input(request) -> dict[str, object]:  # noqa: ANN001
    return json.loads(request.user_prompt.split("INPUT:\n", 1)[1])


class _ModelAdapter:
    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, request):  # noqa: ANN001, ANN204
        self.call_count += 1
        outbound = _prompt_input(request)
        raw_content = json.dumps(
            {
                "case_id": request.case_id,
                "candidates": [
                    {
                        "candidate_sha256": candidate["candidate_sha256"],
                        "slots": [
                            {
                                "slot_index": role["slot_index"],
                                "state": "ABSTAIN",
                                "field": None,
                                "quote": None,
                            }
                            for role in outbound["roles"]
                        ],
                    }
                    for candidate in outbound["candidates"]
                ],
            },
            separators=(",", ":"),
        )
        usage = QwenRoleSlotUsage(
            prompt_tokens=100,
            cached_prompt_tokens=0,
            completion_tokens=20,
            total_tokens=120,
            cost_usd=0.001,
            cost_basis="frozen zero-network review test cost",
        )
        return QwenRoleSlotResponse(
            case_id=request.case_id,
            pass_number=request.pass_number,
            candidate_order=request.candidate_order,
            trace_id=request.trace_id,
            request_sha256=_sha256(request.body()),
            batch_input_sha256=request.batch_input_sha256,
            prompt_sha256=request.prompt_sha256,
            requested_model=request.requested_model,
            returned_model="qwen3.5-plus",
            provider_response_id=f"qwen-response-{self.call_count}",
            provider_request_id=f"qwen-request-{self.call_count}",
            finish_reason="stop",
            raw_content=raw_content,
            raw_content_sha256=_sha256(raw_content.encode("utf-8")),
            usage=usage,
            latency_ms=25.0,
        )


@pytest.fixture(scope="module")
def _frozen_source(tmp_path_factory):  # noqa: ANN001, ANN202
    output = tmp_path_factory.mktemp("v6-review-source") / "result"
    implementation_hashes = _implementation_hashes()
    provider = _ProviderAdapter()
    model = _ModelAdapter()
    execution = development.execute_development_study(
        output_dir=output,
        openalex_soft_stop_usd=0.01,
        model_soft_stop_usd=0.021,
        acknowledge_anonymous_daily_budget=True,
        acknowledge_model_budget=True,
        expected_implementation_sha256=implementation_hashes,
        provider_adapter_factory=lambda: provider,
        model_adapter_factory=lambda: model,
    )
    assert execution.overall_state == "partial"
    assert execution.stop_reason == "model_soft_stop"
    assert execution.openalex_request_count == 8
    assert execution.provider_candidate_count == 64
    assert execution.model_call_count == 21
    assert len(json.loads((output / "artifact-index.json").read_text())["files"]) == 56
    source_hashes = {
        name: _sha256((output / name).read_bytes())
        for name in diagnostic.CORE_SOURCE_FILES
    }
    observations = {
        field: getattr(execution, field)
        for field in diagnostic.EXPECTED_EXECUTION_OBSERVATIONS
    }
    return output, source_hashes, observations, implementation_hashes


@pytest.fixture
def source(tmp_path, monkeypatch, _frozen_source):  # noqa: ANN001, ANN202
    frozen, source_hashes, observations, implementation_hashes = _frozen_source
    copied = tmp_path / "source"
    shutil.copytree(frozen, copied)
    monkeypatch.setattr(
        diagnostic,
        "EXPECTED_SOURCE_FILE_SHA256",
        source_hashes,
    )
    monkeypatch.setattr(
        diagnostic,
        "EXPECTED_EXECUTION_OBSERVATIONS",
        observations,
    )
    # The production diagnostic must keep the exact historical v6 hash map.
    # This fixture instead creates a synthetic run from today's code, so its
    # source lock must use the identity that the synthetic manifest persisted.
    # Source hashes and observations above already follow the same boundary.
    monkeypatch.setattr(
        diagnostic,
        "EXPECTED_IMPLEMENTATION_SHA256",
        implementation_hashes,
    )
    return copied


def test_historical_implementation_identity_remains_frozen():
    """Synthetic fixture adaptation must not rewrite the real v6 identity."""
    assert (
        diagnostic.EXPECTED_IMPLEMENTATION_SHA256
        == development.EXPECTED_IMPLEMENTATION_SHA256
    )


def _lock(source: Path, tmp_path: Path) -> Path:
    path = tmp_path / "private" / "source-lock.json"
    create_source_lock(
        source,
        path,
        study_owner_id="offline-owner",
        confirm_authorized_output=True,
    )
    return path


def _packet(source: Path, tmp_path: Path) -> tuple[Path, Path]:
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "reviewer-packet"
    prepare_packet(source, source_lock, packet)
    return source_lock, packet


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(
    path: Path,
    fieldnames: tuple[str, ...],
    rows: list[dict[str, str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _complete_labels(packet: Path) -> list[dict[str, str]]:
    rows = _read_csv(packet / "labels.csv")
    for row in rows:
        required = json.loads(row["required_roles_json"])
        scope = json.loads(row["scope_roles_json"])
        supporting = json.loads(row["supporting_roles_json"])
        role_ids = [
            item["role_id"] for item in (*required, *scope, *supporting)
        ]
        row.update(
            {
                "direct_relevance": "YES",
                "baseline_novelty": "YES",
                "abstract_sufficient": "YES",
                "supported_role_ids_json": json.dumps(role_ids),
                "title_supported_role_ids_json": json.dumps(
                    [required[0]["role_id"]]
                ),
                "review_note": (
                    "The frozen title and abstract directly support the listed "
                    "roles and add evidence beyond the synthetic baseline."
                ),
            }
        )
    _write_csv(packet / "labels.csv", LABEL_FIELDS, rows)
    return rows


def _complete_declaration(
    packet: Path,
    *,
    ai_use: str = "NONE",
    reviewed_all: str = "YES",
) -> None:
    _write_csv(
        packet / "reviewer_declaration.csv",
        diagnostic.DECLARATION_FIELDS,
        [
            {
                "reviewer_id": "human-reviewer-01",
                "reviewed_all": reviewed_all,
                "generative_ai_use": ai_use,
                "external_sources_checked": "NONE",
                "elapsed_minutes": "45",
                "expertise": "Academic evidence synthesis",
                "completed_date": "2026-09-01",
                "limitations": "Frozen title and abstract text only.",
            }
        ],
    )


def test_packet_preserves_all_candidates_and_hides_every_v6_outcome(
    source,
    tmp_path,
):
    source_lock, packet = _packet(source, tmp_path)
    lock = json.loads(source_lock.read_text(encoding="utf-8"))
    manifest = json.loads(
        (packet / "packet_manifest.json").read_text(encoding="utf-8")
    )
    labels = _read_csv(packet / "labels.csv")

    assert lock["original_source_lock_readiness"] == "not_ready"
    assert lock["production_connected"] is False
    assert len(lock["indexed_file_sha256"]) == 56
    assert manifest["row_count"] == 64
    assert len(labels) == 64
    assert all(
        sum(row["case_id"] == case_id for row in labels) == 8
        for case_id in diagnostic.CASE_IDS
    )
    assert all(row["baseline_sources_json"] for row in labels)
    assert all(row["required_roles_json"] for row in labels)
    assert all(row["abstract"] for row in labels)
    assert not diagnostic._FORBIDDEN_REVIEWER_KEYS.intersection(  # noqa: SLF001
        diagnostic._walk_mapping_keys(manifest)  # noqa: SLF001
    )


def test_blank_packet_is_incomplete_not_a_zero_error_result(source, tmp_path):
    source_lock, packet = _packet(source, tmp_path)

    result = summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "incomplete"
    assert result["diagnostic_state"] == "not_evaluated"
    assert result["completed_row_count"] == 0
    assert len(result["incomplete_row_ids"]) == 64
    assert result["metrics"] is None
    assert result["v6_rescue_authorized"] is False
    assert result["z_cohort_authorized"] is False


def test_complete_review_joins_hidden_trace_only_at_summary(source, tmp_path):
    source_lock, packet = _packet(source, tmp_path)
    _complete_labels(packet)
    _complete_declaration(packet)

    result = summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "complete"
    assert result["diagnostic_state"] == "evaluated_diagnostic_only"
    assert result["production_connection_authorized"] is False
    metrics = result["metrics"]
    assert metrics["candidate_count"] == 64
    assert metrics["model_observed_candidate_count"] == 56
    assert metrics["model_unobserved_candidate_count"] == 8
    assert metrics["model_unobserved_case_ids"] == ["Y08"]
    assert metrics["human_coverable_case_ids"] == list(diagnostic.CASE_IDS)
    assert metrics["model_selected_case_ids"] == []
    assert metrics["model_missed_human_coverable_case_ids"] == list(
        diagnostic.CASE_IDS
    )
    assert metrics["role_confusion"]["false_negative"] == 280


def test_substantive_ai_review_is_retained_but_not_evaluated(source, tmp_path):
    source_lock, packet = _packet(source, tmp_path)
    _complete_labels(packet)
    _complete_declaration(packet, ai_use="MOST_OR_ALL")

    result = summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "excluded_substantive_ai"
    assert result["diagnostic_state"] == "not_evaluated"
    assert result["metrics"] is None
    assert result["declaration"]["generative_ai_use"] == "MOST_OR_ALL"


def test_source_lock_requires_explicit_owner_confirmation(source, tmp_path):
    with pytest.raises(
        RoleSlotFailureReviewError,
        match="authorized-output confirmation",
    ):
        create_source_lock(
            source,
            tmp_path / "lock.json",
            study_owner_id="offline-owner",
            confirm_authorized_output=False,
        )


def test_source_drift_after_lock_blocks_packet_preparation(source, tmp_path):
    source_lock = _lock(source, tmp_path)
    rows = source / "provider-rows.csv"
    rows.write_text(rows.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(RoleSlotFailureReviewError, match="identity drifted"):
        prepare_packet(source, source_lock, tmp_path / "packet")


def test_indexed_child_drift_blocks_source_validation(source, tmp_path):
    journal = source / "provider-journals" / "Y01.json"
    journal.write_text(
        journal.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RoleSlotFailureReviewError, match="indexed artifact"):
        create_source_lock(
            source,
            tmp_path / "lock.json",
            study_owner_id="offline-owner",
            confirm_authorized_output=True,
        )


def test_label_context_drift_is_rejected_even_with_all_identities(source, tmp_path):
    source_lock, packet = _packet(source, tmp_path)
    rows = _complete_labels(packet)
    rows[0]["abstract"] += " altered"
    _write_csv(packet / "labels.csv", LABEL_FIELDS, rows)
    _complete_declaration(packet)

    with pytest.raises(RoleSlotFailureReviewError, match="context or identity"):
        summarize_packet(source, source_lock, packet)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "supported_role_ids_json",
            '["unknown_role"]',
            "unknown role IDs",
        ),
        (
            "title_supported_role_ids_json",
            '["automotive_composite"]',
            "title-supported roles must be supported roles",
        ),
    ],
)
def test_unknown_or_non_subset_role_labels_are_rejected(
    source,
    tmp_path,
    field,
    value,
    message,
):
    source_lock, packet = _packet(source, tmp_path)
    rows = _complete_labels(packet)
    if field == "title_supported_role_ids_json":
        # The default completed fixture marks every declared role as supported.
        # Empty the parent set so this case actually re-injects the forbidden
        # title-only support relation instead of accidentally constructing a
        # valid subset and weakening the seam test.
        rows[0]["supported_role_ids_json"] = "[]"
    rows[0][field] = value
    _write_csv(packet / "labels.csv", LABEL_FIELDS, rows)
    _complete_declaration(packet)

    with pytest.raises(RoleSlotFailureReviewError, match=message):
        summarize_packet(source, source_lock, packet)


def test_packet_manifest_rejects_hidden_decision_leak(source, tmp_path):
    source_lock, packet = _packet(source, tmp_path)
    manifest_path = packet / "packet_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["rows"][0]["candidate_action"] = "KEEP"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RoleSlotFailureReviewError, match="leaks v6 decision"):
        summarize_packet(source, source_lock, packet)


def test_missing_serialized_candidate_fails_at_return_boundary(source, tmp_path):
    source_lock, packet = _packet(source, tmp_path)
    rows = _read_csv(packet / "labels.csv")
    _write_csv(packet / "labels.csv", LABEL_FIELDS, rows[:-1])

    with pytest.raises(RoleSlotFailureReviewError, match="identities drifted"):
        summarize_packet(source, source_lock, packet)


def test_frozen_real_source_identity_uses_complete_sha256_values():
    assert set(diagnostic.EXPECTED_SOURCE_FILE_SHA256) == set(
        diagnostic.CORE_SOURCE_FILES
    )
    assert all(
        len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
        for value in diagnostic.EXPECTED_SOURCE_FILE_SHA256.values()
    )


def test_production_worker_cannot_import_the_failure_review():
    worker = Path("src/academic_agent/pipeline_worker.py").read_text(
        encoding="utf-8"
    )
    assert "openalex_role_slot_failure_review" not in worker
