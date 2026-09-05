"""Runtime summary faults must not hide paid reports or invent reuse/spend.

Exercise real persisted bytes through both HTTP endpoints, including nested
faults in otherwise valid immutable terminals. All data is isolated and local.
"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json

from fastapi.testclient import TestClient
import pytest

from academic_agent.run_terminal import TerminalRecord, UsageAccounting, commit_terminal_record
from api import access, runs
from api.main import app


RID = "20260905T010000Z-aaaaaaaaaa"
USAGE = {"total_tokens": 100, "cost_usd": 0.01, "cost_complete": True, "agents": []}
GOOD = {
    "usage": USAGE,
    "usage_accounting": {"state": "complete"},
    "checkpointing": {"state": "partial", "committed_nodes": ["retrieval"], "errors": []},
    "recovery": {"state": "reused", "reused_nodes": ["retrieval"], "next_node": "academic"},
}
FAULTS = [
    ("usage", value) for value in ([], "private-invalid-value", {},
        *({**USAGE, "cost_usd": value} for value in ("0.01", False, -1, float("nan"), float("inf"))),
        *({**USAGE, "total_tokens": value} for value in ("100", False, -1, 2**54)),
        {**USAGE, "agents": "academic"}, {**USAGE, "agents": [None]},
        {**USAGE, "agents": [{"role": "A", "total_tokens": 1, "cost_usd": "0"}]},
        {**USAGE, "unpriced_models": "unknown"}, {**USAGE, "cost_complete": "false"})
] + [
    ("usage_accounting", value) for value in ([], {}, {"state": []}, {"state": "unknown"},
        {"state": "complete", "run_complete": "false"},
        {"state": "complete", "run_complete": False},
        {"state": "complete", "in_flight_request_may_have_spent": True})
] + [
    ("checkpointing", value) for value in ([], {},
        {"state": "partial", "committed_nodes": "not_retrieval"},
        {"state": "partial", "committed_nodes": [False]},
        {"state": "partial", "committed_nodes": ["retrieval", "retrieval"]},
        {"state": "degraded", "errors": {}}, {"state": []})
] + [
    ("recovery", value) for value in ([], {}, {"state": "reused", "reused_nodes": "academic"},
        {"state": "reused", "reused_nodes": []},
        {"state": "reused", "reused_nodes": ["academic", "academic"]},
        {"state": "reused", "reused_nodes": ["imaginary-node"]},
        {"state": "not_requested", "source_run_id": {}})
]


@pytest.fixture
def runtime_client(tmp_path, monkeypatch):
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(runs, "_registry", {})
    monkeypatch.setattr(access, "ACCESS_CODE", None)
    monkeypatch.setattr(access, "ACCESS_CODES", None)
    directory = tmp_path / RID
    directory.mkdir()
    status = {"done": True, "stage": "Done", "topic": "Local runtime fixture", **deepcopy(GOOD)}
    (directory / "status.json").write_text(json.dumps(status), encoding="utf-8")
    (directory / "commercialization_report.md").write_text("# Preserved report", encoding="utf-8")
    return directory, TestClient(app, raise_server_exceptions=False)


def _terminal(directory):
    start = datetime(2026, 9, 5, tzinfo=UTC)
    commit_terminal_record(directory, TerminalRecord(
        state="completed", reason_code="worker_completed", termination_method="worker_exit",
        started_at=start, ended_at=start + timedelta(seconds=7), elapsed_seconds=7,
        usage=USAGE, checkpointing=GOOD["checkpointing"], recovery=GOOD["recovery"],
        usage_accounting=UsageAccounting(
            state="complete", snapshot_at=start, run_complete=True,
            in_flight_request_may_have_spent=False,
        ),
    ))


def _responses(client):
    for suffix in ("", "/progress"):
        response = client.get(f"/api/runs/{RID}{suffix}")
        assert response.status_code == 200
        yield response.json()


@pytest.mark.parametrize("field,value", FAULTS)
def test_status_runtime_fault_remains_local(runtime_client, field, value):
    """Bad prices/lists used to fail HTTP, crash rendering, or invent reuse counts."""
    directory, client = runtime_client
    path = directory / "status.json"
    status = json.loads(path.read_text(encoding="utf-8"))
    status[field] = value
    original = json.dumps(status).encode("utf-8")
    path.write_bytes(original)
    for body in _responses(client):
        assert body["state"] == "completed"
        assert body["status_record_state"] == "readable"
        assert body["runtime_metadata_unreadable"] == [field]
        if field == "usage_accounting":
            assert body["usage"] == USAGE
            assert body["usage_accounting"]["state"] == "lower_bound"
            assert body["usage_accounting"]["run_complete"] is False
        else:
            assert body[field] is None
        if field == "usage":
            assert body["usage_accounting"]["state"] == "unavailable"
        if field in ("checkpointing", "recovery"):
            assert body["usage"] == USAGE
            assert body["usage_accounting"] == GOOD["usage_accounting"]
        assert "private-invalid-value" not in json.dumps(body)
    assert client.get("/api/runs").status_code == 200
    assert client.get(f"/api/runs/{RID}/report").text == "# Preserved report"
    assert path.read_bytes() == original


@pytest.mark.parametrize("field,value", [
    (field, value) for field, value in FAULTS
    if field != "usage_accounting" and isinstance(value, dict)
])
def test_bad_terminal_summary_never_resurrects_good_mutable_snapshot(runtime_client, field, value):
    """An empty terminal dict used truthiness fallback; other nested faults escaped to JS."""
    directory, client = runtime_client
    _terminal(directory)
    path = directory / "terminal.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record[field] = value
    original = json.dumps(record).encode("utf-8")
    path.write_bytes(original)
    for body in _responses(client):
        assert body["state"] == "completed"
        assert body["terminal"]["record_state"] == "committed"
        assert body["elapsed_seconds"] == 7
        assert body["runtime_metadata_unreadable"] == [field]
        assert body[field] is None
        if field == "usage":
            assert body["usage_accounting"]["state"] == "unavailable"
    assert path.read_bytes() == original
    if field == "usage":
        # The bad counter snapshot does not revoke known worker completion.
        for body in _responses(client):
            assert body["usage_accounting"]["run_complete"] is True
            assert body["usage_accounting"]["in_flight_request_may_have_spent"] is False


def test_valid_terminal_ignores_bad_shadowed_live_summaries(runtime_client):
    """Validate the selected snapshot, not weaker fields that are never displayed."""
    directory, client = runtime_client
    _terminal(directory)
    status = {"done": True, **{key: [] for key in GOOD}}
    (directory / "status.json").write_text(json.dumps(status), encoding="utf-8")
    for body in _responses(client):
        assert body["runtime_metadata_unreadable"] == []
        assert body["usage"] == USAGE
        assert body["checkpointing"] == GOOD["checkpointing"]
        assert body["recovery"] == GOOD["recovery"]


@pytest.mark.parametrize("snapshot", [
    GOOD, {key: None for key in GOOD},
    {"usage": {"total_tokens": 0}, "usage_accounting": None},
    {"usage": {"total_tokens": 12, "cost_usd": None, "cost_complete": False}},
    {"usage": {**USAGE, "collection_error": "collector unavailable"},
     "usage_accounting": {"state": "unavailable"}},
    {"usage": {"collection_error": "collector unavailable"},
     "usage_accounting": {"state": "unavailable"}},
    {"checkpointing": {"state": "degraded", "committed_nodes": ["retrieval"], "errors": ["disk error"]},
     "recovery": {"state": "cold_start", "reused_nodes": [], "source_run_id": "legacy-parent"}},
])
def test_valid_legacy_and_absent_summaries_remain_unchanged(runtime_client, snapshot):
    directory, client = runtime_client
    path = directory / "status.json"
    status = {"done": True, **{key: None for key in GOOD}, **deepcopy(snapshot)}
    path.write_text(json.dumps(status), encoding="utf-8")
    for body in _responses(client):
        assert body["runtime_metadata_unreadable"] == []
        for key, value in snapshot.items():
            assert body[key] == value


def test_complete_accounting_without_measurement_cannot_certify_a_bill(runtime_client):
    directory, client = runtime_client
    (directory / "status.json").write_text(json.dumps({
        "done": True, "usage": None, "usage_accounting": {"state": "complete"},
    }), encoding="utf-8")
    for body in _responses(client):
        assert body["runtime_metadata_unreadable"] == ["usage_accounting"]
        assert body["usage_accounting"]["state"] == "unavailable"


def test_legacy_collector_diagnostic_without_accounting_remains_explicit(runtime_client):
    """Readable diagnostic-only snapshots are unavailable, not a malformed or zero bill."""
    directory, client = runtime_client
    usage = {"collection_error": "collector unavailable"}
    (directory / "status.json").write_text(json.dumps({
        "done": True, "usage": usage,
    }), encoding="utf-8")
    for body in _responses(client):
        assert body["runtime_metadata_unreadable"] == []
        assert body["usage"] == usage
        assert body["usage_accounting"]["state"] == "unavailable"
