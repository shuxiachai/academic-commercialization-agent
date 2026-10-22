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
