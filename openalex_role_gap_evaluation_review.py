"""Source-lock and review the frozen adaptive role-gap v8 AD unseen run.

The provider runner deliberately stopped after one mechanically complete,
production-disconnected AD01-AD08 retrieval run.  This module binds those
exact write-once bytes, prepares a route- and lane-blind Schema v2 packet, and
joins hidden adaptive provenance only after every human source label has been
validated.  It opens no socket, invokes no model, does not reopen either the
AC development cohort or AD retrieval, and never authorizes production Tool
Calling.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evidence_gap_phase4_review import (
    DECLARATION_FIELDS,
    ELIGIBLE_AI_USE,
    VALID_LABEL_PAIRS,
    Phase4ReviewError as RoleGapReviewError,
    _file_sha256,
    _read_csv,
    _read_json_object,
    _validated_declaration,
    _write_csv_new,
    _write_text_new,
)
from openalex_role_gap_evaluation import (
    EXPECTED_IMPLEMENTATION_SHA256,
    RoleGapCasePortfolio,
    RoleGapExecutionArtifact,
    RoleGapLaneExecution,
    RoleGapManifestArtifact,
    RoleGapRouteExecution,
    _AGGREGATE_SOURCE_FILES,
    _CANDIDATE_REVIEW_COLUMNS,
    _CASE_REVIEW_COLUMNS,
    _LANE_ORDER,
    _PROVIDER_ROW_COLUMNS,
    _ROUTE_COLUMNS,
    _UNIQUE_CANDIDATE_COLUMNS,
    _provider_rows,
    _route_execution,
    _route_rows,
    _unique_and_review_rows,
    build_case_portfolio,
)
from openalex_role_gap_unseen import EXPECTED_FIXTURE_SHA256


EXPECTED_EXECUTED_REVISION = "b54fa22666805f8d0de0ff7e26c42af88b641615"
EXPECTED_RUNNER_SHA256 = (
    "1f188fbdef225e0f6407b24a2ddbf40b66f5425ff9013021b5e94e0f176ccffa"
)
EXPECTED_ARTIFACT_INDEX_SHA256 = (
    "01b3193d60d7405388b6d624da543131e18e67d13910bdb42f74e42e21af6e8f"
)

CASE_IDS = tuple(f"AD{index:02d}" for index in range(1, 9))
# Unlike the AC development run, the AD abstention is in the middle of the
# cohort. Spell out the seven closures so a convenient CASE_IDS[:-1]
# assumption cannot drop AD08 or invent an AD03 closure while still producing
# plausible totals.
EXPECTED_CLOSURE_CASE_IDS = (
    "AD01",
    "AD02",
    "AD04",
    "AD05",
    "AD06",
    "AD07",
    "AD08",
)
INDEXED_SOURCE_FILES = (
    *_AGGREGATE_SOURCE_FILES,
    *(
        f"lane-executions/{case_id}--{lane_id}.json"
        for case_id in CASE_IDS
        for lane_id in (
            _LANE_ORDER if case_id in EXPECTED_CLOSURE_CASE_IDS else ("anchor_search",)
        )
    ),
    *(f"route-executions/{case_id}.json" for case_id in CASE_IDS),
    *(f"case-portfolios/{case_id}.json" for case_id in CASE_IDS),
)
SOURCE_FILES = (*INDEXED_SOURCE_FILES, "artifact-index.json")

EXPECTED_UNIQUE_PER_CASE = {
    "AD01": 10,
    "AD02": 4,
    "AD03": 5,
    "AD04": 11,
    "AD05": 10,
    "AD06": 9,
    "AD07": 10,
    "AD08": 8,
}
EXPECTED_REQUEST_COUNT = 15
EXPECTED_CLOSURE_REQUEST_COUNT = 7
EXPECTED_PROVIDER_ROW_COUNT = 90
EXPECTED_PROVIDER_CANDIDATE_COUNT = 73
EXPECTED_PROVIDER_REJECTION_COUNT = 17
EXPECTED_REVIEW_ROW_COUNT = 67
EXPECTED_PROVIDER_COST_USD = 0.015

LABEL_FIELDS = (
    "case_id",
    "row_id",
    "unique_candidate_sha256",
    "topic",
    "title",
    "url",
    "normalized_doi",
    "publisher",
    "published_date",
    "evidence_summary",
    "summary_source",
    "citation_count",
    "frozen_baseline_sources",
    "frozen_role_profile",
    "directly_relevant",
    "baseline_novel",
    "supported_role_ids",
    "review_note",
)
READ_ONLY_LABEL_FIELDS = LABEL_FIELDS[:-4]
HIDDEN_REVIEW_FIELDS = (
    "lane_memberships",
    "selected_closure_role_id",
    "occurrence_count",
    "provider_ranks",
    "frozen_route_decision",
    "closure_contributed_selected_role",
    "owner_occurrence_sha256",
    "occurrence_sha256s",
    "candidate_sha256",
    "route_action",
    "route_reason",
    "missing_role_ids",
    "selected_role_id",
    "selected_role_kind",
)
MEASUREMENT_LIMIT = (
    "This source-locked unseen review measures title-and-abstract relevance, "
    "novelty relative to the visible frozen baseline, human-grounded routing, "
    "selected-role closure contribution, and role coverability for one exact "
    "AD01-AD08 run. It does not verify full-text source truth, estimate recall, "
    "establish inter-rater agreement, measure report value or planner-trigger "
    "precision, or authorize production Tool Calling."
)


class RoleGapSourceLock(BaseModel):
    """Study-owner attestation over the exact AD01-AD08 provider bytes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["openalex_adaptive_role_gap_v8_ad_source_artifact_lock"] = (
        "openalex_adaptive_role_gap_v8_ad_source_artifact_lock"
    )
    cohort: Literal["unseen"] = "unseen"
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    planner_trigger_connected: Literal[False] = False
    recovery_connected: Literal[False] = False
    model_call_count: Literal[0] = 0
    api_key_used: Literal[False] = False
    authorized_output: Literal[True] = True
    executed_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_sha256: dict[str, str]
    runner_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_file_sha256: dict[str, str]
    review_row_count: int = Field(gt=0, le=96)
    study_owner_id: str = Field(min_length=2, max_length=200)
    authorized_at: datetime
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _validate_frozen_identity(self) -> "RoleGapSourceLock":
        if self.executed_revision != EXPECTED_EXECUTED_REVISION:
            raise ValueError("source lock executed revision does not match")
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("source lock fixture identity does not match")
        if self.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
            raise ValueError("source lock implementation identities do not match")
        if self.runner_sha256 != EXPECTED_RUNNER_SHA256:
            raise ValueError("source lock runner identity does not match")
        if set(self.source_file_sha256) != set(SOURCE_FILES):
            raise ValueError("source lock must identify every v8 AD source file")
        if self.source_file_sha256.get("artifact-index.json") != (
            EXPECTED_ARTIFACT_INDEX_SHA256
        ):
            raise ValueError("source lock does not identify the frozen v8 AD run")
        if any(
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in self.source_file_sha256.values()
        ):
            raise ValueError("source lock hashes must be lowercase SHA-256 values")
        if self.review_row_count != EXPECTED_REVIEW_ROW_COUNT:
            raise ValueError("source lock review denominator does not match")
        if self.authorized_at.tzinfo is None:
            raise ValueError("source lock timestamp must be timezone-aware")
        return self


