"""Review all frozen role-slot v6 provider candidates after mechanical failure.

The Y01-Y08 v6 run was already falsified before its human-value gates opened.
Its OpenAlex layer is nevertheless complete, so the original pre-registration
still requires a label-blind review of every provider candidate.  This module
locks those exact bytes, emits a reviewer packet without model decisions, and
joins the hidden role-slot trace only after an eligible review returns.

This root-level experimental utility opens no socket, invokes no model,
registers no evidence, and is never imported by the production worker.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from academic_agent.openalex_role_slot import RoleSlotCaseAudit
from evidence_gap_phase4_review import (
    DECLARATION_FIELDS,
    ELIGIBLE_AI_USE,
    Phase4ReviewError as RoleSlotFailureReviewError,
    _file_sha256,
    _read_csv,
    _read_json_object,
    _validated_declaration,
    _write_csv_new,
    _write_text_new,
)
from openalex_role_slot_development import (
    EXPECTED_IMPLEMENTATION_SHA256,
    RoleSlotCaseExecution,
    RoleSlotDevelopmentExecution,
    RoleSlotDevelopmentManifest,
    RoleSlotModelJournal,
    RoleSlotModelPlan,
    RoleSlotProviderJournal,
    _PROVIDER_ROW_COLUMNS,
    _provider_rows,
)
from openalex_role_slot_unseen import (
    EXPECTED_FIXTURE_SHA256,
    load_frozen_cases,
)


EXPECTED_EXECUTED_REVISION = "d23ffd54bb171d1030f5531a7d57bd6eedc5d853"
EXPECTED_SOURCE_FILE_SHA256 = {
    "manifest.json": (
        "543c5300f36e7e1f498f66cb51fba88eebefea07e93ada817de15e7291178e17"
    ),
    "execution.json": (
        "fbd5f42adffeb714937845fcf5f887bd6291989d308fce587da227be63f6754c"
    ),
    "provider-rows.csv": (
        "c7926e4ae228d3fc16580885ce5b6208a0dc176c39b2650aba6ff833b22bbb8b"
    ),
    "artifact-index.json": (
        "c7a6472d3d32d990e7f3de5470f8eec3af1963bc15207144e7f994e4f844d38a"
    ),
}
EXPECTED_EXECUTION_OBSERVATIONS: dict[str, Any] = {
    "overall_state": "partial",
    "stop_reason": "model_soft_stop",
    "openalex_request_count": 8,
    "openalex_successful_case_count": 8,
    "openalex_cost_state": "known",
    "openalex_cost_usd": 0.008,
    "model_call_count": 21,
    "model_completed_call_count": 21,
    "model_cost_state": "known",
    "model_cost_usd": 0.204363,
    "prompt_tokens": 61_844,
    "cached_prompt_tokens": 0,
    "completion_tokens": 49_106,
    "total_tokens": 110_950,
    "provider_row_count": 64,
    "provider_candidate_count": 64,
    "provider_rejection_count": 0,
    "completed_case_audit_count": 7,
    "selected_case_count": 4,
    "provisional_unanimity_numerator": 34,
    "provisional_unanimity_denominator": 56,
    "audit_boundary_complete": False,
    "mechanical_gate_state": "not_evaluated",
    "source_lock_readiness": "not_ready",
    "human_review_state": "not_prepared",
    "source_value_state": "not_evaluated",
}
CASE_IDS = tuple(f"Y{index:02d}" for index in range(1, 9))
EXPECTED_CANDIDATES_PER_CASE = {case_id: 8 for case_id in CASE_IDS}
EXPECTED_CANDIDATE_COUNT = 64
EXPECTED_INDEXED_FILE_COUNT = 56
CORE_SOURCE_FILES = tuple(EXPECTED_SOURCE_FILE_SHA256)

# Context is intentionally repeated on every label row.  A separate context
# table would be smaller, but it would add a fragile human join at exactly the
# seam where prior project bugs silently lost correct values before the client.
CONTEXT_FIELDS = (
    "case_id",
    "provider_result_index",
    "candidate_sha256",
    "topic",
    "query",
    "baseline_sources_json",
    "required_roles_json",
    "scope_roles_json",
    "supporting_roles_json",
    "title",
    "url",
    "doi",
    "publisher",
    "published_date",
    "abstract",
    "summary_source",
)
LABEL_VALUE_FIELDS = (
    "direct_relevance",
    "baseline_novelty",
    "abstract_sufficient",
    "supported_role_ids_json",
    "title_supported_role_ids_json",
    "review_note",
)
LABEL_FIELDS = (*CONTEXT_FIELDS, *LABEL_VALUE_FIELDS)
VALID_LABEL_COMBINATIONS = {
    ("YES", novelty, "YES") for novelty in ("YES", "NO")
} | {
    ("NO", "N/A", "YES"),
    ("UNVERIFIABLE", "UNVERIFIABLE", "NO"),
}
MEASUREMENT_LIMIT = (
    "This post-outcome diagnostic measures human interpretation of the frozen "
    "title and abstract text for all 64 Y01-Y08 provider candidates. It cannot "
    "change the failed v6 result, validate a successor, open Z01-Z08, or "
    "authorize production Tool Calling."
)
_FORBIDDEN_REVIEWER_KEYS = {
    "action",
    "abstention_reasons",
    "candidate_action",
    "candidate_decisions",
    "case_audit",
    "consensus_supported",
    "covered_required_role_ids",
    "covered_scope_role_ids",
    "covered_supporting_role_ids",
    "model_calls",
    "model_plan",
    "observations",
    "pass_row_states",
    "passes",
    "provisional_actions",
    "provisional_disposition_unanimous",
    "quote",
    "role_consensus",
    "selected_sources",
    "support_count",
    "title_anchor_role_ids",
    "title_support_count",
}


class RoleSlotFailureDiagnosticLock(BaseModel):
    """Owner attestation over the exact provider-complete failed execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["openalex_role_slot_v6_failure_diagnostic_lock"] = (
        "openalex_role_slot_v6_failure_diagnostic_lock"
    )
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    diagnostic_only: Literal[True] = True
    original_source_value_state: Literal["not_evaluated"] = "not_evaluated"
    original_source_lock_readiness: Literal["not_ready"] = "not_ready"
    authorized_output: Literal[True] = True
    executed_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_sha256: dict[str, str]
    source_file_sha256: dict[str, str]
    indexed_file_sha256: dict[str, str]
    study_owner_id: str = Field(min_length=2, max_length=200)
    authorized_at: datetime
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _validate_frozen_identity(self) -> "RoleSlotFailureDiagnosticLock":
        if self.executed_revision != EXPECTED_EXECUTED_REVISION:
            raise ValueError("diagnostic lock executed revision does not match")
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("diagnostic lock fixture identity does not match")
        if self.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
            raise ValueError("diagnostic lock implementation identities do not match")
        if self.source_file_sha256 != EXPECTED_SOURCE_FILE_SHA256:
            raise ValueError("diagnostic lock does not identify the frozen v6 run")
        if len(self.indexed_file_sha256) != EXPECTED_INDEXED_FILE_COUNT:
            raise ValueError("diagnostic lock indexed-file count does not match")
        for mapping in (self.source_file_sha256, self.indexed_file_sha256):
            if any(not _is_sha256(value) for value in mapping.values()):
                raise ValueError(
                    "diagnostic lock hashes must be complete lowercase SHA-256 values"
                )
        if self.authorized_at.tzinfo is None:
            raise ValueError("diagnostic lock timestamp must be timezone-aware")
        return self


