"""Zero-network seams for the frozen Phase 4 live value-study runner."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

import evidence_gap_phase4_live as phase4_live
from academic_agent.evidence_gap import ValidatedGapCall
from academic_agent.tools.evidence_search import (
    ProviderResultRejection,
    ToolAdapterFailure,
    ToolAdapterResponse,
    ToolEvidenceCandidate,
    ToolProviderUsage,
)
from evidence_gap_phase4_audit import load_frozen_cases
from evidence_gap_phase4_live import (
    Phase4LiveError,
    execute_live_study,
)


def _candidate(call: ValidatedGapCall, provider: str, index: int = 0):
    if provider == "openalex":
        return ToolEvidenceCandidate(
            title=f"{call.query} controlled experimental study",
            url=f"https://openalex.org/W42000000{index + 10}",
            publisher="OpenAlex test journal",
            evidence_summary=(
                f"Experimental evidence directly measures {call.query} under "
                "controlled conditions and reports comparative performance."
            ),
            summary_source="abstract",
            provider_result_index=index,
        )
    return ToolEvidenceCandidate(
        title=f"{call.query} patent claims and apparatus",
        url=f"https://lens.org/lens/patent/123-456-789-000-{index + 100}",
        publisher="US patent record",
        evidence_summary=(
            f"The patent abstract directly describes {call.query}, including "
            "claim scope, materials, apparatus and operating conditions."
        ),
        summary_source="abstract",
        provider_result_index=index,
    )


def _response(
    call: ValidatedGapCall,
    provider: str,
    *,
    openalex_cost: float = 0.0001,
    include_rejection: bool = False,
    off_topic: bool = False,
) -> ToolAdapterResponse:
    candidate = _candidate(call, provider)
    if off_topic:
        candidate = candidate.model_copy(
            update={
                "title": "Unrelated municipal archive catalog record",
                "evidence_summary": (
                    "This catalog entry describes historical municipal meeting "
                    "minutes and contains no scientific or patent evidence."
                ),
            }
        )
    rejections = (
        (
            ProviderResultRejection(
                provider_result_index=1,
                code="provider_result_not_object",
                detail="fixture row is not an object",
            ),
        )
        if include_rejection
        else ()
    )
    usage = ToolProviderUsage(
        provider=provider,
        request_id=f"client-{provider}-{call.idempotency_key[:12]}",
        request_id_source="client_generated",
        result_count=1 + len(rejections),
        cost_basis=("reported_usd" if provider == "openalex" else "uninspectable"),
        reported_cost_usd=(openalex_cost if provider == "openalex" else None),
    )
    return ToolAdapterResponse(
        tool=call.tool,
        idempotency_key=call.idempotency_key,
        candidates=(candidate,),
        provider_rejections=rejections,
        search_cost_usd=(openalex_cost if provider == "openalex" else None),
        provider_request_id=usage.request_id,
        provider_usage=usage,
    )


class RecordingFactory:
    """Injected provider boundary that never opens a socket."""

    def __init__(
        self,
        output_dir: Path,
        *,
        openalex_cost: float = 0.0001,
        include_rejection: bool = False,
        off_topic: bool = False,
        fail_provider: str | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.openalex_cost = openalex_cost
        self.include_rejection = include_rejection
        self.off_topic = off_topic
        self.fail_provider = fail_provider
        self.constructed = 0
        self.calls: list[tuple[str, str]] = []
        _, cases = load_frozen_cases()
        self.case_by_key = {
            case.plan.calls[0].idempotency_key: case.spec.case_id for case in cases
        }

    def __call__(self):
        self.constructed += 1

        def adapter(provider: str):
            def run(call: ValidatedGapCall):
                case_id = self.case_by_key[call.idempotency_key]
                assert (self.output_dir / "manifest.json").is_file()
                for previous_provider, previous_case in self.calls:
                    if previous_provider == provider:
                        assert (
                            self.output_dir
                            / "case-executions"
                            / f"{previous_case}.json"
                        ).is_file()
                self.calls.append((provider, case_id))
                if provider == self.fail_provider:
                    raise ToolAdapterFailure(
                        "offline injected provider failure",
                        retryable=False,
                        failure_type="provider_authentication",
                        search_cost_usd=None,
                    )
                return _response(
                    call,
                    provider,
                    openalex_cost=self.openalex_cost,
                    include_rejection=self.include_rejection,
                    off_topic=self.off_topic,
                )

            return run

        return {
            "openalex": adapter("openalex"),
            "lens": adapter("lens"),
        }


def _run(tmp_path: Path, **factory_options):
    output = tmp_path / "phase4-live"
    factory = RecordingFactory(output, **factory_options)
    artifact = execute_live_study(
        output_dir=output,
        openalex_soft_stop_usd=0.01,
        acknowledge_lens_cost_uninspectable=True,
        adapter_factory=factory,
    )
    return output, factory, artifact


def test_complete_run_reaches_journal_accounting_and_artifact_seams(tmp_path):
    output, factory, artifact = _run(tmp_path)

    assert factory.constructed == 1
    assert factory.calls == [
        ("openalex", "D01"),
        ("openalex", "D02"),
        ("openalex", "D03"),
        ("openalex", "D04"),
        ("lens", "D05"),
        ("lens", "D06"),
        ("lens", "D07"),
        ("lens", "D08"),
    ]
    assert artifact.overall_state == "completed"
    assert artifact.request_count == 8
    assert artifact.successful_case_count == 8
    openalex, lens = artifact.provider_summaries
    assert openalex.cost_state == "known"
    assert openalex.reported_cost_usd == pytest.approx(0.0004)
    assert lens.cost_state == "uninspectable"
    assert lens.reported_cost_usd is None
    assert {path.name for path in (output / "case-executions").glob("*.json")} == {
        f"D{index:02d}.json" for index in range(1, 9)
    }
    assert (output / "artifact-index.json").is_file()


def test_every_provider_row_and_accepted_candidate_reaches_csv_boundary(tmp_path):
    output, _, _ = _run(tmp_path, include_rejection=True)

    with (output / "candidates.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    with (output / "review.csv").open(encoding="utf-8", newline="") as handle:
        reviews = list(csv.DictReader(handle))

    assert len(rows) == 16
    assert len(reviews) == 8
    assert CounterLike(row["adapter_disposition"] for row in rows) == {
        "candidate": 8,
        "provider_rejected": 8,
    }
    for case_id in (f"D{index:02d}" for index in range(1, 9)):
        case_rows = [row for row in rows if row["case_id"] == case_id]
        assert [row["provider_result_index"] for row in case_rows] == ["0", "1"]
    assert {row["case_id"] for row in reviews} == {
        f"D{index:02d}" for index in range(1, 9)
    }
    assert all(row["accepted_source_id"] for row in reviews)


def CounterLike(values):
    """Tiny local counter keeps the expected row-disposition seam readable."""

    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result


@pytest.mark.parametrize(
    ("soft_stop", "acknowledge"),
    [
        (0.0, True),
        (0.051, True),
        (0.01, False),
    ],
)
def test_invalid_authorization_fails_before_adapter_construction(
    tmp_path,
    soft_stop,
    acknowledge,
):
    output = tmp_path / "forbidden"
    factory = RecordingFactory(output)

    with pytest.raises(Phase4LiveError):
        execute_live_study(
            output_dir=output,
            openalex_soft_stop_usd=soft_stop,
            acknowledge_lens_cost_uninspectable=acknowledge,
            adapter_factory=factory,
        )

    assert factory.constructed == 0
    assert not output.exists()


def test_existing_output_fails_before_adapter_construction(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    factory = RecordingFactory(output)

    with pytest.raises(FileExistsError, match="already exists"):
        execute_live_study(
            output_dir=output,
            openalex_soft_stop_usd=0.01,
            acknowledge_lens_cost_uninspectable=True,
            adapter_factory=factory,
        )

    assert factory.constructed == 0


def test_implementation_hash_drift_fails_before_factory_and_output(
    tmp_path,
    monkeypatch,
):
    output = tmp_path / "hash-drift"
    factory = RecordingFactory(output)
    monkeypatch.setitem(
        phase4_live.EXPECTED_IMPLEMENTATION_SHA256,
        "domain_evidence_search.py",
        "0" * 64,
    )

    with pytest.raises(Phase4LiveError, match="implementation identity drifted"):
        execute_live_study(
            output_dir=output,
            openalex_soft_stop_usd=0.01,
            acknowledge_lens_cost_uninspectable=True,
            adapter_factory=factory,
        )

    assert factory.constructed == 0
    assert not output.exists()


def test_default_live_path_requires_both_credentials_before_output(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.delenv("LENS_API_KEY", raising=False)
    output = tmp_path / "missing-keys"

    with pytest.raises(Phase4LiveError, match="OPENALEX_API_KEY, LENS_API_KEY"):
        execute_live_study(
            output_dir=output,
            openalex_soft_stop_usd=0.01,
            acknowledge_lens_cost_uninspectable=True,
        )

    assert not output.exists()


def test_openalex_soft_stop_does_not_erase_independent_lens_cases(tmp_path):
    output = tmp_path / "soft-stop"
    factory = RecordingFactory(output, openalex_cost=0.02)

    artifact = execute_live_study(
        output_dir=output,
        openalex_soft_stop_usd=0.01,
        acknowledge_lens_cost_uninspectable=True,
        adapter_factory=factory,
    )

    assert artifact.overall_state == "partial"
    assert artifact.request_count == 5
    assert [case.case_id for case in artifact.cases] == [
        "D01",
        "D05",
        "D06",
        "D07",
        "D08",
    ]
    assert artifact.provider_summaries[0].stopped_reason == "soft_stop"
    assert artifact.provider_summaries[1].stopped_reason == "completed"


def test_provider_failure_stops_that_provider_without_hiding_other_audit(tmp_path):
    output = tmp_path / "provider-failure"
    factory = RecordingFactory(output, fail_provider="openalex")

    artifact = execute_live_study(
        output_dir=output,
        openalex_soft_stop_usd=0.01,
        acknowledge_lens_cost_uninspectable=True,
        adapter_factory=factory,
    )

    assert artifact.overall_state == "partial"
    assert artifact.request_count == 5
    assert artifact.provider_summaries[0].stopped_reason == "request_failed"
    assert artifact.provider_summaries[0].cost_state == "uninspectable"
    assert artifact.provider_summaries[1].stopped_reason == "completed"
    assert (output / "case-executions" / "D01.json").is_file()


def test_artifacts_do_not_contain_environment_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "openalex-artifact-secret")
    monkeypatch.setenv("LENS_API_KEY", "lens-artifact-secret")
    output, _, _ = _run(tmp_path)

    rendered = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output.rglob("*")
        if path.is_file()
    )
    assert "openalex-artifact-secret" not in rendered
    assert "lens-artifact-secret" not in rendered


def test_protocol_dry_run_locks_implementation_without_live_authority():
    result = phase4_live.protocol_dry_run()

    assert result["mode"] == "phase4_domain_adapter_dry_run"
    assert result["implementation_sha256"] == phase4_live.EXPECTED_IMPLEMENTATION_SHA256
    assert result["live_provider_requests_authorized"] is False
    assert result["real_network_calls_performed"] is False


def test_manifest_rejects_expanded_plan_content_drift():
    _, prepared = load_frozen_cases()
    manifest = phase4_live._manifest_artifact(
        prepared,
        phase4_live.EXPECTED_FIXTURE_SHA256,
        phase4_live.verify_frozen_implementation(),
    )
    payload = manifest.model_dump(mode="json")
    payload["cases"][0]["validated_plan"]["calls"][0]["query"] += " drift"

    with pytest.raises(ValueError, match="validated plan hash"):
        phase4_live.Phase4ManifestArtifact.model_validate(payload)


def test_provider_summary_rejects_more_than_one_request_per_attempted_case():
    with pytest.raises(ValueError, match="exactly one request"):
        phase4_live.Phase4ProviderSummary(
            provider="openalex",
            attempted_case_count=1,
            successful_case_count=1,
            request_count=2,
            cost_state="known",
            reported_cost_usd=0.0,
            stopped_reason="request_failed",
        )
