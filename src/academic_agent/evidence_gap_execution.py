"""Production-disconnected execution kernel for evidence-gap Tool Calling.

The module deliberately accepts only a ValidatedGapPlan. Model output, network
clients, and report mutation stay outside this boundary: phase 2 is measuring
whether a plan can be executed and quarantined safely before any production
worker is allowed to connect it.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
import time
from collections.abc import Mapping
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from academic_agent.evidence import EvidenceSource, normalize_doi
from academic_agent.evidence_gap import (
    GapContext,
    GapToolName,
    ValidatedGapCall,
    ValidatedGapPlan,
    source_collection_sha256,
)
from academic_agent.source_pipeline import (
    SourceCollection,
    _OFFICIAL_PATENT_HOSTS,
    _PATENT_HOSTS,
    _authority_category_for_url,
    _canonical_url,
    _market_source_profile,
    _relevance_score,
    _topic_bigrams,
    _topic_domain_keywords,
    _topic_keywords,
)
from academic_agent.tools.evidence_search import (
    ReadOnlySearchAdapter,
    ToolAdapterFailure,
    ToolAdapterResponse,
    ToolEvidenceCandidate,
)


MAX_OUTBOUND_SEARCH_ATTEMPTS = 2
_PREFIX_BY_DOMAIN = {"academic": "A", "patent": "P", "market": "M"}
_MIN_RELEVANCE_BY_DOMAIN = {"academic": 3, "patent": 1, "market": 2}
_ACADEMIC_RECORD_HOSTS = frozenset(
    {
        "arxiv.org",
        "doi.org",
        "ncbi.nlm.nih.gov",
        "openalex.org",
        "pubmed.ncbi.nlm.nih.gov",
        "semanticscholar.org",
    }
)
_BLOCKED_HOST_SUFFIXES = (
    ".internal",
    ".invalid",
    ".local",
    ".localhost",
    ".test",
)
_TITLE_WORDS = re.compile(r"[a-z0-9]+", re.IGNORECASE)

CallState = Literal[
    "accepted",
    "empty",
    "rejected",
    "failed",
    "budget_exhausted",
]
EvidenceDeltaState = Literal["augmented", "incomplete", "unchanged", "failed"]
RejectionCode = Literal[
    "credentialed_url",
    "duplicate_doi",
    "duplicate_title",
    "duplicate_url",
    "host_not_allowlisted",
    "non_public_literal_host",
    "off_topic",
    "source_schema_invalid",
    "unsupported_url",
    "wrong_authority_category",
    "wrong_evidence_domain",
]


class EvidenceGapExecutionError(ValueError):
    """Raised before execution when trusted phase-1 identities do not join."""


class CandidateRejection(BaseModel):
    """One quarantined row and why it did not enter the evidence delta."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_index: int = Field(ge=0)
    code: RejectionCode
    detail: str = Field(min_length=1, max_length=500)


