"""Offline integration tests for context evidence and the final guardrail."""

from datetime import date
from types import SimpleNamespace

from crewai import TaskOutput

from academic_agent.evidence import (
    EvidenceFinding,
    EvidenceReport,
    EvidenceSource,
    make_final_report_guardrail,
)


def _context_task(prefix: str) -> SimpleNamespace:
    sources = [
        EvidenceSource(
            source_id=f"{prefix}{index}",
            title=f"Validated source {prefix}{index}",
            url=f"https://pypi.org/project/crewai/?source={prefix}{index}",
            publisher="PyPI",
            accessed_date=date.today(),
            source_type="other",
            evidence_summary="This validated source supports one integration-test finding.",
        )
        for index in range(1, 4)
    ]
    findings = [
        EvidenceFinding(
            finding_id=f"{prefix}F{index}",
            category="integration test",
            claim="A sufficiently detailed finding for the guardrail integration test.",
            claim_type="observed_fact",
            source_ids=[f"{prefix}{index}"],
            confidence="high",
            commercial_implication="This finding exercises the final report evidence context.",
        )
        for index in range(1, 4)
    ]
    report = EvidenceReport(
        topic="Integration test topic",
        scope_summary="A synthetic report used only for offline guardrail integration testing.",
        search_queries=["offline integration test"],
        findings=findings,
        sources=sources,
        limitations=["This is synthetic test evidence."],
    )
    output = TaskOutput(
        description="context task",
        raw=report.model_dump_json(),
        pydantic=report,
        agent="test agent",
    )
    return SimpleNamespace(output=output)


def _final_markdown() -> str:
    return """# Academic Commercialization Assessment: Test

## Executive Summary
The assessed technology has documented evidence [A1].

## 1. Technology Overview & Maturity
The available evidence supports the maturity assessment [A1].

## 2. Patent Landscape & White Spaces
The preliminary patent discussion uses validated evidence [P1]. This is not legal advice or a freedom-to-operate opinion.

## 3. Target Industries & Use Cases
The target use case is grounded in market evidence [M1].

## 4. Competitive Landscape
The competitive assessment is bounded by public evidence [M1].

## 5. Commercialization Opportunities & Recommendations
The recommendation follows from the cited technical evidence [A1].

## Evidence Limitations
This offline test uses synthetic evidence.

## References
[A1] Validated source A1. PyPI. https://pypi.org/project/crewai/?source=A1
[P1] Validated source P1. PyPI. https://pypi.org/project/crewai/?source=P1
[M1] Validated source M1. PyPI. https://pypi.org/project/crewai/?source=M1
"""


def test_final_guardrail_uses_context_sources() -> None:
    context = [_context_task(prefix) for prefix in ("A", "P", "M")]
    guardrail = make_final_report_guardrail(context)
    output = TaskOutput(
        description="final report",
        raw=_final_markdown(),
        agent="writer",
    )

    success, validated = guardrail(output)

    assert success is True
    assert validated is output


def test_final_guardrail_rejects_unknown_grouped_context_citation() -> None:
    context = [_context_task(prefix) for prefix in ("A", "P", "M")]
    guardrail = make_final_report_guardrail(context)
    markdown = _final_markdown().replace(
        "The available evidence supports the maturity assessment [A1].",
        "The available evidence supports the maturity assessment [A1] [P998, P999].",
    )
    output = TaskOutput(description="final report", raw=markdown, agent="writer")

    success, message = guardrail(output)

    assert success is False
    assert "unknown source IDs" in message
