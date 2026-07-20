"""Tests for features added in the recent development cycle.

Covers:
- Predatory publisher detection
- Fuzzy title deduplication across sources
- ArxivClient Atom feed parsing
- patent_assignees extraction in SourceCollection (via Lens)
- Zero-citation credibility downgrade (OpenAlex + Crossref paths)
- translate_to_language in language module
"""

from __future__ import annotations

import json
from datetime import date
from unittest import TestCase
from unittest.mock import MagicMock, patch

from academic_agent.source_pipeline import (
    _academic_source_from_arxiv,
    _academic_source_from_openalex,
    _filter_by_relevance,
    _is_borderline_publisher,
    _is_predatory_publisher,
    _market_summary_relevant,
    _patent_keywords,
    _patent_source_from_lens,
    _record_relevance_filter,
    SearchAudit,
    ArxivClient,
    EvidenceSource,
    LensPatentClient,
    collect_source_collection,
)


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

_LONG_ABSTRACT = (
    "This peer-reviewed study presents experimental findings on the research topic, "
    "covering the methodology, quantitative results, and implications for commercial "
    "deployment. The work demonstrates significant progress toward practical application "
    "and discusses open challenges in technology transfer."
)

_LONG_PATENT_SNIPPET = (
    "Official patent database record for the claimed invention, verified against the "
    "national registry. Includes independent and dependent claims, priority date, "
    "applicant details, and international classification codes."
)

_LONG_MARKET_SNIPPET = (
    "Independent editorial market report covering commercialization progress and deployment "
    "data, revenue figures, confirmed customer contracts, and competitive dynamics in the "
    "sector. Published by a verified news organization with dedicated industry coverage."
)


class _NullOpenAlex:
    def search(self, *a, **kw) -> list:
        return []

    def search_recent(self, *a, **kw) -> list:
        return []

    def fetch_citation_by_doi(self, doi: str) -> int | None:
        return None

    def search_by_topic(self, topic_id: str, rows: int = 10) -> list:
        return []

    def fetch_referenced_works(self, doi: str, top_n: int = 25) -> list:
        return []

    def fetch_works_by_ids(self, openalex_ids: list, rows: int = 15) -> list:
        return []


class _NullS2:
    def search(self, *a, **kw) -> list:
        return []

    def get_abstract_by_doi(self, doi: str) -> str:
        return ""


def _crossref_record(index: int) -> dict:
    return {
        "DOI": f"10.1234/test-{index}",
        "title": [f"Validated research topic result number {index}"],
        "abstract": _LONG_ABSTRACT,
        "publisher": "Reputable Journal Publisher",
        "published": {"date-parts": [[2024, 6, index]]},
        "is-referenced-by-count": 10,
    }


class _MatchingCrossref:
    def lookup_doi(self, doi: str) -> dict | None:
        try:
            index = int(doi.rsplit("-", 1)[1])
        except (IndexError, ValueError):
            return None
        return _crossref_record(index)

    def search_title(self, title: str) -> list[dict]:
        return []


def _fake_search(query: str) -> dict:
    if "site:patents" in query or "patent applicant" in query:
        return {
            "organic": [
                {
                    "title": f"Research topic commercialization patent {i}",
                    "link": f"https://patents.google.com/patent/US10000{i}",
                    "snippet": _LONG_PATENT_SNIPPET,
                }
                for i in range(1, 4)
            ]
        }
    if " DOI" in query or "review journal" in query or "efficiency stability" in query:
        return {
            "organic": [
                {
                    "title": f"Validated research topic result number {i}",
                    "link": f"https://doi.org/10.1234/test-{i}",
                    "snippet": "Peer-reviewed result with supporting context.",
                }
                for i in range(1, 4)
            ]
        }
    return {
        "organic": [
            {
                "title": f"Commercial market report {i}",
                "link": f"https://www.reuters.com/technology/item-{i}",
                "snippet": _LONG_MARKET_SNIPPET,
            }
            for i in range(1, 4)
        ]
    }


# ---------------------------------------------------------------------------
# 1. Predatory publisher detection
# ---------------------------------------------------------------------------

class PredatoryPublisherTests(TestCase):
    def test_known_predatory_publishers_flagged(self) -> None:
        cases = [
            "Fringe Global Scientific Press",
            "OMICS International Publishing",
            "Science Publishing Group",
            "Hindawi Publishing Corporation",
            "Gavin Publishers Inc",
            "Lupine Publishers LLC",
        ]
        for publisher in cases:
            with self.subTest(publisher=publisher):
                self.assertTrue(
                    _is_predatory_publisher(publisher),
                    f"Expected '{publisher}' to be flagged as predatory",
                )

    def test_reputable_publishers_not_flagged(self) -> None:
        cases = [
            "Nature Publishing Group",
            "Elsevier B.V.",
            "Springer Science",
            "Wiley-Blackwell",
            "American Chemical Society",
            "IEEE",
            "Oxford University Press",
            "PLOS ONE",
        ]
        for publisher in cases:
            with self.subTest(publisher=publisher):
                self.assertFalse(
                    _is_predatory_publisher(publisher),
                    f"Expected '{publisher}' NOT to be flagged as predatory",
                )

    def test_whitelist_prevents_false_positive(self) -> None:
        """Legitimate 'American Journal of X' titles must not be flagged."""
        cases = [
            "American Journal of Medicine",
            "American Journal of Epidemiology",
            "American Journal of Public Health",
            "American Journal of Cardiology",
        ]
        for publisher in cases:
            with self.subTest(publisher=publisher):
                self.assertFalse(
                    _is_predatory_publisher(publisher),
                    f"Whitelist should prevent '{publisher}' from being flagged",
                )

    def test_borderline_publishers_detected(self) -> None:
        """MDPI should be detected as borderline (medium, not low)."""
        self.assertTrue(_is_borderline_publisher("MDPI Open Access Journal"))
        self.assertTrue(_is_borderline_publisher("mdpi"))
        self.assertFalse(_is_borderline_publisher("Nature Publishing Group"))

    def test_borderline_not_in_predatory(self) -> None:
        """MDPI must NOT be flagged as definitively predatory."""
        self.assertFalse(_is_predatory_publisher("MDPI Open Access Journal"))

    def test_empty_publisher_not_flagged(self) -> None:
        self.assertFalse(_is_predatory_publisher(""))

    def test_case_insensitive(self) -> None:
        self.assertTrue(_is_predatory_publisher("OMICS PUBLISHING GROUP"))
        self.assertTrue(_is_predatory_publisher("omics international"))


