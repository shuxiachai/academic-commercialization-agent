"""Tests for features added in the recent development cycle.

Covers:
- Predatory publisher detection
- Fuzzy title deduplication across sources
- ArxivClient Atom feed parsing
- USPTOPatentClient source construction
- patent_assignees extraction in SourceCollection
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
    _is_borderline_publisher,
    _is_predatory_publisher,
    _patent_source_from_uspto,
    ArxivClient,
    LensPatentClient,
    USPTOPatentClient,
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
# 6. USPTOPatentClient source construction
# ---------------------------------------------------------------------------

class USPTOSourceConversionTests(TestCase):
    _RECORD = {
        "patent_number": "10123456",
        "patent_title": "System and method for LLM integration in clinical workflow",
        "patent_abstract": (
            "A system for integrating large language model outputs into electronic health "
            "record workflows with automated safety filtering and physician override controls."
        ),
        "patent_date": "2023-06-15",
        "assignee_organization": [
            {"assignee_organization": "MedTech Innovations Inc"},
            {"assignee_organization": "University Medical Center"},
        ],
    }
    _ACCESSED = date(2025, 7, 1)

    def test_basic_construction(self) -> None:
        source = _patent_source_from_uspto(self._RECORD, "P1", self._ACCESSED)
        self.assertIsNotNone(source)
        self.assertEqual(source.source_id, "P1")
        self.assertEqual(source.source_type, "patent")
        self.assertEqual(source.credibility_tier, "high")
        self.assertIn("US10123456", str(source.url))
        self.assertIn("MedTech Innovations Inc", source.publisher)
        self.assertEqual(source.published_date, date(2023, 6, 15))

    def test_missing_patent_number_returns_none(self) -> None:
        record = {**self._RECORD, "patent_number": ""}
        source = _patent_source_from_uspto(record, "P1", self._ACCESSED)
        self.assertIsNone(source)

    def test_missing_title_returns_none(self) -> None:
        record = {**self._RECORD, "patent_title": ""}
        source = _patent_source_from_uspto(record, "P1", self._ACCESSED)
        self.assertIsNone(source)

    def test_no_assignee_falls_back_to_uspto(self) -> None:
        record = {**self._RECORD, "assignee_organization": []}
        source = _patent_source_from_uspto(record, "P1", self._ACCESSED)
        self.assertIsNotNone(source)
        self.assertEqual(source.publisher, "USPTO")

    def test_abstract_used_as_evidence_summary(self) -> None:
        source = _patent_source_from_uspto(self._RECORD, "P1", self._ACCESSED)
        self.assertIn("large language model", source.evidence_summary.lower())

    def test_credibility_reason_includes_patent_number(self) -> None:
        source = _patent_source_from_uspto(self._RECORD, "P1", self._ACCESSED)
        self.assertIn("US10123456", source.credibility_reason)


# ---------------------------------------------------------------------------
# 7. Fuzzy title deduplication across sources
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
        ), patch(
            "academic_agent.source_pipeline.USPTOPatentClient.search",
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
# 8. patent_assignees extraction in SourceCollection
# ---------------------------------------------------------------------------

class PatentAssigneesTests(TestCase):
    def test_assignees_extracted_from_uspto_results(self) -> None:
        """USPTO results with known assignees should populate patent_assignees."""
        fake_uspto_records = [
            {
                "patent_number": "10000001",
                "patent_title": "Research topic method and system",
                "patent_abstract": _LONG_PATENT_SNIPPET,
                "patent_date": "2023-01-01",
                "assignee_organization": [
                    {"assignee_organization": "Acme Healthcare Corp"},
                ],
            },
            {
                "patent_number": "10000002",
                "patent_title": "Research topic apparatus and process",
                "patent_abstract": _LONG_PATENT_SNIPPET,
                "patent_date": "2023-06-01",
                "assignee_organization": [
                    {"assignee_organization": "BioTech Solutions Ltd"},
                ],
            },
        ]

        with patch(
            "academic_agent.source_pipeline.USPTOPatentClient.search",
            return_value=fake_uspto_records,
        ), patch(
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

        self.assertIn("Acme Healthcare Corp", collection.patent_assignees)
        self.assertIn("BioTech Solutions Ltd", collection.patent_assignees)

    def test_generic_assignee_names_filtered_out(self) -> None:
        """Generic values like 'USPTO' should not appear in patent_assignees."""
        fake_uspto_records = [
            {
                "patent_number": "10000003",
                "patent_title": "Research topic device",
                "patent_abstract": _LONG_PATENT_SNIPPET,
                "patent_date": "2023-01-01",
                "assignee_organization": [],  # → falls back to "USPTO"
            },
        ]

        with patch(
            "academic_agent.source_pipeline.USPTOPatentClient.search",
            return_value=fake_uspto_records,
        ), patch(
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

        self.assertNotIn("USPTO", collection.patent_assignees)
        self.assertNotIn("", collection.patent_assignees)

    def test_assignees_present_in_crew_inputs(self) -> None:
        """patent_assignees_json must appear in crew_inputs() output."""
        with patch(
            "academic_agent.source_pipeline.USPTOPatentClient.search",
            return_value=[],
        ), patch(
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

        inputs = collection.crew_inputs()
        self.assertIn("patent_assignees_json", inputs)
        # Must be valid JSON
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
    """Verify that both Lens and USPTO truncate long topics to core keywords."""

    _LONG_TOPIC = (
        "large language model for healthcare with ethical compliance framework "
        "and multi-modal clinical workflow integration"
    )

    def test_uspto_keywords_strips_stopwords_and_caps_length(self) -> None:
        kw = USPTOPatentClient._keywords(self._LONG_TOPIC, 8)
        words = kw.split()
        self.assertLessEqual(len(words), 8)
        # Stopwords must not appear as standalone tokens
        for stop in ("for", "with", "and", "the", "of"):
            self.assertNotIn(stop, words)
        # Core content words must be present
        self.assertIn("large", words)
        self.assertIn("language", words)

    def test_lens_keywords_same_behaviour(self) -> None:
        kw = LensPatentClient._keywords(self._LONG_TOPIC, 8)
        words = kw.split()
        self.assertLessEqual(len(words), 8)
        self.assertIn("large", words)

    def test_short_topic_not_truncated(self) -> None:
        short = "perovskite solar cell"
        kw = USPTOPatentClient._keywords(short, 8)
        self.assertEqual(kw, short)

    def test_uspto_query_body_uses_or_structure(self) -> None:
        """USPTO search body must use _or so both title and abstract are searched."""
        client = USPTOPatentClient()
        captured: list[dict] = []

        def _fake_urlopen(req, timeout=None):
            import json as _json
            captured.append(_json.loads(req.data))
            raise OSError("no network in test")

        with patch("academic_agent.source_pipeline.urlopen", side_effect=_fake_urlopen):
            client.search(self._LONG_TOPIC, rows=5)

        self.assertTrue(captured, "Expected at least one request to be built")
        q = captured[0].get("q", {})
        self.assertIn("_or", q, "Query must use _or to cover title and abstract")
        clauses = q["_or"]
        fields = [list(c.get("_text_any", {}).keys())[0] for c in clauses if "_text_any" in c]
        self.assertIn("patent_title", fields)
        self.assertIn("patent_abstract", fields)
