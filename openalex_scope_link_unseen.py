"""Zero-network preflight for the frozen OpenAlex scope-link v4 challenge.

W01-W08 were authored after the claim-scope v3 human review but before any
provider response for these topics.  This module locks the fixture bytes,
expands deterministic source collections and one-call plans, and exposes the
identities a separately authorized live runner would need.  It imports no
provider adapter or transport, so this preflight cannot spend an OpenAlex
budget or alter a production report.
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
from academic_agent.openalex_scope_link import OpenAlexScopeLinkProfile
from academic_agent.source_pipeline import SourceCollection


_ROOT = Path(__file__).resolve().parent
DEFAULT_FIXTURE_PATH = (
    _ROOT / "tests/fixtures/openalex_scope_link_v4_challenge.json"
)
EXPECTED_FIXTURE_SHA256 = (
    "f4267c6a79c0bb8a685664de5086e4cfff59ebac1b352cbb56c2277957a55cc3"
)
_CASE_ORDER = tuple(f"W{index:02d}" for index in range(1, 9))
_COLLECTED_AT = datetime(2026, 8, 27, tzinfo=UTC)
_ACCESSED_DATE = date(2026, 8, 27)


class OpenAlexScopeLinkPreflightError(ValueError):
    """Raised before case expansion when the frozen challenge drifts."""


class ScopeLinkRequestContract(BaseModel):
    """Provider request shape frozen without constructing a transport."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    result_limit: Literal[8] = 8
    filter: Literal["has_abstract:true"] = "has_abstract:true"
    aboutness_fields: tuple[Literal["topics", "keywords"], ...] = (
        "topics",
        "keywords",
    )
    redirects: Literal[False] = False
    internal_retries: Literal[False] = False

    @model_validator(mode="after")
    def _validate_aboutness_order(self) -> "ScopeLinkRequestContract":
        if self.aboutness_fields != ("topics", "keywords"):
            raise ValueError("aboutness fields must remain topics then keywords")
        return self


class ScopeLinkDevelopmentObservation(BaseModel):
    """Closed v3 result; retained as history, never as v4 tuning labels."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_document: Literal[
        "docs/results-2026-08-27-openalex-claim-scope-v3-review.md"
    ]
    reviewed_candidate_count: Literal[13] = 13
    relevant_candidate_count: Literal[12] = 12
    wrong_source_count: Literal[1] = 1
    wrong_source_rate: Literal[0.07692307692307693] = 0.07692307692307693
    accepted_case_count: Literal[7] = 7
    novel_relevant_case_count: Literal[7] = 7
    source_truth_state: Literal["complete_fail"] = "complete_fail"
    reuse_for_v4_tuning: Literal[False] = False


class ScopeLinkSourceValueGates(BaseModel):
    """Human-review gates that a future live result cannot rewrite."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    accepted_case_count_min: Literal[6] = 6
    novel_relevant_case_count_min: Literal[6] = 6
    wrong_source_rate_max: Literal[0.05] = 0.05
    all_attempted_sources_reviewed: Literal[True] = True
    substantive_generative_ai_allowed: Literal[False] = False


class ScopeLinkCaseSpec(BaseModel):
    """One unseen query and its role-structured authorization profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^W0[1-8]$")
    topic: str = Field(min_length=20, max_length=300)
    query: str = Field(min_length=20, max_length=500)
    result_limit: Literal[8] = 8
    profile: OpenAlexScopeLinkProfile


class ScopeLinkChallengeManifest(BaseModel):
    """Complete byte-frozen v4 preflight input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["openalex_scope_link_v4_unseen_challenge"]
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    maximum_live_requests: Literal[8] = 8
    request_contract: ScopeLinkRequestContract
    development_observation: ScopeLinkDevelopmentObservation
    challenge_cases: tuple[ScopeLinkCaseSpec, ...] = Field(
        min_length=8,
        max_length=8,
    )
    source_value_gates: ScopeLinkSourceValueGates

    @model_validator(mode="after")
    def _validate_case_order(self) -> "ScopeLinkChallengeManifest":
        observed = tuple(case.case_id for case in self.challenge_cases)
        if observed != _CASE_ORDER:
            raise ValueError("scope-link cases must remain ordered W01 through W08")
        if any(
            case.result_limit != self.request_contract.result_limit
            for case in self.challenge_cases
        ):
            raise ValueError("case result limits drifted from the request contract")
        return self


