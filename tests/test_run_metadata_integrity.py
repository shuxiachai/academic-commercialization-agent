"""Storage faults must not invent completion or take healthy history offline.

Exercise bytes -> both HTTP responses -> history, not only a JSON helper.
All runs are isolated fixtures; no real worker or provider is started.
"""

from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from academic_agent.run_terminal import TerminalRecord, UsageAccounting, commit_terminal_record
from api import access, runs
from api.main import app


RID = "20260905T000000Z-aaaaaaaaaa"
HEALTHY_RID = "20260905T000001Z-bbbbbbbbbb"
USAGE = {"total_tokens": 100, "cost_usd": 0.01, "cost_complete": True, "agents": []}
CORRUPT_STATUS = [
    b'{"done":', b'\xff', b'null', b'[]', b'17', b'"not an object"',
    b'{"done":"false"}', b'{"error":[]}',
]


@pytest.fixture
def history(tmp_path, monkeypatch):
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(runs, "_registry", {})
    monkeypatch.setattr(access, "ACCESS_CODE", None)
    monkeypatch.setattr(access, "ACCESS_CODES", None)
    for rid in (RID, HEALTHY_RID):
        directory = tmp_path / rid
        directory.mkdir()
        (directory / "status.json").write_text(json.dumps({
            "done": True, "stage": "Done", "topic": "Isolated fixture",
            "usage": USAGE, "usage_accounting": {"state": "complete"},
        }), encoding="utf-8")
    return tmp_path / RID, TestClient(app, raise_server_exceptions=False)


def _responses(client):
    bodies = []
    for suffix in ("", "/progress"):
        response = client.get(f"/api/runs/{RID}{suffix}")
        assert response.status_code == 200
        bodies.append(response.json())
    return bodies


def _commit_completed(directory):
    start = datetime(2026, 9, 5, tzinfo=UTC)
    record = TerminalRecord(
        state="completed", reason_code="worker_completed", termination_method="worker_exit",
        started_at=start, ended_at=start + timedelta(seconds=7), elapsed_seconds=7,
        last_stage="Done", usage=USAGE,
        usage_accounting=UsageAccounting(
            state="complete", snapshot_at=start + timedelta(seconds=7),
            run_complete=True, in_flight_request_may_have_spent=False,
        ),
    )
    commit_terminal_record(directory, record)


@pytest.mark.parametrize("payload", CORRUPT_STATUS)
def test_bad_status_preserves_both_read_endpoints_and_healthy_history(history, payload):
    """Syntax, encoding, shape and truthy non-bool flags all used to escape the reader."""
    directory, client = history
    (directory / "status.json").write_bytes(payload)
    direct, progress = _responses(client)
    for body in (direct, progress):
        assert body["state"] == "unknown"
        assert body["status_record_state"] == "unreadable"
        assert body["elapsed_seconds"] is None
        assert body["usage"] is None
        assert body["usage_accounting"]["state"] == "unavailable"
    assert progress["done"] is False
    response = client.get("/api/runs")
    assert response.status_code == 200
    listed = {row["run_id"]: row for row in response.json()["runs"]}
    assert listed[RID]["state"] == "unknown"
    assert listed[RID]["duration"] == "—"
    assert listed[HEALTHY_RID]["state"] == "completed"
    assert (directory / "status.json").read_bytes() == payload


@pytest.mark.parametrize("payload", CORRUPT_STATUS)
def test_valid_terminal_survives_broken_live_projection(history, payload):
    """A weaker damaged projection must not erase committed process/usage facts."""
    directory, client = history
    _commit_completed(directory)
    (directory / "status.json").write_bytes(payload)
    for body in _responses(client):
        assert body["state"] == "completed"
        assert body["status_record_state"] == "unreadable"
        assert body["terminal"]["record_state"] == "committed"
        assert body["elapsed_seconds"] == 7
        assert body["usage"] == USAGE
        assert body["usage_accounting"]["state"] == "complete"
    response = client.get("/api/runs")
    assert response.status_code == 200
    assert next(row for row in response.json()["runs"] if row["run_id"] == RID)["duration"] == "7s"


