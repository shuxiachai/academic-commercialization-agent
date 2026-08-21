"""Analyse agent-topology ablation outputs without making network calls.

The paid runner writes one self-contained ``meta.json`` per cell. This module
keeps report checks and aggregation separate from execution so a completed
batch can be re-analysed after an accounting or presentation bug without
spending another token.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from statistics import mean, median
from typing import Any
from collections.abc import Iterable


ABLATION_ROOT = Path(__file__).parent / "outputs" / "ablation"
VARIANT_ORDER = ("monolith", "specialists_writer", "full")


def _without_reviewer_notes(markdown: str) -> str:
    """Remove deterministic audit notes from the report contract surface.

    Reviewer reasons are appended after References and can themselves mention a
    source ID. Feeding them back through reference validation would treat an
    audit note as a malformed bibliography entry and create a full-arm-only
    false positive.
    """

    return markdown.split("## Reviewer Notes", maxsplit=1)[0].rstrip()


@dataclass(frozen=True)
class FinalReportGrounding:
    """High-precision numeric support screen for delivered Markdown.

    The production grounding screen consumes structured EvidenceReports. An
    ablation needs one common screen after every topology has produced the same
    artifact type: Markdown. Reusing its deliberately conservative number and
    source-support primitives keeps the two screens' meaning aligned. The
    leading-underscore imports are intentional here: duplicating those rules in
    an experiment would let the treatment and production definitions drift.
    """

    status: str
    checked_claim_lines: int
    unsupported_claim_lines: int
    unverifiable_claim_lines: int
    checked_figures: int
    unsupported_figures: tuple[str, ...]
    duplicates_collapsed: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReportMetrics:
    contract_status: str
    validation_errors: tuple[str, ...]
    validation_error_classes: tuple[str, ...]
    required_sections_complete: bool
    word_count: int
    unique_citations: int
    citation_domains: tuple[str, ...]
    grounding: FinalReportGrounding

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["grounding"] = self.grounding.as_dict()
        return data


def _validation_error_class(error: str) -> str:
    """Stable categories for prose errors whose exact wording may improve."""

    lowered = error.lower()
    if "missing required heading" in lowered:
        return "missing_heading"
    if "unknown source" in lowered:
        return "unknown_citation"
    if "missing from references" in lowered:
        return "missing_reference"
    if "uncited source" in lowered:
        return "uncited_reference"
    if "exactly once" in lowered:
        return "duplicate_reference"
    if "validated url or doi" in lowered:
        return "reference_locator"
    if "citation" in lowered or "source id" in lowered:
        return "citation_policy"
    if "patent" in lowered or "freedom to operate" in lowered:
        return "patent_framing"
    return "other"


def analyse_numeric_grounding(
    markdown: str,
    allowed_sources: dict[str, Any],
) -> FinalReportGrounding:
    """Check distinctive figures in report lines against their cited sources.

    A source snippet is a fragment, so absence from it is ``unverifiable`` and
    never ``unsupported``. Likewise, no checkable claim is ``not_checked``
    rather than a vacuous pass. These distinctions are experiment outcomes,
    not presentation details.
    """

    from academic_agent.claim_grounding import (
        _render,
        _source_is_checkable,
        _source_text,
        _supported,
        checkable_figures,
    )
    from academic_agent.evidence import parse_citation_ids

    body = markdown.split("## References", maxsplit=1)[0]
    checked_lines = unsupported_lines = unverifiable_lines = 0
    checked_figures = duplicates_collapsed = 0
    unsupported_figures: list[str] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or re.fullmatch(r"[-|:\s]+", line):
            continue

        figures = checkable_figures(line)
        if not figures:
            continue

        source_ids, citation_errors = parse_citation_ids(line)
        citation_key = tuple(sorted(set(source_ids)))
        duplicate_key = (line, citation_key)
        if duplicate_key in seen:
            duplicates_collapsed += 1
            continue
        seen.add(duplicate_key)

        cited = [allowed_sources[source_id] for source_id in citation_key
                 if source_id in allowed_sources]
        if citation_errors or not cited:
            unverifiable_lines += 1
            continue

        checkable = [source for source in cited if _source_is_checkable(source)]
        if not checkable:
            unverifiable_lines += 1
            continue

        haystack = " ".join(_source_text(source) for source in checkable)
        present = checkable_figures(haystack)
        missing = [
            _render(number, unit)
            for number, unit in figures
            if not _supported(number, unit, present, haystack)
        ]
        checked_lines += 1
        checked_figures += len(figures)
        if missing:
            unsupported_lines += 1
            unsupported_figures.extend(missing)

    if checked_lines == 0:
        status = "not_checked"
    elif unsupported_lines:
        status = "fail"
    else:
        status = "pass"

    return FinalReportGrounding(
        status=status,
        checked_claim_lines=checked_lines,
        unsupported_claim_lines=unsupported_lines,
        unverifiable_claim_lines=unverifiable_lines,
        checked_figures=checked_figures,
        unsupported_figures=tuple(unsupported_figures),
        duplicates_collapsed=duplicates_collapsed,
    )


def analyse_report(
    markdown: str,
    sources: Iterable[Any],
    *,
    required_headings: tuple[str, ...] | None = None,
    output_language: str = "English",
) -> ReportMetrics:
    """Return metrics shared by all three topology arms."""

    allowed = {source.source_id: source for source in sources}
    from academic_agent.evidence import parse_citation_ids, validate_final_report

    contract_markdown = _without_reviewer_notes(markdown)
    errors = validate_final_report(
        contract_markdown,
        allowed,
        required_headings=required_headings,
        output_language=output_language,
    )
    body = contract_markdown.split("## References", maxsplit=1)[0]
    citation_ids, _ = parse_citation_ids(body)
    unique_ids = set(citation_ids)
    error_classes = tuple(dict.fromkeys(_validation_error_class(error) for error in errors))

    return ReportMetrics(
        contract_status="pass" if not errors else "fail",
        validation_errors=tuple(errors),
        validation_error_classes=error_classes,
        required_sections_complete=not any(
            error.startswith("Missing required heading:") for error in errors
        ),
        # Markdown punctuation is not a word. This deliberately measures report
        # scale, not provider tokens, which come from usage accounting below.
        word_count=len(re.findall(r"\b\w+\b", markdown, flags=re.UNICODE)),
        unique_citations=len(unique_ids),
        citation_domains=tuple(sorted({source_id[0] for source_id in unique_ids})),
        grounding=analyse_numeric_grounding(contract_markdown, allowed),
    )


def reviewer_correction_count(report: str) -> int | None:
    """Accepted exact replacements, or None when no reviewer existed."""

    marker = "## Reviewer Notes"
    if marker not in report:
        return None
    notes = report.split(marker, maxsplit=1)[1]
    if "No corrections required." in notes:
        return 0
    return sum(1 for line in notes.splitlines() if line.strip().startswith("- "))


SUMMARY_COLUMNS = (
    "experiment_id",
    "block_id",
    "schedule_index",
    "position",
    "num",
    "rep",
    "topic",
    "variant",
    "nodes",
    "status",
    "fixture_digest",
    "fixture_age_days",
    "elapsed_seconds",
    "total_tokens",
    "total_requests",
    "cost_usd",
    "cost_complete",
    "contract_status",
    "validation_error_count",
    "grounding_status",
    "checked_claim_lines",
    "unsupported_claim_lines",
    "unverifiable_claim_lines",
    "report_guardrail_calls",
    "report_guardrail_failures",
    "report_guardrail_retries",
    "word_count",
    "unique_citations",
    "citation_domains",
    "reviewer_corrections",
    "draft_retention_ratio",
)


def flatten_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Flatten one persisted result; this is the CSV/client boundary."""

    metrics = meta.get("report_metrics") or {}
    grounding = metrics.get("grounding") or {}
    usage = meta.get("usage") or {}
    report_guardrail = meta.get("report_guardrail") or {}
    row = {
        key: meta.get(key, "")
        for key in (
            "experiment_id", "block_id", "schedule_index", "position", "num",
            "rep", "topic", "variant", "nodes", "status", "fixture_digest",
            "fixture_age_days", "elapsed_seconds",
        )
    }
    row.update({
        "total_tokens": usage.get("total_tokens", ""),
        "total_requests": usage.get("total_requests", ""),
        "cost_usd": usage.get("cost_usd", ""),
        "cost_complete": usage.get("cost_complete", ""),
        "contract_status": metrics.get("contract_status", ""),
        "validation_error_count": len(metrics.get("validation_errors") or []),
        "grounding_status": grounding.get("status", ""),
        "checked_claim_lines": grounding.get("checked_claim_lines", ""),
        "unsupported_claim_lines": grounding.get("unsupported_claim_lines", ""),
        "unverifiable_claim_lines": grounding.get("unverifiable_claim_lines", ""),
        "report_guardrail_calls": report_guardrail.get("calls", ""),
        "report_guardrail_failures": report_guardrail.get("failures", ""),
        "report_guardrail_retries": report_guardrail.get("retries", ""),
        "word_count": metrics.get("word_count", ""),
        "unique_citations": metrics.get("unique_citations", ""),
        "citation_domains": ",".join(metrics.get("citation_domains") or []),
        "reviewer_corrections": meta.get("reviewer_corrections", ""),
        "draft_retention_ratio": meta.get("draft_retention_ratio", ""),
    })
    return row


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pairwise_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Paired deltas within one topic/repetition block.

    Pairing is the reason the schedule carries a block ID. Comparing global
    means would let an easy topic in one arm masquerade as an architecture
    effect when a run is missing from another arm.
    """

    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        grouped[str(row.get("block_id", ""))][str(row.get("variant", ""))] = row

    metrics = (
        "elapsed_seconds", "total_tokens", "total_requests", "cost_usd",
        "validation_error_count", "unsupported_claim_lines",
        "report_guardrail_failures", "word_count", "unique_citations",
    )
    result: list[dict[str, Any]] = []
    for block_id, variants in sorted(grouped.items()):
        for left, right in combinations(VARIANT_ORDER, 2):
            if left not in variants or right not in variants:
                continue
            row: dict[str, Any] = {
                "block_id": block_id,
                "left": left,
                "right": right,
            }
            for metric in metrics:
                left_value = _numeric(variants[left].get(metric))
                right_value = _numeric(variants[right].get(metric))
                row[f"{metric}_delta"] = (
                    "" if left_value is None or right_value is None
                    else round(right_value - left_value, 6)
                )
            result.append(row)
    return result


def write_summaries(experiment_root: Path) -> tuple[Path, Path, list[dict[str, Any]]]:
    """Rebuild run and paired CSV files entirely from persisted cell metadata."""

    metas = []
    for path in experiment_root.rglob("meta.json"):
        try:
            metas.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            # Omitting a damaged paid cell would make an incomplete experiment
            # look successful. Stop with the exact artifact instead; callers can
            # repair or rerun it without guessing which result disappeared.
            raise ValueError(
                f"could not inspect ablation metadata: {path}"
            ) from exc
    rows = [flatten_meta(meta) for meta in metas]
    rows.sort(key=lambda row: int(row.get("schedule_index") or 0))

    summary_path = experiment_root / "ablation_summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    paired = pairwise_rows(rows)
    pairwise_path = experiment_root / "ablation_pairwise.csv"
    pair_fields = list(paired[0]) if paired else ["block_id", "left", "right"]
    with pairwise_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=pair_fields)
        writer.writeheader()
        writer.writerows(paired)
    return summary_path, pairwise_path, rows


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Small descriptive summary; never substitutes missing cells with zero."""

    result: dict[str, dict[str, Any]] = {}
    for variant in VARIANT_ORDER:
        arm = [row for row in rows if row.get("variant") == variant]
        successful = [row for row in arm if row.get("status") == "success"]
        summary: dict[str, Any] = {
            "runs": len(arm),
            "successful": len(successful),
        }
        for metric in ("elapsed_seconds", "total_tokens", "cost_usd"):
            values = [_numeric(row.get(metric)) for row in successful]
            observed = [value for value in values if value is not None]
            summary[f"median_{metric}"] = median(observed) if observed else None
            summary[f"mean_{metric}"] = round(mean(observed), 6) if observed else None
        result[variant] = summary
    return result


def _latest_experiment(root: Path) -> Path:
    candidates = sorted(path for path in root.iterdir() if path.is_dir()) if root.exists() else []
    if not candidates:
        raise FileNotFoundError(f"no ablation experiments under {root}")
    return candidates[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path)
    args = parser.parse_args()
    experiment_root = args.path or _latest_experiment(ABLATION_ROOT)
    summary, paired, rows = write_summaries(experiment_root)
    print(json.dumps(aggregate_rows(rows), indent=2, ensure_ascii=False))
    print(f"run summary: {summary}")
    print(f"paired deltas: {paired}")


if __name__ == "__main__":
    main()
