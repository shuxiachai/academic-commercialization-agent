"""Stop ownership must survive physical exit and terminal publication.

Events hold exact seams, not probabilistic sleeps. The processes are fakes;
the real HTTP readers, mutations, admission and terminal writer still run.
"""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from api import access, main, runs


_REAL_POPEN = subprocess.Popen


class Process:
    def __init__(self):
        self.exited = False
        self.terminate = Mock()
        self.kill = Mock()

    def poll(self):
        return 0 if self.exited else None

    def wait(self, timeout=None):
        self.exited = True
        return 0


@pytest.fixture
def stopped_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(runs, "_registry", {})
    monkeypatch.setattr(runs, "_stop_claims", {})
    monkeypatch.setattr(runs, "_inline_paid_operations", {})
    monkeypatch.setattr(runs, "DAILY_CAP", 0)
    monkeypatch.setattr(runs, "MAX_CONCURRENT", 1)
    monkeypatch.setattr(access, "ACCESS_CODE", None)
    monkeypatch.setattr(access, "ACCESS_CODES", None)
    # If admission leaks, fail before anything can launch or cost money.
    monkeypatch.setattr(runs.subprocess, "Popen", Mock(side_effect=AssertionError("worker launch leaked")))
    rid = "20200101T000000Z-abcdef0123"
    directory = tmp_path / rid
    directory.mkdir()
    (directory / "status.json").write_text(json.dumps({"done": False, "stage": "Writer"}))
    (directory / "commercialization_report.md").write_text("Retained partial report")
    proc = Process()
    handle = runs._Handle(rid, "fixture", proc, byok=True)
    handle.started -= runs.TIMEOUT_SECONDS + 1
    runs._registry[rid] = handle
    return TestClient(main.app), rid, directory, proc


@contextmanager
def held_stop(monkeypatch, fixture, method, phase):
    client, rid, _, proc = fixture
    reached, release = Event(), Event()
    original = proc.wait if phase == "process" else runs._commit_external_terminal

    def hold(*args, **kwargs):
        reached.set()
        assert release.wait(15), "test did not release stop seam"
        return original(*args, **kwargs)

    if phase == "process":
        monkeypatch.setattr(proc, "wait", hold)
    else:
        monkeypatch.setattr(runs, "_commit_external_terminal", hold)
    operation = (lambda: client.delete(f"/api/runs/{rid}?intent=cancel")) if method == "cancel" else runs.reap_timeouts
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(operation)
        try:
            assert reached.wait(15), "stop never reached held seam"
            yield
        finally:
            release.set()
        result = future.result(timeout=15)
        if method == "cancel":
            assert result.status_code == 200
        else:
            assert result == [rid]


@pytest.mark.parametrize("method", ["cancel", "timeout"])
@pytest.mark.parametrize("phase", ["process", "terminal"])
def test_stopping_keeps_capacity_and_client_state(monkeypatch, stopped_fixture, method, phase):
    """Popping before wait admitted paid work and presented a live run as failed."""
    client, rid, directory, proc = stopped_fixture
    with held_stop(monkeypatch, stopped_fixture, method, phase):
        health = client.get("/health").json()
        assert (health["active_runs"], health["active_paid_operations"]) == (1, 1)
        assert runs.active_byok_count() == 1
        for suffix in ("", "/progress"):
            response = client.get(f"/api/runs/{rid}{suffix}")
            assert response.status_code == 200
            assert response.json()["state"] == "running"
            if suffix:
                assert response.json()["done"] is False
        # Both funding modes share the retained host slot, including PDF calls.
        for byok in (False, True):
            with pytest.raises(runs.ConcurrencyLimitReached):
                with runs.reserve_inline_paid_operation(owner=None, byok=byok):
                    pytest.fail("inline paid admission leaked")
        assert client.post("/api/runs", json={"topic": "isolated admission fixture"}).status_code == 429
        runs.subprocess.Popen.assert_not_called()
    expected = "cancelled" if method == "cancel" else "timeout"
    assert proc.exited
    assert client.get(f"/api/runs/{rid}").json()["state"] == expected
    assert json.loads((directory / "terminal.json").read_text())["state"] == expected
    assert runs.capacity_counts() == (0, 0)


