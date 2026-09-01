"""Zero-network preflight for the frozen role-slot consensus v6 challenge.

Y01-Y08 and Z01-Z08 were frozen before this implementation existed.  This
module verifies the raw fixture bytes before JSON parsing, expands deterministic
evidence-gap and judge-template identities, and exposes the exact contracts a
future separately authorised runner would need.  It imports no provider or
model adapter, so even the CLI cannot spend either budget.
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
    ValidatedGapPlan,
    build_gap_context,
    source_collection_sha256,
    validate_gap_plan,
)
from academic_agent.openalex_evidence_set import (
    EvidenceSetRoleProfile,
    EvidenceSetRoleSpec,
    EvidenceSetSelectionContract,
)
from academic_agent.source_pipeline import SourceCollection


_ROOT = Path(__file__).resolve().parent
DEFAULT_FIXTURE_PATH = _ROOT / "tests/fixtures/openalex_role_slot_v6_challenge.json"
EXPECTED_FIXTURE_SHA256 = (
    "f07c457f81fc5b198cb180874895410a4502b9fe3558c9e21c8b42a1f8240c85"
)
_DEVELOPMENT_ORDER = tuple(f"Y{index:02d}" for index in range(1, 9))
_UNSEEN_ORDER = tuple(f"Z{index:02d}" for index in range(1, 9))
_COLLECTED_AT = datetime(2026, 9, 1, tzinfo=UTC)
# The Sydney pre-registration happened while UTC was still 2026-08-31.  The
# EvidenceSource validator intentionally compares against the process-local
# calendar date, so freezing the later Sydney date makes the same bytes invalid
# on CI.  Keep the latest date that had elapsed in both environments instead.
_ACCESSED_DATE = date(2026, 8, 31)


class OpenAlexRoleSlotPreflightError(ValueError):
    """Raised before case expansion when the frozen v6 contract drifts."""


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


class RoleSlotProviderContract(BaseModel):
    """Anonymous one-request OpenAlex contract without a transport import."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["anonymous_openalex"] = "anonymous_openalex"
    requests_per_case: Literal[1] = 1
    result_limit: Literal[8] = 8
    require_abstract: Literal[True] = True
    allow_redirects: Literal[False] = False
    allow_retries: Literal[False] = False

    def sha256(self) -> str:
        return _model_sha256(self)


class RoleSlotJudgeContract(BaseModel):
    """Exact future quote-extraction boundary without a model client."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["qwen"] = "qwen"
    model: Literal["qwen3.5-plus"] = "qwen3.5-plus"
    passes_per_case: Literal[3] = 3
    candidate_orders: tuple[str, ...]
    temperature: Literal[0.0] = 0.0
    allow_retries: Literal[False] = False
    allow_repair: Literal[False] = False
    allow_fallback: Literal[False] = False
    minimum_verified_passes_per_role: Literal[2] = 2

    @model_validator(mode="after")
    def _validate_exact_pass_orders(self) -> "RoleSlotJudgeContract":
        if self.candidate_orders != (
            "provider_order",
            "reverse_provider_order",
            "candidate_sha256_order",
        ):
            raise ValueError("judge pass orders drifted from the frozen protocol")
        return self

    def sha256(self) -> str:
        return _model_sha256(self)


class FrozenRoleGroups(BaseModel):
    """Fixture-friendly role groups converted to the shared immutable profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    required: tuple[EvidenceSetRoleSpec, ...] = Field(min_length=2, max_length=4)
    scope: tuple[EvidenceSetRoleSpec, ...] = Field(min_length=1, max_length=4)
    supporting: tuple[EvidenceSetRoleSpec, ...] = Field(
        min_length=2,
        max_length=8,
    )

    @model_validator(mode="after")
    def _validate_unique_role_ids(self) -> "FrozenRoleGroups":
        role_ids = tuple(
            role.role_id
            for roles in (self.required, self.scope, self.supporting)
            for role in roles
        )
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("case role IDs must be unique")
        return self

    def profile(self) -> EvidenceSetRoleProfile:
        return EvidenceSetRoleProfile(
            required_roles=self.required,
            scope_roles=self.scope,
            supporting_roles=self.supporting,
        )


