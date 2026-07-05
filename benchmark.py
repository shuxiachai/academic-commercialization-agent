"""Batch benchmark runner — runs all 10 test topics and saves full outputs.

Usage:
    uv run python benchmark.py              # run all 10 topics
    uv run python benchmark.py --only 01,06 # run specific cases by number
    uv run python benchmark.py --skip 03,04 # skip already-tested cases

Each topic writes to outputs/benchmark/<num>-<slug>/:
    validated_sources.json
    commercialization_report.md
    commercialization_scores.json
    meta.json   ← status, elapsed time, error message if any

Already-succeeded runs are skipped automatically on re-run.
Run benchmark_check.py afterwards to generate benchmark_summary.csv.
"""

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")

sys.path.insert(0, str(Path(__file__).parent / "src"))

from academic_agent.crew import AcademicAgent
from academic_agent.source_pipeline import SourceCollectionError, collect_source_collection

# Each entry: (case_number, topic_string, (expected_trl_min, expected_trl_max), industry)
# expected_trl_range is saved in meta.json so benchmark_check.py can flag calibration issues.
#
# Selection rationale:
#   Cases 01-02: high TRL (7-9) — system should give strong scores; false negatives here are bad
#   Cases 03-05: mid TRL (5-7) — approaching commercial but not fully deployed
#   Cases 06-07: lower-mid TRL (4-6) — partial commercial signal, harder to judge
#   Cases 08-09: low TRL (3-4) — high hype, minimal commercial signal; false positives are bad
#   Case 10:     very low TRL (1-2) — hallucination stress test; should score near-minimum
TOPICS = [
    ("01", "CAR-T cell therapy for blood cancers",                    (7, 9), "Biomed"),
    ("02", "mRNA vaccines for cancer immunotherapy",                   (6, 8), "Biomed"),
    ("03", "solid-state batteries for electric vehicles",              (5, 7), "Energy"),
    ("04", "perovskite solar cells for utility-scale power generation",(4, 6), "Clean Energy"),
    ("05", "CRISPR gene editing for genetic diseases",                 (6, 8), "Biomed"),
    ("06", "carbon capture and storage for industrial emissions",      (5, 7), "Climate"),
    ("07", "cultivated meat for food industry",                        (4, 6), "Food"),
    ("08", "quantum computing for drug discovery",                     (2, 4), "Computing"),
    ("09", "graphene-based flexible electronics",                      (3, 5), "Materials"),
    ("10", "room temperature ambient pressure superconductors",        (1, 2), "Materials"),
]

BENCHMARK_ROOT = Path(__file__).parent / "outputs" / "benchmark"
_INTER_RUN_PAUSE = 15  # seconds between topics to avoid API rate limits


def _slug(topic: str) -> str:
    return topic.lower().replace(" ", "-")[:45].rstrip("-")


def _run_dir(num: str, topic: str) -> Path:
    return BENCHMARK_ROOT / f"{num}-{_slug(topic)}"


def _trl_flag(trl, trl_range: tuple) -> str:
    if not isinstance(trl, int):
        return "?"
    return "pass" if trl_range[0] <= trl <= trl_range[1] else "flag"


def _already_succeeded(run_dir: Path) -> bool:
    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return meta.get("status") == "success"
    except Exception:
        return False


