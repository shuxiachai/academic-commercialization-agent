"""Offline tests for the paid agent-topology ablation harness."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

import ablation
from ablation import GuardrailRecorder, ScheduleCell
from ablation_check import (
    SUMMARY_COLUMNS,
    analyse_numeric_grounding,
    analyse_report,
    flatten_meta,
    pairwise_rows,
    reviewer_correction_count,
    write_summaries,
)
if TYPE_CHECKING:
    from academic_agent.evidence import EvidenceSource
    from academic_agent.source_pipeline import SourceCollection


def _source(
    source_id: str,
    *,
    summary: str | None = None,
    summary_source: str | None = "abstract",
) -> EvidenceSource:
    from academic_agent.evidence import EvidenceSource

    return EvidenceSource(
        source_id=source_id,
        title=f"Validated evidence for {source_id}",
        url=f"https://evidence.example.org/{source_id.lower()}",
        publisher="Evidence Publisher",
        published_date=date(2025, 1, 1),
        accessed_date=date(2026, 8, 21),
        source_type=(
            "academic_paper" if source_id.startswith("A")
            else "patent" if source_id.startswith("P")
            else "company_disclosure"
        ),
        evidence_summary=summary or (
            f"Source {source_id} reports a measured efficiency of 26.1% in a "
            "controlled validation study and explains the experimental conditions, "
            "measurement protocol, comparison baseline, uncertainty, and limitations "
            "in enough detail to support deterministic figure verification. The "
            "record describes sample preparation, instrumentation, repeated "
            "measurements, and the comparison control. It separates measured "
            "performance from analyst interpretation and states where replication "
            "is still needed, making this a substantive evidence record rather "
            "than a truncated search-result fragment."
        ),
        summary_source=summary_source,
    )


def _collection() -> SourceCollection:
    from academic_agent.source_pipeline import SourceCollection

    return SourceCollection(
        topic="Test commercialization technology",
        display_topic="Test commercialization technology",
        output_language="English",
        collected_at=datetime.now(UTC),
        academic_sources=[_source("A1")],
        patent_sources=[_source("P1")],
        market_sources=[_source("M1")],
        academic_queries=["academic query"],
        patent_queries=["patent query"],
        market_queries=["market query"],
    )


def _cell(variant: str, schedule_index: int = 1) -> ScheduleCell:
    return ScheduleCell(
        schedule_index=schedule_index,
        block_id="03-r1",
        position=schedule_index,
        num="03",
        topic="solid-state batteries for electric vehicles",
        expected_trl_range=(5, 7),
        industry="Energy",
        rep=1,
        variant=variant,
    )


def test_full_schedule_balances_every_variant_across_positions() -> None:
    """A time-of-day drift must not be confounded with one fixed arm order."""

    cells = ablation.build_schedule(ablation.TOPICS, repeat=3)

    assert len(cells) == 90
    counts = {
        (variant, position): sum(
            cell.variant == variant and cell.position == position for cell in cells
        )
        for variant in ablation.VARIANTS
        for position in (1, 2, 3)
    }
    assert set(counts.values()) == {10}
    assert len({cell.block_id for cell in cells}) == 30


def test_plan_only_is_the_default_and_never_dispatches_a_paid_cell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Printing a plan must remain a zero-cost operation at the CLI seam."""

    def paid_call_would_be_a_defect(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("plan-only mode dispatched a paid cell")

    monkeypatch.setattr(ablation, "run_cell", paid_call_would_be_a_defect)

    assert ablation.main(["--pilot", "--pause-seconds", "0"]) == 0


def test_full_paid_study_needs_a_second_explicit_confirmation() -> None:
    """One generic execute flag must not accidentally launch ninety cells."""

    with pytest.raises(SystemExit):
        ablation._parse_args(["--full", "--execute"])


def test_missing_fixture_aborts_without_live_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing frozen input must never silently become a live measurement."""

    monkeypatch.setattr(ablation.benchmark_fixtures, "load", lambda *args: None)

    with pytest.raises(FileNotFoundError, match="live fallback is forbidden"):
        ablation._fixture("03", "solid-state batteries for electric vehicles")


def test_variant_builders_have_the_registered_node_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The labels in persisted metadata must match the Crew that gets kicked off."""

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    collection = _collection()

    monolith, monolith_task = ablation.build_variant_crew("monolith", collection)
    four, four_task = ablation.build_variant_crew("specialists_writer", collection)
    full, full_task = ablation.build_variant_crew("full", collection)

    assert (len(monolith.agents), len(monolith.tasks), monolith_task) == (
        1, 1, "monolith_report_task"
    )
    assert (len(four.agents), len(four.tasks), four_task) == (
        4, 4, "commercialization_report_task"
    )
    assert (len(full.agents), len(full.tasks), full_task) == (
        6, 6, "commercialization_report_task"
    )
    # Four nodes are an actual production prefix, not copied prompts that can
    # drift while preserving the same marketing label.
    assert [task.name for task in four.tasks] == [task.name for task in full.tasks[:4]]
    assert four.tasks[3].name == four_task
    assert full.tasks[3].name == full_task
    # The generalist replaces the production writer as the report-producing
    # node, so provider settings must not become a hidden second treatment.
    assert monolith.agents[0].llm.model == four.agents[3].llm.model
    assert monolith.agents[0].llm.temperature == four.agents[3].llm.temperature




def test_monolith_guardrail_delegates_to_the_production_report_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one-node treatment may change evidence flow, not validation strength."""

    from academic_agent import evidence

    observed: dict[str, object] = {}

    def fake_policy(raw, allowed_sources, finding_sources, **kwargs):  # noqa: ANN001
        observed.update({
            "raw": raw,
            "allowed": set(allowed_sources),
            "finding_sources": finding_sources,
            "kwargs": kwargs,
        })
        return "normalized report", []

    monkeypatch.setattr(evidence, "_normalize_and_find_blocking_errors", fake_policy)
    output = SimpleNamespace(raw="x" * 501)

    passed, returned = ablation.make_monolith_report_guardrail(_collection())(output)

    assert passed is True
    assert returned is output
    assert output.raw == "normalized report"
    assert observed["allowed"] == {"A1", "P1", "M1"}
    assert observed["finding_sources"] == {}


def test_guardrail_recorder_preserves_return_values_and_counts_retries() -> None:
    """Instrumentation must wrap CrewAI's private seam without changing retries."""

    calls = 0

    def guardrail(output):  # noqa: ANN001
        nonlocal calls
        calls += 1
        if calls == 1:
            return False, "first attempt failed"
        output.raw = "normalized"
        return True, output

    recorder = GuardrailRecorder()
    wrapped = recorder.wrap("report", guardrail)
    first = SimpleNamespace(raw="draft one")
    second = SimpleNamespace(raw="draft two")

    assert wrapped(first) == (False, "first attempt failed")
    assert wrapped(second) == (True, second)
    summary = recorder.task_summary("report")

    assert summary["calls"] == 2
    assert summary["failures"] == 1
    assert summary["retries"] == 1
    assert summary["attempts"][0]["before_sha256_16"] != ""

    task = SimpleNamespace(
        name="runtime",
        guardrail=guardrail,
        _guardrail=guardrail,
    )
    runtime_recorder = GuardrailRecorder()
    runtime_recorder.instrument([task])
    third = SimpleNamespace(raw="delivered report")
    assert task._guardrail(third) == (True, third)
    assert task.guardrail is task._guardrail
    assert runtime_recorder.task_summary("runtime")["calls"] == 1


def test_report_selection_asserts_the_delivered_artifact_boundary() -> None:
    """A correctly computed report that never reaches persistence is still a bug."""

    outputs = [SimpleNamespace(raw=f"task-{index}") for index in range(6)]

    assert ablation.select_report_outputs("monolith", outputs[:1]) == (
        "task-0", "task-0"
    )
    assert ablation.select_report_outputs("specialists_writer", outputs[:4]) == (
        "task-3", "task-3"
    )
    assert ablation.select_report_outputs("full", outputs) == ("task-3", "task-4")


def test_numeric_grounding_distinguishes_pass_fail_and_not_checked() -> None:
    """Zero checked claims cannot be flattened into the same status as support."""

    source = _source("A1")
    allowed = {"A1": source}

    supported = analyse_numeric_grounding("Efficiency reached 26.1% [A1].", allowed)
    unsupported = analyse_numeric_grounding("Efficiency reached 31.7% [A1].", allowed)
    silent = analyse_numeric_grounding("Performance improved materially [A1].", allowed)

    assert (supported.status, supported.checked_claim_lines) == ("pass", 1)
    assert (unsupported.status, unsupported.unsupported_claim_lines) == ("fail", 1)
    assert unsupported.unsupported_figures == ("31.7%",)
    assert (silent.status, silent.checked_claim_lines) == ("not_checked", 0)


def test_snippet_absence_is_unverifiable_not_unsupported() -> None:
    """A snippet stays unverifiable even when a checkable source shares its line."""

    snippet = _source(
        "M1",
        summary=(
            "A search result fragment describes the commercial programme but "
            "does not expose the complete underlying company disclosure text."
        ),
        summary_source="search_snippet",
    )
    result = analyse_numeric_grounding("Revenue reached $37.4 million [M1].", {"M1": snippet})

    assert result.status == "not_checked"
    assert result.checked_claim_lines == 0
    assert result.unsupported_claim_lines == 0
    assert result.unverifiable_claim_lines == 1

    mixed = analyse_numeric_grounding(
        "Laboratory efficiency improved [A1]. Market revenue reached "
        "$37.4 million [M1].",
        {"A1": _source("A1"), "M1": snippet},
    )
    assert mixed.status == "not_checked"
    assert mixed.checked_claim_lines == 0
    assert mixed.unsupported_claim_lines == 0
    assert mixed.unverifiable_claim_lines == 1


def test_summary_boundary_carries_every_declared_column() -> None:
    """Metrics stored correctly but dropped from CSV would make the study unauditable."""

    meta = {
        "experiment_id": "exp",
        "block_id": "03-r1",
        "schedule_index": 1,
        "position": 1,
        "num": "03",
        "rep": 1,
        "topic": "topic",
        "variant": "monolith",
        "nodes": 1,
        "status": "success",
        "fixture_digest": "abc",
        "fixture_age_days": 2.5,
        "elapsed_seconds": 12.0,
        "usage": {
            "total_tokens": 123,
            "total_requests": 1,
            "cost_usd": 0.01,
            "cost_complete": True,
        },
        "report_metrics": {
            "contract_status": "pass",
            "validation_errors": [],
            "grounding": {
                "status": "not_checked",
                "checked_claim_lines": 0,
                "unsupported_claim_lines": 0,
                "unverifiable_claim_lines": 2,
            },
            "word_count": 900,
            "unique_citations": 8,
            "citation_domains": ["A", "P", "M"],
        },
        "report_guardrail": {"calls": 2, "failures": 1, "retries": 1},
        "reviewer_corrections": None,
        "draft_retention_ratio": None,
    }

    row = flatten_meta(meta)

    assert tuple(row) == SUMMARY_COLUMNS
    assert row["grounding_status"] == "not_checked"
    assert row["unverifiable_claim_lines"] == 2
    assert row["report_guardrail_failures"] == 1
    assert row["citation_domains"] == "A,P,M"


def test_pairwise_rows_compare_only_within_the_same_block() -> None:
    rows = [
        {"block_id": "03-r1", "variant": "monolith", "total_tokens": 100},
        {"block_id": "03-r1", "variant": "specialists_writer", "total_tokens": 150},
        {"block_id": "04-r1", "variant": "full", "total_tokens": 999},
    ]

    paired = pairwise_rows(rows)

    assert len(paired) == 1
    assert paired[0]["block_id"] == "03-r1"
    assert paired[0]["total_tokens_delta"] == 50


def test_summary_files_are_rebuilt_from_persisted_meta() -> None:
    """The analyser must not depend on in-memory state from the paid process."""

    output_root = Path(__file__).parents[1] / "outputs"
    with tempfile.TemporaryDirectory(prefix="test-ablation-", dir=output_root) as raw:
        experiment_root = Path(raw)
        for index, variant in enumerate(("monolith", "specialists_writer"), start=1):
            directory = experiment_root / f"cell-{index}"
            directory.mkdir()
            (directory / "meta.json").write_text(
                json.dumps({
                    "experiment_id": "exp",
                    "block_id": "03-r1",
                    "schedule_index": index,
                    "variant": variant,
                    "status": "success",
                    "usage": {"total_tokens": 100 * index},
                }),
                encoding="utf-8",
            )

        summary, paired, rows = write_summaries(experiment_root)

        assert summary.exists()
        assert paired.exists()
        assert [row["variant"] for row in rows] == ["monolith", "specialists_writer"]


def test_summary_rejects_unreadable_cell_metadata() -> None:
    """A damaged paid result must not silently disappear from aggregation."""

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        cell = root / "001-03-monolith-r1"
        cell.mkdir()
        (cell / "meta.json").write_text("{not-json", encoding="utf-8")

        with pytest.raises(ValueError, match="could not inspect ablation metadata"):
            write_summaries(root)

        assert not (root / "ablation_summary.csv").exists()



def test_reviewer_metrics_are_na_without_notes_and_zero_for_no_edits() -> None:
    assert reviewer_correction_count("report") is None
    assert reviewer_correction_count(
        "report\n\n## Reviewer Notes\n\nNo corrections required."
    ) == 0
    assert reviewer_correction_count(
        "report\n\n## Reviewer Notes\n\n- Fix one\n- Fix two"
    ) == 2


def test_draft_retention_ignores_deterministic_reviewer_notes() -> None:
    draft = "A validated draft."
    delivered = draft + "\n\n## Reviewer Notes\n\nNo corrections required."

    assert ablation.draft_retention_ratio(draft, delivered) == 1.0


def test_paid_execution_requires_an_explicit_scope() -> None:
    """--execute alone must not imply a thirty-cell paid batch."""

    with pytest.raises(SystemExit):
        ablation._parse_args(["--execute"])


def test_registered_pilot_cannot_silently_drop_an_arm() -> None:
    """A cheaper partial run must not be filed under the preregistered pilot."""

    with pytest.raises(SystemExit):
        ablation._parse_args(["--pilot", "--execute", "--variants", "monolith"])


def test_preflight_validates_every_fixture_before_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A late missing fixture must be found before an earlier arm spends money."""

    calls: list[str] = []

    def fake_fixture(num: str, topic: str):
        calls.append(f"{num}:{topic}")
        return _collection(), {"sha256_16": num}

    monkeypatch.setattr(ablation, "_fixture", fake_fixture)
    cases = ablation.TOPICS[:2]

    entries = ablation.preflight_fixtures(cases)

    assert list(entries) == ["01", "02"]
    assert calls == [f"{num}:{topic}" for num, topic, _trl, _industry in cases]


def test_resume_requires_same_commit_fixture_and_topology() -> None:
    """A result from different code or evidence must never be reused."""

    output_root = Path(__file__).parents[1] / "outputs"
    with tempfile.TemporaryDirectory(prefix="test-ablation-", dir=output_root) as raw:
        root = Path(raw)
        cell = _cell("monolith")
        directory = ablation._cell_directory(root, cell)
        directory.mkdir(parents=True)
        (directory / "meta.json").write_text(
            json.dumps({
                "status": "success",
                "evidence_mode": "fixture",
                "block_id": cell.block_id,
                "variant": cell.variant,
                "commit_sha": "same-code",
                "fixture_digest": "same-evidence",
            }),
            encoding="utf-8",
        )

        reused = ablation._reusable_cell_meta(
            root,
            cell,
            commit_sha="same-code",
            fixture_digest="same-evidence",
        )
        changed = ablation._reusable_cell_meta(
            root,
            cell,
            commit_sha="different-code",
            fixture_digest="same-evidence",
        )

        assert reused is not None
        assert changed is None


def test_reviewer_notes_are_outside_the_report_contract() -> None:
    """Reviewer reasons mentioning IDs must not become bibliography failures."""

    report = (
        "A short report [A1].\n\n## References\n\n"
        "[A1] Validated evidence. https://evidence.example.org/a1\n\n"
        "## Reviewer Notes\n\n- Reframed an unsupported claim that cited [M99]."
    )

    metrics = analyse_report(report, [_source("A1")])

    assert all("M99" not in error for error in metrics.validation_errors)


def test_run_cell_persists_the_selected_report_at_the_disk_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A selected in-memory report must reach the artifact the analyser reads."""

    collection = _collection()
    outputs = [
        SimpleNamespace(raw="academic evidence", name="academic"),
        SimpleNamespace(raw="patent evidence", name="patent"),
        SimpleNamespace(raw="market evidence", name="market"),
        SimpleNamespace(raw="delivered report", name="report"),
    ]

    class FakeCrew:
        tasks: list[object] = []
        agents: list[object] = []

        def kickoff(self, *, inputs):  # noqa: ANN001
            assert inputs["research_topic"] == collection.topic
            return SimpleNamespace(tasks_output=outputs)

    monkeypatch.setattr(
        ablation,
        "_fixture",
        lambda *args: (collection, {"sha256_16": "fixture-digest"}),
    )
    monkeypatch.setattr(ablation.benchmark_fixtures, "age_days", lambda num: 1.0)
    monkeypatch.setattr(
        ablation,
        "build_variant_crew",
        lambda *args: (FakeCrew(), "commercialization_report_task"),
    )

    output_root = Path(__file__).parents[1] / "outputs"
    with tempfile.TemporaryDirectory(prefix="test-ablation-", dir=output_root) as raw:
        root = Path(raw)
        cell = _cell("specialists_writer")
        meta = ablation.run_cell(
            cell,
            experiment_id="experiment",
            experiment_root=root,
            commit_sha="commit",
        )
        delivered_path = ablation._cell_directory(root, cell) / "commercialization_report.md"

        assert meta["status"] == "success"
        assert delivered_path.read_text(encoding="utf-8") == "delivered report"
        assert meta["report_metrics"]["contract_status"] == "fail"
