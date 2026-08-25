"""One-request Tavily adapter for the production-disconnected gap experiment.

The adapter deliberately owns no retry loop, redirect following, result-page
fetch, or evidence registration. The phase-2 executor owns retry budgets and
the existing deterministic quarantine owns trust decisions; hiding either
inside this provider client would make request and evidence accounting false.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from datetime import date
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from academic_agent.evidence import normalize_doi
from academic_agent.evidence_gap import GapToolName, ValidatedGapCall
from academic_agent.source_pipeline import (
    _AUTHORITATIVE_RESEARCH_DOMAINS,
    _CLINICAL_REGISTRY_DOMAINS,
    _CONSULTING_RESEARCH_DOMAINS,
    _INDUSTRY_NEWS_DOMAINS,
    _MARKET_RESEARCH_DOMAINS,
    _NONPROFIT_RESEARCH_DOMAINS,
    _PATENT_HOSTS,
    _PRESS_RELEASE_DOMAINS,
    _REGULATORY_AUTHORITY_DOMAINS,
    _REPUTABLE_NEWS_DOMAINS,
    _STANDARDS_BODY_DOMAINS,
    _THINK_TANK_DOMAINS,
)
from academic_agent.tools.evidence_search import (
    ProviderResultRejection,
    ToolAdapterFailure,
    ToolAdapterResponse,
    ToolEvidenceCandidate,
    ToolProviderUsage,
)


TAVILY_SEARCH_ENDPOINT = "https://api.tavily.com/search"
TAVILY_BASIC_USD_PER_CREDIT = 0.008
_ACADEMIC_RECORD_DOMAINS = frozenset(
    {
        "arxiv.org",
        "doi.org",
        "ncbi.nlm.nih.gov",
        "openalex.org",
        "pubmed.ncbi.nlm.nih.gov",
        "semanticscholar.org",
    }
)
_MARKET_DOMAINS = frozenset().union(
    _AUTHORITATIVE_RESEARCH_DOMAINS,
    _CONSULTING_RESEARCH_DOMAINS,
    _INDUSTRY_NEWS_DOMAINS,
    _MARKET_RESEARCH_DOMAINS,
    _NONPROFIT_RESEARCH_DOMAINS,
    _PRESS_RELEASE_DOMAINS,
    _REPUTABLE_NEWS_DOMAINS,
    _STANDARDS_BODY_DOMAINS,
    _THINK_TANK_DOMAINS,
)
_INCLUDE_DOMAINS: Mapping[GapToolName, tuple[str, ...]] = {
    "academic_search": tuple(sorted(_ACADEMIC_RECORD_DOMAINS)),
    "patent_search": tuple(sorted(_PATENT_HOSTS)),
    "market_search": tuple(sorted(_MARKET_DOMAINS)),
    "authority_search": tuple(
        sorted(_REGULATORY_AUTHORITY_DOMAINS | _CLINICAL_REGISTRY_DOMAINS)
    ),
}


class TavilyOneRequestTransport(Protocol):
    """Injected transport whose one invocation equals one outbound request."""

    def __call__(
        self,
        *,
        endpoint: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout: float,
    ) -> bytes: ...


class _NoRedirectHandler(HTTPRedirectHandler):
    """Turn every redirect into HTTPError instead of an uncounted request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        del req, fp, code, msg, headers, newurl
        return None


