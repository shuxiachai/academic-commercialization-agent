"""Precision-first report audit tests at the report/evidence seam.

The audit is advisory.  It may flag only the two frozen high-precision forms,
and every uncertain source or unsupported language must remain visibly
unavailable instead of being converted into a clean result.
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from academic_agent.evidence import EvidenceSource
from academic_agent.report_audit import audit_report, save_report_audit
from academic_agent.run_spec import DecisionContext


def _source(
    source_id: str,
    family: str,
    *,
    summary_source: str = "abstract",
    long_summary: bool = True,
) -> EvidenceSource:
    summary = (
        f"This academic study evaluates a {family} solid-state electrolyte and "
        "reports electrochemical transport, interface stability, cycling behaviour, "
        "cell construction, measurement conditions, and observed limitations. "
    )
    if long_summary:
        summary += (
            "The authors describe the experimental protocol, material preparation, "
            "temperature range, impedance analysis, control samples, uncertainty, "
            "and degradation mechanisms in enough detail for evidence checking. " * 3
        )
    return EvidenceSource(
        source_id=source_id,
        title=f"Study of {family} solid-state electrolyte transport",
        url=f"https://example.org/{source_id.lower()}",
        publisher="Example University",
        accessed_date=date.today(),
        source_type="academic_paper",
        evidence_summary=summary,
        summary_source=summary_source,
    )


def _collection(*sources: EvidenceSource) -> SimpleNamespace:
    return SimpleNamespace(
        academic_sources=list(sources),
        patent_sources=[],
        market_sources=[],
    )


def _gate() -> dict[str, object]:
    return DecisionContext().gate_snapshot()


def test_known_qwen_threshold_and_sulfide_to_oxide_mismatch_are_both_visible() -> None:
    report = (
        "# Report\n\n"
        "Pass Threshold: Coulombic efficiency >99.5%; successful demonstration "
        "in a sulfide electrolyte layer [A5]."
    )

    result = audit_report(
        report,
        collection=_collection(_source("A5", "oxide")),
        decision_gate=_gate(),
        output_language="English",
    )

    assert result["status"] == "completed"
    assert result["findings_count"] == 2
    assert {finding["check"] for finding in result["findings"]} == {
        "decision_threshold_provenance",
        "citation_material_scope",
    }
    material = result["citation_material_scope"]
    assert material["checked"] == 1
    assert material["mismatched"] == 1


def test_locally_qualified_threshold_and_matching_family_are_clean() -> None:
    result = audit_report(
        "# Report\n\nAnalyst proposal — Pass Threshold: demonstrate a sulfide "
        "electrolyte layer above the stated efficiency target [A1].",
        collection=_collection(_source("A1", "sulfide")),
        decision_gate=_gate(),
        output_language="English",
    )

    assert result["status"] == "completed"
    assert result["findings_count"] == 0
    assert result["decision_thresholds"]["candidate_lines"] == 1
    assert result["citation_material_scope"]["checked"] == 1


def test_broad_minimum_language_is_not_reclassified_as_a_decision_threshold() -> None:
    result = audit_report(
        "# Report\n\nThe oxide electrolyte retained at least 10,000 cycles [A1].",
        collection=_collection(_source("A1", "oxide")),
        decision_gate=_gate(),
        output_language="English",
    )

    assert result["decision_thresholds"]["status"] == "not_applicable"
    assert result["decision_thresholds"]["unqualified"] == 0


def test_one_matching_citation_prevents_a_mixed_source_false_positive() -> None:
    result = audit_report(
        "# Report\n\nThe sulfide electrolyte layer remains the target [A1, A2].",
        collection=_collection(_source("A1", "sulfide"), _source("A2", "oxide")),
        decision_gate=_gate(),
        output_language="English",
    )

    assert result["citation_material_scope"]["checked"] == 1
    assert result["citation_material_scope"]["mismatched"] == 0


def test_short_or_snippet_evidence_abstains_instead_of_claiming_a_mismatch() -> None:
    result = audit_report(
        "# Report\n\nThe sulfide electrolyte layer is preferred [A1].",
        collection=_collection(
            _source(
                "A1",
                "oxide",
                summary_source="search_snippet",
                long_summary=False,
            )
        ),
        decision_gate=_gate(),
        output_language="English",
    )

    scope = result["citation_material_scope"]
    assert scope["status"] == "unavailable"
    assert scope["checked"] == 0
    assert scope["mismatched"] == 0
    assert scope["unverifiable"] == 1
    assert result["status"] == "partial"


def test_unsupported_language_is_unavailable_not_clean() -> None:
    result = audit_report(
        "# 报告\n\n通过阈值：硫化物电解质效率高于 99%。[A1]",
        collection=_collection(_source("A1", "sulfide")),
        decision_gate=_gate(),
        output_language="Simplified Chinese",
    )

    assert result["status"] == "unavailable"
    assert result["decision_thresholds"]["status"] == "unavailable"
    assert result["citation_material_scope"]["status"] == "unavailable"


def test_saved_audit_keeps_details_on_disk_and_only_bounded_counts_in_status() -> None:
    report = "# Report\n\nPass Threshold: use a sulfide electrolyte layer [A5]."
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        summary = save_report_audit(
            report,
            collection=_collection(_source("A5", "oxide")),
            decision_gate=_gate(),
            output_language="English",
            run_id="audit-run",
            output_root=root,
        )
        artifact = json.loads(
            (root / "audit-run" / "report_audit.json").read_text(encoding="utf-8")
        )

    assert summary == {
        "status": "completed",
        "non_blocking": True,
        "findings": 2,
        "unqualified_thresholds": 1,
        "citation_scope_checked": 1,
        "citation_scope_mismatches": 1,
        "citation_scope_unverifiable": 0,
    }
    assert artifact["findings_count"] == 2
    assert artifact["findings"][0]["excerpt"]
