"""Best-effort cleanup must not hide individual failures at either HTTP seam."""

import asyncio
import contextlib
import os
import shutil
import time
from pathlib import Path
from threading import Event
from unittest.mock import AsyncMock, Mock, patch

import pytest
import httpx
from fastapi.testclient import TestClient

from api import main, papers, runs
from api.models import ReadinessStatus


@pytest.fixture
def cleanup_env(tmp_path, monkeypatch):
    monkeypatch.setattr(papers, "PAPERS_ROOT", tmp_path / "papers")
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path / "runs")
    monkeypatch.setattr(runs, "RUN_RETENTION_DAYS", 30)
    monkeypatch.setattr(runs, "_registry", {})
    monkeypatch.setattr(runs, "_stop_claims", {})
    monkeypatch.setattr(runs, "_inline_paid_operations", {})
    monkeypatch.setattr(main, "_maintenance_task", Mock(done=lambda: False))
    monkeypatch.setattr(main, "_maintenance_checks", dict.fromkeys(("timeouts", "papers", "retention"), "not_checked"))
    monkeypatch.setattr(main, "_maintenance_timings", {})
    monkeypatch.setattr(main, "readiness", lambda: ReadinessStatus(ready=True, checks={}))
    monkeypatch.setattr(runs.subprocess, "Popen", Mock(side_effect=AssertionError("worker launch leaked")))
    return tmp_path


def old_directory(stage, suffix="a"):
    root = papers.PAPERS_ROOT if stage == "papers" else runs.DEFAULT_OUTPUT_ROOT
    name = f"paper-private-{suffix}" if stage == "papers" else f"20200101T000000Z-{suffix * 10}"
    directory = root / name
    directory.mkdir(parents=True)
    os.utime(directory, (time.time() - 172800,) * 2)
    return directory


def cycle():
    """One real serial maintenance cycle, with no live worker or timed waits."""
    async def exercise():
        with patch.object(main.asyncio, "sleep", AsyncMock(side_effect=[None, asyncio.CancelledError()])):
            with pytest.raises(asyncio.CancelledError):
                await main._reaper()
    asyncio.run(exercise())


def read_cleanup(stage):
    snapshots = []
    for route in ("/health", "/health/ready"):
        response = TestClient(main.app).get(route)
        assert response.status_code == 200, "cleanup-only observations must not evict paid workers"
        if route.endswith("ready"):
            assert response.json()["ready"] is True
        snapshots.append(response.json()["maintenance"]["cleanup"][stage])
    assert snapshots[0] == snapshots[1], "cleanup observation lost at the HTTP schema"
    if snapshots[0]["scan_complete"]:
        outcome = snapshots[0]
        assert outcome["scanned"] == outcome["deleted"] + outcome["skipped"] + outcome["failed"]
        assert outcome["skipped"] == sum(outcome["skip_reasons"].values())
        assert outcome["failed"] == sum(outcome["failure_reasons"].values())
    return snapshots[0]


@pytest.mark.parametrize("stage", ["papers", "retention"])
def test_failed_delete_is_visible_while_peer_cleanup_and_next_cycle_continue(cleanup_env, monkeypatch, stage):
    """An undeletable entry returned normally and only exposed a generic ok."""
    blocked = old_directory(stage, "a")
    removed = old_directory(stage, "b")
    original = shutil.rmtree

    def remove(path, *args, **kwargs):
        if path == blocked:
            raise PermissionError("private directory and capability must not reach health")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(shutil, "rmtree", remove)
        cycle()
    assert blocked.exists() and not removed.exists()
    outcome = read_cleanup(stage)
    assert outcome == {
        "state": "partial", "scan_complete": True,
        "scanned": 2, "deleted": 1, "skipped": 0, "failed": 1,
        "skip_reasons": {}, "failure_reasons": {"delete": 1},
    }
    assert main._maintenance_checks["timeouts"] == "ok"
    assert main._maintenance_checks[stage] == "ok", "legacy normal-return status is not deletion completeness"
    assert "private" not in str(outcome) and blocked.name not in str(outcome)
    cycle()
    assert not blocked.exists()
    outcome = read_cleanup(stage)
    assert outcome["state"] == "complete"
    assert outcome["scanned"] == outcome["deleted"] == 1
    assert outcome["failed"] == 0 and outcome["failure_reasons"] == {}


