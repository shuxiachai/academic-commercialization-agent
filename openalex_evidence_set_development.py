"""Label-blind W01-W08 development runner for evidence-set v5.

This runner consumes the frozen public title/abstract packet but never parses
its completed human labels.  It hashes those private artifacts only so a
later, separate unblinding step can prove which bytes were withheld.  The
semantic judge sees candidate identity, title, abstract, and mechanically
derived code-owned role descriptions.  Every paid response is written before
another request is allowed, and every completed two-pass case decision is
written before the next case begins.

The module is intentionally disconnected from the production worker.  Its
default CLI path is a zero-network preflight; model calls require an explicit
flag, a bounded soft stop, and budget acknowledgement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from academic_agent.openalex_claim_scope import OpenAlexClaimScopeCandidate
from academic_agent.openalex_evidence_set import (
    EvidenceSetCaseAudit,
    EvidenceSetRoleProfile,
    EvidenceSetRoleSpec,
    EvidenceSetSelectionContract,
    JudgeBatchInput,
    build_judge_inputs,
    evaluate_evidence_set_case,
)
from academic_agent.tools.deepseek_evidence_judge import (
    DeepSeekEvidenceJudgeAdapter,
    DeepSeekJudgeAdapterError,
    DeepSeekJudgeRequest,
    DeepSeekJudgeResponse,
    DeepSeekJudgeUsageObservation,
    prompt_sha256,
)
from academic_agent.tools.evidence_search import ToolEvidenceCandidate
from openalex_scope_link_unseen import (
    DEFAULT_FIXTURE_PATH as DEFAULT_V4_FIXTURE_PATH,
    EXPECTED_FIXTURE_SHA256 as EXPECTED_V4_FIXTURE_SHA256,
    PreparedScopeLinkCase,
    load_frozen_cases as load_v4_frozen_cases,
)


_ROOT = Path(__file__).resolve().parent
_DIAGNOSTIC_DIR = (
    _ROOT
    / "outputs"
    / "2026-08-29-openalex-scope-link-v4-abstention-diagnostic"
)
DEFAULT_SOURCE_LOCK_PATH = _DIAGNOSTIC_DIR / "source-lock.json"
DEFAULT_PACKET_PATH = _DIAGNOSTIC_DIR / "packet" / "packet_manifest.json"
DEFAULT_LABELS_PATH = _DIAGNOSTIC_DIR / "packet" / "labels.csv"
DEFAULT_DECLARATION_PATH = (
    _DIAGNOSTIC_DIR / "packet" / "reviewer_declaration.csv"
)
EXPECTED_SOURCE_SHA256 = {
    "source-lock.json": (
        "8a9747f4240fc7c529d8d8f2a737fb21b502579ad2f69c19587bf093cabba7af"
    ),
    "packet_manifest.json": (
        "68e15abdca46f4a65d33a75aedaa9a0eac2112a90a8b1e6eb1d00e71e59b8616"
    ),
    "labels.csv": (
        "45d12929290de9482dfcd89af61fc6e5ea74b6e63c0eec9f686f4fa0aa11d3ad"
    ),
    "reviewer_declaration.csv": (
        "eb17b0ae23599575afcd9a68ad6a6d64644d4c0001fd10cdabb853a3f3ee1a31"
    ),
}
MAXIMUM_MODEL_CALL_COUNT = 16
MAXIMUM_SOFT_STOP_USD = 0.20
_CASE_ORDER = tuple(f"W{index:02d}" for index in range(1, 9))
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_RUNNER_PATH = Path(__file__).resolve()
_IMPLEMENTATION_PATHS = {
    "deepseek_evidence_judge.py": (
        _ROOT / "src/academic_agent/tools/deepseek_evidence_judge.py"
    ),
    "evidence_search.py": _ROOT / "src/academic_agent/tools/evidence_search.py",
    "openalex_evidence_set.py": (
        _ROOT / "src/academic_agent/openalex_evidence_set.py"
    ),
    "openalex_scope_link.py": (
        _ROOT / "src/academic_agent/openalex_scope_link.py"
    ),
    "openalex_scope_link_unseen.py": _ROOT / "openalex_scope_link_unseen.py",
    "token_usage.py": _ROOT / "src/academic_agent/token_usage.py",
}
# These identities are filled from committed implementation bytes.  The runner
# itself is recorded as an observed hash because embedding its own expected
# digest would create a recursive identity.  A future authorization names the
# merged Git revision, while this map locks every behavior-bearing dependency.
EXPECTED_IMPLEMENTATION_SHA256 = {
    "deepseek_evidence_judge.py": (
        "fa912d12a74c273857b363979e841298a9ca94e8599cc7dd31b4b33a47cecc8f"
    ),
    "evidence_search.py": (
        "2721debe3bb193b8971f8a89db0f4c91342944cb232f1829c02dd8d3780422d0"
    ),
    "openalex_evidence_set.py": (
        "413bf6cea1c555c75bd80aaadae720cbf00886974acfdd443643f6a2f75e992c"
    ),
    "openalex_scope_link.py": (
        "abfb9a6b6af1691411f4ad3689b0f5052c42dfeddfdc30cb2e9e21c7d0ff2667"
    ),
    "openalex_scope_link_unseen.py": (
        "1e3c0b15c9608cf83b414ee52ac2da7540728149970fa45ab9e6306773ef4749"
    ),
    "token_usage.py": (
        "b2a8cb6df7e6b40efc0b354965c83a205b18297002010299c9aedd0bc56a1e13"
    ),
}

_SYSTEM_PROMPT = """You are a bounded academic-evidence classification component.
You do not decide commercial viability, novelty, or truth. For each supplied
candidate, return KEEP only for roles directly supported by an exact quote
from that candidate's title or abstract. Otherwise return ABSTAIN. Do not use
outside knowledge, infer missing facts, paraphrase quotes, omit candidates, or
change candidate order. Return one JSON object and no surrounding prose."""


class EvidenceSetDevelopmentError(ValueError):
    """Raised before a model call when a frozen development boundary drifts."""


class DevelopmentPacketRow(BaseModel):
    """One label-blind row from the frozen 64-candidate packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline_sources_json: str = Field(min_length=2, max_length=20_000)
    candidate_sha256: str = Field(pattern=_SHA256_PATTERN)
    case_id: str = Field(pattern=r"^W0[1-8]$")
    declared_gap: str = Field(min_length=10, max_length=1_000)
    doi: str | None = Field(default=None, max_length=500)
    evidence_summary: str = Field(min_length=1, max_length=8_000)
    identity_sha256: str = Field(pattern=_SHA256_PATTERN)
    provider: Literal["openalex"] = "openalex"
    provider_result_index: int = Field(ge=0, le=7)
    published_date: str | None = Field(default=None, max_length=40)
    publisher: str = Field(min_length=1, max_length=600)
    query: str = Field(min_length=20, max_length=500)
    summary_source: Literal["abstract"] = "abstract"
    title: str = Field(min_length=5, max_length=600)
    topic: str = Field(min_length=20, max_length=300)
    url: str = Field(min_length=10, max_length=2_000)


