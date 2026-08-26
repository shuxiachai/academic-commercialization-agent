"""Frozen-input checks for the three-mode Decision Context paid canary.

The canary itself is deliberately not executable from the test suite: paid
provider work always requires fresh operator authorization. These checks keep
the future requests at the public API seam and make a case drift visible before
someone spends money against a different question.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from api.models import RunRequest
from academic_agent.run_spec import DecisionContext


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "tests/fixtures/decision_context_paid_canary_manifest.json"
PREREG_PATH = ROOT / "docs/prereg-2026-08-26-decision-context-paid-canary.md"


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_freezes_one_topic_and_exactly_one_case_per_mode() -> None:
    manifest = _manifest()
    cases = manifest["cases"]

    assert manifest["schema_version"] == 1
    assert [case["case_id"] for case in cases] == ["DC01", "DC02", "DC03"]
    assert [case["expected_assessment_mode"] for case in cases] == [
        "orientation",
        "decision_context_incomplete",
        "decision_support",
    ]
    assert {case["request"]["topic"] for case in cases} == {
        manifest["topic_selection"]["topic"]
    }


def test_every_frozen_payload_reaches_the_public_request_and_gate_seams() -> None:
    for case in _manifest()["cases"]:
        # RunRequest is the actual POST boundary. Validating only RunSpec would
        # miss a fixture field that production silently rejects before launch.
        request = RunRequest.model_validate(case["request"])
        context = request.decision_context or DecisionContext()

        assert request.assessment_mode == case["expected_assessment_mode"]
        assert context.gate_snapshot() == case["expected_gate"]
        assert request.byok is False


def test_cases_change_only_decision_context_and_contain_no_credentials() -> None:
    serialized = json.dumps(_manifest()["cases"], sort_keys=True).lower()

    for case in _manifest()["cases"]:
        assert set(case["request"]) <= {"topic", "decision_context"}
    for secret_field in (
        "access_code",
        "api_key",
        "llm_api_key",
        "serper_api_key",
        "authorization",
    ):
        assert secret_field not in serialized


def test_execution_bounds_cannot_turn_a_canary_into_an_open_ended_batch() -> None:
    manifest = _manifest()
    bounds = manifest["execution_bounds"]

    assert bounds["maximum_root_runs"] == len(manifest["cases"]) == 3
    assert bounds["maximum_runs_per_case"] == 1
    assert bounds["maximum_resumes"] == 0
    assert bounds["maximum_supplementary_search_calls"] == 0
    assert 0 < bounds["soft_stop_usd_per_run"] <= 0.05
    assert 0 < bounds["soft_stop_usd_total"] <= 0.12


def test_preregistration_names_the_exact_committed_manifest_bytes() -> None:
    digest = sha256(MANIFEST_PATH.read_bytes()).hexdigest()
    preregistration = PREREG_PATH.read_text(encoding="utf-8")

    assert f"**Manifest SHA-256:** `{digest}`" in preregistration
