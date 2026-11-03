"""Registered outcomes of a topology-ablation experiment, from its persisted cells only.

    uv run python scripts/ablation_outcomes.py outputs/ablation/<experiment-id> [--write-figures]

Prints the outcome table of the August "Stage 2 full-study outcome" (completed,
finding-free, contract findings, grounding, median tokens, cost and elapsed
time), the paired comparisons behind P1-P4, the six-node reviewer diagnostics
and the per-arm spend. --write-figures also writes article_figures.json into
the experiment directory, computed from successful cells only.

Every number is read from the cells' meta.json, as ablation_check does, never
from terminal output. A missing value stays missing: it is not counted as zero
and does not enter a median.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import median, quantiles
from typing import Any

ARMS = ("monolith", "specialists_writer", "full")
UNCITED = "no inline citation"


def load_cells(experiment: Path) -> list[dict[str, Any]]:
    cells = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(experiment.glob("*/meta.json"))]
    if not cells:
        raise FileNotFoundError(f"no cell metadata under {experiment}")
    return cells


def _ok(cell: dict[str, Any]) -> bool:
    return cell.get("status") == "success"


def _errors(cell: dict[str, Any]) -> list[str]:
    return list((cell.get("report_metrics") or {}).get("validation_errors") or [])


def _grounding(cell: dict[str, Any]) -> dict[str, Any]:
    return (cell.get("report_metrics") or {}).get("grounding") or {}


def _usage(cell: dict[str, Any], key: str) -> float | None:
    value = (cell.get("usage") or {}).get(key)
    return None if value is None or isinstance(value, bool) else float(value)


def _first_attempt_failed(cell: dict[str, Any], task: str | None = None) -> bool | None:
    """Whether the report (or the named task's) guardrail failed its first attempt."""
    record = (cell.get("guardrails") or {}).get(task) if task else cell.get("report_guardrail")
    attempts = (record or {}).get("attempts") or []
    return None if not attempts else not attempts[0].get("passed", False)


def _percentile(values: list[float], fraction: float) -> float:
    """Linear interpolation between closest ranks (numpy's default)."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _median_iqr(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    if len(values) == 1:
        return {"median": values[0], "q1": values[0], "q3": values[0]}
    q1, _, q3 = quantiles(values, n=4, method="inclusive")
    return {"median": median(values), "q1": q1, "q3": q3}


def arm_outcomes(cells: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for arm in ARMS:
        all_cells = [c for c in cells if c.get("variant") == arm]
        ok = [c for c in all_cells if _ok(c)]
        tokens = [v for c in ok if (v := _usage(c, "total_tokens")) is not None]
        cost = [v for c in ok if (v := _usage(c, "cost_usd")) is not None]
        elapsed = [float(c["elapsed_seconds"]) for c in ok if c.get("elapsed_seconds") is not None]
        grounding = [_grounding(c) for c in ok]
        result[arm] = {
            "cells": len(all_cells),
            "completed": len(ok),
            "finding_free": sum(1 for c in ok if not _errors(c)),
            "contract_findings": sum(len(_errors(c)) for c in ok),
            "uncited_findings": sum(1 for c in ok for e in _errors(c) if UNCITED in e),
            "checked_lines": sum(g.get("checked_claim_lines") or 0 for g in grounding),
            "unsupported_lines": sum(g.get("unsupported_claim_lines") or 0 for g in grounding),
            "not_checked_runs": sum(1 for g in grounding if g.get("status") == "not_checked"),
            "median_tokens": median(tokens) if tokens else None,
            "median_cost": round(median(cost), 6) if cost else None,
            "median_elapsed": round(median(elapsed), 3) if elapsed else None,
            "p95_elapsed": round(_percentile(elapsed, 0.95), 3) if elapsed else None,
            "max_elapsed": round(max(elapsed), 3) if elapsed else None,
            "total_cost": round(sum(cost), 6),
            "spend_all_cells": round(sum(v for c in all_cells if (v := _usage(c, "cost_usd")) is not None), 6),
            "first_attempt_report_guardrail_failures": sum(1 for c in ok if _first_attempt_failed(c)),
            "first_attempt_report_guardrail_failures_all_cells": sum(1 for c in all_cells if _first_attempt_failed(c)),
            "failed_cells": [f"{c.get('block_id')}/{arm}: {str(c.get('error', ''))[:160]}"
                             for c in all_cells if not _ok(c)],
        }
    return result


def _blocks(cells: list[dict[str, Any]], left: str, right: str) -> list[tuple[dict, dict]]:
    by_block: dict[str, dict[str, dict]] = {}
    for cell in cells:
        if _ok(cell):
            by_block.setdefault(str(cell.get("block_id")), {})[cell.get("variant")] = cell
    return [(arms[left], arms[right]) for _, arms in sorted(by_block.items()) if left in arms and right in arms]


def _compare(pairs, value) -> dict[str, int]:
    """Blocks where the right arm is lower (better), higher, or tied on `value`."""
    lower = higher = tie = 0
    for left, right in pairs:
        a, b = value(left), value(right)
        lower += b < a
        higher += b > a
        tie += a == b
    return {"pairs": len(pairs), "right_lower": lower, "right_higher": higher, "tie": tie}


def _reduction(pairs, metric) -> list[float]:
    """Paired fractional reduction of the left (larger) arm by the right arm."""
    out = []
    for left, right in pairs:
        a, b = metric(left), metric(right)
        if a not in (None, 0) and b is not None:
            out.append((a - b) / a)
    return out


def paired_outcomes(cells: list[dict[str, Any]]) -> dict[str, Any]:
    mono_four = _blocks(cells, "monolith", "specialists_writer")
    four_full = _blocks(cells, "specialists_writer", "full")
    mono_full = _blocks(cells, "monolith", "full")
    full_four = [(full, four) for four, full in four_full]

    def contract(c):
        return len(_errors(c))

    def unsupported(c):
        return _grounding(c).get("unsupported_claim_lines") or 0

    def first_fail(c):
        return int(bool(_first_attempt_failed(c)))

    def elapsed(c):
        return float(c["elapsed_seconds"])

    return {
        # right = four nodes: right_lower means four had fewer than the monolith
        "four_vs_monolith_contract": _compare(mono_four, contract),
        "four_vs_monolith_unsupported": _compare(mono_four, unsupported),
        "four_vs_monolith_first_attempt_report_failure": _compare(mono_four, first_fail),
        # right = six nodes: right_lower means six had fewer than four
        "full_vs_four_contract": _compare(four_full, contract),
        "full_vs_four_unsupported": _compare(four_full, unsupported),
        # P2 on the blocks where both reports exist
        "full_vs_four_unsupported_lines_on_common_blocks": {
            "four": sum(unsupported(four) for four, _ in four_full),
            "full": sum(unsupported(full) for _, full in four_full),
        },
        # right = six nodes: right_lower means six had fewer than the monolith
        "full_vs_monolith_contract": _compare(mono_full, contract),
        "full_vs_monolith_unsupported": _compare(mono_full, unsupported),
        "full_vs_monolith_first_attempt_report_failure": _compare(mono_full, first_fail),
        # four relative to six: share of six's value that four saved
        "four_vs_full_reduction": {
            "tokens": _median_iqr(_reduction(full_four, lambda c: _usage(c, "total_tokens"))),
            "cost": _median_iqr(_reduction(full_four, lambda c: _usage(c, "cost_usd"))),
            "elapsed": _median_iqr(_reduction(full_four, elapsed)),
        },
    }


def reviewer_diagnostics(cells: list[dict[str, Any]]) -> dict[str, Any]:
    full = [c for c in cells if c.get("variant") == "full"]
    ok = [c for c in full if _ok(c)]
    retention = [float(c["draft_retention_ratio"]) for c in ok if c.get("draft_retention_ratio") is not None]
    corrections = [int(c["reviewer_corrections"]) for c in ok if c.get("reviewer_corrections") is not None]
    reviews = [(c.get("guardrails") or {}).get("report_review_task") or {} for c in full]
    ran = [r for r in reviews if r.get("calls")]
    return {
        "successful_full_runs": len(ok),
        "accepted_corrections": sum(corrections),
        "runs_with_corrections": sum(1 for n in corrections if n > 0),
        "median_retention": median(retention) if retention else None,
        "min_retention": min(retention) if retention else None,
        "review_guardrail_calls": sum(r.get("calls") or 0 for r in reviews),
        "review_first_attempt_failures": sum(1 for r in ran if not (r.get("attempts") or [{}])[0].get("passed", False)),
        "review_retries": sum(r.get("retries") or 0 for r in reviews),
    }


# --- Exploratory, not registered -------------------------------------------
# Two readings added after the October results were seen, to explain them.
# They never replace a registered outcome or enter article_figures.json.

# Items of the writer's "Decision-output contract" (tasks.yaml), added after
# August. Its lines state the mode or an absence ("not established"), so there
# is no source to cite, and the non-blocking uncited-claim screen flags them.
_DECISION_CONTRACT = ("assessment mode", "commercialization route", "decision owner", "cost and time",
                      "go/no_go", "go/no-go", "applicability")


def _report_lines(experiment: Path, cell: dict[str, Any]) -> list[str]:
    directory = experiment / f"{int(cell['schedule_index']):03d}-{cell['num']}-{cell['variant']}-r{cell['rep']}"
    return (directory / "commercialization_report.md").read_text(encoding="utf-8").splitlines()


def uncited_by_line_kind(experiment: Path, cells: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    import re

    result = {}
    for arm in ARMS:
        decision = other = 0
        for cell in (c for c in cells if c.get("variant") == arm and _ok(c)):
            lines = _report_lines(experiment, cell)
            for error in _errors(cell):
                if UNCITED not in error:
                    continue
                number = re.search(r"line (\d+)", error)
                text = lines[int(number.group(1)) - 1].lower() if number else ""
                if any(key in text for key in _DECISION_CONTRACT):
                    decision += 1
                else:
                    other += 1
        result[arm] = {"decision_contract_lines": decision, "other_lines": other}
    return result


def _grounding_recount(markdown: str, allowed: dict[str, Any], *, production_unknown_units: bool) -> dict[str, int]:
    """ablation_check.analyse_numeric_grounding, optionally with production's unknown-unit rule.

    Since 2026-09-11 claim_grounding keeps a figure in unrecognised numeric or
    unit notation out of the checked denominator as unverifiable. The August
    harness calls _supported directly, which returns False for such a figure,
    so the registered screen counts it as unsupported. With the flag off this
    must reproduce the registered counts exactly.
    """
    import re

    from academic_agent.claim_grounding import (
        _UNKNOWN_UNIT, _same_numeric_value, _source_is_checkable, _source_text, _supported, checkable_figures,
    )
    from academic_agent.evidence import parse_citation_ids

    body = markdown.split("## References", maxsplit=1)[0]
    checked = unsupported = unverifiable = 0
    seen: set = set()
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or re.fullmatch(r"[-|:\s]+", line):
            continue
        figures = checkable_figures(line)
        if not figures:
            continue
        source_ids, citation_errors = parse_citation_ids(line)
        key = (line, tuple(sorted(set(source_ids))))
        if key in seen:
            continue
        seen.add(key)
        cited = [allowed[i] for i in key[1] if i in allowed]
        if citation_errors or not cited:
            unverifiable += 1
            continue
        checkable = [s for s in cited if _source_is_checkable(s)]
        if len(checkable) != len(cited):
            unverifiable += 1
            continue
        haystack = " ".join(_source_text(s) for s in checkable)
        present = checkable_figures(haystack)
        if production_unknown_units and (any(unit.startswith(_UNKNOWN_UNIT) for _, unit in figures) or any(
            source_unit.startswith(_UNKNOWN_UNIT)
            and (source_unit == _UNKNOWN_UNIT + "numeric notation" or _same_numeric_value(number, source_number))
            and not _supported(number, unit, present, haystack)
            for number, unit in figures for source_number, source_unit in present
        )):
            unverifiable += 1   # the condition and outcome claim_grounding applies
            continue
        checked += 1
        unsupported += any(not _supported(n, u, present, haystack) for n, u in figures)
    return {"checked_lines": checked, "unsupported_lines": unsupported, "unverifiable_lines": unverifiable,
            "not_checked": int(checked == 0)}


def grounding_recount(experiment: Path, cells: list[dict[str, Any]]) -> dict[str, Any]:
    from experiments.pipeline_audits.ablation_check import _without_reviewer_notes
    from academic_agent.source_pipeline import SourceCollection

    mismatches, result = [], {}
    for arm in ARMS:
        totals = {"checked_lines": 0, "unsupported_lines": 0, "unverifiable_lines": 0, "not_checked_runs": 0}
        for cell in (c for c in cells if c.get("variant") == arm and _ok(c)):
            directory = experiment / f"{int(cell['schedule_index']):03d}-{cell['num']}-{arm}-r{cell['rep']}"
            collection = SourceCollection.model_validate_json(
                (directory / "validated_sources.json").read_text(encoding="utf-8"))
            allowed = {s.source_id: s for s in (*collection.academic_sources, *collection.patent_sources,
                                                *collection.market_sources)}
            markdown = _without_reviewer_notes((directory / "commercialization_report.md").read_text(encoding="utf-8"))
            registered = _grounding_recount(markdown, allowed, production_unknown_units=False)
            recorded = _grounding(cell)
            if (registered["checked_lines"], registered["unsupported_lines"], registered["unverifiable_lines"]) != (
                    recorded.get("checked_claim_lines"), recorded.get("unsupported_claim_lines"),
                    recorded.get("unverifiable_claim_lines")):
                mismatches.append(f"{cell.get('block_id')}/{arm}")
            recount = _grounding_recount(markdown, allowed, production_unknown_units=True)
            for key in ("checked_lines", "unsupported_lines", "unverifiable_lines"):
                totals[key] += recount[key]
            totals["not_checked_runs"] += recount["not_checked"]
        result[arm] = totals
    return {"reproduces_registered_counts": not mismatches, "mismatched_cells": mismatches,
            "production_unknown_unit_rule": result}


def article_figures(arms: dict, paired: dict, reviewer: dict) -> dict[str, Any]:
    """The pre-registered article figures: successful cells only."""
    keys = ("cells", "completed", "uncited_findings", "contract_findings", "checked_lines",
            "unsupported_lines", "median_tokens", "median_cost", "median_elapsed", "max_elapsed",
            "total_cost", "first_attempt_report_guardrail_failures")
    reduction = paired["four_vs_full_reduction"]
    return {
        "arms": {arm: {key: arms[arm][key] for key in keys} for arm in ARMS},
        "four_vs_six_paired_median_reduction": {
            metric: None if reduction[metric] is None else round(reduction[metric]["median"], 6)
            for metric in ("tokens", "cost", "elapsed")
        },
        "reviewer": {
            "median_retention": reviewer["median_retention"],
            "min_retention": reviewer["min_retention"],
            "accepted_corrections": reviewer["accepted_corrections"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("experiment", type=Path)
    parser.add_argument("--write-figures", action="store_true", help="write article_figures.json")
    parser.add_argument("--exploratory", action="store_true",
                        help="also print the two post hoc readings (not registered outcomes)")
    args = parser.parse_args(argv)
    cells = load_cells(args.experiment)
    arms = arm_outcomes(cells)
    paired = paired_outcomes(cells)
    reviewer = reviewer_diagnostics(cells)
    report = {"experiment": args.experiment.name, "cells": len(cells), "arms": arms,
              "paired": paired, "reviewer": reviewer}
    if args.exploratory:
        report["exploratory_not_registered"] = {
            "uncited_by_line_kind": uncited_by_line_kind(args.experiment, cells),
            "grounding_recount": grounding_recount(args.experiment, cells),
        }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.write_figures:
        figures = article_figures(arms, paired, reviewer)
        figures = {"experiment": args.experiment.name, "source": "successful cells' meta.json", **figures}
        path = args.experiment / "article_figures.json"
        path.write_text(json.dumps(figures, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