@dataclass(frozen=True)
class RoleSlotFailureCandidate:
    """One reviewer-visible candidate without any v6 model outcome."""

    case_id: str
    provider_result_index: int
    candidate_sha256: str
    topic: str
    query: str
    baseline_sources_json: str
    required_roles_json: str
    scope_roles_json: str
    supporting_roles_json: str
    title: str
    url: str
    doi: str
    publisher: str
    published_date: str
    abstract: str
    summary_source: str

    @property
    def key(self) -> tuple[str, int, str]:
        return self.case_id, self.provider_result_index, self.candidate_sha256

    @property
    def row_id(self) -> str:
        return (
            f"{self.case_id}/{self.provider_result_index}/"
            f"{self.candidate_sha256[:12]}"
        )

    @property
    def identity_sha256(self) -> str:
        return _sha256_json(asdict(self))

    @property
    def role_groups(self) -> dict[str, tuple[str, ...]]:
        return {
            "required": _role_ids_from_context(self.required_roles_json),
            "scope": _role_ids_from_context(self.scope_roles_json),
            "supporting": _role_ids_from_context(self.supporting_roles_json),
        }

    @property
    def declared_role_ids(self) -> tuple[str, ...]:
        groups = self.role_groups
        return (*groups["required"], *groups["scope"], *groups["supporting"])


