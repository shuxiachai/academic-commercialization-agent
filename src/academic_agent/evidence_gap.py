"""Zero-call contracts for the evidence-gap planner's shadow phase.

Phase 1 deliberately stops before model planning or supplementary retrieval.
It records whether an already validated ``SourceCollection`` contains one of a
small number of explicit gaps, and it validates proposed search intents when a
test or offline experiment injects a planner.  The production worker never
injects one in this phase, so enabling the feature adds no provider request and
cannot change the evidence sent to the six-stage workflow.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from academic_agent.source_pipeline import SourceCollection


EVIDENCE_GAP_SHADOW_ENV = "EVIDENCE_GAP_SHADOW_ENABLED"
EVIDENCE_GAP_SHADOW_FILENAME = "evidence_gap_shadow.json"
EVIDENCE_GAP_SCHEMA_VERSION = 1
MAX_GAP_TOOL_CALLS = 2

EvidenceDomain = Literal["academic", "patent", "market"]
GapScope = Literal["academic", "patent", "market", "cross_domain"]
GapSignalCode = Literal[
    "authority_category_missing",
    "component_missing",
    "retrieval_domain_failed",
]
GapToolName = Literal[
    "academic_search",
    "patent_search",
    "market_search",
    "authority_search",
]

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"", "0", "false", "no", "off"})
_KNOWN_DOMAINS: tuple[EvidenceDomain, ...] = ("academic", "patent", "market")
_DOMAIN_TO_TOOL: dict[EvidenceDomain, GapToolName] = {
    "academic": "academic_search",
    "patent": "patent_search",
    "market": "market_search",
}
_TOOL_TO_DOMAIN: dict[GapToolName, EvidenceDomain] = {
    "academic_search": "academic",
    "patent_search": "patent",
    "market_search": "market",
    # Regulatory and registry records remain M-domain evidence. Giving their
    # future adapter a distinct capability name must not create a fourth source
    # prefix that the report and citation guardrails do not understand.
    "authority_search": "market",
}
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_SCOPE_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_SCOPE_STOP_WORDS = frozenset(
    {
        "and",
        "for",
        "from",
        "into",
        "of",
        "on",
        "the",
        "to",
        "using",
        "via",
        "with",
    }
)
_AUTHORITY_SCOPE_TERMS = {
    "regulatory": frozenset(
        {"approval", "authorization", "ema", "fda", "regulatory"}
    ),
    "clinical_registry": frozenset(
        {"clinical", "clinicaltrials", "registry", "trial"}
    ),
}


class EvidenceGapError(ValueError):
    """Raised when a shadow proposal violates its frozen execution contract."""


class ShadowConfiguration(BaseModel):
    """Parsed feature state; invalid text is visible rather than silently off."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal["enabled", "disabled", "invalid"]
    raw_value: str


class GapSignal(BaseModel):
    """One deterministic reason a run is eligible for later gap planning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_id: str = Field(min_length=8, max_length=24)
    code: GapSignalCode
    scope: GapScope
    subject: str = Field(min_length=1, max_length=240)
    allowed_tools: tuple[GapToolName, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_contract(self) -> "GapSignal":
        if self.code == "authority_category_missing":
            expected_scope: GapScope = "market"
            expected_tools: tuple[GapToolName, ...] = ("authority_search",)
        elif self.code == "component_missing":
            expected_scope = "cross_domain"
            expected_tools = (
                "academic_search",
                "patent_search",
                "market_search",
            )
        else:
            if self.scope == "cross_domain":
                raise ValueError("a failed retrieval domain must name one known domain")
            expected_scope = self.scope
            expected_tools = (_DOMAIN_TO_TOOL[self.scope],)
        if self.scope != expected_scope or self.allowed_tools != expected_tools:
            raise ValueError(
                f"signal contract mismatch for {self.code}: "
                f"scope={self.scope}, tools={self.allowed_tools}"
            )
        return self


class GapContext(BaseModel):
    """Immutable, non-secret input made available to a future planner."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = EVIDENCE_GAP_SCHEMA_VERSION
    topic: str = Field(min_length=3, max_length=1000)
    source_collection_sha256: str
    source_counts: dict[EvidenceDomain, int]
    signals: tuple[GapSignal, ...] = ()
    max_tool_calls: Literal[2] = MAX_GAP_TOOL_CALLS

    @field_validator("source_collection_sha256")
    @classmethod
    def _validate_hash(cls, value: str) -> str:
        if not _HEX_64.fullmatch(value):
            raise ValueError("source_collection_sha256 must be a lowercase SHA-256")
        return value

    @model_validator(mode="after")
    def _validate_counts_and_signals(self) -> "GapContext":
        if set(self.source_counts) != set(_KNOWN_DOMAINS):
            raise ValueError("source_counts must contain academic, patent, and market")
        if any(count < 0 for count in self.source_counts.values()):
            raise ValueError("source counts cannot be negative")
        signal_ids = [signal.signal_id for signal in self.signals]
        if len(signal_ids) != len(set(signal_ids)):
            raise ValueError("gap signal ids must be unique")
        return self


