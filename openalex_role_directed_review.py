"""Source-lock and review the frozen role-directed retrieval v7 AA run.

The provider runner intentionally stopped at a mechanically complete candidate
portfolio.  This module binds those exact write-once bytes, prepares a
lane-blind Schema v2 packet, and evaluates returned human labels against the
five already-frozen candidate-value gates.  It opens no socket, invokes no
model, does not inspect AB01-AA08, and never authorizes production Tool Calling.
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
    Phase4ReviewError as RoleDirectedReviewError,
    _file_sha256,
    _read_csv,
    _read_json_object,
    _validated_declaration,
    _write_csv_new,
    _write_text_new,
)
from openalex_role_directed_live import (
    EXPECTED_IMPLEMENTATION_SHA256,
    RoleDirectedCasePortfolio,
    RoleDirectedExecutionArtifact,
    RoleDirectedLaneExecution,
    RoleDirectedManifestArtifact,
    _AGGREGATE_SOURCE_FILES,
    _LANE_ORDER,
    _PROVIDER_ROW_COLUMNS,
    _REVIEW_COLUMNS,
    _UNIQUE_CANDIDATE_COLUMNS,
    build_case_portfolio,
    _provider_rows,
    _unique_and_review_rows,
)
from openalex_role_directed_unseen import EXPECTED_FIXTURE_SHA256


EXPECTED_EXECUTED_REVISION = "2a61c32d4693f4f9a44965312c378dc8f14fb308"
EXPECTED_RUNNER_SHA256 = (
    "5a41c3647b4fdff100043b5e0c03bc3e66b61a9721e3ac33af5f0bbd7a7b346f"
)
EXPECTED_ARTIFACT_INDEX_SHA256 = (
    "7ff4d2a86d19caac5e2a73177870f77540ec19a431bc42e3f321324830bf56bc"
)
EXPECTED_SOURCE_FILE_SHA256 = {
    "case-portfolios/AA01.json": (
        "46b778254755e98b959cfa18696931d8cb7a5ef02f46aae2db300dde8ddcc3cf"
    ),
    "case-portfolios/AA02.json": (
        "decb3c572a5a70260b5ba396190cc7753bd1555be017534772ecda66a2365039"
    ),
    "case-portfolios/AA03.json": (
        "898d1c94e14b696a4531eddd452e623f2000c36fb3ec3229c84df5ab1d5b2d46"
    ),
    "case-portfolios/AA04.json": (
        "a4238b2c24ef5245443dfebfa27777c2a46e2e7eb95d8f8c5f662ac866861c1a"
    ),
    "case-portfolios/AA05.json": (
        "b34120fa416201f14037deacb1d1f4e41621784c30d0fab0550f344f972919ec"
    ),
    "case-portfolios/AA06.json": (
        "d1c4575e09a3a2f09b0928ac3ab69578ffb2402f4479fbccd716d08d0ad7ecc0"
    ),
    "case-portfolios/AA07.json": (
        "5fed80b348d5861c22c32c88848a367fab0a153f0388b3e3b7f682edd7f47011"
    ),
    "case-portfolios/AA08.json": (
        "06570f66f1314543d4561f6d8985a511ecf29426c5d82181caa51fee344a99d7"
    ),
    "execution.json": (
        "50aeddf9ec2604b12cdc62eb8ae2949c056ce9feeb0a06a60cc3a68ccdcd2506"
    ),
    "lane-executions/AA01--technology_evidence.json": (
        "d54ec8cdae031b102fae345da471dcd9a005ed6a07cb749d20f5747c905b6226"
    ),
    "lane-executions/AA01--technology_scope.json": (
        "c86c17f91f6ee4f759f41505471b20c493da6d69bb2e51013f0bdc34c1e8e259"
    ),
    "lane-executions/AA02--technology_evidence.json": (
        "1e95f7313d08f1db9d99fadb14f2a24be765db2e1c4ed3292e9f4bb29e9b26af"
    ),
    "lane-executions/AA02--technology_scope.json": (
        "d7bb11dd3b89654049032501fa55b4547cdd24e2c776ef482375509686f3c5fa"
    ),
    "lane-executions/AA03--technology_evidence.json": (
        "a2d98f0aaf6557c67c7c5144e03c4477c1abebd89c59655013021fa05469e862"
    ),
    "lane-executions/AA03--technology_scope.json": (
        "b11a68d4b7dd5e2ed5ddff6831d729803f43214d0df21d04b93997079cec8fd7"
    ),
    "lane-executions/AA04--technology_evidence.json": (
        "b5cae15f25be41e8d3f93de5839a13376caa676e9bec341eca4abedd43d7980c"
    ),
    "lane-executions/AA04--technology_scope.json": (
        "50634d8b176c0192735cf05671399d86723859bc96e9827a4e0dda71bf3d93a4"
    ),
    "lane-executions/AA05--technology_evidence.json": (
        "be6a649284c514b179ccb81b376ce8934df5e085210b56fd05b3f94b9e969173"
    ),
    "lane-executions/AA05--technology_scope.json": (
        "be5b44d4715888685da636931a1fa9af5a40a5647873d7fd7fe72ca1ae1124d9"
    ),
    "lane-executions/AA06--technology_evidence.json": (
        "d0f0d8809b78fb4f9228d435b0a02d6265b8bf91673a086a8fa569f9773678cb"
    ),
    "lane-executions/AA06--technology_scope.json": (
        "fee95846ae3a7052b1c1c51849812fd2f9da42e31df141a17084f2a4f51f5c8e"
    ),
    "lane-executions/AA07--technology_evidence.json": (
        "75d98d8b9621b47792345821e6316739458c330d99795fa878c267f7d19cb802"
    ),
    "lane-executions/AA07--technology_scope.json": (
        "bbec5feac2c3223a5cbc6f32b79886d060d511c3d8b9056c5ec8c7a4d31065b8"
    ),
    "lane-executions/AA08--technology_evidence.json": (
        "17c4e850be7fea0467888385b246fe57d27877afba2b2ee076b7c272b0b236ad"
    ),
    "lane-executions/AA08--technology_scope.json": (
        "4de0675a247a48b5db31d286dd7ac038fc150ad4d2ad5202fefd6bf4dd1dcad8"
    ),
    "manifest.json": (
        "221e874252ea010fb60fe253a7aaa06a115f0dc2e38eb2dffac48ccfc6863d7d"
    ),
    "provider-rows.csv": (
        "5f01e459e612d10778925da5f3a2b478eb1a492635212dc80e82b1712513ec0b"
    ),
    "review.csv": (
        "2a62f9b3367413c61f87553b184356eb4c3dfcbef2d25beac14fb859d0210719"
    ),
    "unique-candidates.csv": (
        "1a11206970c8d751de01a896f8f36ef4f904d8ef146f9fbcdd87545b25bd21af"
    ),
    "artifact-index.json": EXPECTED_ARTIFACT_INDEX_SHA256,
}

CASE_IDS = tuple(f"AA{index:02d}" for index in range(1, 9))
INDEXED_SOURCE_FILES = (
    *_AGGREGATE_SOURCE_FILES,
    *(f"lane-executions/{case_id}--{lane_id}.json" for case_id in CASE_IDS for lane_id in _LANE_ORDER),
    *(f"case-portfolios/{case_id}.json" for case_id in CASE_IDS),
)
SOURCE_FILES = (*INDEXED_SOURCE_FILES, "artifact-index.json")
EXPECTED_UNIQUE_PER_CASE = {
    "AA01": 11,
    "AA02": 10,
    "AA03": 7,
    "AA04": 9,
    "AA05": 10,
    "AA06": 12,
    "AA07": 10,
    "AA08": 10,
}
EXPECTED_REVIEW_ROW_COUNT = 79
EXPECTED_PROVIDER_ROW_COUNT = 96
EXPECTED_PROVIDER_CANDIDATE_COUNT = 84
EXPECTED_PROVIDER_REJECTION_COUNT = 12
EXPECTED_PROVIDER_COST_USD = 0.016

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
    "occurrence_count",
    "provider_ranks",
    "owner_occurrence_sha256",
    "occurrence_sha256s",
    "candidate_sha256",
)
MEASUREMENT_LIMIT = (
    "This source-locked development review measures title-and-abstract relevance, "
    "novelty relative to the visible frozen baseline, role coverability, and "
    "retrieval-lane incremental value for one AA01-AA08 run. It does not verify "
    "full-text source truth, estimate recall, evaluate a semantic judge, measure "
    "report value, or authorize production Tool Calling."
)


class RoleDirectedSourceLock(BaseModel):
    """Study-owner attestation over the exact AA01-AA08 provider bytes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["openalex_role_directed_v7_source_artifact_lock"] = (
        "openalex_role_directed_v7_source_artifact_lock"
    )
    cohort: Literal["development"] = "development"
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
    def _validate_frozen_identity(self) -> "RoleDirectedSourceLock":
        if self.executed_revision != EXPECTED_EXECUTED_REVISION:
            raise ValueError("source lock executed revision does not match")
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("source lock fixture identity does not match")
        if self.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
            raise ValueError("source lock implementation identities do not match")
        if self.runner_sha256 != EXPECTED_RUNNER_SHA256:
            raise ValueError("source lock runner identity does not match")
        if self.source_file_sha256 != EXPECTED_SOURCE_FILE_SHA256:
            raise ValueError("source lock does not identify the frozen v7 AA run")
        if self.review_row_count != EXPECTED_REVIEW_ROW_COUNT:
            raise ValueError("source lock review denominator does not match")
        if self.authorized_at.tzinfo is None:
            raise ValueError("source lock timestamp must be timezone-aware")
        return self


