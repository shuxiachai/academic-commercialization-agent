"""A watchdog countdown is a current process fact, not a saved wall timestamp.

Both HTTP readers must deliver the same observation, including during worker
startup and after status loss. All processes and provider work are isolated.
"""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
import pytest

from academic_agent.run_spec import RESUME_SNAPSHOT_DIRECTORY, RunSpec
from api import access, runs
from api.main import app


RID = "20261126T000000Z-aaaaaaaaaa"
SAVED_BUDGET = {
    "state": "active",
    "hard_timeout_seconds": 1800,
    "hard_deadline_at": "2026-11-26T00:30:00+00:00",
    "request_timeout_seconds": 150,
    "remaining_seconds": 999,
}


@pytest.fixture
def run_page(tmp_path, monkeypatch):
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(runs, "_registry", {})
    monkeypatch.setattr(runs, "_stop_claims", {})
    monkeypatch.setattr(access, "ACCESS_CODE", None)
    monkeypatch.setattr(access, "ACCESS_CODES", None)
    directory = tmp_path / RID
    directory.mkdir()
    (directory / "status.json").write_text(json.dumps({
        "done": False, "stage": "Scoring", "topic": "Isolated countdown fixture",
        "runtime_budget": SAVED_BUDGET,
    }), encoding="utf-8")
    yield directory, TestClient(app)
    for handle in runs._registry.values():
        if handle.log_file is not None:
            handle.log_file.close()


def _live_handle(*, duration=1800, proc=None):
    handle = runs._Handle(
        run_id=RID, topic="Isolated countdown fixture",
        proc=proc or SimpleNamespace(poll=lambda: None),
        started=1000, hard_timeout_seconds=duration,
    )
    runs._registry[RID] = handle
    return handle


def _responses(client, run_id=RID):
    for suffix in ("", "/progress"):
        response = client.get(f"/api/runs/{run_id}{suffix}")
        assert response.status_code == 200, response.text
        yield response.json()


@pytest.mark.parametrize("status_fault", [None, "absent", "unreadable"])
def test_both_endpoints_use_current_handle_not_saved_budget(run_page, monkeypatch, status_fault):
    """Old status, missing first status, and read loss cannot invent a countdown."""
    directory, client = run_page
    _live_handle(duration=2100)
    monkeypatch.setattr(runs._Handle, "elapsed", property(lambda self: 123))
    status_path = directory / "status.json"
    if status_fault == "absent":
        status_path.unlink()
    elif status_fault == "unreadable":
        status_path.write_bytes(b"{broken")
    before = status_path.read_bytes() if status_path.exists() else None
    for body in _responses(client):
        assert body["state"] == "running"
        assert body["elapsed_seconds"] == 123
        assert body["runtime_budget"]["hard_timeout_seconds"] == 2100
        assert body["runtime_budget"]["remaining_seconds"] == 1977
        if status_fault is None:
            assert body["runtime_budget"]["request_timeout_seconds"] == 150
    assert (status_path.read_bytes() if status_path.exists() else None) == before


def test_elapsed_and_remaining_share_launch_monotonic_origin(run_page):
    """A wall-clock correction must not change the active run's remaining window."""
    _live_handle(duration=1800)
    with patch.object(runs.time, "monotonic", return_value=1123.8):
        with patch.object(runs.time, "time", return_value=0):
            first = runs.get_state(RID)
        with patch.object(runs.time, "time", return_value=9999999999):
            later = runs.get_state(RID)
    assert first["elapsed_seconds"] == later["elapsed_seconds"] == 123
    assert first["runtime_budget"]["remaining_seconds"] == 1677
    assert first["runtime_budget"] == later["runtime_budget"]


@pytest.mark.parametrize("elapsed,remaining", [(1800, 0), (1900, 0), (-1, None)])
def test_overdue_never_becomes_negative_or_claims_a_terminal_outcome(
    run_page, monkeypatch, elapsed, remaining,
):
    """Watchdog expiry can precede actual exit and immutable terminal publication."""
    _, client = run_page
    _live_handle()
    monkeypatch.setattr(runs._Handle, "elapsed", property(lambda self: elapsed))
    direct, progress = _responses(client)
    for body in (direct, progress):
        assert body["state"] == "running"
        assert body["runtime_budget"]["remaining_seconds"] == remaining
    assert progress["done"] is False


