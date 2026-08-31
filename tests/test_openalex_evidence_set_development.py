"""Zero-network seams for the label-blind v5 development runner."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

import openalex_evidence_set_development as development
from academic_agent.tools.deepseek_evidence_judge import (
    DeepSeekJudgeAdapterError,
    DeepSeekJudgeRequest,
    DeepSeekJudgeResponse,
    DeepSeekJudgeUsage,
    DeepSeekJudgeUsageObservation,
)
from academic_agent.tools.qwen_evidence_judge import (
    QWEN_CHAT_COMPLETIONS_ENDPOINT,
    QwenJudgeAdapterError,
    QwenJudgeRequest,
    QwenJudgeResponse,
    QwenJudgeUsage,
    QwenJudgeUsageObservation,
)


_ROOT = Path(__file__).resolve().parents[1]
_V4_FIXTURE = _ROOT / "tests/fixtures/openalex_scope_link_v4_challenge.json"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class SourceBundle:
    source_lock: Path
    packet: Path
    labels: Path
    declaration: Path
    hashes: dict[str, str]


def _source_bundle(tmp_path: Path) -> SourceBundle:
    fixture = json.loads(_V4_FIXTURE.read_text(encoding="utf-8"))
    source_lock = tmp_path / "source-lock.json"
    source_lock.write_bytes(b'{"frozen":true}\n')
    rows = []
    for case in fixture["challenge_cases"]:
        role_phrases = [
            group["text_phrases"][0]
            for key in ("required_groups", "scope_groups", "supporting_groups")
            for group in case["profile"][key]
        ]
        for index in range(8):
            identity = hashlib.sha256(
                f"{case['case_id']}-identity-{index}".encode()
            ).hexdigest()
            candidate = hashlib.sha256(
                f"{case['case_id']}-candidate-{index}".encode()
            ).hexdigest()
            rows.append(
                {
                    "baseline_sources_json": (
                        '[{"evidence_summary":"DO_NOT_SEND_BASELINE"}]'
                    ),
                    "candidate_sha256": candidate,
                    "case_id": case["case_id"],
                    "declared_gap": "frozen academic evidence retrieval gap",
                    "doi": f"10.1000/{case['case_id'].casefold()}.{index}",
                    "evidence_summary": (
                        "The source discusses " + ", ".join(role_phrases) + "."
                    ),
                    "identity_sha256": identity,
                    "provider": "openalex",
                    "provider_result_index": index,
                    "published_date": "2026-08-29",
                    "publisher": "Frozen Test Journal",
                    "query": case["query"],
                    "summary_source": "abstract",
                    "title": f"{case['topic']} candidate {index}",
                    "topic": case["topic"],
                    "url": f"https://openalex.org/W{case['case_id'][1:]}{index}",
                }
            )
    packet_payload = {
        "case_count": 8,
        "diagnostic_only": True,
        "executed_revision": "1" * 40,
        "measurement_limit": (
            "Synthetic zero-network packet for runner boundary tests only."
        ),
        "mode": "openalex_scope_link_v4_candidate_diagnostic_packet",
        "prepared_at": "2026-08-29T00:00:00+00:00",
        "production_connected": False,
        "report_workflow_connected": False,
        "row_count": 64,
        "rows": rows,
        "schema_version": 1,
        "source_file_sha256": {"execution.json": "2" * 64},
        "source_lock_sha256": _sha256(source_lock.read_bytes()),
        "valid_label_combinations": [["YES", "YES", "YES", "YES"]],
    }
    packet = tmp_path / "packet_manifest.json"
    packet.write_text(
        json.dumps(packet_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # Invalid UTF-8 makes accidental text parsing fail immediately.  A valid
    # dry-run proves these bytes are hashed but never decoded or interpreted.
    labels = tmp_path / "labels.csv"
    labels.write_bytes(b"\xff\xfeDO_NOT_SEND_HUMAN_LABEL")
    declaration = tmp_path / "reviewer_declaration.csv"
    declaration.write_bytes(b"\xff\xfeDO_NOT_SEND_REVIEWER_DECLARATION")
    hashes = {
        "source-lock.json": _sha256(source_lock.read_bytes()),
        "packet_manifest.json": _sha256(packet.read_bytes()),
        "labels.csv": _sha256(labels.read_bytes()),
        "reviewer_declaration.csv": _sha256(declaration.read_bytes()),
    }
    return SourceBundle(source_lock, packet, labels, declaration, hashes)


def _implementation_hashes() -> dict[str, str]:
    return {
        name: development._file_sha256(path)  # noqa: SLF001
        for name, path in development._IMPLEMENTATION_PATHS.items()  # noqa: SLF001
    }


def _qwen_implementation_hashes() -> dict[str, str]:
    return {
        name: development._file_sha256(path)  # noqa: SLF001
        for name, path in development._QWEN_IMPLEMENTATION_PATHS.items()  # noqa: SLF001
    }


def _common(bundle: SourceBundle) -> dict[str, object]:
    return {
        "source_lock_path": bundle.source_lock,
        "packet_path": bundle.packet,
        "labels_path": bundle.labels,
        "declaration_path": bundle.declaration,
        "v4_fixture_path": _V4_FIXTURE,
        "expected_source_sha256": bundle.hashes,
        "expected_v4_fixture_sha256": development.EXPECTED_V4_FIXTURE_SHA256,
        "expected_implementation_sha256": _implementation_hashes(),
    }


def _abstain_content(request: DeepSeekJudgeRequest | QwenJudgeRequest) -> str:
    batch = json.loads(request.user_prompt.split("\nINPUT:\n", 1)[1])
    order = [item["candidate_sha256"] for item in batch["candidates"]]
    return json.dumps(
        {
            "case_id": batch["case_id"],
            "candidate_order": order,
            "decisions": [
                {
                    "candidate_sha256": candidate_sha256,
                    "action": "ABSTAIN",
                    "role_quotes": [],
                }
                for candidate_sha256 in order
            ],
        },
        separators=(",", ":"),
    )


def _response(
    request: DeepSeekJudgeRequest,
    *,
    cost_usd: float = 0.001,
    prompt_sha256: str | None = None,
) -> DeepSeekJudgeResponse:
    content = _abstain_content(request)
    return DeepSeekJudgeResponse(
        trace_id=request.trace_id,
        request_sha256=hashlib.sha256(request.body()).hexdigest(),
        batch_input_sha256=request.batch_input_sha256,
        prompt_sha256=prompt_sha256 or request.prompt_sha256,
        requested_model="deepseek-v4-flash",
        returned_model="deepseek-v4-flash",
        provider_response_id=f"response-{request.trace_id}",
        provider_request_id=f"request-{request.trace_id}",
        finish_reason="stop",
        raw_content=content,
        raw_content_sha256=hashlib.sha256(content.encode()).hexdigest(),
        usage=DeepSeekJudgeUsage(
            prompt_tokens=10,
            cached_prompt_tokens=0,
            completion_tokens=2,
            total_tokens=12,
            cost_usd=cost_usd,
            cost_basis="frozen test price basis",
        ),
        latency_ms=10.0,
    )


class OrderedAdapter:
    def __init__(self, output_dir: Path, *, cost_usd: float = 0.001) -> None:
        self.output_dir = output_dir
        self.cost_usd = cost_usd
        self.requests: list[DeepSeekJudgeRequest] = []

    def __call__(self, request: DeepSeekJudgeRequest) -> DeepSeekJudgeResponse:
        call_index = len(self.requests)
        if call_index:
            previous_case = f"W{((call_index - 1) // 2) + 1:02d}"
            previous_pass = ((call_index - 1) % 2) + 1
            previous = (
                self.output_dir
                / "judge-calls"
                / f"{previous_case}-pass-{previous_pass}.json"
            )
            assert previous.is_file()
        if call_index and call_index % 2 == 0:
            prior_case = f"W{call_index // 2:02d}"
            assert (
                self.output_dir / "case-decisions" / f"{prior_case}.json"
            ).is_file()
        self.requests.append(request)
        return _response(request, cost_usd=self.cost_usd)


class ManifestFirstFactory:
    def __init__(self, output_dir: Path, adapter: OrderedAdapter) -> None:
        self.output_dir = output_dir
        self.adapter = adapter
        self.call_count = 0

    def __call__(self) -> OrderedAdapter:
        self.call_count += 1
        assert (self.output_dir / "manifest.json").is_file()
        return self.adapter


def _execute(
    tmp_path: Path,
    bundle: SourceBundle,
    *,
    soft_stop_usd: float = 0.05,
    cost_usd: float = 0.001,
):
    output = tmp_path / "result"
    adapter = OrderedAdapter(output, cost_usd=cost_usd)
    factory = ManifestFirstFactory(output, adapter)
    result = development.execute_development_study(
        output_dir=output,
        soft_stop_usd=soft_stop_usd,
        acknowledge_model_budget=True,
        adapter_factory=factory,
        **_common(bundle),
    )
    return output, adapter, factory, result


def test_dry_run_hashes_opaque_labels_and_builds_16_label_blind_prompts(tmp_path):
    bundle = _source_bundle(tmp_path)

    result = development.protocol_dry_run(**_common(bundle))

    assert result["case_count"] == 8
    assert result["candidate_count"] == 64
    assert result["maximum_model_call_count"] == 16
    assert result["real_network_calls_performed"] is False
    assert result["real_model_calls_performed"] is False
    assert result["private_label_bytes_hashed"] is True
    assert result["private_label_content_parsed"] is False
    assert len({case["first_prompt_sha256"] for case in result["cases"]}) == 8
    assert len({case["second_prompt_sha256"] for case in result["cases"]}) == 8


def test_full_execution_persists_each_call_and_case_before_the_next(tmp_path):
    bundle = _source_bundle(tmp_path)

    output, adapter, factory, result = _execute(tmp_path, bundle)

    assert factory.call_count == 1
    assert len(adapter.requests) == 16
    assert result.schema_version == 2
    assert result.overall_state == "completed"
    assert result.stop_reason == "completed"
    assert result.attempted_model_call_count == 16
    assert result.completed_case_count == 8
    assert result.persisted_candidate_decision_count == 64
    assert result.disposition_agreement == 1.0
    assert result.mechanical_agreement_gate_passed is True
    assert result.development_gate_state == "ready_for_label_join"
    assert result.cost_usd == pytest.approx(0.016)
    assert len(tuple((output / "judge-calls").glob("*.json"))) == 16
    assert len(tuple((output / "case-decisions").glob("*.json"))) == 8
    assert (output / "artifact-index.json").is_file()


def test_manifest_and_model_boundary_exclude_baseline_urls_and_human_bytes(tmp_path):
    bundle = _source_bundle(tmp_path)

    output, _, _, _ = _execute(tmp_path, bundle)

    manifest = (output / "manifest.json").read_text(encoding="utf-8")
    assert "DO_NOT_SEND_BASELINE" not in manifest
    assert "DO_NOT_SEND_HUMAN_LABEL" not in manifest
    assert "DO_NOT_SEND_REVIEWER_DECLARATION" not in manifest
    assert "openalex.org" not in manifest
    parsed = json.loads(manifest)
    assert parsed["schema_version"] == 2
    assert parsed["requested_model"] == "deepseek-v4-flash"
    for case in parsed["cases"]:
        first = case["first_request"]["user_prompt"]
        second = case["second_request"]["user_prompt"]
        first_batch = json.loads(first.split("\nINPUT:\n", 1)[1])
        second_batch = json.loads(second.split("\nINPUT:\n", 1)[1])
        assert list(first_batch["candidates"]) == list(
            reversed(second_batch["candidates"])
        )
        for candidate in first_batch["candidates"]:
            assert set(candidate) == {"candidate_sha256", "title", "abstract"}


def test_source_drift_stops_before_output_or_adapter_construction(tmp_path):
    bundle = _source_bundle(tmp_path)
    bundle.packet.write_text("{}", encoding="utf-8")
    factory_calls = 0

    def factory():  # noqa: ANN202
        nonlocal factory_calls
        factory_calls += 1
        raise AssertionError("adapter must not be constructed")

    with pytest.raises(
        development.EvidenceSetDevelopmentError,
        match="source identity drifted",
    ):
        development.execute_development_study(
            output_dir=tmp_path / "result",
            soft_stop_usd=0.05,
            acknowledge_model_budget=True,
            adapter_factory=factory,
            **_common(bundle),
        )

    assert factory_calls == 0
    assert not (tmp_path / "result").exists()


def test_soft_stop_commits_in_flight_call_and_starts_no_second_call(tmp_path):
    bundle = _source_bundle(tmp_path)

    output, adapter, _, result = _execute(
        tmp_path,
        bundle,
        soft_stop_usd=0.0005,
        cost_usd=0.001,
    )

    assert len(adapter.requests) == 1
    assert result.overall_state == "partial"
    assert result.stop_reason == "soft_stop"
    assert result.attempted_model_call_count == 1
    assert result.completed_case_count == 0
    assert result.development_gate_state == "not_evaluated"
    assert (output / "judge-calls/W01-pass-1.json").is_file()


class IdentityDriftAdapter:
    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, request: DeepSeekJudgeRequest) -> DeepSeekJudgeResponse:
        self.call_count += 1
        return _response(request, prompt_sha256="f" * 64)


def test_response_identity_drift_is_persisted_and_no_retry_occurs(tmp_path):
    bundle = _source_bundle(tmp_path)
    output = tmp_path / "result"
    adapter = IdentityDriftAdapter()

    result = development.execute_development_study(
        output_dir=output,
        soft_stop_usd=0.05,
        acknowledge_model_budget=True,
        adapter_factory=lambda: adapter,
        **_common(bundle),
    )

    assert adapter.call_count == 1
    assert result.stop_reason == "response_identity_mismatch"
    assert result.cost_state == "known"
    assert result.cost_usd == pytest.approx(0.001)
    assert result.total_tokens == 12
    journal = json.loads(
        (output / "judge-calls/W01-pass-1.json").read_text(encoding="utf-8")
    )
    assert journal["state"] == "failed"
    assert journal["failure_type"] == "adapter_response_identity_mismatch"
    assert "prompt_sha256" in journal["failure_detail"]
    assert journal["observed_returned_model"] == "deepseek-v4-flash"
    assert journal["observed_usage"]["cost_usd"] == pytest.approx(0.001)
    assert "raw_content" not in journal


class FailureAdapter:
    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, request):  # noqa: ANN001, ANN204
        del request
        self.call_count += 1
        raise DeepSeekJudgeAdapterError(
            "provider transport failed",
            failure_type="provider_transport",
            retryable=True,
            request_may_have_spent=True,
        )


def test_adapter_failure_is_one_attempt_and_not_a_silent_pass(tmp_path):
    bundle = _source_bundle(tmp_path)
    output = tmp_path / "result"
    adapter = FailureAdapter()

    result = development.execute_development_study(
        output_dir=output,
        soft_stop_usd=0.05,
        acknowledge_model_budget=True,
        adapter_factory=lambda: adapter,
        **_common(bundle),
    )

    assert adapter.call_count == 1
    assert result.stop_reason == "adapter_failed"
    assert result.completed_model_call_count == 0
    assert result.cost_state == "uninspectable"
    assert result.disposition_agreement is None
    assert result.mechanical_agreement_gate_passed is None
    assert result.development_gate_state == "not_evaluated"


class MeteredIdentityFailureAdapter:
    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, request):  # noqa: ANN001, ANN204
        del request
        self.call_count += 1
        raise DeepSeekJudgeAdapterError(
            "provider returned a different canonical model",
            failure_type="provider_model_identity_mismatch",
            retryable=False,
            request_may_have_spent=True,
            observed_returned_model="deepseek-v4-flash-0731",
            observed_usage=DeepSeekJudgeUsageObservation(
                prompt_tokens=100,
                cached_prompt_tokens=20,
                completion_tokens=10,
                total_tokens=110,
                cost_usd=0.002,
                cost_basis="frozen test price basis",
            ),
        )


def test_failed_identity_call_preserves_safe_usage_at_execution_boundary(tmp_path):
    bundle = _source_bundle(tmp_path)
    output = tmp_path / "result"
    adapter = MeteredIdentityFailureAdapter()

    result = development.execute_development_study(
        output_dir=output,
        soft_stop_usd=0.05,
        acknowledge_model_budget=True,
        adapter_factory=lambda: adapter,
        **_common(bundle),
    )

    assert adapter.call_count == 1
    assert result.completed_model_call_count == 0
    assert result.total_tokens == 110
    assert result.cost_state == "known"
    assert result.cost_usd == pytest.approx(0.002)
    serialized = json.loads((output / "execution.json").read_text(encoding="utf-8"))
    assert serialized["total_tokens"] == 110
    assert serialized["cost_usd"] == pytest.approx(0.002)
    assert serialized["calls"][0]["observed_usage"]["prompt_tokens"] == 100
    assert "raw_content" not in serialized["calls"][0]


def test_existing_output_and_missing_budget_acknowledgement_fail_closed(tmp_path):
    bundle = _source_bundle(tmp_path)
    output = tmp_path / "result"
    output.mkdir()

    with pytest.raises(FileExistsError):
        development.execute_development_study(
            output_dir=output,
            soft_stop_usd=0.05,
            acknowledge_model_budget=True,
            adapter_factory=lambda: FailureAdapter(),
            **_common(bundle),
        )

    with pytest.raises(
        development.EvidenceSetDevelopmentError,
        match="budget acknowledgement",
    ):
        development.execute_development_study(
            output_dir=tmp_path / "other",
            soft_stop_usd=0.05,
            acknowledge_model_budget=False,
            adapter_factory=lambda: FailureAdapter(),
            **_common(bundle),
        )


def test_production_worker_remains_disconnected_from_runner_and_adapter():
    worker = (_ROOT / "src/academic_agent/pipeline_worker.py").read_text(
        encoding="utf-8"
    )

    assert "openalex_evidence_set_development" not in worker
    assert "deepseek_evidence_judge" not in worker
    assert "DeepSeekEvidenceJudgeAdapter" not in worker
    assert "qwen_evidence_judge" not in worker
    assert "QwenEvidenceJudgeAdapter" not in worker


def _qwen_response(
    request: QwenJudgeRequest,
    *,
    cost_usd: float = 0.001,
) -> QwenJudgeResponse:
    content = _abstain_content(request)
    return QwenJudgeResponse(
        trace_id=request.trace_id,
        request_sha256=hashlib.sha256(request.body()).hexdigest(),
        batch_input_sha256=request.batch_input_sha256,
        prompt_sha256=request.prompt_sha256,
        requested_model="qwen3.5-plus",
        returned_model="qwen3.5-plus",
        provider_response_id=f"response-{request.trace_id}",
        provider_request_id=f"request-{request.trace_id}",
        finish_reason="stop",
        raw_content=content,
        raw_content_sha256=hashlib.sha256(content.encode()).hexdigest(),
        usage=QwenJudgeUsage(
            prompt_tokens=10,
            cached_prompt_tokens=1,
            completion_tokens=2,
            total_tokens=12,
            cost_usd=cost_usd,
            cost_basis="frozen Qwen test price basis",
        ),
        latency_ms=10.0,
    )


class QwenOrderedAdapter:
    """Assert the same durable ordering at the provider-switched seam."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.requests: list[QwenJudgeRequest] = []

    def __call__(self, request: QwenJudgeRequest) -> QwenJudgeResponse:
        call_index = len(self.requests)
        if call_index:
            previous_case = f"W{((call_index - 1) // 2) + 1:02d}"
            previous_pass = ((call_index - 1) % 2) + 1
            assert (
                self.output_dir
                / "judge-calls"
                / f"{previous_case}-pass-{previous_pass}.json"
            ).is_file()
        if call_index and call_index % 2 == 0:
            prior_case = f"W{call_index // 2:02d}"
            assert (
                self.output_dir / "case-decisions" / f"{prior_case}.json"
            ).is_file()
        self.requests.append(request)
        return _qwen_response(request)


