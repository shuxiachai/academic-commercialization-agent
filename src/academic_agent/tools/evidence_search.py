"""Strict adapter boundary for bounded supplementary evidence search.

The production pipeline does not instantiate these adapters yet. Phase 2
defines the object that a future network adapter must return after exactly one
provider request, so retry and request budgets remain owned by the executor
rather than being hidden inside a client with its own retry loop.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    model_validator,
)

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
    # A provider index is evidence-lineage metadata, not a source identifier.
    # Keeping it optional preserves the phase-2 fixture contract while letting
    # a live adapter prove which provider row survived schema validation.
    provider_result_index: int | None = Field(default=None, ge=0)

    @field_serializer("published_date")
    def serialize_date(self, value: date | None) -> str | None:
        return value.isoformat() if value is not None else None


ProviderResultRejectionCode = Literal[
    "provider_result_not_object",
    "provider_result_schema_invalid",
]


class ProviderResultRejection(BaseModel):
    """A provider row rejected before it could become a tool candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_result_index: int = Field(ge=0)
    code: ProviderResultRejectionCode
    detail: str = Field(min_length=1, max_length=500)
    title: str | None = Field(default=None, max_length=600)
    url: str | None = Field(default=None, max_length=2000)


class ToolProviderUsage(BaseModel):
    """Provider-owned request identity and conservative credit accounting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["tavily"]
    request_id: str = Field(min_length=3, max_length=300)
    result_count: int = Field(ge=0, le=20)
    credit_count: float = Field(ge=0.0, allow_inf_nan=False)
    usd_per_credit: float = Field(ge=0.0, allow_inf_nan=False)


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
    search_cost_usd: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    provider_request_id: str | None = Field(default=None, max_length=300)
    provider_usage: ToolProviderUsage | None = None
    provider_rejections: tuple[ProviderResultRejection, ...] = Field(
        default=(),
        max_length=20,
    )

    @model_validator(mode="after")
    def _validate_provider_accounting(self) -> "ToolAdapterResponse":
        if self.provider_usage is None:
            if self.provider_rejections:
                raise ValueError(
                    "provider rejections require provider usage accounting"
                )
            return self

        usage = self.provider_usage
        if self.provider_request_id != usage.request_id:
            raise ValueError(
                "provider_request_id must match provider usage identity"
            )
        if usage.result_count != len(self.candidates) + len(
            self.provider_rejections
        ):
            raise ValueError(
                "provider result count must cover candidates and rejections"
            )
        candidate_indices = [
            candidate.provider_result_index for candidate in self.candidates
        ]
        if any(index is None for index in candidate_indices):
            raise ValueError(
                "provider-accounted candidates require provider result indices"
            )
        all_indices = [
            int(index) for index in candidate_indices if index is not None
        ] + [
            rejection.provider_result_index
            for rejection in self.provider_rejections
        ]
        if sorted(all_indices) != list(range(usage.result_count)):
            raise ValueError(
                "provider result indices must cover every returned row once"
            )
        expected_cost = usage.credit_count * usage.usd_per_credit
        if not math.isclose(
            self.search_cost_usd,
            expected_cost,
            rel_tol=1e-9,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "search cost must equal provider credits times unit cost"
            )
        return self


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
        if search_cost_usd is not None and (
            not math.isfinite(search_cost_usd) or search_cost_usd < 0
        ):
            raise ValueError("search_cost_usd must be finite and non-negative")
        self.retryable = retryable
        self.failure_type = failure_type
        self.search_cost_usd = search_cost_usd


class ReadOnlySearchAdapter(Protocol):
    """A capability adapter that performs exactly one outbound request."""

    def __call__(
        self,
        call: ValidatedGapCall,
    ) -> ToolAdapterResponse | dict[str, Any]: ...
