"""Offline tests for deterministic source retrieval and metadata validation."""

from datetime import date
from unittest import TestCase

from academic_agent.source_pipeline import (
    SourceCollectionError,
    _academic_source,
    _web_source,
    collect_source_collection,
)


def _crossref_record(index: int) -> dict:
    return {
        "DOI": f"10.1234/test-{index}",
        "title": [f"Validated academic result {index}"],
        "publisher": "Test Journal Publisher",
        "published": {"date-parts": [[2025, 1, index]]},
    }


class MatchingCrossref:
    def lookup_doi(self, doi: str) -> dict | None:
        try:
            index = int(doi.rsplit("-", 1)[1])
        except (IndexError, ValueError):
            return None
        return _crossref_record(index)

    def search_title(self, title: str) -> list[dict]:
        return []


class MismatchingCrossref:
    def lookup_doi(self, doi: str) -> dict | None:
        return {
            "DOI": doi,
            "title": ["Completely unrelated metadata record"],
            "publisher": "Wrong Publisher",
            "published": {"date-parts": [[2025, 1, 1]]},
        }

    def search_title(self, title: str) -> list[dict]:
        return []


def fake_search(query: str) -> dict:
    if "site:patents" in query or "patent applicant" in query:
        return {
            "organic": [
                {
                    "title": f"Primary patent record {index}",
                    "link": f"https://patents.google.com/patent/US1000000{index}",
                    "snippet": "Official patent database result with applicant details.",
                }
                for index in range(1, 4)
            ]
        }
    if " DOI" in query or "review journal" in query or "efficiency stability" in query:
        return {
            "organic": [
                {
                    "title": f"Validated academic result {index}",
                    "link": f"https://doi.org/10.1234/test-{index}",
                    "snippet": "Peer-reviewed result with sufficient supporting context.",
                }
                for index in range(1, 4)
            ]
        }
    return {
        "organic": [
            {
                "title": f"Commercial deployment disclosure {index}",
                "link": f"https://www.reuters.com/technology/test-{index}",
                "snippet": "Commercial deployment evidence reported with useful context.",
            }
            for index in range(1, 4)
        ]
    }


