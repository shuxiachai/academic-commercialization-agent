"""Frozen, zero-network preflight for Phase 4 domain evidence adapters.

This module intentionally has no live execution switch and imports no network
adapter. It expands the byte-frozen challenge into deterministic gap contexts
and validated calls so a later, separately authorized provider runner can bind
to identities that existed before any provider result was observed.
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
from academic_agent.source_pipeline import SourceCollection


_ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST_PATH = (
    _ROOT / "tests/fixtures/evidence_gap_phase4_domain_challenge.json"
)
EXPECTED_FIXTURE_SHA256 = (
    "f9eee1fcf2ff5acb75e9da840b94baa43e3b10f7e3136dec9886c3a572663a24"
)
_COLLECTED_AT = datetime(2026, 8, 26, tzinfo=UTC)
_ACCESSED_DATE = date(2026, 8, 26)
_EXPECTED_CASES = {
    "D01": ("openalex", "academic_search"),
    "D02": ("openalex", "academic_search"),
    "D03": ("openalex", "academic_search"),
    "D04": ("openalex", "academic_search"),
    "D05": ("lens", "patent_search"),
    "D06": ("lens", "patent_search"),
    "D07": ("lens", "patent_search"),
    "D08": ("lens", "patent_search"),
}


class Phase4AuditError(ValueError):
    """Raised before adapter construction when the frozen contract drifts."""


class Phase4CaseSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^D0[1-8]$")
    provider: Literal["openalex", "lens"]
    tool: Literal["academic_search", "patent_search"]
    topic: str = Field(min_length=20, max_length=300)
    query: str = Field(min_length=20, max_length=500)
    result_limit: Literal[5] = 5

    @model_validator(mode="after")
    def _validate_provider_capability(self) -> "Phase4CaseSpec":
        expected_tool = {
            "openalex": "academic_search",
            "lens": "patent_search",
        }[self.provider]
        if self.tool != expected_tool:
            raise ValueError(
                f"{self.provider} must remain bound to {expected_tool}"
            )
        return self


class Phase4Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["phase4_domain_adapter_challenge"]
    production_connected: Literal[False] = False
    maximum_requests: Literal[8] = 8
    cases: tuple[Phase4CaseSpec, ...] = Field(min_length=8, max_length=8)

    @model_validator(mode="after")
    def _validate_frozen_case_set(self) -> "Phase4Manifest":
        if [case.case_id for case in self.cases] != list(_EXPECTED_CASES):
            raise ValueError("phase-4 cases must remain ordered D01 through D08")
        for case in self.cases:
            if (case.provider, case.tool) != _EXPECTED_CASES[case.case_id]:
                raise ValueError(f"{case.case_id} provider capability drifted")
        return self


@dataclass(frozen=True)
class PreparedPhase4Case:
    spec: Phase4CaseSpec
    collection: SourceCollection
    context: GapContext
    plan: ValidatedGapPlan
    collection_sha256: str
    plan_sha256: str


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _plan_sha256(plan: ValidatedGapPlan) -> str:
    return _sha256_bytes(
        plan.model_dump_json(exclude_none=False).encode("utf-8")
    )


def _seed_source(spec: Phase4CaseSpec) -> EvidenceSource:
    """Supply schema-valid prior context without filling the declared gap."""

    # Academic-gap cases still need one seed record because SourceCollection is
    # a report-level object, not a blank search request. The explicit failed
    # domain signal is authoritative for this synthetic adapter challenge.
    return EvidenceSource(
        source_id="A1",
        title=f"{spec.topic}: frozen Phase 4 baseline context",
        url=f"https://doi.org/10.5555/phase4.{spec.case_id.casefold()}",
        publisher="Frozen Phase 4 Fixture",
        accessed_date=_ACCESSED_DATE,
        source_type="academic_paper",
        evidence_summary=(
            f"This synthetic baseline records prior context for {spec.topic}. "
            "It exists only to keep the collection schema-valid and does not "
            "satisfy the separately declared provider evidence gap."
        ),
        summary_source="abstract",
    )


def build_case(spec: Phase4CaseSpec) -> PreparedPhase4Case:
    """Expand one recipe without clocks, network, models or randomness."""

    gap_subject = "academic" if spec.tool == "academic_search" else "patent"
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
            gap_subject: "frozen Phase 4 source-native retrieval challenge"
        },
    )
    context = build_gap_context(collection)
    trigger = next(
        (
            signal
            for signal in context.signals
            if signal.code == "retrieval_domain_failed"
            and signal.subject == gap_subject
        ),
        None,
    )
    if trigger is None:
        raise Phase4AuditError(
            f"{spec.case_id}: frozen retrieval gap signal was not produced"
        )
    plan = validate_gap_plan(
        context,
        GapPlanProposal(
            decision="search",
            rationale=(
                "The frozen domain-adapter case authorizes one read-only "
                "provider request for its explicit evidence gap."
            ),
            calls=(
                GapSearchIntent(
                    tool=spec.tool,
                    query=spec.query,
                    trigger_ids=(trigger.signal_id,),
                    result_limit=spec.result_limit,
                ),
            ),
        ),
    )
    return PreparedPhase4Case(
        spec=spec,
        collection=collection,
        context=context,
        plan=plan,
        collection_sha256=source_collection_sha256(collection),
        plan_sha256=_plan_sha256(plan),
    )


def load_frozen_cases(
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> tuple[str, tuple[PreparedPhase4Case, ...]]:
    """Validate raw fixture identity before parsing or expanding any case."""

    raw = manifest_path.read_bytes()
    fixture_sha256 = _sha256_bytes(raw)
    if fixture_sha256 != EXPECTED_FIXTURE_SHA256:
        raise Phase4AuditError(
            "phase-4 fixture byte identity drifted: "
            f"expected {EXPECTED_FIXTURE_SHA256}, got {fixture_sha256}"
        )
    manifest = Phase4Manifest.model_validate_json(raw)
    return fixture_sha256, tuple(build_case(spec) for spec in manifest.cases)


def dry_run(manifest_path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    """Expose every deterministic identity while performing zero requests."""

    fixture_sha256, cases = load_frozen_cases(manifest_path)
    return {
        "mode": "phase4_domain_adapter_dry_run",
        "production_connected": False,
        "report_workflow_connected": False,
        "real_network_calls_performed": False,
        "fixture_sha256": fixture_sha256,
        "case_count": len(cases),
        "maximum_request_count": 8,
        "cases": [
            {
                "case_id": case.spec.case_id,
                "provider": case.spec.provider,
                "tool": case.spec.tool,
                "collection_sha256": case.collection_sha256,
                "plan_sha256": case.plan_sha256,
                "idempotency_key": case.plan.calls[0].idempotency_key,
            }
            for case in cases
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    return parser


def main() -> int:
    args = _parser().parse_args()
    print(json.dumps(dry_run(args.manifest), ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
