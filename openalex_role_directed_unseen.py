"""Zero-network preflight for the frozen role-directed retrieval v7 study.

The v6 human diagnostic found that candidate retrieval, not semantic consensus,
was the first bottleneck. AA01-AA08 and AB01-AB08 therefore freeze two
role-directed search lanes per case before this implementation exists. This
module validates the raw fixture bytes before parsing, expands both evidence-gap
calls, and publishes every immutable identity a future separately authorised
runner would need. It imports no provider, execution, or model client, so its
CLI cannot spend either a search or model budget.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from academic_agent.evidence import EvidenceSource
from academic_agent.evidence_gap import (
    GapContext,
    GapPlanProposal,
    GapSearchIntent,
    ValidatedGapCall,
    ValidatedGapPlan,
    build_gap_context,
    source_collection_sha256,
    validate_gap_plan,
)
from academic_agent.openalex_evidence_set import (
    EvidenceSetRoleProfile,
    EvidenceSetRoleSpec,
)
from academic_agent.source_pipeline import SourceCollection


_ROOT = Path(__file__).resolve().parent
DEFAULT_FIXTURE_PATH = (
    _ROOT / "tests/fixtures/openalex_role_directed_v7_challenge.json"
)
EXPECTED_FIXTURE_SHA256 = (
    "9a91746d0a77fee6d57bfc91ae4329ab78a89109fca6f35171d56c0f3ee95761"
)
_DEVELOPMENT_ORDER = tuple(f"AA{index:02d}" for index in range(1, 9))
_UNSEEN_ORDER = tuple(f"AB{index:02d}" for index in range(1, 9))
_LANE_ORDER = ("technology_scope", "technology_evidence")
_COLLECTED_AT = datetime(2026, 9, 1, tzinfo=UTC)
_ACCESSED_DATE = date(2026, 9, 1)

RetrievalLaneId = Literal["technology_scope", "technology_evidence"]


class OpenAlexRoleDirectedPreflightError(ValueError):
    """Raised before live authority when the frozen v7 contract drifts."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256_bytes(canonical.encode("utf-8"))


def _model_sha256(value: BaseModel) -> str:
    return _sha256_bytes(value.model_dump_json(exclude_none=False).encode("utf-8"))


class RoleDirectedProviderContract(BaseModel):
    """Exact two-request OpenAlex boundary without a transport import."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["anonymous_openalex"] = "anonymous_openalex"
    requests_per_case: Literal[2] = 2
    result_limit_per_request: Literal[6] = 6
    require_abstract: Literal[True] = True
    allow_redirects: Literal[False] = False
    allow_retries: Literal[False] = False

    def sha256(self) -> str:
        return _model_sha256(self)


class RoleDirectedPortfolioContract(BaseModel):
    """Deterministic merge rules for a future provider result portfolio."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lane_order: tuple[str, str]
    deduplicate_by: tuple[str, str]
    preserve_lane_memberships: Literal[True] = True
    preserve_provider_rank: Literal[True] = True
    maximum_unique_candidates_per_case: Literal[12] = 12
    maximum_cover_sources_per_case: Literal[3] = 3
    semantic_filter_before_human_qualification: Literal[False] = False

    @model_validator(mode="after")
    def _validate_exact_merge_contract(self) -> "RoleDirectedPortfolioContract":
        if self.lane_order != _LANE_ORDER:
            raise ValueError("v7 retrieval lane order drifted")
        if self.deduplicate_by != (
            "normalized_doi",
            "canonical_openalex_url",
        ):
            raise ValueError("v7 deduplication precedence drifted")
        return self

    def sha256(self) -> str:
        return _model_sha256(self)


class RoleDirectedQualificationContract(BaseModel):
    """Frozen gates that decide whether later semantic judging is justified."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_cases_with_relevant_novel_candidate: Literal[6] = 6
    minimum_human_coverable_cases: Literal[6] = 6
    minimum_candidate_pool_precision: Literal[0.25] = 0.25
    minimum_cases_with_unique_evidence_lane_value: Literal[4] = 4
    minimum_coverability_gain_over_scope_lane: Literal[2] = 2

    def sha256(self) -> str:
        return _model_sha256(self)


class RoleDirectedRoleGroups(BaseModel):
    """Fixture roles converted to the existing immutable role profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    required: tuple[EvidenceSetRoleSpec, ...] = Field(min_length=2, max_length=4)
    scope: tuple[EvidenceSetRoleSpec, ...] = Field(min_length=1, max_length=4)
    supporting: tuple[EvidenceSetRoleSpec, ...] = Field(
        min_length=2,
        max_length=8,
    )

    def profile(self) -> EvidenceSetRoleProfile:
        # The shared profile owns duplicate-ID validation. Reusing it avoids a
        # subtly different v7 role grammar that later code could misinterpret.
        return EvidenceSetRoleProfile(
            required_roles=self.required,
            scope_roles=self.scope,
            supporting_roles=self.supporting,
        )


