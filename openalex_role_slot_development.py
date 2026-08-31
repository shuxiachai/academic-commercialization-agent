"""Write-once Y01-Y08 runner for role-slot consensus v6.

The default CLI path is a zero-network preflight.  A live development attempt
requires two explicit budget acknowledgements and two bounded soft stops.  The
global method manifest is durable before constructing an OpenAlex adapter; for
each successful provider response, the exact three-request model plan is
durable before constructing or invoking the Qwen adapter.  Every request
journal is written before another request may begin.

This runner is deliberately disconnected from the production worker, report
workflow, planner trigger, private labels, and the frozen Z01-Z08 unseen cohort.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal, Protocol, cast
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from academic_agent.evidence_gap import (
    ValidatedGapCall,
    ValidatedGapPlan,
    source_collection_sha256,
)
from academic_agent.openalex_claim_scope import OpenAlexClaimScopeCandidate
from academic_agent.openalex_role_slot import (
    RoleSlotBatchInput,
    RoleSlotCaseAudit,
    build_role_slot_inputs,
    build_role_slot_prompts,
    evaluate_role_slot_case,
)
from academic_agent.source_pipeline import SourceCollection
from academic_agent.tools.evidence_search import ToolAdapterFailure
from academic_agent.tools.openalex_claim_scope_search import (
    AnonymousOpenAlexClaimScopeAdapter,
    OpenAlexClaimScopeAdapterResponse,
)
from academic_agent.tools.qwen_role_slot_judge import (
    QWEN_ROLE_SLOT_MAX_TOKENS,
    QWEN_ROLE_SLOT_MODEL,
    QWEN_ROLE_SLOT_TIMEOUT_SECONDS,
    QwenRoleSlotJudgeAdapter,
    QwenRoleSlotJudgeError,
    QwenRoleSlotRequest,
    QwenRoleSlotResponse,
    QwenRoleSlotUsageObservation,
    RoleSlotCandidateOrder,
    prompt_sha256,
)
from openalex_role_slot_unseen import (
    DEFAULT_FIXTURE_PATH,
    EXPECTED_FIXTURE_SHA256,
    OpenAlexRoleSlotPreflightError,
    PreparedRoleSlotCase,
    RoleSlotCaseSpec,
    RoleSlotChallengeManifest,
    dry_run as phase_one_dry_run,
    load_frozen_cases,
)


_ROOT = Path(__file__).resolve().parent
_RUNNER_PATH = Path(__file__).resolve()
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_CASE_ORDER = tuple(f"Y{index:02d}" for index in range(1, 9))
_CANDIDATE_ORDERS: tuple[RoleSlotCandidateOrder, ...] = (
    "provider_order",
    "reverse_provider_order",
    "candidate_sha256_order",
)
MAXIMUM_OPENALEX_REQUEST_COUNT = 8
MAXIMUM_MODEL_CALL_COUNT = 24
MAXIMUM_OPENALEX_SOFT_STOP_USD = 0.01
MAXIMUM_MODEL_SOFT_STOP_USD = 0.25
ANONYMOUS_OPENALEX_DAILY_BUDGET_USD = 0.10
_MAX_PROVIDER_RESPONSE_BYTES = 1_000_000
_PROVIDER_ROW_COLUMNS = (
    "case_id",
    "provider_result_index",
    "adapter_disposition",
    "candidate_sha256",
    "title",
    "url",
    "doi",
    "publisher",
    "published_date",
    "abstract",
    "provider_rejection_code",
    "rejection_detail",
    "provider_request_id",
    "provider_cost_basis",
    "trace_id",
)

_IMPLEMENTATION_PATHS = {
    "domain_evidence_search.py": (
        _ROOT / "src/academic_agent/tools/domain_evidence_search.py"
    ),
    "evidence.py": _ROOT / "src/academic_agent/evidence.py",
    "evidence_gap.py": _ROOT / "src/academic_agent/evidence_gap.py",
    "evidence_search.py": _ROOT / "src/academic_agent/tools/evidence_search.py",
    "openalex_claim_scope.py": _ROOT / "src/academic_agent/openalex_claim_scope.py",
    "openalex_claim_scope_search.py": (
        _ROOT / "src/academic_agent/tools/openalex_claim_scope_search.py"
    ),
    "openalex_evidence_set.py": (
        _ROOT / "src/academic_agent/openalex_evidence_set.py"
    ),
    "openalex_role_slot.py": _ROOT / "src/academic_agent/openalex_role_slot.py",
    "openalex_role_slot_unseen.py": _ROOT / "openalex_role_slot_unseen.py",
    "qwen_role_slot_judge.py": (
        _ROOT / "src/academic_agent/tools/qwen_role_slot_judge.py"
    ),
    "source_pipeline.py": _ROOT / "src/academic_agent/source_pipeline.py",
    "token_usage.py": _ROOT / "src/academic_agent/token_usage.py",
}

# Populated from committed implementation bytes before any provider call.  The
# runner itself remains an observed hash because embedding its expected digest
# in itself would create a recursive identity.
EXPECTED_IMPLEMENTATION_SHA256 = {
    "domain_evidence_search.py": (
        "ae79c38378321f6ce4481e682787ee49f930ec4c34b696d404fcf78d97b2eeab"
    ),
    "evidence.py": "8e9eda3126dc1b81ec5a97e23ecfce8ba64c59a0d77c9a3fb3aec259f07b38c5",
    "evidence_gap.py": (
        "f2b978ce2af6b4e1d759116466d5a79371e6e4a7e414198b728b427cd93eea25"
    ),
    "evidence_search.py": (
        "2721debe3bb193b8971f8a89db0f4c91342944cb232f1829c02dd8d3780422d0"
    ),
    "openalex_claim_scope.py": (
        "739e165838ff5042ec863c3c510311e737216e8d90804c8d3da5095acce22f16"
    ),
    "openalex_claim_scope_search.py": (
        "070d07ac8c4bcaa32bfbc563513b4034162b012aea1f47ce3208ed06cb085642"
    ),
    "openalex_evidence_set.py": (
        "413bf6cea1c555c75bd80aaadae720cbf00886974acfdd443643f6a2f75e992c"
    ),
    "openalex_role_slot.py": (
        "166eb6d6568a7a187e2f6654c27d3db938a79553c0205501d9328b38437ed8d4"
    ),
    "openalex_role_slot_unseen.py": (
        "3bd69fa0a6703c1b928c905fbde1ce5639aaa3559c2a54f3356cbdb914800a75"
    ),
    "qwen_role_slot_judge.py": (
        "e0bb13862169de8dfd1efbffbcddaf6a88582690865160953a4de49b668a5f84"
    ),
    "source_pipeline.py": (
        "056a545325bc231b1501bbf53cc993faaba55adb0e9c222db6c0b45b90628286"
    ),
    "token_usage.py": (
        "884a314cb6dfa9393afb74e71cdf54e77c22404f647772e88d3845ec89a0acac"
    ),
}


class OpenAlexRoleSlotDevelopmentError(ValueError):
    """Raised before or at one explicit experimental boundary."""


class FrozenRoleSlotCaseArtifact(BaseModel):
    """All code-owned identities committed before provider construction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    spec: RoleSlotCaseSpec
    collection_sha256: str = Field(pattern=_SHA256_PATTERN)
    plan_sha256: str = Field(pattern=_SHA256_PATTERN)
    profile_sha256: str = Field(pattern=_SHA256_PATTERN)
    case_contract_sha256: str = Field(pattern=_SHA256_PATTERN)
    judge_request_template_sha256s: tuple[str, str, str]
    source_collection: SourceCollection
    validated_plan: ValidatedGapPlan

    @model_validator(mode="after")
    def _validate_expansion(self) -> "FrozenRoleSlotCaseArtifact":
        if source_collection_sha256(self.source_collection) != self.collection_sha256:
            raise ValueError("expanded source collection identity drifted")
        observed_plan = _sha256_bytes(
            self.validated_plan.model_dump_json(exclude_none=False).encode("utf-8")
        )
        if observed_plan != self.plan_sha256:
            raise ValueError("expanded validated plan identity drifted")
        if self.spec.roles.profile().sha256() != self.profile_sha256:
            raise ValueError("expanded role profile identity drifted")
        if len(set(self.judge_request_template_sha256s)) != 3:
            raise ValueError("judge request template identities must be distinct")
        if len(self.validated_plan.calls) != 1:
            raise ValueError("each frozen case must retain exactly one provider call")
        return self