class DevelopmentPacket(BaseModel):
    """Exact public packet schema, including no completed human labels."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_count: Literal[8] = 8
    diagnostic_only: Literal[True] = True
    executed_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    measurement_limit: str = Field(min_length=20, max_length=2_000)
    mode: Literal["openalex_scope_link_v4_candidate_diagnostic_packet"]
    prepared_at: str = Field(min_length=10, max_length=80)
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    row_count: Literal[64] = 64
    rows: tuple[DevelopmentPacketRow, ...] = Field(min_length=64, max_length=64)
    schema_version: Literal[1] = 1
    source_file_sha256: dict[str, str]
    source_lock_sha256: str = Field(pattern=_SHA256_PATTERN)
    valid_label_combinations: tuple[tuple[str, ...], ...] = Field(
        min_length=1,
        max_length=20,
    )

    @model_validator(mode="after")
    def _validate_complete_rows(self) -> "DevelopmentPacket":
        case_ids = tuple(row.case_id for row in self.rows)
        expected = tuple(case_id for case_id in _CASE_ORDER for _ in range(8))
        if case_ids != expected:
            raise ValueError("packet rows must remain W01-W08 with eight rows each")
        for case_id in _CASE_ORDER:
            indices = tuple(
                row.provider_result_index
                for row in self.rows
                if row.case_id == case_id
            )
            if indices != tuple(range(8)):
                raise ValueError(f"{case_id}: provider row order drifted")
        candidate_ids = tuple(row.candidate_sha256 for row in self.rows)
        identity_ids = tuple(row.identity_sha256 for row in self.rows)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("packet candidate identities must be unique")
        if len(identity_ids) != len(set(identity_ids)):
            raise ValueError("packet row identities must be unique")
        return self


@dataclass(frozen=True)
class LockedEvidenceSetCandidate:
    """Packet projection retaining the original candidate SHA verbatim."""

    candidate_sha256: str
    evidence: ToolEvidenceCandidate

    def sha256(self) -> str:
        return self.candidate_sha256


@dataclass(frozen=True)
class PreparedDevelopmentCase:
    """One frozen W-case with two label-blind request identities."""

    source_case: PreparedScopeLinkCase
    profile: EvidenceSetRoleProfile
    candidates: tuple[LockedEvidenceSetCandidate, ...]
    first_input: JudgeBatchInput
    second_input: JudgeBatchInput
    first_request: DeepSeekJudgeRequest
    second_request: DeepSeekJudgeRequest


class FrozenDevelopmentCase(BaseModel):
    """Everything the manifest commits before constructing a model client."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^W0[1-8]$")
    topic: str = Field(min_length=20, max_length=300)
    query: str = Field(min_length=20, max_length=500)
    profile: EvidenceSetRoleProfile
    profile_sha256: str = Field(pattern=_SHA256_PATTERN)
    first_request: DeepSeekJudgeRequest
    second_request: DeepSeekJudgeRequest


