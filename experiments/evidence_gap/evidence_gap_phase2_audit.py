"""Replay the frozen Phase-2 bounded Tool Calling contract without networking.

This audit intentionally exercises injected deterministic adapters rather than
real providers. It answers whether the execution, budget, quarantine, and
observability seams behave as pre-registered; it cannot estimate production
trigger precision or evidence value.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import deque
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from academic_agent.evidence import EvidenceSource
from academic_agent.evidence_gap import (
    GapContext,
    GapPlanProposal,
    GapSearchIntent,
    GapSignalCode,
    GapToolName,
    ValidatedGapCall,
    ValidatedGapPlan,
    build_gap_context,
    validate_gap_plan,
)
from academic_agent.evidence_gap_execution import (
    EvidenceGapExecutionAudit,
    execute_gap_plan,
)
from academic_agent.source_pipeline import (
    AuthorityCoverage,
    ComponentCoverage,
    SourceCollection,
)
from academic_agent.tools.evidence_search import (
    ReadOnlySearchAdapter,
    ToolAdapterFailure,
    ToolAdapterResponse,
    ToolEvidenceCandidate,
)


DEFAULT_FIXTURE = Path("tests/fixtures/evidence_gap_phase2_challenge.json")
_TRACE_PREFIX = "phase2-contract"
_SUMMARY = (
    "This source provides sufficiently detailed and topic-specific evidence "
    "for the bounded Tool Calling execution and quarantine audit contract."
)


class Phase2AuditError(ValueError):
    """Raised when the frozen challenge or an observed result drifts."""


class ChallengeCall(BaseModel):
    """One planner-approved intent represented without unstable signal ids."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: GapToolName
    trigger_code: GapSignalCode
    trigger_subject: str = Field(min_length=1, max_length=240)
    query: str | None = Field(default=None, min_length=3, max_length=500)
    result_limit: int = Field(default=5, ge=1, le=10)


class AdapterEvent(BaseModel):
    """One deterministic adapter outcome consumed by one executor attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["response", "failure", "malformed", "mutation"]
    retryable: bool = False
    failure_type: str | None = Field(default=None, max_length=200)
    search_cost_usd: float | None = Field(default=0.0, ge=0.0)
    candidates: tuple[ToolEvidenceCandidate, ...] = Field(default=(), max_length=10)

    @model_validator(mode="after")
    def _validate_event_shape(self) -> "AdapterEvent":
        if self.type == "failure":
            if not self.failure_type:
                raise ValueError("failure events require failure_type")
            if self.candidates:
                raise ValueError("failure events cannot contain candidates")
        elif self.failure_type is not None or self.retryable:
            raise ValueError("only failure events may declare failure metadata")

        if self.type in {"response", "mutation"}:
            if self.search_cost_usd is None:
                raise ValueError("response events require inspectable numeric cost")
        elif self.type == "malformed" and self.candidates:
            raise ValueError("malformed events cannot contain parsed candidates")
        return self


class ExpectedCaseResult(BaseModel):
    """Exact frozen disposition at the public execution-audit seam."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_delta_state: Literal["unchanged", "augmented", "incomplete", "failed"]
    outbound_attempt_count: int = Field(ge=0, le=2)
    accepted_count: int = Field(ge=0, le=20)
    call_states: tuple[str, ...]
    rejection_codes: tuple[str, ...]
    cost_state: Literal["known", "uninspectable"]
    incremental_search_cost_usd: float | None = Field(default=None, ge=0.0)
    failure_type: str | None = None
    call_failure_types: tuple[str | None, ...]

    @model_validator(mode="after")
    def _validate_cost_shape(self) -> "ExpectedCaseResult":
        if self.cost_state == "known" and self.incremental_search_cost_usd is None:
            raise ValueError("known cost requires a numeric expected value")
        if (
            self.cost_state == "uninspectable"
            and self.incremental_search_cost_usd is not None
        ):
            raise ValueError("uninspectable cost must use null")
        return self


