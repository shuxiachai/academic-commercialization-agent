"""Analyse benchmark outputs and generate benchmark_summary.csv.

Run after benchmark.py has completed one or more topics:
    uv run python benchmark_check.py

Reads every outputs/benchmark/<num>-<slug>/ directory, checks:
  - Score values and formula correctness (auto-verified)
  - Report section completeness
  - Numeric claims without a citation bracket (hallucination risk indicator)
  - Source counts per domain

Writes outputs/benchmark/benchmark_summary.csv (Excel-friendly UTF-8 BOM).
Also prints a human-readable table to the terminal.
"""

import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from academic_agent.evidence import (
    _NUMERIC_CLAIM_PATTERN,
    _REQUIRED_REPORT_HEADINGS,
)

BENCHMARK_ROOT = Path(__file__).parent / "outputs" / "benchmark"
OUTPUT_CSV = BENCHMARK_ROOT / "benchmark_summary.csv"

# Matches any [A1], [P2], [M3] citation bracket in a line
_CITATION_PATTERN = re.compile(r"\[[APM]\d+\]")

# Lines we should not flag as "uncited numeric claims"
_SKIP_LINE_PREFIXES = ("#", "|", ">", "```", "---", "===")


# ---------------------------------------------------------------------------
# Per-run analysis helpers
# ---------------------------------------------------------------------------

def _check_sections(report: str) -> tuple[bool, list[str]]:
    missing = [h for h in _REQUIRED_REPORT_HEADINGS if h not in report]
    return len(missing) == 0, missing


def _count_numeric_uncited(report: str) -> int:
    """Body lines that contain a number but no citation bracket.

    This is a proxy for hallucination risk: a claim with a number that has
    no [A1]/[P2]/[M3] citation cannot be traced back to a verified source.
    """
    count = 0
    for line in report.splitlines():
        s = line.strip()
        if not s:
            continue
        if any(s.startswith(p) for p in _SKIP_LINE_PREFIXES):
            continue
        if s.endswith(":"):  # intro / section-header lines
            continue
        if _NUMERIC_CLAIM_PATTERN.search(s) and not _CITATION_PATTERN.search(s):
            count += 1
    return count


def _formula_correct(scores: dict) -> bool:
    trl = scores.get("trl_score", 0)
    pat = scores.get("patent_strength", 0)
    mkt = scores.get("market_accessibility", 0)
    evi = scores.get("evidence_confidence", 0)
    overall = scores.get("overall_score", -1)
    expected = round((trl / 9) * 30 + (mkt / 5) * 35 + (pat / 5) * 20 + (evi / 5) * 15)
    return overall == expected


def analyse_run(run_dir: Path) -> dict | None:
    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    row: dict = {
        "case_num":              meta.get("num", "?"),
        "topic":                 meta.get("topic", "?"),
        "status":                meta.get("status", "?"),
        "elapsed_s":             meta.get("elapsed_seconds", ""),
        # Scores
        "overall_score":         "",
        "trl_score":             "",
        "patent_strength":       "",
        "market_accessibility":  "",
        "evidence_confidence":   "",
        "formula_correct":       "",
        # Sources
        "academic_sources":      "",
        "patent_sources":        "",
        "market_sources":        "",
        # Report quality
        "sections_complete":     "",
        "missing_sections":      "",
        "numeric_uncited_lines": "",
        "report_words":          "",
        # Error summary
        "error":                 meta.get("error", ""),
    }

    if meta.get("status") not in ("success",):
        return row

    # --- Scores ---
    scores_path = run_dir / "commercialization_scores.json"
    if scores_path.exists():
        try:
            scores = json.loads(scores_path.read_text(encoding="utf-8"))
            row["overall_score"]        = scores.get("overall_score", "")
            row["trl_score"]            = scores.get("trl_score", "")
            row["patent_strength"]      = scores.get("patent_strength", "")
            row["market_accessibility"] = scores.get("market_accessibility", "")
            row["evidence_confidence"]  = scores.get("evidence_confidence", "")
            row["formula_correct"]      = _formula_correct(scores)
        except Exception:
            row["error"] = "scores JSON parse error"

    # --- Sources ---
    sources_path = run_dir / "validated_sources.json"
    if sources_path.exists():
        try:
            sources = json.loads(sources_path.read_text(encoding="utf-8"))
            row["academic_sources"] = len(sources.get("academic_sources", []))
            row["patent_sources"]   = len(sources.get("patent_sources", []))
            row["market_sources"]   = len(sources.get("market_sources", []))
        except Exception:
            pass

    # --- Report ---
    report_path = run_dir / "commercialization_report.md"
    if report_path.exists():
        try:
            report = report_path.read_text(encoding="utf-8")
            complete, missing = _check_sections(report)
            row["sections_complete"]     = complete
            row["missing_sections"]      = "; ".join(missing)
            row["numeric_uncited_lines"] = _count_numeric_uncited(report)
            row["report_words"]          = len(report.split())
        except Exception:
            pass

    return row


