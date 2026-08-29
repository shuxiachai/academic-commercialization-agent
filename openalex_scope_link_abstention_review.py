"""Diagnose the frozen scope-link v4 abstentions without changing their result.

The W01-W08 live study failed before its registered source-value review could
begin.  This module creates a separate, explicitly post-outcome diagnostic over
the title and abstract text already on disk.  Reviewers never see the v4 action,
reasons, match provenance, profile, or provider aboutness.  Those hidden traces
are joined only after labels return, so the packet can distinguish retrieval
noise from semantic relationships missed by the exact same-segment rule.

This is deliberately a root-level experimental utility.  It opens no socket,
invokes no model, registers no evidence, and is never imported by the
production report worker.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evidence_gap_phase4_review import (
    DECLARATION_FIELDS,
    ELIGIBLE_AI_USE,
    Phase4ReviewError as ScopeLinkDiagnosticError,
    _file_sha256,
    _read_csv,
    _read_json_object,
    _validated_declaration,
    _write_csv_new,
    _write_text_new,
)
from openalex_scope_link_live import (
    EXPECTED_IMPLEMENTATION_SHA256,
    ScopeLinkCaseExecution,
    ScopeLinkExecutionArtifact,
    ScopeLinkManifestArtifact,
    _AGGREGATE_SOURCE_FILES,
    _CANDIDATE_COLUMNS,
    _REVIEW_COLUMNS,
    _candidate_rows,
)
from openalex_scope_link_unseen import EXPECTED_FIXTURE_SHA256


EXPECTED_EXECUTED_REVISION = "678254d66c599402811d04f9b2b91ff6977ac089"
EXPECTED_SOURCE_FILE_SHA256 = {
    "manifest.json": (
        "3ea66fdb806efe049cba09b582a8dd99daf5a500c584dbce401b22d413ea630b"
    ),
    "execution.json": (
        "aff3b692783c695647dede20b5aafbb9a6a5b96baf58b205349ca0cb691eff87"
    ),
    "candidates.csv": (
        "7e3ae36d1efb02132de241d47bd685117ae4c1c5478d25adeaeeb88498bbcaf3"
    ),
    "review.csv": (
        "6c89b81c657dc0cfd3c3853c738d132e244f91a54f0ec67aa61853ea08243148"
    ),
    "artifact-index.json": (
        "2bc4cd8a7d6719c3799521ea0866530be0331bfb233a6af61c261ef69d67c445"
    ),
    "case-executions/W01.json": (
        "27eac645e068eb064b1fa3e2d775996d707d0830b2e1437ab3ccd369eb14f411"
    ),
    "case-executions/W02.json": (
        "6576026b30a12e2c93e9c893b322e7bdd0b0ae7a8d96c00bbb3d8a7680bb085c"
    ),
    "case-executions/W03.json": (
        "042f6047ed075c5b76a7d4d75aaba1a65ca08f4a15385391e24c83e620f284a5"
    ),
    "case-executions/W04.json": (
        "d230e72c3017ca9781e73e658a4e90160ce182786a7dae0d7c17379e0272ab95"
    ),
    "case-executions/W05.json": (
        "e72d37f606be6b150aca371546deb64767d4027617717ccb46782b418bc9fa9d"
    ),
    "case-executions/W06.json": (
        "3c6e6ff6a799bd25039d46dd5c2d2e1e5fa8709138e1e3b61e974b4baa08f913"
    ),
    "case-executions/W07.json": (
        "41705e6da987a8d040e03ec4aa28703c3f7e1483f38476bb1d8da605089e3509"
    ),
    "case-executions/W08.json": (
        "f34ec5f2f72956e34ae4d0e2e74f76eacaa9902b1e6731fd77efecb3f4c71e1b"
    ),
}
CASE_IDS = tuple(f"W{index:02d}" for index in range(1, 9))
SOURCE_FILES = (
    *_AGGREGATE_SOURCE_FILES,
    "artifact-index.json",
    *(f"case-executions/{case_id}.json" for case_id in CASE_IDS),
)
EXPECTED_ABSTAINED_PER_CASE = {case_id: 8 for case_id in CASE_IDS}
EXPECTED_CANDIDATE_COUNT = 64
EXPECTED_MISSING_SCOPE_LINK_COUNT = 63

# The long immutable context columns are intentional.  A separate context file
# is easier to read but creates a second join that a reviewer can accidentally
# break.  Keeping context and labels on one row makes the returned boundary
# self-contained while the candidate SHA still binds the original provider
# object byte-for-byte.
CONTEXT_FIELDS = (
    "case_id",
    "provider",
    "provider_result_index",
    "candidate_sha256",
    "topic",
    "query",
    "declared_gap",
    "baseline_sources_json",
    "title",
    "url",
    "publisher",
    "published_date",
    "doi",
    "evidence_summary",
    "summary_source",
)
LABEL_VALUE_FIELDS = (
    "direct_relevance",
    "semantic_scope_link",
    "baseline_novelty",
    "abstract_sufficient",
    "review_note",
)
LABEL_FIELDS = (*CONTEXT_FIELDS, *LABEL_VALUE_FIELDS)
VALID_LABEL_COMBINATIONS = {
    ("YES", semantic_link, novelty, "YES")
    for semantic_link in ("YES", "NO")
    for novelty in ("YES", "NO")
} | {
    ("NO", "N/A", "N/A", "YES"),
    ("UNVERIFIABLE", "UNVERIFIABLE", "UNVERIFIABLE", "NO"),
}
MEASUREMENT_LIMIT = (
    "This post-outcome diagnostic measures human interpretation of the frozen "
    "title and abstract text for all 64 W01-W08 candidates. It cannot change "
    "the failed v4 result, establish source truth, validate v5, or authorize "
    "production Tool Calling."
)
_FORBIDDEN_REVIEWER_KEYS = {
    "scope_link_action",
    "abstention_reasons",
    "missing_required_groups",
    "exact_required_groups",
    "provider_only_required_groups",
    "exact_scope_groups",
    "linked_scope_groups",
    "title_anchor_groups",
    "required_match_provenance",
    "scope_match_provenance",
    "supporting_match_provenance",
    "link_evidence",
    "aboutness",
    "claim_scope_profile",
}


class ScopeLinkAbstentionDiagnosticLock(BaseModel):
    """Owner attestation over the exact mechanical-failure execution bytes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["openalex_scope_link_v4_abstention_diagnostic_lock"] = (
        "openalex_scope_link_v4_abstention_diagnostic_lock"
    )
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    diagnostic_only: Literal[True] = True
    original_source_value_state: Literal["not_evaluated"] = "not_evaluated"
    authorized_output: Literal[True] = True
    executed_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_sha256: dict[str, str]
    source_file_sha256: dict[str, str]
    study_owner_id: str = Field(min_length=2, max_length=200)
    authorized_at: datetime
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _validate_frozen_identity(self) -> "ScopeLinkAbstentionDiagnosticLock":
        # Exact-map equality alone does not prove that a manually transcribed
        # digest is a complete SHA-256 value: the expected map can contain the
        # same truncated value. Validate the representation independently so a
        # prose-to-code transcription error fails before a packet is emitted.
        if any(
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in self.source_file_sha256.values()
        ):
            raise ValueError(
                "diagnostic lock source hashes must be complete lowercase SHA-256 values"
            )
        if self.executed_revision != EXPECTED_EXECUTED_REVISION:
            raise ValueError("diagnostic lock executed revision does not match")
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("diagnostic lock fixture identity does not match")
        if self.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
            raise ValueError("diagnostic lock implementation identities do not match")
        if self.source_file_sha256 != EXPECTED_SOURCE_FILE_SHA256:
            raise ValueError("diagnostic lock does not identify the frozen v4 run")
        if self.authorized_at.tzinfo is None:
            raise ValueError("diagnostic lock timestamp must be timezone-aware")
        return self


