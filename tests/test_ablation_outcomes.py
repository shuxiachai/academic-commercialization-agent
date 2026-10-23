"""The ablation outcome script counts what was registered and nothing it invents.

On the August study's persisted cells it reproduces every figure of the
"Stage 2 full-study outcome" section. That output is local, so these tests pin
the rules on synthetic cells instead: a failed cell is neither a zero nor a
median entry, an uncited finding is only "no inline citation", and a pair
needs both arms to have succeeded in the same block.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ablation_outcomes.py"
_spec = importlib.util.spec_from_file_location("ablation_outcomes", SCRIPT)
outcomes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(outcomes)


def _cell(block, variant, *, status="success", tokens=1000, cost=0.01, elapsed=10.0, errors=(),
          checked=2, unsupported=0, first_attempt_passed=True, retention=None, corrections=None):
    attempts = [{"passed": first_attempt_passed}] + ([] if first_attempt_passed else [{"passed": True}])
    return {
        "block_id": block, "variant": variant, "status": status, "elapsed_seconds": elapsed,
        "usage": {"total_tokens": tokens, "cost_usd": cost},
        "report_metrics": {"validation_errors": list(errors),
                           "grounding": {"status": "pass" if checked else "not_checked",
                                         "checked_claim_lines": checked, "unsupported_claim_lines": unsupported}},
        "report_guardrail": {"calls": len(attempts), "attempts": attempts},
        "guardrails": {}, "draft_retention_ratio": retention, "reviewer_corrections": corrections,
        "error": "" if status == "success" else "reviewer JSON truncated",
    }


def _write(tmp_path, cells):
    for index, cell in enumerate(cells, start=1):
        directory = tmp_path / f"{index:03d}"
        directory.mkdir()
        (directory / "meta.json").write_text(json.dumps(cell), encoding="utf-8")
    return tmp_path


def test_a_failed_cell_is_reported_but_never_counted_as_a_zero(tmp_path):
    cells = outcomes.load_cells(_write(tmp_path, [
        _cell("01-r1", "full", tokens=80_000, cost=0.03),
        _cell("02-r1", "full", tokens=60_000, cost=0.02),
        _cell("03-r1", "full", status="error_crew", tokens=40_000, cost=0.04, checked=0),
    ]))
    full = outcomes.arm_outcomes(cells)["full"]
    assert (full["cells"], full["completed"]) == (3, 2)
    assert full["median_tokens"] == 70_000            # not pulled down by the failed cell
    assert full["total_cost"] == 0.05                 # successful cells only (article figure)
    assert full["spend_all_cells"] == 0.09            # what was actually spent
    assert full["not_checked_runs"] == 0              # the failed cell's report was never screened
    assert full["failed_cells"] == ["03-r1/full: reviewer JSON truncated"]


def test_only_missing_inline_citations_count_as_uncited_findings(tmp_path):
    cells = outcomes.load_cells(_write(tmp_path, [_cell("01-r1", "monolith", errors=(
        "Substantive claim on report line 4 has no inline citation.",
        "Unknown source ID [X9] cited on line 7.",
    ))]))
    monolith = outcomes.arm_outcomes(cells)["monolith"]
    assert (monolith["contract_findings"], monolith["uncited_findings"], monolith["finding_free"]) == (2, 1, 0)


def test_pairs_need_both_arms_to_succeed_in_the_same_block(tmp_path):
    cells = outcomes.load_cells(_write(tmp_path, [
        _cell("01-r1", "specialists_writer", tokens=40_000, first_attempt_passed=False),
        _cell("01-r1", "full", tokens=80_000),
        _cell("01-r1", "monolith"),
        _cell("02-r1", "specialists_writer", tokens=30_000),
        _cell("02-r1", "full", status="error_crew"),
    ]))
    paired = outcomes.paired_outcomes(cells)
    assert paired["four_vs_full_reduction"]["tokens"]["median"] == 0.5   # block 02 has no full report
    assert paired["four_vs_monolith_first_attempt_report_failure"] == {
        "pairs": 1, "right_lower": 0, "right_higher": 1, "tie": 0}


def test_article_figures_carry_exactly_the_registered_fields(tmp_path):
    experiment = _write(tmp_path, [_cell("01-r1", arm, retention=0.99, corrections=1) for arm in outcomes.ARMS])
    assert outcomes.main([str(experiment), "--write-figures"]) == 0
    figures = json.loads((experiment / "article_figures.json").read_text(encoding="utf-8"))
    assert set(figures["arms"]["full"]) == {
        "cells", "completed", "uncited_findings", "contract_findings", "checked_lines", "unsupported_lines",
        "median_tokens", "median_cost", "median_elapsed", "max_elapsed", "total_cost",
        "first_attempt_report_guardrail_failures"}
    assert set(figures["four_vs_six_paired_median_reduction"]) == {"tokens", "cost", "elapsed"}
    assert figures["reviewer"] == {"median_retention": 0.99, "min_retention": 0.99, "accepted_corrections": 1}