def stage_root(stage):
    return papers.PAPERS_ROOT if stage == "papers" else runs.DEFAULT_OUTPUT_ROOT


@pytest.mark.parametrize("stage", ["papers", "retention"])
@pytest.mark.parametrize("root_kind", ["absent", "empty", "file", "denied"])
def test_no_scan_is_not_an_empty_success(cleanup_env, monkeypatch, stage, root_kind):
    """Missing/denied/file roots used to be indistinguishable from zero removals."""
    root = stage_root(stage)
    original = Path.stat
    if root_kind in {"empty", "denied"}:
        root.mkdir()
    if root_kind == "file":
        root.write_text("not a directory")

    def stat(path, *args, **kwargs):
        if root_kind == "denied" and path == root:
            raise PermissionError("private root")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "stat", stat)
        cycle()
    outcome = read_cleanup(stage)
    if root_kind == "empty":
        assert outcome == {
            "state": "complete", "scan_complete": True,
            "scanned": 0, "deleted": 0, "skipped": 0, "failed": 0,
            "skip_reasons": {}, "failure_reasons": {},
        }
    else:
        assert outcome["state"] == ("absent" if root_kind == "absent" else "unavailable")
        assert all(outcome[key] is None for key in ("scan_complete", "scanned", "deleted", "skipped", "failed"))
    assert main._maintenance_checks["timeouts"] == "ok"
    assert main._maintenance_checks[stage] == ("failed" if root_kind in {"denied", "file"} else "ok")


def test_disabled_retention_does_not_inspect_root(cleanup_env, monkeypatch):
    """A deliberate no-scan policy must not masquerade as empty successful cleanup."""
    monkeypatch.setattr(runs, "RUN_RETENTION_DAYS", 0)
    root = runs.DEFAULT_OUTPUT_ROOT
    original = Path.stat

    def stat(path, *args, **kwargs):
        assert path != root, "disabled retention accessed its root"
        return original(path, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "stat", stat)
        cycle()
    outcome = read_cleanup("retention")
    assert outcome["state"] == "disabled" and outcome["scan_complete"] is None
    assert outcome["scanned"] is outcome["deleted"] is outcome["skipped"] is outcome["failed"] is None


@pytest.mark.parametrize("stage", ["papers", "retention"])
@pytest.mark.parametrize("after_entry", [False, True])
def test_interrupted_listing_preserves_explicit_lower_bound_counts(cleanup_env, monkeypatch, stage, after_entry):
    """An iterator may fail after a deletion; zeroing or completing that scan lies."""
    directory = old_directory(stage)
    root = stage_root(stage)
    original = Path.iterdir

    def listing(path):
        if path == root:
            if after_entry:
                yield directory
            raise PermissionError("private listing")
        yield from original(path)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "iterdir", listing)
        cycle()
    outcome = read_cleanup(stage)
    assert outcome == {
        "state": "unavailable", "scan_complete": False,
        "scanned": int(after_entry), "deleted": int(after_entry), "skipped": 0, "failed": 0,
        "skip_reasons": {}, "failure_reasons": {},
    }
    # failed counts entries with a known failed operation, not an invented
    # directory for a root/iterator fault. Incomplete coverage names that fault.
    assert main._maintenance_checks[stage] == "failed"
    assert directory.exists() is not after_entry
    assert main._maintenance_checks["timeouts"] == "ok"


@pytest.mark.parametrize("stage", ["papers", "retention"])
def test_metadata_failure_is_counted_and_other_entries_are_processed(cleanup_env, monkeypatch, stage):
    """A stat error must not abort peers or become an unrelated skipped entry."""
    denied = old_directory(stage, "a")
    peer = old_directory(stage, "b")
    original = Path.stat

    def stat(path, *args, **kwargs):
        if path == denied:
            raise PermissionError("private metadata")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "stat", stat)
        cycle()
    outcome = read_cleanup(stage)
    assert outcome["state"] == "partial" and outcome["scan_complete"] is True
    assert (outcome["scanned"], outcome["deleted"], outcome["skipped"], outcome["failed"]) == (2, 1, 0, 1)
    assert outcome["failure_reasons"] == {"metadata": 1}
    assert denied.exists() and not peer.exists()