@dataclass(frozen=True)
class RoleSlotFailureSnapshot:
    """Exact source projection shared by lock, packet, and summary seams."""

    source_file_hashes: dict[str, str]
    indexed_file_hashes: dict[str, str]
    manifest: RoleSlotDevelopmentManifest
    execution: RoleSlotDevelopmentExecution
    candidates: tuple[RoleSlotFailureCandidate, ...]
    hidden_traces: dict[tuple[str, int, str], dict[str, Any]]
    selection_contract: Any


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _sha256_json(value: object) -> str:
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _read_json_value(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RoleSlotFailureReviewError(
            f"could not read JSON artifact {path}: {exc}"
        ) from exc


def _role_context_json(roles: Sequence[Any]) -> str:
    return json.dumps(
        [
            {"role_id": role.role_id, "description": role.description}
            for role in roles
        ],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _role_ids_from_context(value: str) -> tuple[str, ...]:
    try:
        rows = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RoleSlotFailureReviewError(
            "reviewer-visible role context is not valid JSON"
        ) from exc
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RoleSlotFailureReviewError("role context must be a JSON object array")
    role_ids = tuple(row.get("role_id") for row in rows)
    if any(not isinstance(role_id, str) or not role_id for role_id in role_ids):
        raise RoleSlotFailureReviewError("role context contains an invalid role ID")
    if len(role_ids) != len(set(role_ids)):
        raise RoleSlotFailureReviewError("role context contains duplicate role IDs")
    return role_ids


def _baseline_sources_json(case: Any) -> str:
    return json.dumps(
        [source.model_dump(mode="json") for source in case.source_collection.academic_sources],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _expected_index_paths(
    execution: RoleSlotDevelopmentExecution,
) -> set[str]:
    paths = {
        "manifest.json",
        "execution.json",
        "provider-rows.csv",
        "case-audits.json",
    }
    for case in execution.cases:
        paths.add(f"provider-journals/{case.case_id}.json")
        paths.add(f"case-executions/{case.case_id}.json")
        if case.model_plan is not None:
            paths.add(f"model-plans/{case.case_id}.json")
        paths.update(
            f"model-journals/{call.case_id}-pass-{call.pass_number}.json"
            for call in case.model_calls
        )
        if case.case_audit is not None:
            paths.add(f"case-audits/{case.case_id}.json")
    return paths


def _validate_artifact_index(
    source_dir: Path,
    execution: RoleSlotDevelopmentExecution,
) -> dict[str, str]:
    payload = _read_json_object(source_dir / "artifact-index.json")
    expected_header = {
        "schema_version": 1,
        "mode": "openalex_role_slot_v6_development_artifact_index",
        "production_connected": False,
        "report_workflow_connected": False,
        "planner_trigger_connected": False,
    }
    if any(payload.get(key) != value for key, value in expected_header.items()):
        raise RoleSlotFailureReviewError("v6 artifact index header drifted")
    files = payload.get("files")
    if not isinstance(files, dict) or any(
        not isinstance(name, str) or not _is_sha256(value)
        for name, value in files.items()
    ):
        raise RoleSlotFailureReviewError("v6 artifact index file map is invalid")
    expected_paths = _expected_index_paths(execution)
    if set(files) != expected_paths:
        missing = sorted(expected_paths - set(files))
        extra = sorted(set(files) - expected_paths)
        raise RoleSlotFailureReviewError(
            f"v6 artifact index paths drifted; missing={missing}, extra={extra}"
        )
    if len(files) != EXPECTED_INDEXED_FILE_COUNT:
        raise RoleSlotFailureReviewError("v6 artifact index count drifted")
    for name, expected_hash in files.items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or path.as_posix() != name:
            raise RoleSlotFailureReviewError(
                f"v6 artifact index contains an unsafe path: {name}"
            )
        observed = _file_sha256(source_dir / Path(*path.parts))
        if observed != expected_hash:
            raise RoleSlotFailureReviewError(
                f"indexed artifact identity drifted: {name}"
            )
    return dict(files)


def _validate_execution_observations(
    manifest: RoleSlotDevelopmentManifest,
    execution: RoleSlotDevelopmentExecution,
    manifest_sha256: str,
) -> None:
    if execution.manifest_sha256 != manifest_sha256:
        raise RoleSlotFailureReviewError("execution manifest identity drifted")
    if manifest.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
        raise RoleSlotFailureReviewError("v6 fixture identity drifted")
    if manifest.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
        raise RoleSlotFailureReviewError("v6 implementation identity drifted")
    if tuple(case.spec.case_id for case in manifest.cases) != CASE_IDS:
        raise RoleSlotFailureReviewError("manifest cases are not frozen Y01-Y08")
    if tuple(case.case_id for case in execution.cases) != CASE_IDS:
        raise RoleSlotFailureReviewError("execution cases are not frozen Y01-Y08")
    observed = execution.model_dump(mode="json")
    for field, expected in EXPECTED_EXECUTION_OBSERVATIONS.items():
        value = observed.get(field)
        if isinstance(expected, float):
            equal = isinstance(value, (int, float)) and math.isclose(
                float(value), expected, abs_tol=1e-12
            )
        else:
            equal = value == expected
        if not equal:
            raise RoleSlotFailureReviewError(
                f"v6 execution observation drifted for {field}: "
                f"expected {expected!r}, got {value!r}"
            )
    if any(
        (
            case.provider_journal.state != "completed"
            or case.provider_journal.response is None
            or len(case.provider_journal.response.candidates)
            != EXPECTED_CANDIDATES_PER_CASE[case.case_id]
            or case.provider_journal.response.provider_rejections
        )
        for case in execution.cases
    ):
        raise RoleSlotFailureReviewError(
            "provider-complete diagnostic requires every Y case and candidate"
        )
    if any(
        getattr(manifest, field) is not False
        for field in (
            "production_connected",
            "report_workflow_connected",
            "planner_trigger_connected",
            "private_labels_opened",
            "unseen_cohort_opened",
        )
    ) or any(
        getattr(execution, field) is not False
        for field in (
            "production_connected",
            "report_workflow_connected",
            "planner_trigger_connected",
            "private_labels_opened",
            "unseen_cohort_opened",
        )
    ):
        raise RoleSlotFailureReviewError("v6 diagnostic source is not disconnected")


def _validate_child_artifacts(
    source_dir: Path,
    execution: RoleSlotDevelopmentExecution,
) -> None:
    aggregate_audits = _read_json_value(source_dir / "case-audits.json")
    expected_audits = [
        case.case_audit.model_dump(mode="json")
        for case in execution.cases
        if case.case_audit is not None
    ]
    if aggregate_audits != expected_audits:
        raise RoleSlotFailureReviewError("aggregate case audits drifted from execution")
    for case in execution.cases:
        provider = RoleSlotProviderJournal.model_validate(
            _read_json_object(
                source_dir / "provider-journals" / f"{case.case_id}.json"
            )
        )
        if provider != case.provider_journal:
            raise RoleSlotFailureReviewError(
                f"{case.case_id} provider journal drifted from execution"
            )
        child = RoleSlotCaseExecution.model_validate(
            _read_json_object(
                source_dir / "case-executions" / f"{case.case_id}.json"
            )
        )
        if child != case:
            raise RoleSlotFailureReviewError(
                f"{case.case_id} case journal drifted from execution"
            )
        if case.model_plan is not None:
            plan = RoleSlotModelPlan.model_validate(
                _read_json_object(
                    source_dir / "model-plans" / f"{case.case_id}.json"
                )
            )
            if plan != case.model_plan:
                raise RoleSlotFailureReviewError(
                    f"{case.case_id} model plan drifted from execution"
                )
        for call in case.model_calls:
            journal = RoleSlotModelJournal.model_validate(
                _read_json_object(
                    source_dir
                    / "model-journals"
                    / f"{call.case_id}-pass-{call.pass_number}.json"
                )
            )
            if journal != call:
                raise RoleSlotFailureReviewError(
                    f"{case.case_id} model journal drifted from execution"
                )
        if case.case_audit is not None:
            audit = RoleSlotCaseAudit.model_validate(
                _read_json_object(
                    source_dir / "case-audits" / f"{case.case_id}.json"
                )
            )
            if audit != case.case_audit:
                raise RoleSlotFailureReviewError(
                    f"{case.case_id} case audit drifted from execution"
                )


def _project_candidates(
    manifest: RoleSlotDevelopmentManifest,
    execution: RoleSlotDevelopmentExecution,
) -> tuple[
    tuple[RoleSlotFailureCandidate, ...],
    dict[tuple[str, int, str], dict[str, Any]],
]:
    manifest_cases = {case.spec.case_id: case for case in manifest.cases}
    candidates: list[RoleSlotFailureCandidate] = []
    hidden: dict[tuple[str, int, str], dict[str, Any]] = {}
    for execution_case in execution.cases:
        frozen = manifest_cases[execution_case.case_id]
        response = execution_case.provider_journal.response
        if response is None:
            raise RoleSlotFailureReviewError(
                f"{execution_case.case_id} has no provider response"
            )
        audit = execution_case.case_audit
        decisions = (
            {item.candidate_sha256: item for item in audit.candidate_decisions}
            if audit is not None
            else {}
        )
        selected_ids = (
            {item.candidate_sha256 for item in audit.selected_sources}
            if audit is not None
            else set()
        )
        for provider_candidate in sorted(
            response.candidates,
            key=lambda item: int(item.evidence.provider_result_index or 0),
        ):
            evidence = provider_candidate.evidence
            index = evidence.provider_result_index
            if index is None:
                raise RoleSlotFailureReviewError(
                    "provider candidate lost its result index"
                )
            candidate = RoleSlotFailureCandidate(
                case_id=execution_case.case_id,
                provider_result_index=index,
                candidate_sha256=provider_candidate.sha256(),
                topic=frozen.spec.topic,
                query=frozen.spec.query,
                baseline_sources_json=_baseline_sources_json(frozen),
                required_roles_json=_role_context_json(frozen.spec.roles.required),
                scope_roles_json=_role_context_json(frozen.spec.roles.scope),
                supporting_roles_json=_role_context_json(
                    frozen.spec.roles.supporting
                ),
                title=evidence.title,
                url=evidence.url,
                doi=evidence.doi or "",
                publisher=evidence.publisher,
                published_date=(
                    evidence.published_date.isoformat()
                    if evidence.published_date is not None
                    else ""
                ),
                abstract=evidence.evidence_summary,
                summary_source=evidence.summary_source,
            )
            candidates.append(candidate)
            decision = decisions.get(candidate.candidate_sha256)
            trace: dict[str, Any] = {
                "model_observed": decision is not None,
                "case_action": audit.action if audit is not None else None,
                "case_selected": bool(audit is not None and audit.action == "SELECT"),
                "candidate_action": decision.action if decision is not None else None,
                "consensus_supported_role_ids": (
                    sorted(
                        role.role_id
                        for role in decision.role_consensus
                        if role.consensus_supported
                    )
                    if decision is not None
                    else []
                ),
                "title_anchor_role_ids": (
                    sorted(decision.title_anchor_role_ids)
                    if decision is not None
                    else []
                ),
                "provisional_disposition_unanimous": (
                    decision.provisional_disposition_unanimous
                    if decision is not None
                    else None
                ),
                "selected_source": candidate.candidate_sha256 in selected_ids,
                "candidate_abstention_reasons": (
                    list(decision.abstention_reasons)
                    if decision is not None
                    else []
                ),
            }
            hidden[candidate.key] = trace
    ordered = tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.case_id,
                item.provider_result_index,
                item.candidate_sha256,
            ),
        )
    )
    if len(ordered) != EXPECTED_CANDIDATE_COUNT:
        raise RoleSlotFailureReviewError("v6 provider candidate count drifted")
    counts = Counter(item.case_id for item in ordered)
    if dict(counts) != EXPECTED_CANDIDATES_PER_CASE:
        raise RoleSlotFailureReviewError("v6 per-case candidate counts drifted")
    if len({item.key for item in ordered}) != len(ordered):
        raise RoleSlotFailureReviewError("v6 provider candidate identities repeat")
    if set(hidden) != {item.key for item in ordered}:
        raise RoleSlotFailureReviewError(
            "computed hidden traces did not reach every candidate boundary"
        )
    return ordered, hidden


