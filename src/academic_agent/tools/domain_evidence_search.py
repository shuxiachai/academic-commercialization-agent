"""Source-native one-request adapters for the disconnected Phase 4 audit.

These adapters are deliberately not factories for the production worker. They
translate one already validated gap call into one provider request, preserve
every returned row, and hand candidates back to the existing quarantine. The
executor owns retry policy; adding a retry, redirect follow, patent-page fetch,
or abstract fetch here would make its two-request budget untrue.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import date
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from academic_agent.evidence import normalize_doi
from academic_agent.evidence_gap import ValidatedGapCall
from academic_agent.tools.evidence_search import (
    ProviderResultRejection,
    ToolAdapterFailure,
    ToolAdapterResponse,
    ToolEvidenceCandidate,
    ToolProviderUsage,
)


OPENALEX_WORKS_ENDPOINT = "https://api.openalex.org/works"
LENS_PATENT_SEARCH_ENDPOINT = "https://api.lens.org/patent/search"
_OPENALEX_SELECT = ",".join(
    (
        "id",
        "title",
        "doi",
        "publication_date",
        "primary_location",
        "cited_by_count",
        "abstract_inverted_index",
    )
)
_MIN_SUMMARY_LENGTH = 60


class DomainOneRequestTransport(Protocol):
    """Injected transport whose one invocation equals one outbound request."""

    def __call__(
        self,
        *,
        endpoint: str,
        method: str,
        body: bytes | None,
        headers: Mapping[str, str],
        timeout: float,
    ) -> bytes: ...


class _NoRedirectHandler(HTTPRedirectHandler):
    """Turn redirects into HTTPError instead of silently spending a request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        del req, fp, code, msg, headers, newurl
        return None


