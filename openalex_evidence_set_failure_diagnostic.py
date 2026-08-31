"""Explain the sealed Qwen evidence-set v5 failure without rerunning it.

The schema-4 W01-W08 development run completed, persisted every bounded model
call, and failed its frozen agreement gate.  This utility joins that immutable
mechanical trace to the already completed human labels only after validating
both sources byte-for-byte.  It classifies observable failure surfaces; it
does not repair model output, recalculate v5, open X01-X08, or connect anything
to the production workflow.

The row-level join is private.  A separate projection deliberately contains
only aggregates so a public result can describe the failure without publishing
the reviewer packet or provider-generated candidate-level judgments.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import TypeAdapter

from academic_agent.openalex_evidence_set import (
    EvidenceSetCandidateAudit,
    EvidenceSetCaseAudit,
    JudgePassAudit,
)
from evidence_gap_phase4_review import (
    DECLARATION_FIELDS,
    _file_sha256,
    _read_csv,
    _validated_declaration,
    _write_text_new,
)
from openalex_evidence_set_development import (
    DevelopmentExecution,
    DevelopmentManifest,
    DevelopmentPacket,
    DevelopmentPacketRow,
    JudgeCallJournal,
)
from openalex_scope_link_abstention_review import (
    CONTEXT_FIELDS,
    LABEL_FIELDS,
    LABEL_VALUE_FIELDS,
    VALID_LABEL_COMBINATIONS,
)


CASE_IDS = tuple(f"W{index:02d}" for index in range(1, 9))
EXPECTED_EXECUTED_REVISION = "7a2d73ea9f5d1b4af47e2c6d93aa86999c4711db"
EXPECTED_MECHANICAL_KEY_SHA256 = {
    "manifest.json": (
        "df47b0b53003f8347952d2391a9ab9976ff0bdd2cae637018b8d7f69ee29f7a2"
    ),
    "execution.json": (
        "697472f570f43f9131639244cb19efb79e41fb7941fbf44bc56a79714109d39d"
    ),
    "candidate-decisions.json": (
        "5e958cac0e487e740ae1da23611db12c6f04be1f4d323eaead69cae96b8cce26"
    ),
}
EXPECTED_PRIVATE_SHA256 = {
    "source-lock.json": (
        "8a9747f4240fc7c529d8d8f2a737fb21b502579ad2f69c19587bf093cabba7af"
    ),
    "packet_manifest.json": (
        "68e15abdca46f4a65d33a75aedaa9a0eac2112a90a8b1e6eb1d00e71e59b8616"
    ),
    "labels.csv": (
        "a2a3a16f74d2a7d8790ca90669702c423b0c24a83ccbf779ca5867cbe6338f55"
    ),
    "reviewer_declaration.csv": (
        "5c7686d413f4f3050316950899e7f1806ff2a2a0065eacf0bf39e942917d863d"
    ),
}

FailureClass = Literal[
    "invalid_pass_exposure",
    "stable_abstain",
    "action_instability",
    "role_instability",
    "post_consensus_rejection",
    "stable_keep",
]
FAILURE_CLASSES: tuple[FailureClass, ...] = (
    "invalid_pass_exposure",
    "stable_abstain",
    "action_instability",
    "role_instability",
    "post_consensus_rejection",
    "stable_keep",
)
MEASUREMENT_LIMIT = (
    "This disclosed post-outcome diagnostic associates one eligible reviewer's "
    "frozen title/abstract labels with the sealed Qwen v5 trace. It cannot rescue "
    "v5, establish causality or source truth, open X01-X08, authorize another "
    "provider call, or connect Tool Calling to production."
)


class EvidenceSetFailureDiagnosticError(ValueError):
    """Raised when frozen provenance or a diagnostic invariant does not hold."""


@dataclass(frozen=True)
class MechanicalSnapshot:
    """Strictly validated projection of the immutable Qwen execution."""

    source_sha256: Mapping[str, str]
    manifest: DevelopmentManifest
    execution: DevelopmentExecution
    cases: tuple[EvidenceSetCaseAudit, ...]
    calls: Mapping[tuple[str, int], JudgeCallJournal]


@dataclass(frozen=True)
class HumanLabel:
    """One eligible label with context already matched to the public packet."""

    case_id: str
    provider_result_index: int
    candidate_sha256: str
    direct_relevance: str
    semantic_scope_link: str
    baseline_novelty: str
    abstract_sufficient: str


@dataclass(frozen=True)
class HumanSnapshot:
    """Validated private labels; free text is intentionally not retained."""

    source_sha256: Mapping[str, str]
    declaration: Mapping[str, Any]
    packet_rows: tuple[DevelopmentPacketRow, ...]
    labels: Mapping[tuple[str, str], HumanLabel]


def _json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceSetFailureDiagnosticError(
            f"cannot read JSON object {path}: {type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise EvidenceSetFailureDiagnosticError(f"{path} must contain one JSON object")
    return value


def _expected_mechanical_files() -> set[str]:
    return {
        "manifest.json",
        "execution.json",
        "candidate-decisions.json",
        *(f"case-decisions/{case_id}.json" for case_id in CASE_IDS),
        *(
            f"judge-calls/{case_id}-pass-{pass_number}.json"
            for case_id in CASE_IDS
            for pass_number in (1, 2)
        ),
    }


def _validate_indexed_files(
    source_dir: Path,
    expected_key_sha256: Mapping[str, str],
) -> dict[str, str]:
    """Hash every indexed byte before any semantic response is parsed."""

    index = _json_object(source_dir / "artifact-index.json")
    if index.get("mode") != "openalex_evidence_set_v5_development_artifact_index":
        raise EvidenceSetFailureDiagnosticError("mechanical artifact-index mode drifted")
    file_hashes = index.get("files")
    if not isinstance(file_hashes, dict) or set(file_hashes) != _expected_mechanical_files():
        raise EvidenceSetFailureDiagnosticError(
            "mechanical artifact-index file coverage drifted"
        )
    if any(
        not isinstance(path, str)
        or not isinstance(digest, str)
        or len(digest) != 64
        for path, digest in file_hashes.items()
    ):
        raise EvidenceSetFailureDiagnosticError(
            "mechanical artifact-index contains an invalid SHA-256 entry"
        )

    observed: dict[str, str] = {}
    for relative_path in sorted(file_hashes):
        path = source_dir / relative_path
        if not path.is_file():
            raise EvidenceSetFailureDiagnosticError(
                f"mechanical artifact is missing: {relative_path}"
            )
        observed[relative_path] = _file_sha256(path)
    if observed != dict(sorted(file_hashes.items())):
        raise EvidenceSetFailureDiagnosticError(
            "mechanical artifact bytes drifted from artifact-index"
        )
    for relative_path, expected in expected_key_sha256.items():
        if observed.get(relative_path) != expected:
            raise EvidenceSetFailureDiagnosticError(
                f"frozen mechanical identity drifted: {relative_path}"
            )
    return observed


def load_mechanical_snapshot(
    source_dir: Path,
    *,
    expected_key_sha256: Mapping[str, str] = EXPECTED_MECHANICAL_KEY_SHA256,
) -> MechanicalSnapshot:
    """Validate the complete public trace and its repeated serialization seams."""

    if not source_dir.is_dir():
        raise EvidenceSetFailureDiagnosticError(
            f"mechanical source directory does not exist: {source_dir}"
        )
    observed = _validate_indexed_files(source_dir, expected_key_sha256)
    manifest = DevelopmentManifest.model_validate_json(
        (source_dir / "manifest.json").read_text(encoding="utf-8")
    )
    execution = DevelopmentExecution.model_validate_json(
        (source_dir / "execution.json").read_text(encoding="utf-8")
    )
    if (
        manifest.schema_version != 4
        or manifest.requested_provider != "qwen"
        or manifest.requested_model != "qwen3.5-plus"
        or manifest.maximum_model_call_count != 16
    ):
        raise EvidenceSetFailureDiagnosticError(
            "mechanical manifest is not the frozen Qwen schema-4 contract"
        )
    if execution.manifest_sha256 != observed["manifest.json"]:
        raise EvidenceSetFailureDiagnosticError(
            "execution does not bind the frozen manifest bytes"
        )
    if (
        execution.overall_state != "completed"
        or execution.completed_model_call_count != 16
        or execution.completed_case_count != 8
        or execution.persisted_candidate_decision_count != 64
        or execution.disposition_agreement_numerator != 38
        or execution.disposition_agreement_denominator != 64
        or execution.mechanical_agreement_gate_passed is not False
        or execution.openalex_request_count != 0
        or execution.production_connected
        or execution.report_workflow_connected
        or execution.planner_trigger_connected
    ):
        raise EvidenceSetFailureDiagnosticError(
            "execution summary drifted from the sealed failed development result"
        )
    if any(
        call.state != "completed"
        or call.request.requested_model != "qwen3.5-plus"
        or call.response is None
        or call.response.returned_model != "qwen3.5-plus"
        for call in execution.calls
    ):
        raise EvidenceSetFailureDiagnosticError(
            "one or more model-call identities drifted from the frozen run"
        )

    case_adapter = TypeAdapter(tuple[EvidenceSetCaseAudit, ...])
    cases = case_adapter.validate_json(
        (source_dir / "candidate-decisions.json").read_text(encoding="utf-8")
    )
    if cases != execution.case_decisions:
        raise EvidenceSetFailureDiagnosticError(
            "candidate decisions were computed but changed at the aggregate seam"
        )
    if tuple(case.case_id for case in cases) != CASE_IDS:
        raise EvidenceSetFailureDiagnosticError("mechanical case order drifted")

    calls = {(call.case_id, call.pass_number): call for call in execution.calls}
    if len(calls) != 16:
        raise EvidenceSetFailureDiagnosticError("model-call identities are not unique")
    for key, call in calls.items():
        relative_path = f"judge-calls/{key[0]}-pass-{key[1]}.json"
        serialized = JudgeCallJournal.model_validate_json(
            (source_dir / relative_path).read_text(encoding="utf-8")
        )
        if serialized != call:
            raise EvidenceSetFailureDiagnosticError(
                f"model call changed at its file boundary: {relative_path}"
            )
    for case in cases:
        relative_path = f"case-decisions/{case.case_id}.json"
        serialized = EvidenceSetCaseAudit.model_validate_json(
            (source_dir / relative_path).read_text(encoding="utf-8")
        )
        if serialized != case:
            raise EvidenceSetFailureDiagnosticError(
                f"case decision changed at its file boundary: {relative_path}"
            )
    return MechanicalSnapshot(observed, manifest, execution, cases, calls)


def _expected_context(row: DevelopmentPacketRow) -> dict[str, str]:
    values = row.model_dump(mode="python")
    return {
        field: "" if values[field] is None else str(values[field])
        for field in CONTEXT_FIELDS
    }


def _validated_human_label(
    row: Mapping[str, str],
    expected: DevelopmentPacketRow,
) -> HumanLabel:
    observed_context = {field: row[field] for field in CONTEXT_FIELDS}
    if observed_context != _expected_context(expected):
        raise EvidenceSetFailureDiagnosticError(
            f"human label context drifted for {expected.case_id}/"
            f"{expected.candidate_sha256}"
        )
    values = tuple(row[field].strip() for field in LABEL_VALUE_FIELDS)
    if not all(values):
        raise EvidenceSetFailureDiagnosticError(
            f"human label is incomplete for {expected.case_id}/"
            f"{expected.candidate_sha256}"
        )
    direct, semantic, novelty, sufficient, note = values
    normalized = (
        direct.upper(),
        semantic.upper(),
        novelty.upper(),
        sufficient.upper(),
    )
    if normalized not in VALID_LABEL_COMBINATIONS:
        raise EvidenceSetFailureDiagnosticError(
            f"human label values are invalid for {expected.case_id}/"
            f"{expected.candidate_sha256}"
        )
    if len("".join(note.split())) < 12:
        raise EvidenceSetFailureDiagnosticError(
            f"human label note is not grounded for {expected.case_id}/"
            f"{expected.candidate_sha256}"
        )
    return HumanLabel(
        case_id=expected.case_id,
        provider_result_index=expected.provider_result_index,
        candidate_sha256=expected.candidate_sha256,
        direct_relevance=normalized[0],
        semantic_scope_link=normalized[1],
        baseline_novelty=normalized[2],
        abstract_sufficient=normalized[3],
    )


def load_human_snapshot(
    *,
    source_lock_path: Path,
    packet_manifest_path: Path,
    labels_path: Path,
    declaration_path: Path,
    expected_sha256: Mapping[str, str] = EXPECTED_PRIVATE_SHA256,
) -> HumanSnapshot:
    """Hash all private inputs before parsing any human judgment."""

    paths = {
        "source-lock.json": source_lock_path,
        "packet_manifest.json": packet_manifest_path,
        "labels.csv": labels_path,
        "reviewer_declaration.csv": declaration_path,
    }
    if set(paths) != set(expected_sha256):
        raise EvidenceSetFailureDiagnosticError("private source identity is incomplete")
    observed: dict[str, str] = {}
    for name, path in paths.items():
        if not path.is_file():
            raise EvidenceSetFailureDiagnosticError(f"private source is missing: {name}")
        observed[name] = _file_sha256(path)
    if observed != dict(expected_sha256):
        drifted = sorted(
            name for name in observed if observed[name] != expected_sha256[name]
        )
        raise EvidenceSetFailureDiagnosticError(
            f"private source bytes drifted: {drifted}"
        )

    # Parsing begins only after all four private byte identities are known.
    packet = DevelopmentPacket.model_validate_json(
        packet_manifest_path.read_text(encoding="utf-8")
    )
    if packet.source_lock_sha256 != observed["source-lock.json"]:
        raise EvidenceSetFailureDiagnosticError(
            "packet manifest does not bind the frozen source lock"
        )
    label_rows = _read_csv(labels_path, LABEL_FIELDS)
    if len(label_rows) != 64:
        raise EvidenceSetFailureDiagnosticError("human label denominator must be 64")
    expected_by_key = {
        (row.case_id, row.candidate_sha256): row for row in packet.rows
    }
    if len(expected_by_key) != 64:
        raise EvidenceSetFailureDiagnosticError(
            "packet candidate identities are not unique"
        )
    observed_keys = [
        (row["case_id"], row["candidate_sha256"]) for row in label_rows
    ]
    if len(observed_keys) != len(set(observed_keys)):
        raise EvidenceSetFailureDiagnosticError(
            "human labels contain duplicate candidate identities"
        )
    if set(observed_keys) != set(expected_by_key):
        raise EvidenceSetFailureDiagnosticError(
            "human-label identities drifted from the frozen packet"
        )
    labels = {
        key: _validated_human_label(row, expected_by_key[key])
        for key, row in zip(observed_keys, label_rows, strict=True)
    }

    declarations = _read_csv(declaration_path, DECLARATION_FIELDS)
    if len(declarations) != 1:
        raise EvidenceSetFailureDiagnosticError(
            "reviewer declaration must contain exactly one row"
        )
    declaration = _validated_declaration(declarations[0])
    if declaration is None:
        raise EvidenceSetFailureDiagnosticError("reviewer declaration is incomplete")
    if (
        declaration["reviewed_all"] != "YES"
        or declaration["generative_ai_use"] != "NONE"
        or declaration["external_sources_checked"] != "NONE"
    ):
        raise EvidenceSetFailureDiagnosticError(
            "reviewer declaration is not eligible for this frozen diagnostic"
        )
    direct_counts = Counter(label.direct_relevance for label in labels.values())
    semantic_count = sum(
        label.semantic_scope_link == "YES" for label in labels.values()
    )
    if direct_counts != Counter({"YES": 28, "NO": 36}) or semantic_count != 5:
        raise EvidenceSetFailureDiagnosticError(
            "human aggregate drifted from the published eligible review"
        )
    return HumanSnapshot(observed, declaration, packet.rows, labels)


def _pass_decision(
    judge_pass: JudgePassAudit,
    candidate_sha256: str,
) -> tuple[str, tuple[str, ...]]:
    if judge_pass.state != "valid" or judge_pass.response is None:
        raise EvidenceSetFailureDiagnosticError(
            "invalid pass cannot be interpreted as a candidate decision"
        )
    by_id = {
        decision.candidate_sha256: decision
        for decision in judge_pass.response.decisions
    }
    try:
        decision = by_id[candidate_sha256]
    except KeyError as exc:
        raise EvidenceSetFailureDiagnosticError(
            "valid pass omitted a frozen candidate identity"
        ) from exc
    return decision.action, tuple(sorted(item.role_id for item in decision.role_quotes))


def classify_candidate(
    case: EvidenceSetCaseAudit,
    candidate: EvidenceSetCandidateAudit,
) -> tuple[FailureClass, str | None, str | None]:
    """Apply the frozen precedence without consulting raw invalid content."""

    if case.first_pass.state != "valid" or case.second_pass.state != "valid":
        return "invalid_pass_exposure", None, None
    first_action, first_roles = _pass_decision(
        case.first_pass, candidate.candidate_sha256
    )
    second_action, second_roles = _pass_decision(
        case.second_pass, candidate.candidate_sha256
    )
    if first_action == second_action == "ABSTAIN":
        failure_class: FailureClass = "stable_abstain"
    elif first_action != second_action:
        failure_class = "action_instability"
    elif first_roles != second_roles:
        failure_class = "role_instability"
    elif candidate.action == "ABSTAIN":
        failure_class = "post_consensus_rejection"
    else:
        failure_class = "stable_keep"
    return failure_class, first_action, second_action


def _shape_probe(
    call: JudgeCallJournal,
    expected_order: Sequence[str],
) -> dict[str, Any]:
    """Describe invalid raw shape without producing a repaired v5 response."""

    if call.response is None:
        raise EvidenceSetFailureDiagnosticError(
            "completed invalid-pass call has no persisted provider response"
        )
    raw_content = call.response.raw_content
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError:
        return {
            "case_id": call.case_id,
            "pass_number": call.pass_number,
            "persisted_error_code": "schema_invalid",
            "json_object": False,
            "case_id_matches": False,
            "candidate_order_matches": False,
            "decision_row_coverage_matches": False,
            "recognized_actions_only": False,
            "duplicate_role_id_candidate_count": 0,
            "duplicate_role_quote_count": 0,
        }
    if not isinstance(payload, dict):
        payload = {}
    decisions = payload.get("decisions")
    decision_rows = decisions if isinstance(decisions, list) else []
    duplicate_candidates = 0
    duplicate_quotes = 0
    recognized_actions_only = bool(decision_rows)
    decision_ids: list[object] = []
    for row in decision_rows:
        if not isinstance(row, dict):
            recognized_actions_only = False
            continue
        decision_ids.append(row.get("candidate_sha256"))
        if row.get("action") not in {"KEEP", "ABSTAIN"}:
            recognized_actions_only = False
        quotes = row.get("role_quotes")
        if not isinstance(quotes, list):
            recognized_actions_only = False
            continue
        role_ids = [
            quote.get("role_id")
            for quote in quotes
            if isinstance(quote, dict) and isinstance(quote.get("role_id"), str)
        ]
        duplicates = len(role_ids) - len(set(role_ids))
        if duplicates:
            duplicate_candidates += 1
            duplicate_quotes += duplicates
    return {
        "case_id": call.case_id,
        "pass_number": call.pass_number,
        "persisted_error_code": "schema_invalid",
        "json_object": bool(payload),
        "case_id_matches": payload.get("case_id") == call.case_id,
        "candidate_order_matches": payload.get("candidate_order")
        == list(expected_order),
        "decision_row_coverage_matches": decision_ids == list(expected_order),
        "recognized_actions_only": recognized_actions_only,
        "duplicate_role_id_candidate_count": duplicate_candidates,
        "duplicate_role_quote_count": duplicate_quotes,
    }


def _dominant_failure_surface(rows: Sequence[Mapping[str, Any]]) -> str:
    counts = Counter(
        row["failure_class"]
        for row in rows
        if row["direct_relevance"] == "YES"
    )
    if not counts:
        return "not_evaluated"
    maximum = max(counts.values())
    winners = sorted(name for name, count in counts.items() if count == maximum)
    return winners[0] if len(winners) == 1 else "mixed"


def _aggregate_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    class_counts = Counter(row["failure_class"] for row in rows)
    if sum(class_counts.values()) != 64 or set(class_counts) - set(FAILURE_CLASSES):
        raise EvidenceSetFailureDiagnosticError(
            "failure classes do not form one complete 64-row partition"
        )
    by_relevance = {
        relevance: dict(
            sorted(
                Counter(
                    row["failure_class"]
                    for row in rows
                    if row["direct_relevance"] == relevance
                ).items()
            )
        )
        for relevance in ("YES", "NO")
    }
    semantic_rows = [row for row in rows if row["semantic_scope_link"] == "YES"]
    by_case = {
        case_id: dict(
            sorted(
                Counter(
                    row["failure_class"]
                    for row in rows
                    if row["case_id"] == case_id
                ).items()
            )
        )
        for case_id in CASE_IDS
    }
    return {
        "candidate_count": 64,
        "joined_candidate_count": len(rows),
        "direct_relevant_count": sum(
            row["direct_relevance"] == "YES" for row in rows
        ),
        "direct_irrelevant_count": sum(
            row["direct_relevance"] == "NO" for row in rows
        ),
        "human_semantic_link_count": len(semantic_rows),
        "failure_class_counts": dict(sorted(class_counts.items())),
        "failure_class_counts_by_direct_relevance": by_relevance,
        "failure_class_counts_among_human_semantic_links": dict(
            sorted(Counter(row["failure_class"] for row in semantic_rows).items())
        ),
        "failure_class_counts_by_case": by_case,
        "dominant_observed_failure_surface": _dominant_failure_surface(rows),
    }


def build_failure_diagnostic(
    mechanical: MechanicalSnapshot,
    human: HumanSnapshot,
) -> dict[str, Any]:
    """Join labels only after both snapshots have independently passed."""

    mechanical_ids = {
        (case.case_id, candidate.candidate_sha256)
        for case in mechanical.cases
        for candidate in case.candidate_decisions
    }
    if mechanical_ids != set(human.labels):
        raise EvidenceSetFailureDiagnosticError(
            "mechanical and human candidate identities do not form an exact join"
        )
    rows: list[dict[str, Any]] = []
    pass_actions = {
        "pass_1": Counter(valid_candidate_count=0, keep_count=0),
        "pass_2": Counter(valid_candidate_count=0, keep_count=0),
    }
    invalid_shapes: list[dict[str, Any]] = []
    for case in mechanical.cases:
        provider_order = tuple(
            candidate.candidate_sha256
            for candidate in sorted(
                case.candidate_decisions,
                key=lambda item: item.provider_result_index,
            )
        )
        for pass_number, judge_pass in (
            (1, case.first_pass),
            (2, case.second_pass),
        ):
            if judge_pass.state == "valid" and judge_pass.response is not None:
                counter = pass_actions[f"pass_{pass_number}"]
                counter["valid_candidate_count"] += len(judge_pass.response.decisions)
                counter["keep_count"] += sum(
                    decision.action == "KEEP"
                    for decision in judge_pass.response.decisions
                )
            else:
                expected_order = (
                    provider_order if pass_number == 1 else tuple(reversed(provider_order))
                )
                invalid_shapes.append(
                    _shape_probe(
                        mechanical.calls[(case.case_id, pass_number)],
                        expected_order,
                    )
                )
        for candidate in case.candidate_decisions:
            label = human.labels[(case.case_id, candidate.candidate_sha256)]
            failure_class, first_action, second_action = classify_candidate(
                case, candidate
            )
            rows.append(
                {
                    "case_id": case.case_id,
                    "provider_result_index": candidate.provider_result_index,
                    "candidate_sha256": candidate.candidate_sha256,
                    "direct_relevance": label.direct_relevance,
                    "semantic_scope_link": label.semantic_scope_link,
                    "baseline_novelty": label.baseline_novelty,
                    "abstract_sufficient": label.abstract_sufficient,
                    "failure_class": failure_class,
                    "first_pass_state": case.first_pass.state,
                    "second_pass_state": case.second_pass.state,
                    "first_action": first_action,
                    "second_action": second_action,
                    "final_action": candidate.action,
                    "final_abstention_reasons": list(candidate.abstention_reasons),
                }
            )
    rows.sort(key=lambda row: (row["case_id"], row["provider_result_index"]))
    if len(rows) != 64 or len({row["candidate_sha256"] for row in rows}) != 64:
        raise EvidenceSetFailureDiagnosticError(
            "joined row boundary lost or duplicated a candidate"
        )
    metrics = _aggregate_metrics(rows)
    metrics["valid_pass_action_counts"] = {
        name: dict(counter) for name, counter in pass_actions.items()
    }
    return {
        "schema_version": 1,
        "mode": "openalex_evidence_set_v5_qwen_failure_diagnostic",
        "diagnostic_only": True,
        "protocol_status": "complete",
        "production_connected": False,
        "report_workflow_connected": False,
        "planner_trigger_connected": False,
        "x_challenge_opened": False,
        "v5_result_changed": False,
        "executed_revision": EXPECTED_EXECUTED_REVISION,
        "mechanical_source_sha256": dict(mechanical.source_sha256),
        "private_source_sha256": dict(human.source_sha256),
        "review_method": {
            "reviewed_all": human.declaration["reviewed_all"],
            "generative_ai_use": human.declaration["generative_ai_use"],
            "external_sources_checked": human.declaration[
                "external_sources_checked"
            ],
            "reviewer_count": 1,
        },
        "metrics": metrics,
        "invalid_pass_shape_observations": invalid_shapes,
        "rows": rows,
        "measurement_limit": MEASUREMENT_LIMIT,
    }


def public_projection(result: Mapping[str, Any]) -> dict[str, Any]:
    """Drop candidate identities and the private row-level label join."""

    if result.get("protocol_status") != "complete" or len(result.get("rows", ())) != 64:
        raise EvidenceSetFailureDiagnosticError(
            "only a complete 64-row diagnostic can be projected publicly"
        )
    return {
        key: value
        for key, value in result.items()
        if key
        not in {
            "rows",
            "private_source_sha256",
            "review_method",
        }
    }


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _stdout_json(value: object) -> None:
    text = _json_text(value)
    stream = getattr(sys.stdout, "buffer", None)
    if stream is None:
        sys.stdout.write(text)
        return
    stream.write(text.encode("utf-8"))
    stream.flush()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mechanical-dir", type=Path, required=True)
    parser.add_argument("--source-lock", type=Path, required=True)
    parser.add_argument("--packet-manifest", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--reviewer-declaration", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument(
        "--acknowledge-post-outcome-diagnostic",
        action="store_true",
        help="Confirm that this cannot rescue v5 or authorize X01-X08.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not args.acknowledge_post_outcome_diagnostic:
        raise EvidenceSetFailureDiagnosticError(
            "post-outcome diagnostic acknowledgement is required"
        )
    mechanical = load_mechanical_snapshot(args.mechanical_dir)
    human = load_human_snapshot(
        source_lock_path=args.source_lock,
        packet_manifest_path=args.packet_manifest,
        labels_path=args.labels,
        declaration_path=args.reviewer_declaration,
    )
    result = build_failure_diagnostic(mechanical, human)
    # The private artifact commits first. A crash before the public projection
    # cannot leave a reassuring aggregate without the underlying joined rows.
    _write_text_new(args.private_output, _json_text(result))
    projection = public_projection(result)
    _write_text_new(args.public_output, _json_text(projection))
    _stdout_json(projection)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
