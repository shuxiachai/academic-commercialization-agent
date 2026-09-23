"""Persistent production-only budget and expiry controls; no native dispatch."""

from dataclasses import replace
from decimal import Decimal
import sqlite3
from types import SimpleNamespace

import pytest

from academic_agent.saved_source_usage import OperationContext
from api import saved_source_production_policy as policy
from api.saved_source_receipts import ReceiptError
from tests.test_saved_source_controller import RUN_ID

SETTINGS = policy.Settings(True, True, 2, Decimal("0.03"), Decimal("120"))


def operation(index, now_ms):
    return OperationContext(
        receipt_key_sha256=f"{index:064x}", owner_id="a" * 16,
        intent_fingerprint="b" * 64, run_id=RUN_ID,
        expires_at=now_ms // 1000 + 86400,
        selector_identity_sha256="c" * 64, snapshot_hash="d" * 64, catalog_hash="e" * 64,
    )


@pytest.fixture
def budget(tmp_path, monkeypatch):
    clock = SimpleNamespace(now_ms=2_000_000_000_000)
    monkeypatch.setattr(policy, "time", SimpleNamespace(time_ns=lambda: clock.now_ms * 1_000_000))
    store = policy.ControlStore(tmp_path / "control", SETTINGS)
    store.prepare()
    return store, clock


def test_pruned_spent_day_cannot_reopen_after_clock_rollback(budget):
    """Pruning erased the only later clock fact and reopened a consumed UTC day after restart."""
    store, clock = budget
    store.settings = replace(SETTINGS, daily_request_cap=1)
    first_time = clock.now_ms
    first = operation(1, first_time)
    store.reserve(first)
    clock.now_ms = first.expires_at * 1000 + 1000
    assert store.prune_native() == 1
    # There are no remaining rows to reconstruct an observed clock from.
    with store.database(readonly=True) as db:
        assert db.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == 0
    restarted = policy.ControlStore(store.root, store.settings)
    restarted.prepare()
    clock.now_ms = first_time + 120_000
    with pytest.raises(ReceiptError) as denied:
        restarted.reserve(operation(2, clock.now_ms))
    assert denied.value.code == "execution_unavailable"


def test_cleanup_clock_does_not_restart_admission_interval(budget):
    """Advancing last-admission on every 30s reaper pass starves a valid 120s interval."""
    store, clock = budget
    first_time = clock.now_ms
    store.reserve(operation(1, clock.now_ms))
    for delta in (30_000, 60_000, 90_000):
        clock.now_ms = first_time + delta
        assert store.prune_native() == 0
    clock.now_ms = first_time + 120_000
    store.reserve(operation(2, clock.now_ms))
    with store.database(readonly=True) as db:
        assert db.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == 2


@pytest.mark.parametrize("damage", ["unknown_directory", "unknown_file", "oversize_file"])
def test_native_inventory_fault_preserves_all_expired_rows_and_bytes(budget, damage):
    """An expired row cannot authorize deleting an unrecognized native tree."""
    store, clock = budget
    first = operation(1, clock.now_ms)
    directory = store.reserve(first)
    directory.mkdir()
    manifest = directory / "manifest.json"
    manifest.write_bytes(b"{}")
    if damage == "unknown_directory":
        (directory.parent / "unexpected").mkdir()
    elif damage == "unknown_file":
        (directory / "private-extra.txt").write_bytes(b"keep")
    else:
        manifest.write_bytes(b"x" * (256 * 1024 + 1))
    clock.now_ms = first.expires_at * 1000 + 1000
    with pytest.raises(ReceiptError):
        store.prune_native()
    assert manifest.exists()
    with sqlite3.connect(store.root / policy.FILENAME) as db:
        assert db.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == 1
