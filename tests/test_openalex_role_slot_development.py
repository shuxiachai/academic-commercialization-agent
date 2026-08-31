"""Zero-network write-once seams for the role-slot v6 development runner."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import pytest

import openalex_role_slot_development as development
from academic_agent.openalex_claim_scope import OpenAlexClaimScopeCandidate
from academic_agent.tools.evidence_search import (
    ProviderResultRejection,
    ToolAdapterFailure,
    ToolEvidenceCandidate,
    ToolProviderUsage,
)
from academic_agent.tools.openalex_claim_scope_search import (
    OpenAlexClaimScopeAdapterResponse,
)
from academic_agent.tools.qwen_role_slot_judge import (
    QwenRoleSlotJudgeError,
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


def _candidate(case_id: str, index: int) -> OpenAlexClaimScopeCandidate:
    return OpenAlexClaimScopeCandidate(
        evidence=ToolEvidenceCandidate(
            title=f"{case_id} role-slot candidate {index} with direct source text",
            url=f"https://openalex.org/W{case_id[1:]}{index}123456789",
            doi=f"10.5555/{case_id.casefold()}.{index}",
            publisher="Frozen OpenAlex Test Publisher",
            published_date=date(2026, 8, 31),
            evidence_summary=(
                f"This abstract for {case_id} candidate {index} contains enough "
                "public source text for every fixed role-slot parser boundary."
            ),
            summary_source="abstract",
            citation_count=index,
            provider_result_index=index,
        ),
        aboutness=(),
    )


class OrderedProviderAdapter:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.calls = []

    def __call__(self, call):  # noqa: ANN001, ANN204
        case_number = len(self.calls) + 1
        case_id = f"Y{case_number:02d}"
        assert (self.output_dir / "manifest.json").is_file()
        if case_number > 1:
            previous = f"Y{case_number - 1:02d}"
            assert (
                self.output_dir / "case-executions" / f"{previous}.json"
            ).is_file()
        self.calls.append(call)
        request_id = f"client-openalex-v6-{case_id.casefold()}"
        usage = ToolProviderUsage(
            provider="openalex",
            request_id=request_id,
            request_id_source="client_generated",
            result_count=3,
            cost_basis="reported_usd",
            reported_cost_usd=0.001,
        )
        return OpenAlexClaimScopeAdapterResponse(
            idempotency_key=call.idempotency_key,
            candidates=(_candidate(case_id, 0), _candidate(case_id, 1)),
            provider_rejections=(
                ProviderResultRejection(
                    provider_result_index=2,
                    code="provider_result_schema_invalid",
                    detail="frozen malformed provider row",
                    title=f"{case_id} rejected row",
                    url=f"https://openalex.org/W{case_number}999999999",
                ),
            ),
            search_cost_usd=0.001,
            provider_request_id=request_id,
            provider_usage=usage,
        )


def _prompt_input(request) -> dict[str, object]:  # noqa: ANN001
    return json.loads(request.user_prompt.split("INPUT:\n", 1)[1])


def _abstain_content(request) -> str:  # noqa: ANN001
    outbound = _prompt_input(request)
    slots = outbound["roles"]
    return json.dumps(
        {
            "case_id": request.case_id,
            "candidates": [
                {
                    "candidate_sha256": candidate["candidate_sha256"],
                    "slots": [
                        {
                            "slot_index": slot["slot_index"],
                            "state": "ABSTAIN",
                            "field": None,
                            "quote": None,
                        }
                        for slot in slots
                    ],
                }
                for candidate in outbound["candidates"]
            ],
        },
        separators=(",", ":"),
    )


class OrderedModelAdapter:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.calls = []
        self.outbound_orders: list[tuple[str, ...]] = []

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
        outbound = _prompt_input(request)
        candidate_order = tuple(
            row["candidate_sha256"] for row in outbound["candidates"]
        )
        self.outbound_orders.append(candidate_order)
        self.calls.append(request)
        raw_content = _abstain_content(request)
        usage = QwenRoleSlotUsage(
            prompt_tokens=100,
            cached_prompt_tokens=1,
            completion_tokens=20,
            total_tokens=120,
            cost_usd=0.001,
            cost_basis="frozen zero-network test cost",
        )
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
            provider_response_id=f"qwen-response-{len(self.calls)}",
            provider_request_id=f"qwen-request-{len(self.calls)}",
            finish_reason="stop",
            raw_content=raw_content,
            raw_content_sha256=_sha256(raw_content.encode("utf-8")),
            usage=usage,
            latency_ms=25.0,
        )


class ProviderFactory:
    def __init__(self, output_dir: Path, adapter: OrderedProviderAdapter) -> None:
        self.output_dir = output_dir
        self.adapter = adapter
        self.call_count = 0

    def __call__(self):  # noqa: ANN204
        self.call_count += 1
        assert (self.output_dir / "manifest.json").is_file()
        return self.adapter


class ModelFactory:
    def __init__(self, output_dir: Path, adapter: OrderedModelAdapter) -> None:
        self.output_dir = output_dir
        self.adapter = adapter
        self.call_count = 0

    def __call__(self):  # noqa: ANN204
        self.call_count += 1
        assert (self.output_dir / "manifest.json").is_file()
        assert (self.output_dir / "provider-journals" / "Y01.json").is_file()
        assert (self.output_dir / "model-plans" / "Y01.json").is_file()
        return self.adapter


def _run_complete(tmp_path: Path):  # noqa: ANN202
    output = tmp_path / "result"
    provider = OrderedProviderAdapter(output)
    model = OrderedModelAdapter(output)
    provider_factory = ProviderFactory(output, provider)
    model_factory = ModelFactory(output, model)
    execution = development.execute_development_study(
        output_dir=output,
        openalex_soft_stop_usd=0.01,
        model_soft_stop_usd=0.25,
        acknowledge_anonymous_daily_budget=True,
        acknowledge_model_budget=True,
        expected_implementation_sha256=_implementation_hashes(),
        provider_adapter_factory=provider_factory,
        model_adapter_factory=model_factory,
    )
    return output, execution, provider, model, provider_factory, model_factory


def test_dry_run_verifies_all_templates_without_constructing_a_client():
    result = development.protocol_dry_run(
        expected_implementation_sha256=_implementation_hashes()
    )

    assert result["case_count"] == 8
    assert result["maximum_openalex_request_count"] == 8
    assert result["maximum_model_call_count"] == 24
    assert result["requested_model"] == "qwen3.5-plus"
    assert result["model_transport_timeout_seconds"] == 120.0
    assert result["real_network_calls_performed"] is False
    assert result["real_model_calls_performed"] is False
    assert result["unseen_cohort_opened"] is False
    assert [case["case_id"] for case in result["cases"]] == [
        f"Y{index:02d}" for index in range(1, 9)
    ]
    assert all(
        len(set(case["judge_request_template_sha256s"])) == 3
        for case in result["cases"]
    )


def test_complete_execution_persists_every_seam_and_actual_candidate_order(tmp_path):
    """Values must reach durable clients, not merely exist inside the kernel."""

    output, execution, provider, model, provider_factory, model_factory = (
        _run_complete(tmp_path)
    )

    assert execution.overall_state == "completed"
    assert execution.stop_reason == "completed"
    assert execution.openalex_request_count == 8
    assert execution.model_call_count == 24
    assert execution.provider_row_count == 24
    assert execution.provider_candidate_count == 16
    assert execution.provider_rejection_count == 8
    assert execution.completed_case_audit_count == 8
    assert execution.top_level_valid_pass_rate == 1.0
    assert execution.local_valid_row_rate == 1.0
    assert execution.provisional_unanimity_rate == 1.0
    assert execution.selected_case_count == 0
    assert execution.mechanical_gate_state == "fail"
    assert execution.source_lock_readiness == "ready"
    assert execution.human_review_state == "not_prepared"
    assert execution.source_value_state == "not_evaluated"
    assert execution.openalex_cost_usd == pytest.approx(0.008)
    assert execution.model_cost_usd == pytest.approx(0.024)
    assert provider_factory.call_count == 1
    assert model_factory.call_count == 1
    assert len(provider.calls) == 8
    assert len(model.calls) == 24

    for offset in range(0, 24, 3):
        provider_order, reverse_order, sha_order = model.outbound_orders[offset : offset + 3]
        assert reverse_order == tuple(reversed(provider_order))
        assert sha_order == tuple(sorted(provider_order))

    payload = json.loads((output / "execution.json").read_text(encoding="utf-8"))
    assert len(payload["cases"]) == 8
    for case in payload["cases"]:
        assert len(case["model_calls"]) == 3
        assert len(case["case_audit"]["passes"]) == 3
        assert len(case["case_audit"]["candidate_decisions"]) == 2
        slot_count = len(case["model_plan"]["inputs"][0]["roles"])
        for pass_audit in case["case_audit"]["passes"]:
            assert len(pass_audit["candidate_rows"]) == 2
            assert all(
                len(candidate["slots"]) == slot_count
                for candidate in pass_audit["candidate_rows"]
            )
    rows = list(
        csv.DictReader((output / "provider-rows.csv").open(encoding="utf-8"))
    )
    assert len(rows) == 24
    assert {row["adapter_disposition"] for row in rows} == {
        "candidate",
        "provider_rejected",
    }
    index = json.loads((output / "artifact-index.json").read_text(encoding="utf-8"))
    assert len(index["files"]) == 60
    assert "case-audits/Y08.json" in index["files"]
    assert "model-journals/Y08-pass-3.json" in index["files"]


class OneCaseProvider(OrderedProviderAdapter):
    pass


class TerminalModelFailure:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, request):  # noqa: ANN001, ANN204
        self.calls.append(request)
        raise QwenRoleSlotJudgeError(
            "simulated uninspectable model timeout",
            failure_type="provider_transport",
            retryable=True,
            request_may_have_spent=True,
            observed_latency_ms=120_000.0,
        )


def test_model_failure_is_one_attempt_and_uninspectable_not_zero(tmp_path):
    output = tmp_path / "failure"
    provider = OneCaseProvider(output)
    model = TerminalModelFailure()

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

    assert execution.overall_state == "partial"
    assert execution.stop_reason == "model_failed"
    assert execution.model_call_count == 1
    assert execution.model_completed_call_count == 0
    assert execution.model_cost_state == "uninspectable"
    assert execution.model_cost_usd is None
    assert execution.mechanical_gate_state == "not_evaluated"
    assert len(model.calls) == 1
    journal = json.loads(
        (output / "model-journals" / "Y01-pass-1.json").read_text(
            encoding="utf-8"
        )
    )
    assert journal["failure_type"] == "provider_transport"
    assert journal["request_may_have_spent"] is True
    assert "raw_content" not in journal


class TerminalProviderFailure:
    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, call):  # noqa: ANN001, ANN204
        del call
        self.call_count += 1
        raise ToolAdapterFailure(
            "simulated provider timeout",
            retryable=True,
            failure_type="provider_transport",
            search_cost_usd=None,
        )


def test_provider_failure_stops_before_model_factory_and_keeps_unknown_cost(tmp_path):
    output = tmp_path / "provider-failure"
    provider = TerminalProviderFailure()
    model_factory_called = False

    def model_factory():  # noqa: ANN202
        nonlocal model_factory_called
        model_factory_called = True
        raise AssertionError("model factory must not run after provider failure")

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

    assert execution.stop_reason == "provider_failed"
    assert execution.openalex_request_count == 1
    assert execution.openalex_cost_state == "uninspectable"
    assert execution.openalex_cost_usd is None
    assert execution.model_cost_state == "not_observed"
    assert provider.call_count == 1
    assert model_factory_called is False


def test_drift_existing_output_budget_and_key_fail_before_factories(
    tmp_path,
    monkeypatch,
):
    output = tmp_path / "existing"
    output.mkdir()
    factory_calls = 0

    def factory():  # noqa: ANN202
        nonlocal factory_calls
        factory_calls += 1
        raise AssertionError("factory must remain unreachable")

    with pytest.raises(FileExistsError):
        development.execute_development_study(
            output_dir=output,
            openalex_soft_stop_usd=0.01,
            model_soft_stop_usd=0.25,
            acknowledge_anonymous_daily_budget=True,
            acknowledge_model_budget=True,
            expected_implementation_sha256=_implementation_hashes(),
            provider_adapter_factory=factory,
        )
    with pytest.raises(development.OpenAlexRoleSlotDevelopmentError, match="budget"):
        development.execute_development_study(
            output_dir=tmp_path / "missing-ack",
            openalex_soft_stop_usd=0.01,
            model_soft_stop_usd=0.25,
            acknowledge_anonymous_daily_budget=False,
            acknowledge_model_budget=True,
            expected_implementation_sha256=_implementation_hashes(),
            provider_adapter_factory=factory,
        )
    monkeypatch.setenv("OPENALEX_API_KEY", "configured-key-must-not-be-used")
    with pytest.raises(development.OpenAlexRoleSlotDevelopmentError, match="refuses"):
        development.execute_development_study(
            output_dir=tmp_path / "configured-key",
            openalex_soft_stop_usd=0.01,
            model_soft_stop_usd=0.25,
            acknowledge_anonymous_daily_budget=True,
            acknowledge_model_budget=True,
            expected_implementation_sha256=_implementation_hashes(),
            provider_adapter_factory=factory,
        )
    assert factory_calls == 0


def test_fixture_drift_stops_before_output_or_provider_construction(tmp_path):
    output = tmp_path / "drift"
    factory_calls = 0

    def factory():  # noqa: ANN202
        nonlocal factory_calls
        factory_calls += 1
        raise AssertionError("provider factory must not run after fixture drift")

    with pytest.raises(
        development.OpenAlexRoleSlotDevelopmentError,
        match="fixture byte identity drifted",
    ):
        development.execute_development_study(
            output_dir=output,
            openalex_soft_stop_usd=0.01,
            model_soft_stop_usd=0.25,
            acknowledge_anonymous_daily_budget=True,
            acknowledge_model_budget=True,
            expected_fixture_sha256="0" * 64,
            expected_implementation_sha256=_implementation_hashes(),
            provider_adapter_factory=factory,
        )
    assert not output.exists()
    assert factory_calls == 0


def test_live_cli_refuses_unseen_before_execution(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["openalex_role_slot_development.py", "--execute-live", "--cohort", "unseen"],
    )
    with pytest.raises(SystemExit, match="refuses the unseen cohort"):
        development.main()


def test_production_worker_remains_disconnected_from_v6_runtime():
    root = Path(development.__file__).resolve().parent
    production_sources = (
        root / "src/academic_agent/pipeline_worker.py",
        root / "src/academic_agent/crew.py",
        root / "api/main.py",
    )
    forbidden = (
        "openalex_role_slot_development",
        "qwen_role_slot_judge",
        "openalex_role_slot",
    )
    for path in production_sources:
        source = path.read_text(encoding="utf-8")
        assert all(name not in source for name in forbidden)
