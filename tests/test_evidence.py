"""Offline tests for evidence contracts and report guardrails."""

import json
from datetime import date, timedelta
from unittest import TestCase
from unittest.mock import patch

from crewai import TaskOutput
from pydantic import ValidationError

from academic_agent.evidence import (
    EvidenceFinding,
    EvidenceReport,
    EvidenceSource,
    make_evidence_guardrail,
    parse_citation_ids,
    validate_academic_evidence,
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
        evidence_summary="This source directly supports the corresponding finding with relevant experimental data.",
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

    def test_report_model_dump_is_json_serializable(self) -> None:
        payload = make_report().model_dump()

        json.dumps(payload)
        self.assertIsInstance(payload["sources"][0]["url"], str)
        self.assertIsInstance(payload["sources"][0]["published_date"], str)
        self.assertIsInstance(payload["sources"][0]["accessed_date"], str)

    def test_raw_json_is_validated_locally(self) -> None:
        report = make_report()
        output = TaskOutput(
            description="test",
            raw=report.model_dump_json(),
            agent="test",
        )
        with patch(
            "academic_agent.evidence.validate_source_reachability",
            return_value=[],
        ):
            success, validated = validate_academic_evidence(output)

        self.assertTrue(success)
        self.assertIs(validated, output)
        self.assertIsInstance(output.pydantic, EvidenceReport)

    def test_non_json_output_is_rejected_without_llm_conversion(self) -> None:
        output = TaskOutput(
            description="test",
            raw="A free-form Markdown report",
            agent="test",
        )

        success, message = validate_academic_evidence(output)

        self.assertFalse(success)
        self.assertIn("exactly one valid JSON object", message)

    def test_unknown_source_reference_fails(self) -> None:
        report = make_report()
        report.findings[2].source_ids = ["A9"]
        errors = validate_evidence_report(report, "A")
        self.assertTrue(any("unknown sources" in error for error in errors))

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
                evidence_summary="This evidence summary is sufficiently descriptive for analysis purposes.",
            )

    def test_future_dates_are_silently_cleared(self) -> None:
        # Future published_date is silently nullified (not rejected) so that
        # market snippets with forecast years do not crash the pipeline.
        src = EvidenceSource(
            source_id="A1",
            title="Future source",
            url="https://research.test-domain.org/future",
            publisher="Publisher",
            published_date=date.today() + timedelta(days=1),
            accessed_date=date.today(),
            source_type="academic_paper",
            evidence_summary="This evidence summary is sufficiently descriptive for analysis purposes.",
        )
        self.assertIsNone(src.published_date)

    def test_duplicate_urls_are_rejected(self) -> None:
        report = make_report()
        report.sources[1].url = report.sources[0].url
        errors = validate_evidence_report(report, "A")
        self.assertTrue(any("same URL" in error for error in errors))

    def test_non_http_url_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            EvidenceSource(
                source_id="A1",
                title="Unsafe URL source",
                url="javascript:alert(1)",
                publisher="Publisher",
                accessed_date=date.today(),
                source_type="academic_paper",
                evidence_summary="This evidence summary is sufficiently descriptive for analysis purposes.",
            )

    def test_reachability_failure_blocks_task_guardrail(self) -> None:
        report = make_report()
        output = TaskOutput(
            description="test",
            raw=report.model_dump_json(),
            pydantic=report,
            agent="test",
        )
        with patch(
            "academic_agent.evidence.validate_source_reachability",
            return_value=["A1 is unreachable"],
        ):
            success, message = validate_academic_evidence(output)
        self.assertFalse(success)
        self.assertIn("unreachable", message)

    def test_unreachable_sources_are_rejected(self) -> None:
        errors = validate_source_reachability(
            make_report(),
            url_checker=lambda url: (False, "offline test failure"),
        )
        self.assertEqual(len(errors), 3)

    def test_bound_guardrail_uses_immutable_validated_sources(self) -> None:
        report = make_report()
        analysis = {
            "scope_summary": report.scope_summary,
            "findings": [
                finding.model_dump(mode="json") for finding in report.findings
            ],
            "limitations": report.limitations,
        }
        output = TaskOutput(
            description="test",
            raw=json.dumps(analysis),
            agent="test",
        )
        guardrail = make_evidence_guardrail(
            "A",
            report.topic,
            report.sources,
            report.search_queries,
        )

        success, validated = guardrail(output)

        self.assertTrue(success)
        self.assertIs(validated, output)
        self.assertEqual(output.pydantic.sources, report.sources)
        self.assertEqual(output.pydantic.search_queries, report.search_queries)

    def test_bound_guardrail_rejects_unknown_source_id(self) -> None:
        report = make_report()
        report.findings[0].source_ids = ["A99"]
        analysis = {
            "scope_summary": report.scope_summary,
            "findings": [
                finding.model_dump(mode="json") for finding in report.findings
            ],
            "limitations": report.limitations,
        }
        output = TaskOutput(
            description="test",
            raw=json.dumps(analysis),
            agent="test",
        )
        guardrail = make_evidence_guardrail(
            "A",
            report.topic,
            report.sources,
            report.search_queries,
        )

        success, message = guardrail(output)

        self.assertFalse(success)
        self.assertIn("unknown sources", message)


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

    def test_unknown_grouped_citation_fails(self) -> None:
        report = self.valid_report.replace(
            "The available evidence indicates an emerging technology [A1].",
            "The available evidence indicates an emerging technology [A1] [P999, P998].",
        )
        errors = validate_final_report(report, self.allowed)
        self.assertTrue(any("unknown source IDs" in error for error in errors))

    def test_substantive_non_numeric_claim_requires_citation(self) -> None:
        report = self.valid_report.replace(
            "The competitive assessment remains evidence-bounded [A1].",
            "This technology is commercially dominant throughout the global market.",
        )
        errors = validate_final_report(report, self.allowed)
        self.assertTrue(any("Substantive claim" in error for error in errors))

    def test_grouped_and_range_citations_are_parsed(self) -> None:
        source_ids, errors = parse_citation_ids("Evidence [A1-A3] and [P2, M4].")
        self.assertEqual(source_ids, ["A1", "A2", "A3", "P2", "M4"])
        self.assertEqual(errors, [])

    def test_malformed_citation_is_rejected(self) -> None:
        report = self.valid_report.replace(
            "The available evidence indicates an emerging technology [A1].",
            "The available evidence indicates an emerging technology [A1 and A2].",
        )
        errors = validate_final_report(report, self.allowed)
        self.assertTrue(any("Malformed citation" in error for error in errors))
    def _report_with_extra_source(
        self,
        source: EvidenceSource,
        claim: str,
    ) -> tuple[str, dict[str, EvidenceSource]]:
        report = self.valid_report.replace(
            "One target industry was identified from the evidence [A1].",
            "One target industry was identified from the evidence [A1].\n" + claim,
        )
        reference = (
            f"[{source.source_id}] {source.title}. {source.publisher}. {source.url}\n"
        )
        report = report.replace("## References\n", "## References\n" + reference)
        return report, {**self.allowed, source.source_id: source}

    def test_fleet_claim_requires_fleet_support_in_cited_summary(self) -> None:
        market_source = EvidenceSource(
            source_id="M1",
            title="General battery market report",
            url="https://example.edu/market-report",
            publisher="Example University",
            accessed_date=date.today(),
            source_type="market_report",
            evidence_summary="The report discusses battery safety, energy density, and manufacturing cycle performance.",
        )
        report, allowed = self._report_with_extra_source(
            market_source,
            "Truck, bus, and fleet users benefit most from the technology [M1].",
        )

        errors = validate_final_report(report, allowed)

        self.assertTrue(any("Unsupported use-case claim" in error for error in errors))

    def test_fleet_claim_passes_when_cited_summary_mentions_application(self) -> None:
        market_source = EvidenceSource(
            source_id="M1",
            title="Commercial fleet battery deployment",
            url="https://example.edu/fleet-report",
            publisher="Example University",
            accessed_date=date.today(),
            source_type="market_report",
            evidence_summary="Commercial truck and bus fleets are evaluated for large-scale EV deployment.",
        )
        report, allowed = self._report_with_extra_source(
            market_source,
            "Truck and bus fleets are evaluated applications [M1].",
        )

        errors = validate_final_report(report, allowed)

        self.assertFalse(any("Unsupported use-case claim" in error for error in errors))

    def test_patent_freedom_to_operate_overclaim_is_rejected(self) -> None:
        report = self.valid_report.replace(
            "This preliminary patent scan is not legal advice or a freedom-to-operate opinion.",
            (
                "This preliminary patent scan is not legal advice or a freedom-to-operate opinion.\n"
                "The identified white space creates freedom-to-operate opportunities [A1]."
            ),
        )

        errors = validate_final_report(report, self.allowed)

        self.assertTrue(any("Patent legal overclaim" in error for error in errors))

    def test_broad_no_government_claim_contradicts_government_source(self) -> None:
        government_source = EvidenceSource(
            source_id="M1",
            title="Government technology assessment",
            url="https://energy.gov/example-assessment",
            publisher="Department of Energy",
            accessed_date=date.today(),
            source_type="government",
            evidence_summary="The government assessment reviews the technology evidence and policy implications.",
        )
        report, allowed = self._report_with_extra_source(
            government_source,
            "A government assessment reviews available evidence [M1].",
        )
        report = report.replace(
            "Only public evidence was reviewed.",
            "Only public evidence was reviewed.\n- No government or independent verification exists.",
        )

        errors = validate_final_report(report, allowed)

        self.assertTrue(any("Source contradiction" in error for error in errors))
    def test_descriptive_limitation_label_is_not_a_citation(self) -> None:
        report = self.valid_report.replace(
            "Only public evidence was reviewed.",
            "Only public evidence was reviewed [Market Source Limitations].",
        )

        errors = validate_final_report(report, self.allowed)

        self.assertTrue(
            any("Noncanonical citation label" in error for error in errors)
        )
    def test_quality_warning_numbers_are_not_revalidated_as_claims(self) -> None:
        report = self.valid_report.replace(
            "Only public evidence was reviewed.",
            (
                "Only public evidence was reviewed.\n\n"
                "### Automated Quality-Control Warnings\n\n"
                "- Numeric claim on report line 19 has no inline citation."
            ),
        )

        errors = validate_final_report(report, self.allowed)

        self.assertFalse(any(error.startswith("Numeric claim") for error in errors))

    def test_numbered_bold_recommendation_heading_is_not_numeric_claim(self) -> None:
        report = self.valid_report.replace(
            "Proceed with staged validation before investment [A1].",
            "**1. Proceed with staged validation**\nProceed carefully [A1].",
        )

        errors = validate_final_report(report, self.allowed)

        self.assertFalse(any(error.startswith("Numeric claim") for error in errors))
