"""Non-secret, durable input contract for one assessment run.

The API used to retain the topic in ``status.json`` but not the language,
weight-profile choice, or extracted paper contribution that shaped retrieval.
That was enough to display a failed run and not enough to reproduce it safely.
A recovery process must never guess those missing values: a guess can make an
old checkpoint appear applicable to a different request and skip a paid node.

``RunSpec`` is therefore persisted beside every new run before its worker is
started.  It deliberately contains the extracted paper contribution rather
than the uploaded PDF or a path into the short-lived upload store.  The
contribution is already an input to the pipeline, is bounded JSON, and lets a
child recovery run survive upload pruning without retaining another PDF copy.
Provider credentials are not model fields and Pydantic rejects any extra key,
so BYOK secrets cannot enter this artifact by accident.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


RUN_SPEC_FILENAME = ".run-spec.json"
RESUME_SNAPSHOT_DIRECTORY = ".resume-source"


class RunSpec(BaseModel):
    """Frozen request values needed to repeat or resume a run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    topic: str = Field(min_length=1, max_length=300)
    language: str | None = Field(default=None, max_length=100)
    weight_profile: str | None = Field(default=None, max_length=100)
    paper_contribution: dict[str, Any] | None = None

    @field_validator("topic")
    @classmethod
    def _strip_topic(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("topic must contain at least one non-space character")
        return stripped

    @field_validator("language", "weight_profile")
    @classmethod
    def _normalise_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    def save(self, run_directory: Path | str) -> Path:
        """Atomically publish the spec before a worker can observe the run.

        This is not a cache write: losing it means a failed run cannot be
        resumed safely.  A same-directory replace keeps readers from seeing a
        truncated JSON document if the host dies during publication.
        """

        directory = Path(run_directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / RUN_SPEC_FILENAME
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        payload = (self.model_dump_json(indent=2) + "\n").encode("utf-8")
        try:
            with temporary.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                # The committed spec, or the original publication error, is
                # more useful than a cleanup failure for an unreferenced temp.
                pass
        return path

    @classmethod
    def load(cls, run_directory: Path | str) -> "RunSpec":
        """Load and strictly validate a previously persisted run contract."""

        path = Path(run_directory) / RUN_SPEC_FILENAME
        return cls.model_validate_json(path.read_bytes())
