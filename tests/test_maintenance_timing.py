"""Time-qualified maintenance observations must survive both HTTP schemas."""

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from threading import Event
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from api import main, runs
from api.models import ReadinessStatus


STAGES = ("timeouts", "papers", "retention", "receipts")
TIMING_FIELDS = {
    "current_started_at", "current_elapsed_seconds", "last_started_at",
    "last_finished_at", "last_duration_seconds", "last_finished_age_seconds",
}


class Clock:
    """Do not patch time.monotonic globally: asyncio needs its real scheduler."""

    def __init__(self):
        self.wall = datetime(2026, 9, 7, tzinfo=UTC)
        self.mono = 100.0

    def __call__(self):
        return self.wall, self.mono

    def advance(self, seconds, wall_seconds=None):
        self.mono += seconds
        self.wall += timedelta(seconds=seconds if wall_seconds is None else wall_seconds)


@pytest.fixture
def clock(monkeypatch, tmp_path):
    clock = Clock()
    monkeypatch.setattr(main, "_maintenance_clock", clock)
    monkeypatch.setattr(main, "_maintenance_timings", {})
    monkeypatch.setattr(main, "_maintenance_checks", dict.fromkeys(STAGES, "not_checked"))
    monkeypatch.setattr(main, "_maintenance_task", Mock(done=lambda: False))
    monkeypatch.setattr(main, "readiness", lambda: ReadinessStatus(ready=True, checks={}))
    monkeypatch.setattr(runs, "_registry", {})
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(runs, "_stop_claims", {})
    monkeypatch.setattr(runs, "_inline_paid_operations", {})
    monkeypatch.setattr(runs, "shutdown_all", Mock())
    monkeypatch.setattr(runs.subprocess, "Popen", Mock(side_effect=AssertionError("worker launch leaked")))
    return clock


def read_both():
    client = TestClient(main.app)
    responses = [client.get(path) for path in ("/health", "/health/ready")]
    snapshots = [response.json()["maintenance"] for response in responses]
    assert snapshots[0] == snapshots[1], "HTTP endpoints lost or changed observation fields"
    return snapshots[0], responses


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.utcoffset() == timedelta(0)
    return parsed


@pytest.mark.parametrize("stage", STAGES)
def test_old_success_ages_without_becoming_a_new_check(clock, stage):
    """A one-hour-old ok formerly looked identical to a just-completed ok."""
    operation = Mock(side_effect=lambda: clock.advance(3))
    asyncio.run(main._maintenance_stage(stage, operation))
    first, _ = read_both()
    clock.advance(3600)
    later, responses = read_both()
    timing = later["timings"][stage]
    assert set(timing) == TIMING_FIELDS
    assert later["checks"][stage] == first["checks"][stage] == "ok"
    assert timing["last_finished_at"] == first["timings"][stage]["last_finished_at"]
    assert timing["last_finished_age_seconds"] == 3600
    assert first["timings"][stage]["last_finished_age_seconds"] == 0
    assert timing["last_duration_seconds"] == 3
    assert timing["current_started_at"] is None
    assert timing["current_elapsed_seconds"] is None
    assert timestamp(timing["last_started_at"]) == datetime(2026, 9, 7, tzinfo=UTC)
    assert timestamp(later["observed_at"]) == clock.wall
    assert all(response.status_code == 200 for response in responses)
    operation.assert_called_once_with()


@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize("failure", [False, True])
@pytest.mark.parametrize("previous_failure", [False, True])
def test_running_attempt_preserves_previous_result_and_completion_time(clock, stage, failure, previous_failure):
    """Dispatch is not completion, including while graceful cancellation drains."""
    def first():
        clock.advance(2)
        if previous_failure:
            raise PermissionError("previous failure")

    asyncio.run(main._maintenance_stage(stage, first))
    before, _ = read_both()
    clock.advance(10)
    started = clock.wall
    entered, release = Event(), Event()

    def slow():
        entered.set()
        assert release.wait(15), "test did not release maintenance"
        if failure:
            raise PermissionError("private fixture path")
        return []

    async def exercise():
        task = asyncio.create_task(main._maintenance_stage(stage, slow))
        try:
            assert await asyncio.to_thread(entered.wait, 10)
            clock.advance(45)
            for _ in range(2):
                task.cancel()
                await asyncio.sleep(0)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
                for route in ("/health", "/health/ready"):
                    response = await client.get(route)
                    assert response.status_code == (503 if route.endswith("ready") and previous_failure and stage == "timeouts" else 200)
                    snapshot = response.json()["maintenance"]
                    timing = snapshot["timings"][stage]
                    assert snapshot["checks"][stage] == ("failed" if previous_failure else "ok")
                    assert timestamp(timing["current_started_at"]) == started
                    assert timing["current_elapsed_seconds"] == 45
                    assert timing["last_finished_at"] == before["timings"][stage]["last_finished_at"]
                    assert timing["last_duration_seconds"] == 2
                    assert timing["last_finished_age_seconds"] == 55
        finally:
            release.set()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(task, 10)

    asyncio.run(exercise())
    after, responses = read_both()
    timing = after["timings"][stage]
    assert after["checks"][stage] == ("failed" if failure else "ok")
    assert timestamp(timing["last_started_at"]) == started
    assert timestamp(timing["last_finished_at"]) == clock.wall
    assert timing["last_duration_seconds"] == 45
    assert timing["last_finished_age_seconds"] == 0
    assert timing["current_started_at"] is None
    assert timing["current_elapsed_seconds"] is None
    assert responses[1].status_code == (503 if failure and stage == "timeouts" else 200)
    assert "private fixture path" not in responses[1].text
    for other in set(STAGES) - {stage}:
        assert after["checks"][other] == "not_checked"
        assert all(value is None for value in after["timings"][other].values())