@dataclass(frozen=True)
class PreparedScopeLinkCase:
    """Expanded deterministic identity for a later separately locked runner."""

    spec: ScopeLinkCaseSpec
    collection: SourceCollection
    context: GapContext
    plan: ValidatedGapPlan
    collection_sha256: str
    plan_sha256: str
    profile_sha256: str


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _plan_sha256(plan: ValidatedGapPlan) -> str:
    return _sha256_bytes(plan.model_dump_json(exclude_none=False).encode("utf-8"))


def _seed_source(spec: ScopeLinkCaseSpec) -> EvidenceSource:
    """Create valid context without pretending a provider result exists."""

    return EvidenceSource(
        source_id="A1",
        title=f"{spec.topic}: frozen scope-link baseline context",
        url=(
            "https://doi.org/10.5555/"
            f"openalex-scope-link-v4.{spec.case_id.casefold()}"
        ),
        publisher="Frozen Scope-link v4 Fixture",
        accessed_date=_ACCESSED_DATE,
        source_type="academic_paper",
        evidence_summary=(
            f"This synthetic baseline records the question {spec.topic}. "
            "It contains no provider row and does not satisfy the explicit "
            "academic retrieval gap used by this disconnected study."
        ),
        summary_source="abstract",
    )


def build_case(spec: ScopeLinkCaseSpec) -> PreparedScopeLinkCase:
    """Expand one recipe without network, clocks, randomness or model calls."""

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
        failed_domains={"academic": "frozen scope-link v4 retrieval challenge"},
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
        raise OpenAlexScopeLinkPreflightError(
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
    return PreparedScopeLinkCase(
        spec=spec,
        collection=collection,
        context=context,
        plan=plan,
        collection_sha256=source_collection_sha256(collection),
        plan_sha256=_plan_sha256(plan),
        profile_sha256=spec.profile.sha256(),
    )


def load_frozen_cases(
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    *,
    expected_fixture_sha256: str = EXPECTED_FIXTURE_SHA256,
) -> tuple[
    str,
    ScopeLinkChallengeManifest,
    tuple[PreparedScopeLinkCase, ...],
]:
    """Validate raw bytes before parsing or expanding any case."""

    raw = fixture_path.read_bytes()
    fixture_sha256 = _sha256_bytes(raw)
    if fixture_sha256 != expected_fixture_sha256:
        raise OpenAlexScopeLinkPreflightError(
            "scope-link v4 fixture byte identity drifted: "
            f"expected {expected_fixture_sha256}, got {fixture_sha256}"
        )
    manifest = ScopeLinkChallengeManifest.model_validate_json(raw)
    return (
        fixture_sha256,
        manifest,
        tuple(build_case(spec) for spec in manifest.challenge_cases),
    )


def dry_run(
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    *,
    expected_fixture_sha256: str = EXPECTED_FIXTURE_SHA256,
) -> dict[str, Any]:
    """Expose complete frozen identities while opening zero sockets."""

    fixture_sha256, manifest, cases = load_frozen_cases(
        fixture_path,
        expected_fixture_sha256=expected_fixture_sha256,
    )
    return {
        "mode": "openalex_scope_link_v4_unseen_dry_run",
        "production_connected": False,
        "report_workflow_connected": False,
        "real_network_calls_performed": False,
        "live_provider_requests_authorized": False,
        "fixture_sha256": fixture_sha256,
        "case_count": len(cases),
        "maximum_request_count": manifest.maximum_live_requests,
        "request_contract": manifest.request_contract.model_dump(mode="json"),
        "development_observation": manifest.development_observation.model_dump(
            mode="json"
        ),
        "source_value_gates": manifest.source_value_gates.model_dump(mode="json"),
        "cases": [
            {
                "case_id": case.spec.case_id,
                "collection_sha256": case.collection_sha256,
                "plan_sha256": case.plan_sha256,
                "profile_sha256": case.profile_sha256,
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