class GapToolCallAudit(BaseModel):
    """Observable result of one validated logical call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    call_index: int = Field(ge=0, le=1)
    tool: GapToolName
    trigger_ids: tuple[str, ...] = Field(min_length=1, max_length=4)
    query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    state: CallState
    outbound_attempt_count: int = Field(
        ge=0,
        le=MAX_OUTBOUND_SEARCH_ATTEMPTS,
    )
    raw_candidate_count: int = Field(default=0, ge=0, le=10)
    accepted_source_ids: tuple[str, ...] = ()
    rejections: tuple[CandidateRejection, ...] = ()
    latency_ms: float = Field(ge=0.0)
    search_cost_usd: float | None = Field(default=0.0, ge=0.0)
    cost_state: Literal["known", "uninspectable"] = "known"
    failure_type: str | None = Field(default=None, max_length=200)
    trace_id: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def _validate_state(self) -> "GapToolCallAudit":
        if self.cost_state == "uninspectable" and self.search_cost_usd is not None:
            raise ValueError("uninspectable cost must be represented by null")
        if self.cost_state == "known" and self.search_cost_usd is None:
            raise ValueError("known cost requires a numeric value")
        if self.state == "accepted" and not self.accepted_source_ids:
            raise ValueError("accepted state requires at least one registered source")
        if self.state != "accepted" and self.accepted_source_ids:
            raise ValueError(f"{self.state} cannot carry accepted sources")
        if self.state in {"failed", "budget_exhausted"} and not self.failure_type:
            raise ValueError(f"{self.state} requires a failure type")
        if self.state not in {"failed", "budget_exhausted"} and self.failure_type:
            raise ValueError("only failed calls may carry a failure type")
        return self


class EvidenceGapExecutionAudit(BaseModel):
    """Complete phase-2 result; accepted candidates remain quarantined."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["phase2_experiment"] = "phase2_experiment"
    production_connected: Literal[False] = False
    decision: Literal["no_gap", "search", "abstain"]
    evidence_delta_state: EvidenceDeltaState
    source_collection_sha256_before: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_collection_sha256_after: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    outbound_attempt_count: int = Field(
        ge=0,
        le=MAX_OUTBOUND_SEARCH_ATTEMPTS,
    )
    call_audits: tuple[GapToolCallAudit, ...] = Field(default=(), max_length=2)
    accepted_sources: tuple[EvidenceSource, ...] = ()
    incremental_search_cost_usd: float | None = Field(default=0.0, ge=0.0)
    cost_state: Literal["known", "uninspectable"] = "known"
    trace_id: str = Field(min_length=8, max_length=128)
    failure_type: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _validate_totals(self) -> "EvidenceGapExecutionAudit":
        attempts = sum(call.outbound_attempt_count for call in self.call_audits)
        if attempts != self.outbound_attempt_count:
            raise ValueError("outbound_attempt_count must equal the call-audit total")
        accepted_ids = tuple(
            source_id
            for call in self.call_audits
            for source_id in call.accepted_source_ids
        )
        if accepted_ids != tuple(
            source.source_id for source in self.accepted_sources
        ):
            raise ValueError(
                "accepted sources must match call-audit registration order"
            )
        if (
            self.cost_state == "uninspectable"
            and self.incremental_search_cost_usd is not None
        ):
            raise ValueError("uninspectable total cost must be represented by null")
        if (
            self.cost_state == "known"
            and self.incremental_search_cost_usd is None
        ):
            raise ValueError("known total cost requires a numeric value")
        if self.evidence_delta_state == "augmented" and not self.accepted_sources:
            raise ValueError("augmented state requires accepted sources")
        if self.evidence_delta_state != "augmented" and self.accepted_sources:
            raise ValueError(
                f"{self.evidence_delta_state} cannot carry accepted sources"
            )
        if self.evidence_delta_state == "failed" and not self.failure_type:
            raise ValueError("failed execution requires a failure type")
        if self.evidence_delta_state != "failed" and self.failure_type:
            raise ValueError("only failed execution may carry a failure type")
        return self


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _plan_sha256(plan: ValidatedGapPlan) -> str:
    return _sha256_text(plan.model_dump_json(exclude_none=False))


def _host_matches(host: str, allowed: frozenset[str] | set[str]) -> bool:
    normalized = host.removeprefix("www.").lower()
    return any(
        normalized == domain or normalized.endswith(f".{domain}")
        for domain in allowed
    )


def _title_key(value: str) -> str:
    return " ".join(_TITLE_WORDS.findall(value.casefold()))


def _next_source_numbers(collection: SourceCollection) -> dict[str, int]:
    next_numbers: dict[str, int] = {}
    for domain, prefix in _PREFIX_BY_DOMAIN.items():
        numbers = [
            int(source.source_id[1:])
            for source in collection.sources_for_prefix(prefix)
            if (
                source.source_id.startswith(prefix)
                and source.source_id[1:].isdigit()
            )
        ]
        next_numbers[domain] = max(numbers, default=0) + 1
    return next_numbers