# ---------------------------------------------------------------------------
# Terminal table
# ---------------------------------------------------------------------------

def _print_table(rows: list[dict]) -> None:
    header = (
        f"{'#':>2}  {'Topic':<45}  {'Status':<14}  "
        f"{'Score':>5}  {'TRL':>3}  {'Pat':>3}  {'Mkt':>3}  "
        f"{'Src A/P/M':<9}  {'§OK':>3}  {'Uncited':>7}  {'Words':>5}  {'t(s)':>5}"
    )
    print("\n" + "─" * len(header))
    print(header)
    print("─" * len(header))
    for r in rows:
        if r.get("status") != "success":
            print(
                f"{r['case_num']:>2}  {r['topic'][:45]:<45}  "
                f"{r['status']:<14}  {'—':>5}  {'—':>3}  {'—':>3}  {'—':>3}  "
                f"{'—':<9}  {'—':>3}  {'—':>7}  {'—':>5}  {str(r.get('elapsed_s','')):>5}"
            )
            continue
        src = f"{r['academic_sources']}/{r['patent_sources']}/{r['market_sources']}"
        print(
            f"{r['case_num']:>2}  {r['topic'][:45]:<45}  "
            f"{'success':<14}  "
            f"{str(r['overall_score']):>5}  "
            f"{str(r['trl_score']):>3}  "
            f"{str(r['patent_strength']):>3}  "
            f"{str(r['market_accessibility']):>3}  "
            f"{src:<9}  "
            f"{'Y' if r['sections_complete'] else 'N':>3}  "
            f"{str(r['numeric_uncited_lines']):>7}  "
            f"{str(r['report_words']):>5}  "
            f"{str(r['elapsed_s']):>5}"
        )
    print("─" * len(header))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    run_dirs = sorted(d for d in BENCHMARK_ROOT.iterdir() if d.is_dir())
    if not run_dirs:
        print(f"No benchmark runs found in {BENCHMARK_ROOT}")
        print("Run `uv run python benchmark.py` first.")
        sys.exit(1)

    rows = []
    for run_dir in run_dirs:
        row = analyse_run(run_dir)
        if row:
            rows.append(row)

    if not rows:
        print("No analysable results found.")
        sys.exit(1)

    _print_table(rows)

    fieldnames = [
        "case_num", "topic", "status", "elapsed_s",
        "overall_score", "trl_score", "patent_strength",
        "market_accessibility", "evidence_confidence", "formula_correct",
        "academic_sources", "patent_sources", "market_sources",
        "sections_complete", "missing_sections",
        "numeric_uncited_lines", "report_words", "error",
    ]

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    success = sum(1 for r in rows if r.get("status") == "success")
    print(f"\nResults : {success}/{len(rows)} succeeded")
    print(f"CSV     : {OUTPUT_CSV}")
    print()
    print("Next step: open the CSV in Excel and add a 'human_notes' column")
    print("for manual spot-checks (URL accuracy, TRL plausibility, hallucination).")


if __name__ == "__main__":
    main()
