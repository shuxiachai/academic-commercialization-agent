"""Every ablation arm is kicked off with every template variable its crew interpolates.

ablation.py kicked off with collection.crew_inputs() alone. When Decision
Context added {decision_context_json}, {assessment_mode} and
{decision_mode_guidance} to the Writer and Reviewer templates, the four- and
six-node arms would have failed at kickoff with "Missing required template
variable 'decision_context_json'". No test ran a real crew's templates, so
nothing caught it; benchmark.py had the same defect (errata-2026-10-18).
These tests take the inputs at the kickoff call itself, for each arm's real
tasks and agents, on both of run_cell's kickoff paths.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import ablation
from ablation import ScheduleCell

# The pattern CrewAI interpolates; JSON examples in the templates contain
# quotes or spaces inside their braces and so never match it.
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_NUM, _TOPIC = "03", "solid-state batteries for electric vehicles"


def _placeholders(crew) -> set[str]:
    texts = [text for task in crew.tasks for text in (task.description, task.expected_output)]
    texts += [text for agent in crew.agents for text in (agent.role, agent.goal, agent.backstory)]
    return {name for text in texts for name in _PLACEHOLDER.findall(text or "")}


def _kickoff_inputs(monkeypatch, variant: str, max_execution_time: int | None) -> tuple[set[str], dict]:
    """Run one cell of the real arm with a kickoff that records instead of calling a model."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    monkeypatch.delenv("ABLATION_MAX_EXECUTION_TIME", raising=False)
    collection, entry = ablation._fixture(_NUM, _TOPIC)  # the committed frozen fixture
    crew, report_task = ablation.build_variant_crew(variant, collection)
    received: list[dict] = []

    class Recording:
        tasks, agents = crew.tasks, crew.agents

        def kickoff(self, *, inputs):
            received.append(dict(inputs))
            return SimpleNamespace(tasks_output=[])

    monkeypatch.setattr(ablation, "_fixture", lambda *args: (collection, entry))
    monkeypatch.setattr(ablation.benchmark_fixtures, "age_days", lambda num: 1.0)
    monkeypatch.setattr(ablation, "build_variant_crew", lambda *args, **kwargs: (Recording(), report_task))
    cell = ScheduleCell(schedule_index=1, block_id=f"{_NUM}-r1", position=1, num=_NUM, topic=_TOPIC,
                        expected_trl_range=(5, 7), industry="Energy", rep=1, variant=variant)
    output_root = Path(__file__).parents[1] / "outputs"
    output_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="test-ablation-inputs-", dir=output_root) as raw:
        ablation.run_cell(cell, experiment_id="test_inputs", experiment_root=Path(raw),
                          commit_sha="test", max_execution_time=max_execution_time)
    assert len(received) == 1, "run_cell must kick the crew off exactly once"
    return _placeholders(crew), received[0]


@pytest.mark.parametrize("max_execution_time", [None, 30], ids=["direct-kickoff", "deadline-kickoff"])
@pytest.mark.parametrize("variant", ["monolith", "specialists_writer", "full"])
def test_kickoff_supplies_every_variable_the_arm_interpolates(monkeypatch, variant, max_execution_time):
    needed, inputs = _kickoff_inputs(monkeypatch, variant, max_execution_time)
    missing = needed - set(inputs)
    assert not missing, f"{variant} would fail at kickoff on {sorted(missing)}"


@pytest.mark.parametrize("variant", ["specialists_writer", "full"])
def test_the_production_arms_run_as_orientation_runs_like_august(monkeypatch, variant):
    """No arm gets a decision context: the August study had none to give."""
    _needed, inputs = _kickoff_inputs(monkeypatch, variant, None)
    assert inputs["assessment_mode"] == "orientation"
    assert inputs["decision_context_json"] == "{}"
