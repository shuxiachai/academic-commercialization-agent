"""Tests for the non-academic API clients: Serper, Tavily, Lens.org, Crossref.

A web search client (Serper or Tavily) is the only mandatory key in the whole
project — every patent and market source flows through one of them — so
their retry and failure behaviour is worth pinning down precisely. Tavily
exists alongside Serper, not instead of it: some deployment hosts get a 403
from Serper on every request (it proxies Google, which blocks some
datacenter IP ranges) while Tavily, built for server-side callers, does not.

Companion to test_source_clients.py, which covers the four academic clients.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from academic_agent.source_clients import (
    CrossrefClient,
    LensPatentClient,
    SerperClient,
    SourceCollectionError,
    TavilyClient,
    default_web_search_client,
)


class _FakeResponse:
    """Minimal urllib response stub supporting 'with urlopen(...) as resp:'."""

    def __init__(self, data, raw: bytes | None = None):
        if raw is not None:
            self._body = raw
        elif isinstance(data, (dict, list)):
            self._body = json.dumps(data).encode("utf-8")
        else:
            self._body = str(data).encode("utf-8")
        self.status = 200

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def _http_error(code: int, body: bytes = b"") -> HTTPError:
    import io
    return HTTPError(url="http://x", code=code, msg=f"HTTP {code}",
                     hdrs=None, fp=io.BytesIO(body))


# ---------------------------------------------------------------------------
# SerperClient — construction
# ---------------------------------------------------------------------------

class SerperConstructionTests(unittest.TestCase):

    def test_explicit_key_accepted(self):
        self.assertEqual(SerperClient(api_key="abc").api_key, "abc")

    @patch.dict("os.environ", {"SERPER_API_KEY": "from-env"}, clear=False)
    def test_key_read_from_environment(self):
        self.assertEqual(SerperClient().api_key, "from-env")

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_key_raises_immediately(self):
        """Failing at construction beats failing mid-pipeline three agents in."""
        with self.assertRaises(SourceCollectionError) as ctx:
            SerperClient()
        self.assertIn("SERPER_API_KEY", str(ctx.exception))


# ---------------------------------------------------------------------------
# SerperClient — request shape
# ---------------------------------------------------------------------------

class SerperRequestTests(unittest.TestCase):

    def _client(self, **kw):
        return SerperClient(api_key="k", **kw)

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_payload_dict(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse({"organic": [{"title": "T"}]})
        self.assertEqual(self._client().search("q"), {"organic": [{"title": "T"}]})

    @patch("academic_agent.source_clients.urlopen")
    def test_query_and_count_in_body(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse({})
        self._client(n_results=7).search("solid state batteries")
        body = json.loads(mock_urlopen.call_args[0][0].data.decode())
        self.assertEqual(body["q"], "solid state batteries")
        self.assertEqual(body["num"], 7)

    @patch("academic_agent.source_clients.urlopen")
    def test_api_key_sent_as_header(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse({})
        self._client().search("q")
        headers = mock_urlopen.call_args[0][0].headers
        self.assertEqual(headers.get("X-api-key"), "k")

    @patch("academic_agent.source_clients.urlopen")
    def test_default_locale_omitted_from_body(self, mock_urlopen):
        """us/en is Serper's default — sending it adds noise for no gain."""
        mock_urlopen.return_value = _FakeResponse({})
        self._client().search("q")
        body = json.loads(mock_urlopen.call_args[0][0].data.decode())
        self.assertNotIn("gl", body)
        self.assertNotIn("hl", body)

    @patch("academic_agent.source_clients.urlopen")
    def test_non_default_locale_included(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse({})
        self._client(gl="jp", hl="ja").search("q")
        body = json.loads(mock_urlopen.call_args[0][0].data.decode())
        self.assertEqual(body["gl"], "jp")
        self.assertEqual(body["hl"], "ja")

    @patch("academic_agent.source_clients.urlopen")
    def test_non_object_response_rejected(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse(["not", "an", "object"])
        with self.assertRaises(SourceCollectionError):
            self._client().search("q")


# ---------------------------------------------------------------------------
# SerperClient — retry policy
# ---------------------------------------------------------------------------

@patch("academic_agent.source_clients.time.sleep")      # keep the suite fast
class SerperRetryTests(unittest.TestCase):

    def _client(self):
        return SerperClient(api_key="k")

    @patch("academic_agent.source_clients.urlopen")
    def test_transient_network_error_retried_then_succeeds(self, mock_urlopen, _sleep):
        mock_urlopen.side_effect = [URLError("flaky"), _FakeResponse({"organic": []})]
        self.assertEqual(self._client().search("q"), {"organic": []})
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("academic_agent.source_clients.urlopen")
    def test_gives_up_after_three_attempts(self, mock_urlopen, _sleep):
        mock_urlopen.side_effect = URLError("down")
        with self.assertRaises(SourceCollectionError) as ctx:
            self._client().search("q")
        self.assertEqual(mock_urlopen.call_count, 3)
        self.assertIn("3 attempts", str(ctx.exception))

    @patch("academic_agent.source_clients.urlopen")
    def test_rate_limit_is_retried(self, mock_urlopen, _sleep):
        mock_urlopen.side_effect = [_http_error(429), _FakeResponse({"organic": []})]
        self.assertEqual(self._client().search("q"), {"organic": []})

    @patch("academic_agent.source_clients.urlopen")
    def test_server_error_is_retried(self, mock_urlopen, _sleep):
        mock_urlopen.side_effect = [_http_error(503), _FakeResponse({"ok": 1})]
        self.assertEqual(self._client().search("q"), {"ok": 1})

    @patch("academic_agent.source_clients.urlopen")
    def test_auth_failure_is_not_retried(self, mock_urlopen, _sleep):
        """403 means the key is wrong; retrying burns quota and hides the cause.

        HTTPError subclasses URLError, so the ordering of the except clauses
        decides whether this works — get it backwards and every 4xx is treated
        as a transient blip.
        """
        mock_urlopen.side_effect = _http_error(403)
        with self.assertRaises(SourceCollectionError) as ctx:
            self._client().search("q")
        self.assertEqual(mock_urlopen.call_count, 1)
        self.assertIn("403", str(ctx.exception))

    @patch("academic_agent.source_clients.urlopen")
    def test_not_found_is_not_retried(self, mock_urlopen, _sleep):
        mock_urlopen.side_effect = _http_error(404)
        with self.assertRaises(SourceCollectionError):
            self._client().search("q")
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("academic_agent.source_clients.urlopen")
    def test_payment_required_is_not_retried(self, mock_urlopen, _sleep):
        """402 = credits exhausted. Retrying cannot help."""
        mock_urlopen.side_effect = _http_error(402)
        with self.assertRaises(SourceCollectionError):
            self._client().search("q")
        self.assertEqual(mock_urlopen.call_count, 1)


# ---------------------------------------------------------------------------
# TavilyClient — the fallback for hosts where Serper 403s outright
# ---------------------------------------------------------------------------

class TavilyConstructionTests(unittest.TestCase):

    def test_explicit_key_accepted(self):
        self.assertEqual(TavilyClient(api_key="abc").api_key, "abc")

    @patch.dict("os.environ", {"TAVILY_API_KEY": "from-env"}, clear=False)
    def test_key_read_from_environment(self):
        self.assertEqual(TavilyClient().api_key, "from-env")

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_key_raises_immediately(self):
        with self.assertRaises(SourceCollectionError) as ctx:
            TavilyClient()
        self.assertIn("TAVILY_API_KEY", str(ctx.exception))


class TavilyRequestTests(unittest.TestCase):

    def _client(self, **kw):
        return TavilyClient(api_key="k", **kw)

    @patch("academic_agent.source_clients.urlopen")
    def test_key_sent_as_bearer_token(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse({"results": []})
        self._client().search("q")
        headers = mock_urlopen.call_args[0][0].headers
        self.assertEqual(headers.get("Authorization"), "Bearer k")

    @patch("academic_agent.source_clients.urlopen")
    def test_plain_query_has_no_include_domains(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse({"results": []})
        self._client().search("solid state batteries")
        body = json.loads(mock_urlopen.call_args[0][0].data.decode())
        self.assertEqual(body["query"], "solid state batteries")
        self.assertNotIn("include_domains", body)

    @patch("academic_agent.source_clients.urlopen")
    def test_site_token_becomes_include_domains(self, mock_urlopen):
        """The exact query shape _queries() already builds for patent search —
        this client must adapt it, not require source_pipeline.py to change."""
        mock_urlopen.return_value = _FakeResponse({"results": []})
        self._client().search("solid-state batteries site:patents.google.com/patent")
        body = json.loads(mock_urlopen.call_args[0][0].data.decode())
        self.assertEqual(body["query"], "solid-state batteries")
        self.assertEqual(body["include_domains"], ["patents.google.com/patent"])

    @patch("academic_agent.source_clients.urlopen")
    def test_response_reshaped_to_organic(self, mock_urlopen):
        """Every caller in source_pipeline.py reads response['organic'], the
        Serper shape — Tavily's own {results: [{title,url,content}]} must
        come out the other side looking identical regardless of which client
        actually ran the search."""
        mock_urlopen.return_value = _FakeResponse({
            "results": [{"title": "T", "url": "https://x", "content": "snip"}]
        })
        result = self._client().search("q")
        self.assertEqual(
            result, {"organic": [{"title": "T", "link": "https://x", "snippet": "snip"}]}
        )

    @patch("academic_agent.source_clients.urlopen")
    def test_non_object_response_rejected(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse(["not", "an", "object"])
        with self.assertRaises(SourceCollectionError):
            self._client().search("q")


@patch("academic_agent.source_clients.time.sleep")
class TavilyRetryTests(unittest.TestCase):
    """Mirrors SerperRetryTests — same policy, same reasons, different API."""

    def _client(self):
        return TavilyClient(api_key="k")

    @patch("academic_agent.source_clients.urlopen")
    def test_transient_network_error_retried_then_succeeds(self, mock_urlopen, _sleep):
        mock_urlopen.side_effect = [URLError("flaky"), _FakeResponse({"results": []})]
        self.assertEqual(self._client().search("q"), {"organic": []})
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("academic_agent.source_clients.urlopen")
    def test_gives_up_after_three_attempts(self, mock_urlopen, _sleep):
        mock_urlopen.side_effect = URLError("down")
        with self.assertRaises(SourceCollectionError) as ctx:
            self._client().search("q")
        self.assertEqual(mock_urlopen.call_count, 3)
        self.assertIn("3 attempts", str(ctx.exception))

    @patch("academic_agent.source_clients.urlopen")
    def test_forbidden_is_not_retried(self, mock_urlopen, _sleep):
        """The exact failure this client exists to work around for Serper —
        must not be masked by a retry loop here either."""
        mock_urlopen.side_effect = _http_error(403)
        with self.assertRaises(SourceCollectionError) as ctx:
            self._client().search("q")
        self.assertEqual(mock_urlopen.call_count, 1)
        self.assertIn("403", str(ctx.exception))


class DefaultWebSearchClientTests(unittest.TestCase):
    """The auto-detection that lets a deployment switch providers by setting
    one env var, with no code change and no break for existing Serper-only
    setups."""

    @patch.dict("os.environ", {"TAVILY_API_KEY": "t", "SERPER_API_KEY": "s"}, clear=True)
    def test_tavily_preferred_when_both_are_set(self):
        self.assertIsInstance(default_web_search_client(), TavilyClient)

    @patch.dict("os.environ", {"SERPER_API_KEY": "s"}, clear=True)
    def test_serper_used_when_tavily_not_configured(self):
        """The original, still-default setup must keep working unchanged."""
        self.assertIsInstance(default_web_search_client(), SerperClient)

    @patch.dict("os.environ", {"TAVILY_API_KEY": "t"}, clear=True)
    def test_tavily_used_alone(self):
        self.assertIsInstance(default_web_search_client(), TavilyClient)


# ---------------------------------------------------------------------------
# LensPatentClient
# ---------------------------------------------------------------------------

class LensClientTests(unittest.TestCase):

    @patch.dict("os.environ", {}, clear=True)
    def test_absent_key_yields_no_results_without_network(self):
        """Lens is optional — no key must degrade quietly, not crash the run."""
        with patch("academic_agent.source_clients.urlopen") as mock_urlopen:
            self.assertEqual(LensPatentClient().search("batteries"), [])
            mock_urlopen.assert_not_called()

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_data_array(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse(
            {"total": 1, "data": [{"lens_id": "123-456"}]}
        )
        result = LensPatentClient(api_key="k").search("batteries")
        self.assertEqual(result, [{"lens_id": "123-456"}])

    @patch("academic_agent.source_clients.urlopen")
    def test_bearer_token_sent(self, mock_urlopen):
        # An empty result set warns by design (see the zero-results test), so
        # the warning is asserted rather than left to leak — the suite runs
        # with -W error::UserWarning to catch accidental live API calls.
        mock_urlopen.return_value = _FakeResponse({"data": []})
        with self.assertWarns(UserWarning):
            LensPatentClient(api_key="secret").search("q")
        headers = mock_urlopen.call_args[0][0].headers
        self.assertEqual(headers.get("Authorization"), "Bearer secret")

    @patch("academic_agent.source_clients.urlopen")
    def test_row_count_capped_at_fifty(self, mock_urlopen):
        """Lens rejects size > 50 outright."""
        mock_urlopen.return_value = _FakeResponse({"data": []})
        with self.assertWarns(UserWarning):
            LensPatentClient(api_key="k").search("q", rows=500)
        body = json.loads(mock_urlopen.call_args[0][0].data.decode())
        self.assertEqual(body["size"], 50)

    @patch("academic_agent.source_clients.urlopen")
    def test_auth_error_warns_and_returns_empty(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(401, b'{"message":"denied"}')
        with self.assertWarns(UserWarning) as w:
            self.assertEqual(LensPatentClient(api_key="bad").search("q"), [])
        self.assertIn("LENS_API_KEY", str(w.warning))

    @patch("academic_agent.source_clients.urlopen")
    def test_bad_request_warns_with_field_hint(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(400, b'{"message":"bad field"}')
        with self.assertWarns(UserWarning) as w:
            self.assertEqual(LensPatentClient(api_key="k").search("q"), [])
        self.assertIn("bad request", str(w.warning).lower())

    @patch("academic_agent.source_clients.urlopen")
    def test_zero_results_warns_for_diagnosis(self, mock_urlopen):
        """An empty result set is legal but usually means the query was wrong."""
        mock_urlopen.return_value = _FakeResponse({"total": 0, "data": []})
        with self.assertWarns(UserWarning):
            self.assertEqual(LensPatentClient(api_key="k").search("q"), [])

    @patch("academic_agent.source_clients.urlopen")
    def test_html_response_treated_as_no_results(self, mock_urlopen):
        """A redirect to a portal page must not be parsed as data."""
        mock_urlopen.return_value = _FakeResponse(None, raw=b"<html>portal</html>")
        self.assertEqual(LensPatentClient(api_key="k").search("q"), [])


# ---------------------------------------------------------------------------
# CrossrefClient
# ---------------------------------------------------------------------------

class CrossrefUserAgentTests(unittest.TestCase):

    @patch.dict("os.environ", {}, clear=True)
    def test_default_user_agent(self):
        self.assertNotIn("mailto", CrossrefClient().user_agent)

    @patch.dict("os.environ", {"CROSSREF_MAILTO": "me@example.com"}, clear=False)
    def test_mailto_appended_for_polite_pool(self):
        """Crossref routes requests carrying a contact address to a faster pool."""
        self.assertIn("mailto:me@example.com", CrossrefClient().user_agent)


@patch("academic_agent.source_clients.time.sleep")
class CrossrefLookupTests(unittest.TestCase):

    @patch("academic_agent.source_clients.urlopen")
    def test_lookup_returns_message_object(self, mock_urlopen, _sleep):
        mock_urlopen.return_value = _FakeResponse(
            {"status": "ok", "message": {"DOI": "10.1234/x", "title": ["T"]}}
        )
        result = CrossrefClient().lookup_doi("10.1234/x")
        self.assertEqual(result["DOI"], "10.1234/x")

    @patch("academic_agent.source_clients.urlopen")
    def test_doi_is_url_encoded(self, mock_urlopen, _sleep):
        """Slashes in a DOI must not be read as extra path segments."""
        mock_urlopen.return_value = _FakeResponse({"message": {}})
        CrossrefClient().lookup_doi("10.1234/a b/c")
        url = mock_urlopen.call_args[0][0].full_url
        self.assertNotIn(" ", url)
        self.assertIn("10.1234%2Fa%20b%2Fc", url)

    @patch("academic_agent.source_clients.urlopen")
    def test_unknown_doi_returns_none_without_retrying(self, mock_urlopen, _sleep):
        """404 is a definitive answer, not a transient failure."""
        mock_urlopen.side_effect = _http_error(404)
        self.assertIsNone(CrossrefClient().lookup_doi("10.0000/none"))
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("academic_agent.source_clients.urlopen")
    def test_rate_limit_retried_then_succeeds(self, mock_urlopen, _sleep):
        mock_urlopen.side_effect = [_http_error(429), _FakeResponse({"message": {"DOI": "d"}})]
        self.assertEqual(CrossrefClient().lookup_doi("10.1/x")["DOI"], "d")

    @patch("academic_agent.source_clients.urlopen")
    def test_permanent_error_not_retried(self, mock_urlopen, _sleep):
        mock_urlopen.side_effect = _http_error(403)
        client = CrossrefClient()
        self.assertIsNone(client.lookup_doi("10.1/x"))
        self.assertEqual(mock_urlopen.call_count, 1)
        self.assertIn("403", client.last_error)

    @patch("academic_agent.source_clients.urlopen")
    def test_network_failure_exhausts_retries(self, mock_urlopen, _sleep):
        mock_urlopen.side_effect = URLError("down")
        client = CrossrefClient(retries=2)
        self.assertIsNone(client.lookup_doi("10.1/x"))
        self.assertEqual(mock_urlopen.call_count, 3)
        self.assertIn("failed", client.last_error)

    @patch("academic_agent.source_clients.urlopen")
    def test_non_object_payload_reported(self, mock_urlopen, _sleep):
        mock_urlopen.return_value = _FakeResponse(["array"])
        client = CrossrefClient()
        self.assertIsNone(client.lookup_doi("10.1/x"))
        self.assertIn("non-object", client.last_error)

    @patch("academic_agent.source_clients.urlopen")
    def test_missing_message_key_reported(self, mock_urlopen, _sleep):
        mock_urlopen.return_value = _FakeResponse({"status": "ok"})
        client = CrossrefClient()
        self.assertIsNone(client.lookup_doi("10.1/x"))
        self.assertIn("no message", client.last_error)

    @patch("academic_agent.source_clients.urlopen")
    def test_last_error_cleared_on_success(self, mock_urlopen, _sleep):
        """A stale error would make a later successful lookup look failed."""
        client = CrossrefClient()
        mock_urlopen.side_effect = _http_error(403)
        client.lookup_doi("10.1/bad")
        self.assertIsNotNone(client.last_error)

        mock_urlopen.side_effect = None
        mock_urlopen.return_value = _FakeResponse({"message": {"DOI": "ok"}})
        client.lookup_doi("10.1/good")
        self.assertIsNone(client.last_error)


@patch("academic_agent.source_clients.time.sleep")
class CrossrefSearchTitleTests(unittest.TestCase):

    @patch("academic_agent.source_clients.urlopen")
    def test_returns_item_list(self, mock_urlopen, _sleep):
        mock_urlopen.return_value = _FakeResponse(
            {"message": {"items": [{"DOI": "10.1/a"}, {"DOI": "10.1/b"}]}}
        )
        self.assertEqual(len(CrossrefClient().search_title("perovskite")), 2)

    @patch("academic_agent.source_clients.urlopen")
    def test_non_dict_items_filtered_out(self, mock_urlopen, _sleep):
        mock_urlopen.return_value = _FakeResponse(
            {"message": {"items": [{"DOI": "10.1/a"}, "junk", None]}}
        )
        self.assertEqual(CrossrefClient().search_title("x"), [{"DOI": "10.1/a"}])

    @patch("academic_agent.source_clients.urlopen")
    def test_missing_items_returns_empty(self, mock_urlopen, _sleep):
        mock_urlopen.return_value = _FakeResponse({"message": {}})
        self.assertEqual(CrossrefClient().search_title("x"), [])

    @patch("academic_agent.source_clients.urlopen")
    def test_failed_request_returns_empty(self, mock_urlopen, _sleep):
        mock_urlopen.side_effect = _http_error(500)
        self.assertEqual(CrossrefClient().search_title("x"), [])

    @patch("academic_agent.source_clients.urlopen")
    def test_title_sent_as_query_parameter(self, mock_urlopen, _sleep):
        mock_urlopen.return_value = _FakeResponse({"message": {"items": []}})
        CrossrefClient().search_title("solid state batteries")
        url = mock_urlopen.call_args[0][0].full_url
        self.assertIn("query.title=solid+state+batteries", url)


if __name__ == "__main__":
    unittest.main()
