"""What a failed academic minimum records about the papers it could not keep.

A production run (2026-11-25, passive radiative cooling coatings for warehouse
roofs) stopped with 2 of 3 academic sources. Its audit showed seven papers
with on-topic titles rejected for "abstract too thin (0 chars)" and a final
relevance filter that took back six of the eight its queries accepted, and
its page told the owner to edit the topic. Measured on 2026-11-27: the two
papers the review named are Elsevier works, and OpenAlex lists 15 of the 18
abstract-less works among its first 27 for the topic as Elsevier's;
Semantic Scholar answered "abstract": null for the Elsevier ones it
answered at all, and HTTP 429 for the rest. The audit could not tell those
two apart, and the diagnostic did not say which words the final filter had
required.
"""

from __future__ import annotations

from datetime import date
from unittest import TestCase

from academic_agent.run_spec import SearchPlan
from academic_agent.source_pipeline import (
    SourceCollectionError,
    _academic_source_from_openalex,
    collect_source_collection,
)
from api import retrieval_health

_TOPIC = "Passive radiative cooling coatings for warehouse roofs"


def _work(title: str, abstract: str | None, index: int = 1) -> dict:
    inverted: dict[str, list[int]] = {}
    for position, word in enumerate((abstract or "").split()):
        inverted.setdefault(word, []).append(position)
    return {
        "title": title,
        "doi": f"https://doi.org/10.1016/j.test.2026.{index}",
        "abstract_inverted_index": inverted or None,
        "primary_location": {"source": {"display_name": "Test Journal"}},
        "publication_date": "2026-03-01",
        "cited_by_count": 3,
        "topics": [],
    }


class _Lookup:
    """Semantic Scholar as the pipeline now asks it: the text, and why there is none."""

    def __init__(self, answer: tuple[str, str | None]) -> None:
        self.answer = answer

    def lookup_abstract(self, doi: str) -> tuple[str, str | None]:
        return self.answer

    def get_abstract_by_doi(self, doi: str) -> str:
        raise AssertionError("the pipeline must ask for the reason, not only the text")


class _TextOnly:
    """A client with only the older method: whatever it returns is the abstract."""

    def get_abstract_by_doi(self, doi: str) -> str:
        return ""


class AbstractLookupReasonTests(TestCase):
    _TITLE = "Performance of passive radiative cooling coatings under environmental aging"

    def _reason(self, s2) -> str:
        source, reason = _academic_source_from_openalex(
            _work(self._TITLE, None), "A1", date(2026, 11, 27), _TOPIC, s2_client=s2,
        )
        self.assertIsNone(source)
        return reason

    def test_an_answer_without_an_abstract_keeps_the_old_note(self):
        self.assertEqual(self._reason(_Lookup(("", None))), f"abstract too thin (0 chars): {self._TITLE!r}")
        self.assertEqual(self._reason(_TextOnly()), f"abstract too thin (0 chars): {self._TITLE!r}")

    def test_no_answer_says_semantic_scholar_did_not_answer(self):
        self.assertEqual(
            self._reason(_Lookup(("", "HTTP 429"))),
            f"abstract too thin (0 chars; Semantic Scholar did not answer: HTTP 429): {self._TITLE!r}",
        )

    def test_an_abstract_from_semantic_scholar_still_admits_the_paper(self):
        abstract = ("Passive radiative cooling coatings reflect sunlight and emit heat through the "
                    "atmospheric window; this study measures their aging on building surfaces.")
        source, reason = _academic_source_from_openalex(
            _work(self._TITLE, None), "A1", date(2026, 11, 27), _TOPIC, s2_client=_Lookup((abstract, None)),
        )
        self.assertEqual(reason, "")
        self.assertIsNotNone(source)

    def test_the_new_note_is_not_read_as_a_failed_lane(self):
        """/api/health/retrieval flags a lane whose rows carry a give-up note; one
        paper's missing abstract is not the lane failing."""
        row = {"domain": "academic", "query": "[OA-Recent] x", "result_count": 5, "accepted_source_ids": [],
               "rejected_reasons": [
                   f"abstract too thin (0 chars; Semantic Scholar did not answer: HTTP 429): {self._TITLE!r}",
                   f"abstract too thin (0 chars; Semantic Scholar did not answer: network error): {self._TITLE!r}",
               ]}
        self.assertFalse(retrieval_health._failed(row))


