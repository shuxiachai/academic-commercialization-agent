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


def _production_decisions():
    decisions = {}
    for row in _replay_rows():
        anchor = pipeline._academic_anchor_topic(row["display_topic"], row["research_topic"], row["aliases"])
        decisions[row["id"]] = any(
            pipeline._academic_title_matches(row["title"], t, anchor) for t in _gate_topics(row)
        )
    return decisions


class FrozenRuleTests(TestCase):
    def test_production_gate_is_r5_with_the_plural_stemmer(self) -> None:
        rules = _frozen_rules()
        rules._stem = pipeline._academic_stem
        observed = _production_decisions()
        rows = _replay_rows()
        self.assertEqual(len(rows), 494)
        for row in rows:
            with self.subTest(row=row["id"]):
                expected = any(rules.r5_one_matcher(row["title"], t, row) for t in _gate_topics(row))
                self.assertEqual(observed[row["id"]], expected, row["title"])

    def test_the_stemmer_fix_is_the_only_departure_from_frozen_r5(self) -> None:
        # The five decisions the results note's exploratory check reported:
        # four relevant titles ("drones", "interface") and one general UAV survey.
        rules = _frozen_rules()
        observed = _production_decisions()
        changed = {
            row["id"]
            for row in _replay_rows()
            if observed[row["id"]] != any(rules.r5_one_matcher(row["title"], t, row) for t in _gate_topics(row))
        }
        self.assertEqual(changed, {"test-0295", "test-0299", "test-0369", "test-0372", "test-0383"})
        self.assertTrue(all(observed[row_id] for row_id in changed))

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
    def test_plurals_meet_their_singular(self) -> None:
        stem = pipeline._academic_stem
        for plural, singular in (("drones", "drone"), ("interfaces", "interface"), ("supplies", "supply"),
                                 ("processes", "process"), ("farms", "farming")):
            with self.subTest(plural=plural):
                self.assertEqual(stem(plural), stem(singular))
        self.assertTrue(pipeline._academic_title_matches(
            "Unmanned aerial vehicle (drones) in public health: A SWOT analysis.",
            "unmanned aerial vehicle medical supply delivery",
            "drone delivery of medical supplies",
        ))

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


_FARM_USER = "vertical farming for fresh produce"
_FARM_PLAN = "Controlled environment agriculture for leafy greens"  # a drifted live plan


def _arxiv(title, index):
    return {
        "title": title,
        "abstract": "This study measures yield, energy use and lighting strategies in indoor crop production "
                    "systems across several commercial facilities.",
        "arxiv_url": f"https://arxiv.org/abs/2501.0000{index}",
        "pub_date": "2025-01-15",
        "authors": "A. Grower",
    }


class ShortfallTopUpTests(TestCase):
    """results-2026-10-21-academic-gate-live-v1.md: a drifted plan left R5 one paper."""

    def test_a_drifted_plan_retrieves_titles_r5_rejects_and_the_old_gate_admits(self) -> None:
        title = "Controlled environment agriculture for leafy greens: lighting and energy use"
        self.assertFalse(pipeline._academic_title_matches(title, _FARM_PLAN, _FARM_USER))
        self.assertTrue(pipeline._legacy_academic_title_gate(title, _FARM_PLAN, _FARM_USER))

    def test_lanes_accept_an_explicit_gate(self) -> None:
        record = _arxiv("Controlled environment agriculture for leafy greens: lighting and energy use", 1)
        rejected, _ = pipeline._academic_source_from_arxiv(record, "A1", _DATE, _FARM_PLAN, user_topic=_FARM_USER)
        admitted, _ = pipeline._academic_source_from_arxiv(
            record, "A1", _DATE, _FARM_PLAN, user_topic=_FARM_USER,
            title_gate=pipeline._legacy_academic_title_gate,
        )
        self.assertIsNone(rejected)
        self.assertIsNotNone(admitted)

    def test_top_up_admits_old_gate_papers_only_up_to_the_need_and_marks_them(self) -> None:
        kept_source, _ = pipeline._academic_source_from_arxiv(
            _arxiv("Controlled environment agriculture for leafy greens: lighting and energy use", 1),
            "A1", _DATE, _FARM_PLAN, title_gate=pipeline._legacy_academic_title_gate,
        )
        records = [
            _arxiv("Controlled environment agriculture for leafy greens: lighting and energy use", 2),  # duplicate
            _arxiv("Quantum chromodynamics at finite temperature", 3),  # rejected by both gates
            _arxiv("Controlled environment agriculture for leafy greens in urban rooftops", 4),
            _arxiv("Energy benchmarking of controlled environment agriculture for leafy greens", 5),
            _arxiv("Controlled environment agriculture for leafy greens under LED spectra", 6),
        ]
        top_up = pipeline._relaxed_top_up_factory(
            _FARM_PLAN, _DATE, object(), [(records, pipeline._academic_source_from_arxiv, _FARM_PLAN)],
        )
        added, audit = top_up(2, [kept_source])
        self.assertEqual([s.title for s in added], [
            "Controlled environment agriculture for leafy greens in urban rooftops",
            "Energy benchmarking of controlled environment agriculture for leafy greens",
        ])
        self.assertTrue(all("only to reach the academic minimum" in s.credibility_reason for s in added))
        self.assertTrue(audit.query.startswith("[Relaxed-Title-Gate]"))
        self.assertEqual(audit.accepted_source_ids, [s.source_id for s in added])

    def _collect_with_primary(self, accepted_count):
        calls = []

        class Stop(Exception):
            pass

        source, _ = pipeline._academic_source_from_arxiv(
            _arxiv("Vertical farming for fresh produce: a systematic review", 1), "A1", _DATE, _FARM_PLAN,
            user_topic=_FARM_USER,
        )
        source.citation_count = 1  # no citation backfill request

        def primary(*args, relaxed_reserve=None, **kwargs):
            def top_up(needed, kept):
                calls.append(("top_up", needed, len(kept)))
                raise Stop

            relaxed_reserve.append(top_up)
            return [source] * accepted_count, []

        def domain(domain_name, *args, **kwargs):
            calls.append(("domain", domain_name))
            return [], []

        class Lens:  # the first thing collection touches after the academic minimum
            @property
            def api_key(self):
                calls.append(("patents",))
                raise Stop

        with (
            patch("academic_agent.language.plan_topic_search",
                  return_value=TopicSearchPlan(search_topic=_FARM_PLAN)),
            patch.object(pipeline, "_collect_academic_primary", side_effect=primary),
            patch.object(pipeline, "_collect_domain", side_effect=domain),
            patch("socket.socket.connect", side_effect=AssertionError("network forbidden")),
            self.assertRaises(Stop),
        ):
            pipeline.collect_source_collection(
                _FARM_USER, searcher=lambda query: {"organic": []}, crossref=object(),
                openalex=object(), s2=object(), lens=Lens(), accessed_date=_DATE,
            )
        return calls

    def test_collection_tops_up_last_after_the_web_fallback(self) -> None:
        self.assertEqual(self._collect_with_primary(1)[:2], [("domain", "academic"), ("top_up", 2, 1)])

    def test_collection_does_not_top_up_when_the_minimum_is_met(self) -> None:
        self.assertEqual(self._collect_with_primary(3), [("patents",)])
