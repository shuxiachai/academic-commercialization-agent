"""Tests for the scoring guardrail — the last line of defence on the scorecard.

This is the component that makes the numbers trustworthy:

  * source IDs cited by the scorer must actually exist, or the scorecard would
    claim provenance it does not have;
  * overall_score is recomputed from the dimension scores rather than trusted,
    because an LLM adding five weighted terms is a coin flip;
  * the ×10 integer scale the model writes in is normalised on the way out.

All of it runs silently — a wrong score looks exactly like a right one — which
is why it needs tests rather than eyeballing.
"""

from __future__ import annotations

import json
import unittest

from academic_agent.evidence import _WEIGHT_PROFILES, make_scoring_guardrail


class _Output:
    """Stand-in for crewai's TaskOutput."""

    def __init__(self, raw: str):
        self.raw = raw
        self.pydantic = None


def _score_payload(**overrides) -> dict:
    """A valid scorecard as the LLM would emit it (×10 integer scale)."""
    payload = {
        "trl_score": 60,                 # → 6.0
        "trl_rationale": "Pilot line demonstrated at industrial scale in 2024.",
        "trl_source_ids": ["A1"],
        "mrl_score": 50,                 # → 5.0
        "mrl_rationale": "Manufacturing validated on a pre-production line.",
        "mrl_source_ids": ["A1"],
        "patent_strength": 30,           # → 3.0
        "patent_rationale": "Several holders but clear white space remains.",
        "patent_source_ids": ["P1"],
        "market_accessibility": 40,      # → 4.0
        "market_rationale": "Multiple vendors ship commercial product today.",
        "market_source_ids": ["M1"],
        "evidence_confidence": 40,       # → 4.0
        "evidence_rationale": "Independent confirmation across three domains.",
        "evidence_source_ids": ["A1", "P1", "M1"],
        "overall_score": 0,              # scorer always writes 0; formula fills it
        "scoring_rationale": "Balanced profile with solid commercial traction.",
        "key_risks": ["Supply chain concentration in a single region."],
        "key_opportunities": ["Regulatory tailwinds in the EU from 2026."],
    }
    payload.update(overrides)
    return payload


def _run(guardrail, **overrides):
    """Run the guardrail and return (ok, parsed_dict_or_message)."""
    ok, result = guardrail(_Output(json.dumps(_score_payload(**overrides))))
    return (ok, json.loads(result.raw)) if ok else (ok, result)


_KNOWN = frozenset({"A1", "A2", "P1", "M1"})


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

class SchemaValidationTests(unittest.TestCase):

    def test_valid_payload_accepted(self):
        ok, _ = _run(make_scoring_guardrail())
        self.assertTrue(ok)

    def test_malformed_json_rejected_with_guidance(self):
        ok, msg = make_scoring_guardrail()(_Output("not json at all"))
        self.assertFalse(ok)
        self.assertIn("JSON", msg)

    def test_markdown_fenced_json_rejected(self):
        """A fenced block is the most common way the scorer breaks the contract."""
        fenced = "```json\n" + json.dumps(_score_payload()) + "\n```"
        ok, msg = make_scoring_guardrail()(_Output(fenced))
        self.assertFalse(ok)
        self.assertIn("fences", msg.lower())

    def test_out_of_range_score_rejected(self):
        ok, msg = _run(make_scoring_guardrail(), trl_score=999)
        self.assertFalse(ok)
        self.assertIn("Validation error", msg)

    def test_missing_required_field_rejected(self):
        payload = _score_payload()
        del payload["trl_rationale"]
        ok, msg = make_scoring_guardrail()(_Output(json.dumps(payload)))
        self.assertFalse(ok)


# ---------------------------------------------------------------------------
# Hallucinated source IDs
# ---------------------------------------------------------------------------