@pytest.mark.parametrize("method", ["cancel", "timeout"])
@pytest.mark.parametrize("phase", ["process", "terminal"])
def test_stopping_blocks_deletion_retention_and_duplicate_stop(monkeypatch, stopped_fixture, method, phase):
    """A second Cancel or legacy DELETE must not erase the first stop's files."""
    client, rid, directory, proc = stopped_fixture
    with held_stop(monkeypatch, stopped_fixture, method, phase):
        for query in ("?intent=delete", "?intent=cancel", ""):
            assert client.delete(f"/api/runs/{rid}{query}").status_code == 409
        assert runs.reap_timeouts() == []
        assert runs.prune_expired_runs(retention_days=1) == []
        assert (directory / "commercialization_report.md").read_text() == "Retained partial report"
        proc.terminate.assert_called_once_with()
    assert client.delete(f"/api/runs/{rid}?intent=delete").status_code == 200
    assert not directory.exists()


@pytest.mark.parametrize("failure", [PermissionError("private stop path"), subprocess.TimeoutExpired("private command", 5)])
def test_cancel_failure_retains_worker_and_returns_safe_error(monkeypatch, stopped_fixture, failure):
    """A failed terminate used to permanently lose the worker and its paid slot."""
    client, rid, directory, proc = stopped_fixture
    monkeypatch.setattr(proc, "wait", Mock(side_effect=failure))
    response = client.delete(f"/api/runs/{rid}?intent=cancel")
    assert response.status_code == 503
    assert "private" not in response.text
    assert client.get(f"/api/runs/{rid}").json()["state"] == "running"
    assert runs.capacity_counts() == (1, 1)
    assert not (directory / "terminal.json").exists()
    assert not (directory / "cancelled.marker").exists()
    monkeypatch.setattr(proc, "wait", lambda timeout=None: setattr(proc, "exited", True))
    assert client.delete(f"/api/runs/{rid}?intent=cancel").status_code == 200
    assert runs.capacity_counts() == (0, 0)


def test_shutdown_failure_retains_capacity_and_attempts_peer(monkeypatch, stopped_fixture):
    """Shutdown cannot clear a paid worker before knowing whether stop succeeded."""
    client, rid, _, proc = stopped_fixture
    peer = Process()
    runs._registry["peer"] = runs._Handle("peer", "peer", peer)
    monkeypatch.setattr(proc, "wait", Mock(side_effect=PermissionError("denied")))
    with pytest.raises(RuntimeError, match="1 worker"):
        runs.shutdown_all()
    peer.terminate.assert_called_once_with()
    assert peer.exited
    assert client.get(f"/api/runs/{rid}").json()["state"] == "running"
    assert runs.capacity_counts() == (1, 1)
    assert runs._stop_claims == {}


def test_shutdown_cannot_steal_an_active_stop(monkeypatch, stopped_fixture):
    """Normal ASGI draining should avoid this, but a collision must be explicit."""
    _, _, _, proc = stopped_fixture
    with held_stop(monkeypatch, stopped_fixture, "cancel", "terminal"):
        with pytest.raises(RuntimeError, match="1 worker"):
            runs.shutdown_all()
        assert runs.capacity_counts() == (1, 1)
        proc.terminate.assert_called_once_with()
    assert runs.capacity_counts() == (0, 0)
    assert runs._stop_claims == {}


def test_shutdown_cannot_claim_a_pending_launch(stopped_fixture):
    """A no-op placeholder is not successful process termination at shutdown."""
    _, rid, _, _ = stopped_fixture
    runs._registry[rid].proc = runs._PendingProcess()
    with pytest.raises(RuntimeError, match="1 worker"):
        runs.shutdown_all()
    assert runs.capacity_counts() == (1, 1)