class RoleSlotCaseSpec(BaseModel):
    """One exact query and natural-language role profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[YZ]0[1-8]$")
    topic: str = Field(min_length=20, max_length=300)
    query: str = Field(min_length=20, max_length=500)
    roles: FrozenRoleGroups

    def sha256(self) -> str:
        return _model_sha256(self)


class RoleSlotChallengeManifest(BaseModel):
    """Complete raw-byte-frozen v6 development and unseen input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    method_id: Literal["openalex-candidate-local-role-slot-consensus-v6"]
    provider_contract: RoleSlotProviderContract
    judge_contract: RoleSlotJudgeContract
    selection_contract: EvidenceSetSelectionContract
    development_cases: tuple[RoleSlotCaseSpec, ...] = Field(
        min_length=8,
        max_length=8,
    )
    unseen_cases: tuple[RoleSlotCaseSpec, ...] = Field(min_length=8, max_length=8)

    @model_validator(mode="after")
    def _validate_cross_contracts(self) -> "RoleSlotChallengeManifest":
        if tuple(item.case_id for item in self.development_cases) != (
            _DEVELOPMENT_ORDER
        ):
            raise ValueError("development cases must remain Y01 through Y08")
        if tuple(item.case_id for item in self.unseen_cases) != _UNSEEN_ORDER:
            raise ValueError("unseen cases must remain Z01 through Z08")
        all_cases = (*self.development_cases, *self.unseen_cases)
        if len({item.topic for item in all_cases}) != len(all_cases):
            raise ValueError("topic strings must be unique across both cohorts")
        if len({item.query for item in all_cases}) != len(all_cases):
            raise ValueError("queries must be unique across both cohorts")
        if self.selection_contract.maximum_selected_sources_per_case != 3:
            raise ValueError("v6 selected-source ceiling must remain three")
        for case in all_cases:
            profile = case.roles.profile()
            if self.selection_contract.minimum_scope_roles > len(
                profile.scope_roles
            ):
                raise ValueError(f"{case.case_id}: impossible scope threshold")
            if self.selection_contract.minimum_supporting_roles > len(
                profile.supporting_roles
            ):
                raise ValueError(f"{case.case_id}: impossible supporting threshold")
        return self


@dataclass(frozen=True)
class PreparedRoleSlotCase:
    """Deterministic identities for a future separately locked runner."""

    spec: RoleSlotCaseSpec
    collection: SourceCollection
    context: GapContext
    plan: ValidatedGapPlan
    collection_sha256: str
    plan_sha256: str
    profile_sha256: str
    case_contract_sha256: str
    judge_request_template_sha256s: tuple[str, str, str]


def _plan_sha256(plan: ValidatedGapPlan) -> str:
    return _sha256_bytes(plan.model_dump_json(exclude_none=False).encode("utf-8"))


def _case_contract_sha256(
    spec: RoleSlotCaseSpec,
    *,
    method_id: str,
    provider_contract_sha256: str,
    judge_contract_sha256: str,
    selection_contract_sha256: str,
) -> str:
    return _sha256_json(
        {
            "method_id": method_id,
            "spec": spec.model_dump(mode="json"),
            "provider_contract_sha256": provider_contract_sha256,
            "judge_contract_sha256": judge_contract_sha256,
            "selection_contract_sha256": selection_contract_sha256,
        }
    )


def _judge_request_template_sha256s(
    spec: RoleSlotCaseSpec,
    *,
    method_id: str,
    judge_contract: RoleSlotJudgeContract,
) -> tuple[str, str, str]:
    profile_sha256 = spec.roles.profile().sha256()
    return tuple(
        _sha256_json(
            {
                "method_id": method_id,
                "case_id": spec.case_id,
                "topic": spec.topic,
                "query": spec.query,
                "profile_sha256": profile_sha256,
                "pass_number": pass_number,
                "candidate_order": candidate_order,
                "judge_contract_sha256": judge_contract.sha256(),
            }
        )
        for pass_number, candidate_order in enumerate(
            judge_contract.candidate_orders,
            start=1,
        )
    )


