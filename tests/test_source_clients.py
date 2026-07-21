"""Tests for the API client classes in source_clients.py."""

from __future__ import annotations

import json
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from academic_agent.source_clients import (
    ArxivClient,
    OpenAlexClient,
    PubMedClient,
    SemanticScholarClient,
)


class _FakeResponse:
    """Minimal urllib response stub compatible with 'with urlopen(...) as resp:'."""

    def __init__(self, data):
        if isinstance(data, (dict, list)):
            self._body = json.dumps(data).encode("utf-8")
        elif isinstance(data, str):
            self._body = data.encode("utf-8")
        else:
            self._body = bytes(data)
        self.status = 200

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


# ---------------------------------------------------------------------------
# SemanticScholarClient
# ---------------------------------------------------------------------------

class SemanticScholarGetAbstractTests(unittest.TestCase):
    def _client(self):
        return SemanticScholarClient(timeout=5, retries=0)

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_abstract_text_on_success(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse({"abstract": "Cell therapy advances."})
        self.assertEqual(self._client().get_abstract_by_doi("10.1234/test"), "Cell therapy advances.")

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_empty_string_on_url_error(self, mock_urlopen):
        mock_urlopen.side_effect = URLError("timeout")
        self.assertEqual(self._client().get_abstract_by_doi("10.1234/x"), "")

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_empty_string_on_timeout(self, mock_urlopen):
        mock_urlopen.side_effect = TimeoutError()
        self.assertEqual(self._client().get_abstract_by_doi("10.1234/x"), "")

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_empty_string_when_abstract_key_absent(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse({})
        self.assertEqual(self._client().get_abstract_by_doi("10.1234/x"), "")

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_empty_string_on_json_decode_error(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse("not json at all {{{{")
        self.assertEqual(self._client().get_abstract_by_doi("10.1234/x"), "")


class SemanticScholarSearchTests(unittest.TestCase):
    def _client(self, retries=0):
        return SemanticScholarClient(timeout=5, retries=retries)

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_data_list_on_success(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse({"data": [{"title": "Paper A"}]})
        self.assertEqual(self._client().search("CRISPR", rows=5), [{"title": "Paper A"}])

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_empty_list_on_non_429_http_error(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            url="", code=503, msg="Unavailable", hdrs=None, fp=None
        )
        self.assertEqual(self._client().search("topic"), [])

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_empty_list_on_url_error(self, mock_urlopen):
        mock_urlopen.side_effect = URLError("network down")
        self.assertEqual(self._client().search("topic"), [])

    @patch("academic_agent.source_clients.time.sleep")
    @patch("academic_agent.source_clients.urlopen")
    def test_retries_on_429_then_succeeds(self, mock_urlopen, mock_sleep):
        rate_err = HTTPError(
            url="", code=429, msg="Too Many Requests", hdrs=None, fp=None
        )
        ok_resp = _FakeResponse({"data": [{"title": "Paper B"}]})
        mock_urlopen.side_effect = [rate_err, ok_resp]
        result = SemanticScholarClient(timeout=5, retries=1).search("topic")
        self.assertEqual(result, [{"title": "Paper B"}])
        self.assertTrue(mock_sleep.called)

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_empty_list_when_data_key_absent(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse({})
        self.assertEqual(self._client().search("topic"), [])


# ---------------------------------------------------------------------------
# PubMedClient — _parse_article and _parse_xml
# ---------------------------------------------------------------------------

_VALID_ARTICLE_XML = """\
<PubmedArticle>
  <MedlineCitation>
    <PMID>12345678</PMID>
    <Article>
      <ArticleTitle>CRISPR gene therapy advances</ArticleTitle>
      <Abstract><AbstractText>Key advances in CRISPR editing.</AbstractText></Abstract>
      <AuthorList>
        <Author><LastName>Smith</LastName><ForeName>John</ForeName></Author>
        <Author><LastName>Jones</LastName><ForeName>Alice</ForeName></Author>
      </AuthorList>
      <ArticleDate DateType="Electronic">
        <Year>2023</Year><Month>6</Month><Day>1</Day>
      </ArticleDate>
      <ELocationID EIdType="doi">10.1234/crispr.2023</ELocationID>
    </Article>
  </MedlineCitation>
</PubmedArticle>"""


class PubMedParseArticleTests(unittest.TestCase):
    def _client(self):
        return PubMedClient(timeout=5, retries=0)

    def _parse(self, xml_str: str):
        return self._client()._parse_article(ET.fromstring(xml_str))

    def test_valid_article_returns_dict_with_title(self):
        result = self._parse(_VALID_ARTICLE_XML)
        self.assertIsNotNone(result)
        self.assertIn("CRISPR", result["title"])

    def test_valid_article_returns_doi(self):
        result = self._parse(_VALID_ARTICLE_XML)
        self.assertIsNotNone(result)
        self.assertIn("10.1234/crispr", result.get("doi", ""))

    def test_no_medline_citation_returns_none(self):
        self.assertIsNone(self._parse("<PubmedArticle></PubmedArticle>"))

    def test_no_article_element_returns_none(self):
        xml = "<PubmedArticle><MedlineCitation></MedlineCitation></PubmedArticle>"
        self.assertIsNone(self._parse(xml))

    def test_no_title_returns_none(self):
        xml = """\
<PubmedArticle>
  <MedlineCitation><Article></Article></MedlineCitation>
</PubmedArticle>"""
        self.assertIsNone(self._parse(xml))


class PubMedParseXmlTests(unittest.TestCase):
    def _client(self):
        return PubMedClient(timeout=5, retries=0)

    def test_valid_article_set_returns_one_result(self):
        xml = f"<PubmedArticleSet>{_VALID_ARTICLE_XML}</PubmedArticleSet>"
        results = self._client()._parse_xml(xml.encode("utf-8"))
        self.assertEqual(len(results), 1)
        self.assertIn("CRISPR", results[0]["title"])

    def test_malformed_article_skipped_valid_one_kept(self):
        xml = f"<PubmedArticleSet><PubmedArticle></PubmedArticle>{_VALID_ARTICLE_XML}</PubmedArticleSet>"
        results = self._client()._parse_xml(xml.encode("utf-8"))
        self.assertEqual(len(results), 1)

    def test_malformed_xml_bytes_returns_empty_list(self):
        self.assertEqual(self._client()._parse_xml(b"<not valid xml"), [])

    def test_empty_set_returns_empty_list(self):
        self.assertEqual(self._client()._parse_xml(b"<PubmedArticleSet/>"), [])


# ---------------------------------------------------------------------------
# OpenAlexClient
# ---------------------------------------------------------------------------

class OpenAlexFetchCitationTests(unittest.TestCase):
    def _client(self):
        return OpenAlexClient(timeout=5, retries=0)

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_citation_count_as_int(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse({"cited_by_count": 42})
        self.assertEqual(self._client().fetch_citation_by_doi("10.1/x"), 42)

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_zero_when_count_is_none(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse({"cited_by_count": None})
        self.assertEqual(self._client().fetch_citation_by_doi("10.1/x"), 0)

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_none_on_url_error(self, mock_urlopen):
        mock_urlopen.side_effect = URLError("network down")
        self.assertIsNone(self._client().fetch_citation_by_doi("10.1/x"))

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_none_on_timeout(self, mock_urlopen):
        mock_urlopen.side_effect = TimeoutError()
        self.assertIsNone(self._client().fetch_citation_by_doi("10.1/x"))

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_none_on_json_error(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse("bad json {{")
        self.assertIsNone(self._client().fetch_citation_by_doi("10.1/x"))


class OpenAlexFetchReferencedWorksTests(unittest.TestCase):
    def _client(self):
        return OpenAlexClient(timeout=5, retries=0)

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_ids_truncated_to_top_n(self, mock_urlopen):
        ids = [f"W{i}" for i in range(50)]
        mock_urlopen.return_value = _FakeResponse({"referenced_works": ids})
        result = self._client().fetch_referenced_works("10.1/x", top_n=10)
        self.assertEqual(len(result), 10)
        self.assertEqual(result[0], "W0")

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_empty_list_on_network_error(self, mock_urlopen):
        mock_urlopen.side_effect = URLError("down")
        self.assertEqual(self._client().fetch_referenced_works("10.1/x"), [])

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_empty_list_when_key_absent(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse({})
        self.assertEqual(self._client().fetch_referenced_works("10.1/x"), [])

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_full_list_when_under_top_n(self, mock_urlopen):
        ids = ["W1", "W2", "W3"]
        mock_urlopen.return_value = _FakeResponse({"referenced_works": ids})
        result = self._client().fetch_referenced_works("10.1/x", top_n=25)
        self.assertEqual(result, ids)


# ---------------------------------------------------------------------------
# ArxivClient
# ---------------------------------------------------------------------------

_ATOM_NS  = "http://www.w3.org/2005/Atom"
_ARXIV_NS = "http://arxiv.org/schemas/atom"

_VALID_ARXIV_FEED = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="{_ATOM_NS}" xmlns:arxiv="{_ARXIV_NS}">
  <entry>
    <title>Attention Is All You Need</title>
    <summary>Transformer architecture for sequence modeling.</summary>
    <id>http://arxiv.org/abs/1706.03762v5</id>
    <published>2017-06-12T00:00:00Z</published>
    <author><name>Vaswani, Ashish</name></author>
    <author><name>Shazeer, Noam</name></author>
    <arxiv:doi xmlns:arxiv="{_ARXIV_NS}">10.48550/arXiv.1706.03762</arxiv:doi>
  </entry>
</feed>"""


class ArxivParseFeedTests(unittest.TestCase):
    def _client(self):
        return ArxivClient(timeout=5, retries=0)

    def test_parses_valid_entry_title(self):
        results = self._client()._parse_feed(_VALID_ARXIV_FEED.encode("utf-8"))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Attention Is All You Need")

    def test_parses_arxiv_url_from_id(self):
        results = self._client()._parse_feed(_VALID_ARXIV_FEED.encode("utf-8"))
        self.assertIn("1706.03762", results[0]["arxiv_url"])

    def test_parses_multiple_authors_joined(self):
        results = self._client()._parse_feed(_VALID_ARXIV_FEED.encode("utf-8"))
        self.assertIn("Vaswani", results[0]["authors"])

    def test_malformed_xml_bytes_returns_empty_list(self):
        self.assertEqual(self._client()._parse_feed(b"<broken"), [])

    def test_empty_feed_returns_empty_list(self):
        feed = f'<feed xmlns="{_ATOM_NS}"></feed>'
        self.assertEqual(self._client()._parse_feed(feed.encode()), [])

    def test_entry_missing_title_is_skipped(self):
        feed = f"""\
<feed xmlns="{_ATOM_NS}">
  <entry>
    <summary>No title here.</summary>
    <id>http://arxiv.org/abs/0000.00000</id>
    <published>2020-01-01T00:00:00Z</published>
  </entry>
</feed>"""
        self.assertEqual(self._client()._parse_feed(feed.encode()), [])

    def test_entry_with_parsing_error_skipped_valid_one_kept(self):
        bad_entry = f"<entry xmlns='{_ATOM_NS}'><title>OK paper</title><id>http://arxiv.org/abs/1234.56789</id><published>2022-01-01T00:00:00Z</published></entry>"
        feed = f'<feed xmlns="{_ATOM_NS}">{bad_entry}</feed>'
        results = self._client()._parse_feed(feed.encode())
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "OK paper")
