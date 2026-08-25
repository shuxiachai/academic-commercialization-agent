"""Phase-2 bounded Tool Calling execution and evidence-quarantine seams."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from academic_agent.evidence import EvidenceSource
from academic_agent.evidence_gap import (
    GapContext,
    GapPlanProposal,
    GapSearchIntent,
    ValidatedGapCall,
    build_gap_context,
    source_collection_sha256,
    validate_gap_plan,
)
from academic_agent.evidence_gap_execution import (
    EvidenceGapExecutionAudit,
    EvidenceGapExecutionError,
    execute_gap_plan,
)
from academic_agent.source_pipeline import (
    AuthorityCoverage,
    ComponentCoverage,
    SourceCollection,
)
from academic_agent.tools.evidence_search import (
    ToolAdapterFailure,
    ToolAdapterResponse,
    ToolEvidenceCandidate,
)


_SUMMARY = (
    "This source provides sufficiently detailed and topic-specific evidence "
    "for the bounded Tool Calling execution and quarantine test contract."
)
_TOPIC = "battery-free wearable glucose biosensor for remote monitoring"
_TRACE_ID = "trace-phase2-contract"


def _source(
    source_id: str,
    *,
    title: str,
    url: str,
    source_type: str,
    doi: str | None = None,
) -> EvidenceSource:
    return EvidenceSource(
        source_id=source_id,
        title=title,
        url=url,
        doi=doi,
        publisher="Fixture Publisher",
        accessed_date=date(2025, 1, 1),
        source_type=source_type,
        evidence_summary=_SUMMARY,
        summary_source="search_snippet",
    )


def _collection() -> SourceCollection:
    return SourceCollection(
        topic=_TOPIC,
        display_topic=_TOPIC,
        search_aliases=["self-powered wearable glucose sensor monitoring"],
        search_components=["battery-free telemetry", "glucose biosensor"],
        output_language="English",
        weight_profile="biomedical",
        collected_at=datetime(2025, 1, 1, tzinfo=UTC),
        academic_sources=[
            _source(
                "A1",
                title="Battery-free wearable glucose biosensor baseline study",
                url="https://doi.org/10.1000/existing",
                doi="10.1000/existing",
                source_type="academic_paper",
            )
        ],
        patent_sources=[
            _source(
                "P1",
                title="Battery-free wearable glucose biosensor telemetry patent",
                url="https://patents.google.com/patent/US1234567A1",
                source_type="patent",
            )
        ],
        market_sources=[
            _source(
                "M1",
                title="Battery-free wearable glucose monitoring market deployment",
                url="https://www.reuters.com/technology/wearable-glucose-monitoring/",
                source_type="reputable_news",
            )
        ],
        academic_queries=[_TOPIC],
        patent_queries=[_TOPIC],
        market_queries=[_TOPIC],
        authority_coverage=AuthorityCoverage(
            status="incomplete",
            required_categories=["regulatory", "clinical_registry"],
            missing_categories=["regulatory", "clinical_registry"],
        ),
        component_coverage=ComponentCoverage(
            status="incomplete",
            components=["battery-free telemetry", "glucose biosensor"],
            covered_source_ids={"glucose biosensor": ["A1"]},
            missing_components=["battery-free telemetry"],
        ),
        failed_domains={
            "academic": "fixture timeout",
            "patent": "fixture timeout",
            "market": "fixture timeout",
        },
    )


def _trigger(
    context: GapContext,
    *,
    code: str,
    subject: str,
) -> str:
    return next(
        signal.signal_id
        for signal in context.signals
        if signal.code == code and signal.subject == subject
    )


def _call_spec(
    context: GapContext,
    *,
    tool: str,
    code: str,
    subject: str,
    query: str = _TOPIC,
    result_limit: int = 5,
) -> GapSearchIntent:
    return GapSearchIntent(
        tool=tool,
        query=query,
        trigger_ids=(_trigger(context, code=code, subject=subject),),
        result_limit=result_limit,
    )


def _plan(
    context: GapContext,
    *calls: GapSearchIntent,
):
    return validate_gap_plan(
        context,
        GapPlanProposal(
            decision="search",
            rationale=(
                "The frozen challenge exposes a specific evidence gap and "
                "authorizes a bounded read-only search."
            ),
            calls=calls,
        ),
    )


def _candidate(
    *,
    title: str = (
        "Battery-free wearable glucose biosensor remote monitoring evidence"
    ),
    url: str = "https://doi.org/10.1000/novel",
    doi: str | None = "10.1000/novel",
    publisher: str = "Evidence Index",
    summary: str = _SUMMARY,
    summary_source: str = "abstract",
) -> ToolEvidenceCandidate:
    return ToolEvidenceCandidate(
        title=title,
        url=url,
        doi=doi,
        publisher=publisher,
        evidence_summary=summary,
        summary_source=summary_source,
    )


def _response(
    call: ValidatedGapCall,
    *candidates: ToolEvidenceCandidate,
    cost: float = 0.01,
) -> ToolAdapterResponse:
    return ToolAdapterResponse(
        tool=call.tool,
        idempotency_key=call.idempotency_key,
        candidates=candidates,
        search_cost_usd=cost,
        provider_request_id="fixture-request",
    )


def _execute(
    collection: SourceCollection,
    plan,
    adapters,
):
    return execute_gap_plan(
        collection,
        context=build_gap_context(collection),
        plan=plan,
        adapters=adapters,
        trace_id=_TRACE_ID,
    )


def test_adapter_contract_forbids_unknown_fields_and_hidden_extra_requests():
    candidate = _candidate()
    with pytest.raises(ValidationError):
        ToolEvidenceCandidate.model_validate(
            {**candidate.model_dump(mode="json"), "unregistered": True}
        )
    with pytest.raises(ValidationError):
        ToolAdapterResponse(
            tool="academic_search",
            idempotency_key="a" * 64,
            outbound_request_count=2,
        )


def test_valid_academic_candidate_is_quarantined_without_mutating_input():
    collection = _collection()
    context = build_gap_context(collection)
    plan = _plan(
        context,
        _call_spec(
            context,
            tool="academic_search",
            code="retrieval_domain_failed",
            subject="academic",
        ),
    )
    before = source_collection_sha256(collection)

    audit = execute_gap_plan(
        collection,
        context=context,
        plan=plan,
        adapters={
            "academic_search": lambda call: _response(
                call,
                _candidate(),
                cost=0.015,
            )
        },
        trace_id=_TRACE_ID,
    )

    assert audit.evidence_delta_state == "augmented"
    assert audit.outbound_attempt_count == 1
    assert audit.incremental_search_cost_usd == pytest.approx(0.015)
    assert [source.source_id for source in audit.accepted_sources] == ["A2"]
    assert len(collection.academic_sources) == 1
    assert source_collection_sha256(collection) == before
    payload = audit.model_dump(mode="json")
    assert _TOPIC not in payload["call_audits"][0]["query_sha256"]


def test_existing_url_doi_and_title_are_each_rejected_before_registration():
    collection = _collection()
    context = build_gap_context(collection)
    plan = _plan(
        context,
        _call_spec(
            context,
            tool="academic_search",
            code="retrieval_domain_failed",
            subject="academic",
        ),
    )
    candidates = (
        _candidate(
            url="https://doi.org/10.1000/existing",
            doi=None,
            title="Distinct battery-free wearable glucose biosensor URL row",
        ),
        _candidate(
            url="https://openalex.org/W123456",
            doi="10.1000/existing",
            title="Distinct battery-free wearable glucose biosensor DOI row",
        ),
        _candidate(
            url="https://doi.org/10.1000/title-only",
            doi="10.1000/title-only",
            title="Battery-free wearable glucose biosensor baseline study",
        ),
    )

    audit = _execute(
        collection,
        plan,
        {"academic_search": lambda call: _response(call, *candidates)},
    )

    assert audit.evidence_delta_state == "incomplete"
    assert audit.accepted_sources == ()
    assert [item.code for item in audit.call_audits[0].rejections] == [
        "duplicate_url",
        "duplicate_doi",
        "duplicate_title",
    ]


@pytest.mark.parametrize(
    ("url", "expected_code"),
    [
        ("http://127.0.0.1/private", "non_public_literal_host"),
        (
            "https://user:secret@doi.org/10.1000/private",
            "credentialed_url",
        ),
        ("file:///etc/passwd", "unsupported_url"),
        ("https://untrusted.example/paper", "host_not_allowlisted"),
    ],
)
def test_untrusted_candidate_urls_never_reach_evidence(url, expected_code):
    collection = _collection()
    context = build_gap_context(collection)
    plan = _plan(
        context,
        _call_spec(
            context,
            tool="academic_search",
            code="retrieval_domain_failed",
            subject="academic",
        ),
    )

    audit = _execute(
        collection,
        plan,
        {
            "academic_search": lambda call: _response(
                call,
                _candidate(url=url, doi=None),
            )
        },
    )

    assert audit.accepted_sources == ()
    assert audit.call_audits[0].rejections[0].code == expected_code


def test_off_topic_candidate_is_rejected_even_from_an_allowed_host():
    collection = _collection()
    context = build_gap_context(collection)
    plan = _plan(
        context,
        _call_spec(
            context,
            tool="academic_search",
            code="retrieval_domain_failed",
            subject="academic",
        ),
    )

    audit = _execute(
        collection,
        plan,
        {
            "academic_search": lambda call: _response(
                call,
                _candidate(
                    title="Marine archaeology pottery isotope reconstruction",
                    url="https://doi.org/10.1000/off-topic",
                    doi="10.1000/off-topic",
                    summary=(
                        "This archaeology paper studies pottery isotope "
                        "reconstruction and ancient maritime exchange routes."
                    ),
                ),
            )
        },
    )

    assert audit.accepted_sources == ()
    assert audit.call_audits[0].rejections[0].code == "off_topic"


@pytest.mark.parametrize(
    ("tool", "code", "subject", "candidate", "expected_id"),
    [
        (
            "patent_search",
            "retrieval_domain_failed",
            "patent",
            _candidate(
                title=(
                    "Battery-free wearable glucose biosensor telemetry system"
                ),
                url="https://patents.google.com/patent/US2025000001A1",
                doi=None,
                summary_source="search_snippet",
            ),
            "P2",
        ),
        (
            "market_search",
            "retrieval_domain_failed",
            "market",
            _candidate(
                title=(
                    "Battery-free wearable glucose monitoring deployment grows"
                ),
                url=(
                    "https://www.reuters.com/technology/"
                    "battery-free-glucose-monitoring/"
                ),
                doi=None,
                publisher="Reuters",
                summary_source="search_snippet",
            ),
            "M2",
        ),
        (
            "authority_search",
            "authority_category_missing",
            "regulatory",
            _candidate(
                title=(
                    "FDA battery-free wearable glucose biosensor device record"
                ),
                url=(
                    "https://www.fda.gov/medical-devices/"
                    "battery-free-glucose-biosensor"
                ),
                doi=None,
                publisher="US FDA",
                summary_source="search_snippet",
            ),
            "M2",
        ),
    ],
)
def test_each_non_academic_capability_reaches_the_same_quarantine_seam(
    tool,
    code,
    subject,
    candidate,
    expected_id,
):
    collection = _collection()
    context = build_gap_context(collection)
    plan = _plan(
        context,
        _call_spec(
            context,
            tool=tool,
            code=code,
            subject=subject,
            query=(
                _TOPIC
                if tool != "authority_search"
                else f"{_TOPIC} FDA regulatory record"
            ),
        ),
    )

    audit = _execute(
        collection,
        plan,
        {tool: lambda call: _response(call, candidate)},
    )

    assert audit.evidence_delta_state == "augmented"
    assert [source.source_id for source in audit.accepted_sources] == [
        expected_id
    ]


def test_authority_tool_rejects_the_wrong_requested_category():
    collection = _collection()
    context = build_gap_context(collection)
    plan = _plan(
        context,
        _call_spec(
            context,
            tool="authority_search",
            code="authority_category_missing",
            subject="regulatory",
            query=f"{_TOPIC} FDA regulatory record",
        ),
    )

    audit = _execute(
        collection,
        plan,
        {
            "authority_search": lambda call: _response(
                call,
                _candidate(
                    title=(
                        "Clinical trial for battery-free wearable glucose "
                        "biosensor remote monitoring"
                    ),
                    url="https://clinicaltrials.gov/study/NCT01234567",
                    doi=None,
                    publisher="ClinicalTrials.gov",
                    summary_source="search_snippet",
                ),
            )
        },
    )

    assert audit.accepted_sources == ()
    assert (
        audit.call_audits[0].rejections[0].code
        == "wrong_authority_category"
    )


def test_one_call_may_retry_once_and_cost_includes_both_attempts():
    collection = _collection()
    context = build_gap_context(collection)
    plan = _plan(
        context,
        _call_spec(
            context,
            tool="academic_search",
            code="retrieval_domain_failed",
            subject="academic",
        ),
    )
    attempts = 0

    def adapter(call):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ToolAdapterFailure(
                "temporary failure",
                retryable=True,
                failure_type="provider_timeout",
                search_cost_usd=0.004,
            )
        return _response(call, _candidate(), cost=0.006)

    audit = _execute(
        collection,
        plan,
        {"academic_search": adapter},
    )

    assert attempts == 2
    assert audit.outbound_attempt_count == 2
    assert audit.call_audits[0].outbound_attempt_count == 2
    assert audit.call_audits[0].search_cost_usd == pytest.approx(0.01)
    assert audit.incremental_search_cost_usd == pytest.approx(0.01)


def test_two_planned_calls_each_keep_one_slot_and_cannot_retry():
    collection = _collection()
    context = build_gap_context(collection)
    plan = _plan(
        context,
        _call_spec(
            context,
            tool="academic_search",
            code="retrieval_domain_failed",
            subject="academic",
        ),
        _call_spec(
            context,
            tool="patent_search",
            code="retrieval_domain_failed",
            subject="patent",
        ),
    )
    academic = MagicMock(
        side_effect=ToolAdapterFailure(
            "temporary academic failure",
            retryable=True,
            failure_type="provider_timeout",
            search_cost_usd=0.002,
        )
    )
    patent = MagicMock(
        side_effect=lambda call: _response(
            call,
            _candidate(
                title=(
                    "Battery-free wearable glucose biosensor telemetry system"
                ),
                url="https://patents.google.com/patent/US2025000001A1",
                doi=None,
                summary_source="search_snippet",
            ),
            cost=0.003,
        )
    )

    audit = _execute(
        collection,
        plan,
        {
            "academic_search": academic,
            "patent_search": patent,
        },
    )

    assert academic.call_count == 1
    assert patent.call_count == 1
    assert audit.outbound_attempt_count == 2
    assert [call.state for call in audit.call_audits] == [
        "failed",
        "accepted",
    ]
    assert audit.incremental_search_cost_usd == pytest.approx(0.005)


def test_missing_adapter_and_malformed_response_are_not_clean_empty_results():
    collection = _collection()
    context = build_gap_context(collection)
    plan = _plan(
        context,
        _call_spec(
            context,
            tool="academic_search",
            code="retrieval_domain_failed",
            subject="academic",
        ),
    )

    missing = _execute(collection, plan, {})
    malformed = _execute(
        collection,
        plan,
        {
            "academic_search": lambda call: {
                "tool": call.tool,
                "idempotency_key": call.idempotency_key,
                "outbound_request_count": 1,
                "candidates": [],
                "unexpected": True,
            }
        },
    )

    assert missing.call_audits[0].state == "failed"
    assert missing.call_audits[0].outbound_attempt_count == 0
    assert malformed.call_audits[0].state == "failed"
    assert malformed.call_audits[0].cost_state == "uninspectable"
    assert malformed.incremental_search_cost_usd is None


def test_clean_empty_response_is_explicitly_incomplete():
    collection = _collection()
    context = build_gap_context(collection)
    plan = _plan(
        context,
        _call_spec(
            context,
            tool="academic_search",
            code="retrieval_domain_failed",
            subject="academic",
        ),
    )

    audit = _execute(
        collection,
        plan,
        {"academic_search": lambda call: _response(call)},
    )

    assert audit.evidence_delta_state == "incomplete"
    assert audit.call_audits[0].state == "empty"
    assert audit.call_audits[0].raw_candidate_count == 0


def test_context_hash_mismatch_stops_before_any_adapter_attempt():
    collection = _collection()
    context = build_gap_context(collection)
    plan = _plan(
        context,
        _call_spec(
            context,
            tool="academic_search",
            code="retrieval_domain_failed",
            subject="academic",
        ),
    )
    adapter = MagicMock()
    changed = collection.model_copy(deep=True)
    changed.topic = "different topic"

    with pytest.raises(EvidenceGapExecutionError, match="source hash"):
        execute_gap_plan(
            changed,
            context=context,
            plan=plan,
            adapters={"academic_search": adapter},
            trace_id=_TRACE_ID,
        )

    adapter.assert_not_called()


def test_adapter_side_effect_mutation_invalidates_the_whole_delta():
    collection = _collection()
    context = build_gap_context(collection)
    plan = _plan(
        context,
        _call_spec(
            context,
            tool="academic_search",
            code="retrieval_domain_failed",
            subject="academic",
        ),
    )

    def mutating_adapter(call):
        collection.topic = "mutated collection identity"
        return _response(call, _candidate())

    audit = execute_gap_plan(
        collection,
        context=context,
        plan=plan,
        adapters={"academic_search": mutating_adapter},
        trace_id=_TRACE_ID,
    )

    assert audit.evidence_delta_state == "failed"
    assert audit.failure_type == "source_collection_mutated"
    assert audit.accepted_sources == ()
    assert (
        audit.source_collection_sha256_before
        != audit.source_collection_sha256_after
    )


def test_abstention_executes_zero_calls_and_remains_incomplete():
    collection = _collection()
    context = build_gap_context(collection)
    plan = validate_gap_plan(
        context,
        GapPlanProposal(
            decision="abstain",
            rationale=(
                "Expected evidence gain does not justify even one bounded "
                "supplementary request."
            ),
        ),
    )
    adapter = MagicMock()

    audit = execute_gap_plan(
        collection,
        context=context,
        plan=plan,
        adapters={"academic_search": adapter},
        trace_id=_TRACE_ID,
    )

    adapter.assert_not_called()
    assert audit.evidence_delta_state == "incomplete"
    assert audit.outbound_attempt_count == 0


def test_audit_model_rejects_attempt_totals_that_do_not_reach_the_boundary():
    collection = _collection()
    context = build_gap_context(collection)
    plan = _plan(
        context,
        _call_spec(
            context,
            tool="academic_search",
            code="retrieval_domain_failed",
            subject="academic",
        ),
    )
    audit = _execute(
        collection,
        plan,
        {"academic_search": lambda call: _response(call)},
    )
    payload = audit.model_dump(mode="json")
    payload["outbound_attempt_count"] = 0

    with pytest.raises(ValidationError, match="call-audit total"):
        EvidenceGapExecutionAudit.model_validate(payload)