class _UrllibOneRequestTransport:
    """Default transport with no redirect or retry behavior."""

    def __call__(
        self,
        *,
        endpoint: str,
        method: str,
        body: bytes | None,
        headers: Mapping[str, str],
        timeout: float,
    ) -> bytes:
        request = Request(
            endpoint,
            data=body,
            headers=dict(headers),
            method=method,
        )
        opener = build_opener(_NoRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            return response.read()


class _OpenAlexMeta(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    cost_usd: float = Field(ge=0.0, allow_inf_nan=False)


class _OpenAlexSource(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    display_name: str = Field(min_length=2, max_length=300)


class _OpenAlexLocation(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    source: _OpenAlexSource | None = None


class _OpenAlexEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    meta: _OpenAlexMeta
    results: tuple[Any, ...] = Field(max_length=20)


class _OpenAlexResult(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str = Field(min_length=10, max_length=300)
    title: str = Field(min_length=5, max_length=600)
    doi: str | None = Field(default=None, max_length=300)
    publication_date: str | None = None
    primary_location: _OpenAlexLocation | None = None
    cited_by_count: int | None = Field(default=None, ge=0)
    abstract_inverted_index: dict[str, tuple[int, ...]] | None = None


class _LensLocalizedText(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    text: str = Field(min_length=1, max_length=20_000)
    lang: str | None = Field(default=None, max_length=20)


class _LensPublicationReference(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    jurisdiction: str | None = Field(default=None, max_length=50)
    date: str | None = Field(default=None, max_length=40)


class _LensBiblio(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    invention_title: tuple[_LensLocalizedText, ...] = Field(default=(), max_length=20)
    publication_reference: _LensPublicationReference | None = None


class _LensEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    total: int = Field(ge=0)
    data: tuple[Any, ...] = Field(max_length=20)


class _LensResult(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    lens_id: str = Field(min_length=3, max_length=300)
    biblio: _LensBiblio
    abstract: tuple[_LensLocalizedText, ...] = Field(default=(), max_length=20)
    jurisdiction: str | None = Field(default=None, max_length=50)


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
        # Publication date is metadata, not the evidence claim. Keeping a row
        # without it is safer than turning a provider formatting quirk into a
        # hidden second request for enrichment.
        return None


def _client_request_id(
    provider: str,
    call: ValidatedGapCall,
    request_shape: Mapping[str, Any],
) -> str:
    """Create a secret-independent local identity when the API returns none."""

    canonical = json.dumps(
        {
            "provider": provider,
            "idempotency_key": call.idempotency_key,
            "request": request_shape,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"client-{provider}-{digest}"


def _http_failure(provider: str, exc: HTTPError) -> ToolAdapterFailure:
    is_redirect = 300 <= exc.code < 400
    return ToolAdapterFailure(
        f"{provider} HTTP {exc.code}",
        retryable=exc.code in {408, 429} or 500 <= exc.code < 600,
        failure_type="provider_redirect" if is_redirect else "provider_http",
        search_cost_usd=None,
    )


def _transport_failure(provider: str, exc: BaseException) -> ToolAdapterFailure:
    return ToolAdapterFailure(
        f"{provider} transport failed: {type(exc).__name__}",
        retryable=True,
        failure_type="provider_transport",
        search_cost_usd=None,
    )


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


def _localized_text(values: tuple[_LensLocalizedText, ...], *, field: str) -> str:
    if not values:
        raise ValueError(f"Lens row has no {field}")
    selected = next(
        (
            value
            for value in values
            if (value.lang or "").casefold().startswith("en")
        ),
        values[0],
    )
    text = " ".join(selected.text.split()).strip()
    if field == "abstract" and len(text) < _MIN_SUMMARY_LENGTH:
        raise ValueError("Lens abstract is too short for evidence registration")
    return text[:8000]


class OpenAlexEvidenceSearchAdapter:
    """Convert one OpenAlex Works response into quarantined candidates."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = 20.0,
        transport: DomainOneRequestTransport | None = None,
    ) -> None:
        resolved_key = (api_key or os.getenv("OPENALEX_API_KEY") or "").strip()
        if not resolved_key:
            raise ValueError("OPENALEX_API_KEY is required for the live adapter")
        if not 0 < timeout <= 60:
            raise ValueError("timeout must be greater than zero and at most 60 seconds")
        self._api_key = resolved_key
        self._timeout = timeout
        self._transport = transport or _UrllibOneRequestTransport()

    def __call__(self, call: ValidatedGapCall) -> ToolAdapterResponse:
        if call.tool != "academic_search":
            raise ValueError("OpenAlex adapter accepts only academic_search calls")
        request_shape = {
            "search": call.query,
            "per-page": call.result_limit,
            "select": _OPENALEX_SELECT,
        }
        endpoint = f"{OPENALEX_WORKS_ENDPOINT}?{urlencode({**request_shape, 'api_key': self._api_key})}"
        request_id = _client_request_id("openalex", call, request_shape)
        try:
            raw_payload = self._transport(
                endpoint=endpoint,
                method="GET",
                body=None,
                headers={"User-Agent": "AcademicAgentEvidenceGap/1.0"},
                timeout=self._timeout,
            )
        except HTTPError as exc:
            # OpenAlex requires the key in the URL query. urllib exceptions
            # may retain that URL, so chaining the provider exception would
            # leak the credential through an otherwise sanitized traceback.
            raise _http_failure("OpenAlex", exc) from None
        except (URLError, TimeoutError, OSError) as exc:
            raise _transport_failure("OpenAlex", exc) from None

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

        cost = envelope.meta.cost_usd
        if len(envelope.results) > call.result_limit:
            raise ToolAdapterFailure(
                "OpenAlex returned more rows than the authorized result limit",
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
                result = _OpenAlexResult.model_validate(raw_result)
                parsed = urlsplit(result.id)
                if (
                    parsed.scheme != "https"
                    or (parsed.hostname or "").casefold() != "openalex.org"
                ):
                    raise ValueError("OpenAlex work id is not an approved record URL")
                candidates.append(
                    ToolEvidenceCandidate(
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
                )
            except (ValidationError, ValueError) as exc:
                rejections.append(_row_rejection(index, raw_result, exc))

        usage = ToolProviderUsage(
            provider="openalex",
            request_id=request_id,
            request_id_source="client_generated",
            result_count=len(envelope.results),
            cost_basis="reported_usd",
            reported_cost_usd=cost,
        )
        return ToolAdapterResponse(
            tool=call.tool,
            idempotency_key=call.idempotency_key,
            candidates=tuple(candidates),
            search_cost_usd=cost,
            provider_request_id=request_id,
            provider_usage=usage,
            provider_rejections=tuple(rejections),
        )


class LensEvidenceSearchAdapter:
    """Convert one claim-oriented Lens response into quarantined candidates."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = 25.0,
        transport: DomainOneRequestTransport | None = None,
    ) -> None:
        resolved_key = (api_key or os.getenv("LENS_API_KEY") or "").strip()
        if not resolved_key:
            raise ValueError("LENS_API_KEY is required for the live adapter")
        if not 0 < timeout <= 60:
            raise ValueError("timeout must be greater than zero and at most 60 seconds")
        self._api_key = resolved_key
        self._timeout = timeout
        self._transport = transport or _UrllibOneRequestTransport()

    def __call__(self, call: ValidatedGapCall) -> ToolAdapterResponse:
        if call.tool != "patent_search":
            raise ValueError("Lens adapter accepts only patent_search calls")
        request_shape = {
            "query": {
                "bool": {
                    "should": [
                        {"match": {"title": {"query": call.query, "boost": 2}}},
                        {"match": {"abstract": call.query}},
                        {"match": {"claim": call.query}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            "size": call.result_limit,
            "include": ["lens_id", "biblio", "abstract", "claims", "jurisdiction"],
            "sort": [{"_score": "desc"}],
        }
        body = json.dumps(
            request_shape,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        request_id = _client_request_id("lens", call, request_shape)
        try:
            raw_payload = self._transport(
                endpoint=LENS_PATENT_SEARCH_ENDPOINT,
                method="POST",
                body=body,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "AcademicAgentEvidenceGap/1.0",
                },
                timeout=self._timeout,
            )
        except HTTPError as exc:
            raise _http_failure("Lens", exc) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise _transport_failure("Lens", exc) from exc

        try:
            decoded = json.loads(raw_payload.decode("utf-8"))
            envelope = _LensEnvelope.model_validate(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
            raise ToolAdapterFailure(
                f"Lens response failed schema validation: {type(exc).__name__}",
                retryable=False,
                failure_type="provider_response_invalid",
                search_cost_usd=None,
            ) from exc

        if len(envelope.data) > call.result_limit:
            raise ToolAdapterFailure(
                "Lens returned more rows than the authorized result limit",
                retryable=False,
                failure_type="provider_result_limit_exceeded",
                search_cost_usd=None,
            )

        candidates: list[ToolEvidenceCandidate] = []
        rejections: list[ProviderResultRejection] = []
        for index, raw_result in enumerate(envelope.data):
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
                result = _LensResult.model_validate(raw_result)
                title = _localized_text(
                    result.biblio.invention_title,
                    field="invention title",
                )
                summary = _localized_text(result.abstract, field="abstract")
                publication = result.biblio.publication_reference
                jurisdiction = result.jurisdiction or (
                    publication.jurisdiction if publication is not None else None
                )
                candidates.append(
                    ToolEvidenceCandidate(
                        title=title,
                        url=f"https://lens.org/lens/patent/{result.lens_id}",
                        publisher=(
                            f"{jurisdiction} patent record"
                            if jurisdiction
                            else "Lens.org"
                        ),
                        published_date=_optional_date(
                            publication.date if publication is not None else None
                        ),
                        evidence_summary=summary,
                        summary_source="abstract",
                        provider_result_index=index,
                    )
                )
            except (ValidationError, ValueError) as exc:
                rejections.append(_row_rejection(index, raw_result, exc))

        usage = ToolProviderUsage(
            provider="lens",
            request_id=request_id,
            request_id_source="client_generated",
            result_count=len(envelope.data),
            cost_basis="uninspectable",
        )
        return ToolAdapterResponse(
            tool=call.tool,
            idempotency_key=call.idempotency_key,
            candidates=tuple(candidates),
            search_cost_usd=None,
            provider_request_id=request_id,
            provider_usage=usage,
            provider_rejections=tuple(rejections),
        )
