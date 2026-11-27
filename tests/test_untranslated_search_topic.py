"""A topic the model never turned into English is not searched.

On 2026-11-23 four production runs of one account, on Chinese topics about an
active drowning-rescue system, searched every backend with the Chinese text
as typed, no aliases and no components: the shape plan_topic_search leaves
when the planner call and the translation after it both come back empty. The
academic gates only read [a-z] words, so a Chinese phrase gave them nothing
to test: the title gate passed every title and the final relevance filter
kept every paper. OpenAlex's cited-sort answered with whatever it holds, and
eight papers on Chinese literature, translation studies and dam safety became
the runs' academic evidence. All four then failed later, after their paid
searches. A copy of a Railway run from 2026-08-10 ("铀235制取和储存") has the
same shape and, in its log, the planner's failed connection.

Measured on the 380 distinct (run, search topic) pairs saved locally, 73 of
them for non-English input: one search topic was in a non-English script,
that 2026-08-10 run, and no alias was. An English topic whose planner did
not answer still searches as typed, as it always has.
"""
from __future__ import annotations

from datetime import date
from unittest import TestCase
from unittest.mock import MagicMock, patch

from academic_agent import language
from academic_agent.language import plan_topic_search
from academic_agent.pipeline_worker import _error_text
from academic_agent.run_spec import SearchPlan
from academic_agent.source_pipeline import SourceCollectionError, collect_source_collection
from api import runs
from tests.test_source_pipeline import (
    MatchingCrossref, _NullArXiv, _NullLens, _NullPubMed, _NullS2, fake_search,
)

DROWNING = "主动式防溺水智能救援系统"


class _RecordingOpenAlex:
    """Answers any query with an unrelated work, as the cited-sort did."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query: str, *args, **kwargs) -> list:
        self.queries.append(query)
        return [{
            "title": "中国现代翻译文学史研究",
            "doi": "https://doi.org/10.1234/unrelated-1",
            "abstract_inverted_index": {word: [i] for i, word in enumerate(
                "A history of modern Chinese translated literature and its reception".split())},
            "primary_location": {"source": {"display_name": "Some Journal"}},
            "publication_date": "2015-01-01",
            "cited_by_count": 120,
            "topics": [],
        }]

    def search_recent(self, query: str, *args, **kwargs) -> list:
        self.queries.append(query)
        return []

    def fetch_citation_by_doi(self, doi: str) -> int | None:
        return None


def _collect(topic: str, *, searcher=None, openalex=None, **kwargs):
    return collect_source_collection(
        topic,
        searcher=searcher or fake_search,
        crossref=MatchingCrossref(),
        openalex=openalex or _RecordingOpenAlex(),
        s2=_NullS2(), pubmed=_NullPubMed(), arxiv=_NullArXiv(), lens=_NullLens(),
        url_checker=lambda url: (True, ""),
        minimum_sources=3, maximum_sources=3,
        accessed_date=date(2026, 11, 23),
        **kwargs,
    )


def _planner(answers: dict[str, str]):
    """A stand-in for language._llm_call that answers by stage."""
    def call(prompt, *, system, max_tokens=400, stage="language_helper", credentials=None):
        return answers.get(stage, "")
    return call


class UntranslatedTopicIsNotSearched(TestCase):
    def _assert_stopped_before_search(self, topic: str, **kwargs) -> SourceCollectionError:
        openalex, searcher = _RecordingOpenAlex(), MagicMock(return_value={"organic": []})
        with self.assertRaises(SourceCollectionError) as caught:
            _collect(topic, searcher=searcher, openalex=openalex, **kwargs)
        # Nothing was searched: not OpenAlex, and not the paid web search either.
        self.assertEqual(openalex.queries, [])
        searcher.assert_not_called()
        diagnostics = caught.exception.diagnostics
        self.assertEqual(diagnostics["stage"], "topic_planning")
        self.assertEqual(diagnostics["input_topic"], topic)
        self.assertEqual(diagnostics["accepted_sources"], 0)
        self.assertEqual(diagnostics["audit"], [])
        return caught.exception

    def test_a_chinese_topic_whose_planner_and_translation_failed_is_not_searched(self):
        # tests/conftest.py makes every _llm_call return "", the value a failed call returns.
        error = self._assert_stopped_before_search(DROWNING)
        diagnostics = error.diagnostics
        self.assertEqual(diagnostics["search_topic"], DROWNING)
        self.assertEqual(diagnostics["aliases"], [])
        self.assertIs(diagnostics["planned"], False)

    def test_a_mixed_topic_left_untranslated_is_not_searched_either(self):
        # Its one English word would let the gates pass titles on "hyperloop" alone.
        self._assert_stopped_before_search("帮我评估 hyperloop 的商业潜力")

    def test_a_confirmed_reading_that_is_not_english_is_not_searched(self):
        plan = SearchPlan(search_topic="防溺水救援系统")
        error = self._assert_stopped_before_search(DROWNING, search_plan=plan)
        self.assertIs(error.diagnostics["planned"], True)

    def _searched(self, topic: str) -> list[str]:
        """What OpenAlex was asked; the unrelated answers leave the run short, past planning."""
        openalex = _RecordingOpenAlex()
        with self.assertRaises(SourceCollectionError) as caught:
            _collect(topic, openalex=openalex, searcher=MagicMock(return_value={"organic": []}))
        self.assertNotEqual(caught.exception.diagnostics["stage"], "topic_planning")
        return openalex.queries

    def test_a_translated_topic_is_searched_in_english(self):
        with patch.object(language, "_llm_call", _planner({"translation": "Active drowning rescue systems"})):
            queries = self._searched(DROWNING)
        self.assertIn("Active drowning rescue systems", queries)
        self.assertNotIn(DROWNING, queries)

    def test_an_english_topic_whose_planner_did_not_answer_is_searched_as_typed(self):
        topic = "Active drowning rescue systems for swimming pools"
        self.assertIn(topic, self._searched(topic))


class TheStopIsNamedOnThePage(TestCase):
    """The worker's own error text reaches its own code, for every reader."""

    def _raw(self) -> str:
        with self.assertRaises(SourceCollectionError) as caught:
            _collect(DROWNING)
        return _error_text(caught.exception)

    def test_each_reader_is_told_nothing_was_searched(self):
        raw = self._raw()
        for funded_by in (None, "deployment", "own_keys"):
            with self.subTest(funded_by=funded_by):
                code, sentence = runs._public_failure(raw, funded_by=funded_by)
                self.assertEqual(code, "topic_not_translated")
                self.assertIn("English search phrase", sentence)
                self.assertIn("nothing was searched", sentence)
        self.assertIn("API keys", runs._public_failure(raw, funded_by="own_keys")[1])

    def test_it_is_not_read_as_a_shortage_of_evidence(self):
        # A shortage page counts papers; this run found none because it looked for none.
        self.assertNotEqual(runs._public_failure(self._raw())[0], "insufficient_evidence")
        self.assertNotIn("topic_not_translated", runs.OPERATOR_FAILURE_CODES)

    def test_a_shortage_is_still_read_as_one(self):
        with self.assertRaises(SourceCollectionError) as caught:
            _collect("Active drowning rescue systems for swimming pools",
                     openalex=_RecordingOpenAlex(), searcher=MagicMock(return_value={"organic": []}))
        self.assertEqual(runs._public_failure(_error_text(caught.exception))[0], "insufficient_evidence")


