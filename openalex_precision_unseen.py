"""Zero-network preflight for the frozen OpenAlex precision-v2 challenge.

The eight U01-U08 cases were frozen before any provider result was observed.
This module expands those recipes into deterministic source collections,
evidence-gap contexts, validated one-call plans, and trusted precision
profiles.  It intentionally imports no provider adapter and exposes no live
execution switch.  A separate runner may consume these identities only after
its own implementation lock and explicit live authorization have passed.
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
from academic_agent.openalex_precision import AcademicPrecisionProfile
from academic_agent.source_pipeline import SourceCollection


_ROOT = Path(__file__).resolve().parent
DEFAULT_FIXTURE_PATH = (
    _ROOT / "tests/fixtures/openalex_precision_v2_challenge.json"
)
DEFAULT_CORRECTION_PATH = (
    _ROOT / "tests/fixtures/openalex_precision_v2_unseen_correction.json"
)
EXPECTED_FIXTURE_SHA256 = (
    "355782bbe40278f44cb76f650d57fbb13be6b9097bfecb6e101815a24c47ea8b"
)
EXPECTED_CORRECTION_SHA256 = "ac4a0cdfdbd18c688cba2e7edf340b0089f1402a5c549d56804dcab0231bfd84"
_CASE_ORDER = tuple(f"U{index:02d}" for index in range(1, 9))
_COLLECTED_AT = datetime(2026, 8, 27, tzinfo=UTC)
_ACCESSED_DATE = date(2026, 8, 27)


class OpenAlexPrecisionUnseenError(ValueError):
    """Raised before provider construction when frozen unseen input drifts."""


class UnseenSourceValueGates(BaseModel):
    """Human-review gates frozen before the unseen provider observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    accepted_case_count_min: Literal[6] = 6
    novel_relevant_case_count_min: Literal[6] = 6
    wrong_source_rate_max: Literal[0.05] = 0.05
    all_attempted_sources_reviewed: Literal[True] = True
    substantive_generative_ai_allowed: Literal[False] = False


class UnseenChallengeCaseSpec(BaseModel):
    """One byte-frozen query paired with its trusted conjunctive profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^U0[1-8]$")
    topic: str = Field(min_length=20, max_length=300)
    query: str = Field(min_length=20, max_length=500)
    result_limit: Literal[5] = 5
    profile: AcademicPrecisionProfile


class UnseenProfileCorrection(BaseModel):
    """One exact, pre-provider repair to an invalid frozen phrase list."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^U0[1-8]$")
    group_kind: Literal["supporting_groups"]
    group_id: str
    expected_phrases: tuple[str, ...] = Field(min_length=2, max_length=8)
    replacement_phrases: tuple[str, ...] = Field(min_length=1, max_length=8)
    reason: str = Field(min_length=40, max_length=500)


class UnseenCorrectionLock(BaseModel):
    """Separate lock preserving the original historical fixture unchanged."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["openalex_precision_v2_unseen_correction_lock"]
    production_connected: Literal[False] = False
    source_fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    maximum_live_requests: Literal[8] = 8
    corrections: tuple[UnseenProfileCorrection, ...] = Field(
        min_length=1,
        max_length=1,
    )


class UnseenChallengeManifest(BaseModel):
    """Complete fixture shape; raw-byte identity remains the primary lock."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["openalex_precision_v2_unseen_challenge"]
    production_connected: Literal[False] = False
    maximum_live_requests: Literal[8] = 8
    # Development fields remain present so nobody can silently publish a
    # challenge-only derivative that drops the lineage which qualified v2.
    # Their deeper schema is owned by openalex_precision_audit.py; the raw hash
    # makes any byte change fail before these opaque values are used.
    development_source: dict[str, Any]
    development_profiles: tuple[dict[str, Any], ...] = Field(
        min_length=4,
        max_length=4,
    )
    challenge_cases: tuple[dict[str, Any], ...] = Field(
        min_length=8,
        max_length=8,
    )
    source_value_gates: UnseenSourceValueGates

    @model_validator(mode="after")
    def _validate_case_order(self) -> "UnseenChallengeManifest":
        observed = tuple(str(case.get("case_id", "")) for case in self.challenge_cases)
        if observed != _CASE_ORDER:
            raise ValueError("unseen cases must remain ordered U01 through U08")
        return self


@dataclass(frozen=True)
class PreparedUnseenCase:
    """Expanded deterministic input consumed by a separately locked runner."""

    spec: UnseenChallengeCaseSpec
    collection: SourceCollection
    context: GapContext
    plan: ValidatedGapPlan
    collection_sha256: str
    plan_sha256: str
    profile_sha256: str


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _plan_sha256(plan: ValidatedGapPlan) -> str:
    return _sha256_bytes(
        plan.model_dump_json(exclude_none=False).encode("utf-8")
    )


def _seed_source(spec: UnseenChallengeCaseSpec) -> EvidenceSource:
    """Keep the collection valid without pretending it contains the answer.

    Novelty in the later source-value study is measured against this disclosed
    synthetic baseline, not against an undisclosed report or a claim of prior
    literature coverage.  That narrow baseline can establish retrieval
    increment only; it cannot establish report improvement.
    """

    return EvidenceSource(
        source_id="A1",
        title=f"{spec.topic}: frozen unseen baseline context",
        url=(
            "https://doi.org/10.5555/"
            f"openalex-precision-v2.{spec.case_id.casefold()}"
        ),
        publisher="Frozen Precision-v2 Fixture",
        accessed_date=_ACCESSED_DATE,
        source_type="academic_paper",
        evidence_summary=(
            f"This synthetic baseline records the question {spec.topic}. "
            "It contains no provider result and does not satisfy the explicit "
            "academic retrieval gap used by this disconnected study."
        ),
        summary_source="abstract",
    )