class SourceIdValidationTests(unittest.TestCase):

    def test_known_ids_accepted(self):
        ok, _ = _run(make_scoring_guardrail(known_source_ids=_KNOWN))
        self.assertTrue(ok)

    def test_invented_id_rejected(self):
        """A citation to A9 when the pool ends at A2 is a fabricated provenance."""
        ok, msg = _run(make_scoring_guardrail(known_source_ids=_KNOWN),
                       trl_source_ids=["A9"])
        self.assertFalse(ok)
        self.assertIn("A9", msg)

    def test_rejection_message_lists_valid_ids(self):
        """The retry prompt has to tell the model what it may cite."""
        ok, msg = _run(make_scoring_guardrail(known_source_ids=_KNOWN),
                       market_source_ids=["M7"])
        self.assertFalse(ok)
        self.assertIn("A1", msg)

    def test_malformed_id_rejected(self):
        ok, msg = _run(make_scoring_guardrail(known_source_ids=_KNOWN),
                       patent_source_ids=["patent-1"])
        self.assertFalse(ok)
        self.assertIn("invalid source IDs", msg)

    def test_lowercase_id_rejected(self):
        ok, _ = _run(make_scoring_guardrail(known_source_ids=_KNOWN),
                     trl_source_ids=["a1"])
        self.assertFalse(ok)

    def test_every_id_field_is_checked(self):
        fields = ("trl_source_ids", "mrl_source_ids", "patent_source_ids",
                  "market_source_ids", "evidence_source_ids")
        for field in fields:
            with self.subTest(field=field):
                ok, _ = _run(make_scoring_guardrail(known_source_ids=_KNOWN),
                             **{field: ["Z9"]})
                self.assertFalse(ok)

    def test_ids_not_checked_when_pool_unknown(self):
        """Without a source pool, format is all that can be verified."""
        ok, _ = _run(make_scoring_guardrail(), trl_source_ids=["A99"])
        self.assertTrue(ok)


# ---------------------------------------------------------------------------
# Score normalisation and formula
# ---------------------------------------------------------------------------

class ScoreNormalisationTests(unittest.TestCase):

    def test_integer_scale_divided_by_ten(self):
        _, out = _run(make_scoring_guardrail())
        self.assertEqual(out["trl_score"], 6.0)
        self.assertEqual(out["mrl_score"], 5.0)
        self.assertEqual(out["patent_strength"], 3.0)
        self.assertEqual(out["market_accessibility"], 4.0)

    def test_trl_label_derived_from_score(self):
        _, out = _run(make_scoring_guardrail())
        self.assertTrue(out["trl_label"])

    def test_overall_recomputed_not_trusted(self):
        """The scorer writes 0; the guardrail must fill in the real number."""
        _, out = _run(make_scoring_guardrail(), overall_score=0)
        self.assertGreater(out["overall_score"], 0)

    def test_wrong_overall_is_overwritten(self):
        _, out = _run(make_scoring_guardrail(), overall_score=99.9)
        self.assertNotEqual(out["overall_score"], 99.9)
        self.assertTrue(out["auto_corrected"])

    def test_formula_matches_industrial_weights(self):
        w = _WEIGHT_PROFILES["industrial"]
        expected = round(
            (4.0 / 5) * w["market"] + (6.0 / 9) * w["trl"] + (5.0 / 10) * w["mrl"]
            + (3.0 / 5) * w["patent"] + (4.0 / 5) * w["evidence"], 1
        )
        _, out = _run(make_scoring_guardrail("industrial"))
        self.assertEqual(out["overall_score"], expected)

    def test_profile_changes_the_result(self):
        """Same dimensions, different domain → different overall score."""
        _, industrial = _run(make_scoring_guardrail("industrial"))
        _, biomedical = _run(make_scoring_guardrail("biomedical"))
        self.assertNotEqual(industrial["overall_score"], biomedical["overall_score"])

    def test_every_profile_produces_a_valid_score(self):
        for profile in _WEIGHT_PROFILES:
            with self.subTest(profile=profile):
                _, out = _run(make_scoring_guardrail(profile))
                self.assertGreaterEqual(out["overall_score"], 0)
                self.assertLessEqual(out["overall_score"], 100)

    def test_unknown_profile_falls_back_to_industrial(self):
        _, unknown = _run(make_scoring_guardrail("no_such_profile"))
        _, industrial = _run(make_scoring_guardrail("industrial"))
        self.assertEqual(unknown["overall_score"], industrial["overall_score"])

    def test_formula_string_records_the_profile(self):
        _, out = _run(make_scoring_guardrail("biomedical"))
        self.assertIn("biomedical", out["score_formula"])

    def test_max_scores_approach_one_hundred(self):
        _, out = _run(make_scoring_guardrail(), trl_score=90, mrl_score=100,
                      patent_strength=50, market_accessibility=50,
                      evidence_confidence=50)
        self.assertAlmostEqual(out["overall_score"], 100.0, places=1)

    def test_min_scores_stay_low(self):
        _, out = _run(make_scoring_guardrail(), trl_score=10, mrl_score=10,
                      patent_strength=10, market_accessibility=10,
                      evidence_confidence=10)
        self.assertLess(out["overall_score"], 25)


