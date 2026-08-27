"""Outbound-seam tests for the disconnected claim-scope OpenAlex adapter."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from academic_agent.evidence_gap import ValidatedGapCall
from academic_agent.tools.domain_evidence_search import OPENALEX_WORKS_ENDPOINT
from academic_agent.tools.evidence_search import ToolAdapterFailure
from academic_agent.tools.openalex_claim_scope_search import (
    AnonymousOpenAlexClaimScopeAdapter,
)


_QUERY = (
    "near field thermophotovoltaic nanophotonic vacuum gap energy conversion"
)
_SUMMARY = (
    "The integrated thermophotovoltaic experiment measures electrical power "
    "density across a controlled nanoscale vacuum gap and reports conversion "
    "efficiency under calibrated thermal-emitter conditions."
)


def _call(
    tool: str = "academic_search",
    *,
    result_limit: int = 8,
) -> ValidatedGapCall:
    return ValidatedGapCall(
        tool=tool,
        query=_QUERY,
        trigger_ids=("claim-scope-gap",),
        result_limit=result_limit,
        output_domain="academic",
        idempotency_key="c" * 64,
    )


def _inverted_abstract(value: str) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for position, token in enumerate(value.split()):
        result.setdefault(token, []).append(position)
    return result


def _result(
    *,
    work_id: str = "https://openalex.org/W4300000001",
    title: str = "Near-field thermophotovoltaic conversion across a vacuum gap",
) -> dict:
    return {
        "id": work_id,
        "title": title,
        "doi": "https://doi.org/10.1000/claim-scope",
        "publication_date": "2026-04-03",
        "primary_location": {
            "source": {"display_name": "Thermal Photonics Journal"}
        },
        "cited_by_count": 6,
        "abstract_inverted_index": _inverted_abstract(_SUMMARY),
        "topics": [
            {
                "id": "https://openalex.org/T100000001",
                "display_name": "Near-field radiative heat transfer",
                "score": 0.91,
            }
        ],
        "keywords": [
            {
                "id": "https://openalex.org/keywords/thermophotovoltaics",
                "display_name": "Thermophotovoltaics",
                "score": 0.88,
            }
        ],
    }


def _payload(*results: object, cost: float = 0.001) -> dict:
    return {
        "meta": {"count": len(results), "cost_usd": cost},
        "results": list(results),
    }


class RecordingTransport:
    """Injected socket seam; one invocation equals one provider request."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return json.dumps(self.payload).encode("utf-8")


def test_adapter_uses_one_abstract_filtered_request_and_preserves_aboutness(
    monkeypatch,
):
    monkeypatch.setenv("OPENALEX_API_KEY", "must-not-reach-claim-scope-request")
    transport = RecordingTransport(_payload(_result()))

    response = AnonymousOpenAlexClaimScopeAdapter(transport=transport)(_call())

    assert len(transport.calls) == 1
    request = transport.calls[0]
    parsed = urlsplit(request["endpoint"])
    query = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == OPENALEX_WORKS_ENDPOINT
    assert query["search"] == [_QUERY]
    assert query["filter"] == ["has_abstract:true"]
    assert query["per-page"] == ["8"]
    assert "api_key" not in query
    assert set(query["select"][0].split(",")) == {
        "id",
        "title",
        "doi",
        "publication_date",
        "primary_location",
        "cited_by_count",
        "abstract_inverted_index",
        "topics",
        "keywords",
    }
    assert request["method"] == "GET"
    assert request["body"] is None

    assert response.outbound_request_count == 1
    assert response.search_cost_usd == pytest.approx(0.001)
    assert response.provider_usage.result_count == 1
    candidate = response.candidates[0]
    assert candidate.evidence.doi == "10.1000/claim-scope"
    assert [(item.kind, item.display_name) for item in candidate.aboutness] == [
        ("topic", "Near-field radiative heat transfer"),
        ("keyword", "Thermophotovoltaics"),
    ]
    serialized = response.model_dump_json()
    assert "must-not-reach-claim-scope-request" not in serialized


def test_every_malformed_provider_row_remains_explicitly_accounted():
    no_abstract = _result(
        work_id="https://openalex.org/W4300000002",
        title="A result that violates the requested abstract filter",
    )
    no_abstract["abstract_inverted_index"] = None
    malformed_aboutness = _result(
        work_id="https://openalex.org/W4300000003",
        title="A result with malformed provider topic metadata",
    )
    malformed_aboutness["topics"][0]["score"] = "unknown"
    transport = RecordingTransport(
        _payload(_result(), no_abstract, malformed_aboutness, "not-an-object")
    )

    response = AnonymousOpenAlexClaimScopeAdapter(transport=transport)(_call())

    assert len(transport.calls) == 1
    assert [
        item.evidence.provider_result_index for item in response.candidates
    ] == [0]
    assert [
        item.provider_result_index for item in response.provider_rejections
    ] == [1, 2, 3]
    assert response.provider_usage.result_count == 4


def test_wrong_tool_fails_before_transport_construction():
    transport = RecordingTransport(_payload())
    adapter = AnonymousOpenAlexClaimScopeAdapter(transport=transport)

    with pytest.raises(ValueError, match="academic_search"):
        adapter(_call("patent_search"))

    assert transport.calls == []


def test_provider_cannot_exceed_the_authorized_result_limit():
    transport = RecordingTransport(
        _payload(
            _result(),
            _result(work_id="https://openalex.org/W4300000002"),
        )
    )

    with pytest.raises(
        ToolAdapterFailure,
        match="authorized result limit",
    ) as caught:
        AnonymousOpenAlexClaimScopeAdapter(transport=transport)(
            _call(result_limit=1)
        )

    assert len(transport.calls) == 1
    assert caught.value.failure_type == "provider_result_limit_exceeded"
    assert caught.value.search_cost_usd == pytest.approx(0.001)
