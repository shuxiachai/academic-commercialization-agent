"""Frozen-input checks for the report-decision-seams paid canary.

The suite must never execute this canary: a real root run spends operator
funds and therefore requires a later authorization naming the merged revision.
These checks stop request, authority, privacy, or budget drift before that
authorization can be used.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from api.models import RunRequest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    ROOT / "tests/fixtures/report_decision_seams_paid_canary_manifest.json"
)
PREREG_PATH = (
    ROOT / "docs/prereg-2026-09-04-report-decision-seams-paid-canary.md"
)


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_freezes_one_owner_approved_decision_support_case() -> None:
    manifest = _manifest()
    cases = manifest["cases"]

    assert manifest["schema_version"] == 1
    assert [case["case_id"] for case in cases] == ["RDS01"]
    assert [case["expected_assessment_mode"] for case in cases] == [
        "decision_support"
    ]
    assert cases[0]["request"]["topic"] == manifest["topic_selection"]["topic"]


def test_frozen_payload_reaches_request_authority_and_public_gate_seams() -> None:
    case = _manifest()["cases"][0]

    # RunRequest is the real POST boundary. Validating only DecisionContext
    # would miss a fixture field that production rejects before paid launch.
    request = RunRequest.model_validate(case["request"])
    assert request.decision_context is not None
    assert request.assessment_mode == case["expected_assessment_mode"]
    assert request.decision_context.gate_snapshot() == case["expected_gate"]
    assert request.decision_context.threshold_provenance == "owner_approved"
    assert request.byok is False


def test_expected_public_gate_does_not_repeat_the_synthetic_criteria_text() -> None:
    case = _manifest()["cases"][0]
    criteria = case["request"]["decision_context"]["success_criteria"]

    # Field names and authority state are public by design; the bounded gate
    # must not copy the actual criteria text into a status response.
    assert criteria not in json.dumps(case["expected_gate"], sort_keys=True)


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
    assert bounds["maximum_planner_calls"] == 0
    assert bounds["maximum_supplementary_search_calls"] == 0
    assert 0 < bounds["soft_stop_usd_total"] <= 0.10


def test_preregistration_names_the_exact_committed_manifest_bytes() -> None:
    digest = sha256(MANIFEST_PATH.read_bytes()).hexdigest()
    preregistration = PREREG_PATH.read_text(encoding="utf-8")

    assert f"**Manifest SHA-256:** `{digest}`" in preregistration
