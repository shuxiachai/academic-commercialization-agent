"""Batch benchmark runner — runs the 10 test topics and saves full outputs.

Usage:
    uv run python benchmark.py                    # serial (default)
    uv run python benchmark.py --concurrency 3    # 3 topics at a time
    uv run python benchmark.py --only 01,06       # specific cases by number
    uv run python benchmark.py --skip 03,04       # skip already-tested cases
    uv run python benchmark.py --repeat 3         # each topic 3x, for spread
    uv run python benchmark.py --dry-run -c 3     # exercise scheduling, no API calls

Measuring a change to scoring
-----------------------------
Use --repeat. Market sources come from live search, so two runs of the same
topic see different evidence and land on different scores; a single run
therefore cannot separate "the pipeline changed" from "the evidence changed".
benchmark_check.py reports mean and standard deviation per topic once any
topic has more than one run, and a scoring shift smaller than that spread is
not yet evidence of anything. Repetitions are interleaved across the batch
rather than run back to back, so a slow window upstream does not land entirely
on one topic and masquerade as that topic being unstable.

Each topic writes to outputs/benchmark/<num>-<slug>/ (repetitions after the
first get a __r2, __r3 suffix):
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

import benchmark_fixtures

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")

sys.path.insert(0, str(Path(__file__).parent / "src"))

# Heavy pipeline imports are deferred into run_topic() so that --dry-run and
# --help stay fast, and so each worker process imports CrewAI independently.

# Each entry: (case_number, topic_string, (expected_trl_min, expected_trl_max), industry)
# expected_trl_range is saved in meta.json so benchmark_check.py can flag calibration issues.
#
# WHERE THESE RANGES COME FROM
#
# Originally: my own estimate. That is a problem the benchmark cannot detect,
# because the same person wrote the topics, the rubric, the expected ranges and
# the pass criterion — so "26/30 within range" measured agreement with one
# opinion, not accuracy.
#
# Checking them against public milestones in Aug 2026 found three set too low
# (04, 05, 07), and in all three the system had scored at the *ceiling* of my
# range and been recorded as a pass. The yardstick was capping how right the
# output could look, and the pass hid it.
#
# Each range below now cites a milestone anyone can verify. Two caveats stated
# rather than buried:
#
#   1. The revision happened after seeing the scores. What makes these
#      different from the estimates they replace is not the order of work but
#      that they are independently checkable — an FDA approval date does not
#      move because it would be convenient. Every anchor is a dated public
#      event, not a judgement about how the field "feels".
#   2. TRL is assessed for the leading application, not for the whole field.
#      One approved product does not make every use of a technology mature,
#      and the ranges are wide enough to hold both.
#
# ANCHORS (verified 2026-08-14)
#   01 CAR-T ......... FDA approvals from 2017 (Kymriah, Yescarta); marketed
#                      therapies -> 9
#   02 mRNA cancer ... intismeran autogene (mRNA-4157) Phase 3 fully enrolled;
#                      first approvals expected late 2026-27 -> 7
#   03 solid-state ... QuantumScape Eagle pilot line inaugurated 2026-02-04 for
#                      OEM sampling; Toyota mass production targeted 2030+ -> 6
#   04 perovskite .... Oxford PV shipped commercial tandem modules to a US
#                      utility-scale project 2024-09 (~100 kW) -> 7
#   05 CRISPR ........ Casgevy FDA-approved 2023-12-08; indication extended to
#                      age 2+ on 2026-07-01. A marketed therapy -> 9
#   06 CCS ........... commercial-scale capture and storage in operation
#                      (Sleipner 1996-, Quest 2015-) -> 8
#   07 cultivated .... approved for sale Singapore 2020 (retail 2024), US
#                      2023-06, Israel 2024; production volumes tiny -> 8
#   08 quantum ....... no production drug discovered by quantum hardware;
#                      research-stage only -> 3
#   09 graphene ...... UNRESOLVED. Product claims exist but the sources are
#                      market-research summaries, not primary announcements —
#                      exactly the low-credibility tier this project's own
#                      rubric discounts. Range left at my original estimate and
#                      flagged, rather than moved on evidence I would reject if
#                      an agent cited it.
#   10 supercon. ..... no ambient-pressure room-temperature superconductor
#                      exists; the 2023 LK-99 claim was retracted -> 1
TOPICS = [
    ("01", "CAR-T cell therapy for blood cancers",                    (7, 9), "Biomed"),
    ("02", "mRNA vaccines for cancer immunotherapy",                   (6, 8), "Biomed"),
    ("03", "solid-state batteries for electric vehicles",              (5, 7), "Energy"),
    ("04", "perovskite solar cells for utility-scale power generation",(6, 8), "Clean Energy"),
    ("05", "CRISPR gene editing for genetic diseases",                 (8, 9), "Biomed"),
    ("06", "carbon capture and storage for industrial emissions",      (6, 8), "Climate"),
    ("07", "cultivated meat for food industry",                        (6, 8), "Food"),
    ("08", "quantum computing for drug discovery",                     (2, 4), "Computing"),
    ("09", "graphene-based flexible electronics",                      (3, 5), "Materials"),
    ("10", "room temperature ambient pressure superconductors",        (1, 2), "Materials"),
]

BENCHMARK_ROOT = Path(__file__).parent / "outputs" / "benchmark"
_INTER_RUN_PAUSE = 15  # seconds between topics to avoid API rate limits


def _slug(topic: str) -> str:
    return topic.lower().replace(" ", "-")[:45].rstrip("-")


def _run_dir(num: str, topic: str, rep: int = 1) -> Path:
    """Directory for one execution of one topic.

    Repetition 1 keeps the historic unsuffixed name so existing result
    directories, and anything pointing at them, keep working; only the extra
    repetitions of --repeat get a suffix.
    """
    base = BENCHMARK_ROOT / f"{num}-{_slug(topic)}"
    return base if rep <= 1 else base.with_name(f"{base.name}__r{rep}")


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


def _already_succeeded(run_dir: Path, evidence_mode: str = "live") -> bool:
    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if meta.get("status") != "success":
        return False
    # A run done over live retrieval and one done over a fixture measure
    # different things, so resuming across the two would silently blend them
    # into a single summary. Runs from before this field existed are treated
    # as live, which is what they were.
    return meta.get("evidence_mode", "live") == evidence_mode


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
    rep: int = 1,
    use_fixture: bool = False,
) -> dict:
    """Run one topic end to end. Executed in its own process when concurrent."""
    label = num if rep <= 1 else f"{num}#{rep}"
    if dry_run:
        _log(f"  [{label}] dry-run start")
        meta = _simulate_topic(num, topic, trl_range, industry)
        meta["rep"] = rep
        _log(f"  [{label}] dry-run done in {meta['elapsed_seconds']}s")
        return meta

    from academic_agent.crew import AcademicAgent
    from academic_agent.run_output import save_evidence_reports
    from academic_agent.source_pipeline import (
        SourceCollectionError,
        collect_source_collection,
    )

    run_dir = _run_dir(num, topic, rep)
    run_dir.mkdir(parents=True, exist_ok=True)

    _log(f"  [{label}] start — {topic}  [{industry}]  expect TRL {trl_range[0]}–{trl_range[1]}")

    # Skipping succeeded runs makes an interrupted batch resumable, but it also
    # means a plain re-run after changing the pipeline does nothing at all —
    # every topic is skipped and the summary silently reports the old results.
    # --force is the way to re-measure; it rewrites this run's outputs in place.
    evidence_mode = "fixture" if use_fixture else "live"
    if not force and _already_succeeded(run_dir, evidence_mode):
        _log(f"  [{label}] already succeeded — skipping (use --force to re-run)")
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
        meta["skipped"] = True
        return meta

    meta: dict = {
        "num": num,
        "rep": rep,
        "topic": topic,
        "industry": industry,
        "expected_trl_range": list(trl_range),
        "run_dir": str(run_dir),
        "status": "running",
        "rate_limit_hits": 0,
        # Recorded on every run, not only fixture ones: a result whose mode is
        # unstated cannot be compared with anything, and the summary reads
        # this rather than the flag it was invoked with.
        "evidence_mode": evidence_mode,
    }
    start = time.time()

    try:
        # Step 0: evidence — retrieved live, or replayed from a fixture so the
        # measurement isolates the agents' reasoning from what the web happened
        # to return that day.
        source_collection = None
        if use_fixture:
            source_collection = benchmark_fixtures.load(num, _slug(topic))
            if source_collection is None:
                # Not a silent fall back to live retrieval: the run would then
                # be a live measurement filed under a fixture summary, which is
                # the one confusion fixtures exist to prevent.
                raise FileNotFoundError(
                    f"no fixture for topic {num} — capture one with "
                    f"`python benchmark.py --freeze --only {num}`"
                )
            _log(f"  [{label}] evidence: fixture "
                 f"(captured {benchmark_fixtures.age_days(num):.0f}d ago)")
        else:
            source_collection = collect_source_collection(topic)

        (run_dir / "validated_sources.json").write_text(
            source_collection.model_dump_json(indent=2), encoding="utf-8"
        )
        a_count = len(source_collection.academic_sources)
        p_count = len(source_collection.patent_sources)
        m_count = len(source_collection.market_sources)
        _log(f"  [{label}] sources: {a_count} academic / {p_count} patent / {m_count} market")

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
        # Best-effort, matching pipeline_worker. These are inspection files;
        # a disk error while writing them must not turn a run that produced a
        # report into an error_crew result. Without the guard the exception
        # reaches the broad `except Exception` below and the topic is recorded
        # as a crew failure it never had.
        try:
            save_evidence_reports(
                tasks_output, run_id=run_dir.name, output_root=run_dir.parent
            )
        except Exception:  # noqa: BLE001 - inspection files must not fail a run
            _log(f"  [{label}] evidence artifacts could not be written (run unaffected)")

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
                f"  [{label}] score: overall={overall}  "
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
        _log(f"  [{label}] ✗ source collection failed: {exc}")

    except Exception:
        err_text = traceback.format_exc()
        meta["status"] = "error_crew"
        meta["error"] = err_text.splitlines()[-1]
        meta["rate_limit_hits"] += _count_rate_limit_hits(err_text)
        (run_dir / "error.log").write_text(err_text, encoding="utf-8")
        _log(f"  [{label}] ✗ crew failed: {meta['error']}")

    meta["elapsed_seconds"] = round(time.time() - start)
    (run_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    icon = "✓" if meta["status"] == "success" else "✗"
    limits = meta.get("rate_limit_hits", 0)
    suffix = f"  [{limits} rate-limit hits]" if limits else ""
    _log(f"  [{label}] {icon} done in {meta['elapsed_seconds']}s  [{meta['status']}]{suffix}")
    return meta


def _run_serial(selected: list[tuple], dry_run: bool, force: bool = False,
                use_fixture: bool = False) -> list[dict]:
    """Original behaviour: one topic at a time, with a pause between them."""
    results = []
    for i, (num, topic, trl_range, industry, rep) in enumerate(selected):
        meta = run_topic(num, topic, trl_range, industry, dry_run, force, rep, use_fixture)
        results.append(meta)
        if i < len(selected) - 1 and not meta.get("skipped") and not dry_run:
            _log(f"  → pausing {_INTER_RUN_PAUSE}s before next topic")
            time.sleep(_INTER_RUN_PAUSE)
    return results


def _run_concurrent(
    selected: list[tuple], concurrency: int, stagger: float, dry_run: bool,
    force: bool = False, use_fixture: bool = False,
) -> list[dict]:
    """Run topics in a process pool, staggering submissions.

    Submissions are spaced by `stagger` seconds because every topic opens with
    the same burst of source-collection requests; releasing them simultaneously
    is the fastest way to get throttled.
    """
    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=concurrency) as pool:
        futures = {}
        for i, (num, topic, trl_range, industry, rep) in enumerate(selected):
            if i and stagger:
                time.sleep(stagger)
            fut = pool.submit(run_topic, num, topic, trl_range, industry,
                              dry_run, force, rep, use_fixture)
            futures[fut] = (num, rep)

        for done, fut in enumerate(as_completed(futures), start=1):
            num, rep = futures[fut]
            try:
                results.append(fut.result())
            except Exception as exc:                      # worker crashed outright
                _log(f"  [{num if rep <= 1 else f'{num}#{rep}'}] ✗ worker process died: {exc}")
                results.append({
                    "num": num,
                    "rep": rep,
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
    parser.add_argument(
        "-r", "--repeat",
        type=int,
        default=1,
        metavar="N",
        help="Run each topic N times so the summary can report spread as well "
             "as a value. One run cannot tell a real scoring change from "
             "run-to-run variation — market sources come from live search, so "
             "the evidence itself differs between runs. Costs N times as much.",
    )
    parser.add_argument(
        "--fixtures",
        action="store_true",
        help="Replay frozen evidence instead of retrieving it. Holds the "
             "input constant so the spread that remains is the agents' "
             "reasoning rather than what the web returned that day — and "
             "skips the slowest, most rate-limited stage. Results are marked "
             "evidence_mode=fixture and are NOT comparable with live ones.",
    )
    parser.add_argument(
        "--freeze",
        action="store_true",
        help="Capture the current evidence for the selected topics as "
             "fixtures and exit without running the crew. Retrieves live, so "
             "it costs a retrieval pass but no LLM tokens.",
    )
    parser.add_argument(
        "--list-fixtures",
        action="store_true",
        help="Show the captured fixtures with their age and source counts.",
    )
    args = parser.parse_args()

    if args.list_fixtures:
        _log("Fixtures:")
        for line in benchmark_fixtures.describe():
            _log(line)
        return

    if args.fixtures and args.freeze:
        parser.error("--fixtures replays frozen evidence; --freeze captures it. "
                     "Pick one.")
    if args.fixtures and args.dry_run:
        parser.error("--dry-run simulates the whole run, so there is no "
                     "evidence for --fixtures to hold constant.")

    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")

    only_set = {n.strip() for n in args.only.split(",")} if args.only else None
    skip_set = {n.strip() for n in args.skip.split(",")} if args.skip else set()

    topics = [
        (num, topic, trl_range, industry)
        for num, topic, trl_range, industry in TOPICS
        if (only_set is None or num in only_set) and num not in skip_set
    ]
    if not topics:
        _log("No topics selected — check --only / --skip.")
        return

    # Repetitions are interleaved (every topic once, then every topic again)
    # rather than run back to back. A slow window upstream would otherwise land
    # on all repetitions of whichever topic was running at the time, and show up
    # as that topic being unstable — spreading them across the batch keeps the
    # spread this measures closer to real run-to-run variation.
    selected = [
        (num, topic, trl_range, industry, rep)
        for rep in range(1, args.repeat + 1)
        for num, topic, trl_range, industry in topics
    ]

    concurrency = min(args.concurrency, len(selected))
    max_rpm = os.getenv("MAX_RPM", "6")

    BENCHMARK_ROOT.mkdir(parents=True, exist_ok=True)
    _log(f"Benchmark root : {BENCHMARK_ROOT}")
    _log(f"Topics to run  : {len(topics)}"
         + (f" x {args.repeat} repetitions = {len(selected)} runs" if args.repeat > 1 else ""))
    _log(f"Concurrency    : {concurrency}" + ("  (serial)" if concurrency == 1 else ""))
    if concurrency > 1:
        _log(f"Aggregate rate : ~{concurrency} x {max_rpm} RPM to the LLM, plus source-API bursts")
        _log(f"Stagger        : {args.stagger}s between starts")
    if args.dry_run:
        _log("Mode           : DRY RUN — simulated work, no API calls")
    if args.force:
        _log("Mode           : FORCE — re-running topics that already succeeded")
    if args.fixtures:
        # Stated up front and again in the summary. A fixture run and a live
        # run produce the same-looking table, and only one of them is a
        # measurement of the whole system.
        ages = [benchmark_fixtures.age_days(num) for num, *_ in topics]
        known = [a for a in ages if a is not None]
        oldest = f"{max(known):.0f}d" if known else "unknown"
        _log("Mode           : FIXTURES — frozen evidence, reasoning only")
        _log(f"Fixture age    : oldest {oldest}"
             + ("  ⚠ STALE" if known and max(known) > benchmark_fixtures.STALE_AFTER_DAYS
                else ""))
    _log()

    if args.freeze:
        from academic_agent.source_pipeline import collect_source_collection

        _log("Mode           : FREEZE — capturing evidence, not running the crew\n")
        for num, topic, _trl, _industry in topics:
            _log(f"  [{num}] retrieving — {topic}")
            collection = collect_source_collection(topic)
            entry = benchmark_fixtures.freeze(
                num, _slug(topic), topic, collection.model_dump_json(indent=2)
            )
            counts = entry["counts"]
            _log(f"  [{num}] frozen: {counts['academic']}A / {counts['patent']}P "
                 f"/ {counts['market']}M  -> {entry['file']}")
        _log(f"\nFixtures written to {benchmark_fixtures.FIXTURE_ROOT}")
        _log("Replay them with:  uv run python benchmark.py --fixtures")
        return

    wall_start = time.time()
    if concurrency == 1:
        results = _run_serial(selected, args.dry_run, args.force, args.fixtures)
    else:
        results = _run_concurrent(selected, concurrency, args.stagger,
                                  args.dry_run, args.force, args.fixtures)
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
    if args.fixtures:
        _log("  Evidence  : FIXTURE (frozen) — measures reasoning, not retrieval.")
        _log("              Not comparable with a live-retrieval baseline.")
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
