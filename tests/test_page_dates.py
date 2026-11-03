"""Publication dates only from a page's explicit metadata, never invented."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from academic_agent import page_dates
from academic_agent.page_dates import date_from_html, date_from_url, should_date

TODAY = date(2026, 10, 22)


def html(head: str = "", body: str = "") -> str:
    return f"<html><head>{head}</head><body>{body}</body></html>"


@pytest.mark.parametrize("source_type,url,expected", [
    ("reputable_news", "https://finance.yahoo.com/news/egenesis-scoops-191m.html", True),
    ("company_disclosure", "https://www.egenesisbio.com/news/first-transplant", True),
    ("government", "https://www.energy.gov/eere/geothermal/egs", True),
    ("market_report", "https://www.grandviewresearch.com/industry-analysis/x-market", False),
    ("other", "https://en.wikipedia.org/wiki/Hyperloop", False),
    ("company_disclosure", "https://www.virtualincision.com/", False),
    ("company_disclosure", "https://www.virtualincision.com", False),
    ("reputable_news", None, False),
])
def test_which_pages_may_date_their_source(source_type, url, expected):
    assert should_date(source_type, url) is expected


def test_json_ld_date_published_is_read_even_inside_a_graph():
    page = html('<script type="application/ld+json">{"@graph": [{"@type": "WebSite"}, '
                '{"@type": "NewsArticle", "dateModified": "2025-01-02", "datePublished": "2024-09-05T14:53:27Z"}]}'
                '</script>')
    assert date_from_html(page, "https://e.test/a", TODAY) == (date(2024, 9, 5), "json_ld")


def test_meta_and_itemprop_dates_are_read():
    meta = html('<meta property="article:published_time" content="2023-12-21T22:38:04+00:00">')
    assert date_from_html(meta, "https://e.test/a", TODAY) == (date(2023, 12, 21), "meta")
    item = html(body='<time itemprop="datePublished" datetime="2022-07-02">July 2</time>')
    assert date_from_html(item, "https://e.test/a", TODAY) == (date(2022, 7, 2), "itemprop")


def test_modification_dates_and_prose_are_not_publication_dates():
    page = html('<meta property="article:modified_time" content="2026-01-01">'
                '<script type="application/ld+json">{"dateModified": "2026-01-01"}</script>',
                "<p>Published on 12 March 2024</p>")
    assert date_from_html(page, "https://e.test/a", TODAY) == (None, "none")


def test_a_full_url_date_is_used_only_when_the_page_states_none():
    assert date_from_url("https://e.test/news/2025/03/14/story", TODAY) == (date(2025, 3, 14), "url_path")
    assert date_from_url("https://e.test/news/2025/03/story", TODAY) == (None, "none")  # no day: not a date
    page = html('<meta name="pubdate" content="2025-03-15">')
    assert date_from_html(page, "https://e.test/news/2025/03/14/story", TODAY) == (date(2025, 3, 15), "meta")


@pytest.mark.parametrize("value", ["2027-01-01", "1985-05-05", "2024-13-01", "2024-02-30", "March 5, 2024", "", "n.d."])
def test_future_ancient_impossible_and_unformatted_values_are_rejected(value):
    page = html(f'<script type="application/ld+json">{{"datePublished": "{value}"}}</script>')
    assert date_from_html(page, "https://e.test/a", TODAY) == (None, "none")


def test_malformed_markup_and_json_yield_no_date_not_an_error():
    page = html('<script type="application/ld+json">{not json</script><meta property="article:published_time">')
    assert date_from_html(page, "https://e.test/a", TODAY) == (None, "none")


def test_an_unreadable_page_falls_back_to_the_url_only():
    with patch.object(page_dates, "fetch_html", return_value=None):
        assert page_dates.page_publication_date("https://e.test/2024/08/09/x", TODAY) == (date(2024, 8, 9), "url_path")
        assert page_dates.page_publication_date("https://e.test/x", TODAY) == (None, "none")


class _NoRequests:
    def open(self, *args, **kwargs):
        raise AssertionError("no request may be sent")


@pytest.mark.allow_page_fetch
@pytest.mark.parametrize("url", ["http://127.0.0.1/admin", "http://10.0.0.5/x", "file:///etc/passwd",
                                 "http://user:pw@example.com/x"])
def test_fetching_refuses_a_non_public_address_before_any_request(url):
    with patch.object(page_dates, "build_opener", return_value=_NoRequests()):
        assert page_dates.fetch_html(url) is None


# ---------------------------------------------------------------------------
# Boundaries: the day window, the ISO shape, and what counts as a path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("2026-10-22", date(2026, 10, 22)),                # the access day itself is allowed
    ("2026-10-23", None),                              # one day later is not
    ("1990-01-01", date(1990, 1, 1)),                  # the earliest allowed day
    ("1989-12-31", None),                              # one day earlier is not
    ("2026-02-30", None),                              # well formed, impossible
    ("2026-1-5", None),                                # partial fields are not ISO
    (" 2026-10-22", date(2026, 10, 22)),               # leading whitespace is tolerated
    ("2026-10-22T23:59:59+10:00", date(2026, 10, 22)),  # the time part is ignored
    ("2026-10-22extra", None),                         # trailing junk is not
    (["2026-10-22"], None),                            # a JSON-LD list is not a date
    (20261022, None),
    (None, None),
])
def test_the_date_window_and_the_iso_shape_are_exact(value, expected):
    assert page_dates._parse(value, TODAY) == expected


@pytest.mark.parametrize("url,expected", [
    ("https://e.test/2026/10/22", (date(2026, 10, 22), "url_path")),
    ("https://e.test/2026/10/22/#section", (date(2026, 10, 22), "url_path")),
    ("https://e.test/2026/13/01/a", (None, "none")),       # no thirteenth month
    ("https://e.test/2026/10/22x", (None, "none")),         # the day must end its segment
    ("https://e.test/a/1989/01/01/", (None, "none")),       # before the window
    ("https://e.test/?p=/2026/10/22/", (None, "none")),     # the query is not the path
])
def test_only_a_full_date_in_the_path_itself_counts(url, expected):
    assert date_from_url(url, TODAY) == expected


@pytest.mark.parametrize("source_type,url,expected", [
    ("other", "https://e.test/?q=1", False),               # a query string is not a page path
    ("other", "https://e.test//", False),
    ("other", "https://de.wikipedia.org/wiki/X", False),   # every Wikipedia subdomain
    ("other", "https://notwikipedia.org/wiki/X", True),    # but not a look-alike host
    (None, None, False),
])
def test_path_and_host_edge_cases_for_dating(source_type, url, expected):
    assert should_date(source_type, url) is expected


def test_an_impossible_json_ld_date_does_not_hide_a_later_valid_one():
    page = html('<script type="application/ld+json">{"@graph": [{"datePublished": "2030-01-01"}, '
                '{"datePublished": "2026-05-05"}]}</script>'
                '<meta property="article:published_time" content="2026-01-01">')
    assert date_from_html(page, "https://e.test/a", TODAY) == (date(2026, 5, 5), "json_ld")


def test_a_top_level_json_ld_array_is_walked_and_a_list_valued_date_is_not_a_date():
    array = html('<script type="application/ld+json">[{"datePublished": "2026-03-03"}]</script>')
    assert date_from_html(array, "https://e.test/a", TODAY) == (date(2026, 3, 3), "json_ld")
    listed = html('<script type="application/ld+json">{"datePublished": ["2026-03-03"]}</script>')
    assert date_from_html(listed, "https://e.test/a", TODAY) == (None, "none")


def test_meta_attribute_names_are_matched_without_regard_to_case():
    page = html('<META PROPERTY="Article:Published_Time" CONTENT="2026-04-04">')
    assert date_from_html(page, "https://e.test/a", TODAY) == (date(2026, 4, 4), "meta")
