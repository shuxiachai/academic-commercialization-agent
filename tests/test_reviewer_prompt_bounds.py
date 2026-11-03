"""The reviewer prompt states every bound its correction-plan schema enforces.

The schema limited each correction's `reason` to 300 characters, but the
prompt never said so. A model cannot keep to a limit it is never told. On
2026-10-23, with qwen3.8-flash, 21 of 30 first reviewer attempts broke that
one bound. Five runs failed outright after the retry, which only then
showed the limit (results-2026-10-24-agent-topology-ablation-qwen). The prompt
already stated the 20-correction and 2,000-character limits. These tests read
every bound from the schema, so a changed number in either place fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

import benchmark
import benchmark_fixtures
from academic_agent.evidence import ReviewerCorrection, ReviewerCorrectionPlan

_TASKS = Path(__file__).resolve().parents[1] / "src" / "academic_agent" / "config" / "tasks.yaml"


def _max_length(model, field: str) -> int:
    return next(item.max_length for item in model.model_fields[field].metadata if hasattr(item, "max_length"))


def _flat(text: str) -> str:
    return " ".join(text.split())


def _review_prompt() -> str:
    review = yaml.safe_load(_TASKS.read_text(encoding="utf-8"))["report_review_task"]
    return _flat(review["description"] + " " + review["expected_output"])


def test_the_reason_bound_is_stated_with_the_schemas_number():
    bound = _max_length(ReviewerCorrection, "reason")
    prompt = _review_prompt()
    assert f'Keep each "reason" to at most {bound} characters' in prompt
    assert f'"reason": "<what changed and why, at most {bound} characters>"' in prompt


def test_every_other_plan_bound_is_stated_with_the_schemas_number():
    prompt = _review_prompt()
    text_bound = _max_length(ReviewerCorrection, "find")
    assert _max_length(ReviewerCorrection, "replace") == text_bound
    assert f'keep both "find" and "replace" under {text_bound:,} characters' in prompt
    assert f"at most {_max_length(ReviewerCorrectionPlan, 'corrections')} corrections" in prompt


def test_the_review_task_production_builds_carries_the_reason_bound(monkeypatch):
    """The seam: the task object the crew sends, not only the YAML file."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    from academic_agent.crew import AcademicAgent

    num, topic, *_ = benchmark.TOPICS[0]
    collection = benchmark_fixtures.load(num, benchmark._slug(topic))
    assert collection is not None, "committed fixture missing"
    review = next(task for task in AcademicAgent(collection).crew().tasks if task.name == "report_review_task")
    bound = _max_length(ReviewerCorrection, "reason")
    assert re.search(rf'"reason" to at most {bound} characters', _flat(review.description))
    assert f"at most {bound} characters" in _flat(review.expected_output)