def _static_url_policy(
    value: str,
    *,
    call: ValidatedGapCall,
    context: GapContext,
) -> tuple[bool, RejectionCode | None, str, str | None]:
    """Validate a returned record without following its untrusted URL.

    The only outbound operation belongs to the fixed search-provider adapter.
    Fetching each result page here would silently multiply a two-request budget.
    Host policy therefore fails closed before a later production design can add
    separately accounted reachability requests.
    """

    try:
        parsed = urlsplit(value)
        canonical = _canonical_url(value)
    except (TypeError, ValueError) as exc:
        return (
            False,
            "unsupported_url",
            f"URL parsing failed: {type(exc).__name__}",
            None,
        )
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return (
            False,
            "unsupported_url",
            "only absolute HTTP(S) URLs are accepted",
            None,
        )
    if parsed.username or parsed.password:
        return (
            False,
            "credentialed_url",
            "URLs containing credentials are forbidden",
            None,
        )
    if " " in value:
        return (
            False,
            "unsupported_url",
            "URLs containing spaces are forbidden",
            None,
        )
    try:
        value.encode("ascii")
    except UnicodeError:
        return (
            False,
            "unsupported_url",
            "URLs must be ASCII before registration",
            None,
        )

    host = parsed.hostname.rstrip(".").casefold()
    if host == "localhost" or host.endswith(_BLOCKED_HOST_SUFFIXES):
        return (
            False,
            "non_public_literal_host",
            f"blocked host: {host}",
            None,
        )
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        # Even a currently global literal address has no stable publisher
        # identity and can later be reassigned; evidence links require names.
        return (
            False,
            "non_public_literal_host",
            "literal IP hosts are forbidden",
            None,
        )

    if call.tool == "academic_search":
        if not _host_matches(host, _ACADEMIC_RECORD_HOSTS):
            return (
                False,
                "host_not_allowlisted",
                f"academic record host is not approved: {host}",
                None,
            )
    elif call.tool == "patent_search":
        if host not in _PATENT_HOSTS:
            return (
                False,
                "wrong_evidence_domain",
                f"non-patent host returned by patent tool: {host}",
                None,
            )
    else:
        profile = _market_source_profile(canonical, host)
        if profile is None or profile[2].startswith(
            "First-party company page"
        ):
            return (
                False,
                "host_not_allowlisted",
                f"market record host is not approved: {host}",
                None,
            )
        if call.tool == "authority_search":
            category = _authority_category_for_url(canonical)
            if category is None:
                return (
                    False,
                    "wrong_evidence_domain",
                    "authority tool returned a non-authority URL",
                    None,
                )
            signal_by_id = {
                signal.signal_id: signal for signal in context.signals
            }
            expected = {
                signal_by_id[trigger].subject
                for trigger in call.trigger_ids
                if trigger in signal_by_id
            }
            if category not in expected:
                return (
                    False,
                    "wrong_authority_category",
                    (
                        f"authority category {category!r} was not requested "
                        f"by {sorted(expected)!r}"
                    ),
                    None,
                )
    return True, None, "", canonical


def _source_profile(
    *,
    call: ValidatedGapCall,
    canonical_url: str,
) -> tuple[str, str, str]:
    host = (urlsplit(canonical_url).hostname or "").casefold()
    if call.tool == "academic_search":
        return (
            "academic_paper",
            "medium",
            (
                "Structured academic index record; publication status and "
                "claims still require source review."
            ),
        )
    if call.tool == "patent_search":
        if host in _OFFICIAL_PATENT_HOSTS:
            return (
                "patent",
                "high",
                (
                    "Official patent-office record; legal scope still requires "
                    "claim review."
                ),
            )
        return (
            "patent",
            "medium",
            (
                "Approved patent aggregator record; verify legal status "
                "against the issuing office."
            ),
        )
    profile = _market_source_profile(canonical_url, host)
    if profile is None:
        # The static policy already rejected this branch. Raising makes future
        # policy drift fail closed instead of inventing a source type.
        raise EvidenceGapExecutionError(
            "market source profile disappeared after policy validation"
        )
    return profile


def _relevance_for_topic(
    source: EvidenceSource,
    collection: SourceCollection,
) -> int:
    variants = tuple(
        dict.fromkeys((collection.topic, *collection.search_aliases))
    )
    scores = []
    for topic in variants:
        domain_keywords = (
            frozenset()
            if source.source_type not in {"academic_paper", "patent"}
            else _topic_domain_keywords(topic)
        )
        scores.append(
            _relevance_score(
                source,
                _topic_keywords(topic),
                _topic_bigrams(topic),
                domain_keywords,
            )
        )
    return max(scores, default=-1)


