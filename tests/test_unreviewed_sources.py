"""Repository deposits and preprints are not graded as reviewed journal work.

Every DOI-bearing OpenAlex record used to be called a "journal record" and,
when recent or cited, graded high. In 95 saved runs that included 15 Zenodo
deposits graded high, one of them a pseudo-scientific "135.5° Phase Lock"
text, plus bioRxiv, OSF and TechRxiv preprints. arXiv was the one preprint
source already graded medium; these rules extend that policy.
"""

from __future__ import annotations

from datetime import date
from unittest import TestCase

from academic_agent.source_pipeline import (
    _academic_source,
    _academic_source_from_openalex,
)

_ACCESSED = date(2026, 7, 17)
_TOPIC = "nanomaterials tumor treatment drug delivery"
_TITLE = "Nanomaterials for tumor treatment and drug delivery"
_ABSTRACT = (
    "This study investigates nanomaterial-based targeted drug delivery for tumor "
    "treatment. The results demonstrate significant efficacy improvements. "
    "Experimental validation confirms the proposed mechanism. " * 3
)


def _work(doi: str, *, cited: int = 0, published: str = "2026-07-01",
          work_type: str = "article", source_type: str | None = "journal",
          source_name: str = "Nature") -> dict:
    inv: dict = {}
    for i, word in enumerate(_ABSTRACT.split()):
        inv.setdefault(word, []).append(i)
    source = {"display_name": source_name}
    if source_type is not None:
        source["type"] = source_type
    return {
        "title": _TITLE, "doi": f"https://doi.org/{doi}", "type": work_type,
        "abstract_inverted_index": inv, "primary_location": {"source": source},
        "publication_date": published, "cited_by_count": cited,
        "topics": [{"id": "T1", "display_name": "Nanomedicine", "score": 0.9}],
    }


def _openalex(work: dict):
    source, reason = _academic_source_from_openalex(work, "A1", _ACCESSED, _TOPIC)
    assert source is not None, reason
    return source


