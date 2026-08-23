"""Process-level and checker tests for the checkpoint fault-recovery audit."""

from __future__ import annotations

import csv
import copy
import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from academic_agent.evidence import EvidenceSource
from academic_agent.source_pipeline import SourceCollection
from checkpoint_fault_audit import (
    Fixture,
    SCENARIOS,
    check_experiment,
    evaluate_unit,
    run_fault_unit,
)


def _fixture(tmp_path: Path) -> Fixture:
    source = EvidenceSource(
        source_id="A1",
        title="Offline process fault audit source",
        url="https://example.com/checkpoint-fault-audit",
        publisher="Example University",
        published_date=date(2026, 1, 10),
        accessed_date=date.today(),
        source_type="academic_paper",
        credibility_tier="high",
        credibility_reason="Deterministic fixture for a zero-network process test.",
        evidence_summary=(
            "This deliberately long source summary satisfies the evidence model "
            "while the process-level recovery test replaces every network and "
            "model boundary with deterministic local doubles."
        ),
        summary_source="abstract",
    )
    collection = SourceCollection(
        topic="solid-state battery recycling",
        display_topic="solid-state battery recycling",
        collected_at=datetime.now(UTC),
        academic_sources=[source],
        academic_queries=["solid-state battery recycling"],
        patent_queries=["solid-state battery recycling patent"],
        market_queries=["solid-state battery recycling market"],
    )
    path = tmp_path / "validated_sources.json"
    payload = collection.model_dump_json(indent=2)
    path.write_text(payload, encoding="utf-8")
    return Fixture(
        fixture_id="test-fixture",
        path=path,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        topic=collection.topic,
    )

@pytest.fixture(scope="module")
def recovered_audit(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, dict]:
    """Pay the subprocess startup cost once while preserving assertion isolation."""

    root = tmp_path_factory.mktemp("checkpoint-fault-audit")
    fixture = _fixture(root)
    record = run_fault_unit(
        unit_root=root / "unit",
        fixture=fixture,
        scenario=SCENARIOS[1],
        timeout_seconds=20,
    )
    return root, record


def test_hard_killed_worker_recovers_exact_suffix_from_detached_parent(
    recovered_audit: tuple[Path, dict],
) -> None:
    """Prove the seam a field-only test missed: child execution skips paid work.

    The parent is a distinct OS process and is terminated only after the market
    callback's manifest exists. Removing hydration, using the original parent
    path, or executing a committed node again makes this test fail at a
    persisted worker boundary rather than at an internal runtime field.
    """

    root, record = recovered_audit

    assert evaluate_unit(record) == []
    assert record["passed"] is True
    assert record["parent"]["execution_nodes"] == ["academic", "patent", "market"]
    assert record["child"]["execution_nodes"] == ["writer", "reviewer", "scorer"]
    assert not (root / "unit" / "parent").exists()
    assert record["child"]["status"]["stage"] == "Done"


def test_checker_recomputes_verdict_after_reused_node_tampering(
    recovered_audit: tuple[Path, dict],
) -> None:
    """Re-inject duplicate-work evidence and reject it despite ``passed=true``."""

    _root, record = recovered_audit
    tampered = copy.deepcopy(record)
    tampered["passed"] = True
    tampered["child"]["execution_nodes"] = [
        "market",
        "writer",
        "reviewer",
        "scorer",
    ]
    tampered["duplicate_execution_nodes"] = ["market"]

    reasons = evaluate_unit(tampered)

    assert any(reason.startswith("child.execution_nodes:") for reason in reasons)
    assert any(reason.startswith("duplicate_execution_nodes:") for reason in reasons)


def test_checker_does_not_treat_an_uninspectable_study_as_zero_failures(
    tmp_path: Path,
) -> None:
    """An empty directory is unavailable evidence, never a 0/0 recovery pass."""

    summary = check_experiment(tmp_path)

    assert summary["study_passed"] is False
    assert summary["expected_units"] == 30
    assert summary["observed_unit_records"] == 0
    assert summary["passing_units"] == 0
    assert summary["study_errors"]


def test_published_result_matches_the_frozen_30_unit_claim() -> None:
    """Keep the public row evidence and aggregate README claim on one seam."""

    path = (
        Path(__file__).resolve().parents[1]
        / "evals"
        / "checkpoint_recovery"
        / "checkpoint-fault-recovery-offline-v1.csv"
    )
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 30
    assert len({row["unit_id"] for row in rows}) == 30
    assert {row["scenario_id"] for row in rows} == {
        "after_academic",
        "after_market",
        "after_reviewer",
    }
    assert all(row["passed"] == "true" for row in rows)
    assert sum(int(row["parent_task_count"]) for row in rows) == 90
    assert sum(int(row["child_task_count"]) for row in rows) == 90
    assert sum(int(row["duplicate_task_count"]) for row in rows) == 0