class QwenMeteredFailureAdapter:
    """Expose safe Qwen usage while withholding rejected semantic content."""

    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, request):  # noqa: ANN001, ANN204
        del request
        self.call_count += 1
        raise QwenJudgeAdapterError(
            "provider returned a different canonical model",
            failure_type="provider_model_identity_mismatch",
            retryable=False,
            request_may_have_spent=True,
            observed_returned_model="qwen3.5-plus-2026-08-01",
            observed_usage=QwenJudgeUsageObservation(
                prompt_tokens=100,
                cached_prompt_tokens=20,
                completion_tokens=10,
                total_tokens=110,
                cost_usd=0.002,
                cost_basis="frozen Qwen test price basis",
            ),
        )


def test_qwen_failure_reaches_execution_accounting_without_a_retry(tmp_path):
    bundle = _source_bundle(tmp_path)
    common = _common(bundle)
    common["judge_provider"] = "qwen"
    common["expected_implementation_sha256"] = _qwen_implementation_hashes()
    output = tmp_path / "qwen-failure"
    adapter = QwenMeteredFailureAdapter()

    result = development.execute_development_study(
        output_dir=output,
        soft_stop_usd=0.05,
        acknowledge_model_budget=True,
        adapter_factory=lambda: adapter,
        **common,
    )

    assert adapter.call_count == 1
    assert result.schema_version == 3
    assert result.stop_reason == "adapter_failed"
    assert result.completed_model_call_count == 0
    assert result.total_tokens == 110
    assert result.cost_state == "known"
    assert result.cost_usd == pytest.approx(0.002)
    journal = json.loads(
        (output / "judge-calls/W01-pass-1.json").read_text(encoding="utf-8")
    )
    assert journal["request"]["requested_provider"] == "qwen"
    assert journal["observed_returned_model"] == "qwen3.5-plus-2026-08-01"
    assert "raw_content" not in journal


