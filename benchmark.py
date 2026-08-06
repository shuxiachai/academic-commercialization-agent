"""Batch benchmark runner — runs the 10 test topics and saves full outputs.

Usage:
    uv run python benchmark.py                    # serial (default)
    uv run python benchmark.py --concurrency 3    # 3 topics at a time
    uv run python benchmark.py --only 01,06       # specific cases by number
    uv run python benchmark.py --skip 03,04       # skip already-tested cases
    uv run python benchmark.py --dry-run -c 3     # exercise scheduling, no API calls

Each topic writes to outputs/benchmark/<num>-<slug>/:
    validated_sources.json
    commercialization_report.md
    commercialization_scores.json
    meta.json   ← status, elapsed time, rate-limit hits, error message if any

Already-succeeded runs are skipped automatically on re-run.
Run benchmark_check.py afterwards to generate benchmark_summary.csv.

Concurrency notes
-----------------
Topics run in separate processes, not threads: CrewAI keeps global state
(the event bus most notably), so running two crews in one interpreter risks
cross-talk between their event streams.

The ceiling on concurrency is upstream API rate limits, not local CPU. Each
topic issues requests at up to MAX_RPM (default 6) to the LLM, plus bursts to
OpenAlex / Serper / Crossref, so the aggregate rate is roughly
`concurrency x MAX_RPM`. Pushing this too high shows up as 429s in meta.json's
`rate_limit_hits`, which is exactly what the field exists to measure — start
at 2-3 and read that number before going higher.
"""

import argparse
import json
import os
import random
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")

sys.path.insert(0, str(Path(__file__).parent / "src"))

# Heavy pipeline imports are deferred into run_topic() so that --dry-run and
# --help stay fast, and so each worker process imports CrewAI independently.

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
    """Classify a TRL against its expected range.

    Accepts floats. The scoring guardrail divides the model's x10 integer by 10,
    so a TRL is only an int when the model happened to write a multiple of ten
    (85 -> 8.5, but 90 -> 9.0 -> 9). An `isinstance(trl, int)` check therefore
    passed on some runs and returned "?" on others for no meaningful reason,
    silently reporting nothing calibrated when scores were in fact accurate.
    bool is excluded because it is a subclass of int.
    """
    if isinstance(trl, bool) or not isinstance(trl, (int, float)):
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


# Substrings that identify an upstream throttling response, whatever the
# provider's exact wording. Counted per topic so concurrency can be tuned
# against real data instead of guesswork.
_RATE_LIMIT_MARKERS = (
    "429",
    "rate limit",
    "ratelimit",
    "too many requests",
    "quota exceeded",
    "overloaded",
)


def _count_rate_limit_hits(text: str) -> int:
    lowered = text.lower()
    return sum(lowered.count(marker) for marker in _RATE_LIMIT_MARKERS)


def _log(message: str = "") -> None:
    """Print unbuffered.

    Pool workers are separate processes whose stdout is block-buffered when
    piped; without an explicit flush a topic's progress would only appear once
    the whole process exits, which for a 3-minute run is useless.
    """
    print(message, flush=True)


def _simulate_topic(num: str, topic: str, trl_range: tuple, industry: str) -> dict:
    """--dry-run stand-in: exercises scheduling without touching any API."""
    start = time.time()
    time.sleep(random.uniform(1.0, 2.5))
    return {
        "num": num,
        "topic": topic,
        "industry": industry,
        "expected_trl_range": list(trl_range),
        "status": "success",
        "dry_run": True,
        "rate_limit_hits": 0,
        "elapsed_seconds": round(time.time() - start, 1),
    }


