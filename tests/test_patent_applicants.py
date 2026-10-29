"""Web-search patents name who holds them, from the header of their Google Patents page."""

from __future__ import annotations

import threading
import time
from datetime import date
from unittest.mock import patch

import pytest

from academic_agent import patent_applicants, source_pipeline
from academic_agent.evidence import EvidenceSource
from academic_agent.patent_applicants import (
    applicants, assignees_from_html, google_patents_url, patent_dates, patent_page_facts,
)
from academic_agent.source_pipeline import _name_patent_applicants, collect_source_collection
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

_NOTE = "(The listed assignees may be inaccurate. Google has not performed a legal analysis.)"


def header(*, inventors=("Ada Lovelace",), current=(), original=(), before: str = "",
           publication: str | None = "2012-05-15") -> str:
    """A Google Patents header block, in the order the real pages use."""
    def dds(prop, names):
        return "".join(f'<dd itemprop="{prop}" repeat> {name} </dd>' for name in names)
    dates = ('<dt>Priority date</dt><dd><time itemprop="priorityDate" datetime="2005-04-15">2005-04-15</time></dd>'
             '<dt>Filing date</dt><dd><time itemprop="filingDate" datetime="2006-03-08">2006-03-08</time></dd>')
    if publication:
        dates += f'<dt>Publication date</dt><dd><time itemprop="publicationDate" datetime="{publication}">x</time></dd>'
    return (f"<html><body>{before}<dl><dt>Inventor</dt>{dds('inventor', inventors)}"
            + (f"<dt>Current Assignee {_NOTE}</dt>{dds('assigneeCurrent', current)}" if current else "")
            + (f"<dt>Original Assignee</dt>{dds('assigneeOriginal', original)}" if original else "")
            + dates + "</dl></body></html>")


def test_the_current_assignee_is_the_applicant_when_it_differs_from_the_original():
    page = header(current=("Spectra Systems &amp; Technologies Inc",), original=("Individual",))
    assert applicants(page) == (["Spectra Systems & Technologies Inc"], "named")


def test_several_assignees_keep_their_order_and_their_commas():
    page = header(current=("University of California, San Diego", "Anhui Asky Quantum Technology Co Ltd"),
                  original=("University of California, San Diego",))
    assert applicants(page) == (["University of California, San Diego", "Anhui Asky Quantum Technology Co Ltd"],
                                "named")


def test_the_original_assignee_stands_in_when_no_current_one_is_listed():
    assert applicants(header(original=("Climeworks AG",))) == (["Climeworks AG"], "named")


def test_an_inventor_owned_patent_names_its_inventors_not_a_company():
    page = header(inventors=("Edouard Petrounevitch",), current=("Individual",), original=("Individual",))
    assert applicants(page) == (["Edouard Petrounevitch"], "individual")


def test_assignees_in_citation_tables_are_never_taken_for_the_patents_own():
    table = '<table><tr><td itemprop="assigneeOriginal">Someone Else Corp</td></tr></table>'
    page = header(current=("Zunum Aero Inc",), original=("Zunum Aero Inc",), before=table)
    assert assignees_from_html(page) == {"current": ["Zunum Aero Inc"], "original": ["Zunum Aero Inc"],
                                         "inventors": ["Ada Lovelace"]}
    assert applicants(table) == ([], "none")


@pytest.mark.parametrize("url,expected", [
    ("https://patents.google.com/patent/US9422922B2/en", "https://patents.google.com/patent/US9422922B2/en"),
    ("https://patentscope.wipo.int/search/en/WO2011032127", "https://patents.google.com/patent/WO2011032127/en"),
    ("https://patents.justia.com/patent/20100224696", "https://patents.google.com/patent/US20100224696/en"),
    ("https://www.lens.org/lens/patent/123-456-789", None),
    ("https://patents.justia.com/assignee/azur-space-solar-power-gmbh", None),
])
def test_each_web_search_patent_maps_to_its_google_patents_page(url, expected):
    assert google_patents_url(url) == expected


class _NoRequests:
    def open(self, *args, **kwargs):
        raise AssertionError("no request may be sent")


@pytest.mark.allow_page_fetch
@pytest.mark.parametrize("url", ["http://127.0.0.1/patent/US1/en", "http://10.0.0.5/x", "file:///etc/passwd"])
def test_fetching_refuses_a_non_public_address_before_any_request(url):
    with patch.object(patent_applicants, "build_opener", return_value=_NoRequests()):
        assert patent_applicants.fetch_head(url) is None


