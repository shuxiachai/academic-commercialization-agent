"""Integration tests that prevent evidence-pipeline wiring regressions."""

from academic_agent.crew import AcademicAgent

from datetime import date, datetime, timezone
from academic_agent.evidence import EvidenceSource
from academic_agent.source_pipeline import SourceCollection


def _make_collection() -> SourceCollection:
    def sources(prefix: str, source_type: str) -> list[EvidenceSource]:
        return [
            EvidenceSource(
                source_id=f"{prefix}{index}",
                title=f"Validated source {prefix}{index}",
                url=f"https://sources.example.edu/{prefix.lower()}{index}",
                publisher="Validated Publisher",
                published_date=date(2025, 1, index),
                accessed_date=date.today(),
                source_type=source_type,
                evidence_summary="Prevalidated evidence supplied by deterministic code.",
            )
            for index in range(1, 4)
        ]

    return SourceCollection(
        topic="Test commercialization topic",
        collected_at=datetime.now(timezone.utc),
        academic_sources=sources("A", "academic_paper"),
        patent_sources=sources("P", "patent"),
        market_sources=sources("M", "company_disclosure"),
        academic_queries=["academic query"],
        patent_queries=["patent query"],
        market_queries=["market query"],
    )


def test_evidence_pipeline_is_connected(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    crew = AcademicAgent(_make_collection()).crew()

    assert len(crew.tasks) == 6

    # Tasks 0-2: evidence tasks — JSON-mode LLM + evidence guardrail, max 2 retries
    for task in crew.tasks[:3]:
        assert task.output_pydantic is None
        assert task.output_json is None
        assert task.agent is not None
        assert task.agent.llm.response_format == {"type": "json_object"}
        assert task.guardrail is not None
        assert task.guardrail_max_retries == 2

    # Task 3: report writing — markdown mode, guardrail, context = Tasks 0-2
    report_task = crew.tasks[3]
    assert report_task.guardrail is not None
    assert report_task.guardrail_max_retries == 1
    assert report_task.markdown is True
    assert len(report_task.context or []) == 3

    # Task 4: quality reviewer — markdown mode, guardrail, context = Task 3 only
    reviewer_task = crew.tasks[4]
    assert reviewer_task.guardrail is not None
    assert reviewer_task.guardrail_max_retries == 1
    assert reviewer_task.markdown is True
    assert len(reviewer_task.context or []) == 1

    # Task 5: scoring — JSON-mode LLM, guardrail, max 2 retries, context = Tasks 0-2
    scorer_task = crew.tasks[5]
    assert scorer_task.agent is not None
    assert scorer_task.agent.llm.response_format == {"type": "json_object"}
    assert scorer_task.guardrail is not None
    assert scorer_task.guardrail_max_retries == 2
    assert len(scorer_task.context or []) == 3


def test_final_context_reuses_the_research_tasks(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    crew = AcademicAgent(_make_collection()).crew()

    # Scorer (Task 5) context must reuse the same task objects as Tasks 0-2
    scorer_context = crew.tasks[5].context or []
    assert all(crew.tasks[index] is scorer_context[index] for index in range(3))

    # Reviewer (Task 4) context must point to the report task (Task 3)
    reviewer_context = crew.tasks[4].context or []
    assert len(reviewer_context) == 1
    assert crew.tasks[3] is reviewer_context[0]