class RoleSlotDevelopmentManifest(BaseModel):
    """Durable global method boundary written before any client exists."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["openalex_role_slot_v6_development_manifest"] = (
        "openalex_role_slot_v6_development_manifest"
    )
    cohort: Literal["development"] = "development"
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    planner_trigger_connected: Literal[False] = False
    private_labels_opened: Literal[False] = False
    unseen_cohort_opened: Literal[False] = False
    openalex_access_mode: Literal["anonymous_no_key"] = "anonymous_no_key"
    requested_model: Literal["qwen3.5-plus"] = QWEN_ROLE_SLOT_MODEL
    fixture_sha256: str = Field(pattern=_SHA256_PATTERN)
    implementation_sha256: dict[str, str]
    runner_sha256: str = Field(pattern=_SHA256_PATTERN)
    method_id: str = Field(min_length=20, max_length=200)
    provider_contract_sha256: str = Field(pattern=_SHA256_PATTERN)
    judge_contract_sha256: str = Field(pattern=_SHA256_PATTERN)
    selection_contract_sha256: str = Field(pattern=_SHA256_PATTERN)
    maximum_openalex_request_count: Literal[8] = MAXIMUM_OPENALEX_REQUEST_COUNT
    maximum_model_call_count: Literal[24] = MAXIMUM_MODEL_CALL_COUNT
    openalex_soft_stop_usd: float = Field(
        gt=0.0,
        le=MAXIMUM_OPENALEX_SOFT_STOP_USD,
    )
    model_soft_stop_usd: float = Field(gt=0.0, le=MAXIMUM_MODEL_SOFT_STOP_USD)
    model_transport_timeout_seconds: Literal[120.0] = (
        QWEN_ROLE_SLOT_TIMEOUT_SECONDS
    )
    model_max_tokens: Literal[8000] = QWEN_ROLE_SLOT_MAX_TOKENS
    cases: tuple[FrozenRoleSlotCaseArtifact, ...] = Field(
        min_length=8,
        max_length=8,
    )

    @model_validator(mode="after")
    def _validate_manifest(self) -> "RoleSlotDevelopmentManifest":
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("manifest fixture identity drifted")
        if tuple(case.spec.case_id for case in self.cases) != _CASE_ORDER:
            raise ValueError("manifest cases must remain Y01 through Y08")
        if set(self.implementation_sha256) != set(_IMPLEMENTATION_PATHS):
            raise ValueError("manifest implementation lock names drifted")
        if any(
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in self.implementation_sha256.values()
        ):
            raise ValueError("manifest implementation hashes are invalid")
        return self


class RoleSlotModelPlan(BaseModel):
    """Three exact requests persisted after retrieval and before Qwen."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^Y0[1-8]$")
    provider_response_sha256: str = Field(pattern=_SHA256_PATTERN)
    profile_sha256: str = Field(pattern=_SHA256_PATTERN)
    inputs: tuple[RoleSlotBatchInput, RoleSlotBatchInput, RoleSlotBatchInput]
    requests: tuple[
        QwenRoleSlotRequest,
        QwenRoleSlotRequest,
        QwenRoleSlotRequest,
    ]

    @model_validator(mode="after")
    def _validate_plan(self) -> "RoleSlotModelPlan":
        candidate_sets: list[set[str]] = []
        for pass_number, (candidate_order, batch, request) in enumerate(
            zip(_CANDIDATE_ORDERS, self.inputs, self.requests, strict=True),
            start=1,
        ):
            if (
                batch.case_id != self.case_id
                or request.case_id != self.case_id
                or batch.pass_number != pass_number
                or request.pass_number != pass_number
                or request.candidate_order != candidate_order
                or request.batch_input_sha256 != batch.sha256()
            ):
                raise ValueError("model plan request identity drifted")
            candidate_sets.append(
                {candidate.candidate_sha256 for candidate in batch.candidates}
            )
        if any(value != candidate_sets[0] for value in candidate_sets[1:]):
            raise ValueError("all model passes must contain the same candidates")
        provider_order = tuple(
            item.candidate_sha256 for item in self.inputs[0].candidates
        )
        if tuple(
            item.candidate_sha256 for item in self.inputs[1].candidates
        ) != tuple(reversed(provider_order)):
            raise ValueError("reverse-provider model order drifted")
        if tuple(
            item.candidate_sha256 for item in self.inputs[2].candidates
        ) != tuple(sorted(provider_order)):
            raise ValueError("candidate-SHA model order drifted")
        return self


ProviderJournalState = Literal["completed", "failed"]
ModelJournalState = Literal["completed", "failed"]


class RoleSlotProviderJournal(BaseModel):
    """One anonymous OpenAlex request and complete returned-row accounting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^Y0[1-8]$")
    collection_sha256: str = Field(pattern=_SHA256_PATTERN)
    plan_sha256: str = Field(pattern=_SHA256_PATTERN)
    profile_sha256: str = Field(pattern=_SHA256_PATTERN)
    idempotency_key: str = Field(pattern=_SHA256_PATTERN)
    trace_id: str = Field(pattern=r"^openalex-role-slot-v6-y0[1-8]$")
    state: ProviderJournalState
    outbound_attempt_count: Literal[1] = 1
    response: OpenAlexClaimScopeAdapterResponse | None = None
    failure_type: str | None = Field(default=None, max_length=100)
    failure_detail: str | None = Field(default=None, max_length=500)
    failure_retryable: bool | None = None
    request_may_have_spent: Literal[True] = True
    search_cost_usd: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    latency_ms: float = Field(ge=0.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _validate_journal(self) -> "RoleSlotProviderJournal":
        expected_trace = f"openalex-role-slot-v6-{self.case_id.casefold()}"
        if self.trace_id != expected_trace:
            raise ValueError("provider trace identity drifted")
        failures = (
            self.failure_type,
            self.failure_detail,
            self.failure_retryable,
        )
        if self.state == "completed":
            if self.response is None or any(value is not None for value in failures):
                raise ValueError("completed provider journal requires only a response")
            if self.response.idempotency_key != self.idempotency_key:
                raise ValueError("provider response idempotency identity drifted")
            if self.response.search_cost_usd != self.search_cost_usd:
                raise ValueError("provider cost drifted from response")
            if self.response.provider_usage.result_count > 8:
                raise ValueError("provider returned more than eight rows")
        elif self.failure_type is None or self.failure_detail is None:
            raise ValueError("failed provider journal requires failure metadata")
        elif self.response is not None and (
            self.response.search_cost_usd != self.search_cost_usd
        ):
            raise ValueError("failed provider cost drifted from retained response")
        return self


class RoleSlotModelJournal(BaseModel):
    """One potentially billed Qwen call written before a later call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^Y0[1-8]$")
    pass_number: Literal[1, 2, 3]
    candidate_order: RoleSlotCandidateOrder
    state: ModelJournalState
    request: QwenRoleSlotRequest
    response: QwenRoleSlotResponse | None = None
    observed_returned_model: str | None = Field(default=None, max_length=200)
    observed_usage: QwenRoleSlotUsageObservation | None = None
    observed_latency_ms: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    failure_type: str | None = Field(default=None, max_length=100)
    failure_detail: str | None = Field(default=None, max_length=500)
    failure_retryable: bool | None = None
    request_may_have_spent: bool

    @model_validator(mode="after")
    def _validate_journal(self) -> "RoleSlotModelJournal":
        if (
            self.request.case_id != self.case_id
            or self.request.pass_number != self.pass_number
            or self.request.candidate_order != self.candidate_order
        ):
            raise ValueError("model journal request identity drifted")
        failures = (
            self.failure_type,
            self.failure_detail,
            self.failure_retryable,
        )
        observations = (self.observed_returned_model, self.observed_usage)
        if self.state == "completed":
            if (
                self.response is None
                or any(value is not None for value in failures)
                or any(value is not None for value in observations)
                or self.observed_latency_ms is not None
                or not self.request_may_have_spent
            ):
                raise ValueError("completed model journal requires only a response")
            if _response_identity_drift(self.request, self.response):
                raise ValueError("completed response identity drifted from request")
        elif self.response is not None or any(value is None for value in failures):
            raise ValueError("failed model journal requires only failure metadata")
        if self.observed_usage is not None and self.observed_returned_model is None:
            raise ValueError("observed usage requires a returned model")
        if not self.request_may_have_spent and any(
            value is not None for value in observations
        ):
            raise ValueError("non-spending failure cannot carry provider usage")
        return self


