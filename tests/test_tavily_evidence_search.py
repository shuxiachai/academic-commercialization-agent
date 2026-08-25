"""One-request Tavily adapter contract tests; every transport is offline."""

from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest

from academic_agent.evidence_gap import ValidatedGapCall
from academic_agent.tools.evidence_search import ToolAdapterFailure
from academic_agent.tools.tavily_evidence_search import (
    TAVILY_BASIC_USD_PER_CREDIT,
    TAVILY_SEARCH_ENDPOINT,
    TavilyEvidenceSearchAdapter,
)


_OUTPUT_DOMAINS = {
    "academic_search": "academic",
    "patent_search": "patent",
    "market_search": "market",
    "authority_search": "market",
}


def _call(tool: str = "academic_search", *, result_limit: int = 5):
    return ValidatedGapCall(
        tool=tool,
        query="PET cutinase plastic recycling commercial deployment",
        trigger_ids=("gap-fixture",),
        result_limit=result_limit,
        output_domain=_OUTPUT_DOMAINS[tool],
        idempotency_key="a" * 64,
    )


def _payload(*results, credits: float = 1.0):
    return {
        "request_id": "tavily-request-123",
        "results": list(results),
        "usage": {"credits": credits},
    }


def _result(
    *,
    title: str = "PET cutinase improves enzymatic plastic recycling",
    url: str = "https://doi.org/10.1000/pet-cutinase",
    content: str = (
        "The study reports PET cutinase performance for enzymatic plastic "
        "recycling under commercially relevant process conditions."
    ),
):
    return {
        "title": title,
        "url": url,
        "content": content,
        "published_date": "2025-04-03",
    }


class RecordingTransport:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return json.dumps(self.payload).encode("utf-8")


def test_adapter_performs_one_basic_search_and_keeps_secret_out_of_artifacts():
    transport = RecordingTransport(_payload(_result()))
    adapter = TavilyEvidenceSearchAdapter(
        api_key="tvly-test-secret",
        transport=transport,
    )

    response = adapter(_call())

    assert len(transport.calls) == 1
    request = transport.calls[0]
    body = json.loads(request["body"])
    assert request["endpoint"] == TAVILY_SEARCH_ENDPOINT
    assert request["headers"]["Authorization"] == "Bearer tvly-test-secret"
    assert body["search_depth"] == "basic"
    assert body["auto_parameters"] is False
    assert body["include_answer"] is False
    assert body["include_raw_content"] is False
    assert body["include_images"] is False
    assert body["include_usage"] is True
    assert body["max_results"] == 5
    assert body["include_domains"] == sorted(body["include_domains"])
    assert "doi.org" in body["include_domains"]
    assert "tvly-test-secret" not in request["body"].decode("utf-8")

    assert response.outbound_request_count == 1
    assert response.provider_request_id == "tavily-request-123"
    assert response.provider_usage is not None
    assert response.provider_usage.result_count == 1
    assert response.search_cost_usd == pytest.approx(
        TAVILY_BASIC_USD_PER_CREDIT
    )
    assert response.candidates[0].provider_result_index == 0
    assert response.candidates[0].doi == "10.1000/pet-cutinase"
    assert response.candidates[0].publisher == "doi.org"
    serialized = response.model_dump_json()
    assert "tvly-test-secret" not in serialized


@pytest.mark.parametrize(
    ("tool", "required_domain"),
    [
        ("academic_search", "openalex.org"),
        ("patent_search", "patents.google.com"),
        ("market_search", "reuters.com"),
        ("authority_search", "fda.gov"),
    ],
)
def test_each_tool_receives_a_code_owned_sorted_domain_scope(
    tool,
    required_domain,
):
    transport = RecordingTransport(_payload())
    adapter = TavilyEvidenceSearchAdapter(api_key="key", transport=transport)

    adapter(_call(tool))

    body = json.loads(transport.calls[0]["body"])
    assert required_domain in body["include_domains"]
    assert len(body["include_domains"]) == len(set(body["include_domains"]))
    assert body["include_domains"] == sorted(body["include_domains"])