@pytest.mark.parametrize("method", ["cancel", "timeout"])
@pytest.mark.parametrize("force_kill", [False, True])
def test_real_local_child_is_reaped_before_terminal_release(monkeypatch, stopped_fixture, method, force_kill):
    """Exercise OS wait/kill locally without importing the paid pipeline worker."""
    client, rid, directory, _ = stopped_fixture
    # Read stdin until EOF, with no network, repository imports or provider key
    # access. The parent owns cleanup even if an assertion fails on either OS.
    with _REAL_POPEN(
        [sys.executable, "-c", "import sys; sys.stdin.buffer.read()"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ) as proc:
        runs._registry[rid].proc = proc
        original_wait = proc.wait
        try:
            if force_kill:
                # Deterministically exercise escalation without waiting five
                # seconds or relying on platform-specific signal handlers.
                monkeypatch.setattr(proc, "terminate", Mock())
                waits = iter((True, False))

                def wait(timeout=None):
                    if next(waits, False):
                        raise subprocess.TimeoutExpired("local fixture", timeout)
                    return original_wait(timeout=timeout)

                monkeypatch.setattr(proc, "wait", wait)
            if method == "cancel":
                assert client.delete(f"/api/runs/{rid}?intent=cancel").status_code == 200
            else:
                assert runs.reap_timeouts() == [rid]
            assert proc.poll() is not None
            assert runs.capacity_counts() == (0, 0)
            terminal = json.loads((directory / "terminal.json").read_text())
            assert terminal["state"] == ("cancelled" if method == "cancel" else "timeout")
            assert terminal["termination_method"] == ("kill" if force_kill else "terminate")
            assert terminal["usage_accounting"]["state"] == "unavailable"
        finally:
            if proc.poll() is None:
                proc.kill()
            original_wait(timeout=5)


def test_pending_launch_is_not_a_cancelled_process(stopped_fixture):
    """Terminating a no-op placeholder must not acknowledge a cancelled worker."""
    client, rid, directory, _ = stopped_fixture
    runs._registry[rid].proc = runs._PendingProcess()
    assert client.delete(f"/api/runs/{rid}?intent=cancel").status_code == 409
    assert runs.reap_timeouts() == []
    assert runs.capacity_counts() == (1, 1)
    assert not (directory / "terminal.json").exists()


def test_completion_race_does_not_invent_cancellation(stopped_fixture):
    """A natural exit between claim and terminate keeps its completed outcome."""
    client, rid, directory, proc = stopped_fixture
    original = runs._registry[rid].terminate

    def finish_first():
        proc.exited = True
        (directory / "status.json").write_text(json.dumps({"done": True}))
        return original()

    runs._registry[rid].terminate = finish_first
    assert client.delete(f"/api/runs/{rid}?intent=cancel").status_code == 409
    assert client.get(f"/api/runs/{rid}").json()["state"] == "completed"
    assert not (directory / "cancelled.marker").exists()
    assert not (directory / "terminal.json").exists()


def test_terminal_read_racing_release_keeps_nonterminal_projection(monkeypatch, stopped_fixture):
    """A pre-publication disk snapshot cannot certify a settled process exit."""
    client, rid, _, _ = stopped_fixture
    original = runs._read_terminal

    def finish_after_read(directory):
        snapshot = original(directory)
        if rid in runs._registry:
            runs.cancel_run(rid)
        return snapshot

    monkeypatch.setattr(runs, "_read_terminal", finish_after_read)
    response = client.get(f"/api/runs/{rid}/progress")
    assert response.status_code == 200
    projection = response.json()
    assert projection["state"] == "running"
    assert projection["done"] is False
    monkeypatch.setattr(runs, "_read_terminal", original)
    settled = client.get(f"/api/runs/{rid}/progress").json()
    assert settled["state"] == "cancelled"
    assert settled["done"] is True
    assert settled["terminal"]["state"] == "cancelled"


def test_pending_deadline_cannot_kill_a_freshly_installed_worker(monkeypatch, stopped_fixture):
    """An old reservation selected before Popen is not an expired new process."""
    _, rid, directory, proc = stopped_fixture
    runs._registry[rid].proc = runs._PendingProcess()
    original = runs._stop_worker

    def finish_launch_before_claim(run_id):
        runs._registry[run_id] = runs._Handle(run_id, "new worker", proc)
        return original(run_id)

    # The old candidate selection included the overdue placeholder. Swap in
    # a fresh worker exactly at claim, as the launch thread could do there.
    monkeypatch.setattr(runs, "_stop_worker", finish_launch_before_claim)
    assert runs.reap_timeouts() == []
    proc.terminate.assert_not_called()
    assert runs.capacity_counts() == (1, 1)
    assert not (directory / "terminal.json").exists()
