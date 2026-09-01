"""Additional zero-network seams for v6 unavailable and empty-source states."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import openalex_role_slot_development as development
from academic_agent.openalex_claim_scope import OpenAlexClaimScopeCandidate
from academic_agent.tools.evidence_search import ToolEvidenceCandidate, ToolProviderUsage
from academic_agent.tools.openalex_claim_scope_search import (
    OpenAlexClaimScopeAdapterResponse,
)
from academic_agent.tools.qwen_role_slot_judge import (
    QwenRoleSlotResponse,
    QwenRoleSlotUsage,
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _implementation_hashes() -> dict[str, str]:
    return {
        name: _sha256(path.read_bytes())
        for name, path in development._IMPLEMENTATION_PATHS.items()  # noqa: SLF001
    }


def _usage(case_id: str, result_count: int) -> ToolProviderUsage:
    return ToolProviderUsage(
        provider="openalex",
        request_id=f"client-openalex-v6-{case_id.casefold()}",
        request_id_source="client_generated",
        result_count=result_count,
        cost_basis="reported_usd",
        reported_cost_usd=0.001,
    )


class EmptyProvider:
    """Return eight accounted empty result sets without constructing Qwen."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.call_count = 0

    def __call__(self, call):  # noqa: ANN001, ANN204
        self.call_count += 1
        case_id = f"Y{self.call_count:02d}"
        assert (self.output_dir / "manifest.json").is_file()
        if self.call_count > 1:
            previous = f"Y{self.call_count - 1:02d}"
            assert (
                self.output_dir / "case-executions" / f"{previous}.json"
            ).is_file()
        return OpenAlexClaimScopeAdapterResponse(
            idempotency_key=call.idempotency_key,
            candidates=(),
            provider_rejections=(),
            search_cost_usd=0.001,
            provider_request_id=f"client-openalex-v6-{case_id.casefold()}",
            provider_usage=_usage(case_id, 0),
        )


def _candidate(case_id: str) -> OpenAlexClaimScopeCandidate:
    return OpenAlexClaimScopeCandidate(
        evidence=ToolEvidenceCandidate(
            title=f"{case_id} source-text candidate",
            url=f"https://openalex.org/W{case_id[1:]}123456789",
            doi=f"10.5555/{case_id.casefold()}",
            publisher="Frozen OpenAlex Test Publisher",
            published_date=date(2026, 9, 1),
            evidence_summary=(
                f"The public abstract for {case_id} is intentionally sufficient "
                "to reach every parser boundary in this zero-network test."
            ),
            summary_source="abstract",
            citation_count=1,
            provider_result_index=0,
        ),
        aboutness=(),
    )


class OneCandidateProvider:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.call_count = 0

    def __call__(self, call):  # noqa: ANN001, ANN204
        self.call_count += 1
        case_id = f"Y{self.call_count:02d}"
        assert (self.output_dir / "manifest.json").is_file()
        if self.call_count > 1:
            previous = f"Y{self.call_count - 1:02d}"
            assert (
                self.output_dir / "case-executions" / f"{previous}.json"
            ).is_file()
        return OpenAlexClaimScopeAdapterResponse(
            idempotency_key=call.idempotency_key,
            candidates=(_candidate(case_id),),
            provider_rejections=(),
            search_cost_usd=0.001,
            provider_request_id=f"client-openalex-v6-{case_id.casefold()}",
            provider_usage=_usage(case_id, 1),
        )


