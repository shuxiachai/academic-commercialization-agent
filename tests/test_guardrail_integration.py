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


def test_final_guardrail_repairs_model_citation_variants() -> None:
    context = [_context_task(prefix) for prefix in ("A", "P", "M")]
    guardrail = make_final_report_guardrail(context)
    markdown = _final_markdown().replace(
        "The available evidence supports the maturity assessment [A1].",
        "The available evidence supports the maturity assessment [AF1, A2 limitations].",
    )
    markdown = markdown.replace(
        "## Evidence Limitations",
        "## 6. Evidence Limitations",
    )
    markdown = markdown.split("## References", maxsplit=1)[0] + (
        "## References\nAF1. Model-authored finding reference\n"
    )
    output = TaskOutput(description="final report", raw=markdown, agent="writer")

    success, validated = guardrail(output)

    assert success is True
    assert validated is output
    assert "[AF1" not in validated.raw
    assert "A2 limitations" not in validated.raw
    assert "## 6. Evidence Limitations" not in validated.raw
    assert "## Evidence Limitations" in validated.raw
    assert "[A1] Validated source A1." in validated.raw
    assert "[A2] Validated source A2." in validated.raw


def _guardrail_result(markdown: str):
    context = [_context_task(prefix) for prefix in ("A", "P", "M")]
    output = TaskOutput(description="final report", raw=markdown, agent="writer")
    return make_final_report_guardrail(context)(output)


def test_final_guardrail_expands_ranges_and_discards_unknown_findings() -> None:
    markdown = _final_markdown().replace(
        "The available evidence supports the maturity assessment [A1].",
        (
            "The available evidence supports the maturity assessment "
            "[A1-A3 limitations] [PF999]."
        ),
    )

    success, validated = _guardrail_result(markdown)

    assert success is True
    assert "[A1, A2, A3]" in validated.raw
    assert "PF999" not in validated.raw
    assert "[A2] Validated source A2." in validated.raw
    assert "[A3] Validated source A3." in validated.raw


def test_final_guardrail_references_only_cited_sources() -> None:
    success, validated = _guardrail_result(_final_markdown())

    assert success is True
    assert "[A1] Validated source A1." in validated.raw
    assert "[P1] Validated source P1." in validated.raw
    assert "[M1] Validated source M1." in validated.raw
    assert "[A2] Validated source A2." not in validated.raw
    assert "[P2] Validated source P2." not in validated.raw
    assert "[M2] Validated source M2." not in validated.raw


def test_final_guardrail_blocks_missing_core_heading() -> None:
    markdown = _final_markdown().replace(
        "## 4. Competitive Landscape",
        "### Competitive Notes",
    )

    success, message = _guardrail_result(markdown)

    assert success is False
    assert "Missing required heading: ## 4. Competitive Landscape" in message


def test_final_guardrail_blocks_report_without_source_citations() -> None:
    markdown = _final_markdown()
    for source_id in ("A1", "P1", "M1"):
        markdown = markdown.replace(f"[{source_id}]", "")

    success, message = _guardrail_result(markdown)

    assert success is False
    assert "report body contains no source citations" in message.lower()


def test_final_guardrail_inserts_patent_disclaimer() -> None:
    markdown = _final_markdown().replace(
        (
            "The preliminary patent discussion uses validated evidence [P1]. "
            "This is not legal advice or a freedom-to-operate opinion."
        ),
        "The preliminary patent discussion uses validated evidence [P1].",
    )

    success, validated = _guardrail_result(markdown)

    assert success is True
    assert "not legal advice" in validated.raw.lower()
    assert "freedom-to-operate opinion" in validated.raw.lower()


def test_final_guardrail_blocks_unusable_short_report() -> None:
    success, message = _guardrail_result("short report")

    assert success is False
    assert "too short" in message.lower()

def test_final_guardrail_reports_substantive_claim_without_citation() -> None:
    markdown = _final_markdown().replace(
        "The competitive assessment is bounded by public evidence [M1].",
        "The technology is commercially dominant across the global market.",
    )

    success, validated = _guardrail_result(markdown)

    assert success is True
    assert "### Automated Quality-Control Warnings" in validated.raw
    assert "Substantive claim on report line" in validated.raw


def test_final_guardrail_reports_unsupported_fleet_claim() -> None:
    markdown = _final_markdown().replace(
        "The target use case is grounded in market evidence [M1].",
        "Truck and bus fleets benefit most from the technology [M1].",
    )

    success, validated = _guardrail_result(markdown)

    assert success is True
    assert "Unsupported use-case claim" in validated.raw


def test_final_guardrail_repairs_patent_legal_overclaim() -> None:
    markdown = _final_markdown().replace(
        "The preliminary patent discussion uses validated evidence [P1].",
        (
            "The preliminary patent discussion uses validated evidence [P1]. "
            "The white space creates freedom-to-operate opportunities [P1]."
        ),
    )

    success, validated = _guardrail_result(markdown)

    assert success is True
    assert "freedom-to-operate opportunities" not in validated.raw
    assert "dedicated freedom-to-operate analysis" in validated.raw


def test_final_guardrail_removes_descriptive_limitation_label() -> None:
    markdown = _final_markdown().replace(
        "This offline test uses synthetic evidence.",
        "This offline test uses synthetic evidence [Market Source Limitations].",
    )

    success, validated = _guardrail_result(markdown)

    assert success is True
    assert "[Market Source Limitations]" not in validated.raw

def test_final_guardrail_normalizes_parenthetical_source_ids() -> None:
    markdown = _final_markdown().replace(
        "The technology has documented evidence [A1].",
        "The technology has documented evidence (A1).",
    )

    success, validated = _guardrail_result(markdown)

    assert success is True
    assert "documented evidence [A1]." in validated.raw
    assert "documented evidence (A1)." not in validated.raw
