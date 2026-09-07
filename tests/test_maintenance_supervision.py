"""Cleanup faults must not silently remove timeout enforcement or shutdown."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from api import main, runs
from api.models import ReadinessStatus


@pytest.fixture(autouse=True)
def isolated_supervisor(monkeypatch):
    monkeypatch.setattr(main, "_maintenance_task", None)
    monkeypatch.setattr(main, "_maintenance_checks", {})
    monkeypatch.setattr(main, "_maintenance_timings", {})


def test_cleanup_fault_keeps_later_stage_and_next_timeout_cycle_alive():
    """A root PermissionError formerly escaped before the next watchdog tick."""
    async def exercise():
        with (
            patch.object(main.asyncio, "sleep", AsyncMock(side_effect=[None, None, asyncio.CancelledError()])),
            patch.object(runs, "reap_timeouts", return_value=[]) as watchdog,
            patch.object(main.papers, "prune_old", side_effect=PermissionError("private path")),
            patch.object(runs, "prune_expired_runs", return_value=[]) as retention,
        ):
            with pytest.raises(asyncio.CancelledError):
                await main._reaper()
            assert watchdog.call_count == 2
            assert retention.call_count == 2
        assert main._maintenance_checks == {"timeouts": "ok", "papers": "failed", "retention": "ok"}
    asyncio.run(exercise())


def test_failed_task_cannot_skip_worker_shutdown():
    """Awaiting a failed reaper used to bypass shutdown_all entirely."""
    async def broken():
        raise RuntimeError("supervisor defect")

    async def exercise():
        with patch.object(main, "_reaper", broken), patch.object(runs, "shutdown_all") as shutdown:
            async with main._lifespan(main.app):
                await asyncio.sleep(0)
            shutdown.assert_called_once_with()
    asyncio.run(exercise())


@pytest.mark.parametrize("dead", [False, True])
def test_health_delivers_cleanup_failure_but_only_dead_watchdog_blocks_readiness(dead):
    """A diagnostic computed internally must survive both HTTP projections."""
    main._maintenance_checks = {"timeouts": "ok", "papers": "failed", "retention": "ok"}
    main._maintenance_task = Mock(done=lambda: dead, cancelled=lambda: False)
    with patch.object(main, "readiness", return_value=ReadinessStatus(ready=True, checks={})):
        client = TestClient(main.app)
        status = client.get("/health").json()["maintenance"]
        assert status["state"] == ("failed" if dead else "degraded")
        assert status["checks"]["papers"] == "failed"
        response = client.get("/health/ready")
        assert response.status_code == (503 if dead else 200)
        assert response.json()["ready"] is not dead
        assert "private path" not in response.text


def test_unstarted_is_not_a_passing_audit():
    snapshot = TestClient(main.app).get("/health").json()["maintenance"]
    assert snapshot == {
        "state": "not_started", "checks": {}, "timings": {}, "observed_at": snapshot["observed_at"],
    }
    assert snapshot["observed_at"].endswith("Z")


def test_stage_recovers_only_after_its_next_success():
    """A later successful cleanup removes that stage's old fault, not others."""
    async def exercise():
        with (
            patch.object(main.asyncio, "sleep", AsyncMock(side_effect=[None, None, asyncio.CancelledError()])),
            patch.object(runs, "reap_timeouts", side_effect=RuntimeError("fixture timeout failure")),
            patch.object(main.papers, "prune_old", side_effect=[PermissionError("denied"), 0]),
            patch.object(runs, "prune_expired_runs", return_value=[]),
        ):
            with pytest.raises(asyncio.CancelledError):
                await main._reaper()
        assert main._maintenance_checks == {"timeouts": "failed", "papers": "ok", "retention": "ok"}
    asyncio.run(exercise())
    main._maintenance_task = Mock(done=lambda: False)
    with patch.object(main, "readiness", return_value=ReadinessStatus(ready=True, checks={})):
        response = TestClient(main.app).get("/health/ready")
        assert response.status_code == 503
        assert response.json()["checks"]["watchdog"] == "timeout watchdog unavailable"


def test_timeout_stop_failure_preserves_handle_and_still_stops_peers(monkeypatch):
    """Popping the entire batch lost paid workers when the first stop raised."""
    first = Mock(elapsed=runs.TIMEOUT_SECONDS + 1)
    first.terminate.side_effect = PermissionError("denied")
    second = Mock(elapsed=runs.TIMEOUT_SECONDS + 1)
    second.terminate.return_value = "already_exited"
    monkeypatch.setattr(runs, "_registry", {"one": first, "two": second})
    with pytest.raises(RuntimeError, match="1 run"):
        runs.reap_timeouts()
    assert runs._registry == {"one": first}
    second.terminate.assert_called_once_with()


def test_shutdown_attempts_all_workers_before_raising(monkeypatch):
    first, second = Mock(), Mock()
    first.terminate.side_effect = PermissionError("denied")
    monkeypatch.setattr(runs, "_registry", {"one": first, "two": second})
    with pytest.raises(RuntimeError, match="1 worker"):
        runs.shutdown_all()
    second.terminate.assert_called_once_with()
