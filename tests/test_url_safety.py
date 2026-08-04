"""Tests for the URL safety layer (SSRF defence).

Why this matters here: the pipeline fetches URLs that came from an LLM or from
a search engine. Neither is a trusted source, so a URL that resolves inside the
network — a cloud metadata endpoint, an internal admin page — must never be
requested. The checks in evidence.py are what stand between those inputs and
the network, and they had no test coverage at all.

Every test stubs DNS and HTTP; nothing here touches the network.
"""

from __future__ import annotations

import socket
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from academic_agent.evidence import (
    _BLOCKED_HOST_SUFFIXES,
    _PLACEHOLDER_HOSTS,
    _host_is_public,
    _validate_public_url,
    check_public_url,
)


def _addrinfo(*ips: str):
    """Build a getaddrinfo() return value for the given addresses."""
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 0))
            for ip in ips]


def _resolves_to(*ips: str):
    """Patch DNS so any hostname resolves to the given addresses."""
    return patch("academic_agent.evidence.socket.getaddrinfo",
                 return_value=_addrinfo(*ips))


class _Response:
    def __init__(self, status: int = 200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def _redirect(code: int, location: str | None) -> HTTPError:
    headers = {"Location": location} if location else {}
    return HTTPError(url="http://x", code=code, msg="redirect",
                     hdrs=headers, fp=None)


# ---------------------------------------------------------------------------
# Scheme and credential checks — no DNS involved
# ---------------------------------------------------------------------------

class UrlSchemeTests(unittest.TestCase):

    def test_https_scheme_allowed(self):
        with _resolves_to("93.184.216.34"):
            ok, _ = _validate_public_url("https://nature.com/article")
        self.assertTrue(ok)

    def test_http_scheme_allowed(self):
        with _resolves_to("93.184.216.34"):
            ok, _ = _validate_public_url("http://nature.com/article")
        self.assertTrue(ok)

    def test_file_scheme_rejected(self):
        """file:// would read the local disk."""
        ok, why = _validate_public_url("file:///etc/passwd")
        self.assertFalse(ok)
        self.assertIn("HTTP", why)

    def test_ftp_scheme_rejected(self):
        self.assertFalse(_validate_public_url("ftp://files.example.org/x")[0])

    def test_gopher_scheme_rejected(self):
        """gopher:// is a classic SSRF pivot for speaking arbitrary protocols."""
        self.assertFalse(_validate_public_url("gopher://127.0.0.1:6379/_INFO")[0])

    def test_data_scheme_rejected(self):
        self.assertFalse(_validate_public_url("data:text/html,<script>")[0])

    def test_missing_hostname_rejected(self):
        ok, why = _validate_public_url("http:///just-a-path")
        self.assertFalse(ok)
        self.assertIn("hostname", why)

    def test_embedded_credentials_rejected(self):
        """user:pass@ can be used to disguise the real host from a reader."""
        ok, why = _validate_public_url("http://user:pass@nature.com/")
        self.assertFalse(ok)
        self.assertIn("credentials", why)

    def test_username_only_also_rejected(self):
        self.assertFalse(_validate_public_url("http://admin@nature.com/")[0])


# ---------------------------------------------------------------------------
# Host resolution — the core SSRF check
# ---------------------------------------------------------------------------

class HostResolutionTests(unittest.TestCase):

    def test_public_address_allowed(self):
        with _resolves_to("93.184.216.34"):
            self.assertTrue(_host_is_public("nature.com")[0])

    def test_loopback_rejected(self):
        with _resolves_to("127.0.0.1"):
            ok, why = _host_is_public("sneaky.example.org")
            self.assertFalse(ok)
            self.assertIn("non-public", why)

    def test_private_ranges_rejected(self):
        for ip in ("10.0.0.1", "172.16.0.1", "192.168.1.1"):
            with self.subTest(ip=ip), _resolves_to(ip):
                self.assertFalse(_host_is_public("internal.example.org")[0])

    def test_cloud_metadata_endpoint_rejected(self):
        """169.254.169.254 serves instance credentials on every major cloud."""
        with _resolves_to("169.254.169.254"):
            self.assertFalse(_host_is_public("metadata.example.org")[0])

    def test_ipv6_loopback_rejected(self):
        with _resolves_to("::1"):
            self.assertFalse(_host_is_public("v6.example.org")[0])

    def test_ipv6_unique_local_rejected(self):
        with _resolves_to("fd00::1"):
            self.assertFalse(_host_is_public("v6private.example.org")[0])

    def test_any_private_address_disqualifies_the_host(self):
        """A host answering with both a public and a private A record is unsafe.

        This is the DNS-rebinding shape: one record passes the check, the other
        is what a later connection might actually use.
        """
        with _resolves_to("93.184.216.34", "127.0.0.1"):
            self.assertFalse(_host_is_public("rebind.example.org")[0])

    def test_dns_failure_rejected(self):
        with patch("academic_agent.evidence.socket.getaddrinfo",
                   side_effect=socket.gaierror("no such host")):
            ok, why = _host_is_public("nonexistent.example.org")
            self.assertFalse(ok)
            self.assertIn("DNS", why)

    def test_empty_resolution_rejected(self):
        with patch("academic_agent.evidence.socket.getaddrinfo", return_value=[]):
            self.assertFalse(_host_is_public("void.example.org")[0])

    def test_placeholder_hosts_rejected_without_dns(self):
        """LLMs invent example.com constantly; it must never be fetched."""
        for host in sorted(_PLACEHOLDER_HOSTS):
            with self.subTest(host=host):
                with patch("academic_agent.evidence.socket.getaddrinfo") as dns:
                    ok, why = _host_is_public(host)
                    self.assertFalse(ok)
                    self.assertIn("placeholder", why)
                    dns.assert_not_called()

    def test_blocked_suffixes_rejected(self):
        for suffix in _BLOCKED_HOST_SUFFIXES:
            with self.subTest(suffix=suffix):
                self.assertFalse(_host_is_public(f"service{suffix}")[0])

    def test_trailing_dot_normalised(self):
        """'localhost.' is the same host as 'localhost' to a resolver."""
        with patch("academic_agent.evidence.socket.getaddrinfo") as dns:
            self.assertFalse(_host_is_public("localhost.")[0])
            dns.assert_not_called()

    def test_case_insensitive(self):
        with patch("academic_agent.evidence.socket.getaddrinfo") as dns:
            self.assertFalse(_host_is_public("LOCALHOST")[0])
            dns.assert_not_called()


# ---------------------------------------------------------------------------
# check_public_url — reachability with redirect handling
# ---------------------------------------------------------------------------

class CheckPublicUrlTests(unittest.TestCase):

    def setUp(self):
        # The function is lru_cached; stale entries would leak between tests.
        check_public_url.cache_clear()

    def tearDown(self):
        check_public_url.cache_clear()

    def _opener(self, *side_effects):
        opener = MagicMock()
        opener.open.side_effect = side_effects
        return patch("academic_agent.evidence.build_opener", return_value=opener), opener

    def test_reachable_url_accepted(self):
        patcher, _ = self._opener(_Response(200))
        with patcher, _resolves_to("93.184.216.34"):
            self.assertTrue(check_public_url("https://nature.com/a")[0])

    def test_unauthorised_counts_as_reachable(self):
        """401/403 means the resource exists but is paywalled — a valid citation."""
        for code in (401, 403):
            with self.subTest(code=code):
                check_public_url.cache_clear()
                patcher, _ = self._opener(HTTPError("u", code, "no", {}, None))
                with patcher, _resolves_to("93.184.216.34"):
                    self.assertTrue(check_public_url(f"https://nature.com/{code}")[0])

    def test_not_found_rejected(self):
        patcher, _ = self._opener(HTTPError("u", 404, "gone", {}, None))
        with patcher, _resolves_to("93.184.216.34"):
            ok, why = check_public_url("https://nature.com/missing")
        self.assertFalse(ok)
        self.assertIn("404", why)

    def test_network_error_rejected(self):
        patcher, _ = self._opener(URLError("unreachable"))
        with patcher, _resolves_to("93.184.216.34"):
            self.assertFalse(check_public_url("https://nature.com/x")[0])

    def test_redirect_to_public_host_followed(self):
        patcher, opener = self._opener(
            _redirect(301, "https://www.nature.com/final"),
            _Response(200),
        )
        with patcher, _resolves_to("93.184.216.34"):
            self.assertTrue(check_public_url("https://nature.com/old")[0])
        self.assertEqual(opener.open.call_count, 2)

    def test_redirect_into_private_network_blocked(self):
        """The whole reason redirects are handled manually.

        A public URL that 302s to a metadata endpoint must be stopped at the
        second hop — following it automatically is the classic SSRF hole.
        """
        patcher, opener = self._opener(
            _redirect(302, "http://169.254.169.254/latest/meta-data/"),
        )
        dns = patch(
            "academic_agent.evidence.socket.getaddrinfo",
            side_effect=lambda host, *a, **k: _addrinfo(
                "169.254.169.254" if "169.254" in host else "93.184.216.34"
            ),
        )
        with patcher, dns:
            ok, why = check_public_url("https://nature.com/redirects-inward")

        self.assertFalse(ok)
        self.assertIn("non-public", why)
        # It must not have issued a request to the internal address.
        self.assertEqual(opener.open.call_count, 1)

    def test_redirect_to_loopback_blocked(self):
        patcher, _ = self._opener(_redirect(307, "http://127.0.0.1:8080/admin"))
        dns = patch(
            "academic_agent.evidence.socket.getaddrinfo",
            side_effect=lambda host, *a, **k: _addrinfo(
                "127.0.0.1" if host.startswith("127.") else "93.184.216.34"
            ),
        )
        with patcher, dns:
            self.assertFalse(check_public_url("https://nature.com/x")[0])

    def test_redirect_without_location_rejected(self):
        patcher, _ = self._opener(_redirect(302, None))
        with patcher, _resolves_to("93.184.216.34"):
            ok, why = check_public_url("https://nature.com/x")
        self.assertFalse(ok)
        self.assertIn("without Location", why)

    def test_redirect_loop_bounded(self):
        """A self-referencing redirect must terminate, not spin."""
        patcher, opener = self._opener(*[
            _redirect(302, "https://nature.com/loop") for _ in range(10)
        ])
        with patcher, _resolves_to("93.184.216.34"):
            ok, why = check_public_url("https://nature.com/loop")
        self.assertFalse(ok)
        self.assertIn("too many redirects", why)
        self.assertLessEqual(opener.open.call_count, 5)

    def test_method_not_allowed_falls_back_to_get(self):
        """Some publishers reject HEAD but serve GET fine."""
        patcher, opener = self._opener(
            HTTPError("u", 405, "no HEAD", {}, None),
            _Response(200),
        )
        with patcher, _resolves_to("93.184.216.34"):
            self.assertTrue(check_public_url("https://nature.com/nohead")[0])
        self.assertEqual(opener.open.call_args_list[-1][0][0].get_method(), "GET")

    def test_non_ascii_url_rejected(self):
        with _resolves_to("93.184.216.34"):
            ok, why = check_public_url("https://nature.com/文章")
        self.assertFalse(ok)
        self.assertIn("non-ASCII", why)

    def test_url_with_spaces_rejected(self):
        with _resolves_to("93.184.216.34"):
            ok, why = check_public_url("https://nature.com/a b")
        self.assertFalse(ok)
        self.assertIn("spaces", why)

    def test_private_url_never_requested(self):
        """Validation happens before the socket is opened, not after."""
        patcher, opener = self._opener(_Response(200))
        with patcher, _resolves_to("10.0.0.1"):
            self.assertFalse(check_public_url("http://internal.example.org/")[0])
        opener.open.assert_not_called()

    def test_result_is_cached(self):
        patcher, opener = self._opener(_Response(200))
        with patcher, _resolves_to("93.184.216.34"):
            check_public_url("https://nature.com/cached")
            check_public_url("https://nature.com/cached")
        self.assertEqual(opener.open.call_count, 1)


if __name__ == "__main__":
    unittest.main()
