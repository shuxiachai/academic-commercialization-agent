"""Tests for the immutable process-outcome record.

``status.json`` is a mutable progress projection. A parent-enforced timeout
stops the only process that normally rewrites it, so its mtime and last stage
cannot establish the actual end time or whether usage is complete. The
terminal record is the write-once join between worker and API ownership.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from academic_agent.run_terminal import (
    TerminalRecord,
    TerminalRecordUnreadable,
    UsageAccounting,
    commit_terminal_record,
    load_terminal_record,
)


_START = datetime(2026, 9, 4, 1, 0, tzinfo=UTC)


def _record(*, state: str = "completed", reason: str = "worker_completed") -> TerminalRecord:
    usage = {"total_tokens": 12, "total_requests": 1, "cost_usd": 0.001}
    return TerminalRecord(
        state=state,
        reason_code=reason,
        termination_method="worker_exit" if state in {"completed", "failed"} else "terminate",
        started_at=_START,
        ended_at=_START + timedelta(seconds=17),
        elapsed_seconds=17,
        last_stage="Done" if state == "completed" else "Reviewer",
        timeout_seconds=1_800,
        usage=usage,
        usage_accounting=UsageAccounting(
            state="complete" if state == "completed" else "lower_bound",
            snapshot_at=_START + timedelta(seconds=17),
            through_stage="Done" if state == "completed" else "Reviewer",
            run_complete=state == "completed",
            in_flight_request_may_have_spent=state != "completed",
        ),
        checkpointing={"state": "complete", "committed_nodes": ["retrieval"]},
        recovery={"state": "not_requested"},
    )


def test_commit_is_atomic_loadable_and_idempotent(tmp_path: Path) -> None:
    record = _record()

    first = commit_terminal_record(tmp_path, record)
    second = commit_terminal_record(tmp_path, record)

    assert first == second
    assert load_terminal_record(tmp_path) == record
    assert list(tmp_path.glob("*.tmp")) == []


def test_conflicting_second_outcome_cannot_rewrite_history(tmp_path: Path) -> None:
    original = _record()
    commit_terminal_record(tmp_path, original)

    with pytest.raises(FileExistsError, match="conflicting"):
        commit_terminal_record(
            tmp_path,
            _record(state="failed", reason="worker_exception"),
        )

    assert load_terminal_record(tmp_path) == original


def test_invalid_existing_record_is_unreadable_not_absent(tmp_path: Path) -> None:
    (tmp_path / "terminal.json").write_text("{broken", encoding="utf-8")

    with pytest.raises(TerminalRecordUnreadable):
        load_terminal_record(tmp_path)


def test_public_projection_does_not_duplicate_mutable_payloads() -> None:
    projection = _record().public_projection()

    assert projection["record_state"] == "committed"
    assert projection["elapsed_seconds"] == 17
    assert "usage" not in projection
    assert "checkpointing" not in projection


def test_complete_accounting_requires_a_completed_run() -> None:
    with pytest.raises(ValueError, match="completed run"):
        UsageAccounting(
            state="complete",
            snapshot_at=_START,
            through_stage="Reviewer",
            run_complete=False,
            in_flight_request_may_have_spent=False,
        )


def test_complete_accounting_requires_an_explicit_usage_snapshot() -> None:
    accounting = UsageAccounting(
        state="complete",
        snapshot_at=_START,
        through_stage="Done",
        run_complete=True,
        in_flight_request_may_have_spent=False,
    )

    with pytest.raises(ValueError, match="usage snapshot"):
        TerminalRecord(
            state="completed",
            reason_code="worker_completed",
            termination_method="worker_exit",
            started_at=_START,
            ended_at=_START,
            elapsed_seconds=0,
            last_stage="Done",
            usage=None,
            usage_accounting=accounting,
        )
