"""Recovery policy tests at the CrewAI task and disk boundaries.

These are intentionally separate from the storage-primitive tests. A manifest
can be perfectly valid while orchestration never hydrates it, or while CrewAI
ignores the hydrated output and calls the provider again. Both defects would
repeat paid work, so the assertions sit on those two seams.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.llms.base_llm import BaseLLM
from crewai.tasks.task_output import OutputFormat as CrewOutputFormat
from crewai.tasks.task_output import TaskOutput
from pydantic import BaseModel

from academic_agent.checkpoint_runtime import CheckpointRuntime, TASK_NODES
from academic_agent.checkpoints import CheckpointStore
from academic_agent.run_spec import RunSpec


_TEST_DATE = date(2026, 8, 23)
_REVISION = "git:abcdef0123456789"


class _SourceCollection(BaseModel):
    """Small JSON source model sufficient to exercise identity hashing."""

    topic: str = "checkpoint test"
    evidence: list[str] = ["A1", "P1", "M1"]


class _ExplodingLLM(BaseLLM):
    """Provider double: any invocation means CrewAI failed to skip the task."""

    def call(self, *args: Any, **kwargs: Any) -> str:
        raise AssertionError("provider must not be called for a hydrated task")


def _task_output(node: str) -> TaskOutput:
    raw = (
        json.dumps({"node": node, "finding": "validated"}, sort_keys=True)
        if node in {"academic", "patent", "market", "scorer"}
        else f"# {node.title()}\n\nValidated output."
    )
    output_format = (
        CrewOutputFormat.JSON if node in {"academic", "patent", "market", "scorer"} else CrewOutputFormat.RAW
    )
    return TaskOutput(
        description=f"{node} description",
        expected_output=f"{node} expected",
        raw=raw,
        agent=f"{node} agent",
        output_format=output_format,
    )


def _fake_tasks(*, patent_description: str = "patent description") -> list[Any]:
    llm = SimpleNamespace(
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        temperature=0,
        response_format=None,
        api_key="must-never-be-persisted",
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
        task = SimpleNamespace(
            description=(patent_description if node == "patent" else f"{node} description"),
            expected_output=f"{node} expected",
            async_execution=node in {"academic", "patent", "market"},
            context=[],
            guardrail=object(),
            guardrail_max_retries=1,
            output_json=None,
            output_pydantic=None,
            output_format=(
                CrewOutputFormat.JSON if node in {"academic", "patent", "market", "scorer"} else CrewOutputFormat.RAW
            ),
            agent=agent,
            tools=[],
            callback=None,
            output=None,
        )
        tasks.append(task)

    tasks[3].context = tasks[:3]
    tasks[4].context = tasks[:4]
    tasks[5].context = tasks[:3]
    return tasks


def _runtime(
    run_directory: Path,
    *,
    tasks: list[Any],
    source: _SourceCollection,
    retrieval_sha256: str,
    resume_directory: Path | None = None,
    progress_callback: Any = None,
) -> CheckpointRuntime:
    crew = SimpleNamespace(
        tasks=tasks,
        task_callback=progress_callback,
        checkpoint_kickoff_event_id=None,
    )
    return CheckpointRuntime(
        crew=crew,
        source_collection=source,
        crew_inputs={"topic": source.topic, "evidence": source.evidence},
        destination_run_directory=run_directory,
        retrieval_output_sha256=retrieval_sha256,
        revision=_REVISION,
        as_of_date=_TEST_DATE,
        resume_run_id="source-run" if resume_directory is not None else None,
        resume_run_directory=resume_directory,
    )


def _seed_validated_prefix(
    source_run: Path,
    *,
    count: int,
    patent_description: str = "patent description",
) -> tuple[_SourceCollection, str]:
    source = _SourceCollection()
    retrieval_payload = source.model_dump_json()
    spec = RunSpec(topic=source.topic)
    from academic_agent.checkpoint_runtime import retrieval_identity

    retrieval = CheckpointStore(source_run).commit(
        retrieval_identity(spec, revision=_REVISION, as_of_date=_TEST_DATE),
        retrieval_payload,
        output_format="json",
    )
    runtime = _runtime(
        source_run,
        tasks=_fake_tasks(patent_description=patent_description),
        source=source,
        retrieval_sha256=retrieval.output_sha256,
    )
    runtime.install_task_callbacks()
    for index in range(count):
        runtime.tasks[index].callback(_task_output(TASK_NODES[index]))
    return source, retrieval.output_sha256


def test_runtime_restores_and_republishes_only_the_validated_prefix(
    tmp_path: Path,
) -> None:
    source_run = tmp_path / "source"
    child_run = tmp_path / "child"
    source, retrieval_sha256 = _seed_validated_prefix(source_run, count=4)
    tasks = _fake_tasks()
    runtime = _runtime(
        child_run,
        tasks=tasks,
        source=source,
        retrieval_sha256=retrieval_sha256,
        resume_directory=source_run,
    )

    reused = runtime.restore_contiguous_prefix()

    assert reused == 4
    assert [task.output is not None for task in tasks] == [True, True, True, True, False, False]
    assert runtime.crew.checkpoint_kickoff_event_id == "academic-agent:source-run"
    assert runtime.snapshot()["recovery"]["reused_nodes"] == ["academic", "patent", "market", "writer"]
    for node in TASK_NODES[:4]:
        assert (child_run / "checkpoints" / node / "manifest.json").is_file()


def test_first_mismatch_stops_before_a_later_reusable_checkpoint(
    tmp_path: Path,
) -> None:
    source_run = tmp_path / "source"
    source, retrieval_sha256 = _seed_validated_prefix(source_run, count=3)
    tasks = _fake_tasks(patent_description="changed patent prompt")
    runtime = _runtime(
        tmp_path / "child",
        tasks=tasks,
        source=source,
        retrieval_sha256=retrieval_sha256,
        resume_directory=source_run,
    )

    reused = runtime.restore_contiguous_prefix()
    snapshot = runtime.snapshot()["recovery"]

    assert reused == 1
    assert tasks[0].output is not None
    assert tasks[1].output is None
    assert tasks[2].output is None
    assert snapshot["inspections"]["patent"]["state"] == "mismatch"
    # Market is valid on disk, but non-contiguous reuse would change CrewAI's
    # scheduler semantics. It must not even be inspected after patent diverges.
    assert "market" not in snapshot["inspections"]


def test_task_callback_commits_without_advancing_progress_twice(
    tmp_path: Path,
) -> None:
    progress_outputs: list[Any] = []
    source = _SourceCollection()
    runtime = _runtime(
        tmp_path,
        tasks=_fake_tasks(),
        source=source,
        retrieval_sha256="0" * 64,
        progress_callback=progress_outputs.append,
    )
    runtime.install_task_callbacks()

    runtime.tasks[0].callback(_task_output("academic"))

    assert progress_outputs == []
    assert (tmp_path / "checkpoints" / "academic" / "manifest.json").is_file()
    manifest = (tmp_path / "checkpoints" / "academic" / "manifest.json").read_text(encoding="utf-8")
    assert "must-never-be-persisted" not in manifest
    assert "api_key" not in manifest.lower()


def test_pinned_crewai_executor_skips_runtime_restored_prefix_without_provider_call(
    tmp_path: Path,
) -> None:
    """Exercise the whole adapter against CrewAI 1.14.7's real scheduler.

    The six tasks include the production-shaped asynchronous evidence prefix.
    Removing either runtime hydration or checkpoint_kickoff_event_id makes
    CrewAI call _ExplodingLLM, so this proves the paid-provider seam rather
    than merely asserting that fields were assigned.
    """

    def real_crew() -> Crew:
        llm = _ExplodingLLM(model="never-called", temperature=0)
        agents: list[Agent] = []
        tasks: list[Task] = []
        for node in TASK_NODES:
            agent = Agent(
                role=f"{node} restored agent",
                goal=f"Return the restored {node} output",
                backstory="This agent must never execute during the test.",
                llm=llm,
                allow_delegation=False,
                verbose=False,
            )
            context = None
            if node in {"writer", "scorer"}:
                context = tasks[:3]
            elif node == "reviewer":
                context = tasks[:4]
            task = Task(
                description=f"{node} description",
                expected_output=f"{node} expected",
                agent=agent,
                async_execution=node in {"academic", "patent", "market"},
                context=context,
            )
            agents.append(agent)
            tasks.append(task)
        return Crew(
            agents=agents,
            tasks=tasks,
            process=Process.sequential,
            verbose=False,
        )

    source = _SourceCollection()
    crew_inputs = {"topic": source.topic, "evidence": source.evidence}
    retrieval_sha256 = "0" * 64
    source_crew = real_crew()
    source_runtime = CheckpointRuntime(
        crew=source_crew,
        source_collection=source,
        crew_inputs=crew_inputs,
        destination_run_directory=tmp_path / "source",
        retrieval_output_sha256=retrieval_sha256,
        revision=_REVISION,
        as_of_date=_TEST_DATE,
    )
    source_runtime.install_task_callbacks()
    for node, task in zip(TASK_NODES, source_crew.tasks, strict=True):
        assert task.callback is not None
        task.callback(_task_output(node))

    child_crew = real_crew()
    child_runtime = CheckpointRuntime(
        crew=child_crew,
        source_collection=source,
        crew_inputs=crew_inputs,
        destination_run_directory=tmp_path / "child",
        retrieval_output_sha256=retrieval_sha256,
        revision=_REVISION,
        as_of_date=_TEST_DATE,
        resume_run_id="source-run",
        resume_run_directory=tmp_path / "source",
    )
    reused = child_runtime.restore_contiguous_prefix()
    child_runtime.install_task_callbacks()

    result = child_crew.kickoff(inputs=crew_inputs)

    assert reused == len(TASK_NODES)
    assert result.raw == _task_output("scorer").raw
