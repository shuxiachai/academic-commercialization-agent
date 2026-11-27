"""How long a running assessment probably has left, from earlier runs' stage times.

The page showed one figure, the median of the deployment's last thirty
completed runs whatever model they ran on. On 2026-11-18 it said "about 7 min"
at the start of a run that took 24 min 40 s: the deployment had moved to a
slower model two days before, and the thirty still held the faster one's runs.

The range that replaced it (#431) was drawn from whole completed runs of the
same model, and asked only the runs whose current stage had lasted at least as
long as this one's had so far. On 2026-11-27 a run on qwen3.8-2.4t-a95b was
told 1-16 minutes, 11-16 twenty seconds later, then 7-8 and 5-6 with fourteen
minutes still to go, all "going by runs on other models" (tests/
test_eta_replay.py). Near the end of each stage the runs still in it were one
or two, so the range closed to a minute and opened again at the next stage;
and the model had three runs on record, none of which counted, because one
had failed in scoring and one was a resume: only completed whole runs were
history, and three of one model were needed.

So the range is now built stage by stage:

- A stage's time is on record when a run finished that stage, whatever
  became of the run afterwards: a run that failed or timed out lends every
  stage it got through, not the one it stopped in. A resume lends the stages
  it ran and none it took from its parent, and its seconds are read where
  they were spent (`_finished_stages`, as run.js stageSeconds shows them).
- For each stage still ahead, the newest `STAGE_SAMPLES` times of this run's
  model, fastest to slowest. A stage this model has never finished here goes
  by other models' times for it, and the answer names it
  (`other_model_stages`), so the page can say why the range is wide.
- A stage seen fewer than `MIN_SAMPLES` times is widened (`WIDEN`) and named
  (`few_sample_stages`). Measured on the 106 local benchmark runs, in 13
  batches of one model each, whole-run times: the next run lay between the
  fastest and slowest of one earlier run 0% of the time and of two 33%; half
  either way for one and a quarter for two brought that to 69% and 73%.
  Those are whole runs on a local machine, not production stages; the stage
  sum below is wider than any one run's, which is a margin of its own.
- The range is the rest of the current stage plus the later ones: the
  fastest times added up to the slowest added up. Within a stage neither end
  can rise; both fall with the clock, the low end stopping at the later
  stages' fastest. A run slower at its stage than the slowest (widened) time
  is `overdue`, and the range is what the later stages alone took.

It is what earlier runs did, not a promise. The link between the host and the
model provider stalls for minutes at a time (api/link_probe.py), which is
why the range runs to the slowest time and is not narrowed to a middle half.
"""

from __future__ import annotations

import json
import math
import threading
import time
from datetime import datetime
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
#: The checkpoints behind each stage, as run.js STAGES names them: a resume
#: that reused every one of a stage's took that stage from its parent.
STAGE_NODES = {
    "sources": ("retrieval",),
    "evidence": ("academic", "patent", "market"),
    "report": ("writer",),
    "review": ("reviewer",),
    "scoring": ("scorer",),
}
_END_STAGES = frozenset({"Done", "Error"})
#: Run directories read for stage times, newest first.
SCAN_RUNS = 200
#: The newest times of one stage on one model that make its range.
STAGE_SAMPLES = 10
MIN_SAMPLES = 3
#: How much a stage seen once or twice is widened: its fastest time divided
#: by this and its slowest multiplied by it.
WIDEN = {1: 1.5, 2: 1.25}
#: Completed whole runs kept for the figure the public pages state.
SAMPLE_RUNS = 30
MODEL_RUNS = 10
CACHE_SECONDS = 600

_lock = threading.Lock()
_cache: dict[Path, tuple[float, list[dict]]] = {}


def stage_key(stage: object) -> str | None:
    if not isinstance(stage, str):
        return None
    return next((key for marker, key in STAGES if marker in stage), None)