def test_a_page_that_cannot_be_read_or_mapped_names_nobody():
    with patch.object(patent_applicants, "fetch_head", return_value=None):
        assert patent_applicants.patent_applicants("https://patents.google.com/patent/US1/en") == ([], "unreadable")
        assert patent_page_facts("https://patents.google.com/patent/US1/en") == ([], "unreadable", {})
    assert patent_applicants.patent_applicants("https://patents.justia.com/assignee/x") == ([], "no_number")
    assert patent_page_facts("https://patents.justia.com/assignee/x") == ([], "no_number", {})


_SUMMARY = ("Official patent database record for the claimed invention, verified against the national "
            "registry, with claims, priority date and classification codes.")


def patent(source_id: str, url: str) -> EvidenceSource:
    return EvidenceSource(source_id=source_id, title=f"Patent record {source_id}", url=url, publisher="Google",
                          accessed_date=date(2026, 10, 22), source_type="patent",
                          credibility_reason="Official patent office record.", evidence_summary=_SUMMARY)


def test_named_inventor_owned_failing_and_late_rows_each_get_their_due(monkeypatch):
    monkeypatch.setattr(source_pipeline, "_APPLICANT_DEADLINE_SECONDS", 0.2)
    release = threading.Event()
    rows = [patent("P1", "https://patents.google.com/patent/US1/en"),
            patent("P2", "https://patents.google.com/patent/US2/en"),
            patent("P3", "https://patents.google.com/patent/US3/en"),
            patent("P4", "https://patents.google.com/patent/US4/en"),
            patent("P5", "https://www.lens.org/lens/patent/123")]
    asked = []

    def lookup(url):
        asked.append(url)
        if url.endswith("US1/en"):
            return ["University of California, San Diego"], "named"
        if url.endswith("US2/en"):
            return ["Edouard Petrounevitch"], "individual"
        if url.endswith("US3/en"):
            raise OSError("reset")
        release.wait(5)
        return ["Too Late Inc"], "named"

    started = time.monotonic()
    try:
        names, [audit] = _name_patent_applicants(rows, lookup)   # a two-value lookup dates nothing
        assert time.monotonic() - started < 2
    finally:
        release.set()
    assert [r.published_date for r in rows] == [None] * 5
    assert "https://www.lens.org/lens/patent/123" not in asked
    assert names == {"P1": ["University of California, San Diego"], "P2": []}
    assert [r.publisher for r in rows] == ["University of California, San Diego",
                                           "Individual inventor: Edouard Petrounevitch", "Google", "Google", "Google"]
    assert rows[0].credibility_reason.endswith("not a legal title search.")
    assert audit.accepted_source_ids == ["P1", "P2"]
    assert audit.rejected_reasons == ["P3: page could not be read", "P4: page not read within 0.2 s"]


def _collect(**kwargs):
    return collect_source_collection(
        "Test commercialization topic", searcher=fake_search, crossref=MatchingCrossref(),
        openalex=_NullOpenAlex(), s2=_NullS2(), pubmed=_NullPubMed(), arxiv=_NullArXiv(),
        lens=_NullLens(), url_checker=lambda url: (True, ""), minimum_sources=3,
        maximum_sources=3, accessed_date=date(2026, 7, 2), **kwargs)


def test_the_collector_lists_applicants_as_competitors_with_their_commas_intact():
    owners = {"US10000001": (["University of California, San Diego"], "named"),
              "US10000002": (["Edouard Petrounevitch"], "individual")}

    def lookup(url):
        return next((value for number, value in owners.items() if number in url), ([], "none"))

    collection = _collect(patent_applicant_lookup=lookup)
    assert collection.patent_assignees == ["University of California, San Diego"]
    publishers = {str(s.url).rsplit("/", 1)[-1]: s.publisher for s in collection.patent_sources}
    assert publishers["US10000001"] == "University of California, San Diego"
    assert publishers["US10000002"] == "Individual inventor: Edouard Petrounevitch"
    assert publishers["US10000003"] == "Google"
    [row] = [r for r in collection.audit if r.query.startswith("[Patent-Applicants]")]
    assert row.result_count == 3 and len(row.accepted_source_ids) == 2
    assert "Patent-Applicants" not in run_lanes(collection.model_dump(mode="json"))


