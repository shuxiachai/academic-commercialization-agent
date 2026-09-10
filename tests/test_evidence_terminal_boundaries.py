"""Mechanical evidence checks and operational terminal truth at their consumers."""

from datetime import UTC, datetime
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import ops_report
from academic_agent.claim_grounding import _supported, check_report
from academic_agent.run_terminal import TerminalRecord, UsageAccounting, commit_terminal_record
from academic_agent.scoring_contract import make_scoring_guardrail
from api import runs
from tests.test_scoring_guardrail import _run, _KNOWN
from tests.test_crew_wiring import _make_collection


@pytest.mark.parametrize("claim,source", [
    ("10%", "100%"), ("100 MW", "1000 MW"), ("26.1%", "26.19 MW"),
    ("1000", "10000"), ("10.1%", "10.19 million"),
])
def test_order_and_unit_errors_survive_the_findings_to_audit_seam(claim, source):
    report = SimpleNamespace(
        findings=[SimpleNamespace(finding_id="F1", claim=f"Measured {claim}.", source_ids=["A1"])],
        sources=[SimpleNamespace(source_id="A1", evidence_summary=source + " Supporting prose." * 40,
                                 summary_source="abstract")],
    )
    audit = check_report(report).as_dict()
    assert audit["checked"] == 1
    assert audit["ungrounded"] == 1
    assert audit["findings"][0]["finding_id"] == "F1"
    assert "error" not in audit


@pytest.mark.parametrize("claim,source", [
    ("26.1", "26.15"), ("26.2", "26.15"), ("100", "100.0"), ("0.12", "0.123"),
])
def test_decimal_quotation_precision_is_not_a_false_accusation(claim, source):
    assert _supported(claim, "%", [(source, "%")], source + "%")


def test_unitless_fallback_does_not_match_inside_a_longer_number():
    assert not _supported("1000", "", [], "reported 10000 citations")
    assert _supported("1000", "", [], "reported 1,000 citations")


@pytest.mark.parametrize("field,ids", [
    ("patent_source_ids", ["A1"]), ("market_source_ids", ["P1"]),
    ("trl_source_ids", ["P1"]), ("mrl_source_ids", ["P1"]),
])
def test_existing_but_wrong_domain_cannot_reach_saved_scorecard(field, ids):
    ok, error = _run(make_scoring_guardrail(known_source_ids=_KNOWN), **{field: ids})
    assert not ok
    assert field in error and "wrong domain" in error


@pytest.mark.parametrize("field", [
    "trl_rationale", "mrl_rationale", "patent_rationale", "market_rationale",
    "evidence_rationale", "scoring_rationale", "key_risks", "key_opportunities",
])
def test_phantom_citations_in_each_prose_surface_are_rejected(field):
    value = "A decision statement citing a nonexistent source [M999]."
    if field.startswith("key_"):
        value = [value]
    ok, error = _run(make_scoring_guardrail(known_source_ids=_KNOWN), **{field: value})
    assert not ok
    assert "M999" in error


def test_valid_domain_and_prose_refs_keep_the_existing_formula():
    plain_ok, plain = _run(make_scoring_guardrail(known_source_ids=_KNOWN))
    cited_ok, cited = _run(make_scoring_guardrail(known_source_ids=_KNOWN),
                          market_rationale="Observed market adoption [M1].")
    assert plain_ok and cited_ok
    assert cited["overall_score"] == plain["overall_score"]
    assert cited["score_formula"] == plain["score_formula"]


@pytest.mark.parametrize("field", ["trl_source_ids", "mrl_source_ids"])
def test_process_patents_can_supplement_but_not_replace_maturity_anchors(field):
    ok, result = _run(make_scoring_guardrail(known_source_ids=_KNOWN),
                      **{field: ["A1", "P1", "M1"]})
    assert ok
    assert result[field] == ["A1", "P1", "M1"]


def test_production_crew_scoring_task_enforces_the_new_contract(monkeypatch):
    """A correct standalone wrapper is useless if Crew still imports legacy."""
    from academic_agent.crew import AcademicAgent

    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-placeholder")
    guardrail = AcademicAgent(_make_collection()).crew().tasks[5].guardrail
    ok, error = _run(guardrail, patent_source_ids=["A1"])
    assert not ok and "wrong domain" in error
    ok, error = _run(guardrail, market_rationale="Unknown source [M999].")
    assert not ok and "M999" in error
    ok, result = _run(guardrail, mrl_source_ids=["A1", "P1"])
    assert ok and result["mrl_source_ids"] == ["A1", "P1"]


def test_local_recovery_identity_changes_with_production_citation_contract(monkeypatch):
    """A local resume must not reuse scores admitted under obsolete rules."""
    from pathlib import Path
    from academic_agent import checkpoint_runtime

    for name in checkpoint_runtime._REVISION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    before = checkpoint_runtime.pipeline_revision()
    read = Path.read_bytes

    def changed(path):
        value = read(path)
        return value + b"\n# changed admission\n" if path.name == "scoring_contract.py" else value

    monkeypatch.setattr(Path, "read_bytes", changed)
    assert checkpoint_runtime.pipeline_revision() != before


@pytest.mark.parametrize("state", ["completed", "failed", "cancelled", "timeout"])
@pytest.mark.parametrize("legacy", [{"done": True}, {"error": "stale error"}, ["malformed"], None])
def test_ops_outcome_matches_core_api_despite_conflicting_legacy_artifacts(tmp_path, state, legacy):
    """A committed terminal must beat status errors, missing status and markers."""
    run_id = "20260910T000000Z-abcdef123456"
    directory = tmp_path / run_id
    directory.mkdir()
    if legacy is not None:
        (directory / "status.json").write_text(json.dumps(legacy), encoding="utf-8")
    (directory / "cancelled.marker").write_text("stale", encoding="utf-8")
    now = datetime.now(UTC)
    record = TerminalRecord(
        state=state, reason_code="fixture_outcome", termination_method="worker_exit",
        started_at=now, ended_at=now, elapsed_seconds=0,
        usage_accounting=UsageAccounting(state="unavailable", snapshot_at=now,
                                        run_complete=state == "completed",
                                        in_flight_request_may_have_spent=False),
    )
    commit_terminal_record(directory, record)
    with patch.object(runs, "DEFAULT_OUTPUT_ROOT", tmp_path):
        api_state = runs.get_state(run_id)
    collected = ops_report.collect(tmp_path)
    assert collected[0]["outcome"] == state == api_state["state"]
    assert collected[0]["outcome_basis"] == "terminal.json"


def test_unreadable_terminal_cannot_be_counted_as_completed(tmp_path):
    directory = tmp_path / "20260910T000000Z-abcdef123456"
    directory.mkdir()
    (directory / "status.json").write_text('{"done": true}', encoding="utf-8")
    (directory / "terminal.json").write_text('{"state":"timeout"}', encoding="utf-8")
    record = ops_report.collect(tmp_path)[0]
    assert record["outcome"] == "unknown"
    assert record["outcome_basis"] == "unreadable terminal.json"