@dataclass(frozen=True)
class RoleDirectedReviewCandidate:
    """One unique source with reviewer-visible context and hidden lane lineage."""

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
        """Return the exact reviewer projection; lane provenance is excluded."""

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
class RoleDirectedSourceSnapshot:
    """Validated source reused unchanged at lock, packet, and result seams."""

    file_hashes: dict[str, str]
    manifest: RoleDirectedManifestArtifact
    execution: RoleDirectedExecutionArtifact
    candidates: tuple[RoleDirectedReviewCandidate, ...]
    case_contexts: tuple[dict[str, Any], ...]


def _validate_artifact_index(
    source_dir: Path,
    file_hashes: Mapping[str, str],
) -> None:
    index = _read_json_object(source_dir / "artifact-index.json")
    expected = {
        "schema_version": 1,
        "mode": "openalex_role_directed_v7_artifact_index",
        "production_connected": False,
        "report_workflow_connected": False,
        "planner_trigger_connected": False,
        "recovery_connected": False,
        "model_call_count": 0,
        "source_file_sha256": {
            name: file_hashes[name] for name in INDEXED_SOURCE_FILES
        },
    }
    if index != expected:
        raise RoleDirectedReviewError(
            "artifact index does not match the complete role-directed bytes"
        )


def _validate_complete_execution(
    manifest: RoleDirectedManifestArtifact,
    execution: RoleDirectedExecutionArtifact,
) -> None:
    if execution.overall_state != "completed":
        raise RoleDirectedReviewError(
            "only the completed AA01-AA08 v7 run may be source-locked"
        )
    if (
        execution.request_count != 16
        or execution.attempted_lane_count != 16
        or execution.successful_lane_count != 16
        or execution.completed_portfolio_count != 8
    ):
        raise RoleDirectedReviewError(
            "role-directed source execution must contain sixteen successful lanes"
        )
    if (
        execution.provider_row_count != EXPECTED_PROVIDER_ROW_COUNT
        or execution.provider_candidate_count != EXPECTED_PROVIDER_CANDIDATE_COUNT
        or execution.provider_rejection_count != EXPECTED_PROVIDER_REJECTION_COUNT
        or execution.unique_candidate_count != EXPECTED_REVIEW_ROW_COUNT
    ):
        raise RoleDirectedReviewError(
            "role-directed provider or review denominator drifted"
        )
    if (
        execution.review_packet_eligibility != "eligible_for_source_lock"
        or execution.provider_summary.stopped_reason != "completed"
        or execution.provider_summary.cost_state != "known"
    ):
        raise RoleDirectedReviewError(
            "the frozen mechanical gate did not authorize source locking"
        )
    if any(
        (
            execution.production_connected,
            execution.report_workflow_connected,
            execution.planner_trigger_connected,
            execution.recovery_connected,
            execution.api_key_used,
        )
    ) or execution.model_call_count != 0:
        raise RoleDirectedReviewError(
            "the source execution crossed a forbidden connection boundary"
        )
    if (
        manifest.fixture_sha256 != execution.fixture_sha256
        or manifest.implementation_sha256 != execution.implementation_sha256
        or manifest.runner_sha256 != execution.runner_sha256
        or manifest.soft_stop_usd != execution.soft_stop_usd
    ):
        raise RoleDirectedReviewError("execution identity does not join manifest")