class GapSearchIntent(BaseModel):
    """One read-only search proposed by an injected/offline planner."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: GapToolName
    query: str = Field(min_length=3, max_length=500)
    trigger_ids: tuple[str, ...] = Field(min_length=1, max_length=4)
    result_limit: int = Field(default=5, ge=1, le=10)

    @field_validator("query")
    @classmethod
    def _normalise_query(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 3:
            raise ValueError("query must contain at least three non-space characters")
        return value

    @field_validator("trigger_ids")
    @classmethod
    def _unique_triggers(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("trigger_ids must be unique within one intent")
        return value


class GapPlanProposal(BaseModel):
    """Strict JSON boundary for a later planner model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = EVIDENCE_GAP_SCHEMA_VERSION
    decision: Literal["no_gap", "search", "abstain"]
    rationale: str = Field(min_length=10, max_length=1200)
    calls: tuple[GapSearchIntent, ...] = Field(
        default=(), max_length=MAX_GAP_TOOL_CALLS
    )

    @model_validator(mode="after")
    def _validate_decision_shape(self) -> "GapPlanProposal":
        if self.decision == "search" and not self.calls:
            raise ValueError("a search decision requires at least one intent")
        if self.decision != "search" and self.calls:
            raise ValueError(f"{self.decision} cannot include search intents")
        return self


class ValidatedGapCall(GapSearchIntent):
    """A proposal joined to its execution domain and local idempotency key."""

    output_domain: EvidenceDomain
    idempotency_key: str

    @field_validator("idempotency_key")
    @classmethod
    def _validate_idempotency_key(cls, value: str) -> str:
        if not _HEX_64.fullmatch(value):
            raise ValueError("idempotency_key must be a lowercase SHA-256")
        return value


class ValidatedGapPlan(BaseModel):
    """A proposal that is safe to hand to a future bounded executor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = EVIDENCE_GAP_SCHEMA_VERSION
    decision: Literal["no_gap", "search", "abstain"]
    rationale: str
    calls: tuple[ValidatedGapCall, ...] = Field(
        default=(), max_length=MAX_GAP_TOOL_CALLS
    )


class EvidenceGapShadowAudit(BaseModel):
    """Persisted phase-1 observation, including explicit non-execution state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = EVIDENCE_GAP_SCHEMA_VERSION
    mode: Literal["shadow"] = "shadow"
    gate_state: Literal["disabled", "no_gap", "eligible", "failed"]
    planner_state: Literal["not_run", "planned", "abstained", "failed"]
    checked: bool
    context: GapContext | None = None
    plan: ValidatedGapPlan | None = None
    proposed_call_count: int = Field(default=0, ge=0, le=MAX_GAP_TOOL_CALLS)
    executed_call_count: int = Field(default=0, ge=0, le=0)
    added_search_cost_usd: float = Field(default=0.0, ge=0.0, le=0.0)
    planner_latency_ms: float | None = Field(default=None, ge=0.0)
    evidence_changed: bool = False
    failure_type: str | None = None
    persistence_state: Literal["not_attempted", "written", "failed"] = (
        "not_attempted"
    )
    persistence_error_type: str | None = None

    @model_validator(mode="after")
    def _validate_states(self) -> "EvidenceGapShadowAudit":
        if self.executed_call_count != 0 or self.added_search_cost_usd != 0.0:
            raise ValueError("phase 1 cannot execute or charge for search calls")
        if self.proposed_call_count != len(self.plan.calls if self.plan else ()):
            raise ValueError("proposed_call_count must match the validated plan")
        if self.gate_state == "disabled":
            if self.checked or self.context is not None or self.plan is not None:
                raise ValueError("disabled shadow mode cannot claim an evaluation")
        elif self.gate_state == "no_gap":
            if not self.checked or self.context is None or self.context.signals:
                raise ValueError("no_gap requires a checked context with zero signals")
        elif self.gate_state == "eligible":
            if not self.checked or self.context is None or not self.context.signals:
                raise ValueError("eligible requires a checked context with signals")
        elif self.checked:
            raise ValueError("failed gate state cannot be reported as checked")

        if self.planner_state == "planned":
            if self.plan is None or self.plan.decision != "search":
                raise ValueError("planned requires a validated search plan")
        elif self.planner_state == "abstained":
            if self.plan is None or self.plan.decision != "abstain":
                raise ValueError("abstained requires a validated abstention")
        elif self.planner_state == "failed":
            if self.plan is not None or not self.failure_type:
                raise ValueError("planner failure requires a failure type and no plan")
        elif self.plan is not None:
            raise ValueError("not_run cannot carry a plan")

        if self.persistence_state == "failed" and not self.persistence_error_type:
            raise ValueError("failed persistence requires its error type")
        if self.persistence_state != "failed" and self.persistence_error_type:
            raise ValueError("persistence error is only valid for failed persistence")
        return self