def _entries(raw: object) -> list[tuple[str, datetime]]:
    """The worker's (stage, start) lines, end markers kept, as runs.stage_timings parses them."""
    entries: list[tuple[str, datetime]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        stage, started = item.get("stage"), item.get("started_at")
        if not isinstance(stage, str) or not stage or not isinstance(started, str):
            continue
        try:
            started_at = datetime.fromisoformat(started)
        except ValueError:
            continue
        if started_at.tzinfo is not None:
            entries.append((stage, started_at))
    return entries[:32]


def _finished_stages(raw: object, *, completed: bool, ended_at: datetime | None,
                     recovery: object) -> dict[str, int]:
    """Seconds of each stage this run finished itself, by stage key.

    A stage is finished when the run moved on from it to another stage or to
    "Done", or, for the last one of a completed run, when the run ended. One
    followed by "Error", or by nothing in a run that did not complete, was
    cut short and is left out. So is a stage a resume reused whole or in part
    from its parent: it was not run here. Until 2026-11-19 the worker left a
    resume's stage line on the evidence stage until its first task had
    finished, so a resume that only scored filed its scoring under evidence
    (the production resume of 2026-11-18: "Phase 1" 3:33, scoring 0:00).
    Seconds under a stage the resume took whole from its parent were spent
    in the first stage it did run, which its record names, and are counted
    there, as run.js stageSeconds shows them.
    """
    entries = _entries(raw)
    seconds: dict[str, float] = {}
    cut: set[str] = set()
    for index, (stage, started_at) in enumerate(entries):
        key = None if stage in _END_STAGES else stage_key(stage)
        if key is None:
            continue
        if index + 1 < len(entries):
            following, end = entries[index + 1]
            done = following != "Error"
        else:
            end, done = ended_at, completed and ended_at is not None
        if end is None:
            cut.add(key)
            continue
        seconds[key] = seconds.get(key, 0.0) + max(0.0, (end - started_at).total_seconds())
        if not done:
            cut.add(key)

    reused_nodes = (recovery.get("reused_nodes") if isinstance(recovery, dict)
                    and recovery.get("state") == "reused" else None)
    reused_nodes = [node for node in reused_nodes if isinstance(node, str)] if isinstance(reused_nodes, list) else []
    whole = {key for key, nodes in STAGE_NODES.items() if all(node in reused_nodes for node in nodes)}
    part = {key for key, nodes in STAGE_NODES.items() if key not in whole and any(n in reused_nodes for n in nodes)}
    next_node = recovery.get("next_node") if isinstance(recovery, dict) else None
    began = next((key for key, nodes in STAGE_NODES.items() if next_node in nodes), None)
    if began is not None and began not in whole:
        # The first stage is the worker starting up, under that label then and now.
        for key, _nodes in list(STAGE_NODES.items())[1:]:
            if key in whole and key in seconds:
                seconds[began] = seconds.get(began, 0.0) + seconds.pop(key)
                if key in cut:
                    cut.add(began)
    return {key: int(value) for key, value in seconds.items() if key not in cut | whole | part}


def _record(run_dir: Path) -> dict | None:
    """What one ended run says: its model, the stages it finished, and its whole time."""
    from api import runs

    try:
        record = load_terminal_record(run_dir)
    except TerminalRecordUnreadable:
        return None
    if record is None:
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
    completed = record.state == "completed"
    return {
        "run": run_dir.name,
        "model": runs.run_model(status, record.usage),
        "stages": _finished_stages(status.get("stage_timings"), completed=completed,
                                   ended_at=record.ended_at, recovery=recovery),
        "total": record.elapsed_seconds,
        "completed": completed,
        "resumed": isinstance(recovery, dict) and bool(recovery.get("source_run_id")),
    }


def _records() -> list[dict]:
    """The newest ended runs' records, newest first, cached."""
    from api import runs

    root = runs.DEFAULT_OUTPUT_ROOT
    with _lock:
        cached = _cache.get(root)
        if cached is not None and time.monotonic() - cached[0] < CACHE_SECONDS:
            return cached[1]
    records = [record for record in map(_record, runs.run_directories()[:SCAN_RUNS]) if record is not None]
    with _lock:
        _cache[root] = (time.monotonic(), records)
    return records


def history() -> list[dict]:
    """The newest completed runs that ran every stage themselves (not resumes), with their whole times."""
    return [record for record in _records() if record["completed"] and not record["resumed"]][:SAMPLE_RUNS]


def _times(key: str, model: str | None, records: list[dict]) -> tuple[list[tuple[str, int]], bool]:
    """The newest times of one stage: this model's when it has any, else other models'."""
    own = [(r["run"], r["stages"][key]) for r in records if model and r["model"] == model and key in r["stages"]]
    if own:
        return own[:STAGE_SAMPLES], True
    others = [(r["run"], r["stages"][key]) for r in records if key in r["stages"] and not (model and r["model"] == model)]
    return others[:STAGE_SAMPLES], False


def estimate(stage: str, timings: list[dict], *, model: str | None = None) -> dict | None:
    """The rest of the current stage and every later one, fastest to slowest; None with no time on record
    for one of them."""
    order = [key for _, key in STAGES]
    current = stage_key(stage)
    # Before the worker names its first stage the whole run is ahead.
    ahead = order[order.index(current):] if current is not None else order
    in_stage = next((t["duration_seconds"] for t in reversed(timings) if t.get("active")), None)
    in_stage = in_stage if current is not None and isinstance(in_stage, int) else 0

    records = _records()
    ranges: list[tuple[float, float]] = []
    runs_asked: set[str] = set()
    others: list[str] = []
    few: list[str] = []
    for key in ahead:
        times, own = _times(key, model, records)
        if not times:
            return None
        seconds = [value for _run, value in times]
        widen = WIDEN.get(len(seconds), 1.0)
        ranges.append((min(seconds) / widen, max(seconds) * widen))
        runs_asked.update(run for run, _value in times)
        if not own:
            others.append(key)
        if len(seconds) < MIN_SAMPLES:
            few.append(key)

    (now_low, now_high), later = ranges[0], ranges[1:]
    later_low, later_high = sum(low for low, _ in later), sum(high for _, high in later)
    overdue = in_stage > now_high
    if overdue:
        low, high = later_low, later_high
    else:
        low, high = max(0.0, now_low - in_stage) + later_low, now_high - in_stage + later_high
    low_seconds, high_seconds = math.floor(low), math.ceil(high)
    return {
        # The middle of the range, for a client that shows one figure.
        "remaining_seconds": (low_seconds + high_seconds) // 2,
        "low_seconds": low_seconds,
        "high_seconds": high_seconds,
        # The runs whose times went into the range.
        "basis_runs": len(runs_asked),
        "basis": "stages",
        # Whose runs: the model's name when any stage ahead goes by its own times.
        "model": model if len(others) < len(ahead) else None,
        "same_model": bool(model) and not others,
        "overdue": overdue,
        "other_model_stages": others,
        "few_sample_stages": few,
    }


def typical_minutes() -> dict | None:
    """How long the newest completed runs here took, for a page that states it.

    The range of whole runs over the newest `MODEL_RUNS` completed runs that
    were not resumes, of any model, in minutes rounded outward, with how many
    runs it is drawn from. None with fewer than `MIN_SAMPLES`: a page then says
    no figure, rather than one from somewhere else.
    """
    totals = [sample["total"] for sample in history()[:MODEL_RUNS]]
    if len(totals) < MIN_SAMPLES:
        return None
    return {"low": max(1, min(totals) // 60), "high": -(-max(totals) // 60), "runs": len(totals)}
