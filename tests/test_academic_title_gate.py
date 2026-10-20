"""The academic title gate is rule R5 of the 2026-10-20 title-gate experiment.

docs/prereg-2026-10-20-academic-title-gate-v1.md froze the rule and
docs/results-2026-10-20-academic-title-gate-v1.md recorded it as supported.
These tests hold production to the frozen rule on every replayed decision,
and pin the wiring that hands the user's words to each academic lane.
"""

import importlib.util
import json
from datetime import date
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from academic_agent import source_pipeline as pipeline
from academic_agent.language import TopicSearchPlan

_EVAL = Path(__file__).resolve().parents[1] / "evals" / "academic_title_gate_v1"
_DATE = date(2026, 10, 20)
_HYPERLOOP_PLAN = "Hyperloop high-speed vacuum tube transportation"


def _frozen_rules():
    spec = importlib.util.spec_from_file_location("academic_title_gate_v1_rules", _EVAL / "rules.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _replay_rows():
    with open(_EVAL / "dataset.jsonl", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def _gate_topics(row):
    # As the replay and source_pipeline do: web/Crossref results also try aliases.
    return [topic for topic in (row["research_topic"], *(
        row["aliases"] if row["paths"] == ["web"] else ()
    )) if topic]


class FrozenRuleTests(TestCase):
    def test_production_gate_reproduces_r5_on_every_replayed_decision(self) -> None:
        rules = _frozen_rules()
        rows = _replay_rows()
        self.assertEqual(len(rows), 494)
        for row in rows:
            with self.subTest(row=row["id"]):
                expected = any(rules.r5_one_matcher(row["title"], t, row) for t in _gate_topics(row))
                anchor = pipeline._academic_anchor_topic(
                    row["display_topic"], row["research_topic"], row["aliases"]
                )
                observed = any(
                    pipeline._academic_title_matches(row["title"], t, anchor) for t in _gate_topics(row)
                )
                self.assertEqual(observed, expected, row["title"])

    def test_every_replayed_latin_input_anchors_on_the_users_words(self) -> None:
        for row in _replay_rows():
            with self.subTest(row=row["id"]):
                anchor = pipeline._academic_anchor_topic(
                    row["display_topic"], row["research_topic"], row["aliases"]
                )
                # Chinese inputs have no Latin words; R5 then uses the planned phrase.
                latin = pipeline._academic_content_words(row["display_topic"])
                self.assertEqual(anchor, row["display_topic"] if latin else "")


class AcademicTitleGateTests(TestCase):
    def test_one_word_input_needs_that_word_not_the_planners_expansion(self) -> None:
        match = pipeline._academic_title_matches
        # Rejected by the old gate: one shared word with the expanded phrase.
        self.assertFalse(pipeline._title_matches_topic("Hyperloop System Optimization", _HYPERLOOP_PLAN))
        self.assertTrue(match("Hyperloop System Optimization", _HYPERLOOP_PLAN, "hyperloop"))
        # Accepted by the old gate: "high" and "vacuum" from the expansion.
        laser = "Laser-Driven High-Velocity Microparticle Launcher In Atmosphere And Under Vacuum"
        self.assertTrue(pipeline._title_matches_topic(laser, _HYPERLOOP_PLAN))
        self.assertFalse(match(laser, _HYPERLOOP_PLAN, "hyperloop"))

    def test_multi_word_input_matches_as_a_phrase(self) -> None:
        match = pipeline._academic_title_matches
        self.assertTrue(match("Fusion power.", "nuclear fusion energy generation", "fusion power"))
        self.assertFalse(match(
            "Recent advances in solid-state nuclear magnetic resonance studies on membrane fusion proteins.",
            "nuclear fusion energy research",
            "fusion power",
        ))

    def test_based_is_not_a_topic_word(self) -> None:
        self.assertFalse(pipeline._academic_title_matches(
            "Optimal Power Flow for AC/DC System Based on Cooperative Multi-objective Particle Swarm Optimization",
            "Space-based solar power systems",
            "space-based solar power",
        ))

    def test_without_user_words_the_planned_phrase_decides(self) -> None:
        self.assertEqual(pipeline._academic_anchor_topic("漂浮式海上风电", "floating offshore wind energy"), "")
        title = "Efficient preliminary floating offshore wind turbine design and testing methodologies"
        self.assertTrue(pipeline._academic_title_matches(title, "floating offshore wind energy", ""))

    def test_a_request_is_not_an_anchor(self) -> None:
        anchor = pipeline._academic_anchor_topic(
            "We are building an LLM for scriptwriting; assess its value",
            "large language models for scriptwriting",
            ("language model assistance for collaborative creative writing",),
        )
        self.assertEqual(anchor, "")

    def test_an_input_longer_than_the_replay_is_not_an_anchor(self) -> None:
        long_topic = "solid state lithium metal batteries electric vehicles fast charging cold climates"
        self.assertEqual(pipeline._academic_anchor_topic(long_topic, long_topic), "")


class AcademicLaneWiringTests(TestCase):
    def _gate_calls(self, call):
        seen = []

        def spy(title, topic, user_topic=""):
            seen.append((title, topic, user_topic))
            return False

        with patch.object(pipeline, "_academic_title_matches", side_effect=spy):
            source, reason = call()
        self.assertIsNone(source)
        self.assertIn("'Hyperloop System Optimization'", reason)
        return seen

    def test_each_academic_lane_passes_the_users_words(self) -> None:
        title = "Hyperloop System Optimization"
        lanes = {
            "arXiv": lambda: pipeline._academic_source_from_arxiv(
                {"title": title, "arxiv_url": "https://arxiv.org/abs/2401.00001"},
                "A1", _DATE, _HYPERLOOP_PLAN, user_topic="hyperloop",
            ),
            "PubMed": lambda: pipeline._academic_source_from_pubmed(
                {"title": title, "pmid": "1"}, "A1", _DATE, _HYPERLOOP_PLAN, user_topic="hyperloop",
            ),
            "S2": lambda: pipeline._academic_source_from_s2(
                {"title": title, "externalIds": {"DOI": "10.1/x"}}, "A1", _DATE, _HYPERLOOP_PLAN,
                user_topic="hyperloop",
            ),
            "OpenAlex": lambda: pipeline._academic_source_from_openalex(
                {"title": title, "doi": "https://doi.org/10.1/x", "topics": []}, "A1", _DATE,
                _HYPERLOOP_PLAN, user_topic="hyperloop",
            ),
        }
        for lane, call in lanes.items():
            with self.subTest(lane=lane):
                self.assertEqual(self._gate_calls(call), [(title, _HYPERLOOP_PLAN, "hyperloop")])

    def test_crossref_lane_tries_each_alias_with_the_users_words(self) -> None:
        class Crossref:
            def lookup_doi(self, doi):
                return {"DOI": doi, "title": ["Hyperloop System Optimization"], "publisher": "P"}

            def search_title(self, title):
                return []

        result = {"title": "Hyperloop System Optimization", "link": "https://doi.org/10.1234/hyperloop-1", "snippet": ""}
        calls = self._gate_calls(lambda: pipeline._academic_source(
            result, "A1", Crossref(), _DATE, _HYPERLOOP_PLAN, aliases=("evacuated tube transport",),
            user_topic="hyperloop",
        ))
        self.assertEqual([c[1:] for c in calls], [
            (_HYPERLOOP_PLAN, "hyperloop"), ("evacuated tube transport", "hyperloop"),
        ])

    def test_collection_hands_the_anchor_to_the_academic_lanes(self) -> None:
        class Captured(Exception):
            pass

        cases = {
            "hyperloop": ("hyperloop", _HYPERLOOP_PLAN, "hyperloop"),
            "request": (
                "We are building an LLM for scriptwriting; assess its value",
                "large language models for scriptwriting",
                "",
            ),
        }
        for name, (submitted, planned, anchor) in cases.items():
            with self.subTest(case=name):
                seen = {}

                def capture(*args, _seen=seen, **kwargs):
                    _seen.update(kwargs)
                    raise Captured

                with (
                    patch("academic_agent.language.plan_topic_search",
                          return_value=TopicSearchPlan(search_topic=planned)),
                    patch.object(pipeline, "_collect_academic_primary", side_effect=capture),
                    patch("socket.socket.connect", side_effect=AssertionError("network forbidden")),
                    self.assertRaises(Captured),
                ):
                    pipeline.collect_source_collection(
                        submitted, searcher=lambda query: {"organic": []}, crossref=object(),
                        openalex=object(), s2=object(), accessed_date=_DATE,
                    )
                self.assertEqual(seen["user_topic"], anchor)