CaseExecutionState = Literal[
    "completed",
    "no_candidates",
    "provider_failed",
    "model_incomplete",
]


class RoleSlotCaseExecution(BaseModel):
    """One provider journal, optional model plan, calls and deterministic audit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^Y0[1-8]$")
    state: CaseExecutionState
    provider_journal: RoleSlotProviderJournal
    model_plan: RoleSlotModelPlan | None = None
    model_calls: tuple[RoleSlotModelJournal, ...] = Field(max_length=3)
    case_audit: RoleSlotCaseAudit | None = None

    @model_validator(mode="after")
    def _validate_case(self) -> "RoleSlotCaseExecution":
        if self.provider_journal.case_id != self.case_id:
            raise ValueError("case provider journal identity drifted")
        response = self.provider_journal.response
        candidate_count = len(response.candidates) if response is not None else 0
        if self.state == "provider_failed":
            if (
                self.provider_journal.state != "failed"
                or self.model_plan is not None
                or self.model_calls
                or self.case_audit is not None
            ):
                raise ValueError("provider-failed case cannot imply model work")
            return self
        if self.provider_journal.state != "completed" or response is None:
            raise ValueError("non-provider-failed case requires a completed provider")
        if self.state == "no_candidates":
            if (
                candidate_count
                or self.model_plan is not None
                or self.model_calls
                or self.case_audit is not None
            ):
                raise ValueError("no-candidate case cannot imply model work")
            return self
        if candidate_count == 0 or self.model_plan is None:
            raise ValueError("model case requires candidates and a persisted plan")
        if self.model_plan.case_id != self.case_id:
            raise ValueError("case model plan identity drifted")
        planned_ids = {
            item.candidate_sha256 for item in self.model_plan.inputs[0].candidates
        }
        response_ids = {item.sha256() for item in response.candidates}
        if planned_ids != response_ids:
            raise ValueError("model plan candidates drifted from provider response")
        expected_calls = self.model_plan.requests[: len(self.model_calls)]
        if tuple(item.request for item in self.model_calls) != expected_calls:
            raise ValueError("model calls must preserve the planned request prefix")
        if self.state == "completed":
            if (
                len(self.model_calls) != 3
                or any(call.state != "completed" for call in self.model_calls)
                or self.case_audit is None
            ):
                raise ValueError("completed case requires three calls and one audit")
            if self.case_audit.case_id != self.case_id:
                raise ValueError("case audit identity drifted")
            if self.case_audit.provider_candidate_count != candidate_count:
                raise ValueError("every provider candidate must reach the case audit")
        elif self.case_audit is not None:
            raise ValueError("incomplete model case cannot carry a final audit")
        return self


StopReason = Literal[
    "completed",
    "openalex_soft_stop",
    "model_soft_stop",
    "provider_failed",
    "model_failed",
    "accounting_invalid",
]
CostState = Literal["known", "uninspectable", "not_observed"]
MechanicalGateState = Literal["pass", "fail", "not_evaluated"]


class RoleSlotDevelopmentExecution(BaseModel):
    """Final mechanical state; human-value gates remain unopened."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["openalex_role_slot_v6_development_execution"] = (
        "openalex_role_slot_v6_development_execution"
    )
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    planner_trigger_connected: Literal[False] = False
    private_labels_opened: Literal[False] = False
    unseen_cohort_opened: Literal[False] = False
    manifest_sha256: str = Field(pattern=_SHA256_PATTERN)
    overall_state: Literal["completed", "partial"]
    stop_reason: StopReason
    openalex_request_count: int = Field(ge=0, le=8)
    openalex_successful_case_count: int = Field(ge=0, le=8)
    openalex_cost_state: CostState
    openalex_cost_usd: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    model_call_count: int = Field(ge=0, le=24)
    model_completed_call_count: int = Field(ge=0, le=24)
    model_cost_state: CostState
    model_cost_usd: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    prompt_tokens: int = Field(ge=0)
    cached_prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    provider_row_count: int = Field(ge=0, le=64)
    provider_candidate_count: int = Field(ge=0, le=64)
    provider_rejection_count: int = Field(ge=0, le=64)
    completed_case_audit_count: int = Field(ge=0, le=8)
    selected_case_count: int = Field(ge=0, le=8)
    top_level_valid_pass_numerator: int = Field(ge=0, le=24)
    top_level_valid_pass_denominator: int = Field(ge=0, le=24)
    top_level_valid_pass_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    top_level_contract_gate_passed: bool | None
    local_valid_row_numerator: int = Field(ge=0, le=192)
    local_valid_row_denominator: int = Field(ge=0, le=192)
    local_valid_row_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    local_valid_row_gate_passed: bool | None
    provisional_unanimity_numerator: int = Field(ge=0, le=64)
    provisional_unanimity_denominator: int = Field(ge=0, le=64)
    provisional_unanimity_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    provisional_unanimity_gate_passed: bool | None
    selected_case_coverage_gate_passed: bool | None
    audit_boundary_complete: bool
    mechanical_gate_state: MechanicalGateState
    source_lock_readiness: Literal["ready", "not_ready"]
    human_review_state: Literal["not_prepared"] = "not_prepared"
    source_value_state: Literal["not_evaluated"] = "not_evaluated"
    cases: tuple[RoleSlotCaseExecution, ...] = Field(max_length=8)

    @model_validator(mode="after")
    def _validate_execution(self) -> "RoleSlotDevelopmentExecution":
        case_ids = tuple(case.case_id for case in self.cases)
        if case_ids != _CASE_ORDER[: len(case_ids)]:
            raise ValueError("execution cases must preserve the frozen prefix")
        provider_journals = tuple(case.provider_journal for case in self.cases)
        if self.openalex_request_count != len(provider_journals):
            raise ValueError("provider request total drifted from journals")
        provider_successes = sum(
            journal.state == "completed" for journal in provider_journals
        )
        if self.openalex_successful_case_count != provider_successes:
            raise ValueError("provider success total drifted")
        provider_responses = tuple(
            journal.response
            for journal in provider_journals
            if journal.response is not None
        )
        candidate_count = sum(len(response.candidates) for response in provider_responses)
        rejection_count = sum(
            len(response.provider_rejections) for response in provider_responses
        )
        if (
            self.provider_candidate_count,
            self.provider_rejection_count,
            self.provider_row_count,
        ) != (
            candidate_count,
            rejection_count,
            candidate_count + rejection_count,
        ):
            raise ValueError("provider row totals drifted from journals")
        calls = tuple(call for case in self.cases for call in case.model_calls)
        if self.model_call_count != len(calls):
            raise ValueError("model call total drifted from journals")
        completed_calls = sum(call.state == "completed" for call in calls)
        if self.model_completed_call_count != completed_calls:
            raise ValueError("completed model call total drifted")
        usages = tuple(
            usage for call in calls if (usage := _model_journal_usage(call)) is not None
        )
        if (
            self.prompt_tokens,
            self.cached_prompt_tokens,
            self.completion_tokens,
            self.total_tokens,
        ) != (
            sum(item.prompt_tokens for item in usages),
            sum(item.cached_prompt_tokens for item in usages),
            sum(item.completion_tokens for item in usages),
            sum(item.total_tokens for item in usages),
        ):
            raise ValueError("aggregate model tokens drifted from journals")
        expected_provider_state, expected_provider_cost = _provider_cost(provider_journals)
        if (self.openalex_cost_state, self.openalex_cost_usd) != (
            expected_provider_state,
            expected_provider_cost,
        ):
            raise ValueError("aggregate OpenAlex cost drifted from journals")
        expected_model_state, expected_model_cost = _model_cost(calls)
        if self.model_cost_state != expected_model_state:
            raise ValueError("aggregate model cost state drifted from journals")
        if expected_model_cost is None:
            if self.model_cost_usd is not None:
                raise ValueError("unknown model cost cannot carry a numeric total")
        elif self.model_cost_usd is None or not math.isclose(
            self.model_cost_usd,
            expected_model_cost,
            abs_tol=1e-12,
        ):
            raise ValueError("aggregate model cost drifted from journals")
        audits = tuple(
            case.case_audit for case in self.cases if case.case_audit is not None
        )
        if self.completed_case_audit_count != len(audits):
            raise ValueError("completed case-audit total drifted")
        if self.selected_case_count != sum(audit.action == "SELECT" for audit in audits):
            raise ValueError("selected-case total drifted")
        valid_passes = sum(
            pass_audit.state == "valid" for audit in audits for pass_audit in audit.passes
        )
        pass_denominator = sum(len(audit.passes) for audit in audits)
        local_numerator = sum(audit.local_valid_row_numerator for audit in audits)
        local_denominator = sum(audit.local_valid_row_denominator for audit in audits)
        unanimity_numerator = sum(
            audit.provisional_unanimity_numerator for audit in audits
        )
        unanimity_denominator = sum(
            audit.provisional_unanimity_denominator for audit in audits
        )
        _validate_rate(
            self.top_level_valid_pass_numerator,
            self.top_level_valid_pass_denominator,
            self.top_level_valid_pass_rate,
            valid_passes,
            pass_denominator,
            "top-level pass",
        )
        _validate_rate(
            self.local_valid_row_numerator,
            self.local_valid_row_denominator,
            self.local_valid_row_rate,
            local_numerator,
            local_denominator,
            "local row",
        )
        _validate_rate(
            self.provisional_unanimity_numerator,
            self.provisional_unanimity_denominator,
            self.provisional_unanimity_rate,
            unanimity_numerator,
            unanimity_denominator,
            "provisional unanimity",
        )
        complete = (
            len(self.cases) == 8
            and all(
                case.state in {"completed", "no_candidates"} for case in self.cases
            )
            and self.stop_reason == "completed"
        )
        if (self.overall_state == "completed") != complete:
            raise ValueError("overall completion drifted from case journals")
        expected_top = valid_passes == pass_denominator if pass_denominator else None
        expected_local = (
            local_numerator / local_denominator >= 0.95
            if local_denominator
            else None
        )
        expected_unanimity = (
            unanimity_numerator / unanimity_denominator >= 0.8
            if unanimity_denominator
            else None
        )
        expected_selected = self.selected_case_count >= 6 if complete else None
        if (
            self.top_level_contract_gate_passed,
            self.local_valid_row_gate_passed,
            self.provisional_unanimity_gate_passed,
            self.selected_case_coverage_gate_passed,
        ) != (expected_top, expected_local, expected_unanimity, expected_selected):
            raise ValueError("mechanical gate values drifted from audit metrics")
        expected_boundary = _audit_boundary_complete(self.cases)
        if self.audit_boundary_complete != expected_boundary:
            raise ValueError("audit-boundary state drifted from child artifacts")
        all_gates = (
            expected_top,
            expected_local,
            expected_unanimity,
            expected_selected,
            expected_boundary if complete else None,
        )
        expected_gate_state: MechanicalGateState
        if not complete:
            expected_gate_state = "not_evaluated"
        elif all(value is True for value in all_gates):
            expected_gate_state = "pass"
        else:
            expected_gate_state = "fail"
        if self.mechanical_gate_state != expected_gate_state:
            raise ValueError("mechanical gate state drifted")
        expected_readiness = "ready" if complete and expected_boundary else "not_ready"
        if self.source_lock_readiness != expected_readiness:
            raise ValueError("source-lock readiness drifted")
        return self