def validate_finalized_source(
    source_dir: Path,
    *,
    expected_hashes: Mapping[str, str] | None = None,
) -> RoleSlotFailureSnapshot:
    """Validate exact bytes and project a model-decision-blind population."""

    if not source_dir.is_dir():
        raise RoleSlotFailureReviewError(
            f"source directory does not exist: {source_dir}"
        )
    source_hashes = {
        name: _file_sha256(source_dir / name) for name in CORE_SOURCE_FILES
    }
    expected = (
        dict(EXPECTED_SOURCE_FILE_SHA256)
        if expected_hashes is None
        else dict(expected_hashes)
    )
    if set(expected) != set(CORE_SOURCE_FILES):
        raise RoleSlotFailureReviewError(
            "expected hashes must identify every v6 diagnostic core file"
        )
    if source_hashes != expected:
        drift = {
            name: {"expected": expected[name], "observed": source_hashes[name]}
            for name in CORE_SOURCE_FILES
            if source_hashes[name] != expected[name]
        }
        raise RoleSlotFailureReviewError(
            f"source artifact identity drifted after locking: {drift}"
        )
    manifest = RoleSlotDevelopmentManifest.model_validate(
        _read_json_object(source_dir / "manifest.json")
    )
    execution = RoleSlotDevelopmentExecution.model_validate(
        _read_json_object(source_dir / "execution.json")
    )
    _validate_execution_observations(
        manifest,
        execution,
        source_hashes["manifest.json"],
    )
    indexed_hashes = _validate_artifact_index(source_dir, execution)
    _validate_child_artifacts(source_dir, execution)
    provider_rows = _read_csv(
        source_dir / "provider-rows.csv",
        _PROVIDER_ROW_COLUMNS,
    )
    if provider_rows != _provider_rows(execution.cases):
        raise RoleSlotFailureReviewError(
            "provider CSV does not preserve every execution candidate"
        )
    fixture_sha256, challenge, prepared_cases = load_frozen_cases("development")
    if fixture_sha256 != manifest.fixture_sha256:
        raise RoleSlotFailureReviewError("current fixture drifted from source manifest")
    if tuple(item.spec for item in prepared_cases) != tuple(
        item.spec for item in manifest.cases
    ):
        raise RoleSlotFailureReviewError("frozen case context drifted")
    if challenge.selection_contract.sha256() != manifest.selection_contract_sha256:
        raise RoleSlotFailureReviewError("selection contract drifted")
    candidates, hidden = _project_candidates(manifest, execution)
    return RoleSlotFailureSnapshot(
        source_file_hashes=source_hashes,
        indexed_file_hashes=indexed_hashes,
        manifest=manifest,
        execution=execution,
        candidates=candidates,
        hidden_traces=hidden,
        selection_contract=challenge.selection_contract,
    )

def _walk_mapping_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            if isinstance(key, str):
                keys.add(key)
            keys.update(_walk_mapping_keys(child))
    elif isinstance(value, list | tuple):
        for child in value:
            keys.update(_walk_mapping_keys(child))
    return keys


def _packet_rows(snapshot: RoleSlotFailureSnapshot) -> list[dict[str, Any]]:
    rows = [
        {**asdict(candidate), "identity_sha256": candidate.identity_sha256}
        for candidate in snapshot.candidates
    ]
    leaked = sorted(_FORBIDDEN_REVIEWER_KEYS.intersection(_walk_mapping_keys(rows)))
    if leaked:
        raise RoleSlotFailureReviewError(
            f"reviewer packet leaks v6 decision fields: {leaked}"
        )
    return rows


def _packet_manifest(
    snapshot: RoleSlotFailureSnapshot,
    source_lock_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": "openalex_role_slot_v6_failure_diagnostic_packet",
        "prepared_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "production_connected": False,
        "report_workflow_connected": False,
        "diagnostic_only": True,
        "executed_revision": EXPECTED_EXECUTED_REVISION,
        "source_lock_sha256": _file_sha256(source_lock_path),
        "source_file_sha256": snapshot.source_file_hashes,
        "row_count": len(snapshot.candidates),
        "case_count": len(CASE_IDS),
        "rows": _packet_rows(snapshot),
        "valid_label_combinations": [
            list(values) for values in sorted(VALID_LABEL_COMBINATIONS)
        ],
        "role_label_contract": {
            "supported_role_ids_json": (
                "JSON array containing only role IDs declared for the case"
            ),
            "title_supported_role_ids_json": (
                "JSON array that must be a subset of supported_role_ids_json"
            ),
        },
        "measurement_limit": MEASUREMENT_LIMIT,
    }