def _seed_source(spec: RoleSlotCaseSpec) -> EvidenceSource:
    """Create a valid gap context without pretending retrieval already ran."""

    return EvidenceSource(
        source_id="A1",
        title=f"{spec.topic}: frozen role-slot baseline context",
        url=f"https://doi.org/10.5555/openalex-role-slot-v6.{spec.case_id.casefold()}",
        publisher="Frozen Role-slot v6 Fixture",
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
    spec: RoleSlotCaseSpec,
    *,
    method_id: str,
    provider_contract_sha256: str,
    judge_contract: RoleSlotJudgeContract,
    selection_contract_sha256: str,
) -> PreparedRoleSlotCase:
    """Expand one case without network, clocks, randomness, or model calls."""

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
        failed_domains={"academic": "frozen role-slot v6 retrieval challenge"},
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
        raise OpenAlexRoleSlotPreflightError(
            f"{spec.case_id}: frozen academic gap signal was not produced"
        )
    plan = validate_gap_plan(
        context,
        GapPlanProposal(
            decision="search",
            rationale=(
                "The frozen role-slot case authorizes one read-only academic "
                "request for its explicit evidence gap."
            ),
            calls=(
                GapSearchIntent(
                    tool="academic_search",
                    query=spec.query,
                    trigger_ids=(trigger.signal_id,),
                    result_limit=8,
                ),
            ),
        ),
    )
    return PreparedRoleSlotCase(
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
            judge_contract_sha256=judge_contract.sha256(),
            selection_contract_sha256=selection_contract_sha256,
        ),
        judge_request_template_sha256s=_judge_request_template_sha256s(
            spec,
            method_id=method_id,
            judge_contract=judge_contract,
        ),
    )


def load_frozen_cases(
    cohort: Literal["development", "unseen"] = "development",
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    *,
    expected_fixture_sha256: str = EXPECTED_FIXTURE_SHA256,
) -> tuple[
    str,
    RoleSlotChallengeManifest,
    tuple[PreparedRoleSlotCase, ...],
]:
    """Validate raw bytes before parsing or expanding either cohort."""

    raw = fixture_path.read_bytes()
    fixture_sha256 = _sha256_bytes(raw)
    if fixture_sha256 != expected_fixture_sha256:
        raise OpenAlexRoleSlotPreflightError(
            "role-slot v6 fixture byte identity drifted: "
            f"expected {expected_fixture_sha256}, got {fixture_sha256}"
        )
    manifest = RoleSlotChallengeManifest.model_validate_json(raw)
    specs = (
        manifest.development_cases
        if cohort == "development"
        else manifest.unseen_cases
    )
    provider_sha256 = manifest.provider_contract.sha256()
    selection_sha256 = manifest.selection_contract.sha256()
    return (
        fixture_sha256,
        manifest,
        tuple(
            build_case(
                spec,
                method_id=manifest.method_id,
                provider_contract_sha256=provider_sha256,
                judge_contract=manifest.judge_contract,
                selection_contract_sha256=selection_sha256,
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
    """Expose frozen identities while constructing no provider or model client."""

    fixture_sha256, manifest, cases = load_frozen_cases(
        cohort,
        fixture_path,
        expected_fixture_sha256=expected_fixture_sha256,
    )
    return {
        "mode": "openalex_role_slot_v6_dry_run",
        "cohort": cohort,
        "method_id": manifest.method_id,
        "production_connected": False,
        "report_workflow_connected": False,
        "planner_trigger_connected": False,
        "real_network_calls_performed": False,
        "real_model_calls_performed": False,
        "private_labels_opened": False,
        "live_provider_requests_authorized": False,
        "live_model_calls_authorized": False,
        "fixture_sha256": fixture_sha256,
        "case_count": len(cases),
        "maximum_search_request_count": len(cases),
        "maximum_judge_call_count": (
            len(cases) * manifest.judge_contract.passes_per_case
        ),
        "provider_contract": manifest.provider_contract.model_dump(mode="json"),
        "judge_contract": manifest.judge_contract.model_dump(mode="json"),
        "selection_contract": manifest.selection_contract.model_dump(mode="json"),
        "provider_contract_sha256": manifest.provider_contract.sha256(),
        "judge_contract_sha256": manifest.judge_contract.sha256(),
        "selection_contract_sha256": manifest.selection_contract.sha256(),
        "cases": [
            {
                "case_id": case.spec.case_id,
                "case_spec_sha256": case.spec.sha256(),
                "collection_sha256": case.collection_sha256,
                "plan_sha256": case.plan_sha256,
                "profile_sha256": case.profile_sha256,
                "case_contract_sha256": case.case_contract_sha256,
                "provider_idempotency_key": case.plan.calls[0].idempotency_key,
                "judge_request_template_sha256s": (
                    case.judge_request_template_sha256s
                ),
                "result_limit": case.plan.calls[0].result_limit,
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
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE_PATH)
    return parser


def main() -> int:
    args = _parser().parse_args()
    print(
        json.dumps(
            dry_run(args.cohort, args.fixture),
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