ProviderAdapter = Callable[
    [ValidatedGapCall],
    OpenAlexClaimScopeAdapterResponse | dict[str, Any],
]
ProviderAdapterFactory = Callable[[], ProviderAdapter]


class ModelAdapter(Protocol):
    def __call__(
        self,
        request: QwenRoleSlotRequest,
    ) -> QwenRoleSlotResponse | dict[str, Any]: ...


ModelAdapterFactory = Callable[[], ModelAdapter]
Clock = Callable[[], float]


class _NoRedirectHandler(HTTPRedirectHandler):
    """Reject redirects because one case authorizes one OpenAlex request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        del req, fp, code, msg, headers, newurl
        return None


class _OneRequestTransport:
    """Concrete OpenAlex transport with no redirect or retry behavior."""

    def __call__(
        self,
        *,
        endpoint: str,
        method: str,
        body: bytes | None,
        headers: Mapping[str, str],
        timeout: float,
    ) -> bytes:
        request = Request(endpoint, data=body, headers=dict(headers), method=method)
        opener = build_opener(_NoRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            return response.read(_MAX_PROVIDER_RESPONSE_BYTES + 1)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _model_sha256(value: BaseModel) -> str:
    return _sha256_bytes(value.model_dump_json(exclude_none=False).encode("utf-8"))


def _json_text(value: BaseModel | dict[str, Any] | list[Any]) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write_new(path: Path, value: str) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(value)
    except OSError as exc:
        raise OpenAlexRoleSlotDevelopmentError(
            f"could not create write-once artifact {path}: {exc}"
        ) from exc


def _safe_validation_detail(exc: ValidationError) -> str:
    details = []
    for error in exc.errors(include_input=False)[:4]:
        location = ".".join(str(part) for part in error["loc"]) or "response"
        details.append(f"{location}:{error['type']}")
    return "; ".join(details)[:500] or "response validation failed"


def _elapsed_ms(clock: Clock, started_at: float) -> float:
    elapsed = (clock() - started_at) * 1000.0
    if not math.isfinite(elapsed):
        raise OpenAlexRoleSlotDevelopmentError("request clock became non-finite")
    return max(0.0, elapsed)


def _validate_rate(
    numerator: int,
    denominator: int,
    rate: float | None,
    expected_numerator: int,
    expected_denominator: int,
    label: str,
) -> None:
    if (numerator, denominator) != (expected_numerator, expected_denominator):
        raise ValueError(f"{label} counts drifted")
    expected_rate = numerator / denominator if denominator else None
    if expected_rate is None:
        if rate is not None:
            raise ValueError(f"zero {label} denominator cannot report a rate")
    elif rate is None or not math.isclose(rate, expected_rate, abs_tol=1e-12):
        raise ValueError(f"{label} rate drifted")


def verify_frozen_implementation(
    expected: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Reject dependency drift before output reservation or client creation."""

    expected_hashes = dict(
        EXPECTED_IMPLEMENTATION_SHA256 if expected is None else expected
    )
    if set(expected_hashes) != set(_IMPLEMENTATION_PATHS):
        raise OpenAlexRoleSlotDevelopmentError(
            "v6 implementation lock names are inconsistent"
        )
    observed = {
        name: _file_sha256(path) for name, path in _IMPLEMENTATION_PATHS.items()
    }
    if observed != expected_hashes:
        changed = sorted(
            name
            for name, digest in observed.items()
            if expected_hashes.get(name) != digest
        )
        raise OpenAlexRoleSlotDevelopmentError(
            "v6 implementation identity drifted: " + ", ".join(changed)
        )
    return observed


