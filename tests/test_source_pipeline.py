"""Offline tests for deterministic source retrieval and metadata validation."""

from datetime import date
from unittest import TestCase
from unittest.mock import MagicMock, patch

from academic_agent.language import TopicSearchPlan

from academic_agent.source_pipeline import (
    SourceCollectionError,
    _academic_source,
    _detect_weight_profile,
    _web_source,
    collect_source_collection,
)


class _NullOpenAlex:
    """Stub that returns no results, forcing the Serper+Crossref fallback path."""

    def search(self, *args, **kwargs) -> list:  # type: ignore[override]
        return []

    def search_recent(self, *args, **kwargs) -> list:  # type: ignore[override]
        return []

    def fetch_citation_by_doi(self, doi: str) -> int | None:  # type: ignore[override]
        return None


class _NullS2:
    """Stub that returns no results from Semantic Scholar."""

    def search(self, *args, **kwargs) -> list:  # type: ignore[override]
        return []

    def get_abstract_by_doi(self, doi: str) -> str:
        return ""


class _NullPubMed:
    """Stub that returns no results from PubMed, for offline tests."""

    def search(self, *args, **kwargs) -> list:  # type: ignore[override]
        return []

    def search_mesh(self, *args, **kwargs) -> list:  # type: ignore[override]
        return []

    def get_mesh_terms(self, *args, **kwargs) -> list:  # type: ignore[override]
        return []


class _NullArXiv:
    """Stub that returns no results from arXiv, for offline tests."""

    def search(self, *args, **kwargs) -> list:  # type: ignore[override]
        return []


class _NullLens:
    """Stub that returns no results from Lens.org, for offline tests."""

    api_key: str = ""

    def search(self, *args, **kwargs) -> list:  # type: ignore[override]
        return []


_LONG_ACADEMIC_ABSTRACT = (
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


def _crossref_record(index: int) -> dict:
    return {
        "DOI": f"10.1234/test-{index}",
        "title": [f"Validated academic result {index}"],
        "abstract": _LONG_ACADEMIC_ABSTRACT,
        "publisher": "Test Journal Publisher",
        "published": {"date-parts": [[2025, 1, index]]},
        "is-referenced-by-count": 5,
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
                    "title": f"Test commercialization patent record {index}",
                    "link": f"https://patents.google.com/patent/US1000000{index}",
                    "snippet": _LONG_PATENT_SNIPPET,
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
                    "snippet": "Peer-reviewed result with supporting context.",
                }
                for index in range(1, 4)
            ]
        }
    return {
        "organic": [
            {
                "title": f"Commercial deployment disclosure {index}",
                "link": f"https://www.reuters.com/technology/test-{index}",
                "snippet": _LONG_MARKET_SNIPPET,
            }
            for index in range(1, 4)
        ]
    }


