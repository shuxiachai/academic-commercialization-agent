"""Zero-network preflight for the frozen OpenAlex evidence-set v5 challenge.

X01-X08 were frozen after the scope-link v4 diagnostic and before v5 code,
model responses, or OpenAlex results existed.  This module validates the raw
fixture bytes first, expands deterministic evidence-gap identities, and exposes
the contracts a separately authorized runner would need.  It imports neither a
provider adapter nor a model client, so dry-run cannot spend either budget.
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
    EvidenceSetSelectionContract,
)
from academic_agent.source_pipeline import SourceCollection


_ROOT = Path(__file__).resolve().parent
DEFAULT_FIXTURE_PATH = (
    _ROOT / "tests/fixtures/openalex_evidence_set_v5_challenge.json"
)
EXPECTED_FIXTURE_SHA256 = (
    "f0c4cc86593f54a36040cf1b7d95b42207726b9323172b7dccae2df47ca5a521"
)
_CASE_ORDER = tuple(f"X{index:02d}" for index in range(1, 9))
_DEVELOPMENT_CASE_ORDER = tuple(f"W{index:02d}" for index in range(1, 9))
_COLLECTED_AT = datetime(2026, 8, 29, tzinfo=UTC)
_ACCESSED_DATE = date(2026, 8, 29)


class OpenAlexEvidenceSetPreflightError(ValueError):
    """Raised before case expansion when the frozen v5 contract drifts."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _model_sha256(value: BaseModel) -> str:
    return _sha256_bytes(
        value.model_dump_json(exclude_none=False).encode("utf-8")
    )


class EvidenceSetRequestContract(BaseModel):
    """One-request OpenAlex shape frozen without constructing a transport."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    result_limit: Literal[8] = 8
    filter: Literal["has_abstract:true"] = "has_abstract:true"
    aboutness_fields: tuple[Literal["topics", "keywords"], ...]
    aboutness_admissible_for_selection: Literal[False] = False
    redirects: Literal[False] = False
    internal_retries: Literal[False] = False
    supplementary_fetches: Literal[False] = False

    @model_validator(mode="after")
    def _validate_aboutness_order(self) -> "EvidenceSetRequestContract":
        if self.aboutness_fields != ("topics", "keywords"):
            raise ValueError("aboutness fields must remain topics then keywords")
        return self

    def sha256(self) -> str:
        return _model_sha256(self)


class EvidenceSetJudgeContract(BaseModel):
    """Exact future model boundary frozen without importing a model SDK."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["deepseek"] = "deepseek"
    requested_model: Literal["deepseek-chat"] = "deepseek-chat"
    api_base: Literal["https://api.deepseek.com"] = "https://api.deepseek.com"
    passes_per_case: Literal[2] = 2
    first_pass_order: Literal["provider_order"] = "provider_order"
    second_pass_order: Literal["reverse_provider_order"] = "reverse_provider_order"
    temperature: Literal[0.0] = 0.0
    allowed_candidate_fields: tuple[str, ...]
    hidden_fields: tuple[str, ...]
    candidate_dispositions: tuple[str, ...]
    consensus_rule: Literal["both_passes_keep_with_same_role_ids"]
    quote_rule: Literal[
        "every_role_requires_a_verbatim_title_or_abstract_span_in_both_passes"
    ]
    disagreement_rule: Literal["abstain"] = "abstain"
    malformed_or_unverifiable_rule: Literal["abstain"] = "abstain"
    maximum_selected_sources_per_case: Literal[3] = 3
    selection_rule: Literal[
        "deterministic_minimum_set_cover_then_provider_index_then_candidate_sha256"
    ]

    @model_validator(mode="after")
    def _validate_exact_sequences(self) -> "EvidenceSetJudgeContract":
        if self.allowed_candidate_fields != (
            "candidate_sha256",
            "title",
            "abstract",
        ):
            raise ValueError("judge candidate fields drifted")
        if self.hidden_fields != (
            "provider_topics",
            "provider_keywords",
            "provider_scores",
            "v4_action",
            "v4_reasons",
            "human_labels",
            "human_notes",
        ):
            raise ValueError("judge hidden-field contract drifted")
        if self.candidate_dispositions != ("KEEP", "ABSTAIN"):
            raise ValueError("judge dispositions must remain KEEP then ABSTAIN")
        return self

    def sha256(self) -> str:
        return _model_sha256(self)


