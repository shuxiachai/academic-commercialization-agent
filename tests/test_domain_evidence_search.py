"""Offline contracts for the source-native Phase 4 evidence adapters."""

from __future__ import annotations

import json
import traceback
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError

from academic_agent.evidence_gap import ValidatedGapCall
from academic_agent.evidence_gap_execution import execute_gap_plan
from academic_agent.tools.domain_evidence_search import (
    LENS_PATENT_SEARCH_ENDPOINT,
    OPENALEX_WORKS_ENDPOINT,
    LensEvidenceSearchAdapter,
    OpenAlexEvidenceSearchAdapter,
)
from academic_agent.tools.evidence_search import (
    ToolAdapterFailure,
    ToolAdapterResponse,
    ToolEvidenceCandidate,
    ToolProviderUsage,
)
from evidence_gap_phase4_audit import load_frozen_cases


_ACADEMIC_QUERY = (
    "non-thermal plasma ammonia synthesis catalyst energy efficiency experimental"
)
_PATENT_QUERY = (
    "fluoride-ion battery lanthanum fluoride solid electrolyte conductivity"
)
_ACADEMIC_SUMMARY = (
    "The experimental study measures non-thermal plasma ammonia synthesis "
    "with catalyst-dependent energy efficiency and reports reactor conditions."
)
_PATENT_SUMMARY = (
    "The patent abstract describes a fluoride-ion battery using a lanthanum "
    "fluoride solid electrolyte, ionic conductivity controls, and cell design."
)


def _call(tool: str, query: str, *, result_limit: int = 5) -> ValidatedGapCall:
    return ValidatedGapCall(
        tool=tool,
        query=query,
        trigger_ids=("phase4-gap",),
        result_limit=result_limit,
        output_domain="academic" if tool == "academic_search" else "patent",
        idempotency_key="a" * 64,
    )


def _inverted_abstract(value: str) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for position, token in enumerate(value.split()):
        result.setdefault(token, []).append(position)
    return result


def _openalex_result(
    *,
    work_id: str = "https://openalex.org/W4200000001",
    title: str = (
        "Low-temperature non-thermal plasma ammonia synthesis catalyst study"
    ),
    summary: str = _ACADEMIC_SUMMARY,
) -> dict:
    return {
        "id": work_id,
        "title": title,
        "doi": "https://doi.org/10.1000/plasma-ammonia",
        "publication_date": "2025-05-06",
        "primary_location": {"source": {"display_name": "Catalysis Journal"}},
        "cited_by_count": 17,
        "abstract_inverted_index": _inverted_abstract(summary),
    }


def _openalex_payload(*results, cost: float = 0.0001) -> dict:
    return {"meta": {"count": len(results), "cost_usd": cost}, "results": list(results)}


def _lens_result(
    *,
    lens_id: str = "123-456-789-000-111",
    title: str = "Lanthanum-fluoride solid electrolyte for fluoride-ion batteries",
    summary: str = _PATENT_SUMMARY,
) -> dict:
    return {
        "lens_id": lens_id,
        "jurisdiction": "US",
        "biblio": {
            "invention_title": [{"text": title, "lang": "en"}],
            "publication_reference": {
                "jurisdiction": "US",
                "date": "2025-03-04",
            },
        },
        "abstract": [{"text": summary, "lang": "en"}],
        "claims": {"claims": [{"claim_text": "A fluoride-ion battery..."}]},
    }


def _lens_payload(*results) -> dict:
    return {"total": len(results), "data": list(results)}


class RecordingTransport:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return json.dumps(self.payload).encode("utf-8")