class SourcePipelineTests(TestCase):
    def test_free_form_native_input_reaches_sources_through_its_alias(self) -> None:
        """Assert the full retrieval seam, not only the planner's field value.

        The old code did search OpenAlex with the synonym, but converted every
        returned work against the longer literal translation. The value was
        generated and sent correctly yet never reached the source collection.
        """
        raw_topic = "我们在做剧本创作相关的大模型，帮我看看价值如何"
        plan = TopicSearchPlan(
            search_topic="large language models for screenplay creation",
            aliases=("LLM assisted screenwriting", "generative AI scriptwriting"),
        )

        abstract = (
            "This study evaluates language-model assistance for screenplay writing, "
            "including author control, narrative coherence, creative workflow design, "
            "and repeated human evaluation of generated scripts in professional practice."
        )

        titles = [
            "LLM Assisted Screenwriting for Narrative Production",
            "Professional Writer Evaluation of LLM Assisted Screenwriting",
            "Narrative Coherence and Author Control in LLM Assisted Screenwriting",
        ]

        def work(index: int) -> dict:
            inverted: dict[str, list[int]] = {}
            for position, word in enumerate(abstract.split()):
                inverted.setdefault(word, []).append(position)
            return {
                "title": titles[index - 1],
                "doi": f"https://doi.org/10.1234/screenwriting-{index}",
                "abstract_inverted_index": inverted,
                "primary_location": {"source": {"display_name": "Creative AI Journal"}},
                "publication_date": "2024-01-01",
                "cited_by_count": 10 + index,
                "topics": [],
            }

        class AliasOnlyOpenAlex(_NullOpenAlex):
            def __init__(self) -> None:
                self.queries: list[str] = []

            def search(self, query: str, *args, **kwargs) -> list:  # type: ignore[override]
                self.queries.append(query)
                if query == "LLM assisted screenwriting":
                    return [work(index) for index in range(1, 4)]
                return []

        openalex = AliasOnlyOpenAlex()
        with patch("academic_agent.language.plan_topic_search", return_value=plan):
            collection = collect_source_collection(
                raw_topic,
                searcher=lambda _query: {"organic": []},
                crossref=MatchingCrossref(),
                openalex=openalex,
                s2=_NullS2(),
                pubmed=_NullPubMed(),
                arxiv=_NullArXiv(),
                lens=_NullLens(),
                url_checker=lambda url: (True, ""),
                minimum_sources=3,
                maximum_sources=3,
                accessed_date=date(2026, 8, 19),
            )

        self.assertEqual(collection.topic, plan.search_topic)
        self.assertEqual(collection.display_topic, raw_topic)
        self.assertEqual(collection.search_aliases, list(plan.aliases))
        self.assertEqual(len(collection.academic_sources), 3)
        self.assertIn(plan.search_topic, openalex.queries)
        self.assertIn(plan.aliases[0], openalex.queries)

    def test_relevance_filter_shortage_triggers_strict_web_recovery(self) -> None:
        """Recover at the seam where the production screenwriting run failed.

        OpenAlex can fill the source budget with papers which mention the core
        technology but belong to another application domain. Before this
        regression, the web fallback saw a full pre-filter list and did not
        run; the final relevance filter then removed every paper and failed
        despite useful alias-led DOI results being available.
        """
        raw_topic = "We are building an LLM for scriptwriting; assess its value"
        plan = TopicSearchPlan(
            search_topic="large language models for scriptwriting",
            aliases=(
                "language model assistance for collaborative creative writing",
                "generative AI for narrative story creation",
            ),
        )

        off_topic_titles = (
            "Large Language Models for Medical Report Classification",
            "Large Language Models for Energy Demand Forecasting",
            "Large Language Models for Protein Sequence Analysis",
        )
        off_topic_abstract = (
            "This paper evaluates foundation models in a specialist scientific "
            "domain, with quantitative benchmarks, controlled experiments, and "
            "detailed error analysis across representative datasets."
        )

        def openalex_work(index: int) -> dict:
            inverted: dict[str, list[int]] = {}
            for position, word in enumerate(off_topic_abstract.split()):
                inverted.setdefault(word, []).append(position)
            return {
                "title": off_topic_titles[index - 1],
                "doi": f"https://doi.org/10.9999/off-topic-{index}",
                "abstract_inverted_index": inverted,
                "primary_location": {
                    "source": {"display_name": "Unrelated Journal"}
                },
                "publication_date": "2024-01-01",
                "cited_by_count": 12,
                "topics": [],
            }

        class MisleadingOpenAlex(_NullOpenAlex):
            def search_recent(self, *args, **kwargs) -> list:  # type: ignore[override]
                return [openalex_work(index) for index in range(1, 4)]

            def search(self, *args, **kwargs) -> list:  # type: ignore[override]
                return [openalex_work(index) for index in range(1, 4)]

        recovered_titles = (
            "Language Model Assistance for Collaborative Creative Writing",
            "Evaluating Language Model Assistance for Collaborative Creative Writing",
            "Author Control in Language Model Assistance for Collaborative Creative Writing",
        )
        recovered_abstract = (
            "This peer-reviewed study examines collaborative creative writing "
            "with language-model assistance, measuring narrative quality, "
            "author control, workflow efficiency, and screenwriter acceptance."
        )

        class RecoveryCrossref:
            def lookup_doi(self, doi: str) -> dict | None:
                try:
                    index = int(doi.rsplit("-", 1)[1])
                    title = recovered_titles[index - 1]
                except (IndexError, ValueError):
                    return None
                return {
                    "DOI": doi,
                    "title": [title],
                    "abstract": recovered_abstract,
                    "publisher": "Journal of Computational Creativity",
                    "published": {"date-parts": [[2025, 1, index]]},
                    "is-referenced-by-count": 7,
                }

            def search_title(self, title: str) -> list[dict]:
                return []

        recovery_queries: list[str] = []

        def recovery_search(query: str) -> dict:
            recovery_queries.append(query)
            if (
                "collaborative creative writing" not in query
                or "DOI journal" not in query
            ):
                return {"organic": []}
            return {
                "organic": [
                    {
                        "title": title,
                        "link": (
                            f"https://doi.org/10.5555/creative-writing-{index}"
                        ),
                        "snippet": recovered_abstract,
                    }
                    for index, title in enumerate(recovered_titles, start=1)
                ]
            }

        with patch("academic_agent.language.plan_topic_search", return_value=plan):
            collection = collect_source_collection(
                raw_topic,
                searcher=recovery_search,
                crossref=RecoveryCrossref(),
                openalex=MisleadingOpenAlex(),
                s2=_NullS2(),
                pubmed=_NullPubMed(),
                arxiv=_NullArXiv(),
                lens=_NullLens(),
                url_checker=lambda url: (True, ""),
                minimum_sources=3,
                maximum_sources=3,
                accessed_date=date(2026, 8, 19),
            )

        self.assertEqual(
            [source.title for source in collection.academic_sources],
            list(recovered_titles),
        )
        self.assertTrue(
            any("collaborative creative writing" in query for query in recovery_queries)
        )
        self.assertTrue(
            any(
                "collaborative creative writing" in query
                for query in collection.academic_queries
            )
        )
        self.assertTrue(
            any(
                audit.accepted_source_ids
                for audit in collection.audit
                if "collaborative creative writing" in audit.query
            )
        )

    def test_unresolved_free_form_input_fails_before_any_retrieval(self) -> None:
        searcher = MagicMock(return_value={"organic": []})
        unresolved = TopicSearchPlan(search_topic="", aliases=(), resolved=False)

        with patch("academic_agent.language.plan_topic_search", return_value=unresolved), \
             self.assertRaisesRegex(SourceCollectionError, "identify an assessable technology") \
             as caught:
            collect_source_collection("帮我看看这个", searcher=searcher)

        searcher.assert_not_called()
        self.assertEqual(caught.exception.diagnostics["stage"], "topic_planning")
        self.assertEqual(caught.exception.diagnostics["input_topic"], "帮我看看这个")

    def test_collection_returns_three_validated_registries(self) -> None:
        collection = collect_source_collection(
            "Test commercialization topic",
            searcher=fake_search,
            crossref=MatchingCrossref(),
            openalex=_NullOpenAlex(),
            s2=_NullS2(),
            pubmed=_NullPubMed(),
            arxiv=_NullArXiv(),
            lens=_NullLens(),
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
                openalex=_NullOpenAlex(),
                s2=_NullS2(),
                pubmed=_NullPubMed(),
                arxiv=_NullArXiv(),
                lens=_NullLens(),
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
                "https://www.kingsresearch.com/example-industry/example-market",
                "market_report",
                "medium",
            ),
            (
                "https://www.snsinsider.com/reports/example-market",
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

    def test_market_snippet_year_is_not_treated_as_publication_metadata(self) -> None:
        source, reason = _web_source(
            {
                "title": "Company commercialization update",
                "link": "https://www.reuters.com/technology/example-update",
                "snippet": (
                    "The company was founded in 2018 and now reports a commercial "
                    "pilot with customers in several industrial markets."
                ),
            },
            "M1",
            "market",
            date(2026, 7, 2),
            lambda _url: (True, ""),
        )
        self.assertEqual(reason, "")
        self.assertIsNone(source.published_date)

    def test_explicit_market_result_date_is_preserved(self) -> None:
        source, reason = _web_source(
            {
                "title": "Company commercialization update",
                "link": "https://www.reuters.com/technology/example-update",
                "date": "Jun 24, 2025",
                "snippet": (
                    "The company reports a commercial pilot with customers in "
                    "several industrial markets and a planned production line."
                ),
            },
            "M1",
            "market",
            date(2026, 7, 2),
            lambda _url: (True, ""),
        )
        self.assertEqual(reason, "")
        self.assertEqual(source.published_date, date(2025, 6, 24))

    def test_old_explicit_market_report_date_triggers_staleness_penalty(self) -> None:
        source, reason = _web_source(
            {
                "title": "Historical market forecast",
                "link": (
                    "https://www.grandviewresearch.com/industry-analysis/"
                    "historical-example"
                ),
                "date": "2020-01-02",
                "snippet": (
                    "The report estimates market demand and supplier activity "
                    "using a documented commercial forecasting methodology."
                ),
            },
            "M1",
            "market",
            date(2026, 7, 2),
            lambda _url: (True, ""),
        )
        self.assertEqual(reason, "")
        self.assertEqual(source.published_date, date(2020, 1, 2))
        self.assertEqual(source.credibility_tier, "low")
        self.assertIn("Stale market data", source.credibility_reason)

    def test_future_explicit_market_date_is_left_unknown(self) -> None:
        source, reason = _web_source(
            {
                "title": "Company commercialization update",
                "link": "https://www.reuters.com/technology/example-update",
                "date": "2030-01-01",
                "snippet": (
                    "The company reports a commercial pilot with customers in "
                    "several industrial markets and a planned production line."
                ),
            },
            "M1",
            "market",
            date(2026, 7, 2),
            lambda _url: (True, ""),
        )
        self.assertEqual(reason, "")
        self.assertIsNone(source.published_date)

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
                            "snippet": _LONG_MARKET_SNIPPET,
                        }
                        for index in range(1, 4)
                    ],
                ]
            }

        collection = collect_source_collection(
            "Test commercialization topic",
            searcher=search_with_duplicate_market_result,
            crossref=MatchingCrossref(),
            openalex=_NullOpenAlex(),
            s2=_NullS2(),
            pubmed=_NullPubMed(),
            arxiv=_NullArXiv(),
            lens=_NullLens(),
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
                source.credibility_tier == "medium"
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
                    ("Test Commercialization Patent Family Method One", "US1"),
                    ("test commercialization patent family method one", "WO1"),
                    ("Distinct Test Commercialization Electrolyte Method", "US2"),
                    ("Distinct Test Commercialization Manufacturing Process", "US3"),
                )
                return {
                    "organic": [
                        {
                            "title": title,
                            "link": f"https://patents.google.com/patent/{patent_id}",
                            "snippet": _LONG_PATENT_SNIPPET,
                        }
                        for title, patent_id in records
                    ]
                }
            return fake_search(query)

        collection = collect_source_collection(
            "Test commercialization topic",
            searcher=search_with_duplicate_patent_family,
            crossref=MatchingCrossref(),
            openalex=_NullOpenAlex(),
            s2=_NullS2(),
            pubmed=_NullPubMed(),
            arxiv=_NullArXiv(),
            lens=_NullLens(),
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
                "test commercialization patent family method one"
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
                        "snippet": "Independent research assessment with sufficient context for validated direct air capture evidence.",
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
                            "snippet": _LONG_MARKET_SNIPPET,
                        }
                        for index in range(1, 4)
                    ],
                ]
            }

        collection = collect_source_collection(
            "Test commercialization topic",
            searcher=search_with_title_duplicate,
            crossref=MatchingCrossref(),
            openalex=_NullOpenAlex(),
            s2=_NullS2(),
            pubmed=_NullPubMed(),
            arxiv=_NullArXiv(),
            lens=_NullLens(),
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


class WeightProfileDetectionTests(TestCase):
    """Verify that _detect_weight_profile maps topics to the correct weight profile."""

    def test_biomedical_drug_therapy(self):
        self.assertEqual(_detect_weight_profile("mRNA vaccine delivery mechanisms"), "biomedical")
        self.assertEqual(_detect_weight_profile("CAR-T cell therapy manufacturing"), "biomedical")
        self.assertEqual(_detect_weight_profile("antibody drug conjugate"), "biomedical")

    def test_blood_pressure_monitoring_is_biomedical(self):
        """The production canary's exact class must not fall through to industrial."""
        self.assertEqual(
            _detect_weight_profile(
                "Wearable continuous blood pressure monitoring via photoplethysmography"
            ),
            "biomedical",
        )
        # The fix is the biomedical measurement, not the generic word
        # "pressure"; industrial pressure monitoring must retain its profile.
        self.assertEqual(
            _detect_weight_profile("pipeline pressure monitoring for chemical plants"),
            "industrial",
        )

    def test_biomedical_bioprocess(self):
        # Food biotech / cellular agriculture markers added for cultivated-meat topics
        self.assertEqual(_detect_weight_profile("cultivated meat bioreactor scale-up"), "biomedical")
        self.assertEqual(_detect_weight_profile("bioreactor scale for cell culture"), "biomedical")
        self.assertEqual(_detect_weight_profile("cellular agriculture protein production"), "biomedical")
        self.assertEqual(_detect_weight_profile("tissue engineering scaffold"), "biomedical")
        self.assertEqual(_detect_weight_profile("stem cell expansion process"), "biomedical")

    def test_material_science(self):
        self.assertEqual(_detect_weight_profile("perovskite solar cell efficiency"), "material_science")
        self.assertEqual(_detect_weight_profile("solid-state electrolyte for lithium battery"), "material_science")
        self.assertEqual(_detect_weight_profile("graphene deposition thin film"), "material_science")
        self.assertEqual(_detect_weight_profile("catalyst synthesis route"), "material_science")

    def test_industrial_default(self):
        self.assertEqual(_detect_weight_profile("quantum computing hardware"), "industrial")
        self.assertEqual(_detect_weight_profile("autonomous vehicle sensor fusion"), "industrial")
        self.assertEqual(_detect_weight_profile("carbon capture utilization storage"), "industrial")

    def test_case_insensitive(self):
        self.assertEqual(_detect_weight_profile("Cultivated Meat Bioreactor"), "biomedical")
        self.assertEqual(_detect_weight_profile("PEROVSKITE SOLAR CELL"), "material_science")


class MarketQueryRecencyTests(TestCase):
    """Market queries carry a year window, and it has to move with the clock.

    The window was hard-coded as "2024 2025" — correct when written, still
    there in 2026, by which point the queries were steering retrieval away
    from the most recent eighteen months of company activity. Market evidence
    is the primary input to the TRL judgement, so a stale window quietly
    depresses the freshest signal the pipeline has. Nothing failed; the
    results just aged.
    """

    def test_window_tracks_the_current_year(self):
        from academic_agent.source_pipeline import _recent_years
        self.assertEqual(_recent_years(date(2026, 8, 12)), "2025 2026")
        self.assertEqual(_recent_years(date(2030, 1, 1)), "2029 2030")

    def test_no_year_literal_survives_in_market_queries(self):
        """The regression guard: any literal year here ages silently."""
        import re

        from academic_agent.source_pipeline import _queries, _recent_years

        current = set(_recent_years().split())
        market = _queries("solid-state batteries for electric vehicles")["market"]
        for query in market:
            with self.subTest(query=query[:50]):
                years = set(re.findall(r"\b(?:19|20)\d{2}\b", query))
                self.assertTrue(
                    years <= current,
                    f"{sorted(years - current)} is a fixed year in a market query; "
                    "use _recent_years() so the window moves with the clock",
                )

class ComponentQueryPlanningTests(TestCase):
    """Each building block gets a bounded query that cannot be crowded out."""

    def test_each_component_gets_an_independent_query_in_every_domain(self):
        from academic_agent.source_pipeline import _queries

        components = (
            "mycelium composite packaging",
            "distributed environmental sensors",
            "edge AI inference",
        )
        planned = _queries(
            "mycelium packaging with sensor networks and edge AI",
            components=components,
        )

        self.assertEqual(len(planned["patent"]), 6)
        self.assertFalse(any(" OR " in query for query in planned["patent"]))
        for component in components:
            with self.subTest(component=component):
                self.assertEqual(
                    sum(
                        query.startswith(f'"{component}"')
                        for query in planned["patent"]
                    ),
                    1,
                )
                self.assertTrue(any(
                    query.startswith(component) for query in planned["market"]
                ))
                self.assertTrue(any(
                    query.startswith(component) for query in planned["academic"]
                ))


class AuthorityQueryPlanningTests(TestCase):
    """Clinical-product searches must ask authority systems directly."""

    def test_gene_editing_queries_regulators_and_the_trial_registry_first(self):
        from academic_agent.source_pipeline import _queries

        market = _queries(
            "CRISPR gene editing for genetic diseases",
            weight_profile="biomedical",
        )["market"]
        self.assertIn("site:fda.gov", market[0])
        self.assertIn("site:ema.europa.eu", market[1])
        self.assertIn("site:clinicaltrials.gov", market[2])

    def test_blood_pressure_monitor_queries_regulators_but_not_trial_registry(self):
        """A marketed monitor needs regulator evidence, not an invented trial duty."""
        from academic_agent.source_pipeline import _queries

        topic = "Wearable continuous blood pressure monitoring via photoplethysmography"
        market = _queries(topic, weight_profile=_detect_weight_profile(topic))["market"]
        self.assertIn("site:fda.gov", market[0])
        self.assertIn("site:ema.europa.eu", market[1])
        self.assertFalse(any("clinicaltrials.gov" in query for query in market))

    def test_nonclinical_biomedical_methods_do_not_require_clinical_authorities(self):
        from academic_agent.source_pipeline import _queries

        topics = (
            "quantum computing for drug discovery",
            "CRISPR gene editing for drought-resistant crops",
        )
        for topic in topics:
            with self.subTest(topic=topic):
                market = _queries(topic, weight_profile="biomedical")["market"]
                self.assertFalse(any("site:fda.gov" in query for query in market))
                self.assertFalse(
                    any("site:clinicaltrials.gov" in query for query in market)
                )

    def test_the_wider_biomedical_profile_does_not_imply_clinical_authorities(self):
        from academic_agent.source_pipeline import _queries

        market = _queries(
            "cultivated meat for food industry",
            weight_profile="biomedical",
        )["market"]
        self.assertFalse(any("fda.gov" in query for query in market))
        self.assertFalse(any("clinicaltrials.gov" in query for query in market))


class AuthoritySourceClassificationTests(TestCase):
    """Authority labels require the real institution's DNS boundary."""

    def test_ema_is_an_official_regulator(self):
        from academic_agent.source_pipeline import _market_source_profile

        profile = _market_source_profile(
            "https://www.ema.europa.eu/en/medicines/human/example",
            "www.ema.europa.eu",
        )
        self.assertIsNotNone(profile)
        self.assertEqual(profile[:2], ("government", "high"))

    def test_clinicaltrials_is_an_official_registry(self):
        from academic_agent.source_pipeline import _market_source_profile

        profile = _market_source_profile(
            "https://clinicaltrials.gov/study/NCT00000000",
            "clinicaltrials.gov",
        )
        self.assertIsNotNone(profile)
        self.assertEqual(profile[:2], ("research_institute", "high"))

    def test_energy_department_is_government_not_a_research_institute(self):
        from academic_agent.source_pipeline import _market_source_profile

        profile = _market_source_profile(
            "https://www.energy.gov/eere/example",
            "www.energy.gov",
        )
        self.assertIsNotNone(profile)
        self.assertEqual(profile[:2], ("government", "high"))

    def test_official_standards_hosts_receive_the_authority_label(self):
        from academic_agent.source_pipeline import _market_source_profile

        cases = (
            ("https://www.iso.org/standard/12345.html", "www.iso.org"),
            ("https://webstore.iec.ch/publication/12345", "webstore.iec.ch"),
            (
                "https://standards.ieee.org/standard/1234-2026.html",
                "standards.ieee.org",
            ),
        )
        for url, host in cases:
            with self.subTest(host=host):
                profile = _market_source_profile(url, host)
                self.assertIsNotNone(profile)
                self.assertEqual(profile[:2], ("standards_body", "high"))

    def test_standards_looking_attacker_hosts_are_not_authoritative(self):
        from academic_agent.source_pipeline import _market_source_profile

        for host in ("iso.org.attacker.example", "standards.attacker.example"):
            with self.subTest(host=host):
                profile = _market_source_profile(
                    f"https://{host}/catalog/item",
                    host,
                )
                self.assertIsNone(profile)


class AuthorityCoverageTests(TestCase):
    @staticmethod
    def _source(source_id: str, url: str):
        from academic_agent.evidence import EvidenceSource

        return EvidenceSource(
            source_id=source_id,
            title="Official clinical authority record",
            url=url,
            publisher="Official Registry",
            accessed_date=date.today(),
            source_type="government",
            credibility_tier="high",
            credibility_reason="Official authority record for the stated jurisdiction.",
            evidence_summary=(
                "This official record describes the approval or registered clinical "
                "study status for the technology and indication named in the topic."
            ),
        )

    def test_complete_means_both_required_categories_are_present(self):
        from academic_agent.source_pipeline import _measure_authority_coverage

        coverage = _measure_authority_coverage(
            "CRISPR gene editing for genetic diseases",
            "biomedical",
            [
                self._source("M1", "https://www.fda.gov/vaccines-blood-biologics/example"),
                self._source("M2", "https://clinicaltrials.gov/study/NCT00000000"),
            ],
        )
        self.assertEqual(coverage.status, "complete")
        self.assertEqual(coverage.covered_source_ids["regulatory"], ["M1"])
        self.assertEqual(coverage.covered_source_ids["clinical_registry"], ["M2"])

    def test_missing_registry_is_incomplete_not_a_claim_that_no_trial_exists(self):
        from academic_agent.source_pipeline import _measure_authority_coverage

        coverage = _measure_authority_coverage(
            "CRISPR gene editing for genetic diseases",
            "biomedical",
            [self._source("M1", "https://www.fda.gov/medical-products/example")],
        )
        self.assertEqual(coverage.status, "incomplete")
        self.assertEqual(coverage.missing_categories, ["clinical_registry"])

    def test_blood_pressure_monitor_without_official_record_is_incomplete(self):
        """Market-page clearance claims do not satisfy official regulator coverage."""
        from academic_agent.source_pipeline import _measure_authority_coverage

        topic = "Wearable continuous blood pressure monitoring via photoplethysmography"
        coverage = _measure_authority_coverage(
            topic,
            _detect_weight_profile(topic),
            [],
        )
        self.assertEqual(coverage.status, "incomplete")
        self.assertEqual(coverage.required_categories, ["regulatory"])
        self.assertEqual(coverage.missing_categories, ["regulatory"])

    def test_nonclinical_topics_are_explicitly_not_applicable(self):
        from academic_agent.source_pipeline import _measure_authority_coverage

        coverage = _measure_authority_coverage(
            "solid-state batteries for electric vehicles", "material_science", []
        )
        self.assertEqual(coverage.status, "not_applicable")
        self.assertEqual(coverage.required_categories, [])


class ComponentCoverageTests(TestCase):
    """Compound-topic coverage is explicit, advisory, and honest about silence."""

    @staticmethod
    def _source(source_id: str, title: str):
        from academic_agent.evidence import EvidenceSource

        return EvidenceSource(
            source_id=source_id,
            title=title,
            publisher="Peer-reviewed Journal",
            url=f"https://example.org/{source_id.lower()}",
            accessed_date=date.today(),
            source_type="academic_paper",
            credibility_tier="high",
            credibility_reason="Peer-reviewed record with traceable publication metadata.",
            evidence_summary=(
                f"{title} is evaluated with reproducible methods and reports "
                "technical performance relevant to the stated research component."
            ),
        )

    def test_complete_requires_every_planned_component_to_appear(self):
        from academic_agent.source_pipeline import _measure_component_coverage

        components = (
            "mycelium composite packaging",
            "distributed environmental sensors",
            "edge AI inference",
        )
        coverage = _measure_component_coverage(
            components,
            [
                self._source("A1", "Mycelium composite packaging materials"),
                self._source("A2", "Distributed environmental sensor networks"),
                self._source("A3", "Edge AI inference for embedded devices"),
            ],
        )

        self.assertEqual(coverage.status, "complete")
        self.assertEqual(set(coverage.covered_source_ids), set(components))

    def test_missing_component_is_a_warning_not_an_absence_claim(self):
        from academic_agent.source_pipeline import _measure_component_coverage

        coverage = _measure_component_coverage(
            (
                "mycelium composite packaging",
                "distributed environmental sensors",
                "edge AI inference",
            ),
            [
                self._source("A1", "Mycelium composite packaging materials"),
                self._source("A2", "Distributed environmental sensor networks"),
            ],
        )

        self.assertEqual(coverage.status, "incomplete")
        self.assertEqual(coverage.missing_components, ["edge AI inference"])

    def test_non_discriminating_components_are_unchecked_not_complete(self):
        from academic_agent.source_pipeline import _measure_component_coverage

        coverage = _measure_component_coverage(
            ("artificial intelligence systems", "advanced methods"),
            [],
        )

        self.assertEqual(coverage.status, "unchecked")
        self.assertEqual(len(coverage.unchecked_components), 2)

    def test_single_technology_is_explicitly_not_applicable(self):
        from academic_agent.source_pipeline import _measure_component_coverage

        coverage = _measure_component_coverage(("solid-state batteries",), [])
        self.assertEqual(coverage.status, "not_applicable")


class BroadClinicalScopeTests(TestCase):
    def test_obviously_cross_indication_topic_gets_a_nonblocking_scope_instruction(self):
        from academic_agent.source_pipeline import _clinical_scope_warning

        warning = _clinical_scope_warning(
            "CRISPR gene editing for genetic diseases", "biomedical"
        )
        self.assertIsNotNone(warning)
        self.assertIn("multiple", warning)
        self.assertIn("MUST state the scope", warning)

    def test_specific_indication_is_not_flagged(self):
        from academic_agent.source_pipeline import _clinical_scope_warning

        self.assertIsNone(
            _clinical_scope_warning(
                "CAR-T cell therapy for relapsed B-cell lymphoma", "biomedical"
            )
        )


class PatentHostCredibilityTests(TestCase):
    """Patent discovery hosts must not all be described as official registries."""

    @staticmethod
    def _source(host: str):
        return _web_source(
            {
                "title": "Patent record for a commercial technology",
                "link": f"https://{host}/patent/WO2026123456A1/en",
                "snippet": (
                    "The patent record describes an invention, its applicants, "
                    "publication status, and claimed commercial technology use."
                ),
            },
            "P1",
            "patent",
            date.today(),
            lambda _url: (True, ""),
        )[0]

    def test_wipo_record_is_high_tier_and_official(self):
        source = self._source("patentscope.wipo.int")
        self.assertIsNotNone(source)
        self.assertEqual(source.credibility_tier, "high")
        self.assertIn("Official WIPO or EPO", source.credibility_reason)

    def test_google_patents_record_is_medium_tier_and_requires_verification(self):
        source = self._source("patents.google.com")
        self.assertIsNotNone(source)
        self.assertEqual(source.credibility_tier, "medium")
        self.assertIn("Secondary patent aggregator", source.credibility_reason)