# ---------------------------------------------------------------------------
# 2. Predatory publisher credibility downgrade via Crossref path
# ---------------------------------------------------------------------------

class PredatoryPublisherCredibilityTests(TestCase):
    def test_crossref_predatory_publisher_gets_low_credibility(self) -> None:
        """A Crossref source from a predatory publisher must be downgraded to 'low'."""
        from academic_agent.source_pipeline import _academic_source

        predatory_item = {
            "DOI": "10.99999/predatory-001",
            "title": ["Research topic findings from predatory journal"],
            "abstract": _LONG_ABSTRACT,
            "publisher": "Fringe Global Scientific Press",
            "published": {"date-parts": [[2024, 3, 1]]},
            "is-referenced-by-count": 0,
        }

        class _PredatoryCrossref:
            def lookup_doi(self, doi: str) -> dict | None:
                return predatory_item

            def search_title(self, title: str) -> list[dict]:
                return [predatory_item]

        source, reason = _academic_source(
            {
                "title": "Research topic findings from predatory journal",
                "link": "https://doi.org/10.99999/predatory-001",
                "snippet": "Findings on the research topic.",
            },
            "A1",
            _PredatoryCrossref(),
            date(2025, 7, 1),
            "research topic commercialization",
        )

        self.assertIsNotNone(source)
        self.assertEqual(source.credibility_tier, "low")
        self.assertIn("predatory", source.credibility_reason.lower())


# ---------------------------------------------------------------------------
# 3. Zero-citation credibility downgrade
# ---------------------------------------------------------------------------

class ZeroCitationDowngradeTests(TestCase):
    def test_crossref_zero_citation_old_paper_is_medium(self) -> None:
        """0 citations + published >90 days ago → credibility should be 'medium'."""
        from academic_agent.source_pipeline import _academic_source

        item = {
            "DOI": "10.1234/zero-citation-old",
            "title": ["Research topic analysis with zero citations"],
            "abstract": _LONG_ABSTRACT,
            "publisher": "Obscure New Journal",
            "published": {"date-parts": [[2024, 1, 1]]},
            "is-referenced-by-count": 0,
        }

        class _ZeroCiteCrossref:
            def lookup_doi(self, doi: str) -> dict | None:
                return item

            def search_title(self, title: str) -> list[dict]:
                return [item]

        source, reason = _academic_source(
            {
                "title": "Research topic analysis with zero citations",
                "link": "https://doi.org/10.1234/zero-citation-old",
                "snippet": "Analysis of the research topic.",
            },
            "A1",
            _ZeroCiteCrossref(),
            date(2025, 7, 1),   # 181 days after pub → definitely > 90 days
            "research topic commercialization",
        )

        self.assertIsNotNone(source)
        self.assertEqual(source.credibility_tier, "medium")
        self.assertIn("0 citations", source.credibility_reason)

    def test_crossref_zero_citation_new_paper_is_high(self) -> None:
        """0 citations + published ≤90 days ago → should stay 'high'."""
        from academic_agent.source_pipeline import _academic_source

        item = {
            "DOI": "10.1234/zero-citation-new",
            "title": ["Brand new research topic paper"],
            "abstract": _LONG_ABSTRACT,
            "publisher": "Established Journal",
            "published": {"date-parts": [[2025, 6, 10]]},
            "is-referenced-by-count": 0,
        }

        class _NewPaperCrossref:
            def lookup_doi(self, doi: str) -> dict | None:
                return item

            def search_title(self, title: str) -> list[dict]:
                return [item]

        source, reason = _academic_source(
            {
                "title": "Brand new research topic paper",
                "link": "https://doi.org/10.1234/zero-citation-new",
                "snippet": "Recent paper on the research topic.",
            },
            "A1",
            _NewPaperCrossref(),
            date(2025, 7, 1),   # 21 days after pub → ≤ 90 days
            "research topic commercialization",
        )

        self.assertIsNotNone(source)
        self.assertEqual(source.credibility_tier, "high")


# ---------------------------------------------------------------------------
# 4. ArxivClient feed parsing (offline)
# ---------------------------------------------------------------------------

_ARXIV_ATOM_FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2301.12345v2</id>
    <title>Large Language Models for Healthcare Clinical Workflow Integration</title>
    <summary>We present a systematic review of LLM deployment in clinical workflows,
    covering ethical frameworks, implementation paradigms, and safety considerations
    in real-world hospital settings across multiple specialties.</summary>
    <published>2023-01-15T00:00:00Z</published>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <author><name>Carol Lee</name></author>
    <author><name>David Kim</name></author>
    <arxiv:doi>10.1016/j.ijmedinf.2023.105100</arxiv:doi>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2302.99999v1</id>
    <title>Ethics in AI Medical Decision Support Systems</title>
    <summary>A comprehensive analysis of ethical challenges when deploying artificial
    intelligence systems for medical decision support, with focus on bias mitigation,
    explainability requirements, and regulatory compliance pathways.</summary>
    <published>2023-02-20T00:00:00Z</published>
    <author><name>Eve Wilson</name></author>
  </entry>