def test_call_journal_rejects_a_response_from_the_other_provider():
    system = "Return strict JSON for every supplied evidence candidate."
    user = (
        "Keep candidate order and classify every supplied row as JSON.\nINPUT:\n"
        '{"case_id":"W01","candidates":[]}'
    )
    digest = development._prompt_sha256(system, user)  # noqa: SLF001
    qwen_request = QwenJudgeRequest(
        trace_id="openalex-v5-w01-pass-1",
        system_prompt=system,
        user_prompt=user,
        batch_input_sha256="a" * 64,
        prompt_sha256=digest,
    )
    deepseek_request = DeepSeekJudgeRequest(
        trace_id="openalex-v5-w01-pass-1",
        system_prompt=system,
        user_prompt=user,
        batch_input_sha256="a" * 64,
        prompt_sha256=digest,
    )

    with pytest.raises(ValueError, match="response provider drifted"):
        development.JudgeCallJournal(
            case_id="W01",
            pass_number=1,
            state="completed",
            request=qwen_request,
            response=_response(deepseek_request),
            request_may_have_spent=True,
        )


def test_live_cli_requires_an_explicit_judge_provider(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "openalex_evidence_set_development.py",
            "--execute-live",
            "--output-dir",
            str(tmp_path / "unused"),
            "--soft-stop-usd",
            "0.05",
            "--acknowledge-model-budget",
        ],
    )

    with pytest.raises(SystemExit, match="explicit --judge-provider"):
        development.main()