def run_topic(
    num: str,
    topic: str,
    trl_range: tuple,
    industry: str,
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    """Run one topic end to end. Executed in its own process when concurrent."""
    if dry_run:
        _log(f"  [{num}] dry-run start")
        meta = _simulate_topic(num, topic, trl_range, industry)
        _log(f"  [{num}] dry-run done in {meta['elapsed_seconds']}s")
        return meta

    from academic_agent.crew import AcademicAgent
    from academic_agent.run_output import save_evidence_reports
    from academic_agent.source_pipeline import (
        SourceCollectionError,
        collect_source_collection,
    )

    run_dir = _run_dir(num, topic)
    run_dir.mkdir(parents=True, exist_ok=True)

    _log(f"  [{num}] start — {topic}  [{industry}]  expect TRL {trl_range[0]}–{trl_range[1]}")

    # Skipping succeeded runs makes an interrupted batch resumable, but it also
    # means a plain re-run after changing the pipeline does nothing at all —
    # every topic is skipped and the summary silently reports the old results.
    # --force is the way to re-measure; it rewrites this run's outputs in place.
    if not force and _already_succeeded(run_dir):
        _log(f"  [{num}] already succeeded — skipping (use --force to re-run)")
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
        "rate_limit_hits": 0,
    }
    start = time.time()

    try:
        # Step 0: deterministic source collection
        source_collection = collect_source_collection(topic)
        (run_dir / "validated_sources.json").write_text(
            source_collection.model_dump_json(indent=2), encoding="utf-8"
        )
        a_count = len(source_collection.academic_sources)
        p_count = len(source_collection.patent_sources)
        m_count = len(source_collection.market_sources)
        _log(f"  [{num}] sources: {a_count} academic / {p_count} patent / {m_count} market")

        # Throttling during source collection is recorded in the audit trail
        # rather than raised, so it has to be counted separately from crew errors.
        meta["rate_limit_hits"] += sum(
            _count_rate_limit_hits(" ".join(entry.rejected_reasons))
            for entry in source_collection.audit
        )

        # Steps 1–6: crew run
        result = AcademicAgent(source_collection).crew().kickoff(
            inputs=source_collection.crew_inputs()
        )

        tasks_output = getattr(result, "tasks_output", None) or []

        # Keep the evidence stage for inspection. A benchmark exists to explain
        # why a score came out the way it did, and that reasoning lives in
        # Tasks 1-3 — the report writer and scorer never see the raw registry.
        save_evidence_reports(tasks_output, run_id=run_dir.name, output_root=run_dir.parent)

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
            _log(
                f"  [{num}] score: overall={overall}  "
                f"TRL={trl}/9 [{icon} {flag}, expected {trl_range[0]}–{trl_range[1]}]  "
                f"market={scores.get('market_accessibility')}/5"
            )

        meta["status"] = "success"

    except SourceCollectionError as exc:
        # Source collection failed — record separately so we can diagnose
        meta["status"] = "error_sources"
        meta["error"] = str(exc)
        meta["rate_limit_hits"] += _count_rate_limit_hits(str(exc))
        (run_dir / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        _log(f"  [{num}] ✗ source collection failed: {exc}")

    except Exception:
        err_text = traceback.format_exc()
        meta["status"] = "error_crew"
        meta["error"] = err_text.splitlines()[-1]
        meta["rate_limit_hits"] += _count_rate_limit_hits(err_text)
        (run_dir / "error.log").write_text(err_text, encoding="utf-8")
        _log(f"  [{num}] ✗ crew failed: {meta['error']}")

    meta["elapsed_seconds"] = round(time.time() - start)
    (run_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    icon = "✓" if meta["status"] == "success" else "✗"
    limits = meta.get("rate_limit_hits", 0)
    suffix = f"  [{limits} rate-limit hits]" if limits else ""
    _log(f"  [{num}] {icon} done in {meta['elapsed_seconds']}s  [{meta['status']}]{suffix}")
    return meta


def _run_serial(selected: list[tuple], dry_run: bool, force: bool = False) -> list[dict]:
    """Original behaviour: one topic at a time, with a pause between them."""
    results = []
    for i, (num, topic, trl_range, industry) in enumerate(selected):
        meta = run_topic(num, topic, trl_range, industry, dry_run, force)
        results.append(meta)
        if i < len(selected) - 1 and not meta.get("skipped") and not dry_run:
            _log(f"  → pausing {_INTER_RUN_PAUSE}s before next topic")
            time.sleep(_INTER_RUN_PAUSE)
    return results


def _run_concurrent(
    selected: list[tuple], concurrency: int, stagger: float, dry_run: bool,
    force: bool = False,
) -> list[dict]:
    """Run topics in a process pool, staggering submissions.

    Submissions are spaced by `stagger` seconds because every topic opens with
    the same burst of source-collection requests; releasing them simultaneously
    is the fastest way to get throttled.
    """
    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=concurrency) as pool:
        futures = {}
        for i, (num, topic, trl_range, industry) in enumerate(selected):
            if i and stagger:
                time.sleep(stagger)
            fut = pool.submit(run_topic, num, topic, trl_range, industry, dry_run, force)
            futures[fut] = num

        for done, fut in enumerate(as_completed(futures), start=1):
            num = futures[fut]
            try:
                results.append(fut.result())
            except Exception as exc:                      # worker crashed outright
                _log(f"  [{num}] ✗ worker process died: {exc}")
                results.append({
                    "num": num,
                    "status": "error_worker",
                    "error": str(exc),
                    "rate_limit_hits": 0,
                })
            _log(f"  ── progress: {done}/{len(futures)} topics finished")
    return results


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
    parser.add_argument(
        "-c", "--concurrency",
        type=int,
        default=1,
        metavar="N",
        help="Topics to run at once (default 1 = serial). Start at 2-3; check "
             "rate_limit_hits in the summary before raising it.",
    )
    parser.add_argument(
        "--stagger",
        type=float,
        default=10.0,
        metavar="SECONDS",
        help="Delay between starting each topic when concurrent (default 10)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Exercise scheduling with simulated work — no API calls, no cost",
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Re-run topics that already succeeded, overwriting their outputs. "
             "Needed to re-measure after changing the pipeline — without it "
             "every completed topic is skipped and the summary keeps the old numbers.",
    )
    args = parser.parse_args()

    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")

    only_set = {n.strip() for n in args.only.split(",")} if args.only else None
    skip_set = {n.strip() for n in args.skip.split(",")} if args.skip else set()

    selected = [
        (num, topic, trl_range, industry)
        for num, topic, trl_range, industry in TOPICS
        if (only_set is None or num in only_set) and num not in skip_set
    ]
    if not selected:
        _log("No topics selected — check --only / --skip.")
        return

    concurrency = min(args.concurrency, len(selected))
    max_rpm = os.getenv("MAX_RPM", "6")

    BENCHMARK_ROOT.mkdir(parents=True, exist_ok=True)
    _log(f"Benchmark root : {BENCHMARK_ROOT}")
    _log(f"Topics to run  : {len(selected)}")
    _log(f"Concurrency    : {concurrency}" + ("  (serial)" if concurrency == 1 else ""))
    if concurrency > 1:
        _log(f"Aggregate rate : ~{concurrency} x {max_rpm} RPM to the LLM, plus source-API bursts")
        _log(f"Stagger        : {args.stagger}s between starts")
    if args.dry_run:
        _log("Mode           : DRY RUN — simulated work, no API calls")
    if args.force:
        _log("Mode           : FORCE — re-running topics that already succeeded")
    _log()

    wall_start = time.time()
    if concurrency == 1:
        results = _run_serial(selected, args.dry_run, args.force)
    else:
        results = _run_concurrent(selected, concurrency, args.stagger,
                                  args.dry_run, args.force)
    wall_elapsed = time.time() - wall_start

    # A skipped topic carries the previous run's status ("success"), so counting
    # it in both buckets makes failed go negative. Skipped is its own category.
    skipped = sum(1 for r in results if r.get("skipped"))
    success = sum(1 for r in results
                  if r.get("status") == "success" and not r.get("skipped"))
    failed = len(results) - success - skipped
    limit_hits = sum(r.get("rate_limit_hits", 0) for r in results)
    topic_seconds = sum(r.get("elapsed_seconds", 0) for r in results)

    _log(f"\n{'=' * 62}")
    _log("  Benchmark complete")
    _log(f"  Succeeded : {success}   Skipped : {skipped}   Failed : {failed}")

    # Everything skipped means nothing was measured. Saying so beats a summary
    # that looks like a successful run but reports figures from a previous one.
    if skipped == len(results) and not args.dry_run:
        _log("")
        _log("  ⚠ Every topic was skipped — no new results were produced.")
        _log("    Existing runs are kept so an interrupted batch can resume.")
        _log("    To re-measure after changing the pipeline:")
        _log("        uv run python benchmark.py --force --concurrency 3")
        return

    _log(f"  Wall time : {wall_elapsed / 60:.1f} min"
          f"   (sum of topic times: {topic_seconds / 60:.1f} min)")
    if concurrency > 1 and topic_seconds:
        _log(f"  Speed-up  : {topic_seconds / max(wall_elapsed, 1):.2f}x vs running these serially")
    if limit_hits == 0:
        verdict = "→ headroom to try a higher --concurrency"
    else:
        verdict = "→ throttling observed; lower --concurrency or raise --stagger"
    _log(f"  Rate-limit hits : {limit_hits}  {verdict}")
    _log("\n  Run `uv run python benchmark_check.py` to generate the summary CSV.")


if __name__ == "__main__":
    main()
