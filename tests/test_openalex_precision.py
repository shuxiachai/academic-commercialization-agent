"""Tests for the production-disconnected OpenAlex precision-v2 gate."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from academic_agent.openalex_precision import (
    AcademicPrecisionProfile,
    evaluate_academic_candidate,
)
from academic_agent.tools.evidence_search import ToolEvidenceCandidate


_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE = _ROOT / "tests/fixtures/openalex_precision_v2_challenge.json"


def _candidate(
    *,
    title: str,
    summary: str,
    url: str = "https://openalex.org/W1234567890",
) -> ToolEvidenceCandidate:
    return ToolEvidenceCandidate(
        title=title,
        url=url,
        publisher="Frozen Test Publisher",
        evidence_summary=summary,
        summary_source="abstract",
        provider_result_index=0,
    )


def _profile(case_id: str) -> AcademicPrecisionProfile:
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    raw = next(
        item for item in fixture["development_profiles"] if item["case_id"] == case_id
    )
    return AcademicPrecisionProfile.model_validate(
        {key: value for key, value in raw.items() if key != "case_id"}
    )


class OpenAlexPrecisionTests(unittest.TestCase):
    def test_complete_token_matching_does_not_find_pet_inside_carpet(self) -> None:
        profile = AcademicPrecisionProfile.model_validate(
            {
                "required_groups": [
                    {"group_id": "pet_polymer", "phrases": ["pet"]},
                    {
                        "group_id": "depolymerization",
                        "phrases": ["depolymerization"],
                    },
                ],
                "supporting_groups": [
                    {"group_id": "enzyme", "phrases": ["enzymatic"]},
                    {"group_id": "performance", "phrases": ["conversion"]},
                ],
                "minimum_supporting_groups": 2,
                "minimum_title_required_groups": 1,
            }
        )
        decision = evaluate_academic_candidate(
            _candidate(
                title="Enzymatic carpet depolymerization",
                summary="The study reports enzymatic conversion.",
            ),
            profile,
        )

        self.assertEqual(decision.action, "ABSTAIN")
        self.assertEqual(decision.missing_required_groups, ("pet_polymer",))

    def test_punctuation_normalization_preserves_full_phrase_matching(self) -> None:
        decision = evaluate_academic_candidate(
            _candidate(
                title="Cell-free carbon fixation pathway",
                summary="A synthetic enzymatic cycle reports an efficient rate.",
            ),
            _profile("D03"),
        )

        self.assertEqual(decision.action, "ACCEPT")
        self.assertEqual(
            decision.matched_required_groups,
            ("carbon_fixation", "noncellular_route"),
        )
        self.assertEqual(decision.title_required_groups, decision.matched_required_groups)

    def test_duplicate_phrase_across_independent_groups_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            ValidationError,
            "normalized phrase appears in multiple concept groups",
        ):
            AcademicPrecisionProfile.model_validate(
                {
                    "required_groups": [
                        {"group_id": "first_group", "phrases": ["damp-heat"]},
                        {"group_id": "second_group", "phrases": ["perovskite"]},
                    ],
                    "supporting_groups": [
                        {"group_id": "third_group", "phrases": ["damp heat"]},
                        {"group_id": "fourth_group", "phrases": ["module"]},
                    ],
                    "minimum_supporting_groups": 1,
                    "minimum_title_required_groups": 1,
                }
            )

    def test_original_plant_ros_false_acceptance_is_now_abstained(self) -> None:
        # This is one of the exact wrong-source identities from the completed
        # development review.  Its broad pathway vocabulary used to reach the
        # additive score, but it has no cell-free carbon-fixation evidence.
        candidate = _candidate(
            title=(
                "Reactive Oxygen Species, Oxidative Damage, and Antioxidative "
                "Defense Mechanism in Plants under Stressful Conditions"
            ),
            summary=(
                "Plant cellular metabolism produces reactive oxygen species. "
                "Enzymatic antioxidants and stress signaling pathways defend "
                "living tissues against oxidative damage."
            ),
            url="https://openalex.org/W2041493424",
        )
        decision = evaluate_academic_candidate(candidate, _profile("D03"))

        self.assertEqual(decision.action, "ABSTAIN")
        self.assertEqual(decision.missing_required_groups, ("carbon_fixation",))
        self.assertIn("noncellular_route", decision.matched_required_groups)
        self.assertIn("missing_required_groups", decision.abstention_reasons)

    def test_relevant_development_carbon_fixation_source_is_accepted(self) -> None:
        candidate = _candidate(
            title=(
                "Natural carbon fixation and advances in synthetic engineering "
                "for redesigning and creating new fixation pathways"
            ),
            summary=(
                "The review covers efficient in vitro synthetic pathways and "
                "the redesign of enzymatic carbon-fixation cycles."
            ),
            url="https://openalex.org/W4288808193",
        )
        decision = evaluate_academic_candidate(candidate, _profile("D03"))

        self.assertEqual(decision.action, "ACCEPT")
        self.assertEqual(decision.missing_required_groups, ())
        self.assertEqual(decision.abstention_reasons, ())

    def test_decision_serialization_preserves_declared_group_order(self) -> None:
        decision = evaluate_academic_candidate(
            _candidate(
                title="Plasma synthesis of ammonia",
                summary="Catalyst-free production has measured energy efficiency.",
            ),
            _profile("D01"),
        )
        restored = type(decision).model_validate_json(decision.model_dump_json())

        self.assertEqual(restored, decision)
        self.assertEqual(
            restored.matched_supporting_groups,
            (
                "synthesis_or_formation",
                "performance_measure",
                "catalyst_context",
            ),
        )

    def test_production_worker_remains_disconnected(self) -> None:
        worker = (_ROOT / "src/academic_agent/pipeline_worker.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("openalex_precision", worker)
        self.assertNotIn("openalex_precision_audit", worker)


if __name__ == "__main__":
    unittest.main()