class PlannedMeansThePlannerWroteIt(TestCase):
    """`planned` is what a preview shows as the planner's reading."""

    def test_an_answer_without_a_search_topic_is_not_a_reading(self):
        with patch.object(language, "_llm_call", _planner({"search_planning": "Sure, here is a plan."})):
            plan = plan_topic_search(DROWNING)
        # Before, this was planned=True with the Chinese text as its search topic, and
        # a preview showed the topic as typed as if the planner had read it so.
        self.assertEqual((plan.search_topic, plan.planned), (DROWNING, False))

    def test_a_search_topic_too_long_to_use_is_not_a_reading(self):
        answer = "SEARCH_TOPIC: " + " ".join(["drowning"] * 30)
        with patch.object(language, "_llm_call", _planner({"search_planning": answer})):
            plan = plan_topic_search("Active drowning rescue systems")
        self.assertEqual((plan.search_topic, plan.planned), ("Active drowning rescue systems", False))

    def test_a_reading_the_planner_wrote_is_one(self):
        answer = "SEARCH_TOPIC: active drowning rescue systems\nALIAS: drowning detection and rescue"
        with patch.object(language, "_llm_call", _planner({"search_planning": answer})):
            plan = plan_topic_search(DROWNING)
        self.assertEqual(plan.search_topic, "active drowning rescue systems")
        self.assertEqual(plan.aliases, ("drowning detection and rescue",))
        self.assertIs(plan.planned, True)

    def test_an_alias_left_in_chinese_is_dropped(self):
        # The gates read no word of it, so as a reading it would pass every title.
        answer = ("SEARCH_TOPIC: active drowning rescue systems\nALIAS: 防溺水救援\n"
                  "ALIAS: drowning detection and rescue")
        with patch.object(language, "_llm_call", _planner({"search_planning": answer})):
            plan = plan_topic_search(DROWNING)
        self.assertEqual(plan.aliases, ("drowning detection and rescue",))

    def test_a_component_left_in_chinese_is_dropped(self):
        answer = ("SEARCH_TOPIC: active drowning rescue systems\nCOMPONENT: 溺水检测\n"
                  "COMPONENT: wearable drowning sensors\nCOMPONENT: unmanned rescue buoys")
        with patch.object(language, "_llm_call", _planner({"search_planning": answer})):
            plan = plan_topic_search(DROWNING)
        self.assertEqual(plan.components, ("wearable drowning sensors", "unmanned rescue buoys"))