class OpenAlexUnreviewedTests(TestCase):

    def test_new_uncited_zenodo_deposit_is_low_not_high(self):
        """The observed failure: recent + 0 citations was read as 'expected'."""
        src = _openalex(_work("10.5281/zenodo.123", source_type="repository",
                              source_name="Zenodo (CERN European Organization for Nuclear Research)"))
        self.assertEqual(src.credibility_tier, "low")
        self.assertIn("Zenodo", src.credibility_reason)
        self.assertIn("no editorial screening or peer review", src.credibility_reason)
        self.assertNotIn("journal record", src.credibility_reason)

    def test_well_cited_deposit_is_capped_at_medium(self):
        src = _openalex(_work("10.5281/zenodo.456", cited=40, source_type="repository",
                              source_name="Zenodo"))
        self.assertEqual(src.credibility_tier, "medium")

    def test_figshare_is_a_deposit_by_doi_even_without_metadata(self):
        src = _openalex(_work("10.6084/m9.figshare.1", source_type=None, source_name="OpenAlex"))
        self.assertEqual(src.credibility_tier, "low")

    def test_dataset_deposits_are_deposits(self):
        """Found in saved runs: a Mendeley Data dataset admitted as a paper."""
        for doi, work_type, name in (
            ("10.17632/rv4xpdm99t.1", "dataset", "Mendeley Data"),
            ("10.9999/unknown.dataset", "dataset", "Some Repository"),
        ):
            with self.subTest(doi=doi):
                src = _openalex(_work(doi, work_type=work_type, source_type="repository",
                                      source_name=name))
                self.assertEqual(src.credibility_tier, "low")
                self.assertIn("repository deposit", src.credibility_reason)

    def test_arxiv_hosted_version_of_a_conference_doi_is_a_preprint(self):
        """Found in saved runs: OpenAlex's primary location is the arXiv text."""
        src = _openalex(_work("10.4230/oasics.icpec.2025.4", work_type="preprint",
                              source_type="repository", source_name="arXiv (Cornell University)"))
        self.assertEqual(src.credibility_tier, "medium")
        self.assertIn("not peer-reviewed", src.credibility_reason)

    def test_biorxiv_preprint_is_medium(self):
        src = _openalex(_work("10.1101/2026.01.01.123", work_type="preprint",
                              source_type="repository", source_name="bioRxiv"))
        self.assertEqual(src.credibility_tier, "medium")
        self.assertIn("not peer-reviewed", src.credibility_reason)

    def test_well_cited_preprint_matches_the_existing_arxiv_rule(self):
        src = _openalex(_work("10.1101/2024.01.01.999", cited=68, published="2024-01-01",
                              work_type="preprint", source_type="repository",
                              source_name="medRxiv"))
        self.assertEqual(src.credibility_tier, "high")
        self.assertIn("not peer-reviewed", src.credibility_reason)

    def test_preprint_type_without_source_metadata(self):
        """TechRxiv/Authorea records carry work type only."""
        src = _openalex(_work("10.36227/techrxiv.1", work_type="preprint", source_type=None,
                              source_name="OpenAlex"))
        self.assertEqual(src.credibility_tier, "medium")

    def test_journal_article_is_unchanged(self):
        src = _openalex(_work("10.1038/s41586-024-0001", cited=25, published="2024-01-01"))
        self.assertEqual(src.credibility_tier, "high")
        self.assertIn("journal record", src.credibility_reason)

    def test_a_stricter_existing_grade_is_kept(self):
        """A predatory-publisher 'low' keeps its own reason."""
        src = _openalex(_work("10.5281/zenodo.789", source_type="repository",
                              source_name="Zenodo", cited=40))
        self.assertEqual(src.credibility_tier, "medium")
        predatory = _openalex(_work("10.5281/zenodo.790", source_type="repository",
                                    source_name="OMICS International", cited=40))
        self.assertEqual(predatory.credibility_tier, "low")
        self.assertIn("predatory", predatory.credibility_reason)

    def test_reason_cannot_trigger_the_zero_citation_backfill_upgrade(self):
        """collect_source_collection upgrades medium sources whose reason says
        "0 citation" once a backfill finds citations; that must not reach here."""
        for work in (
            _work("10.1101/2026.01.01.5", work_type="preprint", source_type="repository",
                  source_name="bioRxiv", published="2020-01-01"),
            _work("10.5281/zenodo.5", source_type="repository", source_name="Zenodo"),
        ):
            with self.subTest(doi=work["doi"]):
                self.assertNotIn("0 citation", _openalex(work).credibility_reason)


class CrossrefUnreviewedTests(TestCase):

    def _crossref(self, doi: str, *, item_type: str = "journal-article", publisher: str = "Test Publisher"):
        item = {
            "DOI": doi, "type": item_type, "title": [_TITLE], "publisher": publisher,
            "abstract": f"<jats:p>{_ABSTRACT}</jats:p>",
            "published": {"date-parts": [[2026, 7, 1]]},
        }

        class StaticCrossref:
            def lookup_doi(self, _doi: str) -> dict | None:
                return item

            def search_title(self, _title: str) -> list[dict]:
                return [item]

        source, reason = _academic_source(
            {"title": _TITLE, "link": f"https://doi.org/{doi}", "snippet": "A snippet."},
            "A1", StaticCrossref(), _ACCESSED, _TOPIC,
        )
        assert source is not None, reason
        return source

    def test_crossref_posted_content_is_a_preprint(self):
        src = self._crossref("10.20944/preprints202601.0001", item_type="posted-content")
        self.assertEqual(src.credibility_tier, "medium")
        self.assertIn("not peer-reviewed", src.credibility_reason)

    def test_crossref_zenodo_doi_is_a_deposit(self):
        src = self._crossref("10.5281/zenodo.42", publisher="Zenodo")
        self.assertEqual(src.credibility_tier, "low")

    def test_crossref_journal_article_is_unchanged(self):
        src = self._crossref("10.1016/j.test.2026.01.001")
        self.assertEqual(src.credibility_tier, "high")