class _OnlyRecentOpenAlex:
    """Four papers whose titles fit and whose abstracts never name the setting."""

    abstract = ("This peer-reviewed study reports spectral reflectance, thermal emittance and "
                "sub-ambient cooling power of porous polymer coatings in outdoor field tests.")

    def search_recent(self, *args, **kwargs) -> list:
        titles = (
            "Hierarchically porous passive radiative cooling coatings",
            "Durable passive radiative cooling coatings for outdoor use",
            "Scalable passive radiative cooling coatings with silica",
            "Colored passive radiative cooling coatings and their efficiency",
        )
        return [_work(title, self.abstract, index) for index, title in enumerate(titles, start=1)]

    def search(self, *args, **kwargs) -> list:
        return []

    def fetch_citation_by_doi(self, doi: str) -> int | None:
        return None


class _Null:
    api_key = ""

    def search(self, *args, **kwargs) -> list:
        return []

    def search_mesh(self, *args, **kwargs) -> list:
        return []

    def get_mesh_terms(self, *args, **kwargs) -> list:
        return []

    def lookup_abstract(self, doi: str) -> tuple[str, str | None]:
        return "", None


class _NoCrossref:
    def lookup_doi(self, doi: str) -> None:
        return None

    def search_title(self, title: str) -> list:
        return []


class SettingTermsTests(TestCase):
    def _fail(self, plan: SearchPlan) -> dict:
        with self.assertRaises(SourceCollectionError) as caught:
            collect_source_collection(
                plan.search_topic,
                search_plan=plan,
                searcher=lambda _query: {"organic": []},
                crossref=_NoCrossref(),
                openalex=_OnlyRecentOpenAlex(),
                s2=_Null(), pubmed=_Null(), arxiv=_Null(), lens=_Null(),
                url_checker=lambda url: (True, ""),
                page_dater=lambda *args, **kwargs: None,
                patent_applicant_lookup=lambda *args, **kwargs: None,
                minimum_sources=3,
                maximum_sources=8,
                accessed_date=date(2026, 11, 27),
            )
        return caught.exception.diagnostics

    def test_the_final_filter_records_the_setting_words_it_required(self):
        """Every paper passed its query and none names "warehouse" or "roofs":
        the page can say which words were missing only if the run kept them."""
        diagnostics = self._fail(SearchPlan(search_topic=_TOPIC))
        self.assertEqual(diagnostics["stage"], "academic_relevance_filter")
        self.assertEqual(diagnostics["setting_terms"], ["roofs", "warehouse"])
        removed = next(row for row in diagnostics["audit"]
                       if row["domain"] == "academic" and row["query"] == "[Relevance-Filter]")
        self.assertEqual(len(removed["rejected_reasons"]), 4)
        self.assertTrue(all(reason.startswith("score=-1 ") for reason in removed["rejected_reasons"]))

    def test_an_alias_with_a_setting_of_its_own_adds_its_words(self):
        """A paper is removed as off-setting only when no reading of the topic
        has its setting in the paper, so every reading's words are listed."""
        plan = SearchPlan(search_topic=_TOPIC, aliases=("Radiative cooling paints for cold storage",))
        self.assertEqual(self._fail(plan)["setting_terms"], ["cold", "roofs", "storage", "warehouse"])

    def test_no_setting_words_when_a_reading_has_no_setting(self):
        """A reading without a setting scores every paper on its words alone,
        so no paper can have been removed for a missing setting."""
        from academic_agent.source_pipeline import _setting_terms

        self.assertEqual(_setting_terms(_TOPIC, ["Passive radiative cooling paint"]), [])
        self.assertEqual(_setting_terms("Passive radiative cooling paint", []), [])
        self.assertEqual(_setting_terms(_TOPIC, []), ["roofs", "warehouse"])