class SourcePipelineTests(TestCase):
    def test_collection_returns_three_validated_registries(self) -> None:
        collection = collect_source_collection(
            "Test commercialization topic",
            searcher=fake_search,
            crossref=MatchingCrossref(),
            url_checker=lambda url: (True, ""),
            minimum_sources=3,
            maximum_sources=3,
            accessed_date=date(2026, 6, 30),
        )

        self.assertEqual(
            [source.source_id for source in collection.academic_sources],
            ["A1", "A2", "A3"],
        )
        self.assertEqual(
            [source.source_id for source in collection.patent_sources],
            ["P1", "P2", "P3"],
        )
        self.assertEqual(
            [source.source_id for source in collection.market_sources],
            ["M1", "M2", "M3"],
        )
        self.assertTrue(
            all(source.doi for source in collection.academic_sources)
        )
        inputs = collection.crew_inputs()
        self.assertIn('"source_id":"A1"', inputs["academic_sources_json"])
        self.assertIn("academic_search_queries_json", inputs)

    def test_mismatched_crossref_metadata_blocks_collection(self) -> None:
        with self.assertRaisesRegex(
            SourceCollectionError,
            "academic retrieval produced 0 validated sources",
        ):
            collect_source_collection(
                "Test commercialization topic",
                searcher=fake_search,
                crossref=MismatchingCrossref(),
                url_checker=lambda url: (True, ""),
                minimum_sources=3,
                maximum_sources=3,
                accessed_date=date(2026, 6, 30),
            )



    def test_market_user_generated_hosts_are_blocked(self) -> None:
        for host in ("www.youtube.com", "www.quora.com", "www.reddit.com"):
            with self.subTest(host=host):
                source, reason = _web_source(
                    {
                        "title": "User generated market claim",
                        "link": f"https://{host}/content/item",
                        "snippet": "A sufficiently long but unverified user-generated market claim.",
                    },
                    "M1",
                    "market",
                    date(2026, 7, 2),
                    lambda url: (True, ""),
                )

                self.assertIsNone(source)
                self.assertIn("blocked or not approved", reason)

    def test_market_sources_receive_type_and_credibility_grades(self) -> None:
        cases = (
            (
                "https://www.reuters.com/technology/example",
                "reputable_news",
                "medium",
            ),
            (
                "https://www.grandviewresearch.com/industry-analysis/example",
                "market_report",
                "medium",
            ),
            (
                "https://energy.gov/news/example",
                "government",
                "high",
            ),
            (
                "https://batteryco.com/news/commercial-deployment",
                "company_disclosure",
                "medium",
            ),
        )

        for index, (url, expected_type, expected_tier) in enumerate(cases, start=1):
            with self.subTest(url=url):
                source, reason = _web_source(
                    {
                        "title": f"Approved market source {index}",
                        "link": url,
                        "snippet": "A sufficiently detailed market disclosure or report summary.",
                    },
                    f"M{index}",
                    "market",
                    date(2026, 7, 2),
                    lambda value: (True, ""),
                )

                self.assertEqual(reason, "")
                self.assertIsNotNone(source)
                self.assertEqual(source.source_type, expected_type)
                self.assertEqual(source.credibility_tier, expected_tier)
                self.assertGreaterEqual(len(source.credibility_reason), 10)

    def test_academic_publishers_are_not_reused_as_market_sources(self) -> None:
        source, reason = _web_source(
            {
                "title": "Academic paper reused as market evidence",
                "link": "https://pubs.acs.org/doi/10.1234/example",
                "snippet": "A peer-reviewed abstract is not independent market evidence.",
            },
            "M1",
            "market",
            date(2026, 7, 2),
            lambda url: (True, ""),
        )

        self.assertIsNone(source)
        self.assertIn("blocked or not approved", reason)

    def test_collection_assigns_credibility_and_filters_duplicate_dois(self) -> None:
        def search_with_duplicate_market_result(query: str) -> dict:
            if (
                " DOI" in query
                or "review journal" in query
                or "efficiency stability" in query
                or "site:patents" in query
                or "patent applicant" in query
            ):
                return fake_search(query)
            return {
                "organic": [
                    {
                        "title": "Duplicate academic record presented as market news",
                        "link": "https://pubs.acs.org/doi/10.1234/test-1",
                        "snippet": "Duplicate DOI 10.1234/test-1 from the academic registry.",
                    },
                    *[
                        {
                            "title": f"Independent market report {index}",
                            "link": (
                                "https://www.reuters.com/technology/"
                                f"independent-{index}"
                            ),
                            "snippet": (
                                "Independent editorial market reporting with "
                                "sufficient context."
                            ),
                        }
                        for index in range(1, 4)
                    ],
                ]
            }

        collection = collect_source_collection(
            "Test commercialization topic",
            searcher=search_with_duplicate_market_result,
            crossref=MatchingCrossref(),
            url_checker=lambda url: (True, ""),
            minimum_sources=3,
            maximum_sources=3,
            accessed_date=date(2026, 7, 2),
        )

        self.assertTrue(
            all(
                source.credibility_tier == "high"
                for source in collection.academic_sources
            )
        )
        self.assertTrue(
            all(
                source.credibility_tier == "high"
                for source in collection.patent_sources
            )
        )
        self.assertTrue(
            all(
                source.credibility_tier == "medium"
                for source in collection.market_sources
            )
        )
        self.assertTrue(
            all(
                "reuters.com" in str(source.url)
                for source in collection.market_sources
            )
        )
        rejected_reasons = [
            reason
            for audit in collection.audit
            for reason in audit.rejected_reasons
        ]
        self.assertTrue(
            any("duplicates academic DOI" in reason for reason in rejected_reasons)
        )
    def test_patent_family_titles_are_deduplicated(self) -> None:
        def search_with_duplicate_patent_family(query: str) -> dict:
            if "site:patents" in query or "patent applicant" in query:
                records = (
                    ("Solid-State Li-S Batteries and Methods of Making Same", "US1"),
                    ("solid-state li-s batteries and methods of making same", "WO1"),
                    ("Distinct solid electrolyte separator", "US2"),
                    ("Distinct scalable battery manufacturing process", "US3"),
                )
                return {
                    "organic": [
                        {
                            "title": title,
                            "link": f"https://patents.google.com/patent/{patent_id}",
                            "snippet": "Official patent registry summary with sufficient detail.",
                        }
                        for title, patent_id in records
                    ]
                }
            return fake_search(query)

        collection = collect_source_collection(
            "Test commercialization topic",
            searcher=search_with_duplicate_patent_family,
            crossref=MatchingCrossref(),
            url_checker=lambda url: (True, ""),
            minimum_sources=3,
            maximum_sources=3,
            accessed_date=date(2026, 7, 2),
        )

        normalized_titles = [
            " ".join(source.title.lower().split())
            for source in collection.patent_sources
        ]
        self.assertEqual(len(normalized_titles), 3)
        self.assertEqual(
            normalized_titles.count(
                "solid-state li-s batteries and methods of making same"
            ),
            1,
        )
        rejected_reasons = [
            reason
            for audit in collection.audit
            for reason in audit.rejected_reasons
        ]
        self.assertTrue(
            any("duplicate patent family title" in reason for reason in rejected_reasons)
        )
    def test_generic_crossref_title_is_rejected_as_topic_irrelevant(self) -> None:
        item = {
            "DOI": "10.5860/choice.48-2101",
            "title": ["World Resources Institute"],
            "publisher": "American Library Association",
            "published": {"date-parts": [[2010, 12, 1]]},
        }

        class StaticCrossref:
            def lookup_doi(self, doi: str) -> dict | None:
                return item

            def search_title(self, title: str) -> list[dict]:
                return [item]

        source, reason = _academic_source(
            {
                "title": "World Resources Institute",
                "link": "https://doi.org/10.5860/choice.48-2101",
                "snippet": "Direct air capture removes carbon dioxide from ambient air.",
            },
            "A1",
            StaticCrossref(),
            date(2026, 7, 2),
            "Direct air capture for carbon removal",
        )

        self.assertIsNone(source)
        self.assertIn("not relevant to research topic", reason)

    def test_conflicting_snippet_doi_rejects_academic_source(self) -> None:
        item = {
            "DOI": "10.1021/es502887y",
            "title": ["Reducing the Cost of Ca-Based Direct Air Capture of CO2"],
            "publisher": "American Chemical Society",
            "published": {"date-parts": [[2014, 10, 7]]},
        }

        class StaticCrossref:
            def lookup_doi(self, doi: str) -> dict | None:
                return None

            def search_title(self, title: str) -> list[dict]:
                return [item]

        source, reason = _academic_source(
            {
                "title": "Reducing the Cost of Ca-Based Direct Air Capture of CO2",
                "link": "https://pubs.acs.org/doi/abs/10.1021/es502887y",
                "snippet": "A different review is cited as DOI 10.1016/j.ces.2023.119416.",
            },
            "A1",
            StaticCrossref(),
            date(2026, 7, 2),
            "Direct air capture for carbon removal",
        )

        self.assertIsNone(source)
        self.assertIn("different DOI", reason)

    def test_crossref_abstract_is_preferred_over_search_snippet(self) -> None:
        item = {
            "DOI": "10.1234/direct-air-capture",
            "title": ["Direct Air Capture for Carbon Removal"],
            "publisher": "Test Publisher",
            "abstract": "<jats:p>Crossref abstract with validated direct air capture evidence.</jats:p>",
            "published": {"date-parts": [[2025, 1, 1]]},
        }

        class StaticCrossref:
            def lookup_doi(self, doi: str) -> dict | None:
                return item

            def search_title(self, title: str) -> list[dict]:
                return [item]

        source, reason = _academic_source(
            {
                "title": "Direct Air Capture for Carbon Removal",
                "link": "https://doi.org/10.1234/direct-air-capture",
                "snippet": "Search snippet should not replace the registry abstract.",
            },
            "A1",
            StaticCrossref(),
            date(2026, 7, 2),
            "Direct air capture for carbon removal",
        )

        self.assertEqual(reason, "")
        self.assertIsNotNone(source)
        self.assertIn("Crossref abstract", source.credibility_reason)
        self.assertIn("validated direct air capture evidence", source.evidence_summary)
        self.assertNotIn("Search snippet", source.evidence_summary)

    def test_research_institutes_are_allowed_and_pmc_is_academic(self) -> None:
        for index, host in enumerate(("www.iea.org", "www.wri.org"), start=1):
            with self.subTest(host=host):
                source, reason = _web_source(
                    {
                        "title": f"Authoritative direct air capture assessment {index}",
                        "link": f"https://{host}/reports/direct-air-capture",
                        "snippet": "Independent research assessment with sufficient context.",
                    },
                    f"M{index}",
                    "market",
                    date(2026, 7, 2),
                    lambda url: (True, ""),
                )
                self.assertEqual(reason, "")
                self.assertEqual(source.source_type, "research_institute")
                self.assertEqual(source.credibility_tier, "high")

        source, reason = _web_source(
            {
                "title": "Academic article mirrored by PMC",
                "link": "https://pmc.ncbi.nlm.nih.gov/articles/PMC8927912",
                "snippet": "Academic article content should not be market evidence.",
            },
            "M3",
            "market",
            date(2026, 7, 2),
            lambda url: (True, ""),
        )
        self.assertIsNone(source)
        self.assertIn("blocked or not approved", reason)

    def test_market_title_duplicate_of_academic_source_is_rejected(self) -> None:
        def search_with_title_duplicate(query: str) -> dict:
            if (
                " DOI" in query
                or "review journal" in query
                or "efficiency stability" in query
                or "site:patents" in query
                or "patent applicant" in query
            ):
                return fake_search(query)
            return {
                "organic": [
                    {
                        "title": "Validated academic result 1 - PMC",
                        "link": "https://pmc.ncbi.nlm.nih.gov/articles/PMC1",
                        "snippet": "The same academic record appears in market search.",
                    },
                    *[
                        {
                            "title": f"Independent market evidence {index}",
                            "link": f"https://www.reuters.com/technology/market-{index}",
                            "snippet": "Independent commercial reporting with useful context.",
                        }
                        for index in range(1, 4)
                    ],
                ]
            }

        collection = collect_source_collection(
            "Test commercialization topic",
            searcher=search_with_title_duplicate,
            crossref=MatchingCrossref(),
            url_checker=lambda url: (True, ""),
            minimum_sources=3,
            maximum_sources=3,
            accessed_date=date(2026, 7, 2),
        )

        rejected = [
            reason
            for audit in collection.audit
            for reason in audit.rejected_reasons
        ]
        self.assertTrue(any("duplicates academic title" in reason for reason in rejected))
        self.assertTrue(
            all("reuters.com" in str(source.url) for source in collection.market_sources)
        )
    def test_truncated_doi_snippet_is_rejected_without_crossref_abstract(self) -> None:
        item = {
            "DOI": "10.1021/es502887y",
            "title": ["Reducing the Cost of Ca-Based Direct Air Capture of CO2"],
            "publisher": "American Chemical Society",
            "published": {"date-parts": [[2014, 10, 7]]},
        }

        class StaticCrossref:
            def lookup_doi(self, doi: str) -> dict | None:
                return item

            def search_title(self, title: str) -> list[dict]:
                return [item]

        source, reason = _academic_source(
            {
                "title": "Reducing the Cost of Ca-Based Direct Air Capture of CO2",
                "link": "https://doi.org/10.1021/es502887y",
                "snippet": "Another article is listed as Journal 2024. https://doi.org ...",
            },
            "A1",
            StaticCrossref(),
            date(2026, 7, 2),
            "Direct air capture for carbon removal",
        )

        self.assertIsNone(source)
        self.assertIn("truncated or unverifiable DOI", reason)