class _UrllibOneRequestTransport:
    """Default transport with no redirect or retry behavior."""

    def __call__(
        self,
        *,
        endpoint: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout: float,
    ) -> bytes:
        request = Request(
            endpoint,
            data=body,
            headers=dict(headers),
            method="POST",
        )
        opener = build_opener(_NoRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            return response.read()


class _TavilyUsage(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    credits: float = Field(ge=0.0, allow_inf_nan=False)


class _TavilyEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    request_id: str = Field(min_length=3, max_length=300)
    results: tuple[Any, ...] = Field(max_length=20)
    usage: _TavilyUsage


class _TavilyResult(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    title: str = Field(min_length=5, max_length=600)
    url: str = Field(min_length=3, max_length=2000)
    content: str = Field(min_length=1)
    published_date: str | None = None


def _validation_detail(exc: ValidationError) -> str:
    """Describe schema failures without copying untrusted provider content."""

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
        # Date is optional provider metadata. Rejecting an otherwise auditable
        # record over a malformed date would reduce evidence without improving
        # URL, source, or topic precision.
        return None


def _doi_from_url(value: str) -> str | None:
    parsed = urlsplit(value)
    if (parsed.hostname or "").removeprefix("www.").casefold() != "doi.org":
        return None
    return normalize_doi(parsed.path.lstrip("/"))


class TavilyEvidenceSearchAdapter:
    """Convert one Tavily response into unregistered evidence candidates."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = 20.0,
        usd_per_credit: float = TAVILY_BASIC_USD_PER_CREDIT,
        transport: TavilyOneRequestTransport | None = None,
    ) -> None:
        resolved_key = (api_key or os.getenv("TAVILY_API_KEY") or "").strip()
        if not resolved_key:
            raise ValueError("TAVILY_API_KEY is required for the live adapter")
        if not 0 < timeout <= 60:
            raise ValueError("timeout must be greater than zero and at most 60 seconds")
        # Validate the accounting rate before constructing any paid request.
        # Letting NaN or infinity reach the response boundary would turn a
        # configuration error into an uninspectable cost only after billing.
        if not math.isfinite(usd_per_credit) or usd_per_credit < 0:
            raise ValueError("usd_per_credit must be finite and non-negative")
        self._api_key = resolved_key
        self._timeout = timeout
        self._usd_per_credit = usd_per_credit
        self._transport = transport or _UrllibOneRequestTransport()

    def __call__(self, call: ValidatedGapCall) -> ToolAdapterResponse:
        """Perform exactly one provider request and preserve every result row."""

        body = json.dumps(
            {
                "query": call.query,
                "search_depth": "basic",
                "auto_parameters": False,
                "include_answer": False,
                "include_raw_content": False,
                "include_images": False,
                "include_usage": True,
                "max_results": call.result_limit,
                "include_domains": list(_INCLUDE_DOMAINS[call.tool]),
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        try:
            raw_payload = self._transport(
                endpoint=TAVILY_SEARCH_ENDPOINT,
                body=body,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "AcademicAgentEvidenceGap/1.0",
                },
                timeout=self._timeout,
            )
        except HTTPError as exc:
            is_redirect = 300 <= exc.code < 400
            raise ToolAdapterFailure(
                f"Tavily HTTP {exc.code}",
                retryable=exc.code in {408, 429} or 500 <= exc.code < 600,
                failure_type=("provider_redirect" if is_redirect else "provider_http"),
                search_cost_usd=None,
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ToolAdapterFailure(
                f"Tavily transport failed: {type(exc).__name__}",
                retryable=True,
                failure_type="provider_transport",
                search_cost_usd=None,
            ) from exc

        try:
            decoded = json.loads(raw_payload.decode("utf-8"))
            envelope = _TavilyEnvelope.model_validate(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
            raise ToolAdapterFailure(
                f"Tavily response failed schema validation: {type(exc).__name__}",
                retryable=False,
                failure_type="provider_response_invalid",
                search_cost_usd=None,
            ) from exc

        cost = envelope.usage.credits * self._usd_per_credit
        if len(envelope.results) > call.result_limit:
            raise ToolAdapterFailure(
                "Tavily returned more rows than the authorized result limit",
                retryable=False,
                failure_type="provider_result_limit_exceeded",
                search_cost_usd=cost,
            )

        candidates: list[ToolEvidenceCandidate] = []
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
                result = _TavilyResult.model_validate(raw_result)
                host = (urlsplit(result.url).hostname or "").removeprefix("www.")
                candidates.append(
                    ToolEvidenceCandidate(
                        title=result.title,
                        url=result.url,
                        doi=_doi_from_url(result.url),
                        publisher=host,
                        published_date=_optional_date(result.published_date),
                        evidence_summary=result.content[:8000],
                        summary_source="search_snippet",
                        provider_result_index=index,
                    )
                )
            except (ValidationError, ValueError) as exc:
                detail = (
                    _validation_detail(exc)
                    if isinstance(exc, ValidationError)
                    else f"provider row URL parsing failed: {type(exc).__name__}"
                )
                rejections.append(
                    ProviderResultRejection(
                        provider_result_index=index,
                        code="provider_result_schema_invalid",
                        detail=detail,
                        title=(
                            raw_result.get("title")[:600]
                            if isinstance(raw_result.get("title"), str)
                            else None
                        ),
                        url=(
                            raw_result.get("url")[:2000]
                            if isinstance(raw_result.get("url"), str)
                            else None
                        ),
                    )
                )

        usage = ToolProviderUsage(
            provider="tavily",
            request_id=envelope.request_id,
            result_count=len(envelope.results),
            credit_count=envelope.usage.credits,
            usd_per_credit=self._usd_per_credit,
        )
        return ToolAdapterResponse(
            tool=call.tool,
            idempotency_key=call.idempotency_key,
            candidates=tuple(candidates),
            search_cost_usd=cost,
            provider_request_id=envelope.request_id,
            provider_usage=usage,
            provider_rejections=tuple(rejections),
        )
