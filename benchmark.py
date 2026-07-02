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

TOPICS = [
    ("01", "Lithium-ion batteries for electric vehicles"),
    ("02", "Solid-state batteries for grid energy storage"),
    ("03", "Perovskite solar cells for building-integrated photovoltaics"),
    ("04", "Solid-state hydrogen storage for fuel cell vehicles"),
    ("05", "CRISPR gene editing applications in agriculture"),
    ("06", "Room-temperature superconductors"),
    ("07", "Biodegradable plastics from algae"),
    ("08", "AI-powered drug discovery using machine learning"),
    ("09", "Direct air capture of CO2 for carbon removal"),
    ("10", "Quantum computing for pharmaceutical molecular simulation"),
]

BENCHMARK_ROOT = Path(__file__).parent / "outputs" / "benchmark"
_INTER_RUN_PAUSE = 15  # seconds between topics to avoid API rate limits


def _slug(topic: str) -> str:
    return topic.lower().replace(" ", "-")[:45].rstrip("-")


def _run_dir(num: str, topic: str) -> Path:
    return BENCHMARK_ROOT / f"{num}-{_slug(topic)}"


def _already_succeeded(run_dir: Path) -> bool:
    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return meta.get("status") == "success"
    except Exception:
        return False


def run_topic(num: str, topic: str) -> dict:
    run_dir = _run_dir(num, topic)
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 62}")
    print(f"  [{num}/10]  {topic}")
    print(f"{'=' * 62}")

    if _already_succeeded(run_dir):
        print("  → Already succeeded — skipping.")
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
        meta["skipped"] = True
        return meta

    meta: dict = {"num": num, "topic": topic, "run_dir": str(run_dir), "status": "running"}
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
            print(
                f"     Score: overall={scores.get('overall_score')}  "
                f"TRL={scores.get('trl_score')}/9  "
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
        (num, topic)
        for num, topic in TOPICS
        if (only_set is None or num in only_set) and num not in skip_set
    ]

    BENCHMARK_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"Benchmark root : {BENCHMARK_ROOT}")
    print(f"Topics to run  : {len(selected)}")

    results = []
    for i, (num, topic) in enumerate(selected):
        meta = run_topic(num, topic)
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