def _candidate_to_source(
    candidate: ToolEvidenceCandidate,
    *,
    candidate_index: int,
    call: ValidatedGapCall,
    context: GapContext,
    collection: SourceCollection,
    next_numbers: dict[str, int],
    seen_urls: set[str],
    seen_dois: set[str],
    seen_titles: set[str],
) -> tuple[EvidenceSource | None, CandidateRejection | None]:
    safe, code, detail, canonical = _static_url_policy(
        candidate.url,
        call=call,
        context=context,
    )
    if not safe or code is not None or canonical is None:
        return None, CandidateRejection(
            candidate_index=candidate_index,
            code=code or "unsupported_url",
            detail=detail or "URL policy rejected the candidate",
        )

    normalized_doi = normalize_doi(candidate.doi)
    title_key = _title_key(candidate.title)
    if canonical in seen_urls:
        return None, CandidateRejection(
            candidate_index=candidate_index,
            code="duplicate_url",
            detail="canonical URL already exists in the evidence registry",
        )
    if normalized_doi and normalized_doi in seen_dois:
        return None, CandidateRejection(
            candidate_index=candidate_index,
            code="duplicate_doi",
            detail="canonical DOI already exists in the evidence registry",
        )
    if title_key in seen_titles:
        return None, CandidateRejection(
            candidate_index=candidate_index,
            code="duplicate_title",
            detail="normalized title already exists in the evidence registry",
        )

    source_type, credibility_tier, credibility_reason = _source_profile(
        call=call,
        canonical_url=canonical,
    )
    domain = call.output_domain
    source_id = f"{_PREFIX_BY_DOMAIN[domain]}{next_numbers[domain]}"
    try:
        source = EvidenceSource(
            source_id=source_id,
            title=candidate.title,
            url=canonical,
            doi=normalized_doi,
            publisher=candidate.publisher,
            published_date=candidate.published_date,
            accessed_date=collection.collected_at.date(),
            source_type=source_type,
            credibility_tier=credibility_tier,
            credibility_reason=credibility_reason,
            evidence_summary=candidate.evidence_summary,
            summary_source=candidate.summary_source,
            citation_count=candidate.citation_count,
        )
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        field = (
            ".".join(str(part) for part in first.get("loc", ()))
            or "unknown"
        )
        return None, CandidateRejection(
            candidate_index=candidate_index,
            code="source_schema_invalid",
            detail=f"EvidenceSource validation failed at {field}",
        )

    relevance = _relevance_for_topic(source, collection)
    if relevance < _MIN_RELEVANCE_BY_DOMAIN[domain]:
        return None, CandidateRejection(
            candidate_index=candidate_index,
            code="off_topic",
            detail=(
                f"relevance score {relevance} is below the frozen "
                f"{_MIN_RELEVANCE_BY_DOMAIN[domain]} threshold"
            ),
        )

    next_numbers[domain] += 1
    seen_urls.add(canonical)
    if normalized_doi:
        seen_dois.add(normalized_doi)
    seen_titles.add(title_key)
    return source, None


def _existing_registry(
    collection: SourceCollection,
) -> tuple[set[str], set[str], set[str]]:
    sources = (
        *collection.academic_sources,
        *collection.patent_sources,
        *collection.market_sources,
    )
    urls = {
        _canonical_url(str(source.url))
        for source in sources
        if source.url is not None
    }
    dois = {
        doi
        for source in sources
        if (doi := normalize_doi(source.doi))
    }
    titles = {_title_key(source.title) for source in sources}
    return urls, dois, titles


def _known_cost(
    values: list[float | None],
) -> tuple[Literal["known", "uninspectable"], float | None]:
    if any(value is None for value in values):
        return "uninspectable", None
    return "known", sum(value for value in values if value is not None)


