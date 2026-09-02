"""Zero-network source-lock and lane-blind review tests for v7."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import openalex_role_directed_live as live
import openalex_role_directed_review as review
from academic_agent.evidence_gap import ValidatedGapCall
from academic_agent.tools.evidence_search import (
    ToolAdapterResponse,
    ToolEvidenceCandidate,
    ToolProviderUsage,
)
from openalex_role_directed_unseen import (
    RetrievalLaneId,
    load_frozen_cases,
)


def _work_id(case_id: str, lane_id: RetrievalLaneId, index: int) -> str:
    lane_digit = 1 if lane_id == "technology_scope" else 2
    return f"https://openalex.org/W{int(case_id[2:]):02d}{lane_digit}{index:05d}"


def _candidate(
    case_id: str,
    lane_id: RetrievalLaneId,
    index: int,
) -> ToolEvidenceCandidate:
    if index == 0:
        # Different Works with one DOI prove that the review denominator comes
        # from the runner's DOI-first portfolio, not a test-side approximation.
        label = "shared DOI candidate"
        doi = f"10.5555/{case_id.casefold()}.review-shared"
    else:
        label = f"{lane_id} unique {index} candidate"
        doi = None
    return ToolEvidenceCandidate(
        title=f"{case_id} {label} for the frozen role review",
        url=_work_id(case_id, lane_id, index),
        doi=doi,
        publisher="OpenAlex zero-network role review fixture",
        evidence_summary=(
            f"This synthetic {lane_id} abstract for {case_id} is long enough "
            "to test immutable reviewer context without asserting source value."
        ),
        summary_source="abstract",
        citation_count=index + 1,
        provider_result_index=index,
    )


class ReviewFactory:
    """Return three deterministic rows for each of the sixteen frozen lanes."""

    def __init__(self) -> None:
        _, _, cases = load_frozen_cases("development")
        self.by_key = {
            call.idempotency_key: (case, lane.lane_id)
            for case in cases
            for lane, call in zip(case.spec.lanes, case.plan.calls, strict=True)
        }

    def __call__(self):
        def run(call: ValidatedGapCall) -> ToolAdapterResponse:
            case, lane_id = self.by_key[call.idempotency_key]
            candidates = tuple(
                _candidate(case.spec.case_id, lane_id, index)
                for index in range(3)
            )
            request_id = f"client-v7-review-{call.idempotency_key[:16]}"
            usage = ToolProviderUsage(
                provider="openalex",
                request_id=request_id,
                request_id_source="client_generated",
                result_count=len(candidates),
                cost_basis="reported_usd",
                reported_cost_usd=0.001,
            )
            return ToolAdapterResponse(
                tool="academic_search",
                idempotency_key=call.idempotency_key,
                candidates=candidates,
                search_cost_usd=0.001,
                provider_request_id=request_id,
                provider_usage=usage,
            )

        return run


def _source(tmp_path: Path, monkeypatch) -> Path:
    """Materialize a complete offline run and bind only test-local identities."""

    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    source = tmp_path / "role-directed-source"
    artifact = live.execute_live_study(
        output_dir=source,
        soft_stop_usd=0.02,
        acknowledge_anonymous_daily_budget=True,
        adapter_factory=ReviewFactory(),
    )
    hashes = {
        name: hashlib.sha256((source / name).read_bytes()).hexdigest()
        for name in review.SOURCE_FILES
    }
    monkeypatch.setattr(review, "EXPECTED_SOURCE_FILE_SHA256", hashes)
    monkeypatch.setattr(review, "EXPECTED_RUNNER_SHA256", artifact.runner_sha256)
    monkeypatch.setattr(review, "EXPECTED_REVIEW_ROW_COUNT", 40)
    monkeypatch.setattr(review, "EXPECTED_PROVIDER_ROW_COUNT", 48)
    monkeypatch.setattr(review, "EXPECTED_PROVIDER_CANDIDATE_COUNT", 48)
    monkeypatch.setattr(review, "EXPECTED_PROVIDER_REJECTION_COUNT", 0)
    monkeypatch.setattr(
        review,
        "EXPECTED_UNIQUE_PER_CASE",
        {case_id: 5 for case_id in review.CASE_IDS},
    )
    return source


def _lock(source: Path, tmp_path: Path) -> Path:
    path = tmp_path / "private" / "source-lock.json"
    review.create_source_lock(
        source,
        path,
        study_owner_id="offline-v7-review-owner",
        confirm_authorized_output=True,
        authorized_at=datetime(2026, 9, 2, 10, 0, tzinfo=UTC),
    )
    return path


def _write_csv(
    path: Path,
    fields: tuple[str, ...],
    rows: list[dict[str, str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _declaration(
    packet: Path,
    *,
    ai_use: str = "NONE",
    reviewed_all: str = "YES",
    external_sources_checked: str = "NONE",
) -> None:
    _write_csv(
        packet / "reviewer_declaration.csv",
        review.DECLARATION_FIELDS,
        [
            {
                "reviewer_id": "human-v7-reviewer",
                "reviewed_all": reviewed_all,
                "generative_ai_use": ai_use,
                "external_sources_checked": external_sources_checked,
                "elapsed_minutes": "90",
                "expertise": "academic evidence synthesis",
                "completed_date": "2026-09-02",
                "limitations": (
                    "Judgments use only the frozen titles, abstracts, and baseline."
                ),
            }
        ],
    )


def _role_groups(row: dict[str, str]) -> tuple[list[str], list[str], list[str]]:
    profile = json.loads(row["frozen_role_profile"])
    return tuple(
        [item["role_id"] for item in profile[field]]
        for field in ("required_roles", "scope_roles", "supporting_roles")
    )


def _candidate_kind(row: dict[str, str]) -> str:
    title = row["title"]
    if "shared DOI" in title:
        return "shared"
    if "technology_scope unique" in title:
        return "scope_unique"
    return "evidence_unique"


def _set_label(
    row: dict[str, str],
    *,
    relevant: str,
    novel: str,
    roles: list[str],
) -> None:
    row["directly_relevant"] = relevant
    row["baseline_novel"] = novel
    row["supported_role_ids"] = json.dumps(roles)
    row["review_note"] = (
        "The frozen title and abstract were compared with the visible baseline "
        "and role catalogue for this human judgment."
    )


def _complete_labels(packet: Path, *, strategy: str = "pass") -> None:
    with (packet / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        case_number = int(row["case_id"][2:])
        required, scope, supporting = _role_groups(row)
        kind = _candidate_kind(row)
        default_roles = (
            required + scope[:1]
            if kind == "shared"
            else [required[0]]
            if kind == "scope_unique"
            else [supporting[0]]
        )
        relevant, novel, roles = "YES", "YES", default_roles

        if strategy == "relevant_novel" and case_number > 5:
            novel = "NO"
        elif strategy == "human_coverable":
            if case_number <= 3 and kind == "scope_unique":
                roles = [supporting[0]]
            elif case_number > 5 and kind == "evidence_unique":
                roles = [required[0]]
        elif strategy == "candidate_precision":
            selected = (
                case_number <= 4
                and kind == "evidence_unique"
                and "unique 1" in row["title"]
            ) or (case_number in {5, 6} and kind == "shared")
            if selected:
                roles = required + scope[:1] + supporting[:1]
            else:
                relevant, novel, roles = "NO", "N/A", []
        elif strategy == "evidence_lane_value":
            if case_number > 2 and kind == "evidence_unique":
                relevant, novel, roles = "NO", "N/A", []
            elif case_number > 2 and kind == "scope_unique":
                roles = [supporting[0]]
        elif strategy == "coverability_gain" and kind == "scope_unique":
            roles = [supporting[0]]

        _set_label(
            row,
            relevant=relevant,
            novel=novel,
            roles=roles,
        )
    _write_csv(packet / "labels.csv", review.LABEL_FIELDS, rows)


def _packet(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    review.prepare_packet(source, source_lock, packet)
    return source, source_lock, packet


def test_source_lock_and_packet_preserve_all_rows_without_lane_provenance(
    tmp_path,
    monkeypatch,
):
    """All candidates reach the packet, while retrieval provenance does not."""

    source, source_lock, packet = _packet(tmp_path, monkeypatch)
    manifest = json.loads(
        (packet / "packet_manifest.json").read_text(encoding="utf-8")
    )
    lock = json.loads(source_lock.read_text(encoding="utf-8"))
    with (packet / "labels.csv").open(encoding="utf-8", newline="") as handle:
        labels = list(csv.DictReader(handle))

    assert len(manifest["rows"]) == len(labels) == 40
    assert len(manifest["case_contexts"]) == 8
    assert manifest["retrieval_lane_provenance_exposed"] is False
    assert manifest["external_source_access_required"] is False
    assert lock["source_file_sha256"] == review.EXPECTED_SOURCE_FILE_SHA256
    assert source_lock.parent != source
    assert all(
        field not in row
        for row in manifest["rows"]
        for field in review.HIDDEN_REVIEW_FIELDS
    )
    assert all(field not in labels[0] for field in review.HIDDEN_REVIEW_FIELDS)


def test_blank_packet_is_incomplete_not_a_zero_error_pass(tmp_path, monkeypatch):
    """A silent reviewer is explicitly unmeasured rather than successful."""

    source, source_lock, packet = _packet(tmp_path, monkeypatch)
    result = review.summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "incomplete"
    assert result["decision"] == "not_evaluated"
    assert result["completed_row_count"] == 0
    assert result["candidate_value_result"]["metrics"] is None
    assert result["ab_evaluation_eligible"] is False


def test_complete_review_passes_five_gates_without_external_page_access(
    tmp_path,
    monkeypatch,
):
    """The title/abstract protocol keeps external browsing optional."""

    source, source_lock, packet = _packet(tmp_path, monkeypatch)
    _complete_labels(packet)
    _declaration(packet, external_sources_checked="NONE")

    result = review.summarize_packet(source, source_lock, packet)
    metrics = result["candidate_value_result"]["metrics"]

    assert result["protocol_status"] == "complete"
    assert result["decision"] == "pass"
    assert set(
        result["candidate_value_result"]["threshold_results"].values()
    ) == {"pass"}
    assert metrics["reviewable_candidate_denominator"] == 40
    assert metrics["human_coverable_case_count"] == 8
    assert metrics["scope_only_coverable_case_count"] == 0
    assert metrics["coverability_gain_over_scope"] == 8
    assert metrics["unique_evidence_lane_value_case_count"] == 8
    assert result["retrieval_lane_provenance_joined_after_label_validation"] is True
    assert result["ab_evaluation_eligible"] is True
    assert result["production_connection_authorized"] is False


@pytest.mark.parametrize(
    ("strategy", "failed_gate"),
    [
        ("relevant_novel", "relevant_novel_cases"),
        ("human_coverable", "human_coverable_cases"),
        ("candidate_precision", "candidate_pool_precision"),
        ("evidence_lane_value", "unique_evidence_lane_value"),
        ("coverability_gain", "coverability_gain_over_scope"),
    ],
)
def test_each_frozen_gate_can_report_failure(
    tmp_path,
    monkeypatch,
    strategy,
    failed_gate,
):
    """Every frozen gate is computed and can veto the conjunctive decision."""

    source, source_lock, packet = _packet(tmp_path, monkeypatch)
    _complete_labels(packet, strategy=strategy)
    _declaration(packet)

    result = review.summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "complete"
    assert result["decision"] == "fail"
    thresholds = result["candidate_value_result"]["threshold_results"]
    assert thresholds[failed_gate] == "fail"
    if strategy != "relevant_novel":
        other_results = {
            key: value
            for key, value in thresholds.items()
            if key != failed_gate
        }
        assert set(other_results.values()) == {"pass"}


def test_substantive_ai_review_is_retained_but_not_evaluated(
    tmp_path,
    monkeypatch,
):
    source, source_lock, packet = _packet(tmp_path, monkeypatch)
    _complete_labels(packet)
    _declaration(packet, ai_use="MOST_OR_ALL")

    result = review.summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "excluded_substantive_ai"
    assert result["decision"] == "not_evaluated"
    assert result["completed_row_count"] == 40
    assert result["candidate_value_result"]["metrics"] is None


def test_unconfirmed_or_unverifiable_review_is_not_inspectable(
    tmp_path,
    monkeypatch,
):
    source, source_lock, packet = _packet(tmp_path, monkeypatch)
    _complete_labels(packet)
    with (packet / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    _set_label(
        rows[0],
        relevant="UNVERIFIABLE",
        novel="UNVERIFIABLE",
        roles=[],
    )
    _write_csv(packet / "labels.csv", review.LABEL_FIELDS, rows)
    _declaration(packet, reviewed_all="NO")

    result = review.summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "not_inspectable"
    assert result["decision"] == "not_evaluated"
    assert result["uninspectable_row_ids"] == [rows[0]["row_id"]]
    assert result["method_issues"] == ["reviewer_did_not_confirm_all_rows"]


def test_unknown_role_and_relevance_role_contradiction_fail_closed(
    tmp_path,
    monkeypatch,
):
    source, source_lock, packet = _packet(tmp_path, monkeypatch)
    _complete_labels(packet)
    _declaration(packet)
    with (packet / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    rows[0]["supported_role_ids"] = '["not_a_frozen_role"]'
    _write_csv(packet / "labels.csv", review.LABEL_FIELDS, rows)
    with pytest.raises(review.RoleDirectedReviewError, match="unknown supported"):
        review.summarize_packet(source, source_lock, packet)

    _complete_labels(packet)
    with (packet / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["directly_relevant"] = "NO"
    rows[0]["baseline_novel"] = "N/A"
    _write_csv(packet / "labels.csv", review.LABEL_FIELDS, rows)
    with pytest.raises(review.RoleDirectedReviewError, match="empty role array"):
        review.summarize_packet(source, source_lock, packet)


def test_source_and_packet_drift_fail_before_hidden_lineage_is_joined(
    tmp_path,
    monkeypatch,
):
    source, source_lock, packet = _packet(tmp_path, monkeypatch)
    _complete_labels(packet)
    _declaration(packet)

    manifest_path = packet / "packet_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["rows"][0]["lane_memberships"] = ["technology_scope"]
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        review.RoleDirectedReviewError,
        match="lane-blind projection",
    ):
        review.summarize_packet(source, source_lock, packet)

    manifest["rows"][0].pop("lane_memberships")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (packet / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["title"] += " changed"
    _write_csv(packet / "labels.csv", review.LABEL_FIELDS, rows)
    with pytest.raises(
        review.RoleDirectedReviewError,
        match="read-only context drifted",
    ):
        review.summarize_packet(source, source_lock, packet)


def test_source_byte_drift_fails_against_the_owner_lock(tmp_path, monkeypatch):
    source, source_lock, _ = _packet(tmp_path, monkeypatch)
    execution_path = source / "execution.json"
    execution_path.write_text(
        execution_path.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    with pytest.raises(review.RoleDirectedReviewError, match="identity drifted"):
        review.prepare_packet(source, source_lock, tmp_path / "drifted-packet")


def test_portfolio_lineage_drift_fails_before_source_lock(tmp_path, monkeypatch):
    source = _source(tmp_path, monkeypatch)
    portfolio_path = source / "case-portfolios" / "AA01.json"
    portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
    portfolio["lane_execution_sha256s"].reverse()
    portfolio_path.write_text(
        json.dumps(portfolio, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    hashes = {
        name: hashlib.sha256((source / name).read_bytes()).hexdigest()
        for name in review.SOURCE_FILES
    }
    monkeypatch.setattr(review, "EXPECTED_SOURCE_FILE_SHA256", hashes)
    with pytest.raises((review.RoleDirectedReviewError, ValueError)):
        review.validate_finalized_source(source)


def test_production_worker_and_provider_adapter_do_not_import_review_path():
    """The human-review module remains disconnected from production imports."""

    production_files = (
        Path("src/academic_agent/pipeline_worker.py"),
        Path("src/academic_agent/tools/anonymous_openalex_search.py"),
        Path("src/academic_agent/evidence_gap_execution.py"),
    )
    for path in production_files:
        assert "openalex_role_directed_review" not in path.read_text(
            encoding="utf-8"
        )
