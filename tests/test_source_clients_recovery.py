"""Failure and retry paths in the free-API clients.

This layer talks to seven external services and is where every production
surprise in this project has come from: Serper retrying an auth failure until
the quota was gone, Lens returning an empty list for an expired key so the
audit read "0 patents" as a finding, Google Patents serving "No information is
available for this page." into a field with a 60-character floor.

All three were found in production. The equivalent paths in the PubMed and
OpenAlex clients — 204 uncovered lines, almost all of them error handling —
had never been exercised. These cover the distinctions that matter there:
which failures are worth retrying, which are not, and what a caller receives
when the service is unavailable versus when it genuinely has nothing.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from academic_agent.source_clients import OpenAlexClient, PubMedClient


class _FakeResponse:
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


def _http_error(code: int) -> HTTPError:
    return HTTPError("https://example.test", code, "err", {}, None)


class PubMedTransportTests(unittest.TestCase):
    """_get is the single HTTP path under every PubMed call, so what it
    retries decides how a rate limit and an outage each behave."""

    def _client(self, retries: int = 2) -> PubMedClient:
        return PubMedClient(timeout=5, retries=retries)

    @patch("academic_agent.source_clients.time.sleep")
    @patch("academic_agent.source_clients.urlopen")
    def test_a_rate_limit_is_retried(self, urlopen, sleep):
        """429 means "later", not "no". Treating it as a hard failure discards
        a query the service was willing to answer."""
        urlopen.side_effect = [_http_error(429), _FakeResponse({"ok": 1})]
        self.assertTrue(self._client()._get("https://example.test"))
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called()

    @patch("academic_agent.source_clients.time.sleep")
    @patch("academic_agent.source_clients.urlopen")
    def test_a_client_error_is_not_retried(self, urlopen, _sleep):
        """The Serper lesson: retrying a rejection the server will repeat just
        spends quota faster. 400 and 403 will not change on attempt two."""
        for code in (400, 403, 404):
            with self.subTest(code=code):
                urlopen.reset_mock()
                urlopen.side_effect = _http_error(code)
                self.assertEqual(self._client()._get("https://example.test"), b"")
                self.assertEqual(urlopen.call_count, 1)

    @patch("academic_agent.source_clients.time.sleep")
    @patch("academic_agent.source_clients.urlopen")
    def test_a_network_error_is_retried_then_gives_up(self, urlopen, _sleep):
        urlopen.side_effect = URLError("connection reset")
        self.assertEqual(self._client(retries=2)._get("https://example.test"), b"")
        self.assertEqual(urlopen.call_count, 3)

    @patch("academic_agent.source_clients.time.sleep")
    @patch("academic_agent.source_clients.urlopen")
    def test_an_outage_returns_empty_rather_than_raising(self, urlopen, _sleep):
        """PubMed is one of several academic sources. One being down must
        degrade that source, not abort the run — see difficulty 33."""
        urlopen.side_effect = OSError("dns failure")
        self.assertEqual(self._client()._get("https://example.test"), b"")


class PubMedSearchTests(unittest.TestCase):

    def _client(self) -> PubMedClient:
        return PubMedClient(timeout=5, retries=0)

    @patch("academic_agent.source_clients.PubMedClient._get")
    def test_no_ids_means_no_second_request(self, get):
        """A search that matched nothing must not go on to fetch nothing —
        the efetch call would be a wasted round trip against a rate limit
        shared with every other query."""
        get.return_value = json.dumps({"esearchresult": {"idlist": []}}).encode()
        self.assertEqual(self._client().search("nothing matches this"), [])
        self.assertEqual(get.call_count, 1)

    @patch("academic_agent.source_clients.PubMedClient._get")
    def test_malformed_json_yields_no_results(self, get):
        """An HTML error page where JSON was expected is a normal thing for a
        public API to return under load."""
        get.return_value = b"<html>service unavailable</html>"
        self.assertEqual(self._client().search("topic"), [])

    @patch("academic_agent.source_clients.PubMedClient._get")
    def test_an_empty_response_yields_no_results(self, get):
        get.return_value = b""
        self.assertEqual(self._client().search("topic"), [])

    @patch("academic_agent.source_clients.PubMedClient._get")
    def test_ids_are_fetched_when_the_search_matched(self, get):
        get.side_effect = [
            json.dumps({"esearchresult": {"idlist": ["111", "222"]}}).encode(),
            b"<PubmedArticleSet></PubmedArticleSet>",
        ]
        self._client().search("cell therapy")
        self.assertEqual(get.call_count, 2)
        # %2C, not a literal comma: urlencode escapes it, and the encoded form
        # is what reaches the service.
        self.assertIn("id=111%2C222", get.call_args_list[1].args[0])


class MeshTermTests(unittest.TestCase):
    """MeSH expansion is one of the four recall strategies. When it silently
    returns nothing the pipeline still works and simply finds less, which is
    the kind of degradation that never gets reported."""

    def _client(self) -> PubMedClient:
        return PubMedClient(timeout=5, retries=0)

    @patch("academic_agent.source_clients.PubMedClient._get")
    def test_terms_are_read_from_the_translation_stack(self, get):
        get.return_value = json.dumps({"esearchresult": {"translationstack": [
            {"term": '"neoplasms"[MeSH Terms]', "field": "MeSH Terms"},
            {"term": "unrelated", "field": "All Fields"},
        ]}}).encode()
        self.assertEqual(self._client().get_mesh_terms("cancer"), ["neoplasms"])

    @patch("academic_agent.source_clients.PubMedClient._get")
    def test_the_mesh_suffix_and_quotes_are_stripped(self, get):
        """Left in, the term is sent back to PubMed as a literal string with
        brackets and matches nothing."""
        get.return_value = json.dumps({"esearchresult": {"translationstack": [
            {"term": '"gene editing"[MeSH Terms]', "field": "MeSH Terms"},
        ]}}).encode()
        self.assertEqual(self._client().get_mesh_terms("crispr"), ["gene editing"])

    @patch("academic_agent.source_clients.PubMedClient._get")
    def test_duplicates_are_removed_and_the_cap_is_respected(self, get):
        get.return_value = json.dumps({"esearchresult": {"translationstack": [
            {"term": "alpha[MeSH Terms]", "field": "MeSH Terms"},
            {"term": "alpha[MeSH Terms]", "field": "MeSH Terms"},
            {"term": "beta[MeSH Terms]", "field": "MeSH Terms"},
            {"term": "gamma[MeSH Terms]", "field": "MeSH Terms"},
        ]}}).encode()
        self.assertEqual(self._client().get_mesh_terms("x", max_terms=2), ["alpha", "beta"])

    @patch("academic_agent.source_clients.PubMedClient._get")
    def test_it_falls_back_to_esummary_when_the_stack_has_no_terms(self, get):
        get.side_effect = [
            json.dumps({"esearchresult": {"translationstack": [], "idlist": ["68009369"]}}).encode(),
            json.dumps({"result": {"68009369": {"ds_name": "Neoplasms"}}}).encode(),
        ]
        self.assertEqual(self._client().get_mesh_terms("cancer"), ["Neoplasms"])
        self.assertEqual(get.call_count, 2)

    @patch("academic_agent.source_clients.PubMedClient._get")
    def test_no_ids_and_no_stack_means_no_fallback_request(self, get):
        get.return_value = json.dumps(
            {"esearchresult": {"translationstack": [], "idlist": []}}).encode()
        self.assertEqual(self._client().get_mesh_terms("x"), [])
        self.assertEqual(get.call_count, 1)

    @patch("academic_agent.source_clients.PubMedClient._get")
    def test_a_failed_fallback_yields_no_terms(self, get):
        get.side_effect = [
            json.dumps({"esearchresult": {"translationstack": [], "idlist": ["1"]}}).encode(),
            b"",
        ]
        self.assertEqual(self._client().get_mesh_terms("x"), [])

    @patch("academic_agent.source_clients.PubMedClient._get")
    def test_malformed_json_yields_no_terms(self, get):
        get.return_value = b"not json"
        self.assertEqual(self._client().get_mesh_terms("x"), [])


class OpenAlexRecallTests(unittest.TestCase):
    """The three recall strategies layered on top of plain search: citation
    snowballing, topic clusters, and a recency pass."""

    def _client(self) -> OpenAlexClient:
        return OpenAlexClient(timeout=5, retries=1)

    @patch("academic_agent.source_clients.urlopen")
    def test_no_ids_makes_no_request_at_all(self, urlopen):
        """Snowballing from a paper with no references must not issue a query
        whose filter is empty — OpenAlex answers that with the whole corpus."""
        self.assertEqual(self._client().fetch_works_by_ids([]), [])
        urlopen.assert_not_called()

    @patch("academic_agent.source_clients.urlopen")
    def test_the_id_list_is_capped(self, urlopen):
        """URLs have a length limit; an uncapped filter fails the request
        outright rather than returning fewer results."""
        urlopen.return_value = _FakeResponse({"results": []})
        self._client().fetch_works_by_ids([f"W{i}" for i in range(120)])
        url = urlopen.call_args.args[0].full_url
        self.assertEqual(url.count("%7C") + url.count("|"), 49)

    @patch("academic_agent.source_clients.time.sleep")
    @patch("academic_agent.source_clients.urlopen")
    def test_each_recall_call_retries_a_rate_limit(self, urlopen, _sleep):
        for name, call in (
            ("fetch_works_by_ids", lambda c: c.fetch_works_by_ids(["W1"])),
            ("search_by_topic", lambda c: c.search_by_topic("T123")),
            ("search_recent", lambda c: c.search_recent("solid state batteries")),
        ):
            with self.subTest(method=name):
                urlopen.reset_mock()
                urlopen.side_effect = [_http_error(429), _FakeResponse({"results": [{"id": "W1"}]})]
                self.assertEqual(len(call(self._client())), 1)
                self.assertEqual(urlopen.call_count, 2)

    @patch("academic_agent.source_clients.time.sleep")
    @patch("academic_agent.source_clients.urlopen")
    def test_each_recall_call_gives_up_on_a_client_error(self, urlopen, _sleep):
        for name, call in (
            ("fetch_works_by_ids", lambda c: c.fetch_works_by_ids(["W1"])),
            ("search_by_topic", lambda c: c.search_by_topic("T123")),
            ("search_recent", lambda c: c.search_recent("topic")),
        ):
            with self.subTest(method=name):
                urlopen.reset_mock()
                urlopen.side_effect = _http_error(403)
                self.assertEqual(call(self._client()), [])
                self.assertEqual(urlopen.call_count, 1)

    @patch("academic_agent.source_clients.time.sleep")
    @patch("academic_agent.source_clients.urlopen")
    def test_a_truncated_body_is_survived(self, urlopen, _sleep):
        """A connection dropped mid-response yields valid bytes that are not
        valid JSON. Caught alongside the network errors, not left to raise."""
        urlopen.return_value = _FakeResponse('{"results": [')
        self.assertEqual(self._client().search_recent("topic"), [])

    @patch("academic_agent.source_clients.urlopen")
    def test_recency_filter_uses_the_year_before_the_cutoff(self, urlopen):
        """The filter is `>since_year - 1` because OpenAlex's `>` is strict:
        writing `>2023` would silently drop everything published in 2023."""
        urlopen.return_value = _FakeResponse({"results": []})
        self._client().search_recent("topic", since_year=2023)
        self.assertIn("publication_year%3A%3E2022", urlopen.call_args.args[0].full_url)

    @patch("academic_agent.source_clients.urlopen")
    def test_a_missing_results_key_is_treated_as_no_results(self, urlopen):
        urlopen.return_value = _FakeResponse({"meta": {"count": 0}})
        self.assertEqual(self._client().search_by_topic("T1"), [])
