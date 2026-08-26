"""Decision-context state, identity, and browser-contract tests.

The product may run from a topic alone, but it must not turn that orientation
brief into actor-specific advice. These tests keep that distinction in code and
also assert the two seams where an earlier feature class disappeared: durable
input identity and the browser request payload.
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from academic_agent.checkpoint_runtime import retrieval_identity
from academic_agent.run_spec import DecisionContext, RunSpec


ROOT = Path(__file__).resolve().parents[1]
CORE_CONTEXT = {
    "asset_description": "A benchtop electrochemical prototype",
    "target_application": "On-site nitrate removal for small water utilities",
    "decision_owner": "University technology transfer manager",
    "decision_type": "Whether to fund a six-month industry pilot",
}


@pytest.mark.parametrize(
    ("context", "mode", "missing", "go_no_go_allowed"),
    [
        (None, "orientation", list(CORE_CONTEXT), False),
        (
            DecisionContext(asset_description="A prototype"),
            "decision_context_incomplete",
            ["target_application", "decision_owner", "decision_type"],
            False,
        ),
        (DecisionContext(**CORE_CONTEXT), "decision_support", [], True),
    ],
)
def test_decision_gate_distinguishes_absence_from_complete_context(
    context: DecisionContext | None,
    mode: str,
    missing: list[str],
    go_no_go_allowed: bool,
) -> None:
    spec = RunSpec(topic="electrochemical nitrate removal", decision_context=context)

    assert spec.assessment_mode == mode
    assert spec.decision_gate() == {
        "status": "checked",
        "mode": mode,
        "provided_fields": list(context.provided_fields) if context else [],
        "missing_core_fields": missing,
        "go_no_go_allowed": go_no_go_allowed,
    }


def test_context_is_normalized_before_persistence_and_prompting() -> None:
    spec = RunSpec.model_validate(
        {
            "topic": "electrochemical nitrate removal",
            "decision_context": {
                **CORE_CONTEXT,
                "decision_owner": "  University\n technology transfer manager  ",
                "constraints": "  No new pilot plant\tbefore board approval  ",
            },
        }
    )

    assert spec.decision_context is not None
    assert spec.decision_context.decision_owner == "University technology transfer manager"
    prompt_context = json.loads(spec.decision_crew_inputs()["decision_context_json"])
    assert prompt_context["constraints"] == "No new pilot plant before board approval"
    assert spec.decision_crew_inputs()["assessment_mode"] == "decision_support"


def test_empty_context_has_the_same_identity_as_omission() -> None:
    omitted = RunSpec(topic="electrochemical nitrate removal")
    empty = RunSpec.model_validate(
        {"topic": "electrochemical nitrate removal", "decision_context": {}}
    )

    assert empty.decision_context is None
    assert empty.model_dump(mode="json") == omitted.model_dump(mode="json")


def test_unknown_or_oversized_context_is_rejected_before_a_run_can_start() -> None:
    with pytest.raises(ValidationError):
        DecisionContext.model_validate({"investment_advice": "buy"})
    with pytest.raises(ValidationError):
        DecisionContext(asset_description="x" * 501)


def test_version_one_run_specs_remain_readable_as_orientation_runs() -> None:
    legacy = RunSpec.model_validate(
        {"schema_version": 1, "topic": "legacy solid-state battery run"}
    )

    assert legacy.schema_version == 1
    assert legacy.assessment_mode == "orientation"
    assert legacy.decision_gate()["status"] == "checked"


def test_decision_context_is_part_of_checkpoint_input_identity() -> None:
    kwargs = {"revision": "git:abcdef012345", "as_of_date": date(2026, 8, 26)}
    orientation = retrieval_identity(
        RunSpec(topic="electrochemical nitrate removal"), **kwargs
    )
    decision_support = retrieval_identity(
        RunSpec(
            topic="electrochemical nitrate removal",
            decision_context=DecisionContext(**CORE_CONTEXT),
        ),
        **kwargs,
    )

    assert orientation.input_sha256 != decision_support.input_sha256


def test_public_gate_exposes_coverage_without_repeating_user_prose() -> None:
    context = DecisionContext(**CORE_CONTEXT, constraints="Confidential budget ceiling")
    serialized = json.dumps(context.gate_snapshot())

    assert "Confidential budget ceiling" not in serialized
    assert set(context.gate_snapshot()["provided_fields"]) == {
        *CORE_CONTEXT,
        "constraints",
    }


def test_writer_and_reviewer_receive_the_frozen_decision_contract() -> None:
    tasks = (ROOT / "src/academic_agent/config/tasks.yaml").read_text(encoding="utf-8")
    agents = (ROOT / "src/academic_agent/config/agents.yaml").read_text(encoding="utf-8")

    for placeholder in (
        "{assessment_mode}",
        "{decision_context_json}",
        "{decision_mode_guidance}",
    ):
        assert tasks.count(placeholder) >= 2
    assert "GO/NO_GO is not assessed" in tasks
    assert "Rule 7 — Decision applicability" in agents


def test_every_browser_field_reaches_the_json_request_contract() -> None:
    index = (ROOT / "web/index.html").read_text(encoding="utf-8")
    app = (ROOT / "web/static/js/app.js").read_text(encoding="utf-8")
    api = (ROOT / "web/static/js/api.js").read_text(encoding="utf-8")

    for field in (*CORE_CONTEXT, "jurisdiction", "time_horizon", "constraints"):
        assert f'data-context-field="{field}"' in index
    assert "decision_context: readDecisionContext()" in app
    assert "decision_context: decision_context || null" in api
