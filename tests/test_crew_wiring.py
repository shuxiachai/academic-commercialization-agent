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

    assert len(crew.tasks) == 4
    for task in crew.tasks[:3]:
        assert task.output_pydantic is None
        assert task.output_json is None
        assert task.agent is not None
        assert task.agent.llm.response_format == {"type": "json_object"}
        assert task.guardrail is not None
        assert task.guardrail_max_retries == 2

    final_task = crew.tasks[-1]
    assert final_task.guardrail is not None
    assert final_task.guardrail_max_retries == 1
    assert len(final_task.context or []) == 3
    assert final_task.markdown is True


def test_final_context_reuses_the_research_tasks(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    crew = AcademicAgent(_make_collection()).crew()
    context = crew.tasks[-1].context or []

    assert all(crew.tasks[index] is context[index] for index in range(3))
