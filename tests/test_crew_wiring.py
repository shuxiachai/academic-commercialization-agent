"""Integration tests that prevent evidence-pipeline wiring regressions."""

from academic_agent.crew import AcademicAgent
from academic_agent.evidence import EvidenceReport


def test_evidence_pipeline_is_connected() -> None:
    crew = AcademicAgent().crew()

    assert len(crew.tasks) == 4
    for task in crew.tasks[:3]:
        assert task.output_pydantic is EvidenceReport
        assert task.guardrail is not None
        assert task.guardrail_max_retries == 2

    final_task = crew.tasks[-1]
    assert final_task.guardrail is not None
    assert getattr(final_task.guardrail, "__name__", "") != "_check_report_structure"
    assert len(final_task.context or []) == 3
    assert final_task.markdown is True


def test_final_context_reuses_the_research_tasks() -> None:
    crew = AcademicAgent().crew()
    context = crew.tasks[-1].context or []

    assert all(crew.tasks[index] is context[index] for index in range(3))