def test_qwen_dry_run_and_execution_reach_every_persisted_boundary(tmp_path):
    bundle = _source_bundle(tmp_path)
    common = _common(bundle)
    common["judge_provider"] = "qwen"
    common["expected_implementation_sha256"] = _qwen_implementation_hashes()

    dry_run = development.protocol_dry_run(**common)

    assert dry_run["schema_version"] == 3
    assert dry_run["requested_provider"] == "qwen"
    assert dry_run["requested_model"] == "qwen3.5-plus"
    assert dry_run["api_base"] == (
        "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    assert dry_run["case_count"] == 8
    assert dry_run["candidate_count"] == 64

    output = tmp_path / "qwen-result"
    adapter = QwenOrderedAdapter(output)
    factory = ManifestFirstFactory(output, adapter)
    result = development.execute_development_study(
        output_dir=output,
        soft_stop_usd=0.05,
        acknowledge_model_budget=True,
        adapter_factory=factory,
        **common,
    )

    assert factory.call_count == 1
    assert len(adapter.requests) == 16
    assert result.schema_version == 3
    assert result.overall_state == "completed"
    assert result.persisted_candidate_decision_count == 64
    assert result.cost_usd == pytest.approx(0.016)

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 3
    assert manifest["requested_provider"] == "qwen"
    assert manifest["requested_model"] == "qwen3.5-plus"
    assert manifest["api_base"] == (
        "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    for case in manifest["cases"]:
        for request_name in ("first_request", "second_request"):
            request = case[request_name]
            assert request["requested_provider"] == "qwen"
            assert request["requested_model"] == "qwen3.5-plus"
            assert (
                request["chat_completions_endpoint"]
                == QWEN_CHAT_COMPLETIONS_ENDPOINT
            )

    journal = json.loads(
        (output / "judge-calls/W01-pass-1.json").read_text(encoding="utf-8")
    )
    assert journal["request"]["requested_provider"] == "qwen"
    assert journal["response"]["returned_model"] == "qwen3.5-plus"
    assert journal["response"]["usage"]["cached_prompt_tokens"] == 1
    serialized = json.loads((output / "execution.json").read_text(encoding="utf-8"))
    assert serialized["schema_version"] == 3
    assert serialized["calls"][0]["request"]["requested_provider"] == "qwen"


def test_manifest_rejects_a_provider_identity_mismatch(tmp_path):
    bundle = _source_bundle(tmp_path)
    common = _common(bundle)
    common["judge_provider"] = "qwen"
    common["expected_implementation_sha256"] = _qwen_implementation_hashes()
    output = tmp_path / "qwen-result"
    adapter = QwenOrderedAdapter(output)
    development.execute_development_study(
        output_dir=output,
        soft_stop_usd=0.05,
        acknowledge_model_budget=True,
        adapter_factory=lambda: adapter,
        **common,
    )
    payload = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    payload["requested_provider"] = "deepseek"

    with pytest.raises(ValueError, match="provider contract fields"):
        development.DevelopmentManifest.model_validate(payload)