class EvidenceSetDevelopmentObservation(BaseModel):
    """Consumed v4 diagnostic evidence available only for development."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_document: Literal[
        "docs/results-2026-08-29-openalex-scope-link-v4-abstention-diagnostic-review.md"
    ]
    case_ids: tuple[str, ...]
    candidate_count: Literal[64] = 64
    direct_relevant_count: Literal[28] = 28
    retrieval_noise_count: Literal[36] = 36
    human_semantic_link_count: Literal[5] = 5
    v4_semantic_link_miss_count: Literal[4] = 4
    relevant_case_count: Literal[8] = 8
    novel_relevant_case_count: Literal[8] = 8
    reuse_for_v5_development: Literal[True] = True
    reuse_for_v5_validation: Literal[False] = False

    @model_validator(mode="after")
    def _validate_consumed_case_order(self) -> "EvidenceSetDevelopmentObservation":
        if self.case_ids != _DEVELOPMENT_CASE_ORDER:
            raise ValueError("development cases must remain W01 through W08")
        return self


class EvidenceSetDevelopmentGates(BaseModel):
    """Label-blind qualification gates before an unseen request is eligible."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_disposition_agreement_min: Literal[0.9] = 0.9
    semantic_link_rows_retained_min: Literal[4] = 4
    relevant_novel_case_count_min: Literal[6] = 6
    selected_directly_irrelevant_count_max: Literal[1] = 1
    all_decisions_persisted: Literal[True] = True


class EvidenceSetUnseenGates(BaseModel):
    """Conjunctive human-value gates for a separately authorized live run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_case_count_min: Literal[6] = 6
    relevant_novel_case_count_min: Literal[6] = 6
    human_set_coverage_case_count_min: Literal[6] = 6
    selected_wrong_source_rate_max: Literal[0.05] = 0.05
    unsupported_selected_role_rate_max: Literal[0.05] = 0.05
    candidate_disposition_agreement_min: Literal[0.9] = 0.9
    all_provider_rows_reviewed: Literal[True] = True
    all_attempted_sources_opened: Literal[True] = True
    substantive_generative_ai_allowed: Literal[False] = False


class EvidenceSetCaseSpec(BaseModel):
    """One exact unseen query and its natural-language evidence roles."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^X0[1-8]$")
    topic: str = Field(min_length=20, max_length=300)
    query: str = Field(min_length=20, max_length=500)
    result_limit: Literal[8] = 8
    role_profile: EvidenceSetRoleProfile


