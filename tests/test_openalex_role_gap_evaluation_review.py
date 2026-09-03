"""Zero-network source-lock and blind human-review seams for role-gap v8."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import openalex_role_gap_evaluation as live
import openalex_role_gap_evaluation_review as review
from academic_agent.evidence_gap import ValidatedGapCall
from academic_agent.tools.evidence_search import (
    ToolAdapterResponse,
    ToolEvidenceCandidate,
    ToolProviderUsage,
)
from openalex_role_gap_unseen import (
    PreparedRoleGapCase,
    RoleGapClosureOption,
    load_frozen_cases,
)


def _work_id(case_id: str, lane_id: live.LaneId, index: int) -> str:
    lane_digit = 1 if lane_id == "anchor_search" else 2
    return f"https://openalex.org/W{int(case_id[2:]):02d}{lane_digit}{index:05d}"


def _all_role_signal_text(case: PreparedRoleGapCase) -> str:
    phrases = [
        phrase
        for _, role in case.spec.roles.ordered_roles()
        for phrase in role.signal_groups[0]
    ]
    return f"This AD03 anchor contains every frozen role signal: {'; '.join(phrases)}."


def _candidate(
    case: PreparedRoleGapCase,
    lane_id: live.LaneId,
    index: int,
) -> ToolEvidenceCandidate:
    if index == 0:
        # Different Works share one DOI so the review denominator must come
        # from the production deduplicator rather than a test approximation.
        label = "shared DOI candidate"
        doi = f"10.5555/{case.spec.case_id.casefold()}.adaptive-review-shared"
    else:
        label = f"{lane_id} unique {index} candidate"
        doi = None
    summary = (
        _all_role_signal_text(case)
        if case.spec.case_id == "AD03" and lane_id == "anchor_search" and index == 0
        else (
            f"This synthetic {lane_id} abstract for {case.spec.case_id} is long "
            "enough to test immutable review context without asserting real "
            "source relevance or commercial value."
        )
    )
    return ToolEvidenceCandidate(
        title=f"{case.spec.case_id} {label} for adaptive review",
        url=_work_id(case.spec.case_id, lane_id, index),
        doi=doi,
        publisher="OpenAlex zero-network adaptive review fixture",
        evidence_summary=summary,
        summary_source="abstract",
        citation_count=index + 1,
        provider_result_index=index,
    )


class ReviewFactory:
    """Return three deterministic candidates for every selected v8 lane."""

    def __init__(self) -> None:
        _, _, cases = load_frozen_cases("unseen")
        self.by_key: dict[
            str,
            tuple[PreparedRoleGapCase, live.LaneId, RoleGapClosureOption | None],
        ] = {}
        for case in cases:
            self.by_key[case.anchor_call.idempotency_key] = (
                case,
                "anchor_search",
                None,
            )
            for option in case.closure_options:
                self.by_key[option.call.idempotency_key] = (
                    case,
                    "role_closure",
                    option,
                )

    def __call__(self):
        def run(call: ValidatedGapCall) -> ToolAdapterResponse:
            case, lane_id, _ = self.by_key[call.idempotency_key]
            candidates = tuple(_candidate(case, lane_id, index) for index in range(3))
            request_id = f"client-v8-review-{call.idempotency_key[:16]}"
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
    """Materialize one 15-request path and bind only test-local identities."""

    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    source = tmp_path / "role-gap-v8-source"
    artifact = live.execute_unseen_study(
        output_dir=source,
        soft_stop_usd=0.02,
        acknowledge_anonymous_daily_budget=True,
        adapter_factory=ReviewFactory(),
    )
    assert artifact.request_count == 15
    assert artifact.closure_request_count == 7
    routes = {
        item.case_id: item.decision.action for item in artifact.route_executions
    }
    assert routes["AD03"] == "abstain"
    assert {
        case_id for case_id, action in routes.items() if action == "search"
    } == set(review.EXPECTED_CLOSURE_CASE_IDS)

    monkeypatch.setattr(
        review,
        "EXPECTED_ARTIFACT_INDEX_SHA256",
        hashlib.sha256((source / "artifact-index.json").read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(review, "EXPECTED_RUNNER_SHA256", artifact.runner_sha256)
    monkeypatch.setattr(review, "EXPECTED_PROVIDER_ROW_COUNT", 45)
    monkeypatch.setattr(review, "EXPECTED_PROVIDER_CANDIDATE_COUNT", 45)
    monkeypatch.setattr(review, "EXPECTED_PROVIDER_REJECTION_COUNT", 0)
    monkeypatch.setattr(review, "EXPECTED_REVIEW_ROW_COUNT", 38)
    monkeypatch.setattr(
        review,
        "EXPECTED_UNIQUE_PER_CASE",
        {case_id: (3 if case_id == "AD03" else 5) for case_id in review.CASE_IDS},
    )
    return source


def test_middle_abstention_preserves_exact_closure_case_set(
    tmp_path,
    monkeypatch,
):
    """AD03 abstains while AD08 closes; positional AC assumptions must fail."""

    source = _source(tmp_path, monkeypatch)

    assert not (source / "lane-executions" / "AD03--role_closure.json").exists()
    assert (source / "lane-executions" / "AD08--role_closure.json").is_file()
    snapshot = review.validate_finalized_source(source)
    assert len(snapshot.candidates) == 38


def _lock(source: Path, tmp_path: Path) -> Path:
    path = tmp_path / "private" / "source-lock.json"
    review.create_source_lock(
        source,
        path,
        study_owner_id="offline-v8-review-owner",
        confirm_authorized_output=True,
        authorized_at=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
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
                "reviewer_id": "human-v8-reviewer",
                "reviewed_all": reviewed_all,
                "generative_ai_use": ai_use,
                "external_sources_checked": external_sources_checked,
                "elapsed_minutes": "90",
                "expertise": "academic evidence synthesis",
                "completed_date": "2026-09-03",
                "limitations": (
                    "Judgments use only the frozen titles, abstracts, and baseline."
                ),
            }
        ],
    )


def _role_ids(row: dict[str, str]) -> list[str]:
    profile = json.loads(row["frozen_role_profile"])
    return [
        item["role_id"]
        for field in ("required_roles", "scope_roles", "supporting_roles")
        for item in profile[field]
    ]


def _hidden_source_rows(source: Path) -> dict[tuple[str, str], dict[str, str]]:
    with (source / "candidate-review.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    return {
        (row["case_id"], row["unique_candidate_sha256"]): row for row in rows
    }


def _selected_roles(source: Path) -> dict[str, str]:
    with (source / "case-review.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        return {
            row["case_id"]: row["selected_role_id"] for row in csv.DictReader(handle)
        }


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


def _complete_labels(
    packet: Path,
    source: Path,
    *,
    strategy: str = "pass",
) -> None:
    with (packet / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    hidden = _hidden_source_rows(source)
    selected_by_case = _selected_roles(source)
    for row in rows:
        case_id = row["case_id"]
        case_number = int(case_id[2:])
        roles = _role_ids(row)
        selected_role = selected_by_case[case_id]
        lineage = hidden[(case_id, row["unique_candidate_sha256"])]
        lanes = tuple(json.loads(lineage["lane_memberships"]))

        if case_id == "AD03":
            supported = roles if "shared DOI" in row["title"] else [roles[0]]
        elif lanes == ("role_closure",):
            # One closure-only row can form a compact union cover and proves
            # incremental selected-role value without counting a duplicate.
            supported = roles
        else:
            supported = [role for role in roles if role != selected_role]
        relevant, novel = "YES", "YES"

        if strategy == "relevant_novel" and case_number <= 3:
            novel = "NO"
        elif strategy == "candidate_precision" and case_number > 1:
            relevant, novel, supported = "NO", "N/A", []
        elif (
            strategy == "routing"
            and case_id in {"AD01", "AD02", "AD04"}
            and "anchor_search" in lanes
        ):
            supported = roles
        elif (
            strategy == "closure_value"
            and case_id in {"AD01", "AD02", "AD04", "AD05"}
            and lanes == ("role_closure",)
        ):
            relevant, novel, supported = "NO", "N/A", []
        elif strategy == "human_coverable" and case_number <= 3:
            supported = [roles[0]]
        elif strategy == "coverability_gain" and case_number <= 7 and (
            "anchor_search" in lanes
        ):
            supported = roles

        _set_label(
            row,
            relevant=relevant,
            novel=novel,
            roles=supported,
        )
    _write_csv(packet / "labels.csv", review.LABEL_FIELDS, rows)


def _packet(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    review.prepare_packet(source, source_lock, packet)
    return source, source_lock, packet


def test_source_lock_and_packet_preserve_rows_without_adaptive_provenance(
    tmp_path,
    monkeypatch,
):
    """All candidates reach the packet but route answers never do."""

    source, source_lock, packet = _packet(tmp_path, monkeypatch)
    manifest = json.loads(
        (packet / "packet_manifest.json").read_text(encoding="utf-8")
    )
    with (packet / "labels.csv").open(encoding="utf-8", newline="") as handle:
        labels = list(csv.DictReader(handle))

    assert len(manifest["rows"]) == len(labels) == 38
    assert len(manifest["case_contexts"]) == 8
    assert manifest["retrieval_lane_provenance_exposed"] is False
    assert manifest["mechanical_route_exposed"] is False
    assert manifest["ad_cohort_opened"] is True
    assert source_lock.parent != source
    assert all(
        field not in row
        for row in manifest["rows"]
        for field in review.HIDDEN_REVIEW_FIELDS
    )
    assert all(field not in labels[0] for field in review.HIDDEN_REVIEW_FIELDS)


def test_blank_packet_is_incomplete_and_keeps_route_hidden(tmp_path, monkeypatch):
    """No labels is unmeasured, not a zero-error route-value pass."""

    source, source_lock, packet = _packet(tmp_path, monkeypatch)
    result = review.summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "incomplete"
    assert result["decision"] == "not_evaluated"
    assert result["completed_row_count"] == 0
    assert result["role_gap_result"]["metrics"] is None
    assert result["route_assessments_after_unblinding"] is None
    assert result["adaptive_provenance_joined_after_label_validation"] is False
    assert result["post_ad_studies_eligible"] is False


def test_complete_review_passes_six_gates_then_joins_route(tmp_path, monkeypatch):
    """The route becomes inspectable only after every human label is valid."""

    source, source_lock, packet = _packet(tmp_path, monkeypatch)
    _complete_labels(packet, source)
    _declaration(packet, external_sources_checked="NONE")

    result = review.summarize_packet(source, source_lock, packet)
    metrics = result["role_gap_result"]["metrics"]

    assert result["protocol_status"] == "complete"
    assert result["decision"] == "pass"
    assert set(result["role_gap_result"]["threshold_results"].values()) == {
        "pass"
    }
    assert metrics["reviewable_candidate_denominator"] == 38
    assert metrics["human_correct_routing_case_count"] == 8
    assert metrics["selected_role_closure_value_case_count"] == 7
    assert metrics["union_human_coverable_case_count"] == 8
    assert metrics["anchor_human_coverable_case_count"] == 1
    assert metrics["coverability_gain_over_anchor"] == 7
    assert len(result["route_assessments_after_unblinding"]) == 8
    assert result["adaptive_provenance_joined_after_label_validation"] is True
    assert result["mechanical_route_exposed_to_reviewer"] is False
    assert result["reviewer_declaration_raw"]["elapsed_minutes"] == "90"
    assert result["post_ad_studies_eligible"] is True
    assert result["production_connection_authorized"] is False


@pytest.mark.parametrize(
    ("strategy", "failed_gate"),
    [
        ("relevant_novel", "relevant_novel_cases"),
        ("candidate_precision", "candidate_pool_precision"),
        ("routing", "human_correct_routing_decisions"),
        ("closure_value", "selected_role_closure_value"),
        ("human_coverable", "human_coverable_cases"),
        ("coverability_gain", "coverability_gain_over_anchor"),
    ],
)
def test_each_frozen_gate_can_veto_the_conjunctive_decision(
    tmp_path,
    monkeypatch,
    strategy,
    failed_gate,
):
    source, source_lock, packet = _packet(tmp_path, monkeypatch)
    _complete_labels(packet, source, strategy=strategy)
    _declaration(packet)

    result = review.summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "complete"
    assert result["decision"] == "fail"
    assert result["role_gap_result"]["threshold_results"][failed_gate] == "fail"
    assert result["post_ad_studies_eligible"] is False


def test_substantive_ai_review_is_preserved_but_not_evaluated(
    tmp_path,
    monkeypatch,
):
    source, source_lock, packet = _packet(tmp_path, monkeypatch)
    _complete_labels(packet, source)
    _declaration(packet, ai_use="MOST_OR_ALL")

    result = review.summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "excluded_substantive_ai"
    assert result["decision"] == "not_evaluated"
    assert result["completed_row_count"] == 38
    assert result["reviewer_declaration_raw"]["generative_ai_use"] == "MOST_OR_ALL"
    assert result["route_assessments_after_unblinding"] is None


def test_unconfirmed_or_unverifiable_review_is_not_inspectable(
    tmp_path,
    monkeypatch,
):
    source, source_lock, packet = _packet(tmp_path, monkeypatch)
    _complete_labels(packet, source)
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
    _complete_labels(packet, source)
    _declaration(packet)
    with (packet / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    rows[0]["supported_role_ids"] = '["not_a_frozen_role"]'
    _write_csv(packet / "labels.csv", review.LABEL_FIELDS, rows)
    with pytest.raises(review.RoleGapReviewError, match="unknown supported"):
        review.summarize_packet(source, source_lock, packet)

    _complete_labels(packet, source)
    with (packet / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["directly_relevant"] = "NO"
    rows[0]["baseline_novel"] = "N/A"
    _write_csv(packet / "labels.csv", review.LABEL_FIELDS, rows)
    with pytest.raises(review.RoleGapReviewError, match="empty role array"):
        review.summarize_packet(source, source_lock, packet)


def test_packet_and_label_drift_fail_before_adaptive_join(tmp_path, monkeypatch):
    source, source_lock, packet = _packet(tmp_path, monkeypatch)
    _complete_labels(packet, source)
    _declaration(packet)

    manifest_path = packet / "packet_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["rows"][0]["frozen_route_decision"] = {"action": "search"}
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(review.RoleGapReviewError, match="blind projection"):
        review.summarize_packet(source, source_lock, packet)

    manifest["rows"][0].pop("frozen_route_decision")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (packet / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["title"] += " changed"
    _write_csv(packet / "labels.csv", review.LABEL_FIELDS, rows)
    with pytest.raises(review.RoleGapReviewError, match="read-only context drifted"):
        review.summarize_packet(source, source_lock, packet)


def test_source_byte_drift_fails_against_owner_lock(tmp_path, monkeypatch):
    source, source_lock, _ = _packet(tmp_path, monkeypatch)
    execution_path = source / "execution.json"
    execution_path.write_text(
        execution_path.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    with pytest.raises(review.RoleGapReviewError, match="artifact index"):
        review.prepare_packet(source, source_lock, tmp_path / "drifted-packet")


def test_production_worker_and_provider_adapter_do_not_import_review_path():
    """The human-review path remains disconnected from production imports."""

    production_files = (
        Path("src/academic_agent/pipeline_worker.py"),
        Path("src/academic_agent/tools/anonymous_openalex_search.py"),
        Path("src/academic_agent/evidence_gap_execution.py"),
    )
    for path in production_files:
        assert "openalex_role_gap_evaluation_review" not in path.read_text(encoding="utf-8")