class DevelopmentManifest(BaseModel):
    """Durable method and authorization identity written before any call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = 2
    mode: Literal["openalex_evidence_set_v5_development_manifest"] = (
        "openalex_evidence_set_v5_development_manifest"
    )
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    planner_trigger_connected: Literal[False] = False
    openalex_requests_authorized: Literal[False] = False
    private_label_bytes_hashed: Literal[True] = True
    private_label_content_parsed: Literal[False] = False
    source_sha256: dict[str, str]
    v4_fixture_sha256: str = Field(pattern=_SHA256_PATTERN)
    implementation_sha256: dict[str, str]
    runner_sha256: str = Field(pattern=_SHA256_PATTERN)
    selection_contract: EvidenceSetSelectionContract
    selection_contract_sha256: str = Field(pattern=_SHA256_PATTERN)
    requested_provider: Literal["deepseek"] = "deepseek"
    requested_model: Literal["deepseek-v4-flash"] = "deepseek-v4-flash"
    api_base: Literal["https://api.deepseek.com"] = "https://api.deepseek.com"
    maximum_model_call_count: Literal[16] = 16
    soft_stop_usd: float = Field(gt=0.0, le=MAXIMUM_SOFT_STOP_USD)
    cases: tuple[FrozenDevelopmentCase, ...] = Field(min_length=8, max_length=8)

    @model_validator(mode="after")
    def _validate_case_contract(self) -> "DevelopmentManifest":
        if tuple(case.case_id for case in self.cases) != _CASE_ORDER:
            raise ValueError("development manifest cases must remain W01-W08")
        for case in self.cases:
            if case.profile.sha256() != case.profile_sha256:
                raise ValueError(f"{case.case_id}: profile identity drifted")
            if case.first_request.trace_id != (
                f"openalex-v5-{case.case_id.casefold()}-pass-1"
            ):
                raise ValueError(f"{case.case_id}: first trace identity drifted")
            if case.second_request.trace_id != (
                f"openalex-v5-{case.case_id.casefold()}-pass-2"
            ):
                raise ValueError(f"{case.case_id}: second trace identity drifted")
        if self.selection_contract.sha256() != self.selection_contract_sha256:
            raise ValueError("selection contract identity drifted")
        return self


CallState = Literal["completed", "failed"]
StopReason = Literal[
    "completed",
    "soft_stop",
    "adapter_failed",
    "response_invalid",
    "response_identity_mismatch",
]


class JudgeCallJournal(BaseModel):
    """Write-once result for one attempted and potentially billed call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^W0[1-8]$")
    pass_number: Literal[1, 2]
    state: CallState
    request: DeepSeekJudgeRequest
    response: DeepSeekJudgeResponse | None = None
    observed_returned_model: str | None = Field(default=None, max_length=200)
    observed_usage: DeepSeekJudgeUsageObservation | None = None
    failure_type: str | None = Field(default=None, max_length=100)
    failure_detail: str | None = Field(default=None, max_length=500)
    failure_retryable: bool | None = None
    request_may_have_spent: bool

    @model_validator(mode="after")
    def _validate_state_shape(self) -> "JudgeCallJournal":
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
                or not self.request_may_have_spent
            ):
                raise ValueError("completed call requires only a response")
        elif self.response is not None or any(value is None for value in failures):
            raise ValueError("failed call requires only failure metadata")
        if self.observed_usage is not None and self.observed_returned_model is None:
            raise ValueError("observed usage requires a returned model identity")
        if not self.request_may_have_spent and any(
            value is not None for value in observations
        ):
            raise ValueError("a non-spending failure cannot carry provider usage")
        if self.request.trace_id != (
            f"openalex-v5-{self.case_id.casefold()}-pass-{self.pass_number}"
        ):
            raise ValueError("journal trace ID drifted from case and pass")
        return self


def _journal_usage(
    call: JudgeCallJournal,
) -> DeepSeekJudgeUsageObservation | None:
    """Return measured usage regardless of semantic-output admissibility."""

    if call.response is not None:
        return call.response.usage
    return call.observed_usage