@dataclass(frozen=True)
class ScopeLinkDiagnosticCandidate:
    """One reviewer-visible row with no automated decision information."""

    case_id: str
    provider: str
    provider_result_index: int
    candidate_sha256: str
    topic: str
    query: str
    declared_gap: str
    baseline_sources_json: str
    title: str
    url: str
    publisher: str
    published_date: str
    doi: str
    evidence_summary: str
    summary_source: str

    @property
    def key(self) -> tuple[str, int, str]:
        return (
            self.case_id,
            self.provider_result_index,
            self.candidate_sha256,
        )

    @property
    def row_id(self) -> str:
        return (
            f"{self.case_id}/{self.provider_result_index}/"
            f"{self.candidate_sha256[:12]}"
        )

    @property
    def identity_sha256(self) -> str:
        rendered = json.dumps(
            asdict(self),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(rendered).hexdigest()


@dataclass(frozen=True)
class ScopeLinkDiagnosticSnapshot:
    """Validated bytes shared unchanged by lock, packet, and summary seams."""

    file_hashes: dict[str, str]
    manifest: ScopeLinkManifestArtifact
    execution: ScopeLinkExecutionArtifact
    candidates: tuple[ScopeLinkDiagnosticCandidate, ...]
    hidden_traces: dict[tuple[str, int, str], dict[str, Any]]


def _candidate_from_mapping(
    row: Mapping[str, Any],
) -> ScopeLinkDiagnosticCandidate:
    try:
        provider_result_index = int(str(row.get("provider_result_index", "")))
    except ValueError as exc:
        raise ScopeLinkDiagnosticError(
            "provider_result_index must be an integer"
        ) from exc
    values = {
        field: str(row.get(field, ""))
        for field in CONTEXT_FIELDS
        if field != "provider_result_index"
    }
    candidate = ScopeLinkDiagnosticCandidate(
        provider_result_index=provider_result_index,
        **values,
    )
    if candidate.case_id not in CASE_IDS or candidate.provider != "openalex":
        raise ScopeLinkDiagnosticError(
            f"unexpected diagnostic identity: {candidate.case_id}/{candidate.provider}"
        )
    if not 0 <= candidate.provider_result_index <= 7:
        raise ScopeLinkDiagnosticError(
            f"{candidate.case_id}: provider index is outside the frozen page"
        )
    if (
        len(candidate.candidate_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in candidate.candidate_sha256
        )
    ):
        raise ScopeLinkDiagnosticError(
            f"{candidate.case_id}: candidate SHA-256 is invalid"
        )
    required_text = (
        candidate.topic,
        candidate.query,
        candidate.declared_gap,
        candidate.baseline_sources_json,
        candidate.title,
        candidate.url,
        candidate.publisher,
        candidate.evidence_summary,
        candidate.summary_source,
    )
    if not all(required_text):
        raise ScopeLinkDiagnosticError(
            f"{candidate.case_id}: reviewer context is incomplete"
        )
    if not candidate.url.startswith("https://openalex.org/W"):
        raise ScopeLinkDiagnosticError(
            f"{candidate.case_id}: candidate URL is not an OpenAlex work"
        )
    try:
        baseline_sources = json.loads(candidate.baseline_sources_json)
    except json.JSONDecodeError as exc:
        raise ScopeLinkDiagnosticError(
            f"{candidate.case_id}: baseline source context is invalid JSON"
        ) from exc
    if not isinstance(baseline_sources, list) or not baseline_sources:
        raise ScopeLinkDiagnosticError(
            f"{candidate.case_id}: baseline source context is empty"
        )
    return candidate


def _validate_artifact_index(
    source_dir: Path,
    file_hashes: Mapping[str, str],
) -> None:
    index = _read_json_object(source_dir / "artifact-index.json")
    expected = {
        "schema_version": 1,
        "mode": "openalex_scope_link_v4_artifact_index",
        "production_connected": False,
        "report_workflow_connected": False,
        "source_file_sha256": {
            name: file_hashes[name] for name in _AGGREGATE_SOURCE_FILES
        },
    }
    if index != expected:
        raise ScopeLinkDiagnosticError(
            "artifact index does not match aggregate scope-link bytes"
        )


def _validate_complete_mechanical_failure(
    manifest: ScopeLinkManifestArtifact,
    execution: ScopeLinkExecutionArtifact,
) -> None:
    if execution.overall_state != "completed":
        raise ScopeLinkDiagnosticError(
            "only the completed W01-W08 execution may be diagnosed"
        )
    if (
        execution.request_count != 8
        or execution.attempted_case_count != 8
        or execution.successful_case_count != 8
    ):
        raise ScopeLinkDiagnosticError(
            "diagnostic source must contain eight successful requests"
        )
    if (
        execution.provider_summary.stopped_reason != "completed"
        or execution.provider_summary.cost_state != "known"
    ):
        raise ScopeLinkDiagnosticError(
            "provider completion or cost is not inspectable"
        )
    if (
        execution.review_packet_eligibility != "mechanical_gate_failed"
        or execution.scope_link_accepted_candidate_count != 0
        or execution.scope_link_abstained_candidate_count
        != EXPECTED_CANDIDATE_COUNT
        or execution.scope_link_accepted_case_count != 0
        or execution.source_value_state != "not_evaluated"
    ):
        raise ScopeLinkDiagnosticError(
            "source is not the frozen 64-row mechanical coverage failure"
        )
    if (
        manifest.fixture_sha256 != execution.fixture_sha256
        or manifest.implementation_sha256 != execution.implementation_sha256
        or manifest.runner_sha256 != execution.runner_sha256
        or manifest.soft_stop_usd != execution.soft_stop_usd
        or manifest.source_value_gates != execution.source_value_gates
    ):
        raise ScopeLinkDiagnosticError(
            "execution identity does not join the persisted manifest"
        )

    expected_cases = {
        case.spec.case_id: (
            case.collection_sha256,
            case.plan_sha256,
            case.profile_sha256,
            case.validated_plan.calls[0].idempotency_key,
        )
        for case in manifest.cases
    }
    observed_cases = {
        case.case_id: (
            case.collection_sha256,
            case.plan_sha256,
            case.profile_sha256,
            case.idempotency_key,
        )
        for case in execution.cases
    }
    if observed_cases != expected_cases:
        raise ScopeLinkDiagnosticError(
            "case executions do not join the frozen manifest"
        )

    abstained_per_case: dict[str, int] = {}
    missing_scope_link_count = 0
    costs: list[float] = []
    for case in execution.cases:
        if case.state != "completed" or case.response is None:
            raise ScopeLinkDiagnosticError(
                f"{case.case_id}: case is not a completed provider observation"
            )
        usage = case.response.provider_usage
        if (
            case.response.outbound_request_count != 1
            or usage.cost_basis != "reported_usd"
            or usage.reported_cost_usd is None
            or case.search_cost_usd is None
            or usage.reported_cost_usd != case.search_cost_usd
        ):
            raise ScopeLinkDiagnosticError(
                f"{case.case_id}: request or cost accounting is invalid"
            )
        if len(case.response.candidates) != 8 or case.response.provider_rejections:
            raise ScopeLinkDiagnosticError(
                f"{case.case_id}: provider row denominator is not the frozen page"
            )
        if usage.result_count != 8 or len(case.evaluations) != 8:
            raise ScopeLinkDiagnosticError(
                f"{case.case_id}: candidate accounting is incomplete"
            )
        if any(item.decision.action != "ABSTAIN" for item in case.evaluations):
            raise ScopeLinkDiagnosticError(
                f"{case.case_id}: diagnostic source contains an accepted candidate"
            )
        if any(
            item.candidate.evidence.summary_source != "abstract"
            for item in case.evaluations
        ):
            raise ScopeLinkDiagnosticError(
                f"{case.case_id}: frozen-text diagnostic requires abstracts"
            )
        abstained_per_case[case.case_id] = len(case.evaluations)
        missing_scope_link_count += sum(
            "missing_scope_link" in item.decision.abstention_reasons
            for item in case.evaluations
        )
        costs.append(case.search_cost_usd)
    if abstained_per_case != EXPECTED_ABSTAINED_PER_CASE:
        raise ScopeLinkDiagnosticError(
            "abstained candidate distribution does not match the frozen run"
        )
    if missing_scope_link_count != EXPECTED_MISSING_SCOPE_LINK_COUNT:
        raise ScopeLinkDiagnosticError(
            "missing-scope-link denominator does not match the frozen run"
        )
    reported = execution.provider_summary.reported_cost_usd
    if reported is None or abs(reported - sum(costs)) > 1e-12:
        raise ScopeLinkDiagnosticError(
            "provider summary cost does not equal the case journals"
        )


def _validate_case_journals(
    source_dir: Path,
    execution: ScopeLinkExecutionArtifact,
) -> None:
    journal_dir = source_dir / "case-executions"
    if not journal_dir.is_dir():
        raise ScopeLinkDiagnosticError("case-executions directory is missing")
    observed_names = {path.name for path in journal_dir.glob("*.json")}
    expected_names = {f"{case_id}.json" for case_id in CASE_IDS}
    if observed_names != expected_names:
        raise ScopeLinkDiagnosticError(
            "case journals do not cover W01-W08 exactly"
        )
    execution_by_id = {case.case_id: case for case in execution.cases}
    for case_id in CASE_IDS:
        journal = ScopeLinkCaseExecution.model_validate(
            _read_json_object(journal_dir / f"{case_id}.json")
        )
        if journal != execution_by_id[case_id]:
            raise ScopeLinkDiagnosticError(
                f"{case_id}: case journal does not match aggregate execution"
            )


def _baseline_sources_json(case: Any) -> str:
    sources: list[dict[str, str]] = []
    for domain in ("academic", "patent", "market"):
        for source in getattr(case.source_collection, f"{domain}_sources"):
            projection = {
                "domain": domain,
                "source_id": source.source_id,
                "title": source.title,
                "url": str(source.url),
                "evidence_summary": source.evidence_summary,
            }
            if not all(projection.values()):
                raise ScopeLinkDiagnosticError(
                    f"{case.spec.case_id}: baseline source context is incomplete"
                )
            sources.append(projection)
    if not sources:
        raise ScopeLinkDiagnosticError(
            f"{case.spec.case_id}: baseline source context is empty"
        )
    return json.dumps(
        sources,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _project_candidates(
    manifest: ScopeLinkManifestArtifact,
    execution: ScopeLinkExecutionArtifact,
) -> tuple[
    tuple[ScopeLinkDiagnosticCandidate, ...],
    dict[tuple[str, int, str], dict[str, Any]],
]:
    manifest_by_id = {case.spec.case_id: case for case in manifest.cases}
    candidates: list[ScopeLinkDiagnosticCandidate] = []
    traces: dict[tuple[str, int, str], dict[str, Any]] = {}
    for case in execution.cases:
        frozen = manifest_by_id[case.case_id]
        failure_reason = frozen.source_collection.failed_domains.get("academic")
        if not failure_reason:
            raise ScopeLinkDiagnosticError(
                f"{case.case_id}: baseline academic gap state is missing"
            )
        baseline_json = _baseline_sources_json(frozen)
        for item in case.evaluations:
            evidence = item.candidate.evidence
            candidate = ScopeLinkDiagnosticCandidate(
                case_id=case.case_id,
                provider="openalex",
                provider_result_index=item.provider_result_index,
                candidate_sha256=item.decision.candidate_sha256,
                topic=frozen.spec.topic,
                query=frozen.spec.query,
                declared_gap=f"academic retrieval failed: {failure_reason.strip()}",
                baseline_sources_json=baseline_json,
                title=evidence.title,
                url=str(evidence.url),
                publisher=evidence.publisher,
                published_date=(
                    evidence.published_date.isoformat()
                    if evidence.published_date is not None
                    else ""
                ),
                doi=evidence.doi or "",
                evidence_summary=evidence.evidence_summary,
                summary_source=evidence.summary_source,
            )
            if candidate.key in traces:
                raise ScopeLinkDiagnosticError(
                    f"duplicate candidate identity: {candidate.row_id}"
                )
            candidates.append(candidate)
            traces[candidate.key] = {
                "action": item.decision.action,
                "abstention_reasons": list(item.decision.abstention_reasons),
            }
    if len(candidates) != EXPECTED_CANDIDATE_COUNT:
        raise ScopeLinkDiagnosticError(
            "reviewer projection does not contain all 64 candidates"
        )
    return tuple(candidates), traces


def validate_finalized_source(
    source_dir: Path,
    *,
    expected_hashes: Mapping[str, str] | None = None,
) -> ScopeLinkDiagnosticSnapshot:
    """Validate every persisted byte and project a decision-blind population."""

    if not source_dir.is_dir():
        raise ScopeLinkDiagnosticError(
            f"source directory does not exist: {source_dir}"
        )
    file_hashes = {name: _file_sha256(source_dir / name) for name in SOURCE_FILES}
    if expected_hashes is not None:
        expected = dict(expected_hashes)
        if set(expected) != set(SOURCE_FILES):
            raise ScopeLinkDiagnosticError(
                "expected hashes must identify every v4 diagnostic source file"
            )
        if file_hashes != expected:
            drift = {
                name: {"expected": expected[name], "observed": file_hashes[name]}
                for name in SOURCE_FILES
                if file_hashes[name] != expected[name]
            }
            raise ScopeLinkDiagnosticError(
                f"source artifact identity drifted after locking: {drift}"
            )
    _validate_artifact_index(source_dir, file_hashes)

    manifest = ScopeLinkManifestArtifact.model_validate(
        _read_json_object(source_dir / "manifest.json")
    )
    execution = ScopeLinkExecutionArtifact.model_validate(
        _read_json_object(source_dir / "execution.json")
    )
    _validate_complete_mechanical_failure(manifest, execution)
    _validate_case_journals(source_dir, execution)

    candidate_rows = _read_csv(source_dir / "candidates.csv", _CANDIDATE_COLUMNS)
    review_rows = _read_csv(source_dir / "review.csv", _REVIEW_COLUMNS)
    expected_candidates, expected_reviews = _candidate_rows(execution.cases)
    if candidate_rows != expected_candidates:
        raise ScopeLinkDiagnosticError(
            "candidate CSV does not contain every v4 disposition exactly once"
        )
    if review_rows != expected_reviews or review_rows:
        raise ScopeLinkDiagnosticError(
            "the mechanical-failure review boundary must remain header-only"
        )

    candidates, traces = _project_candidates(manifest, execution)
    return ScopeLinkDiagnosticSnapshot(
        file_hashes=file_hashes,
        manifest=manifest,
        execution=execution,
        candidates=candidates,
        hidden_traces=traces,
    )


def create_source_lock(
    source_dir: Path,
    output_path: Path,
    *,
    study_owner_id: str,
    confirm_authorized_output: bool,
    note: str | None = None,
    authorized_at: datetime | None = None,
) -> ScopeLinkAbstentionDiagnosticLock:
    """Bind the exact failed execution before a reviewer packet exists."""

    if not confirm_authorized_output:
        raise ScopeLinkDiagnosticError(
            "diagnostic locking requires authorized-output confirmation"
        )
    if output_path.exists():
        raise ScopeLinkDiagnosticError(
            f"refusing to overwrite diagnostic lock: {output_path}"
        )
    snapshot = validate_finalized_source(source_dir)
    lock = ScopeLinkAbstentionDiagnosticLock(
        executed_revision=EXPECTED_EXECUTED_REVISION,
        fixture_sha256=EXPECTED_FIXTURE_SHA256,
        implementation_sha256=EXPECTED_IMPLEMENTATION_SHA256,
        source_file_sha256=snapshot.file_hashes,
        study_owner_id=study_owner_id.strip(),
        authorized_at=authorized_at or datetime.now(UTC),
        note=note.strip() if note and note.strip() else None,
    )
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ScopeLinkDiagnosticError(
            f"could not create diagnostic-lock parent {output_path.parent}: {exc}"
        ) from exc
    _write_text_new(
        output_path,
        json.dumps(
            lock.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return lock


def _load_source_lock(path: Path) -> ScopeLinkAbstentionDiagnosticLock:
    try:
        return ScopeLinkAbstentionDiagnosticLock.model_validate(
            _read_json_object(path)
        )
    except ValueError as exc:
        if isinstance(exc, ScopeLinkDiagnosticError):
            raise
        raise ScopeLinkDiagnosticError(
            f"diagnostic source lock is invalid: {exc}"
        ) from exc


def _packet_rows(
    snapshot: ScopeLinkDiagnosticSnapshot,
) -> list[dict[str, Any]]:
    rows = [
        {**asdict(candidate), "identity_sha256": candidate.identity_sha256}
        for candidate in snapshot.candidates
    ]
    leaked = sorted(
        _FORBIDDEN_REVIEWER_KEYS.intersection(
            key for row in rows for key in row
        )
    )
    if leaked:
        raise ScopeLinkDiagnosticError(
            f"reviewer packet leaks automated decision fields: {leaked}"
        )
    return rows


def _packet_manifest(
    snapshot: ScopeLinkDiagnosticSnapshot,
    source_lock_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": "openalex_scope_link_v4_candidate_diagnostic_packet",
        "prepared_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "production_connected": False,
        "report_workflow_connected": False,
        "diagnostic_only": True,
        "executed_revision": EXPECTED_EXECUTED_REVISION,
        "source_lock_sha256": _file_sha256(source_lock_path),
        "source_file_sha256": snapshot.file_hashes,
        "row_count": len(snapshot.candidates),
        "case_count": len(CASE_IDS),
        "rows": _packet_rows(snapshot),
        "valid_label_combinations": [
            list(values) for values in sorted(VALID_LABEL_COMBINATIONS)
        ],
        "measurement_limit": MEASUREMENT_LIMIT,
    }


def _packet_readme(snapshot: ScopeLinkDiagnosticSnapshot) -> str:
    counts = Counter(candidate.case_id for candidate in snapshot.candidates)
    cases = "\n".join(
        f"| {case_id} | {counts[case_id]} |" for case_id in CASE_IDS
    )
    return f"""# OpenAlex frozen candidate diagnostic

This packet contains {len(snapshot.candidates)} title-and-abstract rows from one
completed, production-disconnected OpenAlex execution. Preparing and
summarizing the packet makes zero API or LLM calls.

Do not edit `packet_manifest.json`. Complete only `labels.csv` and
`reviewer_declaration.csv`. Rows may be reordered, but every context and
identity field must remain byte-for-byte unchanged. Do not inspect the source
execution, implementation, automated decisions, or separate source-lock file
until after returning the labels. The packet deliberately hides those values.

| Case | Candidate rows |
|---|---:|
{cases}

Judge each candidate from its frozen topic, query, baseline context, title and
abstract. `direct_relevance=YES` means the candidate directly addresses the
declared topic rather than sharing a broad field. `semantic_scope_link=YES`
means the required technology and scope are meaningfully related in the title
or abstract, even when exact wording differs. `baseline_novelty=YES` means the
candidate adds material evidence absent from `baseline_sources_json`.

Use only one of these combinations:

- `YES / YES-or-NO / YES-or-NO / YES`;
- `NO / N/A / N/A / YES`; or
- `UNVERIFIABLE / UNVERIFIABLE / UNVERIFIABLE / NO`.

Every row requires a source-grounded `review_note`. External URLs are optional
because this diagnostic concerns the exact frozen text seen by the method, but
record how many you attempted in `reviewer_declaration.csv`. `NONE` or
`LANGUAGE_ONLY` generative-AI use is eligible; substantive generated judgments
are retained but not evaluated.

This is a post-outcome diagnostic, not a source-value rerun. It cannot change
the original study, validate a later method, or authorize production Tool
Calling.
"""


def prepare_packet(
    source_dir: Path,
    source_lock_path: Path,
    packet_dir: Path,
) -> dict[str, Any]:
    """Create a separate label-blind packet from the locked exact bytes."""

    if packet_dir.exists():
        raise ScopeLinkDiagnosticError(
            f"refusing to overwrite diagnostic packet: {packet_dir}"
        )
    source_lock = _load_source_lock(source_lock_path)
    snapshot = validate_finalized_source(
        source_dir,
        expected_hashes=source_lock.source_file_sha256,
    )
    try:
        packet_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise ScopeLinkDiagnosticError(
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
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return manifest


def _manifest_candidates(
    manifest: dict[str, Any],
    snapshot: ScopeLinkDiagnosticSnapshot,
    source_lock_path: Path,
) -> dict[tuple[str, int, str], ScopeLinkDiagnosticCandidate]:
    expected_header = {
        "schema_version": 1,
        "mode": "openalex_scope_link_v4_candidate_diagnostic_packet",
        "production_connected": False,
        "report_workflow_connected": False,
        "diagnostic_only": True,
        "executed_revision": EXPECTED_EXECUTED_REVISION,
        "source_lock_sha256": _file_sha256(source_lock_path),
        "source_file_sha256": snapshot.file_hashes,
        "row_count": EXPECTED_CANDIDATE_COUNT,
        "case_count": len(CASE_IDS),
        "valid_label_combinations": [
            list(values) for values in sorted(VALID_LABEL_COMBINATIONS)
        ],
        "measurement_limit": MEASUREMENT_LIMIT,
    }
    for key, value in expected_header.items():
        if manifest.get(key) != value:
            raise ScopeLinkDiagnosticError(
                f"diagnostic packet {key} drifted from the frozen contract"
            )
    rows = manifest.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_CANDIDATE_COUNT:
        raise ScopeLinkDiagnosticError(
            "diagnostic packet row denominator is not inspectable"
        )
    candidates: dict[tuple[str, int, str], ScopeLinkDiagnosticCandidate] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ScopeLinkDiagnosticError("diagnostic packet rows must be objects")
        leaked = sorted(_FORBIDDEN_REVIEWER_KEYS.intersection(row))
        if leaked:
            raise ScopeLinkDiagnosticError(
                f"diagnostic packet leaks automated decision fields: {leaked}"
            )
        candidate = _candidate_from_mapping(row)
        if row.get("identity_sha256") != candidate.identity_sha256:
            raise ScopeLinkDiagnosticError(
                f"packet identity hash drifted for {candidate.row_id}"
            )
        if candidate.key in candidates:
            raise ScopeLinkDiagnosticError(
                f"packet contains duplicate identity {candidate.row_id}"
            )
        candidates[candidate.key] = candidate
    expected = {candidate.key: candidate for candidate in snapshot.candidates}
    if candidates != expected:
        raise ScopeLinkDiagnosticError(
            "packet candidates do not match the source-locked population"
        )
    return candidates


def _validated_label(
    row: Mapping[str, str],
    expected: ScopeLinkDiagnosticCandidate,
) -> dict[str, str] | None:
    observed = _candidate_from_mapping(row)
    if observed != expected:
        raise ScopeLinkDiagnosticError(
            f"label context or identity drifted for {expected.row_id}"
        )
    values = [row[field].strip() for field in LABEL_VALUE_FIELDS]
    if not any(values):
        return None
    if not all(values):
        raise ScopeLinkDiagnosticError(
            f"{expected.row_id} is partially completed"
        )
    direct, semantic, novelty, sufficient, note = values
    normalized = (
        direct.upper(),
        semantic.upper(),
        novelty.upper(),
        sufficient.upper(),
    )
    if normalized not in VALID_LABEL_COMBINATIONS:
        raise ScopeLinkDiagnosticError(
            f"{expected.row_id} has invalid diagnostic labels: {normalized}"
        )
    if len("".join(note.split())) < 12:
        raise ScopeLinkDiagnosticError(
            f"{expected.row_id} review_note is too short to ground the judgment"
        )
    return {
        "case_id": expected.case_id,
        "provider_result_index": str(expected.provider_result_index),
        "candidate_sha256": expected.candidate_sha256,
        "row_id": expected.row_id,
        "direct_relevance": normalized[0],
        "semantic_scope_link": normalized[1],
        "baseline_novelty": normalized[2],
        "abstract_sufficient": normalized[3],
        "review_note": note,
    }


def _diagnostic_metrics(
    snapshot: ScopeLinkDiagnosticSnapshot,
    labels: list[dict[str, str]],
) -> dict[str, Any]:
    label_by_key = {
        (
            row["case_id"],
            int(row["provider_result_index"]),
            row["candidate_sha256"],
        ): row
        for row in labels
    }
    direct_counts: Counter[str] = Counter()
    attribution_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    relevant_cases: set[str] = set()
    novel_relevant_cases: set[str] = set()
    semantic_link_count = 0
    semantic_link_miss_count = 0
    by_case: dict[str, Counter[str]] = {
        case_id: Counter() for case_id in CASE_IDS
    }

    for key, trace in snapshot.hidden_traces.items():
        label = label_by_key[key]
        direct = label["direct_relevance"]
        semantic = label["semantic_scope_link"]
        direct_counts[direct] += 1
        by_case[key[0]][f"direct_{direct.casefold()}"] += 1
        for reason in trace["abstention_reasons"]:
            reason_counts[reason] += 1

        if direct == "UNVERIFIABLE":
            attribution = "frozen_text_insufficient"
        elif direct == "NO":
            attribution = "retrieval_noise"
        else:
            relevant_cases.add(key[0])
            if label["baseline_novelty"] == "YES":
                novel_relevant_cases.add(key[0])
            if semantic == "YES":
                semantic_link_count += 1
            if (
                semantic == "YES"
                and "missing_scope_link" in trace["abstention_reasons"]
            ):
                semantic_link_miss_count += 1
                attribution = "semantic_relation_missed_by_v4"
            else:
                attribution = "other_gate_rejection_of_relevant_source"
        attribution_counts[attribution] += 1
        by_case[key[0]][attribution] += 1

    inspectable_count = EXPECTED_CANDIDATE_COUNT - direct_counts["UNVERIFIABLE"]
    retrieval_noise_rate = (
        direct_counts["NO"] / inspectable_count if inspectable_count else None
    )
    semantic_link_miss_rate = (
        semantic_link_miss_count / semantic_link_count
        if semantic_link_count
        else None
    )
    return {
        "candidate_count": EXPECTED_CANDIDATE_COUNT,
        "inspectable_candidate_count": inspectable_count,
        "direct_relevant_count": direct_counts["YES"],
        "direct_irrelevant_count": direct_counts["NO"],
        "unverifiable_count": direct_counts["UNVERIFIABLE"],
        "relevant_case_ids": sorted(relevant_cases),
        "relevant_case_count": len(relevant_cases),
        "novel_relevant_case_ids": sorted(novel_relevant_cases),
        "novel_relevant_case_count": len(novel_relevant_cases),
        "human_semantic_link_count": semantic_link_count,
        "semantic_link_miss_count": semantic_link_miss_count,
        "semantic_link_miss_rate_among_human_links": semantic_link_miss_rate,
        "retrieval_noise_rate_among_inspectable": retrieval_noise_rate,
        "frozen_text_insufficiency_rate": (
            direct_counts["UNVERIFIABLE"] / EXPECTED_CANDIDATE_COUNT
        ),
        "attribution_counts": dict(sorted(attribution_counts.items())),
        "v4_reason_counts": dict(sorted(reason_counts.items())),
        "by_case": {
            case_id: dict(sorted(counts.items()))
            for case_id, counts in by_case.items()
        },
    }


def summarize_packet(
    source_dir: Path,
    source_lock_path: Path,
    packet_dir: Path,
) -> dict[str, Any]:
    """Validate returned labels and join hidden v4 traces only at this seam."""

    if not packet_dir.is_dir():
        raise ScopeLinkDiagnosticError(
            f"diagnostic packet directory does not exist: {packet_dir}"
        )
    source_lock = _load_source_lock(source_lock_path)
    snapshot = validate_finalized_source(
        source_dir,
        expected_hashes=source_lock.source_file_sha256,
    )
    manifest = _read_json_object(packet_dir / "packet_manifest.json")
    expected_candidates = _manifest_candidates(
        manifest,
        snapshot,
        source_lock_path,
    )

    label_rows = _read_csv(packet_dir / "labels.csv", LABEL_FIELDS)
    observed_keys = [
        _candidate_from_mapping(row).key for row in label_rows
    ]
    if len(observed_keys) != len(set(observed_keys)):
        raise ScopeLinkDiagnosticError(
            "diagnostic labels contain duplicate candidate identities"
        )
    if set(observed_keys) != set(expected_candidates):
        missing = sorted(set(expected_candidates) - set(observed_keys))
        extra = sorted(set(observed_keys) - set(expected_candidates))
        raise ScopeLinkDiagnosticError(
            f"diagnostic label identities drifted; missing={missing}, extra={extra}"
        )

    completed: dict[tuple[str, int, str], dict[str, str]] = {}
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
        raise ScopeLinkDiagnosticError(
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

    ordered_labels = [completed[key] for key in sorted(completed)]
    metrics = (
        _diagnostic_metrics(snapshot, ordered_labels)
        if protocol_status == "complete"
        else None
    )
    return {
        "schema_version": 1,
        "mode": "openalex_scope_link_v4_abstention_diagnostic_result",
        "production_connected": False,
        "report_workflow_connected": False,
        "diagnostic_only": True,
        "original_review_packet_eligibility": "mechanical_gate_failed",
        "original_source_value_state": "not_evaluated",
        "v5_validation_authorized": False,
        "executed_revision": EXPECTED_EXECUTED_REVISION,
        "source_lock_sha256": _file_sha256(source_lock_path),
        "source_file_sha256": snapshot.file_hashes,
        "packet_manifest_sha256": _file_sha256(
            packet_dir / "packet_manifest.json"
        ),
        "protocol_status": protocol_status,
        "diagnostic_state": (
            "evaluated" if protocol_status == "complete" else "not_evaluated"
        ),
        "expected_row_count": EXPECTED_CANDIDATE_COUNT,
        "completed_row_count": len(completed),
        "incomplete_row_ids": incomplete_row_ids,
        "method_issues": method_issues,
        "declaration": declaration,
        "metrics": metrics,
        "measurement_limit": MEASUREMENT_LIMIT,
    }


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write_json_stdout(value: object) -> None:
    """Emit UTF-8 even when the Windows text console still advertises GBK."""
    text = _json_text(value)
    stdout_buffer = getattr(sys.stdout, "buffer", None)
    if stdout_buffer is None:
        # StringIO and other test doubles intentionally expose only text I/O.
        sys.stdout.write(text)
        return
    stdout_buffer.write(text.encode("utf-8"))
    stdout_buffer.flush()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lock, prepare, or summarize the zero-network v4 diagnostic."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    lock = commands.add_parser("lock")
    lock.add_argument("--source-dir", type=Path, required=True)
    lock.add_argument("--output", type=Path, required=True)
    lock.add_argument("--study-owner-id", required=True)
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
            study_owner_id=args.study_owner_id,
            confirm_authorized_output=args.confirm_authorized_output,
            note=args.note,
        ).model_dump(mode="json")
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
            _write_text_new(args.output, _json_text(result))
    _write_json_stdout(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