class RoleDirectedLaneSpec(BaseModel):
    """One code-owned query tied to explicit semantic role identifiers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lane_id: RetrievalLaneId
    query: str = Field(min_length=20, max_length=500)
    target_role_ids: tuple[str, ...] = Field(min_length=3, max_length=8)

    @model_validator(mode="after")
    def _validate_unique_targets(self) -> "RoleDirectedLaneSpec":
        if len(self.target_role_ids) != len(set(self.target_role_ids)):
            raise ValueError("retrieval lane target role IDs must be unique")
        return self


class RoleDirectedCaseSpec(BaseModel):
    """One topic, one role profile, and the two ordered retrieval lanes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^A[AB]0[1-8]$")
    topic: str = Field(min_length=20, max_length=300)
    roles: RoleDirectedRoleGroups
    lanes: tuple[RoleDirectedLaneSpec, RoleDirectedLaneSpec]

    @model_validator(mode="after")
    def _validate_role_bound_lanes(self) -> "RoleDirectedCaseSpec":
        if tuple(lane.lane_id for lane in self.lanes) != _LANE_ORDER:
            raise ValueError("case lanes must remain technology_scope then technology_evidence")
        if self.lanes[0].query.casefold() == self.lanes[1].query.casefold():
            raise ValueError("case retrieval queries must be distinct")

        profile = self.roles.profile()
        required_ids = {role.role_id for role in profile.required_roles}
        scope_ids = {role.role_id for role in profile.scope_roles}
        supporting_ids = {role.role_id for role in profile.supporting_roles}
        known_ids = required_ids | scope_ids | supporting_ids

        for lane in self.lanes:
            target_ids = set(lane.target_role_ids)
            unknown = sorted(target_ids - known_ids)
            if unknown:
                raise ValueError(
                    f"{self.case_id} {lane.lane_id}: unknown target roles {unknown}"
                )
            if not required_ids.issubset(target_ids):
                raise ValueError(
                    f"{self.case_id} {lane.lane_id}: every lane must target "
                    "all required roles"
                )
            if lane.lane_id == "technology_scope" and not target_ids & scope_ids:
                raise ValueError(
                    f"{self.case_id}: technology_scope must target a scope role"
                )
            if (
                lane.lane_id == "technology_evidence"
                and not target_ids & supporting_ids
            ):
                raise ValueError(
                    f"{self.case_id}: technology_evidence must target a "
                    "supporting role"
                )
        return self

    def sha256(self) -> str:
        return _model_sha256(self)