def _packet_readme(snapshot: RoleSlotFailureSnapshot) -> str:
    counts = Counter(candidate.case_id for candidate in snapshot.candidates)
    cases = "\n".join(
        f"| {case_id} | {counts[case_id]} |" for case_id in CASE_IDS
    )
    return f"""# Frozen role-slot candidate review

This packet contains {len(snapshot.candidates)} OpenAlex title-and-abstract rows
from eight frozen research questions. Preparing and summarizing it makes zero
API or model calls.

Do not edit packet_manifest.json. Complete only labels.csv and
reviewer_declaration.csv. Rows may be reordered, but every context and identity
field must remain unchanged. Do not inspect the source execution, automated
model outputs, consensus decisions, selected sets, or the separate source-lock
file until after returning the completed packet.

| Case | Candidate rows |
|---|---:|
{cases}

For each row:

1. Set direct_relevance to YES when the frozen title and abstract directly
   address the topic, NO when they only share a broad field, or UNVERIFIABLE
   when the frozen text is insufficient.
2. Set baseline_novelty to YES or NO only for a directly relevant row, N/A for
   a directly irrelevant row, and UNVERIFIABLE otherwise. Novelty is relative
   only to baseline_sources_json, not the whole literature.
3. Set abstract_sufficient to YES for a relevance judgment and NO only with
   the UNVERIFIABLE combination.
4. Enter every supported code-owned role ID as a JSON array in
   supported_role_ids_json, for example ["role_one","role_two"]. Use [] when no
   declared role is supported. Enter the subset supported by title text in
   title_supported_role_ids_json.
5. Give a source-grounded review_note explaining the judgment.

Allowed relevance combinations are YES / YES-or-NO / YES,
NO / N/A / YES, and UNVERIFIABLE / UNVERIFIABLE / NO in
direct_relevance / baseline_novelty / abstract_sufficient order.

Every row must be reviewed. Declare any generative-AI use honestly in
reviewer_declaration.csv; NONE and LANGUAGE_ONLY are eligible, while
substantive generated judgments are retained but not evaluated. External URL
checks are encouraged but optional because this diagnostic concerns the exact
frozen text; record ALL_ATTEMPTED, SOME, or NONE.

The review is diagnostic only. It cannot reverse the failed v6 experiment,
open the unseen cohort, validate a successor, or authorize production Tool
Calling.
"""


def prepare_packet(
    source_dir: Path,
    source_lock_path: Path,
    packet_dir: Path,
) -> dict[str, Any]:
    """Create a separate packet whose rows contain no automated outcome."""

    if packet_dir.exists():
        raise RoleSlotFailureReviewError(
            f"refusing to overwrite diagnostic packet: {packet_dir}"
        )
    source_lock = _load_source_lock(source_lock_path)
    snapshot = validate_finalized_source(
        source_dir,
        expected_hashes=source_lock.source_file_sha256,
    )
    if snapshot.indexed_file_hashes != source_lock.indexed_file_sha256:
        raise RoleSlotFailureReviewError(
            "indexed source identities drifted after diagnostic locking"
        )
    try:
        packet_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise RoleSlotFailureReviewError(
            f"could not create diagnostic packet {packet_dir}: {exc}"
        ) from exc
    manifest = _packet_manifest(snapshot, source_lock_path)
    label_rows = [
        {
            **asdict(candidate),
            **{field: "" for field in LABEL_VALUE_FIELDS},
        }
        for candidate in snapshot.candidates
    ]
    _write_csv_new(packet_dir / "labels.csv", LABEL_FIELDS, label_rows)
    _write_csv_new(
        packet_dir / "reviewer_declaration.csv",
        DECLARATION_FIELDS,
        [{}],
    )
    _write_text_new(packet_dir / "README.md", _packet_readme(snapshot))
    _write_text_new(
        packet_dir / "packet_manifest.json",
        _json_text(manifest),
    )
    return manifest


def _mapping_string(value: Mapping[str, Any], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str):
        raise RoleSlotFailureReviewError(f"{field} must be a string")
    return item


def _candidate_from_mapping(
    value: Mapping[str, Any],
) -> RoleSlotFailureCandidate:
    raw_index = value.get("provider_result_index")
    try:
        provider_result_index = int(raw_index)
    except (TypeError, ValueError) as exc:
        raise RoleSlotFailureReviewError(
            "provider_result_index must be an integer"
        ) from exc
    return RoleSlotFailureCandidate(
        case_id=_mapping_string(value, "case_id"),
        provider_result_index=provider_result_index,
        candidate_sha256=_mapping_string(value, "candidate_sha256"),
        topic=_mapping_string(value, "topic"),
        query=_mapping_string(value, "query"),
        baseline_sources_json=_mapping_string(value, "baseline_sources_json"),
        required_roles_json=_mapping_string(value, "required_roles_json"),
        scope_roles_json=_mapping_string(value, "scope_roles_json"),
        supporting_roles_json=_mapping_string(value, "supporting_roles_json"),
        title=_mapping_string(value, "title"),
        url=_mapping_string(value, "url"),
        doi=_mapping_string(value, "doi"),
        publisher=_mapping_string(value, "publisher"),
        published_date=_mapping_string(value, "published_date"),
        abstract=_mapping_string(value, "abstract"),
        summary_source=_mapping_string(value, "summary_source"),
    )


def _manifest_candidates(
    manifest: dict[str, Any],
    snapshot: RoleSlotFailureSnapshot,
    source_lock_path: Path,
) -> dict[tuple[str, int, str], RoleSlotFailureCandidate]:
    expected_header = {
        "schema_version": 1,
        "mode": "openalex_role_slot_v6_failure_diagnostic_packet",
        "production_connected": False,
        "report_workflow_connected": False,
        "diagnostic_only": True,
        "executed_revision": EXPECTED_EXECUTED_REVISION,
        "source_lock_sha256": _file_sha256(source_lock_path),
        "source_file_sha256": snapshot.source_file_hashes,
        "row_count": EXPECTED_CANDIDATE_COUNT,
        "case_count": len(CASE_IDS),
        "valid_label_combinations": [
            list(values) for values in sorted(VALID_LABEL_COMBINATIONS)
        ],
        "role_label_contract": {
            "supported_role_ids_json": (
                "JSON array containing only role IDs declared for the case"
            ),
            "title_supported_role_ids_json": (
                "JSON array that must be a subset of supported_role_ids_json"
            ),
        },
        "measurement_limit": MEASUREMENT_LIMIT,
    }
    for key, expected in expected_header.items():
        if manifest.get(key) != expected:
            raise RoleSlotFailureReviewError(
                f"diagnostic packet manifest drifted for {key}"
            )
    leaked = sorted(
        _FORBIDDEN_REVIEWER_KEYS.intersection(_walk_mapping_keys(manifest))
    )
    if leaked:
        raise RoleSlotFailureReviewError(
            f"diagnostic packet manifest leaks v6 decision fields: {leaked}"
        )
    rows = manifest.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_CANDIDATE_COUNT:
        raise RoleSlotFailureReviewError(
            "diagnostic packet manifest row count is not inspectable"
        )
    candidates: dict[tuple[str, int, str], RoleSlotFailureCandidate] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise RoleSlotFailureReviewError("packet rows must be objects")
        candidate = _candidate_from_mapping(row)
        if row.get("identity_sha256") != candidate.identity_sha256:
            raise RoleSlotFailureReviewError(
                f"packet identity hash drifted for {candidate.row_id}"
            )
        if candidate.key in candidates:
            raise RoleSlotFailureReviewError(
                f"packet contains duplicate identity {candidate.row_id}"
            )
        candidates[candidate.key] = candidate
    expected = {candidate.key: candidate for candidate in snapshot.candidates}
    if candidates != expected:
        raise RoleSlotFailureReviewError(
            "packet candidates do not match source-locked rows"
        )
    return candidates