def test_by_default_the_collector_reads_the_patents_google_patents_page(monkeypatch):
    pages = {"https://patents.google.com/patent/US10000002/en": header(current=("Climeworks AG",))}
    monkeypatch.setattr("academic_agent.patent_applicants.fetch_head", pages.get)
    collection = _collect()
    assert collection.patent_assignees == ["Climeworks AG"]
    dated = {str(s.url).rsplit("/", 1)[-1]: s.published_date for s in collection.patent_sources}
    assert dated["US10000002"] == date(2012, 5, 15)   # from the page, whatever the row had
    [row] = [r for r in collection.audit if r.query.startswith("[Patent-Dates]")]
    assert row.accepted_source_ids == [s.source_id for s in collection.patent_sources
                                       if str(s.url).endswith("US10000002")]


# ---------------------------------------------------------------------------
# Dates: the same page, read once, dates the row
# ---------------------------------------------------------------------------

def test_the_header_dates_are_read_and_a_malformed_one_is_left_out():
    assert patent_dates(header()) == {"priority": date(2005, 4, 15), "filing": date(2006, 3, 8),
                                      "publication": date(2012, 5, 15)}
    assert patent_dates(header(publication=None)) == {"priority": date(2005, 4, 15), "filing": date(2006, 3, 8)}
    assert patent_dates(header(publication="2012-13-45")) == {"priority": date(2005, 4, 15), "filing": date(2006, 3, 8)}
    assert patent_dates("<html></html>") == {}


def test_the_first_statement_of_a_date_wins_over_a_cited_patents_later_one():
    page = header() + '<table><td><time itemprop="publicationDate" datetime="1999-01-01">x</time></td></table>'
    assert patent_dates(page)["publication"] == date(2012, 5, 15)


def test_page_facts_carry_names_status_and_dates_together():
    with patch.object(patent_applicants, "fetch_head", return_value=header(current=("Climeworks AG",))):
        assert patent_page_facts("https://patents.google.com/patent/US1/en") == (
            ["Climeworks AG"], "named",
            {"priority": date(2005, 4, 15), "filing": date(2006, 3, 8), "publication": date(2012, 5, 15)})


def test_the_page_date_fills_an_undated_row_and_replaces_a_number_derived_one():
    """The saved registries dated a web-search patent to 1 January of the year
    in its number; on 30 sampled pages none matched the real date and ten had
    the wrong year. The page wins, and a replacement is written down."""
    rows = [patent("P1", "https://patents.google.com/patent/US1/en"),
            patent("P2", "https://patents.google.com/patent/US2/en"),
            patent("P3", "https://patents.google.com/patent/US3/en"),
            patent("P4", "https://patents.google.com/patent/US4/en")]
    rows[1].published_date = date(2017, 1, 1)
    rows[2].published_date = date(2012, 5, 15)

    def lookup(url):
        if url.endswith("US4/en"):
            return [], "none", {"priority": date(2005, 4, 15)}       # a page without a publication date
        return ["Acme"], "named", {"publication": date(2012, 5, 15), "priority": date(2005, 4, 15)}

    names, audits = _name_patent_applicants(rows, lookup)
    assert [r.published_date for r in rows] == [date(2012, 5, 15), date(2012, 5, 15), date(2012, 5, 15), None]
    assert names == {"P1": ["Acme"], "P2": ["Acme"], "P3": ["Acme"]}
    assert [a.query.split("]")[0] for a in audits] == ["[Patent-Applicants", "[Patent-Dates"]
    dates = audits[1]
    assert dates.result_count == 4
    assert dates.accepted_source_ids == ["P1", "P2", "P3"]
    assert dates.rejected_reasons == ["P2: 2017-01-01 replaced by 2012-05-15 from the page",
                                      "P4: page states no publication date"]


def test_an_unreadable_page_dates_nothing_and_says_so_once():
    rows = [patent("P1", "https://patents.google.com/patent/US1/en")]
    rows[0].published_date = date(2017, 1, 1)
    names, audits = _name_patent_applicants(rows, lambda url: ([], "unreadable", {}))
    assert rows[0].published_date == date(2017, 1, 1)
    assert audits[0].rejected_reasons == ["P1: no applicant found (unreadable)"]
    assert audits[1].accepted_source_ids == [] and audits[1].rejected_reasons == []
