"""Zero-network source-lock and Schema v2 review tests for Phase 4."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from academic_agent.evidence_gap import ValidatedGapCall
from academic_agent.tools.evidence_search import (
    ToolAdapterResponse,
    ToolEvidenceCandidate,
    ToolProviderUsage,
)
from evidence_gap_phase4_live import execute_live_study
from evidence_gap_phase4_review import (
    DECLARATION_FIELDS,
    REVIEW_FIELDS,
    Phase4ReviewError,
    create_source_lock,
    prepare_packet,
    summarize_packet,
)


def _response(
    call: ValidatedGapCall,
    provider: str,
    *,
    openalex_cost: float,
    off_topic: bool,
) -> ToolAdapterResponse:
    if provider == "openalex":
        title = f"{call.query} controlled experimental study"
        url = f"https://openalex.org/W{call.idempotency_key[:12]}"
        publisher = "OpenAlex test journal"
        summary = (
            f"Experimental evidence directly measures {call.query} under "
            "controlled conditions and reports comparative performance."
        )
    else:
        title = f"{call.query} patent claims and apparatus"
        url = f"https://lens.org/lens/patent/{call.idempotency_key[:20]}"
        publisher = "US patent record"
        summary = (
            f"The patent abstract directly describes {call.query}, including "
            "claim scope, materials, apparatus and operating conditions."
        )
    if off_topic:
        title = "Unrelated municipal archive catalog record"
        summary = (
            "This catalog entry describes historical municipal meeting minutes "
            "and contains no scientific, technical, or patent evidence."
        )
    candidate = ToolEvidenceCandidate(
        title=title,
        url=url,
        publisher=publisher,
        evidence_summary=summary,
        summary_source="abstract",
        provider_result_index=0,
    )
    usage = ToolProviderUsage(
        provider=provider,
        request_id=f"client-{provider}-{call.idempotency_key[:12]}",
        request_id_source="client_generated",
        result_count=1,
        cost_basis=("reported_usd" if provider == "openalex" else "uninspectable"),
        reported_cost_usd=(openalex_cost if provider == "openalex" else None),
    )
    return ToolAdapterResponse(
        tool=call.tool,
        idempotency_key=call.idempotency_key,
        candidates=(candidate,),
        search_cost_usd=(openalex_cost if provider == "openalex" else None),
        provider_request_id=usage.request_id,
        provider_usage=usage,
    )


class ReviewFixtureFactory:
    def __init__(
        self,
        *,
        openalex_cost: float = 0.0001,
        off_topic: bool = False,
    ) -> None:
        self.openalex_cost = openalex_cost
        self.off_topic = off_topic

    def __call__(self):
        def adapter(provider: str):
            return lambda call: _response(
                call,
                provider,
                openalex_cost=self.openalex_cost,
                off_topic=self.off_topic,
            )

        return {
            "openalex": adapter("openalex"),
            "lens": adapter("lens"),
        }


def _source(
    tmp_path: Path,
    *,
    openalex_cost: float = 0.0001,
    off_topic: bool = False,
) -> Path:
    source = tmp_path / "source"
    execute_live_study(
        output_dir=source,
        openalex_soft_stop_usd=0.01,
        acknowledge_lens_cost_uninspectable=True,
        adapter_factory=ReviewFixtureFactory(
            openalex_cost=openalex_cost,
            off_topic=off_topic,
        ),
    )
    return source


def _lock(source: Path, tmp_path: Path) -> Path:
    path = tmp_path / "source-lock.json"
    create_source_lock(
        source,
        path,
        study_owner_id="offline-study-owner",
        confirm_authorized_output=True,
        authorized_at=datetime(2026, 8, 26, 8, 0, tzinfo=UTC),
    )
    return path


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _complete_declaration(packet: Path, *, ai_use: str = "NONE") -> None:
    _write_csv(
        packet / "reviewer_declaration.csv",
        DECLARATION_FIELDS,
        [
            {
                "reviewer_id": "human-reviewer-1",
                "reviewed_all": "YES",
                "generative_ai_use": ai_use,
                "external_sources_checked": "ALL_ATTEMPTED",
                "elapsed_minutes": "45",
                "expertise": "academic and patent evidence review",
                "completed_date": "2026-08-26",
                "limitations": "Synthetic baseline only.",
            }
        ],
    )


def _complete_labels(
    packet: Path,
    *,
    relevant: str = "YES",
    novel: str = "YES",
) -> None:
    with (packet / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["relevant"] = relevant
        row["novel"] = novel
        row["review_note"] = (
            "The external source record directly addresses the declared evidence "
            "gap and adds material detail absent from the frozen baseline."
        )
    _write_csv(packet / "labels.csv", REVIEW_FIELDS, rows)


def test_source_lock_and_packet_preserve_every_identity_and_baseline(tmp_path):
    source = _source(tmp_path)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"

    manifest = prepare_packet(source, source_lock, packet)

    assert manifest["schema_version"] == 2
    assert manifest["production_connected"] is False
    assert len(manifest["baseline_contexts"]) == 8
    assert len(manifest["rows"]) == 8
    assert {row["provider"] for row in manifest["rows"]} == {
        "openalex",
        "lens",
    }
    assert all(
        context["baseline_sources"] for context in manifest["baseline_contexts"]
    )
    assert (packet / "README.md").is_file()


def test_blank_packet_is_incomplete_not_a_zero_error_pass(tmp_path):
    source = _source(tmp_path)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)

    result = summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "incomplete"
    assert result["decision"] == "not_evaluated"
    assert result["completed_row_count"] == 0
    assert result["planner_trigger_study_eligible"] is False
    assert result["production_connection_authorized"] is False


def test_complete_human_labels_apply_both_provider_gates_without_production_authority(
    tmp_path,
):
    source = _source(tmp_path)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)
    _complete_labels(packet)
    _complete_declaration(packet)

    result = summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "complete"
    assert result["decision"] == "pass"
    assert result["provider_results"]["openalex"]["decision"] == "pass"
    assert result["provider_results"]["lens"]["decision"] == "pass"
    assert result["planner_trigger_study_eligible"] is True
    assert result["production_connection_authorized"] is False


def test_substantive_ai_review_is_retained_but_not_evaluated(tmp_path):
    source = _source(tmp_path)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)
    _complete_labels(packet)
    _complete_declaration(packet, ai_use="MOST_OR_ALL")

    result = summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "excluded_substantive_ai"
    assert result["decision"] == "not_evaluated"
    assert result["reviewer_declaration"]["generative_ai_use"] == "MOST_OR_ALL"


def test_zero_accepted_candidates_is_an_explicit_provider_failure(tmp_path):
    source = _source(tmp_path, off_topic=True)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    manifest = prepare_packet(source, source_lock, packet)
    assert manifest["row_count"] == 0
    _complete_declaration(packet)

    result = summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "complete"
    assert result["decision"] == "fail"
    for provider in ("openalex", "lens"):
        provider_result = result["provider_results"][provider]
        assert provider_result["metrics"]["accepted_candidate_count"] == 0
        assert provider_result["metrics"]["wrong_source_rate"] is None
        assert set(provider_result["threshold_results"].values()) == {"fail"}


def test_partial_live_execution_cannot_be_locked_for_human_value(tmp_path):
    source = _source(tmp_path, openalex_cost=0.02)

    with pytest.raises(Phase4ReviewError, match="completed eight-case run"):
        create_source_lock(
            source,
            tmp_path / "partial-lock.json",
            study_owner_id="offline-study-owner",
            confirm_authorized_output=True,
        )


def test_source_lock_requires_explicit_owner_confirmation(tmp_path):
    source = _source(tmp_path)

    with pytest.raises(Phase4ReviewError, match="explicit authorized-output"):
        create_source_lock(
            source,
            tmp_path / "forbidden-lock.json",
            study_owner_id="offline-study-owner",
            confirm_authorized_output=False,
        )


def test_source_drift_after_lock_is_rejected_at_packet_boundary(tmp_path):
    source = _source(tmp_path)
    source_lock = _lock(source, tmp_path)
    with (source / "candidates.csv").open("a", encoding="utf-8") as handle:
        handle.write("\n")

    with pytest.raises(Phase4ReviewError, match="source artifact identity drifted"):
        prepare_packet(source, source_lock, tmp_path / "packet")


def test_packet_baseline_context_drift_is_rejected_before_labels(tmp_path):
    source = _source(tmp_path)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)
    manifest_path = packet / "packet_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["baseline_contexts"][0]["gap_state"] = "fabricated clean baseline"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(Phase4ReviewError, match="baseline context drifted"):
        summarize_packet(source, source_lock, packet)


def test_label_identity_drift_is_rejected_even_when_counts_match(tmp_path):
    source = _source(tmp_path)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)
    with (packet / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["title"] = "Changed title with the same row count"
    _write_csv(packet / "labels.csv", REVIEW_FIELDS, rows)

    with pytest.raises(Phase4ReviewError, match="label identity drifted"):
        summarize_packet(source, source_lock, packet)


def test_case_journal_drift_prevents_source_lock(tmp_path):
    source = _source(tmp_path)
    journal = source / "case-executions" / "D01.json"
    payload = json.loads(journal.read_text(encoding="utf-8"))
    payload["plan_sha256"] = "0" * 64
    journal.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(Phase4ReviewError, match="case journal does not match"):
        create_source_lock(
            source,
            tmp_path / "journal-drift-lock.json",
            study_owner_id="offline-study-owner",
            confirm_authorized_output=True,
        )


def test_packet_measurement_limit_drift_is_rejected(tmp_path):
    source = _source(tmp_path)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)
    manifest_path = packet / "packet_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["measurement_limit"] = "This study proves production utility."
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(Phase4ReviewError, match="measurement limit drifted"):
        summarize_packet(source, source_lock, packet)


def test_provider_lineage_mismatch_prevents_source_lock(tmp_path):
    source = _source(tmp_path)
    execution_path = source / "execution.json"
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    call = execution["cases"][0]["audit"]["call_audits"][0]
    call["provider_usage"]["provider"] = "lens"
    execution_text = (
        json.dumps(execution, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    execution_path.write_text(execution_text, encoding="utf-8")

    journal_path = source / "case-executions" / "D01.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal_call = journal["audit"]["call_audits"][0]
    journal_call["provider_usage"]["provider"] = "lens"
    journal_path.write_text(
        json.dumps(journal, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    index_path = source / "artifact-index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["source_file_sha256"]["execution.json"] = hashlib.sha256(
        execution_path.read_bytes()
    ).hexdigest()
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(Phase4ReviewError, match="provider accounting is invalid"):
        create_source_lock(
            source,
            tmp_path / "provider-lineage-lock.json",
            study_owner_id="offline-study-owner",
            confirm_authorized_output=True,
        )