# ---------------------------------------------------------------------------
# Evidence-confidence floor
# ---------------------------------------------------------------------------

class _Source:
    def __init__(self, tier: str):
        self.credibility_tier = tier


class EvidenceFloorTests(unittest.TestCase):
    """A solid source pool sets a floor under evidence_confidence.

    Without it the scorer sometimes reports low confidence despite every
    source being high-credibility, which drags the overall score down for no
    evidential reason.
    """

    def test_all_high_tier_lifts_low_confidence(self):
        sources = [_Source("high")] * 4
        _, out = _run(make_scoring_guardrail(all_sources=sources),
                      evidence_confidence=10)
        self.assertEqual(out["evidence_confidence"], 3.0)      # floor 30 → 3.0

    def test_all_low_tier_gives_minimum_floor(self):
        sources = [_Source("low")] * 4
        _, out = _run(make_scoring_guardrail(all_sources=sources),
                      evidence_confidence=10)
        self.assertEqual(out["evidence_confidence"], 1.0)      # floor 10 → 1.0

    def test_mixed_pool_gives_intermediate_floor(self):
        sources = [_Source("high"), _Source("high"), _Source("low"), _Source("low")]
        _, out = _run(make_scoring_guardrail(all_sources=sources),
                      evidence_confidence=10)
        self.assertEqual(out["evidence_confidence"], 2.0)      # 10 + 0.5*20 = 20

    def test_floor_does_not_lower_a_higher_score(self):
        """The floor only lifts — a confident scorer is not second-guessed."""
        sources = [_Source("low")] * 4
        _, out = _run(make_scoring_guardrail(all_sources=sources),
                      evidence_confidence=45)
        self.assertEqual(out["evidence_confidence"], 4.5)

    def test_no_floor_without_a_source_pool(self):
        _, out = _run(make_scoring_guardrail(), evidence_confidence=10)
        self.assertEqual(out["evidence_confidence"], 1.0)


# ---------------------------------------------------------------------------
# Market variance cap
# ---------------------------------------------------------------------------

def _market_task(*claims: str):
    """Build a market task whose findings carry the given size estimates.

    The extractor reads task.output.pydantic as an EvidenceReport, so a plain
    text stub would silently yield no figures and make these tests vacuous.
    """
    from academic_agent.evidence import EvidenceFinding, EvidenceReport

    report = EvidenceReport(
        topic="solid state batteries",
        scope_summary="Market sizing across published analyst estimates.",
        search_queries=["solid state battery market size"],
        findings=[
            EvidenceFinding(
                finding_id=f"F{i}",
                category="market_size",
                claim=claim,
                claim_type="estimate",
                source_ids=["M1"],
                confidence="medium",
                commercial_implication="Informs market accessibility scoring.",
            )
            for i, claim in enumerate(claims, start=1)
        ],
        limitations=["Analyst estimates vary by methodology."],
    )
    output = type("Out", (), {"pydantic": report, "raw": ""})()
    return type("Task", (), {"output": output})()


