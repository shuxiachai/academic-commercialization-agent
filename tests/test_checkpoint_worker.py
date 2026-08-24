"""Worker-level proof that a restarted process skips validated paid nodes."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from crewai.tasks.task_output import OutputFormat as CrewOutputFormat
from crewai.tasks.task_output import TaskOutput

from academic_agent.checkpoint_runtime import TASK_NODES
from academic_agent.evidence import (
    EvidenceFinding,
    EvidenceReport,
    EvidenceSource,
)
from academic_agent.run_spec import RESUME_SNAPSHOT_DIRECTORY
from academic_agent.source_pipeline import SourceCollection


def _source_collection() -> SourceCollection:
    source = EvidenceSource(
        source_id="A1",
        title="Validated checkpoint source for worker recovery",
        url="https://example.com/checkpoint-source",
        publisher="Example University",
        published_date=date(2026, 1, 10),
        accessed_date=date.today(),
        source_type="academic_paper",
        credibility_tier="high",
        credibility_reason="Peer-reviewed institutional source used only by an offline test.",
        evidence_summary=(
            "This deliberately long summary provides enough validated source text "
            "for the source model while no external request is ever performed."
        ),
        summary_source="abstract",
    )
    return SourceCollection(
        topic="solid-state battery recycling",
        display_topic="solid-state battery recycling",
        collected_at=datetime.now(UTC),
        academic_sources=[source],
        academic_queries=["solid-state battery recycling"],
        patent_queries=["solid-state battery recycling patent"],
        market_queries=["solid-state battery recycling market"],
    )


def _evidence_output(prefix: str) -> str:
    """Return the post-guardrail JSON shape required by typed recovery."""
    source_id = f"{prefix}1"
    source_types = {
        "A": "academic_paper",
        "P": "patent",
        "M": "market_report",
    }
    source = EvidenceSource(
        source_id=source_id,
        title=f"Deterministic checkpoint source {source_id}",
        url=f"https://example.com/checkpoint-{source_id.lower()}",
        publisher="Example Research Institute",
        published_date=date(2026, 1, 10),
        accessed_date=date(2026, 8, 23),
        source_type=source_types[prefix],
        evidence_summary=(
            "This deterministic source summary represents already validated "
            "evidence at the offline checkpoint worker boundary."
        ),
    )
    findings = [
        EvidenceFinding(
            finding_id=f"{prefix}F{index}",
            category="technology maturity",
            claim="A deterministic checkpoint finding that remains supportable.",
            claim_type="observed_fact",
            source_ids=[source_id],
            confidence="high",
            commercial_implication="This affects the commercialization pathway.",
        )
        for index in range(1, 4)
    ]
    report = EvidenceReport(
        topic="solid-state battery recycling",
        scope_summary="A bounded deterministic review for checkpoint recovery.",
        search_queries=["solid-state battery recycling commercial maturity"],
        findings=findings,
        sources=[source],
        limitations=["The fixture replaces every external provider boundary."],
    )
    return report.model_dump_json()


def _output(node: str) -> TaskOutput:
    if node in {"academic", "patent", "market"}:
        prefix = {"academic": "A", "patent": "P", "market": "M"}[node]
        raw = _evidence_output(prefix)
    elif node == "scorer":
        raw = json.dumps({"node": node, "findings": []}, sort_keys=True)
    else:
        raw = f"# {node.title()}\n\nValidated checkpoint report."
    return TaskOutput(
        description=f"{node} description",
        expected_output=f"{node} expected",
        raw=raw,
        agent=f"{node} agent",
        output_format=(
            CrewOutputFormat.JSON if node in {"academic", "patent", "market", "scorer"} else CrewOutputFormat.RAW
        ),
    )


def _tasks() -> list[Any]:
    llm = SimpleNamespace(
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        temperature=0,
        response_format=None,
    )
    tasks: list[Any] = []
    for node in TASK_NODES:
        agent = SimpleNamespace(
            role=f"{node} agent",
            goal=f"{node} goal",
            backstory=f"{node} backstory",
            inject_date=False,
            allow_delegation=False,
            tools=[],
            llm=llm,
        )
        tasks.append(
            SimpleNamespace(
                description=f"{node} description",
                expected_output=f"{node} expected",
                async_execution=node in {"academic", "patent", "market"},
                context=[],
                guardrail=object(),
                guardrail_max_retries=1,
                output_json=None,
                output_pydantic=None,
                output_format=(
                    CrewOutputFormat.JSON
                    if node in {"academic", "patent", "market", "scorer"}
                    else CrewOutputFormat.RAW
                ),
                agent=agent,
                tools=[],
                callback=None,
                output=None,
            )
        )
    tasks[3].context = tasks[:3]
    tasks[4].context = tasks[:4]
    tasks[5].context = tasks[:3]
    return tasks


class _FakeCrew:
    """Minimal executor that honours the same hydrated-output seam as CrewAI."""

    def __init__(self) -> None:
        self.tasks = _tasks()
        self.agents = [task.agent for task in self.tasks]
        self.task_callback = None
        self.checkpoint_kickoff_event_id = None
        self.executed: list[str] = []

    def kickoff(self, *, inputs: dict[str, str]) -> SimpleNamespace:
        del inputs
        for node, task in zip(TASK_NODES, self.tasks, strict=True):
            if task.output is not None:
                continue
            output = _output(node)
            task.output = output
            self.executed.append(node)
            if task.callback is not None:
                task.callback(output)
            if self.task_callback is not None and self.task_callback is not task.callback:
                self.task_callback(output)
        outputs = [task.output for task in self.tasks]
        return SimpleNamespace(tasks_output=outputs, raw=outputs[-1].raw)


def _run_worker(
    output_root: Path,
    run_id: str,
    source_collection: SourceCollection,
    crew: _FakeCrew,
    *,
    resume_from: str | None = None,
) -> Path:
    argv = ["pipeline_worker.py", run_id, source_collection.topic]
    if resume_from is not None:
        argv += ["--resume-from", resume_from]

    empty_usage = SimpleNamespace(agents=[], collection_error=None)
    with (
        patch.object(sys, "argv", argv),
        patch("academic_agent.run_output.DEFAULT_OUTPUT_ROOT", output_root),
        patch(
            "academic_agent.source_pipeline.collect_source_collection",
            return_value=source_collection,
        ),
        patch("academic_agent.crew.AcademicAgent") as agent_class,
        patch("academic_agent.token_usage.collect_usage", return_value=empty_usage),
    ):
        agent_class.return_value.crew.return_value = crew
        from academic_agent.pipeline_worker import main

        main()
    return output_root / run_id


def test_restarted_worker_reuses_all_nodes_after_parent_directory_disappears(
    tmp_path: Path,
) -> None:
    source_collection = _source_collection()
    source_id = "20260823T010101Z-checkpointsource"
    source_crew = _FakeCrew()
    source_directory = _run_worker(tmp_path, source_id, source_collection, source_crew)

    assert source_crew.executed == list(TASK_NODES)
    for node in ("retrieval", *TASK_NODES):
        assert (source_directory / "checkpoints" / node / "manifest.json").is_file()

    child_id = "20260823T020202Z-checkpointchild"
    child_directory = tmp_path / child_id
    snapshot = child_directory / RESUME_SNAPSHOT_DIRECTORY
    shutil.copytree(
        source_directory / "checkpoints",
        snapshot / "checkpoints",
    )
    # The accepted child owns its snapshot. The worker must not reopen the
    # capability URL's directory after this point.
    shutil.rmtree(source_directory)

    child_crew = _FakeCrew()
    _run_worker(
        tmp_path,
        child_id,
        source_collection,
        child_crew,
        resume_from=source_id,
    )

    status = json.loads((child_directory / "status.json").read_text(encoding="utf-8"))
    assert child_crew.executed == []
    assert status["stage"] == "Done"
    assert status["checkpointing"]["state"] == "complete"
    assert status["recovery"]["state"] == "reused"
    assert status["recovery"]["reused_nodes"] == ["retrieval", *TASK_NODES]
    assert status["recovery"]["next_node"] is None