class ChallengeCase(BaseModel):
    """One adversarial input, injected adapter sequence, and frozen answer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^C\d{2}-[a-z0-9-]+$")
    calls: tuple[ChallengeCall, ...] = Field(min_length=1, max_length=2)
    adapters: dict[GapToolName, tuple[AdapterEvent, ...]]
    expected: ExpectedCaseResult

    @model_validator(mode="after")
    def _validate_case_shape(self) -> "ChallengeCase":
        planned_tools = {call.tool for call in self.calls}
        unexpected = set(self.adapters) - planned_tools
        if unexpected:
            raise ValueError(f"adapters without planned calls: {sorted(unexpected)}")
        if any(not events for events in self.adapters.values()):
            raise ValueError("configured adapters require at least one event")
        if len(self.expected.call_states) != len(self.calls):
            raise ValueError("expected call_states must cover every planned call")
        if len(self.expected.call_failure_types) != len(self.calls):
            raise ValueError(
                "expected call_failure_types must cover every planned call"
            )
        return self


class Phase2Challenge(BaseModel):
    """Strict top-level frozen challenge contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    challenge_id: Literal["evidence-gap-tool-execution-phase2"]
    measurement_design: Literal["synthetic_adversarial_contract_not_production"]
    topic: str = Field(min_length=20, max_length=500)
    cases: tuple[ChallengeCase, ...] = Field(min_length=12)

    @model_validator(mode="after")
    def _validate_unique_case_ids(self) -> "Phase2Challenge":
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("challenge case ids must be unique")
        return self


def _source(
    source_id: str,
    *,
    title: str,
    url: str,
    source_type: str,
    doi: str | None = None,
) -> EvidenceSource:
    return EvidenceSource(
        source_id=source_id,
        title=title,
        url=url,
        doi=doi,
        publisher="Fixture Publisher",
        accessed_date=date(2025, 1, 1),
        source_type=source_type,
        evidence_summary=_SUMMARY,
        summary_source="search_snippet",
    )


def _collection(topic: str) -> SourceCollection:
    """Build the one frozen evidence identity used by every challenge case."""

    return SourceCollection(
        topic=topic,
        display_topic=topic,
        search_aliases=["self-powered wearable glucose sensor monitoring"],
        search_components=["battery-free telemetry", "glucose biosensor"],
        output_language="English",
        weight_profile="biomedical",
        collected_at=datetime(2025, 1, 1, tzinfo=UTC),
        academic_sources=[
            _source(
                "A1",
                title="Battery-free wearable glucose biosensor baseline study",
                url="https://doi.org/10.1000/existing",
                doi="10.1000/existing",
                source_type="academic_paper",
            )
        ],
        patent_sources=[
            _source(
                "P1",
                title="Battery-free wearable glucose biosensor telemetry patent",
                url="https://patents.google.com/patent/US1234567A1",
                source_type="patent",
            )
        ],
        market_sources=[
            _source(
                "M1",
                title="Battery-free wearable glucose monitoring market deployment",
                url="https://www.reuters.com/technology/wearable-glucose-monitoring/",
                source_type="reputable_news",
            )
        ],
        academic_queries=[topic],
        patent_queries=[topic],
        market_queries=[topic],
        authority_coverage=AuthorityCoverage(
            status="incomplete",
            required_categories=["regulatory", "clinical_registry"],
            missing_categories=["regulatory", "clinical_registry"],
        ),
        component_coverage=ComponentCoverage(
            status="incomplete",
            components=["battery-free telemetry", "glucose biosensor"],
            covered_source_ids={"glucose biosensor": ["A1"]},
            missing_components=["battery-free telemetry"],
        ),
        failed_domains={
            "academic": "fixture timeout",
            "patent": "fixture timeout",
            "market": "fixture timeout",
        },
    )


def _trigger_id(
    context: GapContext,
    *,
    code: GapSignalCode,
    subject: str,
) -> str:
    matches = [
        signal.signal_id
        for signal in context.signals
        if signal.code == code and signal.subject == subject
    ]
    if len(matches) != 1:
        raise Phase2AuditError(
            f"expected one trigger for code={code}, subject={subject}; "
            f"found {len(matches)}"
        )
    return matches[0]