class MarketVarianceTests(unittest.TestCase):
    """Wildly disagreeing market estimates should not read as a solid market."""

    def test_wide_spread_caps_market_score(self):
        task = _market_task(
            "One house projects the market at USD 2 billion by 2030.",
            "Another projects USD 40 billion over the same horizon.",
        )
        _, out = _run(make_scoring_guardrail(market_task=task),
                      market_accessibility=50)
        self.assertLessEqual(out["market_accessibility"], 3.5)

    def test_wide_spread_is_reported(self):
        task = _market_task(
            "Estimates start at USD 2 billion for the 2030 market.",
            "Upper-bound estimates reach USD 40 billion for 2030.",
        )
        _, out = _run(make_scoring_guardrail(market_task=task),
                      market_accessibility=50)
        self.assertIn("spread", out["market_uncertainty"])

    def test_consistent_estimates_leave_score_alone(self):
        task = _market_task(
            "Analysts size the 2030 market at USD 10 billion.",
            "A second house puts the 2030 market at USD 12 billion.",
        )
        _, out = _run(make_scoring_guardrail(market_task=task),
                      market_accessibility=50)
        self.assertEqual(out["market_accessibility"], 5.0)
        self.assertIsNone(out["market_uncertainty"])

    def test_single_estimate_cannot_trigger_the_cap(self):
        """One number has no spread — capping on it would be arbitrary."""
        task = _market_task("The 2030 market is projected at USD 2 billion.")
        _, out = _run(make_scoring_guardrail(market_task=task),
                      market_accessibility=50)
        self.assertEqual(out["market_accessibility"], 5.0)

    def test_million_figures_normalised_to_billions(self):
        """500 million vs 40 billion is an 80x spread once units agree."""
        task = _market_task(
            "Conservative estimates put the market at USD 500 million.",
            "Bullish estimates reach USD 40 billion.",
        )
        _, out = _run(make_scoring_guardrail(market_task=task),
                      market_accessibility=50)
        self.assertLessEqual(out["market_accessibility"], 3.5)

    def test_no_market_task_means_no_cap(self):
        _, out = _run(make_scoring_guardrail(), market_accessibility=50)
        self.assertEqual(out["market_accessibility"], 5.0)
        self.assertIsNone(out["market_uncertainty"])


class WeightProfileConsistencyTests(unittest.TestCase):
    """The weights shown to the model must equal the weights it is graded on.

    They live in two places by necessity: agents.yaml states them so the model
    can apply them, and _WEIGHT_PROFILES holds them so the guardrail can
    recompute overall_score and correct the model's arithmetic. Nothing ties
    the two together.

    They drifted once already. The guardrail was left on an older split
    (patent 20 / market 35) after the rubric moved to 30 / 25, so it
    "corrected" scores the model had computed correctly — a CAR-T run went
    from 53 to 51 with no error anywhere. That is the worst shape a bug can
    take here: the wrong number looks exactly like the right one, and the
    component that exists to catch mistakes is the one making them.
    """

    @staticmethod
    def _weights_declared_to_the_model() -> dict[str, dict[str, float]]:
        import re
        from pathlib import Path

        yaml_text = (
            Path(__file__).resolve().parent.parent
            / "src" / "academic_agent" / "config" / "agents.yaml"
        ).read_text(encoding="utf-8")

        pattern = re.compile(
            r"^\s{4}([A-Z_]+) \([^)]*\):\s*\n"
            r"\s+W_market=([\d.]+)\s+W_trl=([\d.]+)\s+W_patent=([\d.]+)"
            r"\s+W_mrl=([\d.]+)\s+W_evidence=([\d.]+)",
            re.M,
        )
        return {
            m.group(1).lower(): {
                "market": float(m.group(2)), "trl": float(m.group(3)),
                "patent": float(m.group(4)), "mrl": float(m.group(5)),
                "evidence": float(m.group(6)),
            }
            for m in pattern.finditer(yaml_text)
        }

    def test_the_rubric_states_every_profile_the_code_scores_with(self):
        declared = self._weights_declared_to_the_model()
        self.assertTrue(declared, "no weight profiles parsed out of agents.yaml — "
                                  "the rubric's format changed and this check went blind")
        self.assertEqual(sorted(declared), sorted(_WEIGHT_PROFILES))

    def test_each_profile_matches_between_rubric_and_guardrail(self):
        declared = self._weights_declared_to_the_model()
        for name, weights in sorted(declared.items()):
            with self.subTest(profile=name):
                self.assertEqual(
                    weights, _WEIGHT_PROFILES[name],
                    f"{name}: agents.yaml tells the model one split and the "
                    "guardrail grades on another, so it will silently overwrite "
                    "correct arithmetic with a wrong total.",
                )


if __name__ == "__main__":
    unittest.main()