@pytest.mark.parametrize("kind", ["pending", "unknown_duration", "completed", "untracked"])
def test_saved_countdown_cannot_survive_missing_current_process_facts(run_page, monkeypatch, kind):
    """A persisted remaining number is stale without a real tracked launch budget."""
    directory, client = run_page
    monkeypatch.setattr(runs._Handle, "elapsed", property(lambda self: 123))
    if kind == "pending":
        _live_handle(proc=runs._PendingProcess())
    elif kind == "unknown_duration":
        _live_handle(duration=None)
    elif kind == "completed":
        status = json.loads((directory / "status.json").read_text(encoding="utf-8"))
        status.update(done=True, stage="Done")
        (directory / "status.json").write_text(json.dumps(status), encoding="utf-8")
    for body in _responses(client):
        assert body["runtime_budget"]["remaining_seconds"] is None


@pytest.mark.parametrize("resume", [False, True])
def test_launch_and_resume_capture_the_duration_sent_to_the_worker(run_page, monkeypatch, resume):
    """Each launch owns its full window; a resume cannot inherit its parent's elapsed time."""
    directory, client = run_page
    if resume:
        (directory / "checkpoints").mkdir()
    monkeypatch.setattr(runs, "TIMEOUT_SECONDS", 2100)
    monkeypatch.setattr(runs, "_admit_paid_operation_locked", lambda **kwargs: None)
    popen = Mock(return_value=SimpleNamespace(poll=lambda: None))
    monkeypatch.setattr(runs.subprocess, "Popen", popen)
    with patch.object(runs.time, "monotonic", return_value=5000):
        run_id, run_dir = runs._start_run_from_spec(
            RunSpec(topic="Isolated countdown launch"), resume_from=RID if resume else None,
        )
    handle = runs._registry[run_id]
    command = popen.call_args.args[0]
    assert handle.started == 5000
    assert handle.hard_timeout_seconds == int(command[command.index("--hard-timeout-seconds") + 1]) == 2100
    assert (run_dir / RESUME_SNAPSHOT_DIRECTORY).is_dir() is resume
    assert not (run_dir / "status.json").exists()
    monkeypatch.setattr(runs._Handle, "elapsed", property(lambda self: 7))
    for body in _responses(client, run_id):
        assert body["elapsed_seconds"] == 7
        assert body["runtime_budget"]["remaining_seconds"] == 2093


def test_regression_assertion_rejects_unchanged_saved_budget(run_page, monkeypatch):
    """Re-injecting the former pass-through must fail the HTTP countdown assertion."""
    _, client = run_page
    _live_handle()
    monkeypatch.setattr(runs._Handle, "elapsed", property(lambda self: 123))
    monkeypatch.setattr(runs, "_runtime_budget_projection", lambda saved, *args, **kwargs: saved)
    for body in _responses(client):
        with pytest.raises(AssertionError):
            assert body["runtime_budget"]["remaining_seconds"] == 1677


@pytest.mark.parametrize("duration,current_policy", [(120, 60), (120, 300), (None, 120)])
def test_countdown_watchdog_and_terminal_share_the_launch_duration(
    run_page, monkeypatch, duration, current_policy,
):
    """Changed policy must neither kill early nor extend a captured launch window."""
    directory, client = run_page
    process = Mock()
    process.poll.return_value = None
    process.terminate.side_effect = lambda: setattr(process.poll, "return_value", -15)
    _live_handle(duration=duration, proc=process)
    monkeypatch.setattr(runs, "TIMEOUT_SECONDS", current_policy)
    elapsed = [119]
    monkeypatch.setattr(runs._Handle, "elapsed", property(lambda self: elapsed[0]))
    for body in _responses(client):
        assert body["runtime_budget"]["remaining_seconds"] == (1 if duration else None)
    assert runs.reap_timeouts() == []
    elapsed[0] = 120
    for body in _responses(client):
        assert body["state"] == "running"
        assert body["runtime_budget"]["remaining_seconds"] == (0 if duration else None)
    assert runs.reap_timeouts() == []  # Preserve the existing strict > boundary.
    elapsed[0] = 121
    assert runs.reap_timeouts() == [RID]
    process.terminate.assert_called_once()
    assert (directory / "error.log").read_text(encoding="utf-8") == "Analysis timed out after 2 minutes."
    terminal = json.loads((directory / "terminal.json").read_text(encoding="utf-8"))
    assert terminal["timeout_seconds"] == 120
    for body in _responses(client):
        assert body["state"] == "timeout"
        assert body["elapsed_seconds"] == 121
        assert body["runtime_budget"]["remaining_seconds"] is None