class RoleDirectedChallengeManifest(BaseModel):
    """Complete raw-byte-frozen v7 development and unseen input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    method_id: Literal["openalex-role-directed-retrieval-portfolio-v7"]
    provider_contract: RoleDirectedProviderContract
    portfolio_contract: RoleDirectedPortfolioContract
    qualification_contract: RoleDirectedQualificationContract
    development_cases: tuple[RoleDirectedCaseSpec, ...] = Field(
        min_length=8,
        max_length=8,
    )
    unseen_cases: tuple[RoleDirectedCaseSpec, ...] = Field(
        min_length=8,
        max_length=8,
    )

    @model_validator(mode="after")
    def _validate_cross_contracts(self) -> "RoleDirectedChallengeManifest":
        if tuple(case.case_id for case in self.development_cases) != (
            _DEVELOPMENT_ORDER
        ):
            raise ValueError("development cases must remain AA01 through AA08")
        if tuple(case.case_id for case in self.unseen_cases) != _UNSEEN_ORDER:
            raise ValueError("unseen cases must remain AB01 through AB08")

        all_cases = (*self.development_cases, *self.unseen_cases)
        if len({case.topic for case in all_cases}) != len(all_cases):
            raise ValueError("topic strings must be unique across both cohorts")
        queries = tuple(lane.query for case in all_cases for lane in case.lanes)
        if len(set(query.casefold() for query in queries)) != len(queries):
            raise ValueError("retrieval queries must be unique across both cohorts")
        if (
            self.provider_contract.requests_per_case
            * self.provider_contract.result_limit_per_request
            != self.portfolio_contract.maximum_unique_candidates_per_case
        ):
            raise ValueError("provider row ceiling and portfolio ceiling drifted")
        if (
            self.portfolio_contract.maximum_cover_sources_per_case
            > self.portfolio_contract.maximum_unique_candidates_per_case
        ):
            raise ValueError("cover-source ceiling exceeds the candidate ceiling")
        return self


@dataclass(frozen=True)
class PreparedRoleDirectedCase:
    """Deterministic identities for a future separately locked live runner."""

    spec: RoleDirectedCaseSpec
    collection: SourceCollection
    context: GapContext
    plan: ValidatedGapPlan
    collection_sha256: str
    plan_sha256: str
    profile_sha256: str
    case_contract_sha256: str
    lane_contract_sha256s: tuple[str, str]


def _plan_sha256(plan: ValidatedGapPlan) -> str:
    return _sha256_bytes(plan.model_dump_json(exclude_none=False).encode("utf-8"))


def _case_contract_sha256(
    spec: RoleDirectedCaseSpec,
    *,
    method_id: str,
    provider_contract_sha256: str,
    portfolio_contract_sha256: str,
    qualification_contract_sha256: str,
) -> str:
    return _sha256_json(
        {
            "method_id": method_id,
            "spec": spec.model_dump(mode="json"),
            "provider_contract_sha256": provider_contract_sha256,
            "portfolio_contract_sha256": portfolio_contract_sha256,
            "qualification_contract_sha256": qualification_contract_sha256,
        }
    )


def _lane_contract_sha256(
    spec: RoleDirectedCaseSpec,
    lane: RoleDirectedLaneSpec,
    call: ValidatedGapCall,
    *,
    method_id: str,
    provider_contract_sha256: str,
    portfolio_contract_sha256: str,
) -> str:
    return _sha256_json(
        {
            "method_id": method_id,
            "case_id": spec.case_id,
            "topic": spec.topic,
            "profile_sha256": spec.roles.profile().sha256(),
            "lane": lane.model_dump(mode="json"),
            "validated_call": call.model_dump(mode="json"),
            "provider_contract_sha256": provider_contract_sha256,
            "portfolio_contract_sha256": portfolio_contract_sha256,
        }
    )


def _seed_source(spec: RoleDirectedCaseSpec) -> EvidenceSource:
    """Create a valid gap context without pretending retrieval already ran."""

    return EvidenceSource(
        source_id="A1",
        title=f"{spec.topic}: frozen role-directed v7 baseline context",
        url=(
            "https://doi.org/10.5555/openalex-role-directed-v7."
            f"{spec.case_id.casefold()}"
        ),
        publisher="Frozen Role-directed v7 Fixture",
        accessed_date=_ACCESSED_DATE,
        source_type="academic_paper",
        evidence_summary=(
            f"This synthetic baseline records the question {spec.topic}. "
            "It contains no provider candidate and does not satisfy the explicit "
            "academic retrieval gap used by this disconnected study."
        ),
        summary_source="abstract",
    )


def build_case(
    spec: RoleDirectedCaseSpec,
    *,
    method_id: str,
    provider_contract_sha256: str,
    portfolio_contract_sha256: str,
    qualification_contract_sha256: str,
    result_limit: int,
) -> PreparedRoleDirectedCase:
    """Expand one two-call plan without network, clocks, randomness, or labels."""

    collection = SourceCollection(
        topic=spec.topic,
        display_topic=spec.topic,
        output_language="English",
        weight_profile="industrial",
        collected_at=_COLLECTED_AT,
        academic_sources=[_seed_source(spec)],
        academic_queries=[spec.topic],
        patent_queries=[spec.topic],
        market_queries=[spec.topic],
        failed_domains={"academic": "frozen role-directed v7 retrieval challenge"},
    )
    context = build_gap_context(collection)
    trigger = next(
        (
            signal
            for signal in context.signals
            if signal.code == "retrieval_domain_failed"
            and signal.subject == "academic"
        ),
        None,
    )
    if trigger is None:
        raise OpenAlexRoleDirectedPreflightError(
            f"{spec.case_id}: frozen academic gap signal was not produced"
        )

    plan = validate_gap_plan(
        context,
        GapPlanProposal(
            decision="search",
            rationale=(
                "The frozen role-directed case authorizes two complementary "
                "read-only academic requests for its explicit evidence gap."
            ),
            calls=tuple(
                GapSearchIntent(
                    tool="academic_search",
                    query=lane.query,
                    trigger_ids=(trigger.signal_id,),
                    result_limit=result_limit,
                )
                for lane in spec.lanes
            ),
        ),
    )
    if len(plan.calls) != len(_LANE_ORDER):
        raise OpenAlexRoleDirectedPreflightError(
            f"{spec.case_id}: validated plan did not retain both retrieval lanes"
        )

    lane_contract_sha256s = tuple(
        _lane_contract_sha256(
            spec,
            lane,
            call,
            method_id=method_id,
            provider_contract_sha256=provider_contract_sha256,
            portfolio_contract_sha256=portfolio_contract_sha256,
        )
        for lane, call in zip(spec.lanes, plan.calls, strict=True)
    )
    return PreparedRoleDirectedCase(
        spec=spec,
        collection=collection,
        context=context,
        plan=plan,
        collection_sha256=source_collection_sha256(collection),
        plan_sha256=_plan_sha256(plan),
        profile_sha256=spec.roles.profile().sha256(),
        case_contract_sha256=_case_contract_sha256(
            spec,
            method_id=method_id,
            provider_contract_sha256=provider_contract_sha256,
            portfolio_contract_sha256=portfolio_contract_sha256,
            qualification_contract_sha256=qualification_contract_sha256,
        ),
        lane_contract_sha256s=lane_contract_sha256s,
    )


def load_frozen_cases(
    cohort: Literal["development", "unseen"] = "development",
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    *,
    expected_fixture_sha256: str = EXPECTED_FIXTURE_SHA256,
) -> tuple[
    str,
    RoleDirectedChallengeManifest,
    tuple[PreparedRoleDirectedCase, ...],
]:
    """Validate raw bytes before parsing or expanding either cohort."""

    raw = fixture_path.read_bytes()
    fixture_sha256 = _sha256_bytes(raw)
    if fixture_sha256 != expected_fixture_sha256:
        raise OpenAlexRoleDirectedPreflightError(
            "role-directed v7 fixture byte identity drifted: "
            f"expected {expected_fixture_sha256}, got {fixture_sha256}"
        )
    manifest = RoleDirectedChallengeManifest.model_validate_json(raw)
    specs = (
        manifest.development_cases
        if cohort == "development"
        else manifest.unseen_cases
    )
    provider_sha256 = manifest.provider_contract.sha256()
    portfolio_sha256 = manifest.portfolio_contract.sha256()
    qualification_sha256 = manifest.qualification_contract.sha256()
    return (
        fixture_sha256,
        manifest,
        tuple(
            build_case(
                spec,
                method_id=manifest.method_id,
                provider_contract_sha256=provider_sha256,
                portfolio_contract_sha256=portfolio_sha256,
                qualification_contract_sha256=qualification_sha256,
                result_limit=manifest.provider_contract.result_limit_per_request,
            )
            for spec in specs
        ),
    )


def dry_run(
    cohort: Literal["development", "unseen"] = "development",
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    *,
    expected_fixture_sha256: str = EXPECTED_FIXTURE_SHA256,
) -> dict[str, Any]:
    """Expose all frozen lane identities while constructing no live client."""

    fixture_sha256, manifest, cases = load_frozen_cases(
        cohort,
        fixture_path,
        expected_fixture_sha256=expected_fixture_sha256,
    )
    flattened_calls = sum(len(case.plan.calls) for case in cases)
    return {
        "mode": "openalex_role_directed_v7_dry_run",
        "cohort": cohort,
        "method_id": manifest.method_id,
        "production_connected": False,
        "report_workflow_connected": False,
        "planner_trigger_connected": False,
        "recovery_connected": False,
        "real_network_calls_performed": False,
        "real_model_calls_performed": False,
        "private_labels_opened": False,
        "human_qualification_performed": False,
        "live_provider_requests_authorized": False,
        "live_model_calls_authorized": False,
        "fixture_sha256": fixture_sha256,
        "case_count": len(cases),
        "maximum_search_request_count": flattened_calls,
        "maximum_provider_row_count": (
            flattened_calls * manifest.provider_contract.result_limit_per_request
        ),
        "maximum_model_call_count": 0,
        "provider_contract": manifest.provider_contract.model_dump(mode="json"),
        "portfolio_contract": manifest.portfolio_contract.model_dump(mode="json"),
        "qualification_contract": manifest.qualification_contract.model_dump(
            mode="json"
        ),
        "provider_contract_sha256": manifest.provider_contract.sha256(),
        "portfolio_contract_sha256": manifest.portfolio_contract.sha256(),
        "qualification_contract_sha256": (
            manifest.qualification_contract.sha256()
        ),
        "cases": [
            {
                "case_id": case.spec.case_id,
                "case_spec_sha256": case.spec.sha256(),
                "collection_sha256": case.collection_sha256,
                "plan_sha256": case.plan_sha256,
                "profile_sha256": case.profile_sha256,
                "case_contract_sha256": case.case_contract_sha256,
                "lanes": [
                    {
                        "lane_id": lane.lane_id,
                        "query": lane.query,
                        "target_role_ids": list(lane.target_role_ids),
                        "idempotency_key": call.idempotency_key,
                        "lane_contract_sha256": lane_sha256,
                        "result_limit": call.result_limit,
                    }
                    for lane, call, lane_sha256 in zip(
                        case.spec.lanes,
                        case.plan.calls,
                        case.lane_contract_sha256s,
                        strict=True,
                    )
                ],
            }
            for case in cases
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cohort",
        choices=("development", "unseen"),
        default="development",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    print(json.dumps(dry_run(args.cohort), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
