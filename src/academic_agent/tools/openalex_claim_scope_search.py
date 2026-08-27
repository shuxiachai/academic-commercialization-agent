"""One-request OpenAlex adapter for the disconnected claim-scope study.

The Phase 4 adapter is byte-frozen evidence and intentionally remains
unchanged.  This separate adapter requests OpenAlex topics and keywords and
filters for works with abstracts before ranking consumes the bounded result
slots.  It requires an injected transport, performs exactly one invocation,
and sends no API key.  Production code must not import this module.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from academic_agent.evidence import normalize_doi
from academic_agent.evidence_gap import ValidatedGapCall
from academic_agent.openalex_claim_scope import (
    OpenAlexAboutnessSignal,
    OpenAlexClaimScopeCandidate,
)
from academic_agent.tools.domain_evidence_search import (
    OPENALEX_WORKS_ENDPOINT,
    DomainOneRequestTransport,
)
from academic_agent.tools.evidence_search import (
    ProviderResultRejection,
    ToolAdapterFailure,
    ToolEvidenceCandidate,
    ToolProviderUsage,
)


_OPENALEX_SCOPE_SELECT = ",".join(
    (
        "id",
        "title",
        "doi",
        "publication_date",
        "primary_location",
        "cited_by_count",
        "abstract_inverted_index",
        "topics",
        "keywords",
    )
)
_MIN_SUMMARY_LENGTH = 60


class _OpenAlexMeta(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    cost_usd: float = Field(ge=0.0, allow_inf_nan=False)


class _OpenAlexSource(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    display_name: str = Field(min_length=2, max_length=300)


class _OpenAlexLocation(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    source: _OpenAlexSource | None = None


class _OpenAlexAboutnessRow(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str = Field(min_length=10, max_length=300)
    display_name: str = Field(min_length=2, max_length=300)
    score: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)


class _OpenAlexResult(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str = Field(min_length=10, max_length=300)
    title: str = Field(min_length=5, max_length=600)
    doi: str | None = Field(default=None, max_length=300)
    publication_date: str | None = None
    primary_location: _OpenAlexLocation | None = None
    cited_by_count: int | None = Field(default=None, ge=0)
    abstract_inverted_index: dict[str, tuple[int, ...]] | None = None
    topics: tuple[_OpenAlexAboutnessRow, ...] = Field(default=(), max_length=50)
    keywords: tuple[_OpenAlexAboutnessRow, ...] = Field(default=(), max_length=50)


class _OpenAlexEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    meta: _OpenAlexMeta
    results: tuple[Any, ...] = Field(max_length=10)


class OpenAlexClaimScopeAdapterResponse(BaseModel):
    """One provider request with complete row and aboutness accounting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: Literal["academic_search"] = "academic_search"
    idempotency_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    outbound_request_count: Literal[1] = 1
    candidates: tuple[OpenAlexClaimScopeCandidate, ...] = Field(
        default=(),
        max_length=10,
    )
    provider_rejections: tuple[ProviderResultRejection, ...] = Field(
        default=(),
        max_length=10,
    )
    search_cost_usd: float = Field(ge=0.0, allow_inf_nan=False)
    provider_request_id: str = Field(min_length=3, max_length=300)
    provider_usage: ToolProviderUsage

    @model_validator(mode="after")
    def _validate_complete_accounting(self) -> "OpenAlexClaimScopeAdapterResponse":
        usage = self.provider_usage
        if usage.provider != "openalex":
            raise ValueError("claim-scope adapter requires OpenAlex accounting")
        if self.provider_request_id != usage.request_id:
            raise ValueError("provider request identity drifted from usage")
        if usage.cost_basis != "reported_usd" or usage.reported_cost_usd is None:
            raise ValueError("claim-scope adapter requires reported USD accounting")
        if self.search_cost_usd != usage.reported_cost_usd:
            raise ValueError("search cost drifted from provider accounting")
        if usage.result_count != len(self.candidates) + len(self.provider_rejections):
            raise ValueError("every provider row must be a candidate or rejection")
        candidate_indices = [
            item.evidence.provider_result_index for item in self.candidates
        ]
        if any(index is None for index in candidate_indices):
            raise ValueError("provider candidates require result indices")
        all_indices = [int(index) for index in candidate_indices] + [
            item.provider_result_index for item in self.provider_rejections
        ]
        if sorted(all_indices) != list(range(usage.result_count)):
            raise ValueError("provider result indices must be complete and unique")
        return self