GapPlanner = Callable[[GapContext], GapPlanProposal | dict[str, Any]]


def parse_shadow_configuration(raw_value: str | None) -> ShadowConfiguration:
    """Parse one environment value without treating a typo as disabled."""

    normalized = (raw_value or "").strip().casefold()
    if normalized in _TRUE_VALUES:
        state: Literal["enabled", "disabled", "invalid"] = "enabled"
    elif normalized in _FALSE_VALUES:
        state = "disabled"
    else:
        state = "invalid"
    return ShadowConfiguration(state=state, raw_value=normalized)


def shadow_configuration_from_environment() -> ShadowConfiguration:
    """Read the opt-in flag at execution time, not at module import time."""

    return parse_shadow_configuration(os.getenv(EVIDENCE_GAP_SHADOW_ENV))


def source_collection_sha256(collection: SourceCollection) -> str:
    """Hash the complete validated input using a canonical JSON projection."""

    payload = json.dumps(
        collection.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _signal_id(code: GapSignalCode, subject: str) -> str:
    identity = f"{code}\0{' '.join(subject.split()).casefold()}".encode()
    return f"gap-{hashlib.sha256(identity).hexdigest()[:16]}"


def build_gap_context(collection: SourceCollection) -> GapContext:
    """Derive only explicit high-precision signals from validated evidence."""

    signals: list[GapSignal] = []
    for category in collection.authority_coverage.missing_categories:
        signals.append(
            GapSignal(
                signal_id=_signal_id("authority_category_missing", category),
                code="authority_category_missing",
                scope="market",
                subject=category,
                allowed_tools=("authority_search",),
            )
        )

    # Partial and unchecked are intentionally excluded. They mean the lexical
    # diagnostic itself cannot decide coverage, which is too weak a basis for
    # spending a search request in a precision-first gate.
    if collection.component_coverage.status == "incomplete":
        for component in collection.component_coverage.missing_components:
            signals.append(
                GapSignal(
                    signal_id=_signal_id("component_missing", component),
                    code="component_missing",
                    scope="cross_domain",
                    subject=component,
                    allowed_tools=(
                        "academic_search",
                        "patent_search",
                        "market_search",
                    ),
                )
            )

    for domain in _KNOWN_DOMAINS:
        if domain not in collection.failed_domains:
            continue
        signals.append(
            GapSignal(
                signal_id=_signal_id("retrieval_domain_failed", domain),
                code="retrieval_domain_failed",
                scope=domain,
                subject=domain,
                allowed_tools=(_DOMAIN_TO_TOOL[domain],),
            )
        )

    return GapContext(
        topic=collection.topic,
        source_collection_sha256=source_collection_sha256(collection),
        source_counts={
            "academic": len(collection.academic_sources),
            "patent": len(collection.patent_sources),
            "market": len(collection.market_sources),
        },
        signals=tuple(signals),
    )


def _scope_tokens(value: str) -> frozenset[str]:
    return frozenset(
        token
        for token in _SCOPE_TOKEN.findall(value.casefold())
        if token not in _SCOPE_STOP_WORDS
    )


def _validate_query_scope(
    context: GapContext,
    intent: GapSearchIntent,
    signal_by_id: dict[str, GapSignal],
) -> None:
    """Keep a valid tool name from becoming an arbitrary-search capability."""

    query_tokens = _scope_tokens(intent.query)
    topic_tokens = _scope_tokens(context.topic)
    required_topic_overlap = min(2, len(topic_tokens))
    if (
        required_topic_overlap
        and len(query_tokens & topic_tokens) < required_topic_overlap
    ):
        raise EvidenceGapError(
            "search query is outside the authorized topic scope"
        )

    for trigger_id in intent.trigger_ids:
        signal = signal_by_id[trigger_id]
        if signal.code == "component_missing":
            if not query_tokens & _scope_tokens(signal.subject):
                raise EvidenceGapError(
                    "component search query does not name its missing component"
                )
        elif signal.code == "authority_category_missing":
            category_terms = _AUTHORITY_SCOPE_TERMS[signal.subject]
            if not query_tokens & category_terms:
                raise EvidenceGapError(
                    "authority search query does not name its missing category"
                )


def validate_gap_plan(
    context: GapContext,
    proposal: GapPlanProposal | dict[str, Any],
) -> ValidatedGapPlan:
    """Join a strict proposal to trigger authorization and idempotency data."""

    parsed = (
        proposal
        if isinstance(proposal, GapPlanProposal)
        else GapPlanProposal.model_validate(proposal)
    )
    signal_by_id = {signal.signal_id: signal for signal in context.signals}
    if not signal_by_id and parsed.decision != "no_gap":
        raise EvidenceGapError("a context without signals can only return no_gap")
    if signal_by_id and parsed.decision == "no_gap":
        raise EvidenceGapError("an eligible context must search or explicitly abstain")

    calls: list[ValidatedGapCall] = []
    seen_intents: set[tuple[str, str, int, tuple[str, ...]]] = set()
    for intent in parsed.calls:
        unknown = sorted(set(intent.trigger_ids) - set(signal_by_id))
        if unknown:
            raise EvidenceGapError(f"intent references unknown trigger ids: {unknown}")
        unauthorized = [
            signal_id
            for signal_id in intent.trigger_ids
            if intent.tool not in signal_by_id[signal_id].allowed_tools
        ]
        if unauthorized:
            raise EvidenceGapError(
                f"tool {intent.tool} is not authorized by triggers {unauthorized}"
            )

        _validate_query_scope(context, intent, signal_by_id)

        normalized_query = " ".join(intent.query.split()).casefold()
        normalized_triggers = tuple(sorted(intent.trigger_ids))
        duplicate_key = (
            intent.tool,
            normalized_query,
            intent.result_limit,
            normalized_triggers,
        )
        if duplicate_key in seen_intents:
            raise EvidenceGapError("duplicate search intents are not allowed")
        seen_intents.add(duplicate_key)
        identity_payload = json.dumps(
            {
                "collection": context.source_collection_sha256,
                "tool": intent.tool,
                "query": normalized_query,
                "result_limit": intent.result_limit,
                "trigger_ids": normalized_triggers,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        calls.append(
            ValidatedGapCall(
                **intent.model_dump(exclude={"trigger_ids"}),
                trigger_ids=normalized_triggers,
                output_domain=_TOOL_TO_DOMAIN[intent.tool],
                idempotency_key=hashlib.sha256(identity_payload).hexdigest(),
            )
        )

    return ValidatedGapPlan(
        decision=parsed.decision,
        rationale=parsed.rationale,
        calls=tuple(calls),
    )


def _failed_audit(
    *,
    context: GapContext | None,
    failure_type: str,
    latency_ms: float | None = None,
    evidence_changed: bool = False,
) -> EvidenceGapShadowAudit:
    return EvidenceGapShadowAudit(
        gate_state="eligible" if context and context.signals else "failed",
        planner_state="failed" if context and context.signals else "not_run",
        checked=bool(context and context.signals),
        context=context,
        planner_latency_ms=latency_ms,
        evidence_changed=evidence_changed,
        failure_type=failure_type,
    )


def run_shadow_assessment(
    collection: SourceCollection,
    *,
    configuration: ShadowConfiguration,
    planner: GapPlanner | None = None,
) -> EvidenceGapShadowAudit:
    """Evaluate or plan in shadow mode while guaranteeing zero tool execution."""

    if configuration.state == "disabled":
        return EvidenceGapShadowAudit(
            gate_state="disabled",
            planner_state="not_run",
            checked=False,
        )
    if configuration.state == "invalid":
        return _failed_audit(
            context=None,
            failure_type="invalid_configuration",
        )

    try:
        context = build_gap_context(collection)
        before_hash = source_collection_sha256(collection)
    except (TypeError, ValueError) as exc:
        return _failed_audit(
            context=None,
            failure_type=f"gate_{type(exc).__name__}",
        )
    if not context.signals:
        return EvidenceGapShadowAudit(
            gate_state="no_gap",
            planner_state="not_run",
            checked=True,
            context=context,
        )
    if planner is None:
        return EvidenceGapShadowAudit(
            gate_state="eligible",
            planner_state="not_run",
            checked=True,
            context=context,
        )

    started = time.perf_counter()
    try:
        plan = validate_gap_plan(context, planner(context))
    except Exception as exc:  # noqa: BLE001
        # An injected planner is an advisory shadow component. Any provider,
        # parse, or schema failure must be observable without discarding the
        # already paid deterministic retrieval and six-stage assessment.
        latency_ms = (time.perf_counter() - started) * 1000
        after_hash = source_collection_sha256(collection)
        if after_hash != before_hash:
            return _failed_audit(
                context=context,
                failure_type="source_collection_mutated",
                latency_ms=latency_ms,
                evidence_changed=True,
            )
        return _failed_audit(
            context=context,
            failure_type=f"planner_{type(exc).__name__}",
            latency_ms=latency_ms,
        )
    latency_ms = (time.perf_counter() - started) * 1000
    after_hash = source_collection_sha256(collection)
    if after_hash != before_hash:
        return _failed_audit(
            context=context,
            failure_type="source_collection_mutated",
            latency_ms=latency_ms,
            evidence_changed=True,
        )
    return EvidenceGapShadowAudit(
        gate_state="eligible",
        planner_state="planned" if plan.decision == "search" else "abstained",
        checked=True,
        context=context,
        plan=plan,
        proposed_call_count=len(plan.calls),
        planner_latency_ms=latency_ms,
    )


def refresh_coverage_for_offline_audit(collection: SourceCollection) -> SourceCollection:
    """Recompute diagnostics for legacy fixtures that predate coverage fields.

    This helper is intentionally named for offline audit use. Runtime
    collections already carry the diagnostics computed by retrieval; silently
    recomputing them later would make the artifact differ from what the report
    actually saw.
    """

    from academic_agent.source_pipeline import (
        _measure_authority_coverage,
        _measure_component_coverage,
    )

    refreshed = collection.model_copy(deep=True)
    refreshed.authority_coverage = _measure_authority_coverage(
        refreshed.topic,
        refreshed.weight_profile,
        refreshed.market_sources,
    )
    refreshed.component_coverage = _measure_component_coverage(
        refreshed.search_components,
        (
            *refreshed.academic_sources,
            *refreshed.patent_sources,
            *refreshed.market_sources,
        ),
    )
    return refreshed


def persist_shadow_audit(
    run_directory: Path,
    audit: EvidenceGapShadowAudit,
) -> EvidenceGapShadowAudit:
    """Atomically persist the audit and return the state safe for status.json."""

    target = run_directory / EVIDENCE_GAP_SHADOW_FILENAME
    temporary = target.with_suffix(".json.tmp")
    written = audit.model_copy(update={"persistence_state": "written"})
    try:
        run_directory.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(written.model_dump_json(indent=2))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except OSError as exc:
        with contextlib.suppress(OSError):
            temporary.unlink()
        return audit.model_copy(
            update={
                "persistence_state": "failed",
                "persistence_error_type": type(exc).__name__,
            }
        )
    return written
