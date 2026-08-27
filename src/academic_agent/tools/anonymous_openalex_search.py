"""Explicitly anonymous OpenAlex adapter for production-disconnected studies.

The Phase 4 domain adapter deliberately requires a credential because that
request contract was frozen before implementation.  OpenAlex subsequently
documented that its Works API also supports a smaller anonymous daily budget.
Changing the frozen adapter would retire its unexecuted implementation identity,
so this module composes the existing parser with a transport that removes one
non-secret sentinel before the socket boundary.  The unusual composition is
intentional: it reuses every response-validation and quarantine decision while
making the no-key request visible and independently testable.
"""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from academic_agent.evidence_gap import ValidatedGapCall
from academic_agent.tools.domain_evidence_search import (
    OPENALEX_WORKS_ENDPOINT,
    DomainOneRequestTransport,
    OpenAlexEvidenceSearchAdapter,
)
from academic_agent.tools.evidence_search import ToolAdapterResponse


_ANONYMOUS_SENTINEL = "anonymous-openalex-key-must-not-reach-network"


class _StripAnonymousSentinelTransport:
    """Remove exactly one local sentinel, then delegate exactly one request.

    Passing a made-up key to OpenAlex would not be anonymous and could change
    provider behavior.  This seam therefore rejects any endpoint other than the
    expected Works URL, requires the exact local sentinel once, removes it, and
    delegates once.  It never retries, follows redirects, or fetches result
    pages; those properties remain the responsibility of the injected one-call
    transport, just as they are for the credentialed adapter.
    """

    def __init__(self, delegate: DomainOneRequestTransport) -> None:
        self._delegate = delegate

    def __call__(
        self,
        *,
        endpoint: str,
        method: str,
        body: bytes | None,
        headers: Mapping[str, str],
        timeout: float,
    ) -> bytes:
        parsed = urlsplit(endpoint)
        expected = urlsplit(OPENALEX_WORKS_ENDPOINT)
        if (
            parsed.scheme != expected.scheme
            or parsed.netloc != expected.netloc
            or parsed.path != expected.path
            or parsed.fragment
        ):
            raise ValueError("anonymous OpenAlex transport received an unexpected endpoint")

        query_items = parse_qsl(parsed.query, keep_blank_values=True)
        sentinels = [value for key, value in query_items if key == "api_key"]
        if sentinels != [_ANONYMOUS_SENTINEL]:
            raise ValueError(
                "anonymous OpenAlex transport requires exactly one local sentinel"
            )
        anonymous_query = [(key, value) for key, value in query_items if key != "api_key"]
        anonymous_endpoint = urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(anonymous_query),
                "",
            )
        )
        return self._delegate(
            endpoint=anonymous_endpoint,
            method=method,
            body=body,
            headers=headers,
            timeout=timeout,
        )


class AnonymousOpenAlexEvidenceSearchAdapter:
    """Reuse the strict OpenAlex contract while sending no API credential.

    A transport is mandatory so importing or constructing this experimental
    adapter can never open a socket implicitly.  The later live-study runner
    owns the concrete no-redirect transport and constructs it only after its
    frozen identities, request cap, output path, and anonymous-budget
    acknowledgement have passed.
    """

    def __init__(
        self,
        *,
        transport: DomainOneRequestTransport,
        timeout: float = 20.0,
    ) -> None:
        self._delegate = OpenAlexEvidenceSearchAdapter(
            api_key=_ANONYMOUS_SENTINEL,
            timeout=timeout,
            transport=_StripAnonymousSentinelTransport(transport),
        )

    def __call__(self, call: ValidatedGapCall) -> ToolAdapterResponse:
        return self._delegate(call)