def build_case(spec: UnseenChallengeCaseSpec) -> PreparedUnseenCase:
    """Expand one frozen recipe without clocks, randomness, models or I/O."""

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
        failed_domains={
            "academic": "frozen precision-v2 unseen retrieval challenge"
        },
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
        raise OpenAlexPrecisionUnseenError(
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
    return PreparedUnseenCase(
        spec=spec,
        collection=collection,
        context=context,
        plan=plan,
        collection_sha256=source_collection_sha256(collection),
        plan_sha256=_plan_sha256(plan),
        profile_sha256=spec.profile.sha256(),
    )



def _apply_corrections(
    raw_cases: tuple[dict[str, Any], ...],
    corrections: tuple[UnseenProfileCorrection, ...],
) -> tuple[UnseenChallengeCaseSpec, ...]:
    """Apply only the separately byte-locked exact phrase replacement.

    General duplicate cleanup here would let future fixture defects disappear
    silently. Requiring complete before-and-after tuples keeps the one known
    correction narrow and impossible to retarget by changing only an ID.
    """

    cases = json.loads(json.dumps(raw_cases, ensure_ascii=True))
    for correction in corrections:
        matching_cases = [
            case for case in cases if case.get("case_id") == correction.case_id
        ]
        if len(matching_cases) != 1:
            raise OpenAlexPrecisionUnseenError(
                f"correction target case {correction.case_id} is not unique"
            )
        profile = matching_cases[0].get("profile")
        if not isinstance(profile, dict):
            raise OpenAlexPrecisionUnseenError(
                f"{correction.case_id} correction target profile is missing"
            )
        groups = profile.get(correction.group_kind)
        if not isinstance(groups, list):
            raise OpenAlexPrecisionUnseenError(
                f"{correction.case_id} correction target group list is missing"
            )
        matching_groups = [
            group
            for group in groups
            if isinstance(group, dict)
            and group.get("group_id") == correction.group_id
        ]
        if len(matching_groups) != 1:
            raise OpenAlexPrecisionUnseenError(
                f"correction target group {correction.group_id} is not unique"
            )
        observed = tuple(matching_groups[0].get("phrases", ()))
        if observed != correction.expected_phrases:
            raise OpenAlexPrecisionUnseenError(
                f"correction target phrases drifted for {correction.group_id}"
            )
        matching_groups[0]["phrases"] = list(correction.replacement_phrases)
    return tuple(UnseenChallengeCaseSpec.model_validate(case) for case in cases)

def load_frozen_cases(
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    *,
    correction_path: Path = DEFAULT_CORRECTION_PATH,
    expected_fixture_sha256: str = EXPECTED_FIXTURE_SHA256,
    expected_correction_sha256: str = EXPECTED_CORRECTION_SHA256,
) -> tuple[str, str, UnseenSourceValueGates, tuple[PreparedUnseenCase, ...]]:
    """Validate raw fixture bytes before parsing or expanding any case."""

    raw = fixture_path.read_bytes()
    fixture_sha256 = _sha256_bytes(raw)
    if fixture_sha256 != expected_fixture_sha256:
        raise OpenAlexPrecisionUnseenError(
            "precision-v2 unseen fixture byte identity drifted: "
            f"expected {expected_fixture_sha256}, got {fixture_sha256}"
        )
    manifest = UnseenChallengeManifest.model_validate_json(raw)
    correction_raw = correction_path.read_bytes()
    correction_sha256 = _sha256_bytes(correction_raw)
    if correction_sha256 != expected_correction_sha256:
        raise OpenAlexPrecisionUnseenError(
            "precision-v2 unseen correction byte identity drifted: "
            f"expected {expected_correction_sha256}, got {correction_sha256}"
        )
    correction_lock = UnseenCorrectionLock.model_validate_json(correction_raw)
    if correction_lock.source_fixture_sha256 != fixture_sha256:
        raise OpenAlexPrecisionUnseenError(
            "unseen correction lock references a different source fixture"
        )
    corrected_cases = _apply_corrections(
        manifest.challenge_cases,
        correction_lock.corrections,
    )
    return (
        fixture_sha256,
        correction_sha256,
        manifest.source_value_gates,
        tuple(build_case(spec) for spec in corrected_cases),
    )


def dry_run(
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    *,
    expected_fixture_sha256: str = EXPECTED_FIXTURE_SHA256,
) -> dict[str, Any]:
    """Expose every frozen identity while constructing no network object."""

    fixture_sha256, correction_sha256, gates, cases = load_frozen_cases(
        fixture_path,
        expected_fixture_sha256=expected_fixture_sha256,
    )
    return {
        "mode": "openalex_precision_v2_unseen_dry_run",
        "production_connected": False,
        "report_workflow_connected": False,
        "real_network_calls_performed": False,
        "live_provider_requests_authorized": False,
        "fixture_sha256": fixture_sha256,
        "correction_sha256": correction_sha256,
        "case_count": len(cases),
        "maximum_request_count": 8,
        "source_value_gates": gates.model_dump(mode="json"),
        "cases": [
            {
                "case_id": case.spec.case_id,
                "collection_sha256": case.collection_sha256,
                "plan_sha256": case.plan_sha256,
                "profile_sha256": case.profile_sha256,
                "idempotency_key": case.plan.calls[0].idempotency_key,
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