@pytest.mark.parametrize("marker", ["done", "error", "cancelled"])
def test_unreadable_terminal_never_uses_legacy_success_or_full_cost(history, marker):
    """A present-but-invalid immutable outcome is not a pre-terminal historical run."""
    directory, client = history
    if marker == "error":
        status = json.loads((directory / "status.json").read_text(encoding="utf-8"))
        status["error"] = "private provider text"
        (directory / "status.json").write_text(json.dumps(status), encoding="utf-8")
    elif marker == "cancelled":
        (directory / "cancelled.marker").write_text("fixture", encoding="utf-8")
    (directory / "terminal.json").write_bytes(b"{broken")
    direct, progress = _responses(client)
    for body in (direct, progress):
        assert body["state"] == "unknown"
        assert body["terminal"] == {"record_state": "unreadable"}
        assert body["elapsed_seconds"] is None
        assert body["usage"] == USAGE
        assert body["usage_accounting"]["state"] == "lower_bound"
        assert body["usage_accounting"]["run_complete"] is False
        assert body["usage_accounting"]["in_flight_request_may_have_spent"] is True
        assert "private provider text" not in json.dumps(body)
    assert progress["done"] is False
    assert runs._elapsed_seconds(directory) is None
    listed = client.get("/api/runs").json()["runs"]
    assert next(row for row in listed if row["run_id"] == RID)["duration"] == "—"


def test_absent_status_is_distinct_and_legacy_completion_is_preserved(history):
    directory, client = history
    for body in _responses(client):
        assert body["state"] == "completed"
        assert body["status_record_state"] == "readable"
        assert body["terminal"] is None
    (directory / "status.json").unlink()
    for body in _responses(client):
        assert body["status_record_state"] == "absent"
        assert body["state"] == "failed"


def test_live_process_remains_running_even_when_both_files_are_unreadable(history):
    directory, client = history
    runs._registry[RID] = SimpleNamespace(alive=lambda: True, elapsed=3, topic="Live fixture")
    (directory / "status.json").write_bytes(b"null")
    (directory / "terminal.json").write_bytes(b"{broken")
    direct, progress = _responses(client)
    for body in (direct, progress):
        assert body["state"] == "running"
        assert body["elapsed_seconds"] == 3
        assert body["topic"] == "Live fixture"
        assert body["usage_accounting"]["state"] == "unavailable"
    assert progress["done"] is False


def test_terminal_unavailable_usage_cannot_be_backfilled_from_stale_status(history):
    """A valid terminal's null usage is not permission to resurrect a mutable bill."""
    directory, client = history
    start = datetime(2026, 9, 5, tzinfo=UTC)
    commit_terminal_record(directory, TerminalRecord(
        state="failed", reason_code="worker_exception", termination_method="worker_exit",
        started_at=start, ended_at=start, elapsed_seconds=0, usage=None,
        usage_accounting=UsageAccounting(
            state="unavailable", snapshot_at=start,
            run_complete=False, in_flight_request_may_have_spent=True,
        ),
    ))
    for body in _responses(client):
        assert body["state"] == "failed"
        assert body["usage"] is None
        assert body["usage_accounting"]["state"] == "unavailable"


def test_permission_error_is_read_failure_not_public_diagnostic(history, monkeypatch):
    """Keep paths and exception details local even when the file cannot be opened."""
    directory, client = history
    path_type = type(directory)
    original = path_type.read_text

    def read_text(path, *args, **kwargs):
        if path == directory / "status.json":
            raise PermissionError("private-storage-path")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(path_type, "read_text", read_text)
    for body in _responses(client):
        assert body["state"] == "unknown"
        assert body["status_record_state"] == "unreadable"
        assert "private-storage-path" not in json.dumps(body)
    assert client.get("/api/runs").status_code == 200