def _validate_frozen_totals(
    manifest: RoleDirectedManifestArtifact,
    execution: RoleDirectedExecutionArtifact,
) -> None:
    """Check the exact observed run rather than only its permissive schema."""

    if (
        manifest.runner_sha256 != EXPECTED_RUNNER_SHA256
        or execution.runner_sha256 != EXPECTED_RUNNER_SHA256
    ):
        raise RoleDirectedReviewError("role-directed runner identity drifted")
    if (
        manifest.fixture_sha256 != EXPECTED_FIXTURE_SHA256
        or execution.fixture_sha256 != EXPECTED_FIXTURE_SHA256
    ):
        raise RoleDirectedReviewError("role-directed fixture identity drifted")
    if (
        manifest.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256
        or execution.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256
    ):
        raise RoleDirectedReviewError("role-directed implementation identity drifted")
    if not math.isclose(
        execution.provider_summary.reported_cost_usd or -1.0,
        EXPECTED_PROVIDER_COST_USD,
        rel_tol=1e-9,
        abs_tol=1e-9,
    ):
        raise RoleDirectedReviewError("role-directed provider cost drifted")
    observed_per_case = {
        portfolio.case_id: len(portfolio.unique_candidates)
        for portfolio in execution.portfolios
    }
    if observed_per_case != EXPECTED_UNIQUE_PER_CASE:
        raise RoleDirectedReviewError(
            "role-directed candidate distribution does not match the frozen run"
        )
    if tuple(case.spec.case_id for case in manifest.cases) != CASE_IDS:
        raise RoleDirectedReviewError("manifest does not contain AA01-AA08 exactly")
    if tuple(portfolio.case_id for portfolio in execution.portfolios) != CASE_IDS:
        raise RoleDirectedReviewError("execution portfolios are not AA01-AA08")