@pytest.mark.parametrize("wall_shift", [-86400, 86400])
def test_clock_adjustments_do_not_rewrite_duration_or_age(clock, wall_shift):
    """NTP changes may reorder UTC labels, never the monotonic elapsed facts."""
    asyncio.run(main._maintenance_stage("timeouts", lambda: clock.advance(4, wall_shift)))
    clock.advance(7, wall_shift)
    snapshot, _ = read_both()
    assert snapshot["timings"]["timeouts"]["last_duration_seconds"] == 4
    assert snapshot["timings"]["timeouts"]["last_finished_age_seconds"] == 7
    assert timestamp(snapshot["observed_at"]) == clock.wall


@pytest.mark.parametrize("stage", STAGES)
def test_first_inflight_attempt_has_no_fabricated_completion(clock, stage):
    """A current dispatch time must not mint a completed result or zero age."""
    entered, release = Event(), Event()

    def first():
        entered.set()
        assert release.wait(15)

    async def exercise():
        task = asyncio.create_task(main._maintenance_stage(stage, first))
        try:
            assert await asyncio.to_thread(entered.wait, 10)
            clock.advance(8)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
                for route in ("/health", "/health/ready"):
                    snapshot = (await client.get(route)).json()["maintenance"]
                    timing = snapshot["timings"][stage]
                    assert snapshot["checks"][stage] == "not_checked"
                    assert timing["current_elapsed_seconds"] == 8
                    assert timestamp(timing["current_started_at"]) == datetime(2026, 9, 7, tzinfo=UTC)
                    assert all(value is None for key, value in timing.items() if key.startswith("last_"))
        finally:
            release.set()
            await asyncio.wait_for(task, 10)

    asyncio.run(exercise())


def test_lifespan_resets_prior_process_observations(clock, monkeypatch):
    """A new managed lifespan cannot inherit the previous watchdog's ok."""
    asyncio.run(main._maintenance_stage("timeouts", lambda: clock.advance(4)))
    monkeypatch.setattr(main, "_REAP_INTERVAL_SECONDS", 3600)

    async def exercise():
        async with main._lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
                for route in ("/health", "/health/ready"):
                    snapshot = (await client.get(route)).json()["maintenance"]
                    assert snapshot["state"] == "running"
                    assert snapshot["checks"] == dict.fromkeys(STAGES, "not_checked")
                    assert set(snapshot["timings"]) == set(STAGES)
                    assert all(value is None for timing in snapshot["timings"].values() for value in timing.values())
        runs.shutdown_all.assert_called_once_with()

    asyncio.run(exercise())


@pytest.mark.parametrize("cancelled", [False, True])
def test_dead_supervisor_preserves_old_observation_without_passing_readiness(clock, monkeypatch, cancelled):
    """A timestamp is evidence of a past result, not proof the supervisor lives."""
    asyncio.run(main._maintenance_stage("timeouts", lambda: clock.advance(1)))
    clock.advance(300)
    monkeypatch.setattr(main, "_maintenance_task", Mock(done=lambda: True, cancelled=lambda: cancelled))
    snapshot, responses = read_both()
    assert snapshot["state"] == ("stopped" if cancelled else "failed")
    assert snapshot["checks"]["timeouts"] == "ok"
    assert snapshot["timings"]["timeouts"]["last_finished_age_seconds"] == 300
    assert responses[1].status_code == 503


def test_unmanaged_readiness_is_explicit_and_timing_schema_is_public(clock, monkeypatch):
    """Readiness previously dropped maintenance entirely at the response seam."""
    monkeypatch.setattr(main, "_maintenance_task", None)
    snapshot, responses = read_both()
    assert snapshot["state"] == "not_started"
    assert "watchdog" not in responses[1].json()["checks"]
    assert all(value is None for timing in snapshot["timings"].values() for value in timing.values())
    schema = TestClient(main.app).get("/openapi.json").json()["components"]["schemas"]
    assert set(schema["MaintenanceTiming"]["properties"]) == TIMING_FIELDS
    assert "timings" in schema["MaintenanceStatus"]["properties"]
    assert "maintenance" in schema["ReadinessStatus"]["properties"]
