"""Precision-first, non-blocking checks over the delivered report.

The evidence guardrails validate structure and source identity before this
module runs.  This audit covers two much narrower seams that are not safely
decidable by those guardrails: whether decision-threshold language declares
its authority, and whether an electrolyte-family claim points exclusively at
sources that explicitly describe a different family.  Both rules abstain
aggressively.  A paid report is never rejected because of this file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from academic_agent.evidence import EvidenceSource, parse_citation_ids

if TYPE_CHECKING:
    from academic_agent.source_pipeline import SourceCollection


REPORT_AUDIT_FILENAME = "report_audit.json"

# Broad words such as "minimum", "at least", and bare "threshold" matched
# legitimate source facts in 9/30 baseline reports.  Only these decision-gate
# forms survived the zero-network precision census registered in docs/.
_DECISION_THRESHOLD = re.compile(
    r"\b(?:pass|evidence|decision)\s+thresholds?\b"
    r"|\bthresholds?\s+must\s+be\s+met\b"
    r"|\b(?:kill|stop)\s+criteria\b",
    re.IGNORECASE,
)
_THRESHOLD_QUALIFIER = re.compile(
    r"\b(?:owner[- ]approved|approved by (?:the )?(?:owner|user)|"
    r"user[- ]supplied|supplied (?:success )?criteri(?:on|a)|"
    r"analyst (?:proposal|proposed|inference)|proposed by (?:the )?analyst|"
    r"illustrative|requires? (?:owner )?confirmation|to be confirmed|"
    r"pending (?:owner )?approval|external benchmark|source benchmark|"
    r"evidence benchmark|not established)\b",
    re.IGNORECASE,
)

# These are intentionally electrolyte-specific rather than a generic material
# ontology.  Generic "oxide" and "polymer" comparisons cross too many domains
# to support a high-precision contradiction finding.
_ELECTROLYTE_CONTEXT = re.compile(
    r"\b(?:electrolytes?|ionic conductors?|solid[- ]state|electrolyte layers?)\b",
    re.IGNORECASE,
)
_MATERIAL_FAMILIES: dict[str, re.Pattern[str]] = {
    "sulfide": re.compile(
        r"\b(?:sulfides?|sulphides?|thiophosphates?|argyrodites?|lgps|lpscl)\b",
        re.IGNORECASE,
    ),
    "oxide": re.compile(
        r"\b(?:oxides?|garnets?|llzo|nasicon|nzsp)\b",
        re.IGNORECASE,
    ),
    "chloride": re.compile(
        r"\b(?:chlorides?|halides?)\b",
        re.IGNORECASE,
    ),
    "polymer": re.compile(
        r"\b(?:polymers?|polymeric|peo)\b",
        re.IGNORECASE,
    ),
}
_MIN_CHECKABLE_SUMMARY = 400


def _material_families(text: str) -> set[str]:
    """Return frozen electrolyte families only when scope is explicit."""

    if not _ELECTROLYTE_CONTEXT.search(text):
        return set()
    return {
        family
        for family, pattern in _MATERIAL_FAMILIES.items()
        if pattern.search(text)
    }


def _source_registry(collection: "SourceCollection") -> dict[str, EvidenceSource]:
    sources = (
        list(collection.academic_sources)
        + list(collection.patent_sources)
        + list(collection.market_sources)
    )
    return {source.source_id: source for source in sources}


def _audit_thresholds(
    report: str,
    *,
    declared_provenance: str,
    output_language: str,
) -> dict[str, Any]:
    if output_language != "English":
        return {
            "status": "unavailable",
            "reason": "unsupported_report_language",
            "declared_provenance": declared_provenance,
            "candidate_lines": 0,
            "unqualified": 0,
            "findings": [],
        }

    candidates = 0
    findings: list[dict[str, Any]] = []
    lines = report.splitlines()
    for index, line in enumerate(lines):
        if not _DECISION_THRESHOLD.search(line):
            continue
        candidates += 1
        # A label may be immediately preceded by a qualifier heading. Looking
        # farther away would let an unrelated disclaimer qualify the whole
        # report, recreating the ambiguity this check is intended to expose.
        local_context = " ".join(lines[max(0, index - 1): index + 1])
        if _THRESHOLD_QUALIFIER.search(local_context):
            continue
        cited_ids, _errors = parse_citation_ids(line)
        findings.append(
            {
                "check": "decision_threshold_provenance",
                "severity": "warning",
                "line": index + 1,
                "excerpt": line.strip()[:500],
                "cited_source_ids": cited_ids,
                "reason": "decision_threshold_has_no_local_authority_qualifier",
            }
        )

    return {
        "status": "not_applicable" if candidates == 0 else "completed",
        "declared_provenance": declared_provenance,
        "candidate_lines": candidates,
        "unqualified": len(findings),
        "findings": findings,
    }


def _audit_material_scope(
    report: str,
    *,
    collection: "SourceCollection",
    output_language: str,
) -> dict[str, Any]:
    if output_language != "English":
        return {
            "status": "unavailable",
            "reason": "unsupported_report_language",
            "candidate_segments": 0,
            "checked": 0,
            "mismatched": 0,
            "unverifiable": 0,
            "findings": [],
        }

    sources = _source_registry(collection)
    candidates = 0
    checked = 0
    unverifiable = 0
    findings: list[dict[str, Any]] = []

    for index, line in enumerate(report.splitlines()):
        claimed = _material_families(line)
        cited_ids, citation_errors = parse_citation_ids(line)
        if len(claimed) != 1 or not cited_ids:
            continue
        candidates += 1
        claimed_family = next(iter(claimed))
        cited_sources = [sources.get(source_id) for source_id in cited_ids]
        if citation_errors or any(source is None for source in cited_sources):
            unverifiable += 1
            continue

        source_families: dict[str, list[str]] = {}
        checkable = True
        for source in cited_sources:
            assert source is not None  # narrowed by the registry check above
            summary = source.evidence_summary
            if (
                source.summary_source == "search_snippet"
                or len(summary) < _MIN_CHECKABLE_SUMMARY
            ):
                checkable = False
                break
            families = _material_families(f"{source.title}. {summary}")
            # Mixed-family or family-free text cannot establish a direct
            # contradiction, even when one of its words differs from the line.
            if len(families) != 1:
                checkable = False
                break
            source_families[source.source_id] = sorted(families)

        if not checkable:
            unverifiable += 1
            continue

        checked += 1
        if any(
            claimed_family in families for families in source_families.values()
        ):
            continue
        findings.append(
            {
                "check": "citation_material_scope",
                "severity": "warning",
                "line": index + 1,
                "excerpt": line.strip()[:500],
                "claimed_family": claimed_family,
                "cited_source_ids": cited_ids,
                "source_families": source_families,
                "reason": "all_checkable_citations_name_a_different_material_family",
            }
        )

    status = "not_applicable"
    if candidates:
        status = "unavailable" if checked == 0 else "partial" if unverifiable else "completed"
    return {
        "status": status,
        "candidate_segments": candidates,
        "checked": checked,
        "mismatched": len(findings),
        "unverifiable": unverifiable,
        "findings": findings,
    }


def audit_report(
    report: str,
    *,
    collection: "SourceCollection",
    decision_gate: dict[str, Any],
    output_language: str,
) -> dict[str, Any]:
    """Return a complete audit record without modifying or rejecting a report."""

    provenance = decision_gate.get("threshold_provenance") or {}
    declared_provenance = str(provenance.get("status") or "unknown")
    thresholds = _audit_thresholds(
        report,
        declared_provenance=declared_provenance,
        output_language=output_language,
    )
    material_scope = _audit_material_scope(
        report,
        collection=collection,
        output_language=output_language,
    )
    findings = [*thresholds["findings"], *material_scope["findings"]]
    check_states = {thresholds["status"], material_scope["status"]}
    if check_states == {"unavailable"}:
        status = "unavailable"
    elif "unavailable" in check_states or "partial" in check_states:
        status = "partial"
    elif check_states == {"not_applicable"}:
        status = "not_applicable"
    else:
        status = "completed"
    return {
        "schema_version": 1,
        "status": status,
        "non_blocking": True,
        "output_language": output_language,
        "findings_count": len(findings),
        "decision_thresholds": thresholds,
        "citation_material_scope": material_scope,
        "findings": findings,
    }


def save_report_audit(
    report: str,
    *,
    collection: "SourceCollection",
    decision_gate: dict[str, Any],
    output_language: str,
    run_id: str,
    output_root: Path,
) -> dict[str, Any]:
    """Persist details and return the bounded status payload for the client."""

    if not run_id:
        raise ValueError(f"run_id must be a non-empty string, got {run_id!r}")
    result = audit_report(
        report,
        collection=collection,
        decision_gate=decision_gate,
        output_language=output_language,
    )
    run_directory = output_root / run_id
    run_directory.mkdir(parents=True, exist_ok=True)
    (run_directory / REPORT_AUDIT_FILENAME).write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "status": result["status"],
        "non_blocking": True,
        "findings": result["findings_count"],
        "unqualified_thresholds": result["decision_thresholds"]["unqualified"],
        "citation_scope_checked": result["citation_material_scope"]["checked"],
        "citation_scope_mismatches": result["citation_material_scope"]["mismatched"],
        "citation_scope_unverifiable": result["citation_material_scope"]["unverifiable"],
    }
