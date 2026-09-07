"""Exercise the ASGI loop while a synchronous maintenance seam is held.

An independent observer releases every hold, including with the original
blocking implementation. An asyncio-only timeout could not detect that defect:
the loop responsible for firing its timeout was itself blocked.
"""

import asyncio
import contextlib
import json
import time
from threading import Event
from unittest.mock import Mock

import httpx
import pytest

from api import main, runs
from api.models import ReadinessStatus


STAGES = ("timeouts", "papers", "retention")
RID = "20200101T000000Z-abcdef0123"
_REAP_TIMEOUTS = runs.reap_timeouts
_SHUTDOWN_ALL = runs.shutdown_all


@pytest.fixture
def maintenance_fixture(tmp_path, monkeypatch):
    """No retained user artifacts or real worker can enter this watchdog."""
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(runs, "_registry", {})
    monkeypatch.setattr(runs, "_stop_claims", {})
    monkeypatch.setattr(runs, "_inline_paid_operations", {})
    monkeypatch.setattr(main, "_maintenance_task", None)
    monkeypatch.setattr(main, "_maintenance_checks", {})
    monkeypatch.setattr(main, "_maintenance_timings", {})
    monkeypatch.setattr(main, "_REAP_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(main, "readiness", lambda: ReadinessStatus(ready=True, checks={}))
    operations = dict.fromkeys(STAGES)
    # Cleanup now accepts a per-attempt observer keyword, while the watchdog
    # still has no argument. Fakes accept it without changing the held-work,
    # timing, cancellation or HTTP assertions these tests were written for.
    for name, module, attribute in (
        ("timeouts", runs, "reap_timeouts"),
        ("papers", main.papers, "prune_old"),
        ("retention", runs, "prune_expired_runs"),
    ):
        operations[name] = Mock(return_value=[])
        monkeypatch.setattr(module, attribute, operations[name])
    monkeypatch.setattr(runs.subprocess, "Popen", Mock(side_effect=AssertionError("worker launch leaked")))
    shutdown = Mock()
    monkeypatch.setattr(runs, "shutdown_all", shutdown)
    directory = tmp_path / RID
    directory.mkdir()
    (directory / "status.json").write_text(json.dumps({"done": True, "stage": "Done"}))
    (directory / "commercialization_report.md").write_text("Offline retained report")
    return operations, shutdown


@pytest.mark.parametrize("stage", STAGES)
def test_http_probes_complete_before_slow_maintenance_is_released(maintenance_fixture, stage):
    """Direct synchronous reaping prevented even free health/status responses."""
    operations, shutdown = maintenance_fixture
    entered, release = Event(), Event()

    def slow(**_kwargs):
        entered.set()
        assert release.wait(15), "observer failed to release maintenance"
        return []

    operations[stage].side_effect = slow

    async def exercise():
        loop = asyncio.get_running_loop()

        async def probe():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
                responses = await asyncio.gather(*(client.get(path) for path in (
                    "/health", "/health/ready", f"/api/runs/{RID}", f"/api/runs/{RID}/progress",
                )))
            assert all(response.status_code == 200 for response in responses)
            assert responses[0].json()["maintenance"]["checks"][stage] == "not_checked"
            assert responses[1].json()["ready"] is True
            assert responses[2].json()["state"] == "completed"
            assert responses[3].json()["done"] is True
            assert not release.is_set(), "responses arrived only after maintenance ended"

        def observe():
            future = None
            try:
                assert entered.wait(10), "maintenance did not start"
                started = time.monotonic()
                future = asyncio.run_coroutine_threadsafe(probe(), loop)
                try:
                    future.result(timeout=5)
                except TimeoutError:
                    pytest.fail(f"HTTP probes stalled behind synchronous {stage} maintenance")
                print(f"{stage}: four held-stage HTTP probes completed in {time.monotonic() - started:.3f}s")
            finally:
                release.set()
                if future is not None and not future.done():
                    future.cancel()

        async with main._lifespan(main.app):
            await asyncio.to_thread(observe)
        shutdown.assert_called_once_with()
        runs.subprocess.Popen.assert_not_called()

    asyncio.run(exercise())


@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize("failure", [False, True])
@pytest.mark.parametrize("cancel_target", ["supervisor", "lifespan"])
def test_shutdown_drains_owned_stage_despite_repeated_cancellation(maintenance_fixture, stage, failure, cancel_target):
    """Cancelling to_thread alone orphaned the stop before shutdown_all ran."""
    operations, shutdown = maintenance_fixture
    entered, release, finished = Event(), Event(), Event()

    def slow(**_kwargs):
        entered.set()
        try:
            assert release.wait(15), "test failed to release maintenance"
            if failure:
                raise PermissionError("private fixture path")
            return []
        finally:
            finished.set()

    operations[stage].side_effect = slow
    def assert_finished():
        assert finished.is_set(), "shutdown stole an in-flight maintenance operation"

    shutdown.side_effect = assert_finished

    async def exercise():
        scope = main._lifespan(main.app)
        await scope.__aenter__()
        closing = None
        try:
            assert await asyncio.to_thread(entered.wait, 10)
            closing = asyncio.create_task(scope.__aexit__(None, None, None))
            # Yield after each cancellation so both reach the actual owner,
            # rather than coalescing before its first suspended await.
            for _ in range(3):
                await asyncio.sleep(0)
                target = main._maintenance_task if cancel_target == "supervisor" else closing
                target.cancel()
            await asyncio.sleep(0)
            assert not closing.done(), "lifespan abandoned its active stage"
            shutdown.assert_not_called()
            assert main._maintenance_checks[stage] == "not_checked"
            assert all(operations[name].call_count == 0 for name in STAGES[STAGES.index(stage) + 1:])
        finally:
            release.set()
            if closing is None:
                await scope.__aexit__(None, None, None)
            else:
                await asyncio.wait_for(closing, 10)
        assert main._maintenance_checks[stage] == ("failed" if failure else "ok")
        assert all(operation.call_count <= 1 for operation in operations.values())
        shutdown.assert_called_once_with()
        assert main._maintenance_task is None

    asyncio.run(exercise())


@pytest.mark.parametrize("failure", [False, True])
def test_real_stop_claim_is_settled_before_shutdown(maintenance_fixture, monkeypatch, failure):
    """Draining must reach the registry/terminal seam, not just an event flag."""
    operations, shutdown = maintenance_fixture
    entered, release = Event(), Event()
    proc = Mock()
    proc.poll.return_value = None

    def wait(timeout=None):
        if not entered.is_set():
            entered.set()
            assert release.wait(15)
            if failure:
                raise PermissionError("first stop denied")
        proc.poll.return_value = 0
        return 0

    proc.wait.side_effect = wait
    handle = runs._Handle(RID, "offline fixture", proc)
    handle.started -= runs.TIMEOUT_SECONDS + 1
    runs._registry[RID] = handle
    monkeypatch.setattr(runs, "reap_timeouts", _REAP_TIMEOUTS)

    def stop_remaining():
        assert not runs._stop_claims, "shutdown raced a still-owned stop"
        assert (RID in runs._registry) is failure
        assert (runs.DEFAULT_OUTPUT_ROOT / RID / "terminal.json").exists() is not failure
        _SHUTDOWN_ALL()

    shutdown.side_effect = stop_remaining

    async def exercise():
        scope = main._lifespan(main.app)
        await scope.__aenter__()
        closing = None
        try:
            assert await asyncio.to_thread(entered.wait, 10)
            closing = asyncio.create_task(scope.__aexit__(None, None, None))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert runs._stop_claims.get(RID) is handle
            assert runs.active_count() == 1
            shutdown.assert_not_called()
        finally:
            release.set()
            if closing is None:
                await scope.__aexit__(None, None, None)
            else:
                await asyncio.wait_for(closing, 10)
        shutdown.assert_called_once_with()
        assert proc.terminate.call_count == (2 if failure else 1)
        assert runs.active_count() == 0
        assert main._maintenance_checks["timeouts"] == ("failed" if failure else "ok")
        operations["papers"].assert_not_called()
        operations["retention"].assert_not_called()
        runs.subprocess.Popen.assert_not_called()

    asyncio.run(exercise())


def test_cancellation_between_cycles_does_not_start_maintenance(maintenance_fixture, monkeypatch):
    """Idle shutdown must not dispatch a cleanup merely to drain the scheduler."""
    operations, shutdown = maintenance_fixture
    monkeypatch.setattr(main, "_REAP_INTERVAL_SECONDS", 3600)

    async def exercise():
        async with main._lifespan(main.app):
            await asyncio.sleep(0)
        assert all(operation.call_count == 0 for operation in operations.values())
        shutdown.assert_called_once_with()

    asyncio.run(exercise())


def test_cycles_remain_serial_and_faults_reach_http(maintenance_fixture):
    """Offloading must not launch a cleanup batch or hide a completed failure."""
    operations, _ = maintenance_fixture
    order = []
    complete = Event()
    count = 0

    def operation(name):
        nonlocal count
        order.append(name)
        count += 1
        if count == 6:
            complete.set()
        if name == "timeouts":
            raise PermissionError("private fixture path")
        return []

    for name in STAGES:
        operations[name].side_effect = lambda name=name, **_kwargs: operation(name)

    async def exercise():
        task = asyncio.create_task(main._reaper())
        main._maintenance_task = task
        try:
            assert await asyncio.to_thread(complete.wait, 10)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
                response = await client.get("/health/ready")
                assert response.status_code == 503
                assert response.json()["checks"]["watchdog"] == "timeout watchdog unavailable"
                assert "private fixture path" not in response.text
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        assert order[:6] == list(STAGES) * 2
        assert order == [STAGES[index % 3] for index in range(len(order))]

    asyncio.run(exercise())