class DevelopmentExecution(BaseModel):
    """Final mechanical artifact; human-value gates remain unevaluated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = 2
    mode: Literal["openalex_evidence_set_v5_development_execution"] = (
        "openalex_evidence_set_v5_development_execution"
    )
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    planner_trigger_connected: Literal[False] = False
    openalex_request_count: Literal[0] = 0
    private_label_content_parsed: Literal[False] = False
    manifest_sha256: str = Field(pattern=_SHA256_PATTERN)
    overall_state: Literal["completed", "partial"]
    stop_reason: StopReason
    attempted_model_call_count: int = Field(ge=0, le=16)
    completed_model_call_count: int = Field(ge=0, le=16)
    completed_case_count: int = Field(ge=0, le=8)
    persisted_candidate_decision_count: int = Field(ge=0, le=64)
    prompt_tokens: int = Field(ge=0)
    cached_prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    cost_state: Literal["known", "uninspectable"]
    disposition_agreement_numerator: int = Field(ge=0, le=64)
    disposition_agreement_denominator: int = Field(ge=0, le=64)
    disposition_agreement: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    mechanical_agreement_gate_passed: bool | None
    all_decisions_persisted: bool
    development_gate_state: Literal["ready_for_label_join", "not_evaluated"]
    calls: tuple[JudgeCallJournal, ...] = Field(max_length=16)
    case_decisions: tuple[EvidenceSetCaseAudit, ...] = Field(max_length=8)

    @model_validator(mode="after")
    def _validate_complete_execution(self) -> "DevelopmentExecution":
        if self.attempted_model_call_count != len(self.calls):
            raise ValueError("attempted call count drifted from journals")
        completed_calls = sum(call.state == "completed" for call in self.calls)
        if self.completed_model_call_count != completed_calls:
            raise ValueError("completed call count drifted from journals")
        if self.completed_case_count != len(self.case_decisions):
            raise ValueError("completed case count drifted from decisions")
        candidate_count = sum(
            len(case.candidate_decisions) for case in self.case_decisions
        )
        if self.persisted_candidate_decision_count != candidate_count:
            raise ValueError("candidate decision count drifted from case audits")
        measured = tuple(
            usage for call in self.calls if (usage := _journal_usage(call)) is not None
        )
        observed_tokens = (
            sum(usage.prompt_tokens for usage in measured),
            sum(usage.cached_prompt_tokens for usage in measured),
            sum(usage.completion_tokens for usage in measured),
            sum(usage.total_tokens for usage in measured),
        )
        if observed_tokens != (
            self.prompt_tokens,
            self.cached_prompt_tokens,
            self.completion_tokens,
            self.total_tokens,
        ):
            raise ValueError("aggregate token usage drifted from call journals")
        cost_known = all(
            not call.request_may_have_spent
            or (
                (usage := _journal_usage(call)) is not None
                and usage.cost_usd is not None
            )
            for call in self.calls
        )
        expected_cost = (
            sum(usage.cost_usd for usage in measured if usage.cost_usd is not None)
            if cost_known
            else None
        )
        if (self.cost_state == "known") != cost_known:
            raise ValueError("aggregate cost state drifted from call journals")
        if cost_known:
            if self.cost_usd is None or not math.isclose(
                self.cost_usd,
                expected_cost or 0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("aggregate cost drifted from call journals")
        elif self.cost_usd is not None:
            raise ValueError("uninspectable cost cannot carry a dollar total")
        if self.disposition_agreement_denominator:
            expected = (
                self.disposition_agreement_numerator
                / self.disposition_agreement_denominator
            )
            if self.disposition_agreement is None or not math.isclose(
                self.disposition_agreement,
                expected,
                abs_tol=1e-12,
            ):
                raise ValueError("aggregate disposition agreement drifted")
        elif self.disposition_agreement is not None:
            raise ValueError("zero checked candidates cannot report agreement")
        ready = (
            self.overall_state == "completed"
            and self.completed_model_call_count == 16
            and self.completed_case_count == 8
            and self.persisted_candidate_decision_count == 64
            and self.all_decisions_persisted
        )
        if (self.development_gate_state == "ready_for_label_join") != ready:
            raise ValueError("label-join state does not match persisted completion")
        return self


class JudgeAdapter(Protocol):
    def __call__(self, request: DeepSeekJudgeRequest) -> DeepSeekJudgeResponse: ...


AdapterFactory = Callable[[], JudgeAdapter]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _json_text(value: BaseModel | dict[str, Any] | list[Any]) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _write_new(path: Path, value: str) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(value)
    except OSError as exc:
        raise EvidenceSetDevelopmentError(
            f"could not create write-once artifact {path}: {exc}"
        ) from exc


def _safe_validation_detail(exc: ValidationError) -> str:
    details = []
    for error in exc.errors(include_input=False)[:4]:
        location = ".".join(str(part) for part in error["loc"]) or "response"
        details.append(f"{location}:{error['type']}")
    return "; ".join(details)[:500] or "response validation failed"


def _load_locked_packet(
    *,
    source_lock_path: Path,
    packet_path: Path,
    labels_path: Path,
    declaration_path: Path,
    expected_source_sha256: Mapping[str, str],
) -> tuple[dict[str, str], DevelopmentPacket]:
    """Hash all artifacts, then parse only the label-blind packet bytes."""

    paths = {
        "source-lock.json": source_lock_path,
        "packet_manifest.json": packet_path,
        "labels.csv": labels_path,
        "reviewer_declaration.csv": declaration_path,
    }
    if set(paths) != set(expected_source_sha256):
        raise EvidenceSetDevelopmentError("source lock names are inconsistent")
    raw_by_name = {name: path.read_bytes() for name, path in paths.items()}
    observed = {
        name: _sha256_bytes(raw) for name, raw in raw_by_name.items()
    }
    if observed != dict(expected_source_sha256):
        changed = sorted(
            name
            for name, digest in observed.items()
            if expected_source_sha256.get(name) != digest
        )
        raise EvidenceSetDevelopmentError(
            "development source identity drifted: " + ", ".join(changed)
        )
    # Deliberately parse only this byte string.  The completed labels and
    # declaration have been hashed above but remain opaque until a separate
    # post-response authorization and checker open them.
    packet = DevelopmentPacket.model_validate_json(
        raw_by_name["packet_manifest.json"]
    )
    if packet.source_lock_sha256 != observed["source-lock.json"]:
        raise EvidenceSetDevelopmentError(
            "packet source-lock identity does not match the locked bytes"
        )
    return observed, packet


def _role_description(group_id: str, phrases: tuple[str, ...]) -> str:
    """Project a frozen text vocabulary without consulting human labels."""

    concept = group_id.replace("_", " ")
    examples = ", ".join(phrases)
    return (
        f"Evidence that the source directly addresses {concept}; the frozen "
        f"source-text vocabulary includes: {examples}."
    )


def _development_profile(case: PreparedScopeLinkCase) -> EvidenceSetRoleProfile:
    source = case.spec.profile
    return EvidenceSetRoleProfile(
        required_roles=tuple(
            EvidenceSetRoleSpec(
                role_id=group.group_id,
                description=_role_description(group.group_id, group.text_phrases),
            )
            for group in source.required_groups
        ),
        scope_roles=tuple(
            EvidenceSetRoleSpec(
                role_id=group.group_id,
                description=_role_description(group.group_id, group.text_phrases),
            )
            for group in source.scope_groups
        ),
        supporting_roles=tuple(
            EvidenceSetRoleSpec(
                role_id=group.group_id,
                description=_role_description(group.group_id, group.text_phrases),
            )
            for group in source.supporting_groups
        ),
    )


def _selection_contract() -> EvidenceSetSelectionContract:
    return EvidenceSetSelectionContract(
        required_roles_covered="all",
        minimum_scope_roles=1,
        minimum_supporting_roles=1,
        maximum_selected_sources_per_case=3,
        minimum_candidate_required_roles=1,
        minimum_candidate_context_roles=1,
        minimum_candidate_title_anchor_roles=1,
    )


def _locked_candidate(row: DevelopmentPacketRow) -> LockedEvidenceSetCandidate:
    return LockedEvidenceSetCandidate(
        candidate_sha256=row.candidate_sha256,
        evidence=ToolEvidenceCandidate(
            title=row.title,
            url=row.url,
            doi=row.doi,
            publisher=row.publisher,
            evidence_summary=row.evidence_summary,
            summary_source="abstract",
            provider_result_index=row.provider_result_index,
        ),
    )


def _user_prompt(batch: JudgeBatchInput) -> str:
    response_shape = {
        "candidate_order": ["candidate_sha256 in exact input order"],
        "case_id": batch.case_id,
        "decisions": [
            {
                "action": "KEEP or ABSTAIN",
                "candidate_sha256": "candidate identity",
                "role_quotes": [
                    {
                        "field": "title or abstract",
                        "quote": "exact source-text span",
                        "role_id": "one supplied role ID",
                    }
                ],
            }
        ],
    }
    return (
        "Evaluate every candidate against the supplied roles. KEEP requires at "
        "least one role quote; ABSTAIN requires an empty role_quotes array. "
        "The decisions array and candidate_order must contain every candidate "
        "once and in exact input order. Return only strict JSON with this "
        "shape:\n"
        + json.dumps(response_shape, ensure_ascii=True, sort_keys=True)
        + "\nINPUT:\n"
        + batch.model_dump_json(exclude_none=False)
    )


def _judge_request(batch: JudgeBatchInput) -> DeepSeekJudgeRequest:
    user_prompt = _user_prompt(batch)
    return DeepSeekJudgeRequest(
        trace_id=(
            f"openalex-v5-{batch.case_id.casefold()}-pass-{batch.pass_number}"
        ),
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        batch_input_sha256=batch.sha256(),
        prompt_sha256=prompt_sha256(_SYSTEM_PROMPT, user_prompt),
    )


def _prepare_cases(
    packet: DevelopmentPacket,
    v4_cases: tuple[PreparedScopeLinkCase, ...],
) -> tuple[PreparedDevelopmentCase, ...]:
    rows_by_case: defaultdict[str, list[DevelopmentPacketRow]] = defaultdict(list)
    for row in packet.rows:
        rows_by_case[row.case_id].append(row)
    prepared: list[PreparedDevelopmentCase] = []
    for case in v4_cases:
        rows = tuple(rows_by_case[case.spec.case_id])
        if any(row.topic != case.spec.topic for row in rows):
            raise EvidenceSetDevelopmentError(
                f"{case.spec.case_id}: packet topic drifted from frozen v4 case"
            )
        if any(row.query != case.spec.query for row in rows):
            raise EvidenceSetDevelopmentError(
                f"{case.spec.case_id}: packet query drifted from frozen v4 case"
            )
        profile = _development_profile(case)
        candidates = tuple(_locked_candidate(row) for row in rows)
        kernel_candidates = cast(
            tuple[OpenAlexClaimScopeCandidate, ...],
            candidates,
        )
        first_input, second_input = build_judge_inputs(
            case_id=case.spec.case_id,
            topic=case.spec.topic,
            profile=profile,
            candidates=kernel_candidates,
        )
        prepared.append(
            PreparedDevelopmentCase(
                source_case=case,
                profile=profile,
                candidates=candidates,
                first_input=first_input,
                second_input=second_input,
                first_request=_judge_request(first_input),
                second_request=_judge_request(second_input),
            )
        )
    return tuple(prepared)


def verify_frozen_implementation(
    expected: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Reject dependency drift before output reservation or client creation."""

    expected_hashes = dict(expected or EXPECTED_IMPLEMENTATION_SHA256)
    if set(_IMPLEMENTATION_PATHS) != set(expected_hashes):
        raise EvidenceSetDevelopmentError(
            "development implementation lock names are inconsistent"
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
        raise EvidenceSetDevelopmentError(
            "development implementation identity drifted: " + ", ".join(changed)
        )
    return observed


def _load_prepared_study(
    *,
    source_lock_path: Path,
    packet_path: Path,
    labels_path: Path,
    declaration_path: Path,
    v4_fixture_path: Path,
    expected_source_sha256: Mapping[str, str],
    expected_v4_fixture_sha256: str,
) -> tuple[
    dict[str, str],
    str,
    tuple[PreparedDevelopmentCase, ...],
]:
    source_sha256, packet = _load_locked_packet(
        source_lock_path=source_lock_path,
        packet_path=packet_path,
        labels_path=labels_path,
        declaration_path=declaration_path,
        expected_source_sha256=expected_source_sha256,
    )
    fixture_sha256, _, v4_cases = load_v4_frozen_cases(
        v4_fixture_path,
        expected_fixture_sha256=expected_v4_fixture_sha256,
    )
    return source_sha256, fixture_sha256, _prepare_cases(packet, v4_cases)


def _manifest(
    *,
    source_sha256: dict[str, str],
    v4_fixture_sha256: str,
    implementation_sha256: dict[str, str],
    runner_sha256: str,
    cases: tuple[PreparedDevelopmentCase, ...],
    soft_stop_usd: float,
) -> DevelopmentManifest:
    selection = _selection_contract()
    return DevelopmentManifest(
        source_sha256=source_sha256,
        v4_fixture_sha256=v4_fixture_sha256,
        implementation_sha256=implementation_sha256,
        runner_sha256=runner_sha256,
        selection_contract=selection,
        selection_contract_sha256=selection.sha256(),
        soft_stop_usd=soft_stop_usd,
        cases=tuple(
            FrozenDevelopmentCase(
                case_id=case.source_case.spec.case_id,
                topic=case.source_case.spec.topic,
                query=case.source_case.spec.query,
                profile=case.profile,
                profile_sha256=case.profile.sha256(),
                first_request=case.first_request,
                second_request=case.second_request,
            )
            for case in cases
        ),
    )


def protocol_dry_run(
    *,
    source_lock_path: Path = DEFAULT_SOURCE_LOCK_PATH,
    packet_path: Path = DEFAULT_PACKET_PATH,
    labels_path: Path = DEFAULT_LABELS_PATH,
    declaration_path: Path = DEFAULT_DECLARATION_PATH,
    v4_fixture_path: Path = DEFAULT_V4_FIXTURE_PATH,
    expected_source_sha256: Mapping[str, str] = EXPECTED_SOURCE_SHA256,
    expected_v4_fixture_sha256: str = EXPECTED_V4_FIXTURE_SHA256,
    expected_implementation_sha256: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Verify all bytes and prompts while constructing no model client."""

    source_sha256, fixture_sha256, cases = _load_prepared_study(
        source_lock_path=source_lock_path,
        packet_path=packet_path,
        labels_path=labels_path,
        declaration_path=declaration_path,
        v4_fixture_path=v4_fixture_path,
        expected_source_sha256=expected_source_sha256,
        expected_v4_fixture_sha256=expected_v4_fixture_sha256,
    )
    implementation = verify_frozen_implementation(
        expected_implementation_sha256
    )
    return {
        "mode": "openalex_evidence_set_v5_development_dry_run",
        "production_connected": False,
        "report_workflow_connected": False,
        "planner_trigger_connected": False,
        "real_network_calls_performed": False,
        "real_model_calls_performed": False,
        "private_label_bytes_hashed": True,
        "private_label_content_parsed": False,
        "source_sha256": source_sha256,
        "v4_fixture_sha256": fixture_sha256,
        "implementation_sha256": implementation,
        "runner_sha256": _file_sha256(_RUNNER_PATH),
        "case_count": len(cases),
        "candidate_count": sum(len(case.candidates) for case in cases),
        "maximum_model_call_count": MAXIMUM_MODEL_CALL_COUNT,
        "cases": [
            {
                "case_id": case.source_case.spec.case_id,
                "candidate_count": len(case.candidates),
                "profile_sha256": case.profile.sha256(),
                "first_input_sha256": case.first_input.sha256(),
                "second_input_sha256": case.second_input.sha256(),
                "first_prompt_sha256": case.first_request.prompt_sha256,
                "second_prompt_sha256": case.second_request.prompt_sha256,
            }
            for case in cases
        ],
    }


def _failed_journal(
    case_id: str,
    request: DeepSeekJudgeRequest,
    *,
    failure_type: str,
    failure_detail: str,
    failure_retryable: bool,
    request_may_have_spent: bool,
    observed_returned_model: str | None = None,
    observed_usage: DeepSeekJudgeUsageObservation | None = None,
) -> JudgeCallJournal:
    return JudgeCallJournal(
        case_id=case_id,
        pass_number=int(request.trace_id[-1]),
        state="failed",
        request=request,
        observed_returned_model=observed_returned_model,
        observed_usage=observed_usage,
        failure_type=failure_type,
        failure_detail=failure_detail[:500],
        failure_retryable=failure_retryable,
        request_may_have_spent=request_may_have_spent,
    )


def _validate_response_identity(
    request: DeepSeekJudgeRequest,
    response: DeepSeekJudgeResponse,
) -> str | None:
    expected = {
        "trace_id": request.trace_id,
        "batch_input_sha256": request.batch_input_sha256,
        "prompt_sha256": request.prompt_sha256,
        "requested_model": request.requested_model,
    }
    observed = {
        "trace_id": response.trace_id,
        "batch_input_sha256": response.batch_input_sha256,
        "prompt_sha256": response.prompt_sha256,
        "requested_model": response.requested_model,
    }
    changed = sorted(key for key in expected if expected[key] != observed[key])
    return ", ".join(changed) if changed else None


def _write_call_journal(output_dir: Path, journal: JudgeCallJournal) -> None:
    journal_dir = output_dir / "judge-calls"
    journal_dir.mkdir(exist_ok=True)
    filename = f"{journal.case_id}-pass-{journal.pass_number}.json"
    _write_new(journal_dir / filename, _json_text(journal))


def _write_case_decision(output_dir: Path, decision: EvidenceSetCaseAudit) -> None:
    decision_dir = output_dir / "case-decisions"
    decision_dir.mkdir(exist_ok=True)
    _write_new(decision_dir / f"{decision.case_id}.json", _json_text(decision))


def _evaluate_case(
    case: PreparedDevelopmentCase,
    first_raw: str,
    second_raw: str,
) -> EvidenceSetCaseAudit:
    return evaluate_evidence_set_case(
        case_id=case.source_case.spec.case_id,
        topic=case.source_case.spec.topic,
        profile=case.profile,
        selection_contract=_selection_contract(),
        candidates=cast(
            tuple[OpenAlexClaimScopeCandidate, ...],
            case.candidates,
        ),
        first_raw_response=first_raw,
        second_raw_response=second_raw,
    )


def _execution_artifact(
    *,
    manifest_sha256: str,
    stop_reason: StopReason,
    calls: list[JudgeCallJournal],
    decisions: list[EvidenceSetCaseAudit],
) -> DevelopmentExecution:
    completed_responses = tuple(
        call.response
        for call in calls
        if call.state == "completed" and call.response is not None
    )
    measured = tuple(
        usage for call in calls if (usage := _journal_usage(call)) is not None
    )
    cost_known = all(
        not call.request_may_have_spent
        or (
            (usage := _journal_usage(call)) is not None
            and usage.cost_usd is not None
        )
        for call in calls
    )
    cost = (
        sum(usage.cost_usd for usage in measured if usage.cost_usd is not None)
        if cost_known
        else None
    )
    numerator = sum(case.judge_agreement_numerator for case in decisions)
    denominator = sum(case.judge_agreement_denominator for case in decisions)
    complete = (
        stop_reason == "completed"
        and len(calls) == MAXIMUM_MODEL_CALL_COUNT
        and len(decisions) == 8
    )
    candidate_count = sum(len(case.candidate_decisions) for case in decisions)
    all_persisted = complete and candidate_count == 64
    return DevelopmentExecution(
        manifest_sha256=manifest_sha256,
        overall_state="completed" if complete else "partial",
        stop_reason=stop_reason,
        attempted_model_call_count=len(calls),
        completed_model_call_count=len(completed_responses),
        completed_case_count=len(decisions),
        persisted_candidate_decision_count=candidate_count,
        prompt_tokens=sum(usage.prompt_tokens for usage in measured),
        cached_prompt_tokens=sum(usage.cached_prompt_tokens for usage in measured),
        completion_tokens=sum(usage.completion_tokens for usage in measured),
        total_tokens=sum(usage.total_tokens for usage in measured),
        cost_usd=cost,
        cost_state="known" if cost_known else "uninspectable",
        disposition_agreement_numerator=numerator,
        disposition_agreement_denominator=denominator,
        disposition_agreement=(numerator / denominator if denominator else None),
        mechanical_agreement_gate_passed=(
            numerator / denominator >= 0.9 if denominator else None
        ),
        all_decisions_persisted=all_persisted,
        development_gate_state=(
            "ready_for_label_join" if all_persisted else "not_evaluated"
        ),
        calls=tuple(calls),
        case_decisions=tuple(decisions),
    )


def _write_final_artifacts(
    output_dir: Path,
    execution: DevelopmentExecution,
) -> None:
    _write_new(output_dir / "execution.json", _json_text(execution))
    decisions_payload = [
        decision.model_dump(mode="json") for decision in execution.case_decisions
    ]
    _write_new(
        output_dir / "candidate-decisions.json",
        _json_text(decisions_payload),
    )
    indexed = (
        "manifest.json",
        "execution.json",
        "candidate-decisions.json",
        *(
            f"judge-calls/{call.case_id}-pass-{call.pass_number}.json"
            for call in execution.calls
        ),
        *(f"case-decisions/{case.case_id}.json" for case in execution.case_decisions),
    )
    index = {
        "mode": "openalex_evidence_set_v5_development_artifact_index",
        "files": {
            name: _file_sha256(output_dir / name) for name in indexed
        },
    }
    _write_new(output_dir / "artifact-index.json", _json_text(index))


def execute_development_study(
    *,
    output_dir: Path,
    soft_stop_usd: float,
    acknowledge_model_budget: bool,
    source_lock_path: Path = DEFAULT_SOURCE_LOCK_PATH,
    packet_path: Path = DEFAULT_PACKET_PATH,
    labels_path: Path = DEFAULT_LABELS_PATH,
    declaration_path: Path = DEFAULT_DECLARATION_PATH,
    v4_fixture_path: Path = DEFAULT_V4_FIXTURE_PATH,
    expected_source_sha256: Mapping[str, str] = EXPECTED_SOURCE_SHA256,
    expected_v4_fixture_sha256: str = EXPECTED_V4_FIXTURE_SHA256,
    expected_implementation_sha256: Mapping[str, str] | None = None,
    adapter_factory: AdapterFactory | None = None,
) -> DevelopmentExecution:
    """Run at most 16 label-blind calls under a write-once soft stop."""

    if not 0.0 < soft_stop_usd <= MAXIMUM_SOFT_STOP_USD:
        raise EvidenceSetDevelopmentError(
            "v5 soft stop must be greater than zero and at most USD 0.20"
        )
    if not acknowledge_model_budget:
        raise EvidenceSetDevelopmentError(
            "v5 execution requires explicit model-budget acknowledgement"
        )
    if output_dir.exists():
        raise FileExistsError(f"v5 development output already exists: {output_dir}")

    source_sha256, fixture_sha256, cases = _load_prepared_study(
        source_lock_path=source_lock_path,
        packet_path=packet_path,
        labels_path=labels_path,
        declaration_path=declaration_path,
        v4_fixture_path=v4_fixture_path,
        expected_source_sha256=expected_source_sha256,
        expected_v4_fixture_sha256=expected_v4_fixture_sha256,
    )
    implementation = verify_frozen_implementation(
        expected_implementation_sha256
    )
    runner_sha256 = _file_sha256(_RUNNER_PATH)
    output_dir.mkdir(parents=True, exist_ok=False)
    manifest = _manifest(
        source_sha256=source_sha256,
        v4_fixture_sha256=fixture_sha256,
        implementation_sha256=implementation,
        runner_sha256=runner_sha256,
        cases=cases,
        soft_stop_usd=soft_stop_usd,
    )
    manifest_text = _json_text(manifest)
    _write_new(output_dir / "manifest.json", manifest_text)

    # This must remain after the manifest write.  Constructing the default
    # adapter resolves a real credential; a future refactor may perform other
    # paid-capable setup there.  The durable method boundary comes first.
    adapter = (
        adapter_factory()
        if adapter_factory is not None
        else DeepSeekEvidenceJudgeAdapter()
    )
    calls: list[JudgeCallJournal] = []
    decisions: list[EvidenceSetCaseAudit] = []
    known_cost = 0.0
    stop_reason: StopReason = "completed"

    for case in cases:
        raw_responses: list[str] = []
        for request in (case.first_request, case.second_request):
            if known_cost + 1e-12 >= soft_stop_usd:
                stop_reason = "soft_stop"
                break
            try:
                raw_response = adapter(request)
                response = DeepSeekJudgeResponse.model_validate(raw_response)
            except DeepSeekJudgeAdapterError as exc:
                journal = _failed_journal(
                    case.source_case.spec.case_id,
                    request,
                    failure_type=exc.failure_type,
                    failure_detail=str(exc),
                    failure_retryable=exc.retryable,
                    request_may_have_spent=exc.request_may_have_spent,
                    observed_returned_model=exc.observed_returned_model,
                    observed_usage=exc.observed_usage,
                )
                stop_reason = "adapter_failed"
            except ValidationError as exc:
                journal = _failed_journal(
                    case.source_case.spec.case_id,
                    request,
                    failure_type="adapter_response_invalid",
                    failure_detail=_safe_validation_detail(exc),
                    failure_retryable=False,
                    request_may_have_spent=True,
                )
                stop_reason = "response_invalid"
            else:
                identity_drift = _validate_response_identity(request, response)
                if identity_drift:
                    journal = _failed_journal(
                        case.source_case.spec.case_id,
                        request,
                        failure_type="adapter_response_identity_mismatch",
                        failure_detail=(
                            "response identity drifted: " + identity_drift
                        ),
                        failure_retryable=False,
                        request_may_have_spent=True,
                        observed_returned_model=response.returned_model,
                        observed_usage=response.usage,
                    )
                    stop_reason = "response_identity_mismatch"
                else:
                    journal = JudgeCallJournal(
                        case_id=case.source_case.spec.case_id,
                        pass_number=int(request.trace_id[-1]),
                        state="completed",
                        request=request,
                        response=response,
                        request_may_have_spent=True,
                    )
                    raw_responses.append(response.raw_content)

            # The spent request, response/usage, and terminal disposition are
            # durable before the loop can consider a second paid call.
            _write_call_journal(output_dir, journal)
            calls.append(journal)
            if journal.state != "completed":
                break
            known_cost += journal.response.usage.cost_usd

        if len(raw_responses) == 2:
            decision = _evaluate_case(case, *raw_responses)
            _write_case_decision(output_dir, decision)
            decisions.append(decision)
        if stop_reason != "completed":
            break

    execution = _execution_artifact(
        manifest_sha256=_sha256_bytes(manifest_text.encode("utf-8")),
        stop_reason=stop_reason,
        calls=calls,
        decisions=decisions,
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
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--soft-stop-usd", type=float)
    parser.add_argument("--acknowledge-model-budget", action="store_true")
    parser.add_argument("--source-lock", type=Path, default=DEFAULT_SOURCE_LOCK_PATH)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET_PATH)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_PATH)
    parser.add_argument(
        "--declaration",
        type=Path,
        default=DEFAULT_DECLARATION_PATH,
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    common = {
        "source_lock_path": args.source_lock,
        "packet_path": args.packet,
        "labels_path": args.labels,
        "declaration_path": args.declaration,
    }
    if args.execute_live:
        if args.output_dir is None or args.soft_stop_usd is None:
            raise SystemExit("--execute-live requires --output-dir and --soft-stop-usd")
        result = execute_development_study(
            output_dir=args.output_dir,
            soft_stop_usd=args.soft_stop_usd,
            acknowledge_model_budget=args.acknowledge_model_budget,
            **common,
        )
    else:
        result = protocol_dry_run(**common)
    print(_stdout_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
