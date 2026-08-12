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
import re
import shutil
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

# Runs allowed per UTC day, independent of concurrency — applied separately
# to each access code (see _daily_counts), not as one total every code
# shares. The concurrency cap limits how many runs are billed at once; it
# does nothing to stop one leaked code from triggering hundreds of runs
# sequentially over a day. 0 disables the cap — the default for local
# development.
DAILY_CAP = int(os.getenv("API_DAILY_RUN_CAP", "0"))

# Run directories are named <UTC timestamp>-<hex>; see create_run_id().
_RUN_ID_PATTERN = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]+")

_CANCEL_MARKER = "cancelled.marker"

# Which access.owner_id() created this run, so list_runs() can scope the
# history each code holder sees to their own runs. Absent for BYOK runs and
# for any deployment with no code configured — both cases mean "no owner",
# not "everyone's owner", so those runs never appear in a filtered list.
_OWNER_FILE = ".owner"

_ARTIFACTS = {
    "report":  "commercialization_report.md",
    "scores":  "commercialization_scores.json",
    "sources": "validated_sources.json",
    "notes":   "reviewer_notes.md",
    "steps":   "steps.jsonl",
}


@dataclass(frozen=True)
class BYOKCredentials:
    """A visitor's own LLM + Serper keys, for a run billed to them, not us.

    Scoped to a single subprocess via an explicit `env=` dict passed to
    Popen — never written to disk, never merged into this process's own
    os.environ, so one BYOK run cannot leak its key to another concurrent
    run (BYOK or not) and does not persist past the subprocess it was built
    for.
    """

    llm_provider: str
    llm_api_key: str
    serper_api_key: str

    def as_env(self, base: dict[str, str]) -> dict[str, str]:
        env = dict(base)
        env["LLM_PROVIDER"] = self.llm_provider
        env[f"{self.llm_provider.upper()}_API_KEY"] = self.llm_api_key
        env["SERPER_API_KEY"] = self.serper_api_key
        return env


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


class DailyCapReached(Exception):
    """Raised when the day's run budget is exhausted."""


class RunNotFound(Exception):
    """Raised for an unknown run_id."""


class RunStillActive(Exception):
    """Raised when delete_run is asked to remove a run that has not stopped."""


_registry: dict[str, _Handle] = {}

# Runs started so far today (UTC), per owner, and the date the counts apply
# to — reset lazily on the next start_run call rather than with a scheduled
# task. Keyed by owner (None = no code configured / BYOK is exempt before
# this is ever consulted) so the cap is a per-person budget, not one pool
# every code holder draws from: ten people sharing a single DAILY_CAP meant
# one enthusiastic tester could exhaust everyone else's day, which defeats
# the point of giving each person their own code in the first place.
_daily_counts: dict[str | None, int] = {}
_daily_date = None

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
    byok: BYOKCredentials | None = None,
    owner: str | None = None,
) -> tuple[str, Path]:
    """Launch a worker subprocess. Returns (run_id, run_dir).

    `byok`, if given, is billed to the requester, not the deployment — so it
    is exempt from the daily cap, which exists only to bound the operator's
    own bill. The concurrency cap still applies to every run regardless of
    who is paying: it protects host resources, not a wallet.

    `owner` is the access.owner_id() of whichever code authorized this run —
    None for BYOK (and for a deployment with no code configured at all). Also
    what DAILY_CAP is scoped by: each owner gets their own budget, not one
    pool every code holder draws from together. Written to the run directory
    so list_runs() can show each code holder only the runs made under their
    own code.
    """
    # Claim a slot and publish the run_id in one atomic step. Checking the cap
    # and registering the handle separately let parallel submissions all pass
    # the check before any of them registered.
    #
    # The slot is reserved with a placeholder handle so the subprocess launch —
    # the slow part — happens outside the lock. A reservation counts towards
    # the cap, so a burst cannot slip through while processes are starting.
    with _registry_lock:
        global _daily_date
        if byok is None:
            today = datetime.now(UTC).date()
            if _daily_date != today:
                _daily_date = today
                _daily_counts.clear()
            owner_count = _daily_counts.get(owner, 0)
            if DAILY_CAP and owner_count >= DAILY_CAP:
                raise DailyCapReached(f"{DAILY_CAP} runs already used today")

        if active_count() >= MAX_CONCURRENT:
            raise ConcurrencyLimitReached(
                f"{active_count()} of {MAX_CONCURRENT} concurrent runs in use"
            )
        run_id = create_run_id()
        if byok is None:
            _daily_counts[owner] = _daily_counts.get(owner, 0) + 1
        _registry[run_id] = _Handle(
            run_id=run_id, topic=topic, proc=_PendingProcess(), log_file=None
        )

    run_dir = run_dir_for(run_id)

    # Any failure from here on must release the reserved slot, or the cap
    # leaks permanently: a placeholder counts as alive and nothing else
    # removes it. This has to start at run_dir.mkdir, not just the Popen
    # call below — a mkdir failure (e.g. an unwritable outputs volume) is
    # exactly the kind of failure this guards against, and one that left
    # outside the boundary leaked a slot per attempt with no way to clear
    # it short of restarting the process.
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        if owner is not None:
            (run_dir / _OWNER_FILE).write_text(owner, encoding="utf-8")

        cmd = [sys.executable, "-m", "academic_agent.pipeline_worker", run_id, topic.strip()]
        if language:
            cmd += ["--language", language]
        if weight_profile:
            cmd += ["--weight-profile", weight_profile]
        if paper_json_path and Path(paper_json_path).exists():
            cmd += ["--paper-json", paper_json_path]

        # BYOK credentials travel as env, never as argv: command-line arguments
        # are visible to any other process on the same host via `ps`/the process
        # list, which a shared or multi-tenant deployment cannot rule out.
        env = byok.as_env(os.environ) if byok is not None else None

        log_file = open(run_dir / "process.log", "w", encoding="utf-8")
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log_file, env=env)
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
    try:
        (run_dir_for(run_id) / _CANCEL_MARKER).write_text(
            datetime.now(UTC).isoformat(), encoding="utf-8"
        )
    except OSError:
        # The directory can vanish here if a concurrent delete_run() call for
        # the same id already popped this handle's twin registration and won
        # the race to remove it — see delete_run's docstring. Nothing left to
        # mark at that point is a fine outcome, not a failure to report.
        pass