def _parse_review_role_ids(
    value: str,
    *,
    candidate: RoleSlotFailureCandidate,
    field: str,
) -> tuple[str, ...]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RoleSlotFailureReviewError(
            f"{candidate.row_id} {field} must be a JSON array"
        ) from exc
    if not isinstance(parsed, list) or any(
        not isinstance(item, str) for item in parsed
    ):
        raise RoleSlotFailureReviewError(
            f"{candidate.row_id} {field} must contain only role IDs"
        )
    role_ids = tuple(parsed)
    if len(role_ids) != len(set(role_ids)):
        raise RoleSlotFailureReviewError(
            f"{candidate.row_id} {field} contains duplicate role IDs"
        )
    unknown = sorted(set(role_ids) - set(candidate.declared_role_ids))
    if unknown:
        raise RoleSlotFailureReviewError(
            f"{candidate.row_id} {field} contains unknown role IDs: {unknown}"
        )
    return tuple(sorted(role_ids))


def _validated_label(
    row: dict[str, str],
    expected: RoleSlotFailureCandidate,
) -> dict[str, Any] | None:
    observed = _candidate_from_mapping(row)
    if observed != expected:
        raise RoleSlotFailureReviewError(
            f"{expected.row_id} context or identity drifted"
        )
    values = [row[field].strip() for field in LABEL_VALUE_FIELDS]
    if not any(values):
        return None
    if not all(values):
        raise RoleSlotFailureReviewError(
            f"{expected.row_id} is partially completed"
        )
    relevance = row["direct_relevance"].strip().upper()
    novelty = row["baseline_novelty"].strip().upper()
    sufficient = row["abstract_sufficient"].strip().upper()
    if (relevance, novelty, sufficient) not in VALID_LABEL_COMBINATIONS:
        raise RoleSlotFailureReviewError(
            f"{expected.row_id} has invalid diagnostic labels: "
            f"{relevance}/{novelty}/{sufficient}"
        )
    supported = _parse_review_role_ids(
        row["supported_role_ids_json"].strip(),
        candidate=expected,
        field="supported_role_ids_json",
    )
    title_supported = _parse_review_role_ids(
        row["title_supported_role_ids_json"].strip(),
        candidate=expected,
        field="title_supported_role_ids_json",
    )
    if not set(title_supported).issubset(supported):
        raise RoleSlotFailureReviewError(
            f"{expected.row_id} title-supported roles must be supported roles"
        )
    note = row["review_note"].strip()
    if len("".join(note.split())) < 12:
        raise RoleSlotFailureReviewError(
            f"{expected.row_id} review_note is too short to ground the judgment"
        )
    return {
        "case_id": expected.case_id,
        "provider_result_index": expected.provider_result_index,
        "candidate_sha256": expected.candidate_sha256,
        "row_id": expected.row_id,
        "direct_relevance": relevance,
        "baseline_novelty": novelty,
        "abstract_sufficient": sufficient,
        "supported_role_ids": list(supported),
        "title_supported_role_ids": list(title_supported),
        "review_note": note,
    }

def _human_candidate_eligible(
    candidate: RoleSlotFailureCandidate,
    label: Mapping[str, Any],
    contract: Any,
) -> bool:
    if (
        label["direct_relevance"] != "YES"
        or label["abstract_sufficient"] != "YES"
    ):
        return False
    groups = candidate.role_groups
    supported = set(label["supported_role_ids"])
    required = len(supported.intersection(groups["required"]))
    context = len(
        supported.intersection((*groups["scope"], *groups["supporting"]))
    )
    title = len(label["title_supported_role_ids"])
    return (
        required >= contract.minimum_candidate_required_roles
        and context >= contract.minimum_candidate_context_roles
        and title >= contract.minimum_candidate_title_anchor_roles
    )


def _human_covering_set(
    case_candidates: Sequence[RoleSlotFailureCandidate],
    labels: Mapping[tuple[str, int, str], Mapping[str, Any]],
    contract: Any,
) -> tuple[RoleSlotFailureCandidate, ...]:
    if not case_candidates:
        return ()
    groups = case_candidates[0].role_groups
    eligible = tuple(
        sorted(
            (
                candidate
                for candidate in case_candidates
                if _human_candidate_eligible(
                    candidate,
                    labels[candidate.key],
                    contract,
                )
            ),
            key=lambda item: (item.provider_result_index, item.candidate_sha256),
        )
    )
    for size in range(1, contract.maximum_selected_sources_per_case + 1):
        valid: list[tuple[RoleSlotFailureCandidate, ...]] = []
        for group in combinations(eligible, size):
            supported = set().union(
                *(
                    set(labels[candidate.key]["supported_role_ids"])
                    for candidate in group
                )
            )
            if (
                set(groups["required"]).issubset(supported)
                and len(supported.intersection(groups["scope"]))
                >= contract.minimum_scope_roles
                and len(supported.intersection(groups["supporting"]))
                >= contract.minimum_supporting_roles
            ):
                valid.append(group)
        if valid:
            return min(
                valid,
                key=lambda group: (
                    tuple(item.provider_result_index for item in group),
                    tuple(item.candidate_sha256 for item in group),
                ),
            )
    return ()


