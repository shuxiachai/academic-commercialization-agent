"""Zero-network seams for the post-outcome scope-link v4 diagnostic."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import openalex_scope_link_abstention_review as diagnostic
from academic_agent.evidence_gap import ValidatedGapCall
from academic_agent.openalex_claim_scope import OpenAlexClaimScopeCandidate
from academic_agent.tools.evidence_search import ToolEvidenceCandidate, ToolProviderUsage
from academic_agent.tools.openalex_claim_scope_search import (
    OpenAlexClaimScopeAdapterResponse,
)
from openalex_scope_link_abstention_review import (
    DECLARATION_FIELDS,
    LABEL_FIELDS,
    ScopeLinkDiagnosticError,
    create_source_lock,
    prepare_packet,
    summarize_packet,
)
from openalex_scope_link_live import execute_live_study
from openalex_scope_link_unseen import PreparedScopeLinkCase, load_frozen_cases


class _LegacyEncodedStdout:
    """Expose an ASCII text facade plus a byte buffer like Windows stdout."""

    def __init__(self) -> None:
        self.buffer = io.BytesIO()

    def write(self, text: str) -> int:
        text.encode("ascii")
        return len(text)


def _candidate(
    case: PreparedScopeLinkCase,
    index: int,
) -> OpenAlexClaimScopeCandidate:
    """Build a row that contains every concept but no same-segment relation."""

    required = [
        group.text_phrases[0] for group in case.spec.profile.required_groups
    ]
    scope = [group.text_phrases[0] for group in case.spec.profile.scope_groups]
    supporting = [
        group.text_phrases[0]
        for group in case.spec.profile.supporting_groups[
            : case.spec.profile.minimum_supporting_groups
        ]
    ]
    return OpenAlexClaimScopeCandidate(
        evidence=ToolEvidenceCandidate(
            title=f"{' '.join(required)} controlled review {index}",
            url=(
                f"https://openalex.org/W{case.spec.case_id[1:]}"
                f"{index + 1:07d}"
            ),
            publisher="OpenAlex zero-network abstention diagnostic fixture",
            evidence_summary=(
                f"{' '.join(scope)}. {' '.join(supporting)}. "
                "Required and scope concepts remain in separate sentences."
            ),
            summary_source="abstract",
            provider_result_index=index,
        ),
        aboutness=(),
    )


class DiagnosticFactory:
    """Return eight deterministic ABSTAIN rows for every frozen case."""

    def __init__(self) -> None:
        _, _, cases = load_frozen_cases()
        self.case_by_key = {
            case.plan.calls[0].idempotency_key: case for case in cases
        }

    def __call__(self):
        def run(call: ValidatedGapCall) -> OpenAlexClaimScopeAdapterResponse:
            case = self.case_by_key[call.idempotency_key]
            candidates = tuple(_candidate(case, index) for index in range(8))
            request_id = (
                f"client-openalex-diagnostic-{case.spec.case_id.casefold()}"
            )
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
                candidates=candidates,
                search_cost_usd=0.001,
                provider_request_id=request_id,
                provider_usage=usage,
            )

        return run


def _source(tmp_path: Path, monkeypatch) -> Path:
    """Materialize the exact 8x8 shape and bind test-local source hashes."""

    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    source = tmp_path / "scope-link-v4-source"
    execution = execute_live_study(
        output_dir=source,
        soft_stop_usd=0.01,
        acknowledge_anonymous_daily_budget=True,
        adapter_factory=DiagnosticFactory(),
    )
    assert execution.scope_link_accepted_candidate_count == 0
    assert execution.scope_link_abstained_candidate_count == 64
    hashes = {
        name: hashlib.sha256((source / name).read_bytes()).hexdigest()
        for name in diagnostic.SOURCE_FILES
    }
    monkeypatch.setattr(diagnostic, "EXPECTED_SOURCE_FILE_SHA256", hashes)
    # The real execution contains one row with a link that fails another
    # requirement.  The synthetic source isolates the link rule on all 64 rows,
    # so its test-local frozen denominator is intentionally different.
    monkeypatch.setattr(diagnostic, "EXPECTED_MISSING_SCOPE_LINK_COUNT", 64)
    return source


def _lock(source: Path, tmp_path: Path) -> Path:
    path = tmp_path / "private" / "diagnostic-source-lock.json"
    create_source_lock(
        source,
        path,
        study_owner_id="offline-scope-link-owner",
        confirm_authorized_output=True,
        authorized_at=datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
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
    fields: tuple[str, ...],
    rows: list[dict[str, str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _complete_declaration(
    packet: Path,
    *,
    ai_use: str = "NONE",
    reviewed_all: str = "YES",
    external_sources_checked: str = "NONE",
) -> None:
    _write_csv(
        packet / "reviewer_declaration.csv",
        DECLARATION_FIELDS,
        [
            {
                "reviewer_id": "human-diagnostic-reviewer",
                "reviewed_all": reviewed_all,
                "generative_ai_use": ai_use,
                "external_sources_checked": external_sources_checked,
                "elapsed_minutes": "180",
                "expertise": "Academic evidence synthesis",
                "completed_date": "2026-08-29",
                "limitations": "Judged from the frozen title and abstract text.",
            }
        ],
    )


def _complete_labels(
    packet: Path,
    *,
    semantic: str = "YES",
    novelty: str = "YES",
) -> list[dict[str, str]]:
    rows = _read_csv(packet / "labels.csv")
    for row in rows:
        row.update(
            {
                "direct_relevance": "YES",
                "semantic_scope_link": semantic,
                "baseline_novelty": novelty,
                "abstract_sufficient": "YES",
                "review_note": (
                    "The frozen abstract directly addresses the declared topic "
                    "and supports this human diagnostic label."
                ),
            }
        )
    _write_csv(packet / "labels.csv", LABEL_FIELDS, rows)
    return rows


def test_packet_preserves_all_rows_and_hides_every_v4_decision_signal(
    tmp_path,
    monkeypatch,
):
    source = _source(tmp_path, monkeypatch)
    source_lock, packet = _packet(source, tmp_path)

    lock_payload = json.loads(source_lock.read_text(encoding="utf-8"))
    manifest = json.loads(
        (packet / "packet_manifest.json").read_text(encoding="utf-8")
    )
    label_text = (packet / "labels.csv").read_text(encoding="utf-8")
    manifest_text = (packet / "packet_manifest.json").read_text(encoding="utf-8")
    labels = _read_csv(packet / "labels.csv")

    assert lock_payload["original_source_value_state"] == "not_evaluated"
    assert lock_payload["production_connected"] is False
    assert manifest["row_count"] == 64
    assert len(labels) == 64
    assert {row["case_id"] for row in labels} == set(diagnostic.CASE_IDS)
    assert all(
        sum(row["case_id"] == case_id for row in labels) == 8
        for case_id in diagnostic.CASE_IDS
    )
    assert all(row["evidence_summary"] for row in labels)
    assert all(row["baseline_sources_json"] for row in labels)
    forbidden_values = (
        "scope_link_action",
        "abstention_reasons",
        "missing_scope_link",
        "link_evidence",
        "ABSTAIN",
    )
    assert all(value not in label_text for value in forbidden_values)
    assert all(value not in manifest_text for value in forbidden_values)


def test_blank_packet_is_incomplete_not_a_zero_error_result(tmp_path, monkeypatch):
    source = _source(tmp_path, monkeypatch)
    source_lock, packet = _packet(source, tmp_path)

    result = summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "incomplete"
    assert result["diagnostic_state"] == "not_evaluated"
    assert result["completed_row_count"] == 0
    assert len(result["incomplete_row_ids"]) == 64
    assert result["metrics"] is None
    assert result["original_source_value_state"] == "not_evaluated"
    assert result["v5_validation_authorized"] is False


def test_complete_labels_join_hidden_trace_only_at_summary(tmp_path, monkeypatch):
    source = _source(tmp_path, monkeypatch)
    source_lock, packet = _packet(source, tmp_path)
    _complete_labels(packet)
    _complete_declaration(packet, external_sources_checked="NONE")

    result = summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "complete"
    assert result["diagnostic_state"] == "evaluated"
    assert result["production_connected"] is False
    assert result["completed_row_count"] == 64
    metrics = result["metrics"]
    assert metrics["direct_relevant_count"] == 64
    assert metrics["human_semantic_link_count"] == 64
    assert metrics["semantic_link_miss_count"] == 64
    assert metrics["semantic_link_miss_rate_among_human_links"] == 1.0
    assert metrics["v4_reason_counts"] == {"missing_scope_link": 64}
    assert metrics["attribution_counts"] == {
        "semantic_relation_missed_by_v4": 64
    }
    assert result["declaration"]["external_sources_checked"] == "NONE"


def test_diagnostic_keeps_noise_and_unverifiable_rows_in_denominators(
    tmp_path,
    monkeypatch,
):
    source = _source(tmp_path, monkeypatch)
    source_lock, packet = _packet(source, tmp_path)
    rows = _complete_labels(packet)
    rows[0].update(
        {
            "direct_relevance": "NO",
            "semantic_scope_link": "N/A",
            "baseline_novelty": "N/A",
            "abstract_sufficient": "YES",
            "review_note": (
                "The abstract shares a broad field but does not address the "
                "declared technical topic."
            ),
        }
    )
    rows[1].update(
        {
            "direct_relevance": "UNVERIFIABLE",
            "semantic_scope_link": "UNVERIFIABLE",
            "baseline_novelty": "UNVERIFIABLE",
            "abstract_sufficient": "NO",
            "review_note": (
                "The frozen abstract is insufficient to determine direct "
                "relevance or the requested semantic relation."
            ),
        }
    )
    rows[2].update(
        {
            "semantic_scope_link": "NO",
            "review_note": (
                "The source is relevant to the field but does not connect the "
                "required technology to the declared scope."
            ),
        }
    )
    _write_csv(packet / "labels.csv", LABEL_FIELDS, rows)
    _complete_declaration(packet)

    metrics = summarize_packet(source, source_lock, packet)["metrics"]

    assert metrics["candidate_count"] == 64
    assert metrics["inspectable_candidate_count"] == 63
    assert metrics["direct_relevant_count"] == 62
    assert metrics["direct_irrelevant_count"] == 1
    assert metrics["unverifiable_count"] == 1
    assert metrics["retrieval_noise_rate_among_inspectable"] == pytest.approx(
        1 / 63
    )
    assert metrics["frozen_text_insufficiency_rate"] == pytest.approx(1 / 64)
    assert metrics["attribution_counts"]["retrieval_noise"] == 1
    assert metrics["attribution_counts"]["frozen_text_insufficient"] == 1
    assert (
        metrics["attribution_counts"][
            "other_gate_rejection_of_relevant_source"
        ]
        == 1
    )


def test_substantive_ai_review_is_retained_but_not_evaluated(
    tmp_path,
    monkeypatch,
):
    source = _source(tmp_path, monkeypatch)
    source_lock, packet = _packet(source, tmp_path)
    _complete_labels(packet)
    _complete_declaration(packet, ai_use="MOST_OR_ALL")

    result = summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "excluded_substantive_ai"
    assert result["completed_row_count"] == 64
    assert result["metrics"] is None
    assert result["declaration"]["generative_ai_use"] == "MOST_OR_ALL"


def test_source_lock_requires_explicit_owner_confirmation(tmp_path, monkeypatch):
    source = _source(tmp_path, monkeypatch)

    with pytest.raises(
        ScopeLinkDiagnosticError,
        match="authorized-output confirmation",
    ):
        create_source_lock(
            source,
            tmp_path / "lock.json",
            study_owner_id="offline-owner",
            confirm_authorized_output=False,
        )


def test_frozen_source_identity_contains_only_complete_sha256_values():
    """A prior prose transcription dropped one hex digit from the index hash."""
    assert set(diagnostic.EXPECTED_SOURCE_FILE_SHA256) == set(
        diagnostic.SOURCE_FILES
    )
    assert all(
        len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
        for value in diagnostic.EXPECTED_SOURCE_FILE_SHA256.values()
    )


def test_json_stdout_bypasses_legacy_windows_text_encoding(monkeypatch):
    """A real packet reached disk but GBK print failure hid CLI success."""
    stdout = _LegacyEncodedStdout()
    monkeypatch.setattr(diagnostic.sys, "stdout", stdout)

    diagnostic._write_json_stdout({"topic": "battery−grid"})

    assert '"topic": "battery−grid"' in stdout.buffer.getvalue().decode("utf-8")


def test_source_drift_after_lock_blocks_packet_preparation(tmp_path, monkeypatch):
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    candidates = source / "candidates.csv"
    candidates.write_text(
        candidates.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ScopeLinkDiagnosticError, match="identity drifted"):
        prepare_packet(source, source_lock, tmp_path / "packet")


def test_case_journal_drift_blocks_source_lock(tmp_path, monkeypatch):
    source = _source(tmp_path, monkeypatch)
    journal_path = source / "case-executions" / "W01.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["trace_id"] = "openalex-scope-link-v4-w08"
    journal_path.write_text(
        json.dumps(journal, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ScopeLinkDiagnosticError, match="does not match aggregate"):
        create_source_lock(
            source,
            tmp_path / "lock.json",
            study_owner_id="offline-owner",
            confirm_authorized_output=True,
        )


def test_label_context_drift_is_rejected_even_when_identity_count_matches(
    tmp_path,
    monkeypatch,
):
    source = _source(tmp_path, monkeypatch)
    source_lock, packet = _packet(source, tmp_path)
    rows = _complete_labels(packet)
    rows[0]["evidence_summary"] += " altered"
    _write_csv(packet / "labels.csv", LABEL_FIELDS, rows)
    _complete_declaration(packet)

    with pytest.raises(ScopeLinkDiagnosticError, match="context or identity drifted"):
        summarize_packet(source, source_lock, packet)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"semantic_scope_link": ""}, "partially completed"),
        (
            {
                "direct_relevance": "NO",
                "semantic_scope_link": "YES",
                "baseline_novelty": "N/A",
            },
            "invalid diagnostic labels",
        ),
        ({"review_note": "too short"}, "review_note is too short"),
    ],
)
def test_partial_invalid_or_ungrounded_labels_are_rejected(
    tmp_path,
    monkeypatch,
    updates,
    message,
):
    source = _source(tmp_path, monkeypatch)
    source_lock, packet = _packet(source, tmp_path)
    rows = _complete_labels(packet)
    rows[0].update(updates)
    _write_csv(packet / "labels.csv", LABEL_FIELDS, rows)
    _complete_declaration(packet)

    with pytest.raises(ScopeLinkDiagnosticError, match=message):
        summarize_packet(source, source_lock, packet)


def test_packet_manifest_rejects_automated_decision_leak(tmp_path, monkeypatch):
    source = _source(tmp_path, monkeypatch)
    source_lock, packet = _packet(source, tmp_path)
    manifest_path = packet / "packet_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["rows"][0]["scope_link_action"] = "ABSTAIN"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ScopeLinkDiagnosticError,
        match="leaks automated decision fields",
    ):
        summarize_packet(source, source_lock, packet)


def test_production_worker_cannot_import_the_diagnostic():
    worker = Path("src/academic_agent/pipeline_worker.py").read_text(
        encoding="utf-8"
    )

    assert "openalex_scope_link_abstention_review" not in worker
