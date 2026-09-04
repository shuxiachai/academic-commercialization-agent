"""Durable terminal facts for one assessment process.

``status.json`` is a live projection and is intentionally rewritten at every
stage.  It cannot be the authoritative end record for a process killed by the
API: the worker that owns the file is exactly the process that no longer gets
to write it.  ``terminal.json`` is the smaller immutable contract shared by
both writers.  A worker commits it after its final status write; the API
commits it only after a timeout or cancellation has stopped the worker.

The record does not claim exactly-once provider accounting.  A process can be
terminated after a provider accepted a request but before the SDK exposed its
usage.  ``usage_accounting`` therefore distinguishes a complete total, a
durable lower bound, and an unavailable measurement instead of presenting a
partial number as the bill.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


TERMINAL_FILENAME = "terminal.json"

TerminalState = Literal["completed", "failed", "cancelled", "timeout"]
TerminationMethod = Literal["worker_exit", "terminate", "kill", "already_exited"]
UsageAccountingState = Literal["complete", "lower_bound", "unavailable"]


class TerminalRecordUnreadable(OSError):
    """The terminal file exists but cannot be parsed as the frozen contract."""


class UsageAccounting(BaseModel):
    """How much confidence a reader may place in the adjacent usage snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: UsageAccountingState
    snapshot_at: datetime
    through_stage: str = Field(default="", max_length=300)
    run_complete: bool
    in_flight_request_may_have_spent: bool

    @field_validator("snapshot_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("snapshot_at must include a timezone")
        return value

    @model_validator(mode="after")
    def _state_matches_completion(self) -> "UsageAccounting":
        if self.state == "complete" and not self.run_complete:
            raise ValueError("complete accounting requires a completed run")
        if self.state == "lower_bound" and self.run_complete:
            raise ValueError("a completed run cannot have lower-bound accounting")
        if self.state == "complete" and self.in_flight_request_may_have_spent:
            raise ValueError("complete accounting cannot have an in-flight request")
        return self


class TerminalRecord(BaseModel):
    """Immutable process outcome written once after execution has stopped."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    state: TerminalState
    reason_code: str = Field(min_length=1, max_length=100)
    termination_method: TerminationMethod
    started_at: datetime
    ended_at: datetime
    elapsed_seconds: int = Field(ge=0)
    last_stage: str = Field(default="", max_length=300)
    timeout_seconds: int | None = Field(default=None, gt=0)
    usage: dict[str, Any] | None = None
    usage_accounting: UsageAccounting
    checkpointing: dict[str, Any] | None = None
    recovery: dict[str, Any] | None = None

    @field_validator("started_at", "ended_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("terminal timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def _end_cannot_precede_start(self) -> "TerminalRecord":
        if self.ended_at < self.started_at:
            raise ValueError("ended_at cannot precede started_at")
        if self.usage_accounting.state == "complete" and self.usage is None:
            # A completed zero-call workflow still needs an explicit zero
            # snapshot.  None means accounting could not run, not zero spend.
            raise ValueError("complete accounting requires a usage snapshot")
        return self

    def public_projection(self) -> dict[str, Any]:
        """Process metadata safe for both capability-based read endpoints.

        Usage, checkpoint and recovery data already have top-level response
        fields.  Repeating them here creates two client paths that can drift,
        so the nested projection contains only terminal-process facts.
        """

        return {
            "record_state": "committed",
            "schema_version": self.schema_version,
            "state": self.state,
            "reason_code": self.reason_code,
            "termination_method": self.termination_method,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "elapsed_seconds": self.elapsed_seconds,
            "last_stage": self.last_stage,
            "timeout_seconds": self.timeout_seconds,
        }


def load_terminal_record(run_directory: Path | str) -> TerminalRecord | None:
    """Load the terminal record, returning None only when it was never written."""

    path = Path(run_directory) / TERMINAL_FILENAME
    try:
        payload = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise TerminalRecordUnreadable(str(path)) from exc
    try:
        return TerminalRecord.model_validate_json(payload)
    except ValueError as exc:
        raise TerminalRecordUnreadable(f"{path}: invalid terminal record") from exc


def commit_terminal_record(
    run_directory: Path | str,
    record: TerminalRecord,
) -> Path:
    """Atomically publish one immutable terminal record.

    The lifecycle serializes the two possible writers: the worker writes only
    while it owns execution; the API waits for that process to stop before it
    writes.  A pre-existing byte-identical record is idempotent.  A conflicting
    record is never replaced, because doing so would turn a race into a false
    history rather than making the race visible.
    """

    directory = Path(run_directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / TERMINAL_FILENAME
    payload = (record.model_dump_json(indent=2) + "\n").encode("utf-8")

    try:
        existing = path.read_bytes()
    except FileNotFoundError:
        existing = None
    if existing is not None:
        try:
            current = TerminalRecord.model_validate_json(existing)
        except ValueError as exc:
            raise TerminalRecordUnreadable(
                f"{path}: existing terminal record is invalid"
            ) from exc
        if current == record:
            return path
        raise FileExistsError(f"conflicting terminal record already exists: {path}")

    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # os.replace gives readers an all-or-nothing JSON document.  The
        # lifecycle ordering above, rather than this replace alone, prevents a
        # second writer from intentionally overwriting an existing outcome.
        if path.exists():
            return commit_terminal_record(directory, record)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            # Preserve the publication error; this file is unreferenced and a
            # cleanup failure says nothing about the committed outcome.
            pass
    return path