@dataclass(frozen=True)
class RoleGapReviewCandidate:
    """One source with reviewer-visible context and hidden adaptive lineage."""

    case_id: str
    unique_candidate_sha256: str
    topic: str
    title: str
    url: str
    normalized_doi: str
    publisher: str
    published_date: str
    evidence_summary: str
    summary_source: str
    citation_count: str
    frozen_baseline_sources: str
    frozen_role_profile: str
    lane_memberships: tuple[str, ...]

    @property
    def row_id(self) -> str:
        return f"{self.case_id}/{self.unique_candidate_sha256[:12]}"

    @property
    def key(self) -> tuple[str, str]:
        return self.case_id, self.unique_candidate_sha256

    @property
    def identity_sha256(self) -> str:
        rendered = json.dumps(
            self.visible_values(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(rendered).hexdigest()

    def visible_values(self) -> dict[str, str]:
        """Return the exact blind projection; route and lanes stay excluded."""

        return {
            "case_id": self.case_id,
            "row_id": self.row_id,
            "unique_candidate_sha256": self.unique_candidate_sha256,
            "topic": self.topic,
            "title": self.title,
            "url": self.url,
            "normalized_doi": self.normalized_doi,
            "publisher": self.publisher,
            "published_date": self.published_date,
            "evidence_summary": self.evidence_summary,
            "summary_source": self.summary_source,
            "citation_count": self.citation_count,
            "frozen_baseline_sources": self.frozen_baseline_sources,
            "frozen_role_profile": self.frozen_role_profile,
        }


@dataclass(frozen=True)
class RoleGapSourceSnapshot:
    """Validated source reused unchanged at lock, packet, and result seams."""

    file_hashes: dict[str, str]
    manifest: RoleGapManifestArtifact
    execution: RoleGapExecutionArtifact
    candidates: tuple[RoleGapReviewCandidate, ...]
    case_contexts: tuple[dict[str, Any], ...]


def _validate_artifact_index(source_dir: Path) -> dict[str, str]:
    """Trust the index only after its exact real-run digest is confirmed."""

    index_path = source_dir / "artifact-index.json"
    if _file_sha256(index_path) != EXPECTED_ARTIFACT_INDEX_SHA256:
        raise RoleGapReviewError("artifact-index identity does not match the v8 AD run")
    index = _read_json_object(index_path)
    expected_envelope = {
        "schema_version": 1,
        "mode": "openalex_adaptive_role_gap_v8_ad_artifact_index",
        "cohort": "unseen",
        "production_connected": False,
        "report_workflow_connected": False,
        "planner_trigger_connected": False,
        "recovery_connected": False,
        "model_call_count": 0,
    }
    if any(index.get(key) != value for key, value in expected_envelope.items()):
        raise RoleGapReviewError("artifact index connection or schema envelope drifted")
    indexed = index.get("source_file_sha256")
    if not isinstance(indexed, dict) or set(indexed) != set(INDEXED_SOURCE_FILES):
        raise RoleGapReviewError("artifact index does not cover the exact v8 AD files")
    if any(
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        for value in indexed.values()
    ):
        raise RoleGapReviewError("artifact index contains a malformed source hash")
    return dict(indexed)


def _validate_complete_execution(
    manifest: RoleGapManifestArtifact,
    execution: RoleGapExecutionArtifact,
) -> None:
    if execution.overall_state != "completed":
        raise RoleGapReviewError("only the completed AD01-AD08 run may be locked")
    if (
        execution.request_count != EXPECTED_REQUEST_COUNT
        or execution.successful_request_count != EXPECTED_REQUEST_COUNT
        or execution.route_decision_count != len(CASE_IDS)
        or execution.closure_request_count != EXPECTED_CLOSURE_REQUEST_COUNT
        or execution.completed_portfolio_count != len(CASE_IDS)
    ):
        raise RoleGapReviewError("adaptive request, route, or portfolio totals drifted")
    observed_closure_case_ids = tuple(
        route.case_id
        for route in execution.route_executions
        if route.decision.action == "search"
    )
    if observed_closure_case_ids != EXPECTED_CLOSURE_CASE_IDS:
        raise RoleGapReviewError("adaptive closure case identities drifted")
    if (
        execution.provider_row_count != EXPECTED_PROVIDER_ROW_COUNT
        or execution.provider_candidate_count != EXPECTED_PROVIDER_CANDIDATE_COUNT
        or execution.provider_rejection_count != EXPECTED_PROVIDER_REJECTION_COUNT
        or execution.unique_candidate_count != EXPECTED_REVIEW_ROW_COUNT
    ):
        raise RoleGapReviewError("adaptive provider or review denominator drifted")
    if (
        execution.review_packet_eligibility != "eligible_for_source_lock"
        or execution.provider_summary.stopped_reason != "completed"
        or execution.provider_summary.cost_state != "known"
    ):
        raise RoleGapReviewError("the mechanical gate did not authorize source locking")
    if any(
        (
            execution.production_connected,
            execution.report_workflow_connected,
            execution.planner_trigger_connected,
            execution.recovery_connected,
            execution.api_key_used,
        )
    ) or execution.model_call_count != 0:
        raise RoleGapReviewError("the source execution crossed a forbidden boundary")
    if (
        manifest.fixture_sha256 != execution.fixture_sha256
        or manifest.implementation_sha256 != execution.implementation_sha256
        or manifest.runner_sha256 != execution.runner_sha256
        or manifest.soft_stop_usd != execution.soft_stop_usd
    ):
        raise RoleGapReviewError("execution identity does not join manifest")


def _validate_frozen_totals(
    manifest: RoleGapManifestArtifact,
    execution: RoleGapExecutionArtifact,
) -> None:
    """Check the exact observed run rather than its permissive schema alone."""

    if (
        manifest.runner_sha256 != EXPECTED_RUNNER_SHA256
        or execution.runner_sha256 != EXPECTED_RUNNER_SHA256
    ):
        raise RoleGapReviewError("adaptive role-gap runner identity drifted")
    if (
        manifest.fixture_sha256 != EXPECTED_FIXTURE_SHA256
        or execution.fixture_sha256 != EXPECTED_FIXTURE_SHA256
    ):
        raise RoleGapReviewError("adaptive role-gap fixture identity drifted")
    if (
        manifest.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256
        or execution.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256
    ):
        raise RoleGapReviewError("adaptive role-gap implementation identity drifted")
    if not math.isclose(
        execution.provider_summary.reported_cost_usd or -1.0,
        EXPECTED_PROVIDER_COST_USD,
        rel_tol=1e-9,
        abs_tol=1e-9,
    ):
        raise RoleGapReviewError("adaptive role-gap provider cost drifted")
    observed_per_case = {
        portfolio.case_id: len(portfolio.unique_candidates)
        for portfolio in execution.portfolios
    }
    if observed_per_case != EXPECTED_UNIQUE_PER_CASE:
        raise RoleGapReviewError("adaptive candidate distribution drifted")
    if tuple(case.spec.case_id for case in manifest.cases) != CASE_IDS:
        raise RoleGapReviewError("manifest does not contain AD01-AD08 exactly")
    if tuple(portfolio.case_id for portfolio in execution.portfolios) != CASE_IDS:
        raise RoleGapReviewError("execution portfolios are not AD01-AD08")


def _validate_lane_journals(
    source_dir: Path,
    manifest: RoleGapManifestArtifact,
    execution: RoleGapExecutionArtifact,
) -> dict[tuple[str, str], RoleGapLaneExecution]:
    journal_dir = source_dir / "lane-executions"
    if not journal_dir.is_dir():
        raise RoleGapReviewError("lane-executions journal directory is missing")
    expected_names = {
        Path(name).name
        for name in INDEXED_SOURCE_FILES
        if name.startswith("lane-executions/")
    }
    observed_names = {path.name for path in journal_dir.glob("*.json")}
    if observed_names != expected_names:
        raise RoleGapReviewError("lane journals do not cover the frozen path exactly")

    aggregate = {
        (item.case_id, item.lane_id): item for item in execution.lane_executions
    }
    frozen_cases = {case.spec.case_id: case for case in manifest.cases}
    routes = {item.case_id: item for item in execution.route_executions}
    validated: dict[tuple[str, str], RoleGapLaneExecution] = {}
    known_cost = 0.0
    for case_id in CASE_IDS:
        frozen = frozen_cases[case_id]
        route = routes[case_id]
        lane_ids = (
            _LANE_ORDER if route.decision.action == "search" else ("anchor_search",)
        )
        for lane_id in lane_ids:
            journal = RoleGapLaneExecution.model_validate(
                _read_json_object(journal_dir / f"{case_id}--{lane_id}.json")
            )
            key = (case_id, lane_id)
            if journal != aggregate.get(key):
                raise RoleGapReviewError(
                    f"{case_id}/{lane_id}: journal differs from execution"
                )
            if lane_id == "anchor_search":
                expected_call = frozen.anchor_call
                expected_plan = frozen.anchor_plan_sha256
                expected_contract = frozen.anchor_contract_sha256
                expected_role_id = None
                expected_role_kind = None
            else:
                selected = route.decision.selected_closure
                if selected is None:  # pragma: no cover - Pydantic guards this
                    raise RoleGapReviewError(f"{case_id}: closure route lost its role")
                expected_call = selected.call
                expected_plan = selected.plan_sha256
                expected_contract = selected.closure_contract_sha256
                expected_role_id = selected.role_id
                expected_role_kind = selected.role_kind
            if (
                journal.state != "completed"
                or journal.outbound_attempt_count != 1
                or journal.response is None
                or journal.collection_sha256 != frozen.collection_sha256
                or journal.profile_sha256 != frozen.profile_sha256
                or journal.case_contract_sha256 != frozen.case_contract_sha256
                or journal.plan_sha256 != expected_plan
                or journal.lane_contract_sha256 != expected_contract
                or journal.idempotency_key != expected_call.idempotency_key
                or journal.selected_role_id != expected_role_id
                or journal.selected_role_kind != expected_role_kind
            ):
                raise RoleGapReviewError(
                    f"{case_id}/{lane_id}: completed request contract drifted"
                )
            if journal.search_cost_usd is None:
                raise RoleGapReviewError(
                    f"{case_id}/{lane_id}: provider cost is not inspectable"
                )
            known_cost += journal.search_cost_usd
            validated[key] = journal
    if not math.isclose(
        known_cost,
        EXPECTED_PROVIDER_COST_USD,
        rel_tol=1e-9,
        abs_tol=1e-9,
    ):
        raise RoleGapReviewError("lane costs do not join the frozen provider total")
    return validated


def _validate_route_journals(
    source_dir: Path,
    manifest: RoleGapManifestArtifact,
    execution: RoleGapExecutionArtifact,
    lanes: Mapping[tuple[str, str], RoleGapLaneExecution],
) -> tuple[RoleGapRouteExecution, ...]:
    route_dir = source_dir / "route-executions"
    if not route_dir.is_dir():
        raise RoleGapReviewError("route-executions journal directory is missing")
    expected_names = {f"{case_id}.json" for case_id in CASE_IDS}
    observed_names = {path.name for path in route_dir.glob("*.json")}
    if observed_names != expected_names:
        raise RoleGapReviewError("route journals do not cover AD01-AD08 exactly")

    aggregate = {item.case_id: item for item in execution.route_executions}
    frozen_cases = {case.spec.case_id: case for case in manifest.cases}
    validated: list[RoleGapRouteExecution] = []
    for case_id in CASE_IDS:
        route = RoleGapRouteExecution.model_validate(
            _read_json_object(route_dir / f"{case_id}.json")
        )
        if route != aggregate.get(case_id):
            raise RoleGapReviewError(f"{case_id}: route journal differs from execution")
        rebuilt = _route_execution(frozen_cases[case_id], lanes[(case_id, "anchor_search")])  # type: ignore[arg-type]
        if route != rebuilt:
            raise RoleGapReviewError(
                f"{case_id}: route cannot be rebuilt from its anchor journal"
            )
        validated.append(route)
    return tuple(validated)


def _validate_case_portfolios(
    source_dir: Path,
    manifest: RoleGapManifestArtifact,
    execution: RoleGapExecutionArtifact,
    lanes: Mapping[tuple[str, str], RoleGapLaneExecution],
    routes: tuple[RoleGapRouteExecution, ...],
) -> tuple[RoleGapCasePortfolio, ...]:
    portfolio_dir = source_dir / "case-portfolios"
    if not portfolio_dir.is_dir():
        raise RoleGapReviewError("case-portfolios directory is missing")
    expected_names = {f"{case_id}.json" for case_id in CASE_IDS}
    observed_names = {path.name for path in portfolio_dir.glob("*.json")}
    if observed_names != expected_names:
        raise RoleGapReviewError("case portfolios do not cover AD01-AD08 exactly")

    aggregate = {item.case_id: item for item in execution.portfolios}
    frozen_cases = {case.spec.case_id: case for case in manifest.cases}
    route_by_case = {item.case_id: item for item in routes}
    validated: list[RoleGapCasePortfolio] = []
    for case_id in CASE_IDS:
        portfolio = RoleGapCasePortfolio.model_validate(
            _read_json_object(portfolio_dir / f"{case_id}.json")
        )
        if portfolio != aggregate.get(case_id):
            raise RoleGapReviewError(
                f"{case_id}: portfolio differs from aggregate execution"
            )
        route = route_by_case[case_id]
        lane_ids = (
            _LANE_ORDER if route.decision.action == "search" else ("anchor_search",)
        )
        ordered_lanes = tuple(lanes[(case_id, lane_id)] for lane_id in lane_ids)
        rebuilt = build_case_portfolio(  # type: ignore[arg-type]
            frozen_cases[case_id],
            route,
            ordered_lanes,
        )
        if portfolio != rebuilt:
            raise RoleGapReviewError(
                f"{case_id}: portfolio cannot be rebuilt from route and lanes"
            )
        validated.append(portfolio)
    return tuple(validated)


def _case_contexts(
    manifest: RoleGapManifestArtifact,
) -> tuple[dict[str, Any], ...]:
    """Project baseline and role context without exposing adaptive answers."""

    contexts: list[dict[str, Any]] = []
    for frozen in manifest.cases:
        baseline_sources = [
            source.model_dump(mode="json")
            for source in frozen.source_collection.academic_sources
        ]
        gap_state = frozen.source_collection.failed_domains.get("academic", "")
        if not baseline_sources or not gap_state:
            raise RoleGapReviewError(
                f"{frozen.spec.case_id}: frozen academic context is incomplete"
            )
        contexts.append(
            {
                "case_id": frozen.spec.case_id,
                "topic": frozen.spec.topic,
                "collection_sha256": frozen.collection_sha256,
                "profile_sha256": frozen.profile_sha256,
                "gap_subject": "academic",
                "gap_state": gap_state,
                "frozen_baseline_sources": baseline_sources,
                "frozen_role_profile": frozen.spec.roles.profile().model_dump(
                    mode="json"
                ),
            }
        )
    return tuple(contexts)


def _candidate_from_review_row(
    row: Mapping[str, str],
    lanes_by_candidate: Mapping[tuple[str, str], tuple[str, ...]],
) -> RoleGapReviewCandidate:
    key = (row["case_id"], row["unique_candidate_sha256"])
    lane_memberships = lanes_by_candidate.get(key)
    if lane_memberships is None:
        raise RoleGapReviewError(f"review candidate has no portfolio lineage: {key}")
    return RoleGapReviewCandidate(
        case_id=row["case_id"],
        unique_candidate_sha256=row["unique_candidate_sha256"],
        topic=row["topic"],
        title=row["title"],
        url=row["url"],
        normalized_doi=row["normalized_doi"],
        publisher=row["publisher"],
        published_date=row["published_date"],
        evidence_summary=row["evidence_summary"],
        summary_source=row["summary_source"],
        citation_count=row["citation_count"],
        frozen_baseline_sources=row["frozen_baseline_sources"],
        frozen_role_profile=row["frozen_role_profile"],
        lane_memberships=lane_memberships,
    )


def validate_finalized_source(
    source_dir: Path,
    *,
    expected_hashes: Mapping[str, str] | None = None,
) -> RoleGapSourceSnapshot:
    """Reconstruct every AC source seam without network, labels, or mutation."""

    if not source_dir.is_dir():
        raise RoleGapReviewError(f"source directory does not exist: {source_dir}")
    indexed_hashes = _validate_artifact_index(source_dir)
    file_hashes = {
        name: _file_sha256(source_dir / name) for name in INDEXED_SOURCE_FILES
    }
    if file_hashes != indexed_hashes:
        drift = {
            name: {"expected": indexed_hashes[name], "observed": file_hashes[name]}
            for name in INDEXED_SOURCE_FILES
            if file_hashes[name] != indexed_hashes[name]
        }
        raise RoleGapReviewError(f"source files drifted from artifact index: {drift}")
    file_hashes["artifact-index.json"] = EXPECTED_ARTIFACT_INDEX_SHA256
    if expected_hashes is not None and file_hashes != dict(expected_hashes):
        raise RoleGapReviewError("source artifact identity drifted after owner locking")

    manifest = RoleGapManifestArtifact.model_validate(
        _read_json_object(source_dir / "manifest.json")
    )
    execution = RoleGapExecutionArtifact.model_validate(
        _read_json_object(source_dir / "execution.json")
    )
    _validate_complete_execution(manifest, execution)
    _validate_frozen_totals(manifest, execution)
    lanes = _validate_lane_journals(source_dir, manifest, execution)
    routes = _validate_route_journals(source_dir, manifest, execution, lanes)
    portfolios = _validate_case_portfolios(
        source_dir,
        manifest,
        execution,
        lanes,
        routes,
    )

    provider_rows = _read_csv(
        source_dir / "provider-rows.csv", _PROVIDER_ROW_COLUMNS
    )
    if provider_rows != _provider_rows(execution.lane_executions, portfolios):
        raise RoleGapReviewError("provider rows cannot be rebuilt from lane journals")
    route_rows = _read_csv(source_dir / "route-decisions.csv", _ROUTE_COLUMNS)
    if route_rows != _route_rows(routes):
        raise RoleGapReviewError("route CSV cannot be rebuilt from route journals")
    unique_rows = _read_csv(
        source_dir / "unique-candidates.csv", _UNIQUE_CANDIDATE_COLUMNS
    )
    candidate_review_rows = _read_csv(
        source_dir / "candidate-review.csv", _CANDIDATE_REVIEW_COLUMNS
    )
    case_review_rows = _read_csv(
        source_dir / "case-review.csv", _CASE_REVIEW_COLUMNS
    )
    expected_unique, expected_candidate_review, expected_case_review = (
        _unique_and_review_rows(manifest, routes, portfolios)
    )
    if unique_rows != expected_unique:
        raise RoleGapReviewError("unique-candidate CSV does not match portfolios")
    if candidate_review_rows != expected_candidate_review:
        raise RoleGapReviewError("candidate-review CSV cannot be reconstructed")
    if case_review_rows != expected_case_review:
        raise RoleGapReviewError("case-review CSV cannot be reconstructed")
    if any(
        row[field].strip()
        for row in candidate_review_rows
        for field in (
            "directly_relevant",
            "baseline_novel",
            "supported_role_ids",
            "closure_contributed_selected_role",
            "review_note",
        )
    ):
        raise RoleGapReviewError("source candidate-review.csv is no longer blank")
    if any(
        row[field].strip()
        for row in case_review_rows
        for field in (
            "routing_decision_correct",
            "anchor_human_coverable_within_three",
            "union_human_coverable_within_three",
            "review_note",
        )
    ):
        raise RoleGapReviewError("source case-review.csv is no longer blank")

    lanes_by_candidate = {
        (candidate.case_id, candidate.unique_candidate_sha256): tuple(
            candidate.lane_memberships
        )
        for portfolio in portfolios
        for candidate in portfolio.unique_candidates
    }
    candidates = tuple(
        _candidate_from_review_row(row, lanes_by_candidate)
        for row in candidate_review_rows
    )
    if len(candidates) != EXPECTED_REVIEW_ROW_COUNT:
        raise RoleGapReviewError("review denominator does not match the frozen run")
    if len({candidate.key for candidate in candidates}) != len(candidates):
        raise RoleGapReviewError("review candidates contain duplicate identities")
    observed_per_case = dict(
        sorted(Counter(candidate.case_id for candidate in candidates).items())
    )
    if observed_per_case != EXPECTED_UNIQUE_PER_CASE:
        raise RoleGapReviewError("review rows lost the frozen case denominator")
    return RoleGapSourceSnapshot(
        file_hashes=file_hashes,
        manifest=manifest,
        execution=execution,
        candidates=candidates,
        case_contexts=_case_contexts(manifest),
    )


def create_source_lock(
    source_dir: Path,
    output_path: Path,
    *,
    study_owner_id: str,
    confirm_authorized_output: bool,
    note: str | None = None,
    authorized_at: datetime | None = None,
) -> RoleGapSourceLock:
    """Write a separate owner attestation over the exact inspected bytes."""

    if not confirm_authorized_output:
        raise RoleGapReviewError(
            "source locking requires explicit authorized-output confirmation"
        )
    if output_path.exists():
        raise RoleGapReviewError(f"refusing to overwrite source lock: {output_path}")
    snapshot = validate_finalized_source(source_dir)
    source_lock = RoleGapSourceLock(
        executed_revision=EXPECTED_EXECUTED_REVISION,
        fixture_sha256=EXPECTED_FIXTURE_SHA256,
        implementation_sha256=EXPECTED_IMPLEMENTATION_SHA256,
        runner_sha256=EXPECTED_RUNNER_SHA256,
        source_file_sha256=snapshot.file_hashes,
        review_row_count=len(snapshot.candidates),
        study_owner_id=study_owner_id.strip(),
        authorized_at=authorized_at or datetime.now(UTC),
        note=note.strip() if note and note.strip() else None,
    )
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RoleGapReviewError(
            f"could not create source-lock parent {output_path.parent}: {exc}"
        ) from exc
    _write_text_new(
        output_path,
        source_lock.model_dump_json(indent=2) + "\n",
    )
    return source_lock


def _load_source_lock(path: Path) -> RoleGapSourceLock:
    try:
        return RoleGapSourceLock.model_validate(_read_json_object(path))
    except ValueError as exc:
        if isinstance(exc, RoleGapReviewError):
            raise
        raise RoleGapReviewError(f"source lock is invalid: {exc}") from exc


def _packet_rows(snapshot: RoleGapSourceSnapshot) -> list[dict[str, str]]:
    """Return all source rows without any route or retrieval-lane clue."""

    return [
        {
            **candidate.visible_values(),
            "identity_sha256": candidate.identity_sha256,
        }
        for candidate in snapshot.candidates
    ]


def _packet_readme(snapshot: RoleGapSourceSnapshot) -> str:
    case_rows = "\n".join(
        (
            f"| {context['case_id']} | {context['topic']} | "
            f"{len(context['frozen_baseline_sources'])} | "
            f"{len(context['frozen_role_profile']['required_roles'])} / "
            f"{len(context['frozen_role_profile']['scope_roles'])} / "
            f"{len(context['frozen_role_profile']['supporting_roles'])} |"
        )
        for context in snapshot.case_contexts
    )
    return f"""# OpenAlex adaptive role-gap v8 human source review

This packet contains all {len(snapshot.candidates)} DOI/OpenAlex-deduplicated
candidates from one exact, completed and production-disconnected AD01-AD08
run. Preparing or summarizing it makes zero API or model calls.

Do not edit `packet_manifest.json`. Complete only `labels.csv` and
`reviewer_declaration.csv`. Rows may be reordered, but every read-only field
must remain byte-for-byte unchanged. Do not send the separate source-lock file
to the reviewer.

## Blinding

The packet deliberately hides anchor/closure membership, provider rank,
duplicate occurrences, the mechanical route, selected closure role, computed
coverability, aggregate answers and answer keys. Judge only the visible topic,
frozen baseline, role catalogue, title and abstract. Hidden provenance is
joined only after all labels and the declaration pass validation.

## Cases

| Case | Topic | Baseline sources | Required / scope / supporting roles |
|---|---|---:|---:|
{case_rows}

For every row, read the `frozen_baseline_sources` and `frozen_role_profile`
JSON. `supported_role_ids` must be a JSON array containing only visible role
IDs, for example `["required_role", "scope_role"]`.

## Labels

- `YES/YES`: directly relevant and materially absent from the visible baseline.
- `YES/NO`: directly relevant but already represented by the baseline.
- `NO/N/A`: adjacent, generic, or not directly relevant.
- `UNVERIFIABLE/UNVERIFIABLE`: the frozen title and abstract are insufficient
  for a defensible judgment.

Relevant rows require at least one supported role. `NO/N/A` and
`UNVERIFIABLE/UNVERIFIABLE` require `[]`. Every completed row requires a
source-grounded `review_note` of at least twelve non-whitespace characters.

This protocol is intentionally title-and-abstract based. Opening external
pages is optional; declare `ALL_ATTEMPTED`, `SOME`, or `NONE`. External access
is not an eligibility gate. Complete `reviewer_declaration.csv` after all rows.
Only `NONE` and `LANGUAGE_ONLY` generative-AI use are eligible. Substantive
generated judgments remain inspectable but are excluded from gate evaluation.

After every label is locked, the summarizer reveals the frozen route and joins
it to the human labels. A search route is correct only when its selected role
is absent from directly relevant anchor rows. An abstention is correct only
when directly relevant, baseline-novel anchor rows already cover all required
roles plus at least one scope and one supporting role in no more than three
sources. Closure value requires a closure-only `YES/YES` row supporting the
selected role; a duplicate already returned by the anchor cannot earn credit.

All six frozen gates are conjunctive. Passing AD permits only separately
pre-registered planner-trigger, disabled-path and report-value studies. It never
authorizes production Tool Calling.
"""


def _packet_manifest(
    snapshot: RoleGapSourceSnapshot,
    source_lock_path: Path,
    *,
    prepared_at: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "mode": "openalex_adaptive_role_gap_v8_ad_source_review_packet",
        "prepared_at": prepared_at or datetime.now(UTC).isoformat(timespec="seconds"),
        "cohort": "unseen",
        "production_connected": False,
        "report_workflow_connected": False,
        "planner_trigger_connected": False,
        "recovery_connected": False,
        "model_call_count": 0,
        "ad_cohort_opened": True,
        "retrieval_lane_provenance_exposed": False,
        "mechanical_route_exposed": False,
        "external_source_access_required": False,
        "executed_revision": EXPECTED_EXECUTED_REVISION,
        "fixture_sha256": EXPECTED_FIXTURE_SHA256,
        "artifact_index_sha256": EXPECTED_ARTIFACT_INDEX_SHA256,
        "source_lock_sha256": _file_sha256(source_lock_path),
        "source_file_sha256": snapshot.file_hashes,
        "row_count": len(snapshot.candidates),
        "mechanical_result": {
            "request_count": snapshot.execution.request_count,
            "provider_row_count": snapshot.execution.provider_row_count,
            "unique_candidate_count": snapshot.execution.unique_candidate_count,
            "review_packet_eligibility": (
                snapshot.execution.review_packet_eligibility
            ),
            "provider_cost_state": snapshot.execution.provider_summary.cost_state,
            "provider_reported_cost_usd": (
                snapshot.execution.provider_summary.reported_cost_usd
            ),
        },
        "case_contexts": list(snapshot.case_contexts),
        "rows": _packet_rows(snapshot),
        "valid_label_pairs": [list(pair) for pair in sorted(VALID_LABEL_PAIRS)],
        "supported_role_ids_format": "JSON array of visible role IDs",
        "qualification_thresholds": (
            snapshot.manifest.qualification_contract.model_dump(mode="json")
        ),
        "measurement_limit": MEASUREMENT_LIMIT,
    }


def prepare_packet(
    source_dir: Path,
    source_lock_path: Path,
    packet_dir: Path,
) -> dict[str, Any]:
    """Create a route- and lane-blind Schema v2 packet from locked bytes."""

    if packet_dir.exists():
        raise RoleGapReviewError(f"refusing to overwrite packet: {packet_dir}")
    source_lock = _load_source_lock(source_lock_path)
    snapshot = validate_finalized_source(
        source_dir,
        expected_hashes=source_lock.source_file_sha256,
    )
    if source_lock.review_row_count != len(snapshot.candidates):
        raise RoleGapReviewError("source-lock review denominator drifted")
    try:
        packet_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise RoleGapReviewError(f"could not create packet {packet_dir}: {exc}") from exc

    manifest = _packet_manifest(snapshot, source_lock_path)
    label_rows = [
        {
            **candidate.visible_values(),
            "directly_relevant": "",
            "baseline_novel": "",
            "supported_role_ids": "",
            "review_note": "",
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
    snapshot: RoleGapSourceSnapshot,
    source_lock_path: Path,
) -> dict[tuple[str, str], RoleGapReviewCandidate]:
    try:
        prepared_at = datetime.fromisoformat(str(manifest["prepared_at"]))
    except (KeyError, ValueError) as exc:
        raise RoleGapReviewError("packet prepared_at is not an ISO timestamp") from exc
    if prepared_at.tzinfo is None:
        raise RoleGapReviewError("packet prepared_at must be timezone-aware")
    expected_manifest = _packet_manifest(
        snapshot,
        source_lock_path,
        prepared_at=str(manifest["prepared_at"]),
    )
    if manifest != expected_manifest:
        raise RoleGapReviewError(
            "packet manifest does not match the source-locked blind projection"
        )
    expected_rows = _packet_rows(snapshot)
    if any(
        hidden in row
        for row in expected_rows
        for hidden in HIDDEN_REVIEW_FIELDS
    ):
        raise RoleGapReviewError("reviewer packet leaks adaptive provenance")
    return {candidate.key: candidate for candidate in snapshot.candidates}


def _profile_role_groups(
    candidate: RoleGapReviewCandidate,
) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    try:
        profile = json.loads(candidate.frozen_role_profile)
        required = frozenset(
            item["role_id"] for item in profile["required_roles"]
        )
        scope = frozenset(item["role_id"] for item in profile["scope_roles"])
        supporting = frozenset(
            item["role_id"] for item in profile["supporting_roles"]
        )
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RoleGapReviewError(
            f"{candidate.row_id}: frozen role profile is malformed"
        ) from exc
    if (
        not required
        or not scope
        or not supporting
        or (required & scope)
        or (required & supporting)
        or (scope & supporting)
    ):
        raise RoleGapReviewError(
            f"{candidate.row_id}: frozen role groups are incomplete or overlap"
        )
    return required, scope, supporting


def _validated_role_ids(
    value: str,
    candidate: RoleGapReviewCandidate,
) -> tuple[str, ...]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RoleGapReviewError(
            f"{candidate.row_id}: supported_role_ids must be JSON"
        ) from exc
    if (
        not isinstance(parsed, list)
        or any(not isinstance(item, str) or not item for item in parsed)
        or len(parsed) != len(set(parsed))
    ):
        raise RoleGapReviewError(
            f"{candidate.row_id}: supported_role_ids must be a unique string array"
        )
    required, scope, supporting = _profile_role_groups(candidate)
    unknown = sorted(set(parsed) - (required | scope | supporting))
    if unknown:
        raise RoleGapReviewError(
            f"{candidate.row_id}: unknown supported role IDs {unknown}"
        )
    return tuple(sorted(parsed))


def _validated_label(
    row: dict[str, str],
    expected: RoleGapReviewCandidate,
) -> dict[str, Any] | None:
    observed_visible = {field: row[field] for field in READ_ONLY_LABEL_FIELDS}
    if observed_visible != expected.visible_values():
        raise RoleGapReviewError(
            f"label identity or read-only context drifted for {expected.row_id}"
        )
    values = [
        row[field].strip()
        for field in (
            "directly_relevant",
            "baseline_novel",
            "supported_role_ids",
            "review_note",
        )
    ]
    if not any(values):
        return None
    if not all(values):
        raise RoleGapReviewError(f"{expected.row_id} is partially completed")
    relevant, novel, role_text, note = values
    relevant = relevant.upper()
    novel = novel.upper()
    if (relevant, novel) not in VALID_LABEL_PAIRS:
        raise RoleGapReviewError(
            f"{expected.row_id} has invalid relevance/novelty pair: "
            f"{relevant}/{novel}"
        )
    role_ids = _validated_role_ids(role_text, expected)
    if relevant == "YES" and not role_ids:
        raise RoleGapReviewError(
            f"{expected.row_id}: relevant rows require supported roles"
        )
    if relevant != "YES" and role_ids:
        raise RoleGapReviewError(
            f"{expected.row_id}: non-relevant rows must use an empty role array"
        )
    if len("".join(note.split())) < 12:
        raise RoleGapReviewError(
            f"{expected.row_id}: review_note is too short to ground the judgment"
        )
    return {
        "case_id": expected.case_id,
        "unique_candidate_sha256": expected.unique_candidate_sha256,
        "row_id": expected.row_id,
        "directly_relevant": relevant,
        "baseline_novel": novel,
        "supported_role_ids": role_ids,
        "review_note": note,
    }


def _minimal_cover(
    case_candidates: list[tuple[RoleGapReviewCandidate, dict[str, Any]]],
    *,
    anchor_only: bool,
) -> tuple[str, ...] | None:
    eligible = [
        (candidate, label)
        for candidate, label in case_candidates
        if label["directly_relevant"] == "YES"
        and label["baseline_novel"] == "YES"
        and (not anchor_only or "anchor_search" in candidate.lane_memberships)
    ]
    if not eligible:
        return None
    eligible.sort(key=lambda item: item[0].row_id)
    required, scope, supporting = _profile_role_groups(eligible[0][0])
    for size in range(1, min(3, len(eligible)) + 1):
        for selected in combinations(eligible, size):
            covered = set().union(
                *(set(label["supported_role_ids"]) for _, label in selected)
            )
            if (
                required.issubset(covered)
                and bool(scope & covered)
                and bool(supporting & covered)
            ):
                return tuple(candidate.row_id for candidate, _ in selected)
    return None


def _role_gap_metrics(
    snapshot: RoleGapSourceSnapshot,
    completed: Mapping[tuple[str, str], dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, str], str, list[dict[str, Any]]]:
    relevant_rows = [
        label
        for label in completed.values()
        if label["directly_relevant"] == "YES"
    ]
    denominator = len(snapshot.candidates)
    precision = len(relevant_rows) / denominator if denominator else None
    relevant_novel_case_ids = sorted(
        {
            label["case_id"]
            for label in completed.values()
            if label["directly_relevant"] == "YES"
            and label["baseline_novel"] == "YES"
        }
    )

    candidates_by_case = {
        case_id: [
            candidate
            for candidate in snapshot.candidates
            if candidate.case_id == case_id
        ]
        for case_id in CASE_IDS
    }
    route_by_case = {
        route.case_id: route for route in snapshot.execution.route_executions
    }
    anchor_covers: dict[str, tuple[str, ...]] = {}
    union_covers: dict[str, tuple[str, ...]] = {}
    correct_route_ids: list[str] = []
    closure_value_ids: list[str] = []
    route_assessments: list[dict[str, Any]] = []
    for case_id in CASE_IDS:
        case_items = [
            (candidate, completed[candidate.key])
            for candidate in candidates_by_case[case_id]
        ]
        anchor_cover = _minimal_cover(case_items, anchor_only=True)
        union_cover = _minimal_cover(case_items, anchor_only=False)
        if anchor_cover is not None:
            anchor_covers[case_id] = anchor_cover
        if union_cover is not None:
            union_covers[case_id] = union_cover

        human_anchor_role_ids = sorted(
            set().union(
                *(
                    set(label["supported_role_ids"])
                    for candidate, label in case_items
                    if "anchor_search" in candidate.lane_memberships
                    and label["directly_relevant"] == "YES"
                )
            )
        )
        route = route_by_case[case_id]
        selected = route.decision.selected_closure
        if route.decision.action == "search":
            if selected is None:  # pragma: no cover - Pydantic guards this
                raise RoleGapReviewError(f"{case_id}: search route lost selected role")
            route_correct = selected.role_id not in human_anchor_role_ids
            contribution_rows = sorted(
                candidate.row_id
                for candidate, label in case_items
                if candidate.lane_memberships == ("role_closure",)
                and label["directly_relevant"] == "YES"
                and label["baseline_novel"] == "YES"
                and selected.role_id in label["supported_role_ids"]
            )
        else:
            route_correct = anchor_cover is not None
            contribution_rows = []
        if route_correct:
            correct_route_ids.append(case_id)
        if contribution_rows:
            closure_value_ids.append(case_id)
        route_assessments.append(
            {
                "case_id": case_id,
                "route_action": route.decision.action,
                "route_reason": route.decision.reason,
                "mechanical_missing_role_ids": list(
                    route.decision.missing_role_ids
                ),
                "selected_role_id": selected.role_id if selected else None,
                "human_relevant_anchor_role_ids": human_anchor_role_ids,
                "routing_decision_correct": route_correct,
                "anchor_human_coverable_within_three": anchor_cover is not None,
                "anchor_selected_cover_row_ids": list(anchor_cover or ()),
                "union_human_coverable_within_three": union_cover is not None,
                "union_selected_cover_row_ids": list(union_cover or ()),
                "closure_selected_role_contribution_row_ids": contribution_rows,
            }
        )

    anchor_case_ids = sorted(anchor_covers)
    union_case_ids = sorted(union_covers)
    coverability_gain = len(union_case_ids) - len(anchor_case_ids)
    thresholds = snapshot.manifest.qualification_contract
    threshold_results = {
        "relevant_novel_cases": (
            "pass"
            if len(relevant_novel_case_ids)
            >= thresholds.minimum_cases_with_relevant_novel_candidate
            else "fail"
        ),
        "candidate_pool_precision": (
            "pass"
            if precision is not None
            and precision >= thresholds.minimum_candidate_pool_precision
            else "fail"
        ),
        "human_correct_routing_decisions": (
            "pass"
            if len(correct_route_ids)
            >= thresholds.minimum_human_correct_routing_decisions
            else "fail"
        ),
        "selected_role_closure_value": (
            "pass"
            if len(closure_value_ids)
            >= thresholds.minimum_cases_with_selected_role_closure_value
            else "fail"
        ),
        "human_coverable_cases": (
            "pass"
            if len(union_case_ids) >= thresholds.minimum_human_coverable_cases
            else "fail"
        ),
        "coverability_gain_over_anchor": (
            "pass"
            if coverability_gain >= thresholds.minimum_coverability_gain_over_anchor
            else "fail"
        ),
    }
    metrics = {
        "case_denominator": len(CASE_IDS),
        "reviewable_candidate_denominator": denominator,
        "directly_relevant_candidate_count": len(relevant_rows),
        "candidate_pool_precision": precision,
        "relevant_novel_case_ids": relevant_novel_case_ids,
        "relevant_novel_case_count": len(relevant_novel_case_ids),
        "human_correct_routing_case_ids": sorted(correct_route_ids),
        "human_correct_routing_case_count": len(correct_route_ids),
        "selected_role_closure_value_case_ids": sorted(closure_value_ids),
        "selected_role_closure_value_case_count": len(closure_value_ids),
        "anchor_human_coverable_case_ids": anchor_case_ids,
        "anchor_human_coverable_case_count": len(anchor_case_ids),
        "union_human_coverable_case_ids": union_case_ids,
        "union_human_coverable_case_count": len(union_case_ids),
        "coverability_gain_over_anchor": coverability_gain,
    }
    decision = (
        "pass"
        if all(result == "pass" for result in threshold_results.values())
        else "fail"
    )
    return metrics, threshold_results, decision, route_assessments


def summarize_packet(
    source_dir: Path,
    source_lock_path: Path,
    packet_dir: Path,
) -> dict[str, Any]:
    """Validate labels before joining hidden adaptive route provenance."""

    if not packet_dir.is_dir():
        raise RoleGapReviewError(f"packet directory does not exist: {packet_dir}")
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
        (row["case_id"], row["unique_candidate_sha256"]) for row in label_rows
    ]
    if len(observed_keys) != len(set(observed_keys)):
        raise RoleGapReviewError("labels contain duplicate candidate identities")
    if set(observed_keys) != set(expected_candidates):
        missing = sorted(set(expected_candidates) - set(observed_keys))
        extra = sorted(set(observed_keys) - set(expected_candidates))
        raise RoleGapReviewError(
            f"label identities do not match packet; missing={missing}, extra={extra}"
        )

    completed: dict[tuple[str, str], dict[str, Any]] = {}
    incomplete_row_ids: list[str] = []
    for row in label_rows:
        key = (row["case_id"], row["unique_candidate_sha256"])
        validated = _validated_label(row, expected_candidates[key])
        if validated is None:
            incomplete_row_ids.append(expected_candidates[key].row_id)
        else:
            completed[key] = validated

    declaration_path = packet_dir / "reviewer_declaration.csv"
    declaration_rows = _read_csv(declaration_path, DECLARATION_FIELDS)
    if len(declaration_rows) != 1:
        raise RoleGapReviewError(
            "reviewer_declaration.csv must contain exactly one row"
        )
    raw_declaration = dict(declaration_rows[0])
    declaration = _validated_declaration(raw_declaration)
    ordered_completed = [completed[key] for key in sorted(completed)]
    uninspectable_row_ids = [
        row["row_id"]
        for row in ordered_completed
        if row["directly_relevant"] == "UNVERIFIABLE"
    ]
    method_issues: list[str] = []
    if declaration is not None and declaration["reviewed_all"] != "YES":
        method_issues.append("reviewer_did_not_confirm_all_rows")

    if incomplete_row_ids or declaration is None:
        protocol_status = "incomplete"
    elif declaration["generative_ai_use"] not in ELIGIBLE_AI_USE:
        protocol_status = "excluded_substantive_ai"
    elif uninspectable_row_ids or method_issues:
        protocol_status = "not_inspectable"
    else:
        protocol_status = "complete"

    metrics: dict[str, Any] | None = None
    route_assessments: list[dict[str, Any]] | None = None
    threshold_results = {
        "relevant_novel_cases": "not_evaluated",
        "candidate_pool_precision": "not_evaluated",
        "human_correct_routing_decisions": "not_evaluated",
        "selected_role_closure_value": "not_evaluated",
        "human_coverable_cases": "not_evaluated",
        "coverability_gain_over_anchor": "not_evaluated",
    }
    decision = "not_evaluated"
    if protocol_status == "complete":
        metrics, threshold_results, decision, route_assessments = _role_gap_metrics(
            snapshot,
            completed,
        )

    return {
        "schema_version": 1,
        "mode": "openalex_adaptive_role_gap_v8_ad_source_review_result",
        "cohort": "unseen",
        "production_connected": False,
        "report_workflow_connected": False,
        "planner_trigger_connected": False,
        "recovery_connected": False,
        "model_call_count": 0,
        "ad_cohort_opened": True,
        "source_lock_sha256": _file_sha256(source_lock_path),
        "source_file_sha256": snapshot.file_hashes,
        "packet_manifest_sha256": _file_sha256(
            packet_dir / "packet_manifest.json"
        ),
        "labels_file_sha256": _file_sha256(packet_dir / "labels.csv"),
        "reviewer_declaration_file_sha256": _file_sha256(declaration_path),
        "executed_revision": EXPECTED_EXECUTED_REVISION,
        "protocol_status": protocol_status,
        "decision": decision,
        "row_count": len(expected_candidates),
        "completed_row_count": len(completed),
        "incomplete_row_ids": sorted(incomplete_row_ids),
        "uninspectable_row_ids": sorted(uninspectable_row_ids),
        "method_issues": method_issues,
        # Preserve exact spreadsheet strings as well as the normalized
        # declaration. This prevents a later correction from rewriting history.
        "reviewer_declaration_raw": raw_declaration,
        "reviewer_declaration": declaration,
        "external_source_access_required": False,
        "retrieval_lane_provenance_exposed_to_reviewer": False,
        "mechanical_route_exposed_to_reviewer": False,
        "adaptive_provenance_joined_after_label_validation": (
            protocol_status == "complete"
        ),
        "observed_label_counts": (
            {
                "directly_relevant": dict(
                    sorted(
                        Counter(
                            row["directly_relevant"] for row in ordered_completed
                        ).items()
                    )
                ),
                "baseline_novel": dict(
                    sorted(
                        Counter(
                            row["baseline_novel"] for row in ordered_completed
                        ).items()
                    )
                ),
            }
            if not incomplete_row_ids
            else None
        ),
        "route_assessments_after_unblinding": route_assessments,
        "role_gap_result": {
            "metrics": metrics,
            "threshold_results": threshold_results,
            "decision": decision,
        },
        "qualification_thresholds": manifest["qualification_thresholds"],
        "post_ad_studies_eligible": decision == "pass",
        "production_connection_authorized": False,
        "remaining_production_blockers": (
            [
                "planner_trigger_precision",
                "disabled_path_regression",
                "report_value",
            ]
            if decision == "pass"
            else [
                "adaptive_role_gap_v8_unseen_candidate_value",
                "planner_trigger_precision",
                "disabled_path_regression",
                "report_value",
            ]
        ),
        "measurement_limit": MEASUREMENT_LIMIT,
    }


def write_summary(path: Path, result: dict[str, Any]) -> None:
    """Persist one strict interpretation without replacing human evidence."""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RoleGapReviewError(
            f"could not create summary parent {path.parent}: {exc}"
        ) from exc
    _write_text_new(
        path,
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _stdout_json(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    # Provider titles may contain characters outside a Windows console code
    # page. Escaping stdout cannot alter the UTF-8 artifacts already written.
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    lock = commands.add_parser("lock", help="bind the exact v8 AD unseen output")
    lock.add_argument("source", type=Path)
    lock.add_argument("output", type=Path)
    lock.add_argument("--study-owner-id", required=True)
    lock.add_argument("--confirm-authorized-output", action="store_true")
    lock.add_argument("--note")

    prepare = commands.add_parser(
        "prepare",
        help="create a blank route- and lane-blind Schema v2 packet",
    )
    prepare.add_argument("source", type=Path)
    prepare.add_argument("source_lock", type=Path)
    prepare.add_argument("packet", type=Path)

    summarize = commands.add_parser(
        "summarize",
        help="validate human labels and write one strict result",
    )
    summarize.add_argument("source", type=Path)
    summarize.add_argument("source_lock", type=Path)
    summarize.add_argument("packet", type=Path)
    summarize.add_argument("output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "lock":
        result = create_source_lock(
            args.source,
            args.output,
            study_owner_id=args.study_owner_id,
            confirm_authorized_output=args.confirm_authorized_output,
            note=args.note,
        )
    elif args.command == "prepare":
        result = prepare_packet(args.source, args.source_lock, args.packet)
    else:
        result = summarize_packet(
            args.source,
            args.source_lock,
            args.packet,
        )
        write_summary(args.output, result)
    print(_stdout_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