def test_openalex_performs_one_search_and_preserves_reported_cost_without_secret():
    transport = RecordingTransport(_openalex_payload(_openalex_result()))
    adapter = OpenAlexEvidenceSearchAdapter(
        api_key="openalex-test-secret",
        transport=transport,
    )

    response = adapter(_call("academic_search", _ACADEMIC_QUERY))

    assert len(transport.calls) == 1
    request = transport.calls[0]
    parsed = urlsplit(request["endpoint"])
    query = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == OPENALEX_WORKS_ENDPOINT
    assert request["method"] == "GET"
    assert request["body"] is None
    assert query["search"] == [_ACADEMIC_QUERY]
    assert query["per-page"] == ["5"]
    assert query["api_key"] == ["openalex-test-secret"]
    assert set(query["select"][0].split(",")) == {
        "id",
        "title",
        "doi",
        "publication_date",
        "primary_location",
        "cited_by_count",
        "abstract_inverted_index",
    }

    assert response.outbound_request_count == 1
    assert response.search_cost_usd == pytest.approx(0.0001)
    assert response.provider_usage is not None
    assert response.provider_usage.provider == "openalex"
    assert response.provider_usage.request_id_source == "client_generated"
    assert response.provider_usage.cost_basis == "reported_usd"
    assert response.provider_usage.reported_cost_usd == pytest.approx(0.0001)
    assert response.candidates[0].summary_source == "abstract"
    assert response.candidates[0].doi == "10.1000/plasma-ammonia"
    serialized = response.model_dump_json()
    assert "openalex-test-secret" not in serialized


def test_openalex_request_identity_is_stable_across_secret_rotation():
    first_transport = RecordingTransport(_openalex_payload())
    second_transport = RecordingTransport(_openalex_payload())
    call = _call("academic_search", _ACADEMIC_QUERY)

    first = OpenAlexEvidenceSearchAdapter(
        api_key="first-secret",
        transport=first_transport,
    )(call)
    second = OpenAlexEvidenceSearchAdapter(
        api_key="second-secret",
        transport=second_transport,
    )(call)

    assert first.provider_request_id == second.provider_request_id
    assert "first-secret" not in first.provider_request_id
    assert "second-secret" not in second.provider_request_id


def test_openalex_accounts_for_each_malformed_row_without_dropping_siblings():
    missing_abstract = _openalex_result(
        work_id="https://openalex.org/W4200000002",
        title="OpenAlex record whose abstract metadata is missing",
    )
    missing_abstract["abstract_inverted_index"] = None
    transport = RecordingTransport(
        _openalex_payload(
            _openalex_result(),
            "not-an-object",
            missing_abstract,
            _openalex_result(
                work_id="https://openalex.org/W4200000003",
                title="Second plasma ammonia catalyst performance experiment",
            ),
        )
    )
    response = OpenAlexEvidenceSearchAdapter(
        api_key="key",
        transport=transport,
    )(_call("academic_search", _ACADEMIC_QUERY))

    assert [item.provider_result_index for item in response.candidates] == [0, 3]
    assert [item.provider_result_index for item in response.provider_rejections] == [
        1,
        2,
    ]
    assert response.provider_usage is not None
    assert response.provider_usage.result_count == 4


@pytest.mark.parametrize(
    "payload",
    [
        {"meta": {"count": 0}, "results": []},
        {"meta": {"cost_usd": "unknown"}, "results": []},
        {"meta": {"cost_usd": 0}, "results": "not-a-list"},
    ],
)
def test_openalex_missing_or_invalid_cost_is_uninspectable_failure(payload):
    transport = RecordingTransport(payload)
    adapter = OpenAlexEvidenceSearchAdapter(api_key="key", transport=transport)

    with pytest.raises(ToolAdapterFailure) as caught:
        adapter(_call("academic_search", _ACADEMIC_QUERY))

    assert len(transport.calls) == 1
    assert caught.value.failure_type == "provider_response_invalid"
    assert caught.value.search_cost_usd is None


