"""Accepted market sources take the publication date their own page states."""

from __future__ import annotations

import threading
import time
from datetime import date

from academic_agent import source_pipeline
from academic_agent.evidence import EvidenceSource
from academic_agent.source_pipeline import _date_market_pages, collect_source_collection
from api.retrieval_health import run_lanes
from tests.test_source_pipeline import (
    MatchingCrossref,
    _NullArXiv,
    _NullLens,
    _NullOpenAlex,
    _NullPubMed,
    _NullS2,
    fake_search,
)

ACCESSED = date(2026, 10, 22)
_SUMMARY = ("Independent editorial coverage of commercial deployment, customer contracts and "
            "funding in the sector, from a verified news organization.")


def source(source_id: str, url: str, source_type: str = "reputable_news",
           published: date | None = None) -> EvidenceSource:
    return EvidenceSource(source_id=source_id, title=f"Market record {source_id}", url=url,
                          publisher="Publisher", published_date=published, accessed_date=ACCESSED,
                          source_type=source_type, evidence_summary=_SUMMARY)


def test_only_undated_sources_the_rule_admits_are_read():
    sources = [
        source("M1", "https://news.example.com/bci/startups"),
        source("M2", "https://www.grandviewresearch.com/industry-analysis/bci-market", "market_report"),
        source("M3", "https://en.wikipedia.org/wiki/Brain-computer_interface", "other"),
        source("M4", "https://www.company.example.com/", "company_disclosure"),
        source("M5", "https://news.example.com/dated", published=date(2024, 3, 1)),
        source("M6", "https://news.example.com/no-metadata"),
    ]
    asked = []

    def dater(url, accessed):
        asked.append((url, accessed))
        return (date(2025, 9, 18), "json_ld") if url.endswith("/startups") else (None, "none")

    audit = _date_market_pages(sources, ACCESSED, dater)
    assert asked == [("https://news.example.com/bci/startups", ACCESSED),
                     ("https://news.example.com/no-metadata", ACCESSED)]
    assert [s.published_date for s in sources] == [date(2025, 9, 18), None, None, None, date(2024, 3, 1), None]
    assert (audit.domain, audit.result_count, audit.accepted_source_ids) == ("market", 2, ["M1"])
    assert audit.query.startswith("[Page-Dates]")
    assert audit.rejected_reasons == ["M6: no publication date found"]


def test_nothing_eligible_reads_nothing_and_adds_no_audit_row():
    def dater(*_args):
        raise AssertionError("no page may be read")

    sources = [source("M1", "https://www.grandviewresearch.com/x-market", "market_report")]
    assert _date_market_pages(sources, ACCESSED, dater) is None


def test_a_failing_late_or_future_page_stays_undated_without_holding_up_the_run(monkeypatch):
    monkeypatch.setattr(source_pipeline, "_PAGE_DATE_DEADLINE_SECONDS", 0.2)
    release = threading.Event()
    sources = [source("M1", "https://e.test/fails"), source("M2", "https://e.test/slow"),
               source("M3", "https://e.test/future"), source("M4", "https://e.test/fine")]

    def dater(url, _accessed):
        if url.endswith("fails"):
            raise OSError("connection reset")
        if url.endswith("slow"):
            release.wait(5)
            return date(2025, 1, 1), "json_ld"
        if url.endswith("future"):
            return date(2026, 10, 23), "meta"
        return date(2026, 2, 3), "itemprop"

    started = time.monotonic()
    try:
        audit = _date_market_pages(sources, ACCESSED, dater)
        assert time.monotonic() - started < 2
    finally:
        release.set()
    assert [s.published_date for s in sources] == [None, None, None, date(2026, 2, 3)]
    assert audit.accepted_source_ids == ["M4"]
    assert audit.rejected_reasons == ["M1: page could not be read", "M2: page not read within 0.2 s",
                                      "M3: no publication date found"]


def _collect(**kwargs):
    return collect_source_collection(
        "Test commercialization topic", searcher=fake_search, crossref=MatchingCrossref(),
        openalex=_NullOpenAlex(), s2=_NullS2(), pubmed=_NullPubMed(), arxiv=_NullArXiv(),
        lens=_NullLens(), url_checker=lambda url: (True, ""), minimum_sources=3,
        maximum_sources=3, accessed_date=date(2026, 6, 30), **kwargs)


def _page_dates_rows(collection):
    return [row for row in collection.audit if row.query.startswith("[Page-Dates]")]


def test_the_collector_dates_market_sources_and_records_which():
    asked = []

    def dater(url, _accessed):
        asked.append(url)
        return (date(2026, 5, 4), "meta") if url.endswith("test-2") else (None, "none")

    collection = _collect(page_dater=dater)
    # Academic and patent sources are never read for a date.
    assert sorted(asked) == sorted(str(s.url) for s in collection.market_sources)
    dated = [s for s in collection.market_sources if s.published_date is not None]
    assert [str(s.url) for s in dated] == ["https://www.reuters.com/technology/test-2"]
    assert dated[0].published_date == date(2026, 5, 4)
    [row] = _page_dates_rows(collection)
    assert row.accepted_source_ids == [dated[0].source_id]
    assert row.result_count == len(collection.market_sources)
    # The row records a step after retrieval, not a search lane.
    assert "Page-Dates" not in run_lanes(collection.model_dump(mode="json"))


def test_by_default_the_collector_reads_the_page_metadata(monkeypatch):
    pages = {"https://www.reuters.com/technology/test-1":
             '<script type="application/ld+json">{"datePublished": "2025-11-12T08:00:00Z"}</script>'}
    monkeypatch.setattr("academic_agent.page_dates.fetch_html", pages.get)

    collection = _collect()
    dated = {str(s.url): s.published_date for s in collection.market_sources if s.published_date}
    assert dated == {"https://www.reuters.com/technology/test-1": date(2025, 11, 12)}
    assert len(_page_dates_rows(collection)[0].accepted_source_ids) == 1