def _frozen_case(case: PreparedRoleSlotCase) -> FrozenRoleSlotCaseArtifact:
    return FrozenRoleSlotCaseArtifact(
        spec=case.spec,
        collection_sha256=case.collection_sha256,
        plan_sha256=case.plan_sha256,
        profile_sha256=case.profile_sha256,
        case_contract_sha256=case.case_contract_sha256,
        judge_request_template_sha256s=case.judge_request_template_sha256s,
        source_collection=case.collection,
        validated_plan=case.plan,
    )


def _manifest(
    fixture_sha256: str,
    challenge: RoleSlotChallengeManifest,
    cases: tuple[PreparedRoleSlotCase, ...],
    implementation_sha256: dict[str, str],
    *,
    openalex_soft_stop_usd: float,
    model_soft_stop_usd: float,
) -> RoleSlotDevelopmentManifest:
    return RoleSlotDevelopmentManifest(
        fixture_sha256=fixture_sha256,
        implementation_sha256=implementation_sha256,
        runner_sha256=_file_sha256(_RUNNER_PATH),
        method_id=challenge.method_id,
        provider_contract_sha256=challenge.provider_contract.sha256(),
        judge_contract_sha256=challenge.judge_contract.sha256(),
        selection_contract_sha256=challenge.selection_contract.sha256(),
        openalex_soft_stop_usd=openalex_soft_stop_usd,
        model_soft_stop_usd=model_soft_stop_usd,
        cases=tuple(_frozen_case(case) for case in cases),
    )