def _validate_lane_journals(
    source_dir: Path,
    manifest: RoleDirectedManifestArtifact,
    execution: RoleDirectedExecutionArtifact,
) -> dict[tuple[str, str], RoleDirectedLaneExecution]:
    journal_dir = source_dir / "lane-executions"
    if not journal_dir.is_dir():
        raise RoleDirectedReviewError("lane-executions journal directory is missing")
    expected_names = {
        f"{case_id}--{lane_id}.json"
        for case_id in CASE_IDS
        for lane_id in _LANE_ORDER
    }
    observed_names = {path.name for path in journal_dir.glob("*.json")}
    if observed_names != expected_names:
        raise RoleDirectedReviewError(
            "lane journals do not cover the sixteen frozen requests exactly"
        )

    aggregate = {
        (item.case_id, item.lane_id): item for item in execution.lane_executions
    }
    manifest_cases = {case.spec.case_id: case for case in manifest.cases}
    validated: dict[tuple[str, str], RoleDirectedLaneExecution] = {}
    known_cost = 0.0
    for case_id in CASE_IDS:
        frozen_case = manifest_cases[case_id]
        for lane_id in _LANE_ORDER:
            journal = RoleDirectedLaneExecution.model_validate(
                _read_json_object(journal_dir / f"{case_id}--{lane_id}.json")
            )
            key = (case_id, lane_id)
            if journal != aggregate.get(key):
                raise RoleDirectedReviewError(
                    f"{case_id}/{lane_id}: lane journal differs from execution"
                )
            lane_index = _LANE_ORDER.index(lane_id)
            if (
                journal.state != "completed"
                or journal.outbound_attempt_count != 1
                or journal.response is None
                or journal.lane_index != lane_index
                or journal.collection_sha256 != frozen_case.collection_sha256
                or journal.plan_sha256 != frozen_case.plan_sha256
                or journal.profile_sha256 != frozen_case.profile_sha256
                or journal.case_contract_sha256 != frozen_case.case_contract_sha256
                or journal.lane_contract_sha256
                != frozen_case.lane_contract_sha256s[lane_index]
            ):
                raise RoleDirectedReviewError(
                    f"{case_id}/{lane_id}: completed request contract drifted"
                )
            if journal.search_cost_usd is None:
                raise RoleDirectedReviewError(
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
        raise RoleDirectedReviewError("lane-journal costs do not join the frozen total")
    return validated


def _validate_case_portfolios(
    source_dir: Path,
    manifest: RoleDirectedManifestArtifact,
    execution: RoleDirectedExecutionArtifact,
    lanes: Mapping[tuple[str, str], RoleDirectedLaneExecution],
) -> tuple[RoleDirectedCasePortfolio, ...]:
    portfolio_dir = source_dir / "case-portfolios"
    if not portfolio_dir.is_dir():
        raise RoleDirectedReviewError("case-portfolios directory is missing")
    expected_names = {f"{case_id}.json" for case_id in CASE_IDS}
    observed_names = {path.name for path in portfolio_dir.glob("*.json")}
    if observed_names != expected_names:
        raise RoleDirectedReviewError(
            "case portfolios do not cover AA01-AA08 exactly"
        )

    aggregate = {item.case_id: item for item in execution.portfolios}
    frozen_cases = {case.spec.case_id: case for case in manifest.cases}
    validated: list[RoleDirectedCasePortfolio] = []
    for case_id in CASE_IDS:
        portfolio = RoleDirectedCasePortfolio.model_validate(
            _read_json_object(portfolio_dir / f"{case_id}.json")
        )
        if portfolio != aggregate.get(case_id):
            raise RoleDirectedReviewError(
                f"{case_id}: portfolio differs from aggregate execution"
            )
        ordered_lanes = tuple(lanes[(case_id, lane_id)] for lane_id in _LANE_ORDER)
        rebuilt = build_case_portfolio(frozen_cases[case_id], ordered_lanes)  # type: ignore[arg-type]
        if portfolio != rebuilt:
            raise RoleDirectedReviewError(
                f"{case_id}: portfolio cannot be rebuilt from its lane journals"
            )
        validated.append(portfolio)
    return tuple(validated)


def _case_contexts(
    manifest: RoleDirectedManifestArtifact,
) -> tuple[dict[str, Any], ...]:
    """Project only context the reviewer needs; query-lane data stays hidden."""

    contexts: list[dict[str, Any]] = []
    for frozen in manifest.cases:
        baseline_sources = [
            source.model_dump(mode="json")
            for source in frozen.source_collection.academic_sources
        ]
        if not baseline_sources:
            raise RoleDirectedReviewError(
                f"{frozen.spec.case_id}: frozen academic baseline is empty"
            )
        contexts.append(
            {
                "case_id": frozen.spec.case_id,
                "topic": frozen.spec.topic,
                "collection_sha256": frozen.collection_sha256,
                "profile_sha256": frozen.profile_sha256,
                "gap_subject": "academic",
                "gap_state": frozen.source_collection.failed_domains.get(
                    "academic", ""
                ),
                "frozen_baseline_sources": baseline_sources,
                "frozen_role_profile": frozen.spec.roles.profile().model_dump(
                    mode="json"
                ),
            }
        )
    if any(not context["gap_state"] for context in contexts):
        raise RoleDirectedReviewError("frozen academic gap state is missing")
    return tuple(contexts)


def _candidate_from_review_row(
    row: Mapping[str, str],
    lanes_by_candidate: Mapping[tuple[str, str], tuple[str, ...]],
) -> RoleDirectedReviewCandidate:
    key = (row["case_id"], row["unique_candidate_sha256"])
    lane_memberships = lanes_by_candidate.get(key)
    if lane_memberships is None:
        raise RoleDirectedReviewError(
            f"review candidate has no portfolio lineage: {key}"
        )
    return RoleDirectedReviewCandidate(
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
) -> RoleDirectedSourceSnapshot:
    """Reconstruct every source seam without network, labels, or mutation."""

    if not source_dir.is_dir():
        raise RoleDirectedReviewError(f"source directory does not exist: {source_dir}")
    file_hashes = {name: _file_sha256(source_dir / name) for name in SOURCE_FILES}
    frozen_hashes = (
        dict(expected_hashes)
        if expected_hashes is not None
        else EXPECTED_SOURCE_FILE_SHA256
    )
    if set(frozen_hashes) != set(SOURCE_FILES):
        raise RoleDirectedReviewError(
            "expected hashes must identify every v7 AA source file"
        )
    if file_hashes != frozen_hashes:
        drift = {
            name: {"expected": frozen_hashes[name], "observed": file_hashes[name]}
            for name in SOURCE_FILES
            if file_hashes[name] != frozen_hashes[name]
        }
        raise RoleDirectedReviewError(
            f"source artifact identity drifted after locking: {drift}"
        )
    _validate_artifact_index(source_dir, file_hashes)

    manifest = RoleDirectedManifestArtifact.model_validate(
        _read_json_object(source_dir / "manifest.json")
    )
    execution = RoleDirectedExecutionArtifact.model_validate(
        _read_json_object(source_dir / "execution.json")
    )
    _validate_complete_execution(manifest, execution)
    _validate_frozen_totals(manifest, execution)
    lanes = _validate_lane_journals(source_dir, manifest, execution)
    portfolios = _validate_case_portfolios(
        source_dir,
        manifest,
        execution,
        lanes,
    )

    provider_rows = _read_csv(
        source_dir / "provider-rows.csv", _PROVIDER_ROW_COLUMNS
    )
    expected_provider_rows = _provider_rows(execution.lane_executions, portfolios)
    if provider_rows != expected_provider_rows:
        raise RoleDirectedReviewError(
            "provider rows cannot be reconstructed from lane journals"
        )
    unique_rows = _read_csv(
        source_dir / "unique-candidates.csv", _UNIQUE_CANDIDATE_COLUMNS
    )
    review_rows = _read_csv(source_dir / "review.csv", _REVIEW_COLUMNS)
    expected_unique_rows, expected_review_rows = _unique_and_review_rows(
        manifest,
        portfolios,
    )
    if unique_rows != expected_unique_rows:
        raise RoleDirectedReviewError(
            "unique-candidate CSV does not match reconstructed portfolios"
        )
    if review_rows != expected_review_rows:
        raise RoleDirectedReviewError(
            "blank review CSV does not match reconstructed candidates"
        )
    if any(
        row[field].strip()
        for row in review_rows
        for field in (
            "directly_relevant",
            "baseline_novel",
            "supported_role_ids",
            "review_note",
        )
    ):
        raise RoleDirectedReviewError("source review.csv is no longer blank")

    lanes_by_candidate = {
        (candidate.case_id, candidate.unique_candidate_sha256): tuple(
            candidate.lane_memberships
        )
        for portfolio in portfolios
        for candidate in portfolio.unique_candidates
    }
    candidates = tuple(
        _candidate_from_review_row(row, lanes_by_candidate)
        for row in review_rows
    )
    if len(candidates) != EXPECTED_REVIEW_ROW_COUNT:
        raise RoleDirectedReviewError(
            "review candidate denominator does not match the frozen run"
        )
    if len({candidate.key for candidate in candidates}) != len(candidates):
        raise RoleDirectedReviewError("review candidates contain duplicate identities")
    observed_per_case = dict(
        sorted(Counter(candidate.case_id for candidate in candidates).items())
    )
    if observed_per_case != EXPECTED_UNIQUE_PER_CASE:
        raise RoleDirectedReviewError(
            "review rows do not retain the frozen per-case denominator"
        )
    return RoleDirectedSourceSnapshot(
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
) -> RoleDirectedSourceLock:
    """Write a separate owner attestation over the exact inspected bytes."""

    if not confirm_authorized_output:
        raise RoleDirectedReviewError(
            "source locking requires explicit authorized-output confirmation"
        )
    if output_path.exists():
        raise RoleDirectedReviewError(
            f"refusing to overwrite source lock: {output_path}"
        )
    snapshot = validate_finalized_source(source_dir)
    source_lock = RoleDirectedSourceLock(
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
        raise RoleDirectedReviewError(
            f"could not create source-lock parent {output_path.parent}: {exc}"
        ) from exc
    _write_text_new(
        output_path,
        json.dumps(
            source_lock.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return source_lock


def _load_source_lock(path: Path) -> RoleDirectedSourceLock:
    try:
        return RoleDirectedSourceLock.model_validate(_read_json_object(path))
    except ValueError as exc:
        if isinstance(exc, RoleDirectedReviewError):
            raise
        raise RoleDirectedReviewError(f"source lock is invalid: {exc}") from exc


def _qualification_thresholds(
    snapshot: RoleDirectedSourceSnapshot,
) -> dict[str, int | float]:
    return snapshot.manifest.qualification_contract.model_dump(mode="json")


def _packet_rows(
    snapshot: RoleDirectedSourceSnapshot,
) -> list[dict[str, str]]:
    """Return the complete reviewer projection without retrieval-lane clues."""

    return [
        {
            **candidate.visible_values(),
            "identity_sha256": candidate.identity_sha256,
        }
        for candidate in snapshot.candidates
    ]


def _packet_readme(snapshot: RoleDirectedSourceSnapshot) -> str:
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
    return f"""# OpenAlex role-directed retrieval v7 human review

This packet contains all {len(snapshot.candidates)} DOI/OpenAlex-deduplicated
candidates from one exact, completed and production-disconnected AA01-AA08
run. Preparing or summarizing it makes zero API or model calls.

Do not edit `packet_manifest.json`. Complete only `labels.csv` and
`reviewer_declaration.csv`. Rows may be reordered, but every read-only field
must remain byte-for-byte unchanged. Do not send the separate source-lock file
to the reviewer.

## Blinding

The packet deliberately hides retrieval-lane membership, provider rank,
duplicate occurrence count, lane incremental status, computed coverability,
model judgments and answer keys. Judge only the visible topic, frozen baseline,
role catalogue, title and abstract. Do not try to infer which query returned a
candidate.

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

The five frozen gates are conjunctive: relevant-and-novel evidence in at least
6/8 cases, union role coverability in at least 6/8 cases, at least 25% directly
relevant candidates, a unique evidence-lane contribution in at least 4/8
cases, and at least two more union-coverable cases than scope-only cases. Lane
provenance is joined only after every human label passes validation. Even a
pass permits only a separately pre-registered AB evaluation; it never
authorizes production Tool Calling.
"""


def _packet_manifest(
    snapshot: RoleDirectedSourceSnapshot,
    source_lock_path: Path,
    *,
    prepared_at: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "mode": "openalex_role_directed_v7_candidate_value_review_packet",
        "prepared_at": prepared_at or datetime.now(UTC).isoformat(timespec="seconds"),
        "cohort": "development",
        "production_connected": False,
        "report_workflow_connected": False,
        "planner_trigger_connected": False,
        "recovery_connected": False,
        "model_call_count": 0,
        "ab_cohort_opened": False,
        "retrieval_lane_provenance_exposed": False,
        "external_source_access_required": False,
        "executed_revision": EXPECTED_EXECUTED_REVISION,
        "fixture_sha256": EXPECTED_FIXTURE_SHA256,
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
        "qualification_thresholds": _qualification_thresholds(snapshot),
        "measurement_limit": MEASUREMENT_LIMIT,
    }


def prepare_packet(
    source_dir: Path,
    source_lock_path: Path,
    packet_dir: Path,
) -> dict[str, Any]:
    """Create a lane-blind Schema v2 packet from exact source-locked bytes."""

    if packet_dir.exists():
        raise RoleDirectedReviewError(f"refusing to overwrite packet: {packet_dir}")
    source_lock = _load_source_lock(source_lock_path)
    snapshot = validate_finalized_source(
        source_dir,
        expected_hashes=source_lock.source_file_sha256,
    )
    if source_lock.review_row_count != len(snapshot.candidates):
        raise RoleDirectedReviewError("source-lock review denominator drifted")
    try:
        packet_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise RoleDirectedReviewError(
            f"could not create packet {packet_dir}: {exc}"
        ) from exc

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
    snapshot: RoleDirectedSourceSnapshot,
    source_lock_path: Path,
) -> dict[tuple[str, str], RoleDirectedReviewCandidate]:
    try:
        prepared_at = datetime.fromisoformat(str(manifest["prepared_at"]))
    except (KeyError, ValueError) as exc:
        raise RoleDirectedReviewError(
            "packet prepared_at is not an ISO timestamp"
        ) from exc
    if prepared_at.tzinfo is None:
        raise RoleDirectedReviewError("packet prepared_at must be timezone-aware")

    expected_manifest = _packet_manifest(
        snapshot,
        source_lock_path,
        prepared_at=str(manifest["prepared_at"]),
    )
    if manifest != expected_manifest:
        raise RoleDirectedReviewError(
            "packet manifest does not match the source-locked lane-blind projection"
        )
    expected_rows = _packet_rows(snapshot)
    if any(
        hidden in row
        for row in expected_rows
        for hidden in HIDDEN_REVIEW_FIELDS
    ):
        raise RoleDirectedReviewError(
            "reviewer-visible packet leaks hidden retrieval provenance"
        )
    return {candidate.key: candidate for candidate in snapshot.candidates}


def _profile_role_groups(
    candidate: RoleDirectedReviewCandidate,
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
        raise RoleDirectedReviewError(
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
        raise RoleDirectedReviewError(
            f"{candidate.row_id}: frozen role groups are incomplete or overlap"
        )
    return required, scope, supporting


def _validated_role_ids(
    value: str,
    candidate: RoleDirectedReviewCandidate,
) -> tuple[str, ...]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RoleDirectedReviewError(
            f"{candidate.row_id}: supported_role_ids must be JSON"
        ) from exc
    if (
        not isinstance(parsed, list)
        or any(not isinstance(item, str) or not item for item in parsed)
        or len(parsed) != len(set(parsed))
    ):
        raise RoleDirectedReviewError(
            f"{candidate.row_id}: supported_role_ids must be a unique string array"
        )
    required, scope, supporting = _profile_role_groups(candidate)
    known = required | scope | supporting
    unknown = sorted(set(parsed) - known)
    if unknown:
        raise RoleDirectedReviewError(
            f"{candidate.row_id}: unknown supported role IDs {unknown}"
        )
    # Canonical ordering removes reviewer spreadsheet order from deterministic
    # cover selection while preserving exactly which roles the human supplied.
    return tuple(sorted(parsed))


def _validated_label(
    row: dict[str, str],
    expected: RoleDirectedReviewCandidate,
) -> dict[str, Any] | None:
    observed_visible = {field: row[field] for field in READ_ONLY_LABEL_FIELDS}
    if observed_visible != expected.visible_values():
        raise RoleDirectedReviewError(
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
        raise RoleDirectedReviewError(f"{expected.row_id} is partially completed")
    relevant, novel, role_text, note = values
    relevant = relevant.upper()
    novel = novel.upper()
    if (relevant, novel) not in VALID_LABEL_PAIRS:
        raise RoleDirectedReviewError(
            f"{expected.row_id} has invalid relevance/novelty pair: "
            f"{relevant}/{novel}"
        )
    role_ids = _validated_role_ids(role_text, expected)
    if relevant == "YES" and not role_ids:
        raise RoleDirectedReviewError(
            f"{expected.row_id}: relevant rows require supported roles"
        )
    if relevant != "YES" and role_ids:
        raise RoleDirectedReviewError(
            f"{expected.row_id}: non-relevant rows must use an empty role array"
        )
    if len("".join(note.split())) < 12:
        raise RoleDirectedReviewError(
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
    case_candidates: list[
        tuple[RoleDirectedReviewCandidate, dict[str, Any]]
    ],
    *,
    scope_only: bool,
) -> tuple[str, ...] | None:
    eligible = [
        (candidate, label)
        for candidate, label in case_candidates
        if label["directly_relevant"] == "YES"
        and label["baseline_novel"] == "YES"
        and (
            not scope_only
            or "technology_scope" in candidate.lane_memberships
        )
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


def _candidate_value_metrics(
    snapshot: RoleDirectedSourceSnapshot,
    completed: Mapping[tuple[str, str], dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, str], str]:
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
        case_id: [candidate for candidate in snapshot.candidates if candidate.case_id == case_id]
        for case_id in CASE_IDS
    }
    union_covers: dict[str, tuple[str, ...]] = {}
    scope_covers: dict[str, tuple[str, ...]] = {}
    evidence_only_case_ids: list[str] = []
    for case_id in CASE_IDS:
        case_items = [
            (candidate, completed[candidate.key])
            for candidate in candidates_by_case[case_id]
        ]
        union_cover = _minimal_cover(case_items, scope_only=False)
        if union_cover is not None:
            union_covers[case_id] = union_cover
        scope_cover = _minimal_cover(case_items, scope_only=True)
        if scope_cover is not None:
            scope_covers[case_id] = scope_cover
        if any(
            label["directly_relevant"] == "YES"
            and candidate.lane_memberships == ("technology_evidence",)
            for candidate, label in case_items
        ):
            evidence_only_case_ids.append(case_id)

    union_case_ids = sorted(union_covers)
    scope_case_ids = sorted(scope_covers)
    coverability_gain = len(union_case_ids) - len(scope_case_ids)
    thresholds = snapshot.manifest.qualification_contract
    threshold_results = {
        "relevant_novel_cases": (
            "pass"
            if len(relevant_novel_case_ids)
            >= thresholds.minimum_cases_with_relevant_novel_candidate
            else "fail"
        ),
        "human_coverable_cases": (
            "pass"
            if len(union_case_ids) >= thresholds.minimum_human_coverable_cases
            else "fail"
        ),
        "candidate_pool_precision": (
            "pass"
            if precision is not None
            and precision >= thresholds.minimum_candidate_pool_precision
            else "fail"
        ),
        "unique_evidence_lane_value": (
            "pass"
            if len(evidence_only_case_ids)
            >= thresholds.minimum_cases_with_unique_evidence_lane_value
            else "fail"
        ),
        "coverability_gain_over_scope": (
            "pass"
            if coverability_gain
            >= thresholds.minimum_coverability_gain_over_scope_lane
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
        "human_coverable_case_ids": union_case_ids,
        "human_coverable_case_count": len(union_case_ids),
        "scope_only_coverable_case_ids": scope_case_ids,
        "scope_only_coverable_case_count": len(scope_case_ids),
        "coverability_gain_over_scope": coverability_gain,
        "unique_evidence_lane_value_case_ids": sorted(evidence_only_case_ids),
        "unique_evidence_lane_value_case_count": len(evidence_only_case_ids),
        "union_selected_cover_row_ids": {
            case_id: list(union_covers[case_id]) for case_id in union_case_ids
        },
        "scope_only_selected_cover_row_ids": {
            case_id: list(scope_covers[case_id]) for case_id in scope_case_ids
        },
    }
    decision = (
        "pass"
        if all(result == "pass" for result in threshold_results.values())
        else "fail"
    )
    return metrics, threshold_results, decision


def summarize_packet(
    source_dir: Path,
    source_lock_path: Path,
    packet_dir: Path,
) -> dict[str, Any]:
    """Validate human evidence before joining hidden lane provenance."""

    if not packet_dir.is_dir():
        raise RoleDirectedReviewError(
            f"packet directory does not exist: {packet_dir}"
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
        (row["case_id"], row["unique_candidate_sha256"])
        for row in label_rows
    ]
    if len(observed_keys) != len(set(observed_keys)):
        raise RoleDirectedReviewError("labels contain duplicate candidate identities")
    if set(observed_keys) != set(expected_candidates):
        missing = sorted(set(expected_candidates) - set(observed_keys))
        extra = sorted(set(observed_keys) - set(expected_candidates))
        raise RoleDirectedReviewError(
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

    declaration_rows = _read_csv(
        packet_dir / "reviewer_declaration.csv",
        DECLARATION_FIELDS,
    )
    if len(declaration_rows) != 1:
        raise RoleDirectedReviewError(
            "reviewer_declaration.csv must contain exactly one row"
        )
    declaration = _validated_declaration(declaration_rows[0])
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
    threshold_results = {
        "relevant_novel_cases": "not_evaluated",
        "human_coverable_cases": "not_evaluated",
        "candidate_pool_precision": "not_evaluated",
        "unique_evidence_lane_value": "not_evaluated",
        "coverability_gain_over_scope": "not_evaluated",
    }
    decision = "not_evaluated"
    if protocol_status == "complete":
        metrics, threshold_results, decision = _candidate_value_metrics(
            snapshot,
            completed,
        )

    return {
        "schema_version": 1,
        "mode": "openalex_role_directed_v7_candidate_value_review_result",
        "cohort": "development",
        "production_connected": False,
        "report_workflow_connected": False,
        "planner_trigger_connected": False,
        "recovery_connected": False,
        "model_call_count": 0,
        "ab_cohort_opened": False,
        "source_lock_sha256": _file_sha256(source_lock_path),
        "source_file_sha256": snapshot.file_hashes,
        "packet_manifest_sha256": _file_sha256(
            packet_dir / "packet_manifest.json"
        ),
        "executed_revision": EXPECTED_EXECUTED_REVISION,
        "protocol_status": protocol_status,
        "decision": decision,
        "row_count": len(expected_candidates),
        "completed_row_count": len(completed),
        "incomplete_row_ids": sorted(incomplete_row_ids),
        "uninspectable_row_ids": sorted(uninspectable_row_ids),
        "method_issues": method_issues,
        "reviewer_declaration": declaration,
        "external_source_access_required": False,
        "retrieval_lane_provenance_exposed_to_reviewer": False,
        "retrieval_lane_provenance_joined_after_label_validation": (
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
        "candidate_value_result": {
            "metrics": metrics,
            "threshold_results": threshold_results,
            "decision": decision,
        },
        "qualification_thresholds": manifest["qualification_thresholds"],
        "ab_evaluation_eligible": decision == "pass",
        "production_connection_authorized": False,
        "remaining_production_blockers": (
            [
                "separately_preregistered_ab_evaluation",
                "semantic_source_selection",
                "planner_trigger_precision",
                "disabled_path_regression",
                "report_value",
            ]
            if decision == "pass"
            else [
                "role_directed_v7_candidate_value",
                "planner_trigger_precision",
                "disabled_path_regression",
                "report_value",
            ]
        ),
        "measurement_limit": MEASUREMENT_LIMIT,
    }


def write_summary(path: Path, result: dict[str, Any]) -> None:
    """Persist one strict interpretation without changing returned labels."""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RoleDirectedReviewError(
            f"could not create summary parent {path.parent}: {exc}"
        ) from exc
    _write_text_new(
        path,
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _stdout_json(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    # Windows terminals often default to GBK. Escaping stdout keeps provider
    # titles from turning a fully persisted zero-network operation into a false
    # process failure after all artifacts have already been written.
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    lock = commands.add_parser("lock", help="bind the exact v7 AA live output")
    lock.add_argument("source", type=Path)
    lock.add_argument("output", type=Path)
    lock.add_argument("--study-owner-id", required=True)
    lock.add_argument("--confirm-authorized-output", action="store_true")
    lock.add_argument("--note")

    prepare = commands.add_parser(
        "prepare",
        help="create a blank lane-blind Schema v2 packet",
    )
    prepare.add_argument("source", type=Path)
    prepare.add_argument("source_lock", type=Path)
    prepare.add_argument("packet", type=Path)

    summarize = commands.add_parser(
        "summarize",
        help="validate returned labels and write one result",
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
