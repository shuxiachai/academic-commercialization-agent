#!/usr/bin/env python
"""What actually happens to real runs, read off the outputs directory.

The benchmark answers "is the scoring calibrated" against ten curated English
topics. It cannot answer "what breaks when someone uses this", because real
input does not look like benchmark input: the runs on disk include a Chinese
topic with embedded parameters, the string "test", and an empty topic. The
benchmark passed 30/30 while a quarter of real runs were failing.

Nobody had looked at this data. It costs nothing, it is already on disk, and
it is the only record of the system meeting inputs nobody designed for.

Three things this deliberately does that a naive summary would not:

**It reports the specific cause, not the guardrail's prefix.** Every scoring
failure begins "Return exactly one valid JSON object ... with no Markdown
fences or prose", which is a generic retry hint. Grouping on that puts three
unrelated faults in one bucket. The real cause is the validation error
appended after it, and reading the wrong one sends you to fix formatting when
the actual problem was a schema minimum no output could satisfy.

**It segments by time and names the last occurrence.** A failure mode fixed
last week still sits in the directory forever and keeps inflating the overall
rate. Reading that rate as current is a mistake I made with this exact data:
the dominant August failure had been fixed ten hours after the last run that
hit it, and the fix was already shipped while the number still said 33%.

**It never turns missing evidence into a pass.** Legacy runs may have a report
or an error artifact but no status file; newer runs can have an unreadable or
non-terminal status. All matching directories remain in the denominator audit,
with completed, failed, timeout, cancelled and unknown reported separately.
Unknown runs are excluded from the resolved success rate and named by reason.
Optional reliability checks also report ``not recorded`` rather than being
silently presented as successful.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

OUTPUT_ROOT = Path(__file__).parent / "outputs"

#: Run directories are <UTC timestamp>-<hex>; the benchmark writes elsewhere.
_RUN_DIR = re.compile(r"^(\d{8})T(\d{6})Z-[0-9a-f]+$")

#: "1 validation error for CommercializationScore\npatent_source_ids\n  List
#: should have at least 1 item ..." -> the model, the field and the rule.
_PYDANTIC = re.compile(
    r"validation error[s]? for (\w+)\s*\n\s*([\w.]+)\s*\n\s*([^\[\n]+)", re.MULTILINE)

_TIMEOUT_MARKERS = ("timed out", "timeout", "deadline exceeded")


def _read_failure_artifact(directory: Path) -> str:
    """Best local diagnostic for a run whose status lacks an error.

    This is an operator-only report, so it may inspect the unredacted artifact.
    ``error.log`` is authoritative. Arbitrary worker output is deliberately
    not treated as failure evidence: every successful legacy run can have a
    process log too.
    """
    try:
        error = (directory / "error.log").read_text(
            encoding="utf-8", errors="replace"
        ).strip()
        if error:
            return error
    except OSError:
        pass
    return ""


def _outcome(
    directory: Path,
    status: dict,
    *,
    status_present: bool,
    status_readable: bool,
) -> tuple[str, str, str]:
    """Return outcome, evidence basis, and raw failure reason.

    Old runs predate ``status.json``. A delivered report or ``error.log`` is a
    strong terminal artifact for those directories, so excluding them biases
    the history toward newer releases. The inverse is not safe: a directory
    with neither artifact is not a success merely because no error was found.

    A present but unreadable status stays ``unknown`` even if a report exists.
    The API makes the same conservative choice because a corrupt source-of-
    truth file can reflect a partial write or disk fault. Silence is therefore
    never converted into a pass.
    """
    if (directory / "cancelled.marker").exists():
        return "cancelled", "cancelled.marker", ""
    if status_present and not status_readable:
        return "unknown", "unreadable status.json", ""

    status_error = str(status.get("error") or "").strip()
    artifact_error = _read_failure_artifact(directory)
    failure = status_error or artifact_error
    if failure:
        lowered = failure.lower()
        outcome = (
            "timeout" if any(marker in lowered for marker in _TIMEOUT_MARKERS)
            else "failed"
        )
        basis = "status.json error" if status_error else "error.log"
        return outcome, basis, failure
    if status.get("done") is True:
        return "completed", "status.json done=true", ""
    if not status_present and (directory / "commercialization_report.md").exists():
        return "completed", "legacy report artifact", ""
    if status_present:
        return "unknown", "non-terminal status.json", ""
    return "unknown", "no terminal artifact", ""


def _check_state(status: dict, field: str, state_field: str = "status") -> str:
    """Quality-screen state without converting missing telemetry to success."""
    value = status.get(field)
    if isinstance(value, dict):
        state = value.get(state_field)
        if isinstance(state, str) and state.strip():
            return state.strip()
    return "not recorded"



def _specific_cause(error: str) -> str:
    """The narrowest description of why this run failed.

    Falls back to the first line only when nothing more specific parses —
    stated rather than silent, because "unparsed" and "generic failure" are
    different findings and collapsing them hides which one you have.
    """
    if not error:
        return "(no error recorded)"
    match = _PYDANTIC.search(error)
    if match:
        model, field, rule = match.groups()
        return f"{model}.{field}: {rule.strip()}"
    for marker in ("Last error:", "Validation error:"):
        if marker in error:
            error = error.split(marker, 1)[1].strip()
            break
    # First sentence only. The tail carries run-specific detail — which hosts
    # were rejected, which source id was missing — and grouping on the whole
    # string splits one fault into as many buckets as it had variations.
    head = re.split(r"[.;:]\s", " ".join(error.split()), maxsplit=1)[0]
    return head[:90]


def _classify_topic(topic: str | None) -> str:
    """What the user typed — or, distinctly, that we never recorded it.

    Conflating the two sends someone to fix input validation for a case that
    never happened. Every "empty" run in this directory turned out to be a
    status.json written before the topic field existed, not a blank
    submission.
    """
    if topic is None:
        return "not recorded"
    if not topic.strip():
        return "empty submission"
    if len(topic.strip()) < 8:
        return "trivial (<8 chars)"
    cjk = sum(1 for c in topic if "一" <= c <= "鿿")
    if cjk / max(len(topic), 1) > 0.2:
        return "CJK"
    return "latin"


def collect(root: Path) -> list[dict]:
    runs = []
    for directory in sorted(root.iterdir() if root.exists() else []):
        if not directory.is_dir() or not _RUN_DIR.match(directory.name):
            continue
        status_path = directory / "status.json"
        status_present = status_path.exists()
        status_readable = True
        try:
            status = (
                json.loads(status_path.read_text(encoding="utf-8"))
                if status_present else {}
            )
        except (OSError, ValueError):
            status = {}
            status_readable = False
        stamp = _RUN_DIR.match(directory.name).group(1)
        outcome, outcome_basis, error = _outcome(
            directory,
            status,
            status_present=status_present,
            status_readable=status_readable,
        )
        runs.append({
            "date": f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}",
            "run_id": directory.name,
            # None means the field was absent, "" means it was submitted
            # blank. _classify_topic keeps them apart.
            "topic": status.get("topic"),
            "outcome": outcome,
            "outcome_basis": outcome_basis,
            # Kept for callers of the old shape. Timeout is a system failure;
            # user cancellation and an unclassifiable directory are not.
            "failed": outcome in {"failed", "timeout"},
            "cause": _specific_cause(error) if error else "",
            "usage": status.get("usage"),
            "checks": {
                "claim grounding": _check_state(status, "claim_grounding"),
                "checkpointing": _check_state(status, "checkpointing", "state"),
                "quality review": _check_state(status, "quality_review"),
                "recovery": _check_state(status, "recovery"),
            },
        })
    return runs


def _print_outcomes(runs: list[dict]) -> None:
    by_week: dict[str, Counter] = defaultdict(Counter)
    for run in runs:
        year, month, day = (int(x) for x in run["date"].split("-"))
        week = datetime(year, month, day).strftime("%Y-W%V")
        by_week[week][run["outcome"]] += 1

    print(
        f"\n{'week':<10}{'done':>6}{'failed':>8}{'timeout':>9}"
        f"{'cancel':>8}{'unknown':>9}{'success':>9}"
    )
    print("-" * 59)
    for week in sorted(by_week):
        counts = by_week[week]
        resolved = counts["completed"] + counts["failed"] + counts["timeout"]
        rate = f"{counts['completed'] / resolved:.0%}" if resolved else "n/a"
        print(
            f"{week:<10}{counts['completed']:>6}{counts['failed']:>8}"
            f"{counts['timeout']:>9}{counts['cancelled']:>8}"
            f"{counts['unknown']:>9}{rate:>9}"
        )
    print(
        "Success excludes user cancellations and unknown directories; unknown "
        "is never counted as a pass."
    )

    bases = Counter(
        run["outcome_basis"] for run in runs if run["outcome"] == "unknown"
    )
    if bases:
        print("\nUnknown outcome reasons")
        print("-" * 36)
        for basis, count in bases.most_common():
            print(f"  {count:>3}x  {basis}")


def _print_causes(runs: list[dict]) -> None:
    failures = [r for r in runs if r["outcome"] in {"failed", "timeout"}]
    if not failures:
        print("\nNo failed or timed-out runs recorded.")
        return

    causes: dict[str, list[str]] = defaultdict(list)
    for run in failures:
        causes[run["cause"]].append(run["date"])

    print(f"\nFailure causes ({len(failures)} failed or timed-out runs)")
    print("-" * 78)
    for cause, dates in sorted(causes.items(), key=lambda kv: -len(kv[1])):
        last = max(dates)
        # The question a raw count cannot answer. A mode last seen before the
        # newest successful run may already be fixed; one seen today is live.
        since = sum(1 for r in runs if r["date"] > last)
        note = f"last {last}, {since} run(s) since" if since else f"last {last} — MOST RECENT"
        print(f"  {len(dates):>3}x  {cause[:60]}")
        print(f"       {note}")


def _print_inputs(runs: list[dict]) -> None:
    """What people actually typed, against what the benchmark tests."""
    kinds = Counter(_classify_topic(r["topic"]) for r in runs)
    unrecorded = kinds.get("not recorded", 0)
    print(
        f"\n{'input shape':<22}{'runs':>6}{'done':>7}{'failed':>8}"
        f"{'unknown':>9}"
    )
    print("-" * 52)
    for kind, count in kinds.most_common():
        matching = [r for r in runs if _classify_topic(r["topic"]) == kind]
        completed = sum(r["outcome"] == "completed" for r in matching)
        failed = sum(r["outcome"] in {"failed", "timeout"} for r in matching)
        unknown = sum(r["outcome"] == "unknown" for r in matching)
        print(f"{kind:<22}{count:>6}{completed:>7}{failed:>8}{unknown:>9}")

    try:
        from benchmark import TOPICS
        bench = Counter(_classify_topic(t) for _n, t, _r, _i in TOPICS)
        print(f"\nBenchmark covers: {dict(bench)}")
        missing = set(kinds) - set(bench) - {"not recorded"}
        if missing:
            print(f"Real input shapes the benchmark never exercises: "
                  f"{', '.join(sorted(missing))}")
    except ImportError:
        pass

    if unrecorded:
        print(f"\n{unrecorded} run(s) have no recorded topic — absent, not "
              f"blank. They remain visible as 'not recorded' rather than "
              f"being counted as empty input.")


def _print_check_coverage(runs: list[dict]) -> None:
    """Show whether optional reliability checks ran, not just what they found."""
    print("\nReliability-check coverage (all runs; absence is not a pass)")
    print("-" * 68)
    for check in ("claim grounding", "checkpointing", "quality review", "recovery"):
        states = Counter(run["checks"][check] for run in runs)
        rendered = ", ".join(
            f"{state}={count}" for state, count in sorted(states.items())
        )
        print(f"  {check:<18} {rendered}")


def _print_cost(runs: list[dict]) -> None:
    priced = [r["usage"] for r in runs
              if isinstance(r.get("usage"), dict) and r["usage"].get("cost_usd") is not None]
    if not priced:
        return
    total = sum(u["cost_usd"] for u in priced)
    missing = len(runs) - len(priced)
    print(f"\nRecorded spend: ${total:.4f} over {len(priced)} run(s) "
          f"({missing} without recorded cost: legacy runs or failures before "
          f"usage accounting began)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", default=str(OUTPUT_ROOT),
                        help="Directory holding run folders (default: outputs/)")
    parser.add_argument("--since", default="",
                        help="Only runs on or after this date, YYYY-MM-DD. Use "
                             "it to ask whether a fix held, rather than reading "
                             "a lifetime average as the current rate.")
    args = parser.parse_args()

    runs = collect(Path(args.root))
    if args.since:
        runs = [r for r in runs if r["date"] >= args.since]

    if not runs:
        print("No runs found. This reads real runs, not benchmark runs — "
              "those live in outputs/benchmark and are covered by "
              "benchmark_check.py.")
        return

    print(f"{len(runs)} run(s), {runs[0]['date']} to {runs[-1]['date']}")
    _print_outcomes(runs)
    _print_causes(runs)
    _print_inputs(runs)
    _print_check_coverage(runs)
    _print_cost(runs)

if __name__ == "__main__":
    main()