class MalformedSemanticModel:
    """Return paid, accounted responses whose semantic JSON is unusable."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.calls = []

    def __call__(self, request):  # noqa: ANN001, ANN204
        assert (
            self.output_dir / "provider-journals" / f"{request.case_id}.json"
        ).is_file()
        assert (
            self.output_dir / "model-plans" / f"{request.case_id}.json"
        ).is_file()
        if request.pass_number > 1:
            assert (
                self.output_dir
                / "model-journals"
                / f"{request.case_id}-pass-{request.pass_number - 1}.json"
            ).is_file()
        self.calls.append(request)
        raw_content = "{}"
        return QwenRoleSlotResponse(
            case_id=request.case_id,
            pass_number=request.pass_number,
            candidate_order=request.candidate_order,
            trace_id=request.trace_id,
            request_sha256=_sha256(request.body()),
            batch_input_sha256=request.batch_input_sha256,
            prompt_sha256=request.prompt_sha256,
            requested_model=request.requested_model,
            returned_model="qwen3.5-plus",
            provider_response_id=f"qwen-malformed-response-{len(self.calls)}",
            provider_request_id=f"qwen-malformed-request-{len(self.calls)}",
            finish_reason="stop",
            raw_content=raw_content,
            raw_content_sha256=_sha256(raw_content.encode("utf-8")),
            usage=QwenRoleSlotUsage(
                prompt_tokens=100,
                cached_prompt_tokens=0,
                completion_tokens=2,
                total_tokens=102,
                cost_usd=0.001,
                cost_basis="frozen zero-network test cost",
            ),
            latency_ms=20.0,
        )


def test_empty_provider_results_complete_without_constructing_qwen(tmp_path):
    """No evidence means checked-but-empty, not a model call or silent pass."""

    output = tmp_path / "empty-provider"
    provider = EmptyProvider(output)
    model_factory_called = False

    def model_factory():  # noqa: ANN202
        nonlocal model_factory_called
        model_factory_called = True
        raise AssertionError("Qwen must not be constructed without candidates")

    execution = development.execute_development_study(
        output_dir=output,
        openalex_soft_stop_usd=0.01,
        model_soft_stop_usd=0.25,
        acknowledge_anonymous_daily_budget=True,
        acknowledge_model_budget=True,
        expected_implementation_sha256=_implementation_hashes(),
        provider_adapter_factory=lambda: provider,
        model_adapter_factory=model_factory,
    )

    assert execution.overall_state == "completed"
    assert execution.openalex_request_count == 8
    assert execution.openalex_successful_case_count == 8
    assert execution.provider_row_count == 0
    assert execution.model_call_count == 0
    assert execution.model_cost_state == "not_observed"
    assert execution.top_level_valid_pass_denominator == 0
    assert execution.top_level_contract_gate_passed is None
    assert execution.mechanical_gate_state == "fail"
    assert execution.source_lock_readiness == "ready"
    assert all(case.state == "no_candidates" for case in execution.cases)
    assert provider.call_count == 8
    assert model_factory_called is False


def test_malformed_semantic_json_is_accounted_unavailable_and_reaches_clients(tmp_path):
    """A paid malformed answer remains visible and never becomes a repair/pass."""

    output = tmp_path / "malformed-semantic"
    provider = OneCandidateProvider(output)
    model = MalformedSemanticModel(output)
    execution = development.execute_development_study(
        output_dir=output,
        openalex_soft_stop_usd=0.01,
        model_soft_stop_usd=0.25,
        acknowledge_anonymous_daily_budget=True,
        acknowledge_model_budget=True,
        expected_implementation_sha256=_implementation_hashes(),
        provider_adapter_factory=lambda: provider,
        model_adapter_factory=lambda: model,
    )

    assert execution.overall_state == "completed"
    assert execution.model_call_count == 24
    assert execution.model_completed_call_count == 24
    assert execution.model_cost_state == "known"
    assert execution.top_level_valid_pass_numerator == 0
    assert execution.top_level_valid_pass_denominator == 24
    assert execution.top_level_contract_gate_passed is False
    assert execution.mechanical_gate_state == "fail"
    assert len(model.calls) == 24
    for case in execution.cases:
        assert case.case_audit is not None
        assert [item.state for item in case.case_audit.passes] == [
            "malformed",
            "malformed",
            "malformed",
        ]
        for pass_audit in case.case_audit.passes:
            assert len(pass_audit.candidate_rows) == 1
            assert pass_audit.candidate_rows[0].row_state == "pass_unavailable"
            assert all(
                slot.state == "row_unavailable"
                for slot in pass_audit.candidate_rows[0].slots
            )
        for call in case.model_calls:
            assert call.response is not None
            assert call.response.raw_content == "{}"

    execution_payload = json.loads(
        (output / "execution.json").read_text(encoding="utf-8")
    )
    aggregate = json.loads(
        (output / "case-audits.json").read_text(encoding="utf-8")
    )
    expected_aggregate = [
        case["case_audit"]
        for case in execution_payload["cases"]
        if case["case_audit"] is not None
    ]
    assert aggregate == expected_aggregate
    for row in aggregate:
        per_case = json.loads(
            (output / "case-audits" / f"{row['case_id']}.json").read_text(
                encoding="utf-8"
            )
        )
        assert row == per_case
