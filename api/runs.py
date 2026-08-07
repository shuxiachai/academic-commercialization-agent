"""Run lifecycle management for the HTTP API.

Owns the registry of live worker processes, enforces the concurrency cap,
and derives run state from the artifacts on disk.

State lives in two places by design:
  • status.json — written by the worker, the source of truth for stage/progress
  • terminal markers (error.log, cancelled.marker) — written by this module for
    events the worker cannot know about (cancellation, timeout)

Keeping the worker's contract unchanged means the Gradio UI and this API can
observe the same run without either knowing about the other.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path

from academic_agent.run_output import DEFAULT_OUTPUT_ROOT, create_run_id

# A run is killed after this long. Matches the Gradio path's limit so both
# entry points behave identically.
TIMEOUT_SECONDS = 1800

# Concurrent workers. The real ceiling is upstream API rate limits, not local
# CPU — each run issues dozens of requests to OpenAlex/Serper/the LLM.
MAX_CONCURRENT = int(os.getenv("API_MAX_CONCURRENT", "2"))

_CANCEL_MARKER = "cancelled.marker"

_ARTIFACTS = {
    "report":  "commercialization_report.md",
    "scores":  "commercialization_scores.json",
    "sources": "validated_sources.json",
    "notes":   "reviewer_notes.md",
    "steps":   "steps.jsonl",
}


class _PendingProcess:
    """Stands in for a subprocess that is being launched.

    Occupies a concurrency slot from the moment it is reserved until the real
    Popen replaces it, so a burst of submissions cannot all pass the cap check
    while their processes are still starting. Reports itself as alive for that
    reason; terminate() is a no-op because there is nothing to signal yet.
    """

    def poll(self) -> None:
        return None

    def terminate(self) -> None:
        return None

    def kill(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        return 0


@dataclass
class _Handle:
    """A live worker process tracked by the API."""

    run_id: str
    topic: str
    proc: subprocess.Popen
    started: float = field(default_factory=time.monotonic)
    log_file: object = None

    @property
    def elapsed(self) -> int:
        return int(time.monotonic() - self.started)

    def alive(self) -> bool:
        return self.proc.poll() is None

    def terminate(self) -> None:
        """Terminate, then kill if it ignores SIGTERM."""
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.log_file is not None:
            try:
                self.log_file.close()
            except OSError:
                pass


class ConcurrencyLimitReached(Exception):
    """Raised when the active-run cap would be exceeded."""


class RunNotFound(Exception):
    """Raised for an unknown run_id."""


_registry: dict[str, _Handle] = {}

# Guards _registry. FastAPI runs `def` endpoints in a thread pool, so two
# submissions genuinely execute in parallel — the cap was checked and written
# without any lock, and the gap between them spans a mkdir and a Popen. Six
# concurrent submissions against a cap of 2 all started. Each run is a
# six-agent LLM pipeline, so exceeding the cap costs real money and pushes
# concurrent retrieval into upstream rate limits.
#
# Reentrant because start_run calls active_count while holding it.
_registry_lock = threading.RLock()


def active_count() -> int:
    """Number of runs still executing. Reaps finished handles as a side effect."""
    with _registry_lock:
        for run_id in [rid for rid, h in _registry.items() if not h.alive()]:
            h = _registry.pop(run_id, None)
            if h and h.log_file is not None:
                try:
                    h.log_file.close()
                except OSError:
                    pass
        return len(_registry)


def run_dir_for(run_id: str) -> Path:
    return DEFAULT_OUTPUT_ROOT / run_id


def _is_valid_run_id(run_id: str) -> bool:
    """Reject anything that could escape the outputs directory."""
    return (
        bool(run_id)
        and "/" not in run_id
        and "\\" not in run_id
        and ".." not in run_id
        and run_id == Path(run_id).name
    )


def start_run(
    topic: str,
    language: str | None = None,
    weight_profile: str | None = None,
    paper_json_path: str | None = None,
) -> tuple[str, Path]:
    """Launch a worker subprocess. Returns (run_id, run_dir)."""
    # Claim a slot and publish the run_id in one atomic step. Checking the cap
    # and registering the handle separately let parallel submissions all pass
    # the check before any of them registered.
    #
    # The slot is reserved with a placeholder handle so the subprocess launch —
    # the slow part — happens outside the lock. A reservation counts towards
    # the cap, so a burst cannot slip through while processes are starting.
    with _registry_lock:
        if active_count() >= MAX_CONCURRENT:
            raise ConcurrencyLimitReached(
                f"{active_count()} of {MAX_CONCURRENT} concurrent runs in use"
            )
        run_id = create_run_id()
        _registry[run_id] = _Handle(
            run_id=run_id, topic=topic, proc=_PendingProcess(), log_file=None
        )

    run_dir = run_dir_for(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, "-m", "academic_agent.pipeline_worker", run_id, topic.strip()]
    if language:
        cmd += ["--language", language]
    if weight_profile:
        cmd += ["--weight-profile", weight_profile]
    if paper_json_path and Path(paper_json_path).exists():
        cmd += ["--paper-json", paper_json_path]

    # Any failure from here on must release the reserved slot, or the cap
    # leaks permanently: a placeholder counts as alive and nothing else
    # removes it.
    try:
        log_file = open(run_dir / "process.log", "w", encoding="utf-8")
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log_file)
        except BaseException:
            log_file.close()
            raise
    except BaseException:
        with _registry_lock:
            _registry.pop(run_id, None)
        raise

    with _registry_lock:
        _registry[run_id] = _Handle(
            run_id=run_id, topic=topic, proc=proc, log_file=log_file
        )
    return run_id, run_dir


def cancel_run(run_id: str) -> None:
    """Terminate a live run and mark it cancelled."""
    # Removed under the lock so two concurrent cancels cannot both decide the
    # run is theirs to terminate.
    with _registry_lock:
        handle = _registry.get(run_id)
        if handle is None or not handle.alive():
            raise RunNotFound(f"No live run with id {run_id}")
        _registry.pop(run_id, None)
    handle.terminate()
    (run_dir_for(run_id) / _CANCEL_MARKER).write_text(
        datetime.now(UTC).isoformat(), encoding="utf-8"
    )


def reap_timeouts() -> list[str]:
    """Kill runs past the deadline. Returns the run_ids that were killed."""
    killed: list[str] = []
    # Claim each expired run under the lock before terminating it, so a
    # concurrent cancel_run cannot terminate the same handle twice.
    with _registry_lock:
        expired = [
            (rid, h) for rid, h in _registry.items()
            if h.alive() and h.elapsed > TIMEOUT_SECONDS
        ]
        for run_id, _handle in expired:
            _registry.pop(run_id, None)

    for run_id, handle in expired:
        handle.terminate()
        (run_dir_for(run_id) / "error.log").write_text(
            f"Analysis timed out after {TIMEOUT_SECONDS // 60} minutes.",
            encoding="utf-8",
        )
        killed.append(run_id)
    return killed


def shutdown_all() -> None:
    """Terminate every live run. Called on application shutdown."""
    with _registry_lock:
        handles = list(_registry.values())
        _registry.clear()
    for handle in handles:
        handle.terminate()


def _read_status(run_dir: Path) -> dict:
    try:
        return json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _failure_reason(run_dir: Path) -> str:
    """Best available explanation for a run that did not complete."""
    try:
        msg = (run_dir / "error.log").read_text(encoding="utf-8", errors="replace").strip()
        if msg:
            return msg[:800]
    except OSError:
        pass
    try:
        log = (run_dir / "process.log").read_text(encoding="utf-8", errors="replace").strip()
        if log:
            return "Worker stderr:\n" + log[-800:]
    except OSError:
        pass
    return "The worker exited without completing. Check API keys and network, then retry."


def artifact_names() -> list[str]:
    """Every artifact name the API can serve, whether or not a given run has it."""
    return sorted(_ARTIFACTS)


def available_artifacts(run_dir: Path) -> list[str]:
    return [name for name, fname in _ARTIFACTS.items() if (run_dir / fname).exists()]


def artifact_path(run_id: str, name: str) -> Path | None:
    """Resolve an artifact name to a path, or None if unknown/missing.

    Validates run_id itself rather than trusting the caller. Both current
    callers happen to call get_state() first, which rejects a traversing id —
    so this function was safe by call order rather than by construction, and a
    new endpoint that resolved an artifact directly would have reintroduced the
    traversal. The filename is already confined by the _ARTIFACTS allowlist.
    """
    if not _is_valid_run_id(run_id):
        return None
    fname = _ARTIFACTS.get(name)
    if fname is None:
        return None
    path = run_dir_for(run_id) / fname
    return path if path.exists() else None


def get_state(run_id: str) -> dict:
    """Derive the full state of a run from disk plus the live registry."""
    if not _is_valid_run_id(run_id):
        raise RunNotFound(f"Invalid run id: {run_id!r}")

    run_dir = run_dir_for(run_id)
    if not run_dir.is_dir():
        raise RunNotFound(f"No run with id {run_id}")

    status = _read_status(run_dir)
    handle = _registry.get(run_id)

    if handle is not None and handle.alive():
        state = "running"
        error = None
        elapsed = handle.elapsed
    else:
        elapsed = None
        if (run_dir / _CANCEL_MARKER).exists():
            state, error = "cancelled", "Cancelled by request."
        elif status.get("error"):
            state, error = "failed", str(status["error"])
        elif status.get("done"):
            state, error = "completed", None
        else:
            reason = _failure_reason(run_dir)
            state = "timeout" if "timed out" in reason.lower() else "failed"
            error = reason

    return {
        "run_id": run_id,
        "state": state,
        "stage": status.get("stage", ""),
        "topic": status.get("topic") or (handle.topic if handle else ""),
        "output_language": status.get("output_language") or "English",
        "error": error,
        "elapsed_seconds": elapsed,
        "source_counts": status.get("source_counts"),
        "artifacts": available_artifacts(run_dir),
    }


def _started_at(run_id: str) -> str:
    try:
        stamp = run_id.split("-")[0]
        dt = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        return dt.isoformat()
    except ValueError:
        return ""


def _duration(run_dir: Path) -> str:
    try:
        stamp = run_dir.name.split("-")[0]
        start = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        status_path = run_dir / "status.json"
        if not status_path.exists():
            return "—"
        end = datetime.fromtimestamp(os.path.getmtime(status_path), tz=UTC)
        secs = int((end - start).total_seconds())
        if secs < 0:
            return "—"
        return f"{secs}s" if secs < 60 else f"{secs // 60}m {secs % 60:02d}s"
    except (ValueError, OSError):
        return "—"


def list_runs(limit: int = 50) -> tuple[list[dict], int]:
    """Return (summaries, total) for finished and running runs, newest first."""
    if not DEFAULT_OUTPUT_ROOT.is_dir():
        return [], 0

    dirs = sorted(
        (d for d in DEFAULT_OUTPUT_ROOT.iterdir() if d.is_dir() and d.name != "benchmark"),
        key=lambda d: d.name,
        reverse=True,
    )
    summaries = []
    for d in dirs[:limit]:
        try:
            state = get_state(d.name)["state"]
        except RunNotFound:
            continue
        summaries.append({
            "run_id": d.name,
            "state": state,
            "topic": _read_status(d).get("topic", "—"),
            "started_at": _started_at(d.name),
            "duration": _duration(d),
        })
    return summaries, len(dirs)