def protocol_dry_run(
    *,
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    expected_fixture_sha256: str = EXPECTED_FIXTURE_SHA256,
    expected_implementation_sha256: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Verify every frozen byte and template while constructing no adapter."""

    phase_one = phase_one_dry_run(
        "development",
        fixture_path,
        expected_fixture_sha256=expected_fixture_sha256,
    )
    implementation = verify_frozen_implementation(expected_implementation_sha256)
    return {
        "mode": "openalex_role_slot_v6_development_dry_run",
        "cohort": "development",
        "production_connected": False,
        "report_workflow_connected": False,
        "planner_trigger_connected": False,
        "private_labels_opened": False,
        "unseen_cohort_opened": False,
        "real_network_calls_performed": False,
        "real_model_calls_performed": False,
        "fixture_sha256": phase_one["fixture_sha256"],
        "implementation_sha256": implementation,
        "runner_sha256": _file_sha256(_RUNNER_PATH),
        "case_count": phase_one["case_count"],
        "maximum_openalex_request_count": MAXIMUM_OPENALEX_REQUEST_COUNT,
        "maximum_model_call_count": MAXIMUM_MODEL_CALL_COUNT,
        "requested_model": QWEN_ROLE_SLOT_MODEL,
        "model_transport_timeout_seconds": QWEN_ROLE_SLOT_TIMEOUT_SECONDS,
        "model_max_tokens": QWEN_ROLE_SLOT_MAX_TOKENS,
        "cases": phase_one["cases"],
    }


def _judge_request(
    batch: RoleSlotBatchInput,
    candidate_order: RoleSlotCandidateOrder,
) -> QwenRoleSlotRequest:
    system_prompt, user_prompt = build_role_slot_prompts(batch)
    return QwenRoleSlotRequest(
        case_id=batch.case_id,
        pass_number=batch.pass_number,
        candidate_order=candidate_order,
        trace_id=(
            f"openalex-v6-{batch.case_id.casefold()}-pass-{batch.pass_number}"
        ),
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        batch_input_sha256=batch.sha256(),
        prompt_sha256=prompt_sha256(system_prompt, user_prompt),
    )


def _model_plan(
    case: PreparedRoleSlotCase,
    response: OpenAlexClaimScopeAdapterResponse,
) -> RoleSlotModelPlan:
    candidates = cast(
        tuple[OpenAlexClaimScopeCandidate, ...],
        response.candidates,
    )
    inputs = build_role_slot_inputs(
        case_id=case.spec.case_id,
        topic=case.spec.topic,
        profile=case.spec.roles.profile(),
        candidates=candidates,
    )
    requests = tuple(
        _judge_request(batch, candidate_order)
        for batch, candidate_order in zip(inputs, _CANDIDATE_ORDERS, strict=True)
    )
    return RoleSlotModelPlan(
        case_id=case.spec.case_id,
        provider_response_sha256=_model_sha256(response),
        profile_sha256=case.profile_sha256,
        inputs=inputs,
        requests=cast(
            tuple[QwenRoleSlotRequest, QwenRoleSlotRequest, QwenRoleSlotRequest],
            requests,
        ),
    )


def _response_identity_drift(
    request: QwenRoleSlotRequest,
    response: QwenRoleSlotResponse,
) -> tuple[str, ...]:
    expected = {
        "case_id": request.case_id,
        "pass_number": request.pass_number,
        "candidate_order": request.candidate_order,
        "trace_id": request.trace_id,
        "batch_input_sha256": request.batch_input_sha256,
        "prompt_sha256": request.prompt_sha256,
        "requested_model": request.requested_model,
    }
    observed = {
        "case_id": response.case_id,
        "pass_number": response.pass_number,
        "candidate_order": response.candidate_order,
        "trace_id": response.trace_id,
        "batch_input_sha256": response.batch_input_sha256,
        "prompt_sha256": response.prompt_sha256,
        "requested_model": response.requested_model,
    }
    return tuple(key for key in expected if expected[key] != observed[key])


def _model_journal_usage(
    journal: RoleSlotModelJournal,
) -> QwenRoleSlotUsageObservation | None:
    if journal.response is not None:
        return journal.response.usage
    return journal.observed_usage


def _provider_cost(
    journals: tuple[RoleSlotProviderJournal, ...],
) -> tuple[CostState, float | None]:
    if not journals:
        return "not_observed", None
    values = tuple(journal.search_cost_usd for journal in journals)
    if any(value is None for value in values):
        return "uninspectable", None
    return "known", sum(value for value in values if value is not None)


def _model_cost(
    journals: tuple[RoleSlotModelJournal, ...],
) -> tuple[CostState, float | None]:
    if not journals:
        return "not_observed", None
    usages = tuple(_model_journal_usage(journal) for journal in journals)
    known = all(
        not journal.request_may_have_spent
        or (usage is not None and usage.cost_usd is not None)
        for journal, usage in zip(journals, usages, strict=True)
    )
    if not known:
        return "uninspectable", None
    return (
        "known",
        sum(
            usage.cost_usd
            for usage in usages
            if usage is not None and usage.cost_usd is not None
        ),
    )


def _audit_boundary_complete(
    cases: tuple[RoleSlotCaseExecution, ...],
) -> bool:
    if len(cases) != 8:
        return False
    for case in cases:
        response = case.provider_journal.response
        if response is None:
            return False
        if case.state == "no_candidates":
            if response.candidates:
                return False
            continue
        if case.state != "completed" or case.case_audit is None:
            return False
        candidate_ids = {candidate.sha256() for candidate in response.candidates}
        audit_ids = {
            candidate.candidate_sha256
            for candidate in case.case_audit.candidate_decisions
        }
        if candidate_ids != audit_ids:
            return False
        for pass_audit in case.case_audit.passes:
            if {row.candidate_sha256 for row in pass_audit.candidate_rows} != candidate_ids:
                return False
            expected_slot_count = len(case.model_plan.inputs[0].roles)
            if any(len(row.slots) != expected_slot_count for row in pass_audit.candidate_rows):
                return False
    return True


def _write_provider_journal(
    output_dir: Path,
    journal: RoleSlotProviderJournal,
) -> None:
    directory = output_dir / "provider-journals"
    directory.mkdir(exist_ok=True)
    _write_new(directory / f"{journal.case_id}.json", _json_text(journal))


def _write_model_plan(output_dir: Path, plan: RoleSlotModelPlan) -> None:
    directory = output_dir / "model-plans"
    directory.mkdir(exist_ok=True)
    _write_new(directory / f"{plan.case_id}.json", _json_text(plan))


def _write_model_journal(
    output_dir: Path,
    journal: RoleSlotModelJournal,
) -> None:
    directory = output_dir / "model-journals"
    directory.mkdir(exist_ok=True)
    _write_new(
        directory / f"{journal.case_id}-pass-{journal.pass_number}.json",
        _json_text(journal),
    )


def _write_case_audit(output_dir: Path, audit: RoleSlotCaseAudit) -> None:
    directory = output_dir / "case-audits"
    directory.mkdir(exist_ok=True)
    _write_new(directory / f"{audit.case_id}.json", _json_text(audit))


def _write_case_execution(
    output_dir: Path,
    execution: RoleSlotCaseExecution,
) -> None:
    directory = output_dir / "case-executions"
    directory.mkdir(exist_ok=True)
    _write_new(directory / f"{execution.case_id}.json", _json_text(execution))


def _provider_rows(
    cases: tuple[RoleSlotCaseExecution, ...],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for case in cases:
        journal = case.provider_journal
        response = journal.response
        if response is None:
            continue
        usage = response.provider_usage
        for candidate in response.candidates:
            evidence = candidate.evidence
            index = evidence.provider_result_index
            if index is None:
                raise OpenAlexRoleSlotDevelopmentError(
                    "provider candidate lost its result index"
                )
            rows.append(
                {
                    "case_id": case.case_id,
                    "provider_result_index": str(index),
                    "adapter_disposition": "candidate",
                    "candidate_sha256": candidate.sha256(),
                    "title": evidence.title,
                    "url": evidence.url,
                    "doi": evidence.doi or "",
                    "publisher": evidence.publisher,
                    "published_date": (
                        evidence.published_date.isoformat()
                        if evidence.published_date is not None
                        else ""
                    ),
                    "abstract": evidence.evidence_summary,
                    "provider_rejection_code": "",
                    "rejection_detail": "",
                    "provider_request_id": response.provider_request_id,
                    "provider_cost_basis": usage.cost_basis,
                    "trace_id": journal.trace_id,
                }
            )
        for rejection in response.provider_rejections:
            rows.append(
                {
                    "case_id": case.case_id,
                    "provider_result_index": str(rejection.provider_result_index),
                    "adapter_disposition": "provider_rejected",
                    "candidate_sha256": "",
                    "title": rejection.title or "",
                    "url": rejection.url or "",
                    "doi": "",
                    "publisher": "",
                    "published_date": "",
                    "abstract": "",
                    "provider_rejection_code": rejection.code,
                    "rejection_detail": rejection.detail,
                    "provider_request_id": response.provider_request_id,
                    "provider_cost_basis": usage.cost_basis,
                    "trace_id": journal.trace_id,
                }
            )
    rows.sort(key=lambda row: (row["case_id"], int(row["provider_result_index"])))
    return rows


def _csv_text(columns: tuple[str, ...], rows: list[dict[str, str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _execution_artifact(
    *,
    manifest_sha256: str,
    stop_reason: StopReason,
    cases: list[RoleSlotCaseExecution],
) -> RoleSlotDevelopmentExecution:
    frozen_cases = tuple(cases)
    provider_journals = tuple(case.provider_journal for case in frozen_cases)
    model_journals = tuple(
        call for case in frozen_cases for call in case.model_calls
    )
    provider_state, provider_cost = _provider_cost(provider_journals)
    model_state, model_cost = _model_cost(model_journals)
    usages = tuple(
        usage
        for journal in model_journals
        if (usage := _model_journal_usage(journal)) is not None
    )
    responses = tuple(
        journal.response
        for journal in provider_journals
        if journal.response is not None
    )
    audits = tuple(
        case.case_audit for case in frozen_cases if case.case_audit is not None
    )
    complete = (
        stop_reason == "completed"
        and len(frozen_cases) == 8
        and all(
            case.state in {"completed", "no_candidates"} for case in frozen_cases
        )
    )
    valid_passes = sum(
        pass_audit.state == "valid" for audit in audits for pass_audit in audit.passes
    )
    pass_denominator = sum(len(audit.passes) for audit in audits)
    local_numerator = sum(audit.local_valid_row_numerator for audit in audits)
    local_denominator = sum(audit.local_valid_row_denominator for audit in audits)
    unanimity_numerator = sum(
        audit.provisional_unanimity_numerator for audit in audits
    )
    unanimity_denominator = sum(
        audit.provisional_unanimity_denominator for audit in audits
    )
    selected_case_count = sum(audit.action == "SELECT" for audit in audits)
    top_gate = valid_passes == pass_denominator if pass_denominator else None
    local_gate = (
        local_numerator / local_denominator >= 0.95 if local_denominator else None
    )
    unanimity_gate = (
        unanimity_numerator / unanimity_denominator >= 0.8
        if unanimity_denominator
        else None
    )
    selected_gate = selected_case_count >= 6 if complete else None
    boundary = _audit_boundary_complete(frozen_cases)
    if not complete:
        gate_state: MechanicalGateState = "not_evaluated"
    elif all(
        value is True
        for value in (top_gate, local_gate, unanimity_gate, selected_gate, boundary)
    ):
        gate_state = "pass"
    else:
        gate_state = "fail"
    return RoleSlotDevelopmentExecution(
        manifest_sha256=manifest_sha256,
        overall_state="completed" if complete else "partial",
        stop_reason=stop_reason,
        openalex_request_count=len(provider_journals),
        openalex_successful_case_count=sum(
            journal.state == "completed" for journal in provider_journals
        ),
        openalex_cost_state=provider_state,
        openalex_cost_usd=provider_cost,
        model_call_count=len(model_journals),
        model_completed_call_count=sum(
            journal.state == "completed" for journal in model_journals
        ),
        model_cost_state=model_state,
        model_cost_usd=model_cost,
        prompt_tokens=sum(usage.prompt_tokens for usage in usages),
        cached_prompt_tokens=sum(usage.cached_prompt_tokens for usage in usages),
        completion_tokens=sum(usage.completion_tokens for usage in usages),
        total_tokens=sum(usage.total_tokens for usage in usages),
        provider_row_count=sum(
            len(response.candidates) + len(response.provider_rejections)
            for response in responses
        ),
        provider_candidate_count=sum(len(response.candidates) for response in responses),
        provider_rejection_count=sum(
            len(response.provider_rejections) for response in responses
        ),
        completed_case_audit_count=len(audits),
        selected_case_count=selected_case_count,
        top_level_valid_pass_numerator=valid_passes,
        top_level_valid_pass_denominator=pass_denominator,
        top_level_valid_pass_rate=(
            valid_passes / pass_denominator if pass_denominator else None
        ),
        top_level_contract_gate_passed=top_gate,
        local_valid_row_numerator=local_numerator,
        local_valid_row_denominator=local_denominator,
        local_valid_row_rate=(
            local_numerator / local_denominator if local_denominator else None
        ),
        local_valid_row_gate_passed=local_gate,
        provisional_unanimity_numerator=unanimity_numerator,
        provisional_unanimity_denominator=unanimity_denominator,
        provisional_unanimity_rate=(
            unanimity_numerator / unanimity_denominator
            if unanimity_denominator
            else None
        ),
        provisional_unanimity_gate_passed=unanimity_gate,
        selected_case_coverage_gate_passed=selected_gate,
        audit_boundary_complete=boundary,
        mechanical_gate_state=gate_state,
        source_lock_readiness="ready" if complete and boundary else "not_ready",
        cases=frozen_cases,
    )


def _write_final_artifacts(
    output_dir: Path,
    execution: RoleSlotDevelopmentExecution,
) -> None:
    _write_new(output_dir / "execution.json", _json_text(execution))
    _write_new(
        output_dir / "provider-rows.csv",
        _csv_text(_PROVIDER_ROW_COLUMNS, _provider_rows(execution.cases)),
    )
    _write_new(
        output_dir / "case-audits.json",
        _json_text(
            [
                case.case_audit.model_dump(mode="json")
                for case in execution.cases
                if case.case_audit is not None
            ]
        ),
    )
    indexed = [
        "manifest.json",
        "execution.json",
        "provider-rows.csv",
        "case-audits.json",
    ]
    for case in execution.cases:
        indexed.append(f"provider-journals/{case.case_id}.json")
        indexed.append(f"case-executions/{case.case_id}.json")
        if case.model_plan is not None:
            indexed.append(f"model-plans/{case.case_id}.json")
        indexed.extend(
            f"model-journals/{call.case_id}-pass-{call.pass_number}.json"
            for call in case.model_calls
        )
        if case.case_audit is not None:
            indexed.append(f"case-audits/{case.case_id}.json")
    index = {
        "schema_version": 1,
        "mode": "openalex_role_slot_v6_development_artifact_index",
        "production_connected": False,
        "report_workflow_connected": False,
        "planner_trigger_connected": False,
        "files": {name: _file_sha256(output_dir / name) for name in indexed},
    }
    _write_new(output_dir / "artifact-index.json", _json_text(index))


def _failed_provider_journal(
    case: PreparedRoleSlotCase,
    *,
    failure_type: str,
    failure_detail: str,
    failure_retryable: bool | None,
    latency_ms: float,
    search_cost_usd: float | None,
    response: OpenAlexClaimScopeAdapterResponse | None = None,
) -> RoleSlotProviderJournal:
    return RoleSlotProviderJournal(
        case_id=case.spec.case_id,
        collection_sha256=case.collection_sha256,
        plan_sha256=case.plan_sha256,
        profile_sha256=case.profile_sha256,
        idempotency_key=case.plan.calls[0].idempotency_key,
        trace_id=f"openalex-role-slot-v6-{case.spec.case_id.casefold()}",
        state="failed",
        response=response,
        failure_type=failure_type,
        failure_detail=failure_detail[:500],
        failure_retryable=failure_retryable,
        search_cost_usd=search_cost_usd,
        latency_ms=latency_ms,
    )


def _completed_provider_journal(
    case: PreparedRoleSlotCase,
    response: OpenAlexClaimScopeAdapterResponse,
    latency_ms: float,
) -> RoleSlotProviderJournal:
    return RoleSlotProviderJournal(
        case_id=case.spec.case_id,
        collection_sha256=case.collection_sha256,
        plan_sha256=case.plan_sha256,
        profile_sha256=case.profile_sha256,
        idempotency_key=case.plan.calls[0].idempotency_key,
        trace_id=f"openalex-role-slot-v6-{case.spec.case_id.casefold()}",
        state="completed",
        response=response,
        search_cost_usd=response.search_cost_usd,
        latency_ms=latency_ms,
    )


def _failed_model_journal(
    request: QwenRoleSlotRequest,
    *,
    failure_type: str,
    failure_detail: str,
    failure_retryable: bool,
    request_may_have_spent: bool,
    observed_returned_model: str | None = None,
    observed_usage: QwenRoleSlotUsageObservation | None = None,
    observed_latency_ms: float | None = None,
) -> RoleSlotModelJournal:
    return RoleSlotModelJournal(
        case_id=request.case_id,
        pass_number=request.pass_number,
        candidate_order=request.candidate_order,
        state="failed",
        request=request,
        observed_returned_model=observed_returned_model,
        observed_usage=observed_usage,
        observed_latency_ms=observed_latency_ms,
        failure_type=failure_type,
        failure_detail=failure_detail[:500],
        failure_retryable=failure_retryable,
        request_may_have_spent=request_may_have_spent,
    )


def execute_development_study(
    *,
    output_dir: Path,
    openalex_soft_stop_usd: float,
    model_soft_stop_usd: float,
    acknowledge_anonymous_daily_budget: bool,
    acknowledge_model_budget: bool,
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    expected_fixture_sha256: str = EXPECTED_FIXTURE_SHA256,
    expected_implementation_sha256: Mapping[str, str] | None = None,
    provider_adapter_factory: ProviderAdapterFactory | None = None,
    model_adapter_factory: ModelAdapterFactory | None = None,
    monotonic_clock: Clock | None = None,
) -> RoleSlotDevelopmentExecution:
    """Run a bounded Y development attempt with no retry or recovery."""

    if not 0.0 < openalex_soft_stop_usd <= MAXIMUM_OPENALEX_SOFT_STOP_USD:
        raise OpenAlexRoleSlotDevelopmentError(
            "OpenAlex soft stop must be greater than zero and at most USD 0.01"
        )
    if not 0.0 < model_soft_stop_usd <= MAXIMUM_MODEL_SOFT_STOP_USD:
        raise OpenAlexRoleSlotDevelopmentError(
            "Qwen soft stop must be greater than zero and at most USD 0.25"
        )
    if not acknowledge_anonymous_daily_budget:
        raise OpenAlexRoleSlotDevelopmentError(
            "v6 execution requires anonymous OpenAlex budget acknowledgement"
        )
    if not acknowledge_model_budget:
        raise OpenAlexRoleSlotDevelopmentError(
            "v6 execution requires Qwen model-budget acknowledgement"
        )
    if (os.getenv("OPENALEX_API_KEY") or "").strip():
        raise OpenAlexRoleSlotDevelopmentError(
            "anonymous v6 study refuses a configured OPENALEX_API_KEY"
        )
    if output_dir.exists():
        raise FileExistsError(f"v6 development output already exists: {output_dir}")

    try:
        fixture_sha256, challenge, cases = load_frozen_cases(
            "development",
            fixture_path,
            expected_fixture_sha256=expected_fixture_sha256,
        )
    except OpenAlexRoleSlotPreflightError as exc:
        # The live runner owns its public failure contract.  Preserving the
        # phase-one exception here would force callers to know which earlier
        # preflight helper happened to reject a frozen identity.
        raise OpenAlexRoleSlotDevelopmentError(str(exc)) from exc
    implementation = verify_frozen_implementation(
        expected_implementation_sha256
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    manifest = _manifest(
        fixture_sha256,
        challenge,
        cases,
        implementation,
        openalex_soft_stop_usd=openalex_soft_stop_usd,
        model_soft_stop_usd=model_soft_stop_usd,
    )
    manifest_text = _json_text(manifest)
    _write_new(output_dir / "manifest.json", manifest_text)

    # Client construction is a capability boundary because default factories
    # resolve credentials and own socket-capable transports.  The global
    # manifest must already be durable when either custom or default provider
    # construction begins.
    provider_adapter = (
        provider_adapter_factory()
        if provider_adapter_factory is not None
        else AnonymousOpenAlexClaimScopeAdapter(transport=_OneRequestTransport())
    )
    model_adapter: ModelAdapter | None = None
    clock = monotonic_clock or time.perf_counter
    case_executions: list[RoleSlotCaseExecution] = []
    known_openalex_cost = 0.0
    known_model_cost = 0.0
    stop_reason: StopReason = "completed"

    for case in cases:
        if known_openalex_cost + 1e-12 >= openalex_soft_stop_usd:
            stop_reason = "openalex_soft_stop"
            break
        call = case.plan.calls[0]
        started_at = clock()
        provider_stop: StopReason | None = None
        try:
            raw_provider_response = provider_adapter(call)
        except ToolAdapterFailure as exc:
            provider_journal = _failed_provider_journal(
                case,
                failure_type=exc.failure_type,
                failure_detail=str(exc),
                failure_retryable=exc.retryable,
                latency_ms=_elapsed_ms(clock, started_at),
                search_cost_usd=exc.search_cost_usd,
            )
            provider_stop = "provider_failed"
        else:
            latency_ms = _elapsed_ms(clock, started_at)
            try:
                provider_response = OpenAlexClaimScopeAdapterResponse.model_validate(
                    raw_provider_response
                )
            except ValidationError as exc:
                provider_journal = _failed_provider_journal(
                    case,
                    failure_type="adapter_response_invalid",
                    failure_detail=_safe_validation_detail(exc),
                    failure_retryable=False,
                    latency_ms=latency_ms,
                    search_cost_usd=None,
                )
                provider_stop = "accounting_invalid"
            else:
                if provider_response.idempotency_key != call.idempotency_key:
                    provider_journal = _failed_provider_journal(
                        case,
                        failure_type="adapter_identity_mismatch",
                        failure_detail=(
                            "provider response idempotency key does not match the "
                            "authorized call"
                        ),
                        failure_retryable=False,
                        latency_ms=latency_ms,
                        search_cost_usd=provider_response.search_cost_usd,
                        response=provider_response,
                    )
                    provider_stop = "accounting_invalid"
                else:
                    provider_journal = _completed_provider_journal(
                        case,
                        provider_response,
                        latency_ms,
                    )

        # A spent provider request and every returned row are durable before
        # model planning, Qwen construction, or the next OpenAlex request.
        _write_provider_journal(output_dir, provider_journal)
        if provider_journal.search_cost_usd is None:
            provider_stop = provider_stop or "accounting_invalid"
        else:
            known_openalex_cost += provider_journal.search_cost_usd
        if provider_stop is not None:
            case_execution = RoleSlotCaseExecution(
                case_id=case.spec.case_id,
                state="provider_failed",
                provider_journal=provider_journal,
                model_calls=(),
            )
            _write_case_execution(output_dir, case_execution)
            case_executions.append(case_execution)
            stop_reason = provider_stop
            break

        provider_response = cast(
            OpenAlexClaimScopeAdapterResponse,
            provider_journal.response,
        )
        if not provider_response.candidates:
            case_execution = RoleSlotCaseExecution(
                case_id=case.spec.case_id,
                state="no_candidates",
                provider_journal=provider_journal,
                model_calls=(),
            )
            _write_case_execution(output_dir, case_execution)
            case_executions.append(case_execution)
            continue

        model_plan = _model_plan(case, provider_response)
        _write_model_plan(output_dir, model_plan)
        if model_adapter is None:
            model_adapter = (
                model_adapter_factory()
                if model_adapter_factory is not None
                else QwenRoleSlotJudgeAdapter()
            )

        model_journals: list[RoleSlotModelJournal] = []
        raw_responses: list[str] = []
        case_stop: StopReason | None = None
        for request in model_plan.requests:
            if known_model_cost + 1e-12 >= model_soft_stop_usd:
                case_stop = "model_soft_stop"
                break
            try:
                raw_model_response = model_adapter(request)
                model_response = QwenRoleSlotResponse.model_validate(
                    raw_model_response
                )
            except QwenRoleSlotJudgeError as exc:
                model_journal = _failed_model_journal(
                    request,
                    failure_type=exc.failure_type,
                    failure_detail=str(exc),
                    failure_retryable=exc.retryable,
                    request_may_have_spent=exc.request_may_have_spent,
                    observed_returned_model=exc.observed_returned_model,
                    observed_usage=exc.observed_usage,
                    observed_latency_ms=exc.observed_latency_ms,
                )
                case_stop = "model_failed"
            except ValidationError as exc:
                model_journal = _failed_model_journal(
                    request,
                    failure_type="adapter_response_invalid",
                    failure_detail=_safe_validation_detail(exc),
                    failure_retryable=False,
                    request_may_have_spent=True,
                )
                case_stop = "accounting_invalid"
            else:
                drift = _response_identity_drift(request, model_response)
                if drift:
                    model_journal = _failed_model_journal(
                        request,
                        failure_type="adapter_response_identity_mismatch",
                        failure_detail="response identity drifted: " + ", ".join(drift),
                        failure_retryable=False,
                        request_may_have_spent=True,
                        observed_returned_model=model_response.returned_model,
                        observed_usage=model_response.usage,
                        observed_latency_ms=model_response.latency_ms,
                    )
                    case_stop = "accounting_invalid"
                else:
                    model_journal = RoleSlotModelJournal(
                        case_id=request.case_id,
                        pass_number=request.pass_number,
                        candidate_order=request.candidate_order,
                        state="completed",
                        request=request,
                        response=model_response,
                        request_may_have_spent=True,
                    )
                    raw_responses.append(model_response.raw_content)

            # The response and safe usage are durable before another Qwen call.
            _write_model_journal(output_dir, model_journal)
            model_journals.append(model_journal)
            usage = _model_journal_usage(model_journal)
            if model_journal.request_may_have_spent and (
                usage is None or usage.cost_usd is None
            ):
                case_stop = case_stop or "accounting_invalid"
            elif usage is not None and usage.cost_usd is not None:
                known_model_cost += usage.cost_usd
            if model_journal.state != "completed":
                break

        if len(raw_responses) == 3 and case_stop is None:
            audit = evaluate_role_slot_case(
                case_id=case.spec.case_id,
                topic=case.spec.topic,
                profile=case.spec.roles.profile(),
                selection_contract=challenge.selection_contract,
                candidates=cast(
                    tuple[OpenAlexClaimScopeCandidate, ...],
                    provider_response.candidates,
                ),
                raw_responses=cast(tuple[str, str, str], tuple(raw_responses)),
            )
            _write_case_audit(output_dir, audit)
            case_execution = RoleSlotCaseExecution(
                case_id=case.spec.case_id,
                state="completed",
                provider_journal=provider_journal,
                model_plan=model_plan,
                model_calls=tuple(model_journals),
                case_audit=audit,
            )
        else:
            case_execution = RoleSlotCaseExecution(
                case_id=case.spec.case_id,
                state="model_incomplete",
                provider_journal=provider_journal,
                model_plan=model_plan,
                model_calls=tuple(model_journals),
            )
        # The complete case boundary is durable before the next provider call.
        _write_case_execution(output_dir, case_execution)
        case_executions.append(case_execution)
        if case_stop is not None:
            stop_reason = case_stop
            break

    execution = _execution_artifact(
        manifest_sha256=_sha256_bytes(manifest_text.encode("utf-8")),
        stop_reason=stop_reason,
        cases=case_executions,
    )
    _write_final_artifacts(output_dir, execution)
    return execution


def _stdout_json(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--cohort", choices=("development", "unseen"), default="development")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE_PATH)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--openalex-soft-stop-usd", type=float)
    parser.add_argument("--model-soft-stop-usd", type=float)
    parser.add_argument("--acknowledge-anonymous-daily-budget", action="store_true")
    parser.add_argument("--acknowledge-model-budget", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not args.execute_live:
        print(_stdout_json(protocol_dry_run(fixture_path=args.fixture)))
        return 0
    if args.cohort != "development":
        raise SystemExit("v6 live execution refuses the unseen cohort")
    if (
        args.output_dir is None
        or args.openalex_soft_stop_usd is None
        or args.model_soft_stop_usd is None
    ):
        raise SystemExit(
            "--execute-live requires --output-dir and both provider soft stops"
        )
    execution = execute_development_study(
        output_dir=args.output_dir,
        openalex_soft_stop_usd=args.openalex_soft_stop_usd,
        model_soft_stop_usd=args.model_soft_stop_usd,
        acknowledge_anonymous_daily_budget=args.acknowledge_anonymous_daily_budget,
        acknowledge_model_budget=args.acknowledge_model_budget,
        fixture_path=args.fixture,
    )
    print(_stdout_json(execution))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