def _plan_for_case(
    context: GapContext,
    case: ChallengeCase,
) -> ValidatedGapPlan:
    calls = tuple(
        GapSearchIntent(
            tool=call.tool,
            query=call.query or context.topic,
            trigger_ids=(
                _trigger_id(
                    context,
                    code=call.trigger_code,
                    subject=call.trigger_subject,
                ),
            ),
            result_limit=call.result_limit,
        )
        for call in case.calls
    )
    return validate_gap_plan(
        context,
        GapPlanProposal(
            decision="search",
            rationale=(
                "The frozen synthetic challenge contains a specific evidence "
                "gap and permits only this bounded read-only search."
            ),
            calls=calls,
        ),
    )


class _FixtureAdapter:
    """Consume declared events without opening a socket or hiding a retry."""

    def __init__(
        self,
        events: tuple[AdapterEvent, ...],
        *,
        collection: SourceCollection,
        case_id: str,
    ) -> None:
        self._events = deque(events)
        self._collection = collection
        self._case_id = case_id
        self._attempt = 0

    def __call__(
        self,
        call: ValidatedGapCall,
    ) -> ToolAdapterResponse | dict[str, object]:
        self._attempt += 1
        if not self._events:
            raise RuntimeError("fixture adapter received an unregistered attempt")
        event = self._events.popleft()
        if event.type == "failure":
            raise ToolAdapterFailure(
                "frozen fixture failure",
                retryable=event.retryable,
                failure_type=event.failure_type or "fixture_failure",
                search_cost_usd=event.search_cost_usd,
            )
        if event.type == "malformed":
            # The unknown key proves the strict response schema, while the
            # missing provider cost must remain visibly uninspectable.
            return {
                "tool": call.tool,
                "idempotency_key": call.idempotency_key,
                "outbound_request_count": 1,
                "candidates": [],
                "unexpected": True,
            }
        if event.type == "mutation":
            # This simulates a badly behaved injected adapter. The returned row
            # is otherwise valid so only the final hash seam can catch it.
            self._collection.display_topic = "mutated fixture display topic"

        return ToolAdapterResponse(
            tool=call.tool,
            idempotency_key=call.idempotency_key,
            candidates=event.candidates,
            search_cost_usd=event.search_cost_usd or 0.0,
            provider_request_id=(
                f"{self._case_id}-{call.tool}-{self._attempt}"
            ),
        )


def _adapters_for_case(
    case: ChallengeCase,
    collection: SourceCollection,
) -> dict[GapToolName, ReadOnlySearchAdapter]:
    return {
        tool: _FixtureAdapter(
            events,
            collection=collection,
            case_id=case.case_id,
        )
        for tool, events in case.adapters.items()
    }


def _expected_projection(audit: EvidenceGapExecutionAudit) -> dict[str, object]:
    cost = audit.incremental_search_cost_usd
    return {
        "evidence_delta_state": audit.evidence_delta_state,
        "outbound_attempt_count": audit.outbound_attempt_count,
        "accepted_count": len(audit.accepted_sources),
        "call_states": [call.state for call in audit.call_audits],
        "rejection_codes": [
            rejection.code
            for call in audit.call_audits
            for rejection in call.rejections
        ],
        "cost_state": audit.cost_state,
        "incremental_search_cost_usd": (
            round(cost, 9) if cost is not None else None
        ),
        "failure_type": audit.failure_type,
        "call_failure_types": [
            call.failure_type for call in audit.call_audits
        ],
    }


def _deterministic_projection(
    audit: EvidenceGapExecutionAudit,
) -> dict[str, object]:
    payload = audit.model_dump(mode="json")
    for call in payload["call_audits"]:
        # Wall-clock duration is required telemetry, but it is not an identity
        # field and cannot be byte-identical across two local replays.
        call.pop("latency_ms", None)
    return payload


def _execute_case(
    challenge: Phase2Challenge,
    case: ChallengeCase,
) -> EvidenceGapExecutionAudit:
    collection = _collection(challenge.topic)
    context = build_gap_context(collection)
    plan = _plan_for_case(context, case)
    return execute_gap_plan(
        collection,
        context=context,
        plan=plan,
        adapters=_adapters_for_case(case, collection),
        trace_id=f"{_TRACE_PREFIX}-{case.case_id}",
    )


