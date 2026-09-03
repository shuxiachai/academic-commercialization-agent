"""Decision applicability and threshold-authority delivery seam tests.

The model may write persuasive prose, but it does not own the decision mode or
the authority behind a threshold.  These tests keep both facts code-derived,
durable, and visible in the exact report bytes a client downloads.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from pydantic import ValidationError

from academic_agent.checkpoint_runtime import retrieval_identity
from academic_agent.report_applicability import add_applicability_block
from academic_agent.run_output import save_report
from academic_agent.run_spec import DecisionContext, RunSpec


ROOT = Path(__file__).resolve().parents[1]
CORE_CONTEXT = {
    "asset_description": "A benchtop electrochemical prototype",
    "target_application": "On-site nitrate removal for small water utilities",
    "decision_owner": "University technology transfer manager",
    "decision_type": "Whether to fund a six-month industry pilot",
}


@pytest.mark.parametrize(
    ("criteria", "authority", "expected"),
    [
        (None, None, "not_established"),
        ("Removal efficiency must exceed 90%.", None, "user_supplied_unapproved"),
        (
            "Removal efficiency must exceed 90%.",
            "owner_approved",
            "owner_approved",
        ),
    ],
)
def test_threshold_provenance_distinguishes_three_authority_states(
    criteria: str | None,
    authority: str | None,
    expected: str,
) -> None:
    context = DecisionContext(
        **CORE_CONTEXT,
        success_criteria=criteria,
        success_criteria_authority=authority,
    )

    snapshot = context.gate_snapshot()["threshold_provenance"]

    assert snapshot["status"] == expected
    assert snapshot["criteria_supplied"] is (criteria is not None)
    assert snapshot["owner_approval_declared"] is (authority is not None)


def test_a_bare_authority_flag_cannot_manufacture_an_approved_threshold() -> None:
    with pytest.raises(ValidationError, match="requires supplied success_criteria"):
        DecisionContext(success_criteria_authority="owner_approved")


def test_old_run_specs_remain_readable_and_new_specs_write_version_three() -> None:
    for version in (1, 2):
        legacy = RunSpec.model_validate(
            {"schema_version": version, "topic": "legacy battery assessment"}
        )
        assert legacy.schema_version == version
        assert legacy.decision_gate()["threshold_provenance"]["status"] == (
            "not_established"
        )

    assert RunSpec(topic="new assessment").schema_version == 3


def test_criteria_and_authority_each_change_the_checkpoint_input_identity() -> None:
    identity_kwargs = {
        "revision": "git:abcdef012345",
        "as_of_date": date(2026, 9, 3),
    }
    without_criteria = RunSpec(
        topic="electrochemical nitrate removal",
        decision_context=DecisionContext(**CORE_CONTEXT),
    )
    unapproved = RunSpec(
        topic="electrochemical nitrate removal",
        decision_context=DecisionContext(
            **CORE_CONTEXT,
            success_criteria="Removal efficiency must exceed 90%.",
        ),
    )
    approved = RunSpec(
        topic="electrochemical nitrate removal",
        decision_context=DecisionContext(
            **CORE_CONTEXT,
            success_criteria="Removal efficiency must exceed 90%.",
            success_criteria_authority="owner_approved",
        ),
    )

    identities = {
        retrieval_identity(spec, **identity_kwargs).input_sha256
        for spec in (without_criteria, unapproved, approved)
    }

    assert len(identities) == 3


def test_public_gate_exposes_authority_without_repeating_private_criteria() -> None:
    secret_criteria = "Confidential board hurdle: margin must exceed 37%."
    context = DecisionContext(
        **CORE_CONTEXT,
        success_criteria=secret_criteria,
        success_criteria_authority="owner_approved",
    )

    snapshot = context.gate_snapshot()

    assert secret_criteria not in str(snapshot)
    assert snapshot["threshold_provenance"]["status"] == "owner_approved"


@pytest.mark.parametrize(
    ("context", "expected_phrase"),
    [
        (DecisionContext(**CORE_CONTEXT), "analyst proposal"),
        (
            DecisionContext(
                **CORE_CONTEXT,
                success_criteria="Removal efficiency must exceed 90%.",
            ),
            "pending approval",
        ),
        (
            DecisionContext(
                **CORE_CONTEXT,
                success_criteria="Removal efficiency must exceed 90%.",
                success_criteria_authority="owner_approved",
            ),
            "explicitly declared owner-approved",
        ),
    ],
)
def test_prompt_contract_names_threshold_authority_without_inferring_it(
    context: DecisionContext,
    expected_phrase: str,
) -> None:
    guidance = context.crew_inputs()["decision_mode_guidance"]

    assert expected_phrase in guidance
    assert "cited external benchmark" in guidance.lower()


def test_save_report_inserts_code_owned_applicability_after_the_title() -> None:
    context = DecisionContext(
        **CORE_CONTEXT,
        success_criteria="Removal efficiency must exceed 90%.",
    )
    with TemporaryDirectory() as temporary_directory:
        _, path = save_report(
            "# Commercialization report\n\n## Evidence\n\nBody.\n",
            run_id="run-authority",
            output_root=Path(temporary_directory),
            decision_gate=context.gate_snapshot(),
            output_language="English",
        )
        delivered = path.read_text(encoding="utf-8")

    assert delivered.index("# Commercialization report") < delivered.index(
        "<!-- decision-applicability:v1 -->"
    )
    assert "Mode `decision_support`" in delivered
    assert "`user_supplied_unapproved`" in delivered
    assert delivered.index("decision-applicability:v1") < delivered.index("## Evidence")


def test_applicability_insertion_is_idempotent() -> None:
    gate = DecisionContext(**CORE_CONTEXT).gate_snapshot()
    once = add_applicability_block(
        "# Report\n\nBody.", decision_gate=gate, output_language="English"
    )
    twice = add_applicability_block(
        once, decision_gate=gate, output_language="English"
    )

    assert twice == once
    assert twice.count("decision-applicability:v1") == 1


def test_chinese_report_receives_localized_code_owned_applicability() -> None:
    delivered = add_applicability_block(
        "# 商业化报告\n\n正文。",
        decision_gate=DecisionContext().gate_snapshot(),
        output_language="Simplified Chinese",
    )

    assert "评估适用范围（代码判定）" in delivered
    assert "未评估针对具体决策者的 `GO/NO_GO`" in delivered
    assert "`not_established`" in delivered


def test_a_legacy_save_without_a_gate_keeps_the_report_bytes_unchanged() -> None:
    original = "# Legacy report\n\nOriginal bytes.\n"
    with TemporaryDirectory() as temporary_directory:
        _, path = save_report(
            original,
            run_id="legacy-run",
            output_root=Path(temporary_directory),
        )

        assert path.read_text(encoding="utf-8") == original


def test_browser_collects_both_threshold_fields_and_renders_the_gate() -> None:
    index = (ROOT / "web/index.html").read_text(encoding="utf-8")
    result = (ROOT / "web/static/js/result.js").read_text(encoding="utf-8")

    assert 'data-context-field="success_criteria"' in index
    assert 'data-context-field="success_criteria_authority"' in index
    assert "decisionApplicability(progress.decision_gate)" not in result
    assert "renderDecisionApplicability(progress.decision_gate)" in result
    assert "gate.threshold_provenance?.status" in result