@pytest.mark.parametrize("stage", ["papers", "retention"])
def test_skips_are_not_reported_as_failed_deletions(cleanup_env, stage):
    """Fresh and unrelated entries are intentional retention, not storage faults."""
    old = old_directory(stage)
    root = stage_root(stage)
    fresh = root / ("paper-fresh" if stage == "papers" else "20990101T000000Z-bbbbbbbbbb")
    fresh.mkdir()
    (root / "unrelated.txt").write_text("keep")
    cycle()
    outcome = read_cleanup(stage)
    assert outcome == {
        "state": "complete", "scan_complete": True,
        "scanned": 3, "deleted": 1, "skipped": 2, "failed": 0,
        "skip_reasons": {"fresh": 1, "unrelated": 1}, "failure_reasons": {},
    }
    assert not old.exists() and fresh.exists() and (root / "unrelated.txt").exists()


def test_retention_keeps_a_stop_owned_run_and_names_the_skip(cleanup_env, monkeypatch):
    """Finished-but-owned terminal publication is still a live retention exclusion."""
    directory = old_directory("retention")
    handle = Mock()
    handle.proc.poll.return_value = 0
    monkeypatch.setattr(runs, "_registry", {directory.name: handle})
    monkeypatch.setattr(runs, "_stop_claims", {directory.name: handle})
    with patch.object(runs, "reap_timeouts", return_value=[]):
        cycle()
    outcome = read_cleanup("retention")
    assert outcome["skipped"] == 1 and outcome["skip_reasons"] == {"live": 1}
    assert outcome["failed"] == outcome["deleted"] == 0 and directory.exists()


@pytest.mark.parametrize("stage", ["papers", "retention"])
def test_running_and_cancel_draining_attempt_does_not_publish_tally_early(cleanup_env, monkeypatch, stage):
    """An in-flight mutable tally must not replace the prior completed observation."""
    directory = old_directory(stage)
    with patch.object(shutil, "rmtree", side_effect=PermissionError("denied")):
        cycle()
    before = read_cleanup(stage)
    assert before["failed"] == 1
    entered, release = Event(), Event()
    original = papers.prune_old if stage == "papers" else runs.prune_expired_runs

    def held(*, cleanup):
        result = original(cleanup=cleanup)
        entered.set()
        assert release.wait(15)
        return result

    async def exercise():
        task = asyncio.create_task(main._maintenance_stage(stage, held, collect_cleanup=True))
        try:
            assert await asyncio.to_thread(entered.wait, 10)
            for _ in range(2):
                task.cancel()
                await asyncio.sleep(0)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
                for route in ("/health", "/health/ready"):
                    response = await client.get(route)
                    assert response.status_code == 200
                    snapshot = response.json()["maintenance"]
                    assert snapshot["cleanup"][stage] == before
                    assert snapshot["timings"][stage]["current_started_at"] is not None
        finally:
            release.set()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(task, 10)
    asyncio.run(exercise())
    after = read_cleanup(stage)
    assert after["state"] == "complete" and after["deleted"] == 1 and after["failed"] == 0
    assert not directory.exists()


def test_lifespan_resets_cleanup_and_http_schema_exposes_every_field(cleanup_env, monkeypatch):
    """New lifespans cannot inherit a previous successful/partial cleanup."""
    old_directory("papers")
    cycle()
    assert read_cleanup("papers")["deleted"] == 1
    monkeypatch.setattr(main, "_REAP_INTERVAL_SECONDS", 3600)
    monkeypatch.setattr(runs, "shutdown_all", Mock())
    with TestClient(main.app) as client:
        for route in ("/health", "/health/ready"):
            snapshot = client.get(route).json()["maintenance"]
            assert set(snapshot["cleanup"]) == {"papers", "retention"}
            for outcome in snapshot["cleanup"].values():
                assert outcome["state"] == "not_checked"
                assert all(outcome[key] is None for key in ("scan_complete", "scanned", "deleted", "skipped", "failed"))
        schemas = client.get("/openapi.json").json()["components"]["schemas"]
    assert set(schemas["CleanupSummary"]["properties"]) == set(read_cleanup("papers"))
    assert "cleanup" in schemas["MaintenanceStatus"]["properties"]
