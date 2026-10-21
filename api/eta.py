"""How long a running assessment probably has left, from recent finished runs.

A run takes ten to twenty minutes, and the page showed only how long it had
been going. This estimates the rest from the deployment's own history: the
median duration of each stage over recent completed runs when enough of them
recorded stage times, otherwise the median total. It is a typical figure, not
a promise; `remaining_seconds` goes negative once a run is slower than usual,
and the page says so rather than counting down past zero.
"""

from __future__ import annotations

import json
import statistics
import threading
import time
from pathlib import Path

from academic_agent.run_terminal import TerminalRecordUnreadable, load_terminal_record

# The worker's stage labels, matched by substring as the browser matches them.
STAGES = (
    ("Source Collection", "sources"),
    ("Phase 1", "evidence"),
    ("Agent 4", "report"),
    ("Agent 5", "review"),
    ("Agent 6", "scoring"),
)
SAMPLE_RUNS = 30
MIN_SAMPLES = 3
CACHE_SECONDS = 600

_lock = threading.Lock()
_cache: dict[Path, tuple[float, dict]] = {}


def stage_key(stage: object) -> str | None:
    if not isinstance(stage, str):
        return None
    return next((key for marker, key in STAGES if marker in stage), None)


def _sample(run_dir: Path) -> tuple[int, dict[str, int]] | None:
    from api import runs

    try:
        record = load_terminal_record(run_dir)
    except TerminalRecordUnreadable:
        return None
    if record is None or record.state != "completed":
        return None
    try:
        status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        status = {}
    per_stage: dict[str, int] = {}
    raw = status.get("stage_timings") if isinstance(status, dict) else None
    for timing in runs.stage_timings(raw, running=False, ended_at=record.ended_at):
        key = stage_key(timing["stage"])
        if key is not None and timing["duration_seconds"] is not None:
            per_stage[key] = per_stage.get(key, 0) + timing["duration_seconds"]
    return record.elapsed_seconds, per_stage


def typical_durations() -> dict:
    """Median total and per-stage seconds over recent completed runs, cached."""
    from api import runs

    root = runs.DEFAULT_OUTPUT_ROOT
    with _lock:
        cached = _cache.get(root)
        if cached is not None and time.monotonic() - cached[0] < CACHE_SECONDS:
            return cached[1]
    totals: list[int] = []
    stages: dict[str, list[int]] = {key: [] for _, key in STAGES}
    for run_dir in runs.run_directories():
        if len(totals) >= SAMPLE_RUNS:
            break
        sample = _sample(run_dir)
        if sample is None:
            continue
        totals.append(sample[0])
        for key, seconds in sample[1].items():
            stages[key].append(seconds)
    typical = {
        "runs": len(totals),
        "total": int(statistics.median(totals)) if len(totals) >= MIN_SAMPLES else None,
        "stages": {
            key: int(statistics.median(values))
            for key, values in stages.items() if len(values) >= MIN_SAMPLES
        },
    }
    with _lock:
        _cache[root] = (time.monotonic(), typical)
    return typical


def estimate(stage: str, elapsed_seconds: int | None, timings: list[dict]) -> dict | None:
    """Seconds probably left for a running run, or None without enough history."""
    typical = typical_durations()
    order = [key for _, key in STAGES]
    current = stage_key(stage)
    in_stage = next((t["duration_seconds"] for t in reversed(timings) if t.get("active")), None)
    if current is not None and in_stage is not None and len(typical["stages"]) == len(order):
        later = order[order.index(current) + 1:]
        remaining = typical["stages"][current] - in_stage + sum(typical["stages"][k] for k in later)
        return {"remaining_seconds": remaining, "basis_runs": typical["runs"], "basis": "stages"}
    if typical["total"] is not None and elapsed_seconds is not None:
        return {"remaining_seconds": typical["total"] - elapsed_seconds,
                "basis_runs": typical["runs"], "basis": "total"}
    return None
