"""Frozen-input checks for the runtime-terminal-integrity paid canary.

The suite must never execute this canary. A production root run spends owner
funds and requires later authorization naming the merged and deployed revision.
These checks bind the request, runtime policy, outcome semantics, privacy, and
budget before that authorization can be used.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import get_args

from api.models import RunRequest
from api.runs import TIMEOUT_SECONDS, artifact_names
from academic_agent.run_spec import DecisionContext
from academic_agent.run_terminal import (
    TerminalState,
    TerminationMethod,
    UsageAccountingState,
)
from academic_agent.runtime_budget import (
    FINALIZATION_RESERVE_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    REVIEWER_RESERVE_SECONDS,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    ROOT / "tests/fixtures/runtime_terminal_integrity_paid_canary_manifest.json"
)
PREREG_PATH = (
    ROOT / "docs/prereg-2026-09-04-runtime-terminal-integrity-paid-canary.md"
)
CONSUMED_CANARY_PATH = (
    ROOT / "tests/fixtures/report_decision_seams_paid_canary_manifest.json"
)


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_freezes_one_new_orientation_root_request() -> None:
    manifest = _manifest()
    cases = manifest["cases"]
    consumed = json.loads(CONSUMED_CANARY_PATH.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 1
    assert [case["case_id"] for case in cases] == ["RTI01"]
    assert cases[0]["request"]["topic"] == manifest["topic_selection"]["topic"]
    # The failed RDS01 run is historical evidence, not a reusable paid fixture.
    assert cases[0]["request"]["topic"] != consumed["topic_selection"]["topic"]


def test_frozen_payload_reaches_the_real_request_and_gate_seams() -> None:
    case = _manifest()["cases"][0]

    # RunRequest is the paid POST boundary. Constructing only a topic string
    # would miss an accidental BYOK field or an invalid future API payload.
    request = RunRequest.model_validate(case["request"])
    assert request.assessment_mode == case["expected_assessment_mode"]
    assert request.decision_context is None
    assert request.byok is False
    assert request.model_dump(exclude_none=True) == case["request"]
    assert DecisionContext().gate_snapshot() == case["expected_gate"]


def test_frozen_runtime_contract_matches_the_production_policy() -> None:
    contract = _manifest()["runtime_contract"]

    assert contract["hard_timeout_seconds"] == TIMEOUT_SECONDS == 1800
    assert contract["request_timeout_seconds"] == REQUEST_TIMEOUT_SECONDS == 150
    assert contract["reviewer_reserve_seconds"] == REVIEWER_RESERVE_SECONDS == 240
    assert (
        contract["finalization_reserve_seconds"]
        == FINALIZATION_RESERVE_SECONDS
        == 60
    )
    assert contract["terminal_schema_version"] == 1
    assert set(contract["terminal_states"]) == set(get_args(TerminalState))
    assert set(contract["termination_methods"]) == set(get_args(TerminationMethod))
    assert set(contract["usage_accounting_states"]) == set(
        get_args(UsageAccountingState)
    )


def test_primary_gate_cannot_turn_a_partial_terminal_path_into_a_pass() -> None:
    manifest = _manifest()
    gate = manifest["primary_acceptance"]
    lanes = manifest["outcome_lanes"]

    assert gate["required_terminal_state"] == "completed"
    assert gate["required_reason_code"] == "worker_completed"
    assert gate["required_termination_method"] == "worker_exit"
    assert gate["required_usage_accounting_state"] == "complete"
    assert gate["required_runtime_budget_state"] == "active"
    # Usage is a status/terminal field, not a separately registered download.
    # Checking the real registry prevents a plausible-looking protocol from
    # requesting an artifact that the production route can never deliver.
    assert gate["required_artifacts"] == ["terminal"]
    assert set(gate["required_artifacts"]) <= set(artifact_names())
    assert set(gate["nonpassing_terminal_states"]) == {
        "failed",
        "cancelled",
        "timeout",
    }
    assert set(lanes) == {
        "completed_reviewed",
        "completed_reviewer_fallback",
        "failed",
        "timeout",
        "cancelled",
        "not_inspectable",
    }


def test_manifest_contains_no_credentials_or_open_ended_paid_authority() -> None:
    manifest = _manifest()
    serialized = json.dumps(manifest, sort_keys=True).lower()
    bounds = manifest["execution_bounds"]

    for secret_field in (
        "access_code",
        "api_key",
        "llm_api_key",
        "serper_api_key",
        "authorization",
    ):
        assert secret_field not in serialized
    assert bounds["maximum_root_runs"] == len(manifest["cases"]) == 1
    assert bounds["maximum_runs_per_case"] == 1
    assert bounds["maximum_operator_retries"] == 0
    assert bounds["maximum_resumes"] == 0
    assert bounds["maximum_operator_cancellations"] == 0
    assert bounds["maximum_planner_calls"] == 0
    assert bounds["maximum_supplementary_search_calls"] == 0
    assert 0 < bounds["soft_stop_usd_total"] <= 0.10
    assert bounds["poll_interval_seconds"] >= 10
    assert bounds["maximum_observation_seconds"] > TIMEOUT_SECONDS


def test_preregistration_names_the_exact_committed_manifest_bytes() -> None:
    digest = sha256(MANIFEST_PATH.read_bytes()).hexdigest()
    preregistration = PREREG_PATH.read_text(encoding="utf-8")

    assert f"**Manifest SHA-256:** `{digest}`" in preregistration