def _safe_rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _diagnostic_metrics(
    snapshot: RoleSlotFailureSnapshot,
    completed: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    labels = {
        (
            str(row["case_id"]),
            int(row["provider_result_index"]),
            str(row["candidate_sha256"]),
        ): row
        for row in completed
    }
    inspectable = [
        row for row in completed if row["direct_relevance"] != "UNVERIFIABLE"
    ]
    relevant = [row for row in completed if row["direct_relevance"] == "YES"]
    irrelevant = [row for row in completed if row["direct_relevance"] == "NO"]
    unverifiable = [
        row for row in completed if row["direct_relevance"] == "UNVERIFIABLE"
    ]
    novel_relevant = [
        row
        for row in completed
        if row["direct_relevance"] == "YES"
        and row["baseline_novelty"] == "YES"
    ]

    role_confusion = Counter()
    title_confusion = Counter()
    admission_confusion = Counter()
    model_observed_candidate_count = 0
    attribution = Counter()
    for candidate in snapshot.candidates:
        label = labels[candidate.key]
        trace = snapshot.hidden_traces[candidate.key]
        if label["direct_relevance"] == "NO":
            attribution["retrieval_noise"] += 1
        elif label["direct_relevance"] == "UNVERIFIABLE":
            attribution["frozen_text_insufficient"] += 1
        if not trace["model_observed"]:
            attribution["model_not_observed"] += 1
            continue
        model_observed_candidate_count += 1
        model_roles = set(trace["consensus_supported_role_ids"])
        human_roles = set(label["supported_role_ids"])
        for role_id in candidate.declared_role_ids:
            model_positive = role_id in model_roles
            human_positive = role_id in human_roles
            role_confusion[
                (
                    "true_positive"
                    if model_positive and human_positive
                    else "false_positive"
                    if model_positive
                    else "false_negative"
                    if human_positive
                    else "true_negative"
                )
            ] += 1
        model_title = set(trace["title_anchor_role_ids"])
        human_title = set(label["title_supported_role_ids"])
        for role_id in candidate.declared_role_ids:
            model_positive = role_id in model_title
            human_positive = role_id in human_title
            title_confusion[
                (
                    "true_positive"
                    if model_positive and human_positive
                    else "false_positive"
                    if model_positive
                    else "false_negative"
                    if human_positive
                    else "true_negative"
                )
            ] += 1
        model_keep = trace["candidate_action"] == "KEEP"
        human_keep = _human_candidate_eligible(
            candidate,
            label,
            snapshot.selection_contract,
        )
        admission_confusion[
            (
                "true_positive"
                if model_keep and human_keep
                else "false_positive"
                if model_keep
                else "false_negative"
                if human_keep
                else "true_negative"
            )
        ] += 1
        if model_roles - human_roles:
            attribution["candidate_with_consensus_false_positive"] += 1
        if human_roles - model_roles:
            attribution["candidate_with_consensus_false_negative"] += 1

    candidates_by_case = {
        case_id: tuple(
            candidate
            for candidate in snapshot.candidates
            if candidate.case_id == case_id
        )
        for case_id in CASE_IDS
    }
    human_sets = {
        case_id: _human_covering_set(
            candidates,
            labels,
            snapshot.selection_contract,
        )
        for case_id, candidates in candidates_by_case.items()
    }
    human_coverable = sorted(
        case_id for case_id, group in human_sets.items() if group
    )
    model_selected = sorted(
        case.case_id
        for case in snapshot.execution.cases
        if case.case_audit is not None and case.case_audit.action == "SELECT"
    )
    model_unobserved = sorted(
        case.case_id
        for case in snapshot.execution.cases
        if case.case_audit is None
    )
    attribution["case_without_human_covering_set"] = (
        len(CASE_IDS) - len(human_coverable)
    )

    role_positive = (
        role_confusion["true_positive"] + role_confusion["false_positive"]
    )
    human_role_positive = (
        role_confusion["true_positive"] + role_confusion["false_negative"]
    )
    title_positive = (
        title_confusion["true_positive"] + title_confusion["false_positive"]
    )
    human_title_positive = (
        title_confusion["true_positive"] + title_confusion["false_negative"]
    )
    return {
        "candidate_count": len(snapshot.candidates),
        "inspectable_candidate_count": len(inspectable),
        "direct_relevant_count": len(relevant),
        "direct_irrelevant_count": len(irrelevant),
        "unverifiable_count": len(unverifiable),
        "retrieval_noise_rate_among_inspectable": _safe_rate(
            len(irrelevant), len(inspectable)
        ),
        "frozen_text_insufficiency_rate": _safe_rate(
            len(unverifiable), len(snapshot.candidates)
        ),
        "novel_relevant_candidate_count": len(novel_relevant),
        "novel_relevant_case_ids": sorted(
            {str(row["case_id"]) for row in novel_relevant}
        ),
        "human_supported_role_assignment_count": sum(
            len(row["supported_role_ids"]) for row in completed
        ),
        "human_title_supported_role_assignment_count": sum(
            len(row["title_supported_role_ids"]) for row in completed
        ),
        "model_observed_candidate_count": model_observed_candidate_count,
        "model_unobserved_candidate_count": (
            len(snapshot.candidates) - model_observed_candidate_count
        ),
        "role_confusion": dict(sorted(role_confusion.items())),
        "role_precision": _safe_rate(
            role_confusion["true_positive"], role_positive
        ),
        "role_recall": _safe_rate(
            role_confusion["true_positive"], human_role_positive
        ),
        "unsupported_consensus_role_rate": _safe_rate(
            role_confusion["false_positive"], role_positive
        ),
        "title_anchor_confusion": dict(sorted(title_confusion.items())),
        "title_anchor_precision": _safe_rate(
            title_confusion["true_positive"], title_positive
        ),
        "title_anchor_recall": _safe_rate(
            title_confusion["true_positive"], human_title_positive
        ),
        "candidate_admission_confusion": dict(
            sorted(admission_confusion.items())
        ),
        "human_coverable_case_ids": human_coverable,
        "human_covering_sets": {
            case_id: [candidate.row_id for candidate in group]
            for case_id, group in human_sets.items()
            if group
        },
        "model_selected_case_ids": model_selected,
        "model_unobserved_case_ids": model_unobserved,
        "model_missed_human_coverable_case_ids": sorted(
            set(human_coverable) - set(model_selected)
        ),
        "model_selected_without_human_cover_case_ids": sorted(
            set(model_selected) - set(human_coverable)
        ),
        "attribution_counts": dict(sorted(attribution.items())),
    }


def summarize_packet(
    source_dir: Path,
    source_lock_path: Path,
    packet_dir: Path,
) -> dict[str, Any]:
    """Validate returned labels and join hidden v6 traces only here."""

    if not packet_dir.is_dir():
        raise RoleSlotFailureReviewError(
            f"diagnostic packet directory does not exist: {packet_dir}"
        )
    source_lock = _load_source_lock(source_lock_path)
    snapshot = validate_finalized_source(
        source_dir,
        expected_hashes=source_lock.source_file_sha256,
    )
    if snapshot.indexed_file_hashes != source_lock.indexed_file_sha256:
        raise RoleSlotFailureReviewError(
            "indexed source identities drifted after diagnostic locking"
        )
    manifest = _read_json_object(packet_dir / "packet_manifest.json")
    expected_candidates = _manifest_candidates(
        manifest,
        snapshot,
        source_lock_path,
    )
    label_rows = _read_csv(packet_dir / "labels.csv", LABEL_FIELDS)
    observed_keys = [_candidate_from_mapping(row).key for row in label_rows]
    if len(observed_keys) != len(set(observed_keys)):
        raise RoleSlotFailureReviewError(
            "diagnostic labels contain duplicate candidate identities"
        )
    if set(observed_keys) != set(expected_candidates):
        missing = sorted(set(expected_candidates) - set(observed_keys))
        extra = sorted(set(observed_keys) - set(expected_candidates))
        raise RoleSlotFailureReviewError(
            f"diagnostic label identities drifted; missing={missing}, "
            f"extra={extra}"
        )
    completed: dict[tuple[str, int, str], dict[str, Any]] = {}
    incomplete_row_ids: list[str] = []
    for row in label_rows:
        candidate = _candidate_from_mapping(row)
        validated = _validated_label(row, expected_candidates[candidate.key])
        if validated is None:
            incomplete_row_ids.append(candidate.row_id)
        else:
            completed[candidate.key] = validated

    declaration_rows = _read_csv(
        packet_dir / "reviewer_declaration.csv",
        DECLARATION_FIELDS,
    )
    if len(declaration_rows) != 1:
        raise RoleSlotFailureReviewError(
            "reviewer_declaration.csv must contain exactly one row"
        )
    declaration = _validated_declaration(declaration_rows[0])
    method_issues: list[str] = []
    if declaration is not None and declaration["reviewed_all"] != "YES":
        method_issues.append("reviewer_did_not_confirm_all_rows")
    if incomplete_row_ids or declaration is None:
        protocol_status = "incomplete"
    elif declaration["generative_ai_use"] not in ELIGIBLE_AI_USE:
        protocol_status = "excluded_substantive_ai"
    elif method_issues:
        protocol_status = "not_inspectable"
    else:
        protocol_status = "complete"
    ordered = [completed[key] for key in sorted(completed)]
    metrics = (
        _diagnostic_metrics(snapshot, ordered)
        if protocol_status == "complete"
        else None
    )
    return {
        "schema_version": 1,
        "mode": "openalex_role_slot_v6_failure_diagnostic_result",
        "production_connected": False,
        "report_workflow_connected": False,
        "diagnostic_only": True,
        "original_v6_result": "irrecoverably_failed",
        "original_source_lock_readiness": "not_ready",
        "original_source_value_state": "not_evaluated",
        "v6_rescue_authorized": False,
        "z_cohort_authorized": False,
        "production_connection_authorized": False,
        "executed_revision": EXPECTED_EXECUTED_REVISION,
        "source_lock_sha256": _file_sha256(source_lock_path),
        "source_file_sha256": snapshot.source_file_hashes,
        "packet_manifest_sha256": _file_sha256(
            packet_dir / "packet_manifest.json"
        ),
        "protocol_status": protocol_status,
        "diagnostic_state": (
            "evaluated_diagnostic_only"
            if protocol_status == "complete"
            else "not_evaluated"
        ),
        "expected_row_count": EXPECTED_CANDIDATE_COUNT,
        "completed_row_count": len(completed),
        "incomplete_row_ids": sorted(incomplete_row_ids),
        "method_issues": method_issues,
        "declaration": declaration,
        "metrics": metrics,
        "measurement_limit": MEASUREMENT_LIMIT,
    }


def write_summary(path: Path, result: dict[str, Any]) -> None:
    """Persist one interpretation without replacing prior human evidence."""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RoleSlotFailureReviewError(
            f"could not create summary parent {path.parent}: {exc}"
        ) from exc
    _write_text_new(path, _json_text(result))


def _write_json_stdout(value: object) -> None:
    """Emit UTF-8 even when a legacy Windows console advertises GBK."""

    text = _json_text(value)
    stdout_buffer = getattr(sys.stdout, "buffer", None)
    if stdout_buffer is None:
        sys.stdout.write(text)
        return
    stdout_buffer.write(text.encode("utf-8"))
    stdout_buffer.flush()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lock, prepare, or summarize the zero-network v6 diagnostic."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    lock = commands.add_parser("lock")
    lock.add_argument("--source-dir", type=Path, required=True)
    lock.add_argument("--output", type=Path, required=True)
    lock.add_argument("--owner", required=True)
    lock.add_argument("--note")
    lock.add_argument("--confirm-authorized-output", action="store_true")

    prepare = commands.add_parser("prepare")
    prepare.add_argument("--source-dir", type=Path, required=True)
    prepare.add_argument("--source-lock", type=Path, required=True)
    prepare.add_argument("--packet-dir", type=Path, required=True)

    summarize = commands.add_parser("summarize")
    summarize.add_argument("--source-dir", type=Path, required=True)
    summarize.add_argument("--source-lock", type=Path, required=True)
    summarize.add_argument("--packet-dir", type=Path, required=True)
    summarize.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "lock":
        result: object = create_source_lock(
            args.source_dir,
            args.output,
            study_owner_id=args.owner,
            confirm_authorized_output=args.confirm_authorized_output,
            note=args.note,
        )
        result = result.model_dump(mode="json")
    elif args.command == "prepare":
        result = prepare_packet(
            args.source_dir,
            args.source_lock,
            args.packet_dir,
        )
    else:
        result = summarize_packet(
            args.source_dir,
            args.source_lock,
            args.packet_dir,
        )
        if args.output is not None:
            write_summary(args.output, result)
    _write_json_stdout(result)
    return 0




def create_source_lock(
    source_dir: Path,
    output_path: Path,
    *,
    study_owner_id: str,
    confirm_authorized_output: bool,
    note: str | None = None,
    authorized_at: datetime | None = None,
) -> RoleSlotFailureDiagnosticLock:
    """Bind the provider-complete failed run before a packet exists."""

    if not confirm_authorized_output:
        raise RoleSlotFailureReviewError(
            "diagnostic locking requires authorized-output confirmation"
        )
    if output_path.exists():
        raise RoleSlotFailureReviewError(
            f"refusing to overwrite diagnostic lock: {output_path}"
        )
    snapshot = validate_finalized_source(source_dir)
    lock = RoleSlotFailureDiagnosticLock(
        executed_revision=EXPECTED_EXECUTED_REVISION,
        fixture_sha256=snapshot.manifest.fixture_sha256,
        implementation_sha256=snapshot.manifest.implementation_sha256,
        source_file_sha256=snapshot.source_file_hashes,
        indexed_file_sha256=snapshot.indexed_file_hashes,
        study_owner_id=study_owner_id.strip(),
        authorized_at=authorized_at or datetime.now(UTC),
        note=note.strip() if note and note.strip() else None,
    )
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RoleSlotFailureReviewError(
            f"could not create diagnostic-lock parent {output_path.parent}: {exc}"
        ) from exc
    _write_text_new(output_path, _json_text(lock.model_dump(mode="json")))
    return lock


def _load_source_lock(path: Path) -> RoleSlotFailureDiagnosticLock:
    try:
        return RoleSlotFailureDiagnosticLock.model_validate(
            _read_json_object(path)
        )
    except ValueError as exc:
        if isinstance(exc, RoleSlotFailureReviewError):
            raise
        raise RoleSlotFailureReviewError(
            f"diagnostic source lock is invalid: {exc}"
        ) from exc

if __name__ == "__main__":
    raise SystemExit(main())