def test_malformed_provider_rows_are_accounted_without_dropping_valid_siblings():
    transport = RecordingTransport(
        _payload(
            _result(),
            "not-an-object",
            {"title": "bad", "url": "https://doi.org/10.1000/bad"},
            _result(
                title="Malformed URL should reject only this provider row",
                url="https://[invalid",
            ),
            _result(
                title="Second PET cutinase plastic recycling evidence record",
                url="https://openalex.org/W123456",
            ),
        )
    )
    adapter = TavilyEvidenceSearchAdapter(api_key="key", transport=transport)

    response = adapter(_call())

    assert [item.provider_result_index for item in response.candidates] == [0, 4]
    assert [item.provider_result_index for item in response.provider_rejections] == [
        1,
        2,
        3,
    ]
    assert [item.code for item in response.provider_rejections] == [
        "provider_result_not_object",
        "provider_result_schema_invalid",
        "provider_result_schema_invalid",
    ]
    assert response.provider_usage is not None
    assert response.provider_usage.result_count == 5


@pytest.mark.parametrize(
    "payload",
    [
        {"request_id": "request", "results": []},
        {"request_id": "request", "results": [], "usage": {}},
        {"request_id": "x", "results": [], "usage": {"credits": 1}},
    ],
)
def test_missing_or_invalid_provider_accounting_is_not_reported_as_free(payload):
    transport = RecordingTransport(payload)
    adapter = TavilyEvidenceSearchAdapter(api_key="key", transport=transport)

    with pytest.raises(ToolAdapterFailure) as caught:
        adapter(_call())

    assert len(transport.calls) == 1
    assert caught.value.failure_type == "provider_response_invalid"
    assert caught.value.search_cost_usd is None
    assert caught.value.retryable is False


@pytest.mark.parametrize(
    ("status", "retryable", "failure_type"),
    [
        (302, False, "provider_redirect"),
        (401, False, "provider_http"),
        (408, True, "provider_http"),
        (429, True, "provider_http"),
        (503, True, "provider_http"),
    ],
)
def test_http_failures_are_classified_without_a_hidden_retry(
    status,
    retryable,
    failure_type,
):
    attempts = 0

    def failing_transport(**kwargs):
        nonlocal attempts
        attempts += 1
        raise HTTPError(kwargs["endpoint"], status, "fixture", None, None)

    adapter = TavilyEvidenceSearchAdapter(
        api_key="key",
        transport=failing_transport,
    )

    with pytest.raises(ToolAdapterFailure) as caught:
        adapter(_call())

    assert attempts == 1
    assert caught.value.retryable is retryable
    assert caught.value.failure_type == failure_type
    assert caught.value.search_cost_usd is None


def test_provider_result_limit_violation_preserves_known_credit_cost():
    transport = RecordingTransport(
        _payload(_result(), _result(title="Another valid PET cutinase result"))
    )
    adapter = TavilyEvidenceSearchAdapter(api_key="key", transport=transport)

    with pytest.raises(ToolAdapterFailure) as caught:
        adapter(_call(result_limit=1))

    assert len(transport.calls) == 1
    assert caught.value.failure_type == "provider_result_limit_exceeded"
    assert caught.value.search_cost_usd == pytest.approx(
        TAVILY_BASIC_USD_PER_CREDIT
    )


@pytest.mark.parametrize("invalid_rate", [float("nan"), float("inf"), -0.001])
def test_invalid_accounting_rate_fails_before_transport(invalid_rate):
    transport = RecordingTransport(_payload(_result()))

    with pytest.raises(ValueError, match="finite and non-negative"):
        TavilyEvidenceSearchAdapter(
            api_key="key",
            usd_per_credit=invalid_rate,
            transport=transport,
        )

    assert transport.calls == []