def delete_run(run_id: str) -> None:
    """Permanently remove a finished run's directory and every artifact in it.

    Refuses a run that is still active — cancel_run() first — so a delete
    can never pull the filesystem out from under a subprocess still writing
    to it. The registry check and the active-run rejection happen under the
    lock together so a run that starts finishing mid-call cannot slip
    through between the two.
    """
    if not _is_valid_run_id(run_id):
        raise RunNotFound(f"Invalid run id: {run_id!r}")

    run_dir = run_dir_for(run_id)
    if not run_dir.is_dir():
        raise RunNotFound(f"No run with id {run_id}")

    with _registry_lock:
        handle = _registry.get(run_id)
        if handle is not None and handle.alive():
            raise RunStillActive(f"Run {run_id} is still active — cancel it first")
        _registry.pop(run_id, None)

    shutil.rmtree(run_dir)


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


def read_steps(run_id: str, since: int = 0) -> list[dict]:
    """Step events from steps.jsonl, skipping the first `since` entries.

    The worker appends to this file while running, so a partially written
    trailing line is normal and is skipped rather than treated as corruption.
    """
    if not _is_valid_run_id(run_id):
        raise RunNotFound(f"Invalid run id: {run_id!r}")

    path = run_dir_for(run_id) / "steps.jsonl"
    if not path.exists():
        return []

    events: list[dict] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index < since:
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue      # the writer is mid-line; it will be there next poll
    except OSError:
        return []
    return events


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
        # A finished run has no handle, and returning None here meant a client
        # showed 0:00 for a run that plainly took minutes. The elapsed time is
        # still on disk: the directory name carries the start and status.json's
        # mtime the last write.
        elapsed = _elapsed_seconds(run_dir)
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


def _elapsed_seconds(run_dir: Path) -> int | None:
    """Wall-clock seconds for a finished run, from what is on disk.

    The run_id encodes the start; status.json's mtime is the last thing the
    worker wrote. Used for runs whose handle is gone, where the in-memory
    timer is no longer available.
    """
    try:
        stamp = run_dir.name.split("-")[0]
        start = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        status_path = run_dir / "status.json"
        if not status_path.exists():
            return None
        end = datetime.fromtimestamp(os.path.getmtime(status_path), tz=UTC)
        secs = int((end - start).total_seconds())
        return secs if secs >= 0 else None
    except (ValueError, OSError):
        return None


def _duration(run_dir: Path) -> str:
    try:
        secs = _elapsed_seconds(run_dir)
        if secs is None:
            return "—"
        return f"{secs}s" if secs < 60 else f"{secs // 60}m {secs % 60:02d}s"
    except (ValueError, OSError):
        return "—"


def _read_owner(run_dir: Path) -> str | None:
    try:
        return (run_dir / _OWNER_FILE).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def owner_of(run_id: str) -> str | None:
    """The access.owner_id() that created this run, or None if it has no owner.

    None covers three distinct cases the caller must not conflate: a BYOK run
    (deliberately untagged), a run created on a deployment with no access code
    configured, and a run directory that does not exist. Callers deciding
    authorization should check existence separately rather than reading None
    as "unowned, therefore fair game".
    """
    if not _is_valid_run_id(run_id):
        return None
    return _read_owner(run_dir_for(run_id))


def list_runs(limit: int = 50, owner: str | None = None) -> tuple[list[dict], int]:
    """Return (summaries, total) for finished and running runs, newest first.

    `owner`, when given, scopes the result to runs created under that same
    access.owner_id() — a code holder sees only their own history, not
    every code's combined. None means no filter: every run, the behaviour
    for a deployment with no access code configured at all.
    """
    if not DEFAULT_OUTPUT_ROOT.is_dir():
        return [], 0

    # Match the run_id shape rather than excluding known non-runs one at a
    # time. The old rule skipped only "benchmark", so adding outputs/_papers
    # for uploads immediately put a storage directory in the run list, where
    # it rendered as a run with no topic and no status.
    dirs = sorted(
        (d for d in DEFAULT_OUTPUT_ROOT.iterdir()
         if d.is_dir() and _RUN_ID_PATTERN.fullmatch(d.name)),
        key=lambda d: d.name,
        reverse=True,
    )
    if owner is not None:
        dirs = [d for d in dirs if _read_owner(d) == owner]
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
            # Not part of RunSummary — the API layer strips this back out
            # for everyone except an admin request, which resolves it to a
            # readable code via access.label_for_owner() first. Included
            # unconditionally here because this function has no notion of
            # "admin"; that decision belongs to the caller, not this layer.
            "_owner": _read_owner(d),
        })
    return summaries, len(dirs)
