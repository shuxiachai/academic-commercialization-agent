"""Anonymous OpenAlex tests assert the actual outbound request seam."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from academic_agent.evidence_gap import ValidatedGapCall
from academic_agent.tools.anonymous_openalex_search import (
    AnonymousOpenAlexEvidenceSearchAdapter,
)
from academic_agent.tools.domain_evidence_search import OPENALEX_WORKS_ENDPOINT


_QUERY = "solid-state sodium battery dendrite suppression operando evidence"
_SUMMARY = (
    "The operando study measures sodium dendrite suppression in a solid-state "
    "battery and reports comparative electrochemical stability under cycling."
)


def _call(tool: str = "academic_search") -> ValidatedGapCall:
    return ValidatedGapCall(
        tool=tool,
        query=_QUERY,
        trigger_ids=("anonymous-openalex-gap",),
        result_limit=5,
        output_domain="academic",
        idempotency_key="b" * 64,
    )


def _payload() -> dict:
    inverted: dict[str, list[int]] = {}
    for position, token in enumerate(_SUMMARY.split()):
        inverted.setdefault(token, []).append(position)
    return {
        "meta": {"count": 1, "cost_usd": 0.001},
        "results": [
            {
                "id": "https://openalex.org/W4200000999",
                "title": "Operando sodium dendrite suppression in solid-state cells",
                "doi": "https://doi.org/10.1000/anonymous-openalex",
                "publication_date": "2026-05-02",
                "primary_location": {"source": {"display_name": "Battery Journal"}},
                "cited_by_count": 3,
                "abstract_inverted_index": inverted,
            }
        ],
    }


class RecordingTransport:
    """Injected socket seam; one invocation represents one provider request."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return json.dumps(_payload()).encode("utf-8")


def test_anonymous_adapter_removes_key_before_the_outbound_request(monkeypatch):
    """A configured process key must not leak into an explicitly anonymous call."""

    monkeypatch.setenv("OPENALEX_API_KEY", "environment-secret-must-be-ignored")
    transport = RecordingTransport()
    response = AnonymousOpenAlexEvidenceSearchAdapter(transport=transport)(_call())

    assert len(transport.calls) == 1
    request = transport.calls[0]
    parsed = urlsplit(request["endpoint"])
    query = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == OPENALEX_WORKS_ENDPOINT
    assert "api_key" not in query
    assert query["search"] == [_QUERY]
    assert query["per-page"] == ["5"]
    assert request["method"] == "GET"
    assert request["body"] is None
    assert response.outbound_request_count == 1
    assert response.search_cost_usd == pytest.approx(0.001)
    assert response.provider_usage is not None
    assert response.provider_usage.cost_basis == "reported_usd"
    serialized = response.model_dump_json()
    assert "environment-secret-must-be-ignored" not in serialized
    assert "anonymous-openalex-key-must-not-reach-network" not in serialized


def test_anonymous_adapter_keeps_the_academic_only_capability():
    transport = RecordingTransport()
    adapter = AnonymousOpenAlexEvidenceSearchAdapter(transport=transport)

    with pytest.raises(ValueError, match="academic_search"):
        adapter(_call("patent_search"))

    assert transport.calls == []
