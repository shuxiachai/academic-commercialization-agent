"""How long a running assessment probably has left, from recent finished runs.

The page showed one figure, the median of the deployment's last thirty
completed runs whatever model they ran on. On 2026-11-18 it said "about 7 min"
at the start of a run that took 24 min 40 s: the deployment had moved to a
slower model two days before, and the thirty still held the faster one's
runs. A resumed run that only had scoring left then counted as a completed
run of 3 min 48 s, with those seconds filed under the evidence stage.

So the estimate is now a range, drawn from runs of the same model:

- A sample is a completed run that ran every stage itself. A resumed run is
  not one: it ran only what its parent had not finished.
- The pool is the newest `MODEL_RUNS` samples on the running run's model.
  With fewer than `MIN_SAMPLES` of those, it is the newest `MODEL_RUNS`
  samples of any model, and the answer says so (`same_model` false): the
  reader is told the figure comes from other models, not given it as if it
  were this one's.
- For each run in the pool: what it took from this point to its end, that is
  the rest of the current stage plus every later stage. The range is the
  fastest and the slowest of those. Only runs whose current stage lasted at
  least as long as this one's already has are asked: a run that had left the
  stage by now says nothing about how much of it is left. When none lasted
  this long the run is `overdue`, slower at this stage than every run in the
  pool, and the range is what the later stages alone took.

It is what recent runs did, not a promise. The link between the host and the
model provider stalls for minutes at a time (api/link_probe.py), which is
why the range is wide and why it is not narrowed to a middle half: the slow
runs are the ones a waiting reader needs to know about.
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
#: Completed runs kept, newest first, across every model.
SAMPLE_RUNS = 30
#: At most this many runs make one range.
MODEL_RUNS = 10
MIN_SAMPLES = 3
CACHE_SECONDS = 600

_lock = threading.Lock()
_cache: dict[Path, tuple[float, list[dict]]] = {}


def stage_key(stage: object) -> str | None:
    if not isinstance(stage, str):
        return None
    return next((key for marker, key in STAGES if marker in stage), None)


def _sample(run_dir: Path) -> dict | None:
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
    if not isinstance(status, dict):
        status = {}
    # The terminal record's copy is the one the run page shows; the live file
    # is the fallback for a record written without it.
    recovery = record.recovery if record.recovery is not None else status.get("recovery")
    if isinstance(recovery, dict) and recovery.get("source_run_id"):
        return None
    per_stage: dict[str, int] = {}
    for timing in runs.stage_timings(status.get("stage_timings"), running=False, ended_at=record.ended_at):
        key = stage_key(timing["stage"])
        if key is not None and timing["duration_seconds"] is not None:
            per_stage[key] = per_stage.get(key, 0) + timing["duration_seconds"]
    return {
        "total": record.elapsed_seconds,
        "stages": per_stage,
        "model": runs.run_model(status, record.usage),
    }


def history() -> list[dict]:
    """The newest completed, unresumed runs with their stage times and model, cached."""
    from api import runs

    root = runs.DEFAULT_OUTPUT_ROOT
    with _lock:
        cached = _cache.get(root)
        if cached is not None and time.monotonic() - cached[0] < CACHE_SECONDS:
            return cached[1]
    samples: list[dict] = []
    for run_dir in runs.run_directories():
        if len(samples) >= SAMPLE_RUNS:
            break
        sample = _sample(run_dir)
        if sample is not None:
            samples.append(sample)
    with _lock:
        _cache[root] = (time.monotonic(), samples)
    return samples


def _pool(model: str | None) -> tuple[list[dict], bool]:
    samples = history()
    same = [sample for sample in samples if model and sample["model"] == model][:MODEL_RUNS]
    if len(same) >= MIN_SAMPLES:
        return same, True
    return samples[:MODEL_RUNS], False


def _answer(values: list[int], *, pool: list[dict], basis: str, model: str | None,
            same_model: bool, overdue: bool) -> dict:
    return {
        # The middle of the range, for a client that shows one figure.
        "remaining_seconds": int(statistics.median(values)),
        "low_seconds": min(values),
        "high_seconds": max(values),
        "basis_runs": len(pool),
        "basis": basis,
        # Whose runs the range is drawn from: the model's name, or None for
        # runs of other models.
        "model": model if same_model else None,
        "same_model": same_model,
        "overdue": overdue,
    }


def estimate(stage: str, elapsed_seconds: int | None, timings: list[dict], *,
             model: str | None = None) -> dict | None:
    """What recent runs took from this point to their end, or None without enough of them."""
    pool, same_model = _pool(model)
    if len(pool) < MIN_SAMPLES:
        return None
    order = [key for _, key in STAGES]
    current = stage_key(stage)
    in_stage = next((t["duration_seconds"] for t in reversed(timings) if t.get("active")), None)
    staged = [sample for sample in pool if len(sample["stages"]) == len(order)]
    if current is not None and in_stage is not None and len(staged) >= MIN_SAMPLES:
        later = order[order.index(current) + 1:]
        rest = [sum(sample["stages"][key] for key in later) for sample in staged]
        still_in = [
            sample["stages"][current] - in_stage + after
            for sample, after in zip(staged, rest, strict=True)
            if sample["stages"][current] >= in_stage
        ]
        return _answer(still_in or rest, pool=staged, basis="stages", model=model,
                       same_model=same_model, overdue=not still_in)
    if elapsed_seconds is None:
        return None
    left = [sample["total"] - elapsed_seconds for sample in pool if sample["total"] >= elapsed_seconds]
    return _answer(left or [0], pool=pool, basis="total", model=model,
                   same_model=same_model, overdue=not left)


def typical_minutes() -> dict | None:
    """How long the newest completed runs here took, for a page that states it.

    The range of whole runs over the newest `MODEL_RUNS` samples of any
    model, in minutes rounded outward, with how many runs it is drawn from.
    None with fewer than `MIN_SAMPLES`: a page then says no figure, rather
    than one from somewhere else.
    """
    totals = [sample["total"] for sample in history()[:MODEL_RUNS]]
    if len(totals) < MIN_SAMPLES:
        return None
    return {"low": max(1, min(totals) // 60), "high": -(-max(totals) // 60), "runs": len(totals)}