def test_lens_performs_one_claim_search_and_marks_cost_uninspectable():
    transport = RecordingTransport(_lens_payload(_lens_result()))
    adapter = LensEvidenceSearchAdapter(
        api_key="lens-test-secret",
        transport=transport,
    )

    response = adapter(_call("patent_search", _PATENT_QUERY))

    assert len(transport.calls) == 1
    request = transport.calls[0]
    body = json.loads(request["body"])
    should = body["query"]["bool"]["should"]
    assert request["endpoint"] == LENS_PATENT_SEARCH_ENDPOINT
    assert request["method"] == "POST"
    assert request["headers"]["Authorization"] == "Bearer lens-test-secret"
    assert body["size"] == 5
    assert body["query"]["bool"]["minimum_should_match"] == 1
    assert {next(iter(branch["match"])) for branch in should} == {
        "title",
        "abstract",
        "claim",
    }
    assert "claims" in body["include"]
    assert "lens-test-secret" not in request["body"].decode("utf-8")

    assert response.search_cost_usd is None
    assert response.provider_usage is not None
    assert response.provider_usage.provider == "lens"
    assert response.provider_usage.request_id_source == "client_generated"
    assert response.provider_usage.cost_basis == "uninspectable"
    assert response.candidates[0].url.startswith("https://lens.org/lens/patent/")
    assert response.candidates[0].publisher == "US patent record"
    assert "lens-test-secret" not in response.model_dump_json()


def test_lens_accounts_for_missing_abstract_and_non_object_rows():
    missing_abstract = _lens_result(lens_id="123-456-789-000-222")
    missing_abstract["abstract"] = []
    transport = RecordingTransport(
        _lens_payload(
            _lens_result(),
            missing_abstract,
            ["not", "an", "object"],
        )
    )

    response = LensEvidenceSearchAdapter(
        api_key="key",
        transport=transport,
    )(_call("patent_search", _PATENT_QUERY))

    assert [item.provider_result_index for item in response.candidates] == [0]
    assert [item.provider_result_index for item in response.provider_rejections] == [
        1,
        2,
    ]
    assert response.provider_usage is not None
    assert response.provider_usage.result_count == 3


@pytest.mark.parametrize(
    ("adapter_type", "tool", "query"),
    [
        (OpenAlexEvidenceSearchAdapter, "patent_search", _PATENT_QUERY),
        (LensEvidenceSearchAdapter, "academic_search", _ACADEMIC_QUERY),
    ],
)
def test_wrong_provider_capability_fails_before_transport(
    adapter_type,
    tool,
    query,
):
    transport = RecordingTransport({})
    adapter = adapter_type(api_key="key", transport=transport)

    with pytest.raises(ValueError, match="accepts only"):
        adapter(_call(tool, query))

    assert transport.calls == []


@pytest.mark.parametrize(
    ("adapter_type", "tool", "query"),
    [
        (OpenAlexEvidenceSearchAdapter, "academic_search", _ACADEMIC_QUERY),
        (LensEvidenceSearchAdapter, "patent_search", _PATENT_QUERY),
    ],
)
def test_redirect_is_one_uninspectable_attempt_without_hidden_retry(
    adapter_type,
    tool,
    query,
):
    attempts = 0

    def redirecting_transport(**kwargs):
        nonlocal attempts
        attempts += 1
        raise HTTPError(kwargs["endpoint"], 302, "fixture", None, None)

    adapter = adapter_type(api_key="key", transport=redirecting_transport)
    with pytest.raises(ToolAdapterFailure) as caught:
        adapter(_call(tool, query))

    assert attempts == 1
    assert caught.value.failure_type == "provider_redirect"
    assert caught.value.search_cost_usd is None
    assert caught.value.retryable is False


@pytest.mark.parametrize(
    ("adapter_type", "tool", "query"),
    [
        (OpenAlexEvidenceSearchAdapter, "academic_search", _ACADEMIC_QUERY),
        (LensEvidenceSearchAdapter, "patent_search", _PATENT_QUERY),
    ],
)
def test_retryable_transport_failure_is_not_retried_inside_adapter(
    adapter_type,
    tool,
    query,
):
    attempts = 0

    def failing_transport(**kwargs):
        nonlocal attempts
        attempts += 1
        raise URLError(f"offline fixture for {kwargs['endpoint']}")

    api_key = "openalex-query-secret" if tool == "academic_search" else "lens-secret"
    adapter = adapter_type(api_key=api_key, transport=failing_transport)
    with pytest.raises(ToolAdapterFailure) as caught:
        adapter(_call(tool, query))

    assert attempts == 1
    assert caught.value.failure_type == "provider_transport"
    assert caught.value.search_cost_usd is None
    assert caught.value.retryable is True
    rendered = "".join(traceback.format_exception(caught.value))
    assert api_key not in rendered