def _validation_detail(exc: ValidationError) -> str:
    details = []
    for error in exc.errors(include_input=False)[:4]:
        location = ".".join(str(part) for part in error["loc"]) or "row"
        details.append(f"{location}:{error['type']}")
    return "; ".join(details)[:500] or "provider row failed schema validation"


def _optional_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        # Date metadata is not the evidence claim.  A formatting quirk must not
        # trigger a hidden enrichment request in a one-request adapter.
        return None


def _openalex_abstract(index: dict[str, tuple[int, ...]] | None) -> str:
    if not index:
        raise ValueError("OpenAlex row has no reconstructable abstract")
    positioned: list[tuple[int, str]] = []
    seen_positions: set[int] = set()
    for token, positions in index.items():
        normalized = " ".join(token.split())
        if not normalized:
            raise ValueError("OpenAlex abstract contains an empty token")
        for position in positions:
            if position < 0 or position > 20_000 or position in seen_positions:
                raise ValueError("OpenAlex abstract positions are invalid")
            seen_positions.add(position)
            positioned.append((position, normalized))
            if len(positioned) > 5_000:
                raise ValueError("OpenAlex abstract exceeds the token safety limit")
    abstract = " ".join(token for _, token in sorted(positioned))[:8000].strip()
    if len(abstract) < _MIN_SUMMARY_LENGTH:
        raise ValueError("OpenAlex abstract is too short for evidence registration")
    return abstract


def _approved_openalex_url(value: str, *, label: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").casefold() != "openalex.org"
    ):
        raise ValueError(f"{label} is not an approved OpenAlex record URL")


