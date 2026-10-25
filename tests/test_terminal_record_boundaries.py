"""The immutable terminal record at its validation and publication edges."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from academic_agent.run_terminal import (
    TerminalRecord, TerminalRecordUnreadable, UsageAccounting, commit_terminal_record, load_terminal_record,
)

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


def _accounting(**overrides) -> UsageAccounting:
    fields = dict(state="unavailable", snapshot_at=NOW, run_complete=False, in_flight_request_may_have_spent=False)
    fields.update(overrides)
    return UsageAccounting(**fields)


def _record(**overrides) -> TerminalRecord:
    fields = dict(state="failed", reason_code="worker_error", termination_method="worker_exit",
                  started_at=NOW, ended_at=NOW + timedelta(seconds=5), elapsed_seconds=5,
                  usage_accounting=_accounting())
    fields.update(overrides)
    return TerminalRecord(**fields)


def test_timestamps_without_a_timezone_are_refused_everywhere():
    naive = NOW.replace(tzinfo=None)
    with pytest.raises(ValidationError):
        _accounting(snapshot_at=naive)
    with pytest.raises(ValidationError):
        _record(started_at=naive)
    with pytest.raises(ValidationError):
        _record(ended_at=naive)


def test_accounting_state_must_agree_with_whether_the_run_completed():
    with pytest.raises(ValidationError):
        _accounting(state="lower_bound", run_complete=True)
    with pytest.raises(ValidationError):
        _accounting(state="complete", run_complete=True, in_flight_request_may_have_spent=True)
    assert _accounting(state="lower_bound", run_complete=False).state == "lower_bound"
    assert _accounting(state="unavailable", run_complete=True).state == "unavailable"


def test_an_end_before_the_start_is_refused_but_a_zero_length_run_is_not():
    with pytest.raises(ValidationError):
        _record(ended_at=NOW - timedelta(seconds=1))
    assert _record(ended_at=NOW, elapsed_seconds=0).elapsed_seconds == 0
    with pytest.raises(ValidationError):
        _record(elapsed_seconds=-1)
    with pytest.raises(ValidationError):
        _record(timeout_seconds=0)


def test_an_unreadable_terminal_file_is_reported_not_treated_as_absent(tmp_path: Path):
    assert load_terminal_record(tmp_path) is None
    commit_terminal_record(tmp_path, _record())
    with patch.object(Path, "read_bytes", side_effect=PermissionError("locked")):
        with pytest.raises(TerminalRecordUnreadable):
            load_terminal_record(tmp_path)
    assert load_terminal_record(tmp_path) == _record()


def test_a_failed_cleanup_of_the_temporary_file_does_not_undo_the_commit(tmp_path: Path):
    with patch.object(Path, "unlink", side_effect=OSError("busy")):
        path = commit_terminal_record(tmp_path, _record())
    assert path.exists()
    assert load_terminal_record(tmp_path) == _record()
