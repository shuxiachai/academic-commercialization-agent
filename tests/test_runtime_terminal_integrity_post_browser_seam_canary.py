"""Frozen checks for the post-browser-seam runtime integrity canary.

The predecessor authorization reached admission only. These tests preserve
that zero-request fact, bind the replacement request to the production API and
runtime policy, and make the browser reason/method projection part of the
frozen boundary. The suite never submits a run or opens a socket.
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
    ROOT
    / "tests/fixtures/runtime_terminal_integrity_post_browser_seam_canary_manifest.json"
)
PREREG_PATH = (
    ROOT
    / "docs/prereg-2026-09-04-runtime-terminal-integrity-post-browser-seam-paid-canary.md"
)
PREDECESSOR_RESULT_PATH = (
    ROOT / "docs/results-2026-09-04-runtime-terminal-integrity-paid-canary-preflight.md"
)
RUN_JS_PATH = ROOT / "web/static/js/run.js"
APP_JS_PATH = ROOT / "web/static/js/app.js"
I18N_JS_PATH = ROOT / "web/static/js/i18n.js"
INDEX_PATH = ROOT / "web/index.html"


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_replacement_preserves_an_unconsumed_orientation_request() -> None:
    manifest = _manifest()
    predecessor = manifest["predecessor"]
    case = manifest["cases"][0]
    result = PREDECESSOR_RESULT_PATH.read_text(encoding="utf-8")

    assert [item["case_id"] for item in manifest["cases"]] == ["RTI02"]
    assert case["request"]["topic"] == manifest["topic_selection"]["topic"]
    assert predecessor["outcome"] == "not_started / preflight_failed"
    assert predecessor["root_runs_submitted"] == 0
    assert predecessor["provider_or_search_requests"] == 0
    assert predecessor["cost_usd"] == 0.0
    assert "Root runs submitted | 0" in result
    assert "Paid provider or search requests: **0**" in result


def test_frozen_payload_reaches_the_real_request_and_gate_seams() -> None:
    case = _manifest()["cases"][0]

    request = RunRequest.model_validate(case["request"])
    assert request.assessment_mode == case["expected_assessment_mode"]
    assert request.decision_context is None
    assert request.byok is False
    assert request.model_dump(exclude_none=True) == case["request"]
    assert DecisionContext().gate_snapshot() == case["expected_gate"]


def test_runtime_contract_still_matches_production_policy() -> None:
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


def test_browser_contract_is_bound_to_shipped_code_and_markup() -> None:
    browser = _manifest()["browser_contract"]
    run_js = RUN_JS_PATH.read_text(encoding="utf-8")
    app_js = APP_JS_PATH.read_text(encoding="utf-8")
    i18n_js = I18N_JS_PATH.read_text(encoding="utf-8")
    markup = INDEX_PATH.read_text(encoding="utf-8")

    assert f'id="{browser["element_id"]}"' in markup
    assert f'$("#{browser["element_id"]}")' in app_js
    assert "terminalSummary(terminal, state)" in app_js
    assert "terminalTitle(terminal, state)" in app_js
    assert "export function terminalSummary" in run_js
    assert "export function terminalTitle" in run_js
    for reason, label in browser["known_reason_labels"].items():
        assert reason in run_js
        assert label in i18n_js
    for field in browser["tooltip_fields"]:
        assert f"terminal.{field}" in run_js
    assert browser["missing_terminal_on_terminal_state"] in i18n_js
    assert browser["unreadable_record"] in i18n_js


def test_primary_gate_cannot_promote_a_partial_terminal_path() -> None:
    manifest = _manifest()
    gate = manifest["primary_acceptance"]

    assert gate["required_terminal_state"] == "completed"
    assert gate["required_reason_code"] == "worker_completed"
    assert gate["required_termination_method"] == "worker_exit"
    assert gate["required_usage_accounting_state"] == "complete"
    assert gate["required_runtime_budget_state"] == "active"
    assert gate["required_artifacts"] == ["terminal"]
    assert set(gate["required_artifacts"]) <= set(artifact_names())
    assert set(gate["required_public_seams"]) == {"status", "progress", "browser"}
    assert set(gate["required_browser_observations"]) == {
        "translated_reason",
        "raw_reason_code",
        "raw_termination_method",
    }
    assert set(gate["nonpassing_terminal_states"]) == {
        "failed",
        "cancelled",
        "timeout",
    }


def test_manifest_contains_no_secret_or_open_ended_paid_authority() -> None:
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


def test_preregistration_names_exact_committed_manifest_bytes() -> None:
    digest = sha256(MANIFEST_PATH.read_bytes()).hexdigest()
    preregistration = PREREG_PATH.read_text(encoding="utf-8")

    assert f"**Manifest SHA-256:** `{digest}`" in preregistration
