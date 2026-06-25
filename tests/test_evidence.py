"""Offline tests for evidence contracts and report guardrails."""

from datetime import date, timedelta
from unittest import TestCase

from pydantic import ValidationError

from academic_agent.evidence import (
    EvidenceFinding,
    EvidenceReport,
    EvidenceSource,
    validate_evidence_report,
    validate_final_report,
    validate_source_reachability,
)


def make_source(source_id: str) -> EvidenceSource:
    return EvidenceSource(
        source_id=source_id,
        title=f"Credible source {source_id}",
        url=f"https://research.test-domain.org/{source_id.lower()}",
        publisher="Research Publisher",
        published_date=date(2026, 1, 10),
        accessed_date=date.today(),
        source_type="academic_paper",
        evidence_summary="This source directly supports the corresponding finding.",
    )


def make_finding(finding_id: str, source_id: str) -> EvidenceFinding:
    return EvidenceFinding(
        finding_id=finding_id,
        category="technology maturity",
        claim="A sufficiently detailed and externally supportable research conclusion.",
        claim_type="observed_fact",
        source_ids=[source_id],
        confidence="high",
        commercial_implication="This affects the commercialization pathway.",
    )


def make_report(prefix: str = "A") -> EvidenceReport:
    return EvidenceReport(
        topic="Neuromorphic computing",
        scope_summary="A bounded review of technical maturity and published evidence.",
        search_queries=["neuromorphic computing commercial maturity"],
        findings=[
            make_finding(f"{prefix}F1", f"{prefix}1"),
            make_finding(f"{prefix}F2", f"{prefix}2"),
            make_finding(f"{prefix}F3", f"{prefix}3"),
        ],
        sources=[
            make_source(f"{prefix}1"),
            make_source(f"{prefix}2"),
            make_source(f"{prefix}3"),
        ],
        limitations=["Publicly available evidence may omit private deployments."],
    )


class EvidenceValidationTests(TestCase):
    def test_valid_report_passes(self) -> None:
        self.assertEqual(validate_evidence_report(make_report(), "A"), [])

    def test_unknown_source_reference_fails(self) -> None:
        report = make_report()
        report.findings[2].source_ids = ["A9"]
        errors = validate_evidence_report(report, "A")
        self.assertTrue(any("unknown sources" in error for error in errors))
        self.assertTrue(any("unused sources" in error for error in errors))

    def test_inference_without_limitation_fails(self) -> None:
        report = make_report("M")
        report.findings[0].claim_type = "analyst_inference"
        errors = validate_evidence_report(report, "M")
        self.assertTrue(any("must state its limitations" in error for error in errors))

    def test_invalid_doi_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            EvidenceSource(
                source_id="A1",
                title="Invalid DOI source",
                doi="not-a-doi",
                publisher="Publisher",
                accessed_date=date.today(),
                source_type="academic_paper",
                evidence_summary="This evidence summary is sufficiently descriptive.",
            )

    def test_future_dates_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            EvidenceSource(
                source_id="A1",
                title="Future source",
                url="https://research.test-domain.org/future",
                publisher="Publisher",
                published_date=date.today() + timedelta(days=1),
                accessed_date=date.today(),
                source_type="academic_paper",
                evidence_summary="This evidence summary is sufficiently descriptive.",
            )

    def test_duplicate_urls_are_rejected(self) -> None:
        report = make_report()
        report.sources[1].url = report.sources[0].url
        errors = validate_evidence_report(report, "A")
        self.assertTrue(any("same URL" in error for error in errors))

    def test_unreachable_sources_are_rejected(self) -> None:
        errors = validate_source_reachability(
            make_report(),
            url_checker=lambda url: (False, "offline test failure"),
        )
        self.assertEqual(len(errors), 3)


class FinalReportValidationTests(TestCase):
    def setUp(self) -> None:
        self.source = make_source("A1")
        self.allowed = {"A1": self.source}
        self.valid_report = f"""# Academic Commercialization Assessment: Test

## Executive Summary
The technology reached level 5 in the assessed framework [A1].

## 1. Technology Overview & Maturity
The available evidence indicates an emerging technology [A1].

## 2. Patent Landscape & White Spaces
This preliminary patent scan is not legal advice or a freedom-to-operate opinion.

## 3. Target Industries & Use Cases
One target industry was identified from the evidence [A1].

## 4. Competitive Landscape
The competitive assessment remains evidence-bounded [A1].

## 5. Commercialization Opportunities & Recommendations
Proceed with staged validation before investment [A1].

## Evidence Limitations
Only public evidence was reviewed.

## References
[A1] {self.source.title}. {self.source.publisher}. {self.source.url}
"""

    def test_valid_final_report_passes(self) -> None:
        self.assertEqual(
            validate_final_report(self.valid_report, self.allowed),
            [],
        )

    def test_unknown_citation_fails(self) -> None:
        report = self.valid_report.replace("[A1].", "[A9].", 1)
        errors = validate_final_report(report, self.allowed)
        self.assertTrue(any("unknown source IDs" in error for error in errors))

    def test_missing_reference_fails(self) -> None:
        report = self.valid_report.replace(
            f"[A1] {self.source.title}. {self.source.publisher}. {self.source.url}",
            "",
        )
        errors = validate_final_report(report, self.allowed)
        self.assertTrue(any("missing from References" in error for error in errors))

    def test_numeric_claim_requires_inline_citation(self) -> None:
        report = self.valid_report.replace(
            "reached level 5 in the assessed framework [A1]",
            "reached level 5 in the assessed framework",
        )
        errors = validate_final_report(report, self.allowed)
        self.assertTrue(any("Numeric claim" in error for error in errors))