def _case_result(
    challenge: Phase2Challenge,
    case: ChallengeCase,
) -> dict[str, object]:
    first = _execute_case(challenge, case)
    second = _execute_case(challenge, case)
    if _deterministic_projection(first) != _deterministic_projection(second):
        raise Phase2AuditError(
            f"{case.case_id}: deterministic replay drifted outside latency"
        )

    observed = _expected_projection(first)
    frozen = case.expected.model_dump(mode="json")
    if observed != frozen:
        raise Phase2AuditError(
            f"{case.case_id}: observed disposition differs from frozen answer\n"
            f"expected={json.dumps(frozen, sort_keys=True)}\n"
            f"observed={json.dumps(observed, sort_keys=True)}"
        )
    return {
        "case_id": case.case_id,
        "status": "passed",
        "observed": observed,
        "audit": first.model_dump(mode="json"),
        "deterministic_replay": "passed",
    }


def run_challenge(fixture_path: Path = DEFAULT_FIXTURE) -> dict[str, object]:
    """Validate and replay the complete frozen challenge twice per case."""

    fixture_bytes = fixture_path.read_bytes()
    challenge = Phase2Challenge.model_validate_json(fixture_bytes)
    case_results = [
        _case_result(challenge, case)
        for case in challenge.cases
    ]
    attempts = [
        int(result["observed"]["outbound_attempt_count"])
        for result in case_results
    ]
    accepted = [
        int(result["observed"]["accepted_count"])
        for result in case_results
    ]
    return {
        "schema_version": 1,
        "challenge_id": challenge.challenge_id,
        "measurement_design": challenge.measurement_design,
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "production_connected": False,
        "real_network_calls_performed": False,
        "case_count": len(case_results),
        "passed_case_count": len(case_results),
        "deterministic_replay_passed_count": len(case_results),
        "simulated_adapter_attempt_count": sum(attempts),
        "maximum_case_attempt_count": max(attempts, default=0),
        "accepted_source_count": sum(accepted),
        "unexpected_accepted_source_count": 0,
        "status": "passed",
        "cases": case_results,
    }


def write_audit_artifacts(
    result: dict[str, object],
    output_directory: Path,
) -> None:
    """Write once so a later replay cannot overwrite its measured result."""

    output_directory.mkdir(parents=True, exist_ok=False)
    summary_path = output_directory / "summary.json"
    summary_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    cases = result.get("cases")
    if not isinstance(cases, list):
        raise Phase2AuditError("result cases are not a list")
    with (output_directory / "cases.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "case_id",
                "status",
                "evidence_delta_state",
                "outbound_attempt_count",
                "accepted_count",
                "cost_state",
                "incremental_search_cost_usd",
                "deterministic_replay",
            ),
        )
        writer.writeheader()
        for item in cases:
            if not isinstance(item, dict) or not isinstance(
                item.get("observed"), dict
            ):
                raise Phase2AuditError("case result has an invalid shape")
            observed = item["observed"]
            writer.writerow(
                {
                    "case_id": item["case_id"],
                    "status": item["status"],
                    "evidence_delta_state": observed["evidence_delta_state"],
                    "outbound_attempt_count": observed[
                        "outbound_attempt_count"
                    ],
                    "accepted_count": observed["accepted_count"],
                    "cost_state": observed["cost_state"],
                    "incremental_search_cost_usd": observed[
                        "incremental_search_cost_usd"
                    ],
                    "deterministic_replay": item["deterministic_replay"],
                }
            )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay the frozen zero-network Phase-2 Tool Calling audit."
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="Strict frozen challenge JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New output directory; existing paths are refused.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = run_challenge(args.fixture)
    write_audit_artifacts(result, args.output)
    print(
        "Phase-2 audit passed: "
        f"{result['passed_case_count']}/{result['case_count']} cases; "
        f"max attempts={result['maximum_case_attempt_count']}; "
        "real network calls=0."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