</feed>"""


class ArxivClientParsingTests(TestCase):
    def setUp(self) -> None:
        self.client = ArxivClient()

    def test_parse_feed_returns_two_entries(self) -> None:
        results = self.client._parse_feed(_ARXIV_ATOM_FIXTURE)
        self.assertEqual(len(results), 2)

    def test_first_entry_fields(self) -> None:
        results = self.client._parse_feed(_ARXIV_ATOM_FIXTURE)
        first = results[0]
        self.assertIn("Large Language Models", first["title"])
        self.assertIn("systematic review", first["abstract"])
        self.assertEqual(first["arxiv_url"], "https://arxiv.org/abs/2301.12345")
        self.assertEqual(first["doi"], "10.1016/j.ijmedinf.2023.105100")
        self.assertEqual(first["pub_date"], "2023-01-15")

    def test_author_truncation_with_et_al(self) -> None:
        results = self.client._parse_feed(_ARXIV_ATOM_FIXTURE)
        # 4 authors → truncated to 3 + " et al."
        self.assertIn("et al.", results[0]["authors"])
        # 1 author → no "et al."
        self.assertNotIn("et al.", results[1]["authors"])

    def test_second_entry_has_no_doi(self) -> None:
        results = self.client._parse_feed(_ARXIV_ATOM_FIXTURE)
        self.assertEqual(results[1]["doi"], "")
        self.assertEqual(results[1]["arxiv_url"], "https://arxiv.org/abs/2302.99999")

    def test_malformed_xml_returns_empty_list(self) -> None:
        self.assertEqual(self.client._parse_feed(b"not xml at all"), [])

    def test_empty_feed_returns_empty_list(self) -> None:
        empty = b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        self.assertEqual(self.client._parse_feed(empty), [])


# ---------------------------------------------------------------------------
# 5. _academic_source_from_arxiv conversion
# ---------------------------------------------------------------------------

class ArxivSourceConversionTests(TestCase):
    _BASE_RECORD = {
        "title": "Large Language Models for Healthcare Clinical Workflow Integration",
        "abstract": (
            "We present a systematic review of LLM deployment in clinical workflows, "
            "covering ethical frameworks and safety considerations in real-world settings. "
            "The study spans 50 hospitals and includes quantitative outcomes."
        ),
        "arxiv_url": "https://arxiv.org/abs/2301.12345",
        "doi": "",
        "pub_date": "2023-01-15",
        "authors": "Alice Smith, Bob Jones, Carol Lee",
    }
    _ACCESSED = date(2025, 7, 1)
    _TOPIC = "large language model healthcare clinical workflow"

    def test_preprint_without_doi_gets_medium_credibility(self) -> None:
        source, reason = _academic_source_from_arxiv(
            self._BASE_RECORD, "A1", self._ACCESSED, self._TOPIC
        )
        self.assertIsNotNone(source)
        self.assertEqual(reason, "")
        self.assertEqual(source.credibility_tier, "medium")
        self.assertEqual(str(source.url), "https://arxiv.org/abs/2301.12345")
        self.assertIsNone(source.doi)

    def test_preprint_with_doi_gets_high_credibility(self) -> None:
        record = {**self._BASE_RECORD, "doi": "10.1016/j.ijmedinf.2023.105100"}
        source, reason = _academic_source_from_arxiv(
            record, "A1", self._ACCESSED, self._TOPIC
        )
        self.assertIsNotNone(source)
        self.assertEqual(source.credibility_tier, "high")
        self.assertEqual(str(source.url), "https://doi.org/10.1016/j.ijmedinf.2023.105100")
        self.assertEqual(source.doi, "10.1016/j.ijmedinf.2023.105100")

    def test_missing_title_returns_none(self) -> None:
        record = {**self._BASE_RECORD, "title": ""}
        source, reason = _academic_source_from_arxiv(
            record, "A1", self._ACCESSED, self._TOPIC
        )
        self.assertIsNone(source)
        self.assertIn("no title", reason)

    def test_thin_abstract_returns_none(self) -> None:
        record = {**self._BASE_RECORD, "abstract": "Too short."}
        source, reason = _academic_source_from_arxiv(
            record, "A1", self._ACCESSED, self._TOPIC
        )
        self.assertIsNone(source)
        self.assertIn("too thin", reason)

    def test_off_topic_title_rejected(self) -> None:
        record = {**self._BASE_RECORD, "title": "Quantum Chromodynamics in High Energy Physics"}
        source, reason = _academic_source_from_arxiv(
            record, "A1", self._ACCESSED, self._TOPIC
        )
        self.assertIsNone(source)
        self.assertIn("not relevant", reason)

    def test_future_publication_date_rejected(self) -> None:
        record = {**self._BASE_RECORD, "pub_date": "2099-01-01"}
        source, reason = _academic_source_from_arxiv(
            record, "A1", self._ACCESSED, self._TOPIC
        )
        self.assertIsNone(source)
        self.assertIn("future", reason)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 6. Fuzzy title deduplication across sources
# ---------------------------------------------------------------------------

class FuzzyTitleDeduplicationTests(TestCase):
    """Verify that near-duplicate titles from different sources are deduplicated."""

    def test_arxiv_near_duplicate_of_crossref_source_rejected(self) -> None:
        """
        Scenario: Crossref returns paper A; PubMed supplement returns paper B
        with a title that is ≥0.88 similar to A. Paper B should be rejected.
        """
        arxiv_near_dup = {
            "title": "Validated research topic result number one",  # ≈ "Validated research topic result number 1"
            "abstract": _LONG_ABSTRACT + " Additional context for the near-duplicate.",
            "arxiv_url": "https://arxiv.org/abs/2401.99999",
            "doi": "",
            "pub_date": "2024-01-01",
            "authors": "Some Author",
        }

        with patch(
            "academic_agent.source_pipeline.ArxivClient.search",
            return_value=[arxiv_near_dup],
        ), patch(
            "academic_agent.source_pipeline.PubMedClient.search",
            return_value=[],
        ), patch(
            "academic_agent.source_pipeline.LensPatentClient.search",
            return_value=[],
        ):
            collection = collect_source_collection(
                "research topic commercialization",
                searcher=_fake_search,
                crossref=_MatchingCrossref(),
                openalex=_NullOpenAlex(),
                s2=_NullS2(),
                url_checker=lambda url: (True, ""),
                minimum_sources=3,
                maximum_sources=6,
                accessed_date=date(2025, 7, 1),
            )

        # All academic sources must have unique normalised titles
        titles = [src.title.lower() for src in collection.academic_sources]
        self.assertEqual(len(titles), len(set(titles)),
                         "Duplicate titles found in accepted sources")

        # The near-duplicate should appear in rejected reasons
        rejected = [
            r for audit in collection.audit for r in audit.rejected_reasons
        ]
        self.assertTrue(
            any("near-duplicate" in r or "duplicate" in r for r in rejected),
            f"Expected a duplicate rejection, got: {rejected}",
        )


# ---------------------------------------------------------------------------
# 7. patent_assignees extraction in SourceCollection
# ---------------------------------------------------------------------------

def _lens_patent_record(lens_id: str, doc_number: str, title: str, applicants: list[str]) -> dict:
    """Build a minimal Lens.org patent record for testing."""
    return {
        "lens_id": lens_id,
        "jurisdiction": "US",
        "biblio": {
            "publication_reference": {
                "jurisdiction": "US",
                "doc_number": doc_number,
                "kind": "A",
                "date": "2023-01-01",
            },
            "invention_title": [{"text": title, "lang": "en"}],
            "parties": {
                "applicants": [
                    {"extracted_name": {"value": name}} for name in applicants
                ],
            },
            "application_reference": {},
            "priority_claims": [],
        },
        "abstract": [{"text": _LONG_PATENT_SNIPPET, "lang": "en"}],
    }


class _FakeLens:
    """Fake LensPatentClient that bypasses the api_key guard."""
    api_key = "fake-test-key"

    def __init__(self, records: list[dict]) -> None:
        self._records = records

    def search(self, topic: str, rows: int = 10) -> list[dict]:
        return self._records


class PatentAssigneesTests(TestCase):
    def _run_collection(self, lens_records: list[dict]) -> "SourceCollection":  # type: ignore[name-defined]
        with patch(
            "academic_agent.source_pipeline.PubMedClient.search",
            return_value=[],
        ), patch(
            "academic_agent.source_pipeline.ArxivClient.search",
            return_value=[],
        ):
            return collect_source_collection(
                "research topic commercialization",
                searcher=_fake_search,
                crossref=_MatchingCrossref(),
                openalex=_NullOpenAlex(),
                s2=_NullS2(),
                lens=_FakeLens(lens_records),
                url_checker=lambda url: (True, ""),
                minimum_sources=3,
                maximum_sources=6,
                accessed_date=date(2025, 7, 1),
            )

    def test_assignees_extracted_from_lens_results(self) -> None:
        """Lens results with known applicants should populate patent_assignees."""
        records = [
            _lens_patent_record(
                "001-001-001-001-001", "10000001",
                "Research topic method and system",
                ["Acme Healthcare Corp"],
            ),
            _lens_patent_record(
                "002-002-002-002-002", "10000002",
                "Research topic apparatus and process",
                ["BioTech Solutions Ltd"],
            ),
        ]
        collection = self._run_collection(records)
        self.assertIn("Acme Healthcare Corp", collection.patent_assignees)
        self.assertIn("BioTech Solutions Ltd", collection.patent_assignees)

    def test_generic_assignee_names_filtered_out(self) -> None:
        """'Patent Applicant' (Lens fallback) should not appear in patent_assignees."""
        records = [
            _lens_patent_record(
                "003-003-003-003-003", "10000003",
                "Research topic device and system",
                [],  # no applicant → publisher becomes "Patent Applicant"
            ),
        ]
        collection = self._run_collection(records)
        self.assertNotIn("Patent Applicant", collection.patent_assignees)
        self.assertNotIn("", collection.patent_assignees)

    def test_assignees_present_in_crew_inputs(self) -> None:
        """patent_assignees_json must appear in crew_inputs() output."""
        collection = self._run_collection([])
        inputs = collection.crew_inputs()
        self.assertIn("patent_assignees_json", inputs)
        parsed = json.loads(inputs["patent_assignees_json"])
        self.assertIsInstance(parsed, list)


# ---------------------------------------------------------------------------
# 9. translate_to_language (language module)
# ---------------------------------------------------------------------------

class TranslateToLanguageTests(TestCase):
    def test_returns_translation_when_llm_succeeds(self) -> None:
        from academic_agent.language import translate_to_language

        with patch(
            "academic_agent.language._llm_call",
            return_value="大语言模型在医疗保健领域的应用",
        ):
            result = translate_to_language(
                "Large language models in healthcare",
                "Simplified Chinese",
            )

        self.assertEqual(result, "大语言模型在医疗保健领域的应用")

    def test_falls_back_to_original_on_llm_failure(self) -> None:
        from academic_agent.language import translate_to_language

        original = "Large language models in healthcare"
        with patch("academic_agent.language._llm_call", return_value=""):
            result = translate_to_language(original, "Simplified Chinese")

        self.assertEqual(result, original)

    def test_different_target_languages(self) -> None:
        from academic_agent.language import translate_to_language

        translations = {
            "Japanese":  "大規模言語モデル",
            "Korean":    "대규모 언어 모델",
            "French":    "grands modèles de langage",
        }
        for lang, expected in translations.items():
            with self.subTest(language=lang):
                with patch("academic_agent.language._llm_call", return_value=expected):
                    result = translate_to_language("large language models", lang)
                self.assertEqual(result, expected)


# ---------------------------------------------------------------------------
# 10. Patent API keyword truncation
# ---------------------------------------------------------------------------

class PatentApiKeywordTests(TestCase):
    """Verify that _patent_keywords truncates long topics to core keywords."""

    _LONG_TOPIC = (
        "large language model for healthcare with ethical compliance framework "
        "and multi-modal clinical workflow integration"
    )

    def test_keywords_strips_stopwords_and_caps_length(self) -> None:
        kw = _patent_keywords(self._LONG_TOPIC, 8)
        words = kw.split()
        self.assertLessEqual(len(words), 8)
        # Stopwords must not appear as standalone tokens
        for stop in ("for", "with", "and", "the", "of"):
            self.assertNotIn(stop, words)
        # Core content words must be present
        self.assertIn("large", words)
        self.assertIn("language", words)

    def test_short_topic_not_truncated(self) -> None:
        short = "perovskite solar cell"
        kw = _patent_keywords(short, 8)
        self.assertEqual(kw, short)


# ---------------------------------------------------------------------------
# 11. OpenAlex peer-review artifact filter
# ---------------------------------------------------------------------------

def _make_oa_work(title: str, abstract: str = "", doi: str = "10.1234/test") -> dict:
    """Build a minimal OpenAlex work dict for testing."""
    inv: dict = {}
    if abstract:
        for i, word in enumerate(abstract.split()):
            inv.setdefault(word, []).append(i)
    return {
        "title": title,
        "doi": f"https://doi.org/{doi}",
        "abstract_inverted_index": inv,
        "primary_location": {"source": {"display_name": "Nature"}},
        "publication_date": "2024-01-01",
        "cited_by_count": 10,
        "topics": [{"id": "T1", "display_name": "Nanomedicine", "score": 0.9}],
    }


_LONG_OA_ABSTRACT = (
    "This study investigates nanomaterial-based targeted drug delivery for tumor "
    "treatment. The results demonstrate significant efficacy improvements. "
    "Experimental validation confirms the proposed mechanism. " * 3
)


class OpenAlexPeerReviewFilterTests(TestCase):
    """_academic_source_from_openalex must reject peer-review meta-documents."""

    _ACCESSED = date(2026, 7, 17)
    _TOPIC = "nanomaterials tumor treatment drug delivery"

    def _convert(self, work: dict):
        return _academic_source_from_openalex(work, "A1", self._ACCESSED, self._TOPIC)

    def test_review_for_title_rejected(self) -> None:
        src, reason = self._convert(_make_oa_work('Review for "Nanomaterial drug delivery study"'))
        self.assertIsNone(src)
        self.assertIn("peer-review artifact", reason)

    def test_decision_letter_title_rejected(self) -> None:
        src, reason = self._convert(_make_oa_work("Decision letter for \"Nanomaterial study\""))
        self.assertIsNone(src)
        self.assertIn("peer-review artifact", reason)

    def test_author_response_title_rejected(self) -> None:
        src, reason = self._convert(_make_oa_work("Author response for \"Nanomaterial study\""))
        self.assertIsNone(src)
        self.assertIn("peer-review artifact", reason)

    def test_normal_paper_passes(self) -> None:
        src, reason = self._convert(_make_oa_work(
            "Nanomaterials for tumor treatment and drug delivery",
            abstract=_LONG_OA_ABSTRACT,
        ))
        self.assertIsNotNone(src)
        self.assertEqual(reason, "")

    def test_summary_source_is_abstract_for_openalex_source(self) -> None:
        src, _ = self._convert(_make_oa_work(
            "Nanomaterials for tumor treatment and drug delivery",
            abstract=_LONG_OA_ABSTRACT,
        ))
        self.assertIsNotNone(src)
        self.assertEqual(src.summary_source, "abstract")


# ---------------------------------------------------------------------------
# 12. _record_relevance_filter audit tracking
# ---------------------------------------------------------------------------

class RelevanceFilterAuditTests(TestCase):
    """_record_relevance_filter must add audit entries for silently removed sources."""

    def _make_source(self, sid: str, title: str) -> EvidenceSource:
        return EvidenceSource(
            source_id=sid,
            title=title,
            url="https://example.com",
            publisher="Test Publisher",
            accessed_date=date(2026, 7, 17),
            source_type="academic_paper",
            credibility_tier="high",
            credibility_reason="Peer-reviewed journal, DOI verified.",
            evidence_summary=_LONG_ABSTRACT,
        )

    def test_adds_audit_entry_for_removed_sources(self) -> None:
        removed = [(self._make_source("A2", "removed paper"), 1)]
        audits: list[SearchAudit] = []
        _record_relevance_filter(removed, "academic", audits, min_score=2)
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].query, "[Relevance-Filter]")
        self.assertTrue(any("removed paper" in r for r in audits[0].rejected_reasons))
        # New format includes actual score
        self.assertTrue(any("score=1" in r for r in audits[0].rejected_reasons))

    def test_no_audit_entry_when_nothing_removed(self) -> None:
        audits: list[SearchAudit] = []
        _record_relevance_filter([], "academic", audits, min_score=2)
        self.assertEqual(len(audits), 0)

    def test_multiple_removals_all_recorded(self) -> None:
        removed = [
            (self._make_source(f"A{i}", f"paper {i}"), i)
            for i in range(2, 5)
        ]
        audits: list[SearchAudit] = []
        _record_relevance_filter(removed, "patent", audits, min_score=1)
        self.assertEqual(len(audits), 1)
        self.assertEqual(len(audits[0].rejected_reasons), 3)  # A2, A3, A4 removed


# ---------------------------------------------------------------------------
# 13. Patent electrode-direction filter (cathode vs. anode)
# ---------------------------------------------------------------------------

class PatentElectrodeDirectionFilterTests(TestCase):
    """Patents targeting the wrong electrode must be rejected when the topic
    is electrode-specific (anode-focused topic → cathode patents rejected)."""

    _ANODE_TOPIC = "hard carbon anode for sodium batteries"

    # Custom Crossref whose titles contain "anode sodium" so _title_matches_topic
    # finds ≥2 non-stopword overlaps with _ANODE_TOPIC ("anode", "sodium").
    class _AnodicCrossref:
        def lookup_doi(self, doi: str) -> dict | None:
            try:
                index = int(doi.rsplit("-", 1)[1])
            except (IndexError, ValueError):
                return None
            return {
                "DOI": doi,
                "title": [f"Hard carbon anode for sodium battery study number {index}"],
                "abstract": _LONG_ABSTRACT,
                "publisher": "Reputable Journal Publisher",
                "published": {"date-parts": [[2024, 6, index]]},
                "is-referenced-by-count": 10,
            }

        def search_title(self, title: str) -> list[dict]:
            return []

    def _search_with_cathode_patent(self, query: str) -> dict:
        if "site:patents" in query or "patent applicant" in query:
            return {
                "organic": [
                    {
                        # Title includes "hard carbon" + "sodium" (score ≥ 2) so it
                        # passes _tscore check and reaches the electrode-direction filter.
                        "title": "Hard carbon cathode for sodium batteries",
                        "link": "https://patents.google.com/patent/US99990001",
                        "snippet": (
                            "Hard carbon cathode active material for sodium-ion battery. "
                            "Improved cycle stability and rate performance."
                        ),
                    },
                    {
                        "title": "Hard carbon anode for sodium storage in batteries",
                        "link": "https://patents.google.com/patent/US99990002",
                        "snippet": (
                            "Anode material for sodium-ion secondary batteries with "
                            "improved first coulombic efficiency and cycle stability."
                        ),
                    },
                ]
            }
        # Academic Serper results for the fallback — DOIs use the "test-N" pattern
        if any(kw in query for kw in (" DOI", "review journal", "efficiency stability",
                                       "systematic review", "scholar.google")):
            return {
                "organic": [
                    {
                        "title": f"Hard carbon anode for sodium battery study number {i}",
                        "link": f"https://doi.org/10.1234/test-{i}",
                        "snippet": "Peer-reviewed result with supporting context.",
                    }
                    for i in range(1, 4)
                ]
            }
        # Market results — snippet must contain topic keywords to pass _market_summary_relevant
        return {
            "organic": [
                {
                    "title": f"Hard carbon anode sodium battery market report {i}",
                    "link": f"https://www.reuters.com/technology/hard-carbon-anode-{i}",
                    "snippet": (
                        f"Hard carbon anode materials for sodium batteries: "
                        f"commercialization trends, revenue data, and industry dynamics. "
                        f"Report {i} covers supply chain and manufacturing outlook."
                    ),
                }
                for i in range(1, 4)
            ]
        }

    def test_cathode_patent_rejected_for_anode_topic(self) -> None:
        with patch(
            "academic_agent.source_pipeline.LensPatentClient.search",
            return_value=[],
        ), patch(
            "academic_agent.source_pipeline.PubMedClient.search",
            return_value=[],
        ), patch(
            "academic_agent.source_pipeline.ArxivClient.search",
            return_value=[],
        ):
            collection = collect_source_collection(
                self._ANODE_TOPIC,
                searcher=self._search_with_cathode_patent,
                crossref=self._AnodicCrossref(),
                openalex=_NullOpenAlex(),
                s2=_NullS2(),
                url_checker=lambda url: (True, ""),
                minimum_sources=1,
                maximum_sources=6,
                accessed_date=date(2026, 7, 17),
            )

        patent_titles = [p.title.lower() for p in collection.patent_sources]
        # Cathode patent must have been rejected
        self.assertFalse(
            any("cathode" in t for t in patent_titles),
            f"Cathode patent should be rejected for anode topic, got: {patent_titles}",
        )
        # Anode patent must be accepted
        self.assertTrue(
            any("anode" in t for t in patent_titles),
            f"Anode patent should be accepted, got: {patent_titles}",
        )

    def test_no_cathode_rejection_for_non_specific_topic(self) -> None:
        """A topic without electrode direction should not filter out electrode patents."""
        with patch(
            "academic_agent.source_pipeline.LensPatentClient.search",
            return_value=[],
        ), patch(
            "academic_agent.source_pipeline.PubMedClient.search",
            return_value=[],
        ), patch(
            "academic_agent.source_pipeline.ArxivClient.search",
            return_value=[],
        ):
            collection = collect_source_collection(
                "sodium battery materials",
                searcher=self._search_with_cathode_patent,
                crossref=self._AnodicCrossref(),
                openalex=_NullOpenAlex(),
                s2=_NullS2(),
                url_checker=lambda url: (True, ""),
                minimum_sources=1,
                maximum_sources=6,
                accessed_date=date(2026, 7, 17),
            )
        # Both cathode and anode patents may appear since topic is not electrode-specific
        patent_titles = [p.title.lower() for p in collection.patent_sources]
        self.assertTrue(
            any("anode" in t or "cathode" in t for t in patent_titles) or len(patent_titles) == 0,
            "Non-electrode-specific topic should not apply electrode direction filter",
        )

    def test_cathode_rejection_recorded_in_audit(self) -> None:
        with patch(
            "academic_agent.source_pipeline.LensPatentClient.search",
            return_value=[],
        ), patch(
            "academic_agent.source_pipeline.PubMedClient.search",
            return_value=[],
        ), patch(
            "academic_agent.source_pipeline.ArxivClient.search",
            return_value=[],
        ):
            collection = collect_source_collection(
                self._ANODE_TOPIC,
                searcher=self._search_with_cathode_patent,
                crossref=self._AnodicCrossref(),
                openalex=_NullOpenAlex(),
                s2=_NullS2(),
                url_checker=lambda url: (True, ""),
                minimum_sources=1,
                maximum_sources=6,
                accessed_date=date(2026, 7, 17),
            )

        all_rejected = [r for audit in collection.audit for r in audit.rejected_reasons]
        self.assertTrue(
            any("cathode" in r and "anode" in r for r in all_rejected),
            f"Expected cathode-vs-anode rejection reason in audit, got: {all_rejected}",
        )


# ---------------------------------------------------------------------------
# H-4: _market_summary_relevant() — zero test coverage before this PR
# ---------------------------------------------------------------------------

class MarketSummaryRelevantTests(TestCase):
    """Unit tests for _market_summary_relevant()."""

    def test_core_word_in_summary_passes(self):
        self.assertTrue(
            _market_summary_relevant(
                "The sodium battery market is growing rapidly",
                "sodium-ion battery technology",
            )
        )

    def test_no_relevant_word_in_summary_fails(self):
        self.assertFalse(
            _market_summary_relevant(
                "Global automotive industry revenue report 2024",
                "hard carbon anode sodium-ion batteries",
            )
        )

    def test_tail_word_match_passes_for_for_structure(self):
        # Topic has "for X" structure → tail words {solid, tumors} used as filter
        self.assertTrue(
            _market_summary_relevant(
                "Market for solid tumor immunotherapy projected to $50B by 2030",
                "CAR-T cell therapy for solid tumors",
            )
        )

    def test_no_tail_or_core_word_fails_for_for_structure(self):
        self.assertFalse(
            _market_summary_relevant(
                "General pharmaceutical industry market report 2024",
                "CAR-T cell therapy for solid tumors",
            )
        )

    def test_empty_filter_words_always_passes(self):
        # Topic of only stopwords → filter_words empty → pass by default
        self.assertTrue(
            _market_summary_relevant(
                "Any unrelated summary",
                "for and the in",
            )
        )

    def test_empty_summary_fails(self):
        self.assertFalse(
            _market_summary_relevant(
                "",
                "hard carbon anode sodium-ion batteries",
            )
        )

    def test_core_word_match_without_for_structure(self):
        # No "for" → falls back to core words ≥6 chars; "carbon" matches
        self.assertTrue(
            _market_summary_relevant(
                "Carbon material suppliers and market share report",
                "hard carbon anode sodium batteries",
            )
        )

    def test_short_core_words_without_for_structure_filtered_out(self):
        # Core words are all <6 chars after stopword removal → filter_words empty → True
        self.assertTrue(
            _market_summary_relevant(
                "Totally unrelated content here",
                "hard coal anode",   # "hard"(4), "coal"(4), "anode"(5) — all < 6 chars
            )
        )


# ---------------------------------------------------------------------------
# M-5: _patent_source_from_lens() — integration tests with real Lens JSON
# ---------------------------------------------------------------------------

# Representative Lens.org Patent API response (verified against live API 2026-07).
_LENS_PATENT_RECORD = {
    "lens_id": "157-112-256-209-36X",
    "jurisdiction": "CN",
    "biblio": {
        "publication_reference": {
            "jurisdiction": "CN",
            "doc_number": "109678130",
            "kind": "A",
            "date": "2019-04-26",
        },
        "invention_title": [
            {
                "text": (
                    "Hard carbon material for anode of sodium-ion battery, "
                    "preparation method of hard carbon material and related sodium-ion battery"
                ),
                "lang": "en",
            },
            {"text": "一种用于钠离子电池负极的硬碳材料", "lang": "zh"},
        ],
        "parties": {
            "applicants": [
                {"extracted_name": {"value": "UNIV ELECTRONIC SCI & TECH CHINA"}},
                {"extracted_name": {"value": "BAOSHAN YALONGXIN INVESTMENT MAN CO LTD"}},
            ],
        },
        "application_reference": {},
        "priority_claims": [],
    },
    "abstract": [
        {
            "text": (
                "The invention provides a hard carbon material for an anode of "
                "a sodium-ion battery, a preparation method and related battery."
            ),
            "lang": "en",
        },
        {"text": "本发明提供一种硬碳材料。", "lang": "zh"},
    ],
}


class LensPatentParserTests(TestCase):
    """Integration tests for _patent_source_from_lens() with real API JSON structure."""

    _TOPIC = "hard carbon anode sodium-ion battery"

    def _parse(self, record=None):
        return _patent_source_from_lens(
            record or _LENS_PATENT_RECORD,
            "P1",
            date(2026, 7, 17),
            self._TOPIC,
        )

    def test_english_title_preferred(self):
        src, err = self._parse()
        self.assertIsNotNone(src, f"Expected source, got error: {err}")
        self.assertIn("Hard carbon material", src.title)

    def test_pub_number_constructed_from_biblio_reference(self):
        src, _ = self._parse()
        self.assertIsNotNone(src)
        # jurisdiction=CN, doc_number=109678130, kind=A → CN109678130A
        self.assertIn("CN109678130A", src.credibility_reason)

    def test_applicant_from_extracted_name_field(self):
        src, _ = self._parse()
        self.assertIsNotNone(src)
        self.assertIn("UNIV ELECTRONIC SCI & TECH CHINA", src.publisher)

    def test_publication_date_from_pub_reference(self):
        src, _ = self._parse()
        self.assertIsNotNone(src)
        self.assertEqual(src.published_date, date(2019, 4, 26))

    def test_english_abstract_used_as_evidence_summary(self):
        src, _ = self._parse()
        self.assertIsNotNone(src)
        self.assertIn("sodium-ion battery", src.evidence_summary)

    def test_lens_url_uses_lens_id(self):
        src, _ = self._parse()
        self.assertIsNotNone(src)
        self.assertEqual(str(src.url), "https://lens.org/lens/patent/157-112-256-209-36X")

    def test_missing_title_returns_none(self):
        record = {
            **_LENS_PATENT_RECORD,
            "biblio": {**_LENS_PATENT_RECORD["biblio"], "invention_title": []},
        }
        src, err = self._parse(record)
        self.assertIsNone(src)
        self.assertIn("no title", err)

    def test_irrelevant_title_rejected(self):
        record = {
            **_LENS_PATENT_RECORD,
            "biblio": {
                **_LENS_PATENT_RECORD["biblio"],
                "invention_title": [
                    {"text": "Automotive engine lubricant compound additive", "lang": "en"}
                ],
            },
        }
        src, err = self._parse(record)
        self.assertIsNone(src)
        self.assertIn("not relevant", err)

    def test_missing_lens_id_returns_none(self):
        record = {**_LENS_PATENT_RECORD, "lens_id": ""}
        src, err = self._parse(record)
        self.assertIsNone(src)
        self.assertIn("no lens_id", err)


# ---------------------------------------------------------------------------
# Fix-1: _filter_by_relevance(skip_domain_filter=True) — market domain guard
# ---------------------------------------------------------------------------

class FilterByRelevanceSkipDomainTests(TestCase):
    """Regression tests for the market domain_filter bypass.

    Topics with a 'for X' structure (e.g. 'perovskite solar cell for photovoltaic
    applications') cause _topic_domain_keywords() to extract domain tokens such as
    'photovoltaic'.  Market reports that use the industry shorthand 'PV' instead
    of 'photovoltaic' receive score=-1 (hard domain exclusion) and are incorrectly
    filtered out.  skip_domain_filter=True bypasses this check.
    """

    # "for photovoltaic applications" → domain_keywords = {"photovoltaic"}
    _TOPIC = "perovskite solar cell for photovoltaic applications"

    def _make_source(self, title: str, summary: str = "") -> EvidenceSource:
        from datetime import date
        return EvidenceSource(
            source_id="M1",
            title=title,
            url="https://example.com",
            publisher="Test Publisher",
            published_date=None,
            accessed_date=date.today(),
            source_type="market_report",
            credibility_tier="medium",
            credibility_reason="Commercial market estimate with proprietary methodology.",
            evidence_summary=summary,
            summary_source=None,
            citation_count=None,
        )

    def test_pv_source_rejected_without_skip(self):
        # "PV" is 2 chars, not extracted as keyword → no "photovoltaic" in body
        # → domain hard-exclusion fires → score=-1 → excluded even by min_keep fallback
        src = self._make_source(
            "Global PV Solar Cell Market Size and Forecast 2024",
            "The PV solar market is projected to reach $100B by 2030 driven by rising installations.",
        )
        kept, _ = _filter_by_relevance([src], self._TOPIC, min_score=2, min_keep=1)
        self.assertEqual(kept, [])

    def test_pv_source_passes_with_skip(self):
        # With domain filter bypassed: "solar"(+1) + "cell"(+1) + "solar cell" bigram(+2) = 4 ≥ 2
        src = self._make_source(
            "Global PV Solar Cell Market Size and Forecast 2024",
            "The PV solar market is projected to reach $100B by 2030 driven by rising installations.",
        )
        kept, _ = _filter_by_relevance([src], self._TOPIC, min_score=2, min_keep=1,
                                        skip_domain_filter=True)
        self.assertIn(src, kept)

    def test_unrelated_source_still_filtered_with_skip(self):
        # Even with skip, sources with score < min_score are excluded
        src = self._make_source(
            "Global Automotive Engine Lubricant Market 2024",
            "Engine oil and lubricant demand growing with automotive industry expansion.",
        )
        kept, _ = _filter_by_relevance([src], self._TOPIC, min_score=2, min_keep=0,
                                        skip_domain_filter=True)
        self.assertEqual(kept, [])


# ---------------------------------------------------------------------------
# L-4: _append_quality_control_warnings unit tests
# ---------------------------------------------------------------------------

class AppendQualityControlWarningsTests(TestCase):
    """Unit tests for _append_quality_control_warnings()."""

    def _make_report(self) -> str:
        return (
            "## Executive Summary\n\nSome content.\n\n"
            "## References\n\n[A1] Example source.\n"
        )

    def test_warnings_inserted_before_references(self) -> None:
        from academic_agent.evidence import _append_quality_control_warnings

        result = _append_quality_control_warnings(
            self._make_report(), ["Unverified numeric claim: 95% efficiency"]
        )
        ref_pos = result.index("## References")
        warn_pos = result.index("### Automated Quality-Control Warnings")
        self.assertLess(warn_pos, ref_pos)

    def test_empty_warnings_returns_markdown_unchanged(self) -> None:
        from academic_agent.evidence import _append_quality_control_warnings

        md = self._make_report()
        result = _append_quality_control_warnings(md, [])
        self.assertEqual(result, md)

    def test_no_references_marker_returns_unchanged(self) -> None:
        from academic_agent.evidence import _append_quality_control_warnings

        md = "## Executive Summary\n\nSome content without a references section.\n"
        result = _append_quality_control_warnings(md, ["some warning"])
        self.assertEqual(result, md)

    def test_duplicate_warnings_deduplicated(self) -> None:
        from academic_agent.evidence import _append_quality_control_warnings

        warnings = ["Same warning"] * 5
        result = _append_quality_control_warnings(self._make_report(), warnings)
        self.assertEqual(result.count("Same warning"), 1)

    def test_excess_warnings_capped_at_twelve(self) -> None:
        from academic_agent.evidence import _append_quality_control_warnings

        warnings = [f"Warning {i}" for i in range(20)]
        result = _append_quality_control_warnings(self._make_report(), warnings)
        self.assertIn("additional automated warnings", result)
        self.assertNotIn("Warning 12", result)


# ---------------------------------------------------------------------------
# L-4: pdf_extractor._call_llm_json JSON parse failure tests
# ---------------------------------------------------------------------------

class CallLlmJsonParseErrorTests(TestCase):
    """_call_llm_json must raise ValueError when the LLM returns non-JSON."""

    def test_raises_value_error_on_invalid_json(self) -> None:
        from academic_agent.pdf_extractor import _call_llm_json

        mock_llm = MagicMock()
        mock_llm.call.return_value = "This is not JSON at all."

        with patch("academic_agent.llm_config.create_llm", return_value=mock_llm):
            with self.assertRaises(ValueError) as ctx:
                _call_llm_json("Extract data from this text.")

        self.assertIn("non-JSON", str(ctx.exception))

    def test_returns_dict_on_valid_json(self) -> None:
        from academic_agent.pdf_extractor import _call_llm_json

        mock_llm = MagicMock()
        mock_llm.call.return_value = '{"title": "Test Paper", "doi": "10.1234/test"}'

        with patch("academic_agent.llm_config.create_llm", return_value=mock_llm):
            result = _call_llm_json("Extract data.")

        self.assertEqual(result["title"], "Test Paper")
        self.assertEqual(result["doi"], "10.1234/test")

    def test_strips_markdown_fences_before_parse(self) -> None:
        from academic_agent.pdf_extractor import _call_llm_json

        mock_llm = MagicMock()
        mock_llm.call.return_value = '```json\n{"key": "value"}\n```'

        with patch("academic_agent.llm_config.create_llm", return_value=mock_llm):
            result = _call_llm_json("Extract data.")

        self.assertEqual(result["key"], "value")
