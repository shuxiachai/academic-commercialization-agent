"""Request and response models for the HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RunState = Literal["running", "completed", "failed", "cancelled", "timeout"]


class RunRequest(BaseModel):
    """Body for POST /api/runs."""

    topic: str = Field(min_length=3, max_length=300, description="Research topic to assess")
    language: str | None = Field(
        default=None,
        description="Force report language (e.g. 'Simplified Chinese'); auto-detected when omitted",
    )
    weight_profile: str | None = Field(
        default=None,
        description="Force scoring profile (industrial | biomedical | material_science "
                    "| clean_tech | software_ai); auto-detected when omitted",
    )


class RunAccepted(BaseModel):
    """Response for a successfully queued run."""

    run_id: str
    state: RunState
    topic: str


class RunStatus(BaseModel):
    """Current state of a run, read from its status.json."""

    run_id: str
    state: RunState
    stage: str = ""
    topic: str = ""
    output_language: str = "English"
    error: str | None = None
    elapsed_seconds: int | None = None
    source_counts: dict[str, int] | None = None
    artifacts: list[str] = Field(
        default_factory=list,
        description="Artifact names available via /api/runs/{run_id}/{name}",
    )


class RunSummary(BaseModel):
    """One entry in the run list."""

    run_id: str
    state: RunState
    topic: str
    started_at: str
    duration: str


class RunList(BaseModel):
    runs: list[RunSummary]
    total: int


class HealthStatus(BaseModel):
    status: Literal["ok"]
    active_runs: int
    max_concurrent: int
    llm_provider: str | None = None