class EvidenceSetChallengeManifest(BaseModel):
    """Complete raw-byte-frozen v5 preflight input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["openalex_quote_grounded_evidence_set_v5_unseen_challenge"]
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    planner_trigger_connected: Literal[False] = False
    maximum_live_search_requests: Literal[8] = 8
    maximum_live_judge_calls: Literal[16] = 16
    request_contract: EvidenceSetRequestContract
    semantic_judge_contract: EvidenceSetJudgeContract
    development_observation: EvidenceSetDevelopmentObservation
    challenge_cases: tuple[EvidenceSetCaseSpec, ...] = Field(
        min_length=8,
        max_length=8,
    )
    collection_coverage_contract: EvidenceSetSelectionContract
    development_qualification_gates: EvidenceSetDevelopmentGates
    unseen_value_gates: EvidenceSetUnseenGates

    @model_validator(mode="after")
    def _validate_cross_contracts(self) -> "EvidenceSetChallengeManifest":
        observed = tuple(case.case_id for case in self.challenge_cases)
        if observed != _CASE_ORDER:
            raise ValueError("evidence-set cases must remain ordered X01 through X08")
        if any(
            case.result_limit != self.request_contract.result_limit
            for case in self.challenge_cases
        ):
            raise ValueError("case result limits drifted from the request contract")
        if self.maximum_live_search_requests != len(self.challenge_cases):
            raise ValueError("search request cap must remain one per case")
        expected_judge_calls = (
            len(self.challenge_cases) * self.semantic_judge_contract.passes_per_case
        )
        if self.maximum_live_judge_calls != expected_judge_calls:
            raise ValueError("judge call cap must remain two per case")
        if (
            self.collection_coverage_contract.maximum_selected_sources_per_case
            != self.semantic_judge_contract.maximum_selected_sources_per_case
        ):
            raise ValueError("judge and set-cover source ceilings drifted")
        for case in self.challenge_cases:
            if self.collection_coverage_contract.minimum_scope_roles > len(
                case.role_profile.scope_roles
            ):
                raise ValueError(f"{case.case_id}: impossible scope-role threshold")
            if self.collection_coverage_contract.minimum_supporting_roles > len(
                case.role_profile.supporting_roles
            ):
                raise ValueError(
                    f"{case.case_id}: impossible supporting-role threshold"
                )
        return self


@dataclass(frozen=True)
class PreparedEvidenceSetCase:
    """Deterministic identities for a future separately locked live runner."""

    spec: EvidenceSetCaseSpec
    collection: SourceCollection
    context: GapContext
    plan: ValidatedGapPlan
    collection_sha256: str
    plan_sha256: str
    profile_sha256: str
    case_contract_sha256: str


def _plan_sha256(plan: ValidatedGapPlan) -> str:
    return _sha256_bytes(plan.model_dump_json(exclude_none=False).encode("utf-8"))


def _case_contract_sha256(
    spec: EvidenceSetCaseSpec,
    *,
    request_contract_sha256: str,
    judge_contract_sha256: str,
    selection_contract_sha256: str,
) -> str:
    payload = {
        "spec": spec.model_dump(mode="json"),
        "request_contract_sha256": request_contract_sha256,
        "judge_contract_sha256": judge_contract_sha256,
        "selection_contract_sha256": selection_contract_sha256,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256_bytes(canonical.encode("utf-8"))


def _seed_source(spec: EvidenceSetCaseSpec) -> EvidenceSource:
    """Create valid gap context without pretending provider evidence exists."""

    return EvidenceSource(
        source_id="A1",
        title=f"{spec.topic}: frozen evidence-set baseline context",
        url=(
            "https://doi.org/10.5555/"
            f"openalex-evidence-set-v5.{spec.case_id.casefold()}"
        ),
        publisher="Frozen Evidence-set v5 Fixture",
        accessed_date=_ACCESSED_DATE,
        source_type="academic_paper",
        evidence_summary=(
            f"This synthetic baseline records the question {spec.topic}. "
            "It contains no provider row and does not satisfy the explicit "
            "academic retrieval gap used by this disconnected study."
        ),
        summary_source="abstract",
    )


def build_case(
    spec: EvidenceSetCaseSpec,
    *,
    request_contract_sha256: str,
    judge_contract_sha256: str,
    selection_contract_sha256: str,
) -> PreparedEvidenceSetCase:
    """Expand one X-case without network, clocks, randomness or model calls."""

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
        failed_domains={"academic": "frozen evidence-set v5 retrieval challenge"},
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
        raise OpenAlexEvidenceSetPreflightError(
            f"{spec.case_id}: frozen academic gap signal was not produced"
        )
    plan = validate_gap_plan(
        context,
        GapPlanProposal(
            decision="search",
            rationale=(
                "The frozen unseen case authorizes one read-only academic "
                "request for its explicit evidence gap."
            ),
            calls=(
                GapSearchIntent(
                    tool="academic_search",
                    query=spec.query,
                    trigger_ids=(trigger.signal_id,),
                    result_limit=spec.result_limit,
                ),
            ),
        ),
    )
    return PreparedEvidenceSetCase(
        spec=spec,
        collection=collection,
        context=context,
        plan=plan,
        collection_sha256=source_collection_sha256(collection),
        plan_sha256=_plan_sha256(plan),
        profile_sha256=spec.role_profile.sha256(),
        case_contract_sha256=_case_contract_sha256(
            spec,
            request_contract_sha256=request_contract_sha256,
            judge_contract_sha256=judge_contract_sha256,
            selection_contract_sha256=selection_contract_sha256,
        ),
    )


def load_frozen_cases(
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    *,
    expected_fixture_sha256: str = EXPECTED_FIXTURE_SHA256,
) -> tuple[
    str,
    EvidenceSetChallengeManifest,
    tuple[PreparedEvidenceSetCase, ...],
]:
    """Validate raw bytes before parsing or expanding any X-case."""

    raw = fixture_path.read_bytes()
    fixture_sha256 = _sha256_bytes(raw)
    if fixture_sha256 != expected_fixture_sha256:
        raise OpenAlexEvidenceSetPreflightError(
            "evidence-set v5 fixture byte identity drifted: "
            f"expected {expected_fixture_sha256}, got {fixture_sha256}"
        )
    manifest = EvidenceSetChallengeManifest.model_validate_json(raw)
    request_sha256 = manifest.request_contract.sha256()
    judge_sha256 = manifest.semantic_judge_contract.sha256()
    selection_sha256 = manifest.collection_coverage_contract.sha256()
    return (
        fixture_sha256,
        manifest,
        tuple(
            build_case(
                spec,
                request_contract_sha256=request_sha256,
                judge_contract_sha256=judge_sha256,
                selection_contract_sha256=selection_sha256,
            )
            for spec in manifest.challenge_cases
        ),
    )


def dry_run(
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    *,
    expected_fixture_sha256: str = EXPECTED_FIXTURE_SHA256,
) -> dict[str, Any]:
    """Expose every frozen identity while opening zero sockets or model clients."""

    fixture_sha256, manifest, cases = load_frozen_cases(
        fixture_path,
        expected_fixture_sha256=expected_fixture_sha256,
    )
    return {
        "mode": "openalex_evidence_set_v5_unseen_dry_run",
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
        "maximum_search_request_count": manifest.maximum_live_search_requests,
        "maximum_judge_call_count": manifest.maximum_live_judge_calls,
        "request_contract": manifest.request_contract.model_dump(mode="json"),
        "semantic_judge_contract": manifest.semantic_judge_contract.model_dump(
            mode="json"
        ),
        "development_observation": manifest.development_observation.model_dump(
            mode="json"
        ),
        "collection_coverage_contract": (
            manifest.collection_coverage_contract.model_dump(mode="json")
        ),
        "development_qualification_gates": (
            manifest.development_qualification_gates.model_dump(mode="json")
        ),
        "unseen_value_gates": manifest.unseen_value_gates.model_dump(mode="json"),
        "request_contract_sha256": manifest.request_contract.sha256(),
        "judge_contract_sha256": manifest.semantic_judge_contract.sha256(),
        "selection_contract_sha256": (
            manifest.collection_coverage_contract.sha256()
        ),
        "cases": [
            {
                "case_id": case.spec.case_id,
                "collection_sha256": case.collection_sha256,
                "plan_sha256": case.plan_sha256,
                "profile_sha256": case.profile_sha256,
                "case_contract_sha256": case.case_contract_sha256,
                "idempotency_key": case.plan.calls[0].idempotency_key,
                "result_limit": case.plan.calls[0].result_limit,
            }
            for case in cases
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE_PATH)
    return parser


def main() -> int:
    args = _parser().parse_args()
    print(json.dumps(dry_run(args.fixture), ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