def _non_search_result(
    *,
    collection_hash: str,
    plan: ValidatedGapPlan,
    trace_id: str,
) -> EvidenceGapExecutionAudit:
    return EvidenceGapExecutionAudit(
        decision=plan.decision,
        evidence_delta_state=(
            "incomplete" if plan.decision == "abstain" else "unchanged"
        ),
        source_collection_sha256_before=collection_hash,
        source_collection_sha256_after=collection_hash,
        plan_sha256=_plan_sha256(plan),
        outbound_attempt_count=0,
        trace_id=trace_id,
    )


def execute_gap_plan(
    collection: SourceCollection,
    *,
    context: GapContext,
    plan: ValidatedGapPlan,
    adapters: Mapping[GapToolName, ReadOnlySearchAdapter],
    trace_id: str,
) -> EvidenceGapExecutionAudit:
    """Execute a validated search plan under one global two-attempt budget."""

    before_hash = source_collection_sha256(collection)
    if context.source_collection_sha256 != before_hash:
        raise EvidenceGapExecutionError(
            "GapContext source hash does not identify the supplied "
            "SourceCollection"
        )
    if plan.decision != "search":
        return _non_search_result(
            collection_hash=before_hash,
            plan=plan,
            trace_id=trace_id,
        )

    next_numbers = _next_source_numbers(collection)
    seen_urls, seen_dois, seen_titles = _existing_registry(collection)
    call_audits: list[GapToolCallAudit] = []
    accepted_sources: list[EvidenceSource] = []
    total_attempts = 0
    all_costs: list[float | None] = []

    for call_index, call in enumerate(plan.calls):
        started = time.perf_counter()
        query_sha256 = _sha256_text(
            " ".join(call.query.split()).casefold()
        )
        adapter = adapters.get(call.tool)
        if adapter is None:
            call_audits.append(
                GapToolCallAudit(
                    call_index=call_index,
                    tool=call.tool,
                    trigger_ids=call.trigger_ids,
                    query_sha256=query_sha256,
                    idempotency_key=call.idempotency_key,
                    state="failed",
                    outbound_attempt_count=0,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    failure_type="adapter_unavailable",
                    trace_id=trace_id,
                )
            )
            continue

        remaining_calls = len(plan.calls) - call_index - 1
        attempts_available = (
            MAX_OUTBOUND_SEARCH_ATTEMPTS - total_attempts
        )
        # Reserve one attempt for each later planned call. A single-call plan
        # may retry once; a two-call plan cannot spend the second call's slot.
        attempts_for_call = max(
            0,
            attempts_available - remaining_calls,
        )
        if attempts_for_call == 0:
            call_audits.append(
                GapToolCallAudit(
                    call_index=call_index,
                    tool=call.tool,
                    trigger_ids=call.trigger_ids,
                    query_sha256=query_sha256,
                    idempotency_key=call.idempotency_key,
                    state="budget_exhausted",
                    outbound_attempt_count=0,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    failure_type="outbound_budget_exhausted",
                    trace_id=trace_id,
                )
            )
            continue

        attempt_count = 0
        call_costs: list[float | None] = []
        response: ToolAdapterResponse | None = None
        failure_type: str | None = None
        while attempt_count < attempts_for_call:
            attempt_count += 1
            total_attempts += 1
            try:
                raw_response = adapter(call)
                response = (
                    raw_response
                    if isinstance(raw_response, ToolAdapterResponse)
                    else ToolAdapterResponse.model_validate(raw_response)
                )
                call_costs.append(response.search_cost_usd)
                all_costs.append(response.search_cost_usd)
                if response.tool != call.tool:
                    raise EvidenceGapExecutionError(
                        "adapter returned a mismatched tool identity"
                    )
                if response.idempotency_key != call.idempotency_key:
                    raise EvidenceGapExecutionError(
                        "adapter returned a mismatched idempotency key"
                    )
                if len(response.candidates) > call.result_limit:
                    failure_type = "result_limit_exceeded"
                    response = None
                break
            except ToolAdapterFailure as exc:
                call_costs.append(exc.search_cost_usd)
                all_costs.append(exc.search_cost_usd)
                failure_type = exc.failure_type
                if exc.retryable and attempt_count < attempts_for_call:
                    continue
                break
            except (
                EvidenceGapExecutionError,
                ValidationError,
                TypeError,
                ValueError,
            ) as exc:
                # The provider attempt happened, but a malformed response may
                # omit its cost. It is therefore uninspectable, not free.
                if not call_costs:
                    call_costs.append(None)
                    all_costs.append(None)
                failure_type = (
                    f"adapter_contract_{type(exc).__name__}"
                )
                response = None
                break
            except Exception as exc:  # noqa: BLE001
                # Experimental adapters are injected third-party boundaries.
                # Unexpected exceptions remain failed attempts rather than
                # bringing down the surrounding offline audit.
                call_costs.append(None)
                all_costs.append(None)
                failure_type = (
                    f"adapter_unexpected_{type(exc).__name__}"
                )
                response = None
                break

        call_cost_state, call_cost = _known_cost(call_costs)
        if response is None:
            call_audits.append(
                GapToolCallAudit(
                    call_index=call_index,
                    tool=call.tool,
                    trigger_ids=call.trigger_ids,
                    query_sha256=query_sha256,
                    idempotency_key=call.idempotency_key,
                    state="failed",
                    outbound_attempt_count=attempt_count,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    search_cost_usd=call_cost,
                    cost_state=call_cost_state,
                    failure_type=(
                        failure_type or "adapter_failed_without_reason"
                    ),
                    trace_id=trace_id,
                )
            )
            continue

        accepted_for_call: list[str] = []
        rejections: list[CandidateRejection] = []
        for candidate_index, candidate in enumerate(response.candidates):
            source, rejection = _candidate_to_source(
                candidate,
                candidate_index=candidate_index,
                call=call,
                context=context,
                collection=collection,
                next_numbers=next_numbers,
                seen_urls=seen_urls,
                seen_dois=seen_dois,
                seen_titles=seen_titles,
            )
            if source is not None:
                accepted_sources.append(source)
                accepted_for_call.append(source.source_id)
            elif rejection is not None:
                rejections.append(rejection)

        if accepted_for_call:
            state: CallState = "accepted"
        elif response.candidates:
            state = "rejected"
        else:
            state = "empty"
        call_audits.append(
            GapToolCallAudit(
                call_index=call_index,
                tool=call.tool,
                trigger_ids=call.trigger_ids,
                query_sha256=query_sha256,
                idempotency_key=call.idempotency_key,
                state=state,
                outbound_attempt_count=attempt_count,
                raw_candidate_count=len(response.candidates),
                accepted_source_ids=tuple(accepted_for_call),
                rejections=tuple(rejections),
                latency_ms=(time.perf_counter() - started) * 1000,
                search_cost_usd=call_cost,
                cost_state=call_cost_state,
                trace_id=trace_id,
            )
        )

    after_hash = source_collection_sha256(collection)
    total_cost_state, total_cost = _known_cost(all_costs)
    if after_hash != before_hash:
        # Never publish candidates after input mutation: the audit could no
        # longer say which evidence set was evaluated.
        sanitized_calls = tuple(
            call.model_copy(
                update={
                    "accepted_source_ids": (),
                    "state": "failed",
                    "failure_type": "source_collection_mutated",
                }
            )
            if call.accepted_source_ids
            else call
            for call in call_audits
        )
        return EvidenceGapExecutionAudit(
            decision=plan.decision,
            evidence_delta_state="failed",
            source_collection_sha256_before=before_hash,
            source_collection_sha256_after=after_hash,
            plan_sha256=_plan_sha256(plan),
            outbound_attempt_count=total_attempts,
            call_audits=sanitized_calls,
            incremental_search_cost_usd=total_cost,
            cost_state=total_cost_state,
            trace_id=trace_id,
            failure_type="source_collection_mutated",
        )

    return EvidenceGapExecutionAudit(
        decision=plan.decision,
        evidence_delta_state=(
            "augmented" if accepted_sources else "incomplete"
        ),
        source_collection_sha256_before=before_hash,
        source_collection_sha256_after=after_hash,
        plan_sha256=_plan_sha256(plan),
        outbound_attempt_count=total_attempts,
        call_audits=tuple(call_audits),
        accepted_sources=tuple(accepted_sources),
        incremental_search_cost_usd=total_cost,
        cost_state=total_cost_state,
        trace_id=trace_id,
    )