def test_result_limit_failure_keeps_openalex_cost_and_lens_unknown_distinct():
    academic = OpenAlexEvidenceSearchAdapter(
        api_key="key",
        transport=RecordingTransport(
            _openalex_payload(_openalex_result(), _openalex_result())
        ),
    )
    patent = LensEvidenceSearchAdapter(
        api_key="key",
        transport=RecordingTransport(_lens_payload(_lens_result(), _lens_result())),
    )

    with pytest.raises(ToolAdapterFailure) as academic_error:
        academic(_call("academic_search", _ACADEMIC_QUERY, result_limit=1))
    with pytest.raises(ToolAdapterFailure) as patent_error:
        patent(_call("patent_search", _PATENT_QUERY, result_limit=1))

    assert academic_error.value.search_cost_usd == pytest.approx(0.0001)
    assert patent_error.value.search_cost_usd is None


def test_provider_accounting_cannot_turn_unknown_lens_cost_into_zero():
    usage = ToolProviderUsage(
        provider="lens",
        request_id="client-lens-request",
        request_id_source="client_generated",
        result_count=0,
        cost_basis="uninspectable",
    )
    with pytest.raises(ValidationError, match="must remain null"):
        ToolAdapterResponse(
            tool="patent_search",
            idempotency_key="a" * 64,
            search_cost_usd=0,
            provider_request_id=usage.request_id,
            provider_usage=usage,
        )


def test_provider_row_accounting_requires_every_index_at_executor_boundary():
    candidate = ToolEvidenceCandidate(
        title="A valid academic evidence candidate for accounting",
        url="https://openalex.org/W4200000001",
        publisher="OpenAlex",
        evidence_summary=_ACADEMIC_SUMMARY,
        summary_source="abstract",
        provider_result_index=0,
    )
    usage = ToolProviderUsage(
        provider="openalex",
        request_id="client-openalex-request",
        request_id_source="client_generated",
        result_count=2,
        cost_basis="reported_usd",
        reported_cost_usd=0.0001,
    )
    with pytest.raises(ValidationError, match="cover candidates and rejections"):
        ToolAdapterResponse(
            tool="academic_search",
            idempotency_key="a" * 64,
            candidates=(candidate,),
            search_cost_usd=0.0001,
            provider_request_id=usage.request_id,
            provider_usage=usage,
        )


def test_openalex_and_lens_metadata_reach_the_executor_audit_seam():
    _, cases = load_frozen_cases()
    academic_case = cases[0]
    patent_case = cases[4]
    academic_adapter = OpenAlexEvidenceSearchAdapter(
        api_key="key",
        transport=RecordingTransport(_openalex_payload(_openalex_result())),
    )
    patent_adapter = LensEvidenceSearchAdapter(
        api_key="key",
        transport=RecordingTransport(_lens_payload(_lens_result())),
    )

    academic_audit = execute_gap_plan(
        academic_case.collection,
        context=academic_case.context,
        plan=academic_case.plan,
        adapters={"academic_search": academic_adapter},
        trace_id="phase4-openalex-seam",
        outbound_attempt_limit=1,
    )
    patent_audit = execute_gap_plan(
        patent_case.collection,
        context=patent_case.context,
        plan=patent_case.plan,
        adapters={"patent_search": patent_adapter},
        trace_id="phase4-lens-seam",
        outbound_attempt_limit=1,
    )

    academic_call = academic_audit.call_audits[0]
    patent_call = patent_audit.call_audits[0]
    assert academic_call.provider_usage is not None
    assert academic_call.provider_usage.provider == "openalex"
    assert academic_call.provider_usage.request_id_source == "client_generated"
    assert academic_call.cost_state == "known"
    assert academic_audit.evidence_delta_state == "augmented"
    assert patent_call.provider_usage is not None
    assert patent_call.provider_usage.provider == "lens"
    assert patent_call.provider_usage.cost_basis == "uninspectable"
    assert patent_call.cost_state == "uninspectable"
    assert patent_audit.cost_state == "uninspectable"
    assert patent_audit.evidence_delta_state == "augmented"