def _request_id(call: ValidatedGapCall, request_shape: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        {
            "provider": "openalex-claim-scope",
            "idempotency_key": call.idempotency_key,
            "request": request_shape,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"client-openalex-claim-scope-{digest}"


def _row_rejection(
    index: int,
    raw_result: object,
    exc: ValidationError | ValueError,
) -> ProviderResultRejection:
    raw = raw_result if isinstance(raw_result, dict) else {}
    title = raw.get("title")
    url = raw.get("id")
    return ProviderResultRejection(
        provider_result_index=index,
        code="provider_result_schema_invalid",
        detail=(
            _validation_detail(exc)
            if isinstance(exc, ValidationError)
            else str(exc)[:500] or "provider row failed semantic validation"
        ),
        title=title[:600] if isinstance(title, str) else None,
        url=url[:2000] if isinstance(url, str) else None,
    )


def _aboutness(
    result: _OpenAlexResult,
) -> tuple[OpenAlexAboutnessSignal, ...]:
    signals: list[OpenAlexAboutnessSignal] = []
    for kind, rows in (("topic", result.topics), ("keyword", result.keywords)):
        for row in rows:
            _approved_openalex_url(row.id, label=f"OpenAlex {kind} id")
            signals.append(
                OpenAlexAboutnessSignal(
                    kind=kind,
                    provider_id=row.id,
                    display_name=row.display_name,
                    score=row.score,
                )
            )
    return tuple(signals)


class AnonymousOpenAlexClaimScopeAdapter:
    """Fetch abstract-bearing works and preserve provider semantic metadata."""

    def __init__(
        self,
        *,
        transport: DomainOneRequestTransport,
        timeout: float = 20.0,
    ) -> None:
        if not 0 < timeout <= 60:
            raise ValueError("timeout must be greater than zero and at most 60 seconds")
        self._transport = transport
        self._timeout = timeout

    def __call__(
        self,
        call: ValidatedGapCall,
    ) -> OpenAlexClaimScopeAdapterResponse:
        if call.tool != "academic_search":
            raise ValueError("OpenAlex claim-scope adapter accepts academic_search only")
        request_shape = {
            "search": call.query,
            "filter": "has_abstract:true",
            "per-page": call.result_limit,
            "select": _OPENALEX_SCOPE_SELECT,
        }
        endpoint = f"{OPENALEX_WORKS_ENDPOINT}?{urlencode(request_shape)}"
        request_id = _request_id(call, request_shape)
        try:
            raw_payload = self._transport(
                endpoint=endpoint,
                method="GET",
                body=None,
                headers={"User-Agent": "AcademicAgentClaimScopeStudy/1.0"},
                timeout=self._timeout,
            )
        except HTTPError as exc:
            raise ToolAdapterFailure(
                f"OpenAlex HTTP {exc.code}",
                retryable=exc.code in {408, 429} or 500 <= exc.code < 600,
                failure_type="provider_http",
                search_cost_usd=None,
            ) from None
        except (URLError, TimeoutError, OSError) as exc:
            raise ToolAdapterFailure(
                f"OpenAlex transport failed: {type(exc).__name__}",
                retryable=True,
                failure_type="provider_transport",
                search_cost_usd=None,
            ) from None

        try:
            decoded = json.loads(raw_payload.decode("utf-8"))
            envelope = _OpenAlexEnvelope.model_validate(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
            raise ToolAdapterFailure(
                f"OpenAlex response failed schema validation: {type(exc).__name__}",
                retryable=False,
                failure_type="provider_response_invalid",
                search_cost_usd=None,
            ) from exc
        if len(envelope.results) > call.result_limit:
            raise ToolAdapterFailure(
                "OpenAlex returned more rows than the authorized result limit",
                retryable=False,
                failure_type="provider_result_limit_exceeded",
                search_cost_usd=envelope.meta.cost_usd,
            )

        candidates: list[OpenAlexClaimScopeCandidate] = []
        rejections: list[ProviderResultRejection] = []
        for index, raw_result in enumerate(envelope.results):
            if not isinstance(raw_result, dict):
                rejections.append(
                    ProviderResultRejection(
                        provider_result_index=index,
                        code="provider_result_not_object",
                        detail="provider result must be a JSON object",
                    )
                )
                continue
            try:
                result = _OpenAlexResult.model_validate(raw_result)
                _approved_openalex_url(result.id, label="OpenAlex work id")
                evidence = ToolEvidenceCandidate(
                    title=result.title,
                    url=result.id,
                    doi=normalize_doi(result.doi),
                    publisher=(
                        result.primary_location.source.display_name
                        if result.primary_location is not None
                        and result.primary_location.source is not None
                        else "OpenAlex"
                    ),
                    published_date=_optional_date(result.publication_date),
                    evidence_summary=_openalex_abstract(
                        result.abstract_inverted_index
                    ),
                    summary_source="abstract",
                    citation_count=result.cited_by_count,
                    provider_result_index=index,
                )
                candidates.append(
                    OpenAlexClaimScopeCandidate(
                        evidence=evidence,
                        aboutness=_aboutness(result),
                    )
                )
            except (ValidationError, ValueError) as exc:
                rejections.append(_row_rejection(index, raw_result, exc))

        usage = ToolProviderUsage(
            provider="openalex",
            request_id=request_id,
            request_id_source="client_generated",
            result_count=len(envelope.results),
            cost_basis="reported_usd",
            reported_cost_usd=envelope.meta.cost_usd,
        )
        return OpenAlexClaimScopeAdapterResponse(
            idempotency_key=call.idempotency_key,
            candidates=tuple(candidates),
            provider_rejections=tuple(rejections),
            search_cost_usd=envelope.meta.cost_usd,
            provider_request_id=request_id,
            provider_usage=usage,
        )
