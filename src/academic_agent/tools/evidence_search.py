"""Strict adapter boundary for bounded supplementary evidence search.

The production pipeline does not instantiate these adapters yet. Phase 2
defines the object that a future network adapter must return after exactly one
provider request, so retry and request budgets remain owned by the executor
rather than being hidden inside a client with its own retry loop.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from academic_agent.evidence_gap import GapToolName, ValidatedGapCall


class ToolEvidenceCandidate(BaseModel):
    """Unregistered provider result kept outside the report evidence registry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=5, max_length=600)
    url: str = Field(min_length=3, max_length=2000)
    doi: str | None = Field(default=None, max_length=300)
    publisher: str = Field(min_length=2, max_length=300)
    published_date: date | None = None
    evidence_summary: str = Field(min_length=1, max_length=8000)
    summary_source: Literal["abstract", "search_snippet"]
    citation_count: int | None = Field(default=None, ge=0)

    @field_serializer("published_date")
    def serialize_date(self, value: date | None) -> str | None:
        return value.isoformat() if value is not None else None


class ToolAdapterResponse(BaseModel):
    """One adapter invocation, which must equal one provider request.

    An adapter that follows redirects, fetches result pages, or performs an
    internal retry cannot truthfully emit this shape. Those operations need a
    separately budgeted transport; accepting a client-reported integer greater
    than one and checking only afterwards would discover overspend too late.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: GapToolName
    idempotency_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    outbound_request_count: Literal[1] = 1
    candidates: tuple[ToolEvidenceCandidate, ...] = Field(default=(), max_length=10)
    search_cost_usd: float = Field(default=0.0, ge=0.0)
    provider_request_id: str | None = Field(default=None, max_length=300)


class ToolAdapterFailure(RuntimeError):
    """Structured failure from one request attempt.

    Cost may be unknown after a transport failure. Keeping None distinct from
    zero prevents a failed provider response from being reported as free.
    """

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        failure_type: str,
        search_cost_usd: float | None = None,
    ) -> None:
        super().__init__(message)
        if search_cost_usd is not None and search_cost_usd < 0:
            raise ValueError("search_cost_usd cannot be negative")
        self.retryable = retryable
        self.failure_type = failure_type
        self.search_cost_usd = search_cost_usd


class ReadOnlySearchAdapter(Protocol):
    """A capability adapter that performs exactly one outbound request."""

    def __call__(
        self,
        call: ValidatedGapCall,
    ) -> ToolAdapterResponse | dict[str, Any]: ...