def run_topic(num: str, topic: str, trl_range: tuple, industry: str) -> dict:
    run_dir = _run_dir(num, topic)
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 62}")
    print(f"  [{num}/10]  {topic}  [{industry}]")
    print(f"  Expected TRL: {trl_range[0]}–{trl_range[1]}")
    print(f"{'=' * 62}")

    if _already_succeeded(run_dir):
        print("  → Already succeeded — skipping.")
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
        meta["skipped"] = True
        return meta

    meta: dict = {
        "num": num,
        "topic": topic,
        "industry": industry,
        "expected_trl_range": list(trl_range),
        "run_dir": str(run_dir),
        "status": "running",
    }
    start = time.time()

    try:
        # Step 0: deterministic source collection
        print("  → Collecting and validating sources...")
        source_collection = collect_source_collection(topic)
        (run_dir / "validated_sources.json").write_text(
            source_collection.model_dump_json(indent=2), encoding="utf-8"
        )
        a_count = len(source_collection.academic_sources)
        p_count = len(source_collection.patent_sources)
        m_count = len(source_collection.market_sources)
        print(f"     Sources: {a_count} academic / {p_count} patent / {m_count} market")

        # Steps 1–6: crew run
        print("  → Running 6-agent crew (5–8 min)...")
        result = AcademicAgent(source_collection).crew().kickoff(
            inputs=source_collection.crew_inputs()
        )

        tasks_output = getattr(result, "tasks_output", None) or []
        if len(tasks_output) >= 2:
            report_raw = tasks_output[-2].raw   # Task 5 = reviewer = Markdown report
            scores_raw = tasks_output[-1].raw   # Task 6 = scorer  = JSON scorecard
        else:
            report_raw = result.raw
            scores_raw = None

        (run_dir / "commercialization_report.md").write_text(report_raw, encoding="utf-8")
        if scores_raw:
            (run_dir / "commercialization_scores.json").write_text(
                scores_raw, encoding="utf-8"
            )
            scores = json.loads(scores_raw)
            trl = scores.get("trl_score")
            overall = scores.get("overall_score")
            flag = _trl_flag(trl, trl_range)
            meta["trl_score"] = trl
            meta["trl_calibration"] = flag
            icon = "✓" if flag == "pass" else "⚠"
            print(
                f"     Score: overall={overall}  "
                f"TRL={trl}/9 [{icon} {flag}, expected {trl_range[0]}–{trl_range[1]}]  "
                f"market={scores.get('market_accessibility')}/5"
            )

        meta["status"] = "success"

    except SourceCollectionError as exc:
        # Source collection failed — record separately so we can diagnose
        meta["status"] = "error_sources"
        meta["error"] = str(exc)
        (run_dir / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        print(f"  ✗ Source collection failed: {exc}")

    except Exception:
        err_text = traceback.format_exc()
        meta["status"] = "error_crew"
        meta["error"] = err_text.splitlines()[-1]
        (run_dir / "error.log").write_text(err_text, encoding="utf-8")
        print(f"  ✗ Crew failed: {meta['error']}")

    meta["elapsed_seconds"] = round(time.time() - start)
    (run_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    icon = "✓" if meta["status"] == "success" else "✗"
    print(f"  {icon} Done in {meta['elapsed_seconds']}s  [{meta['status']}]")
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description="Run benchmark topics through the pipeline.")
    parser.add_argument(
        "--only",
        metavar="01,02",
        help="Comma-separated case numbers to run (e.g. --only 01,06)",
    )
    parser.add_argument(
        "--skip",
        metavar="03,04",
        help="Comma-separated case numbers to skip",
    )
    args = parser.parse_args()

    only_set = {n.strip() for n in args.only.split(",")} if args.only else None
    skip_set = {n.strip() for n in args.skip.split(",")} if args.skip else set()

    selected = [
        (num, topic, trl_range, industry)
        for num, topic, trl_range, industry in TOPICS
        if (only_set is None or num in only_set) and num not in skip_set
    ]

    BENCHMARK_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"Benchmark root : {BENCHMARK_ROOT}")
    print(f"Topics to run  : {len(selected)}")

    results = []
    for i, (num, topic, trl_range, industry) in enumerate(selected):
        meta = run_topic(num, topic, trl_range, industry)
        results.append(meta)
        if i < len(selected) - 1 and not meta.get("skipped"):
            print(f"  → Pausing {_INTER_RUN_PAUSE}s before next topic...")
            time.sleep(_INTER_RUN_PAUSE)

    success = sum(1 for r in results if r.get("status") == "success")
    skipped = sum(1 for r in results if r.get("skipped"))
    failed = len(results) - success - skipped

    print(f"\n{'=' * 62}")
    print(f"  Benchmark complete")
    print(f"  Succeeded : {success}   Skipped : {skipped}   Failed : {failed}")
    print(f"\n  Run `uv run python benchmark_check.py` to generate the summary CSV.")


if __name__ == "__main__":
    main()
