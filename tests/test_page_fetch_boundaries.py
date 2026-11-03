"""The two bounded page fetchers at their edges: content types, redirects and hops.

page_dates.fetch_html and patent_applicants.fetch_head share one shape: read at
most MAX_BYTES of an HTML page, follow at most five redirects, and refuse any
hop that is not a public HTTP(S) address. These tests drive that shape with a
fake opener; no request leaves the process.
"""

from __future__ import annotations

import ipaddress
import socket
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from academic_agent import page_dates, patent_applicants


class _Response:
    def __init__(self, body: bytes = b"<html></html>", content_type: str = "text/html; charset=utf-8"):
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.body = body
        self.reads: list[int] = []

    def read(self, n: int = -1) -> bytes:
        self.reads.append(n)
        return self.body[:n] if n is not None and n > 0 else self.body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _redirect(code: int, location: str | None):
    headers = Message()
    if location is not None:
        headers["Location"] = location
    return HTTPError("https://news.sample-press.net/x", code, "redirect", headers, None)


class _Opener:
    """Routes a URL to a response or an exception, and records every request."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.requested: list[str] = []

    def open(self, request, timeout=None):
        url = request.full_url
        self.requested.append(url)
        item = self.routes.get(url)
        if item is None:
            raise URLError("unrouted")
        if isinstance(item, BaseException):
            raise item
        return item


def _resolve(host, *args, **kwargs):
    """Offline stand-in for DNS: the test host is public, IP literals are themselves,
    anything else does not resolve. The public-address check then runs for real."""
    try:
        address = str(ipaddress.ip_address(host))
    except ValueError:
        if host != "news.sample-press.net":
            raise socket.gaierror(f"no such host in tests: {host}") from None
        address = "93.184.216.34"
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 0))]


@pytest.fixture
def opener():
    installed: list = [patch("socket.getaddrinfo", side_effect=_resolve)]
    installed[0].start()

    def install(module, routes):
        fake = _Opener(routes)
        patcher = patch.object(module, "build_opener", return_value=fake)
        patcher.start()
        installed.append(patcher)
        return fake

    yield install
    for patcher in installed:
        patcher.stop()


@pytest.mark.allow_page_fetch
@pytest.mark.parametrize("module,fetch", [(page_dates, "fetch_html"), (patent_applicants, "fetch_head")])
def test_only_html_is_read_and_only_up_to_the_byte_ceiling(module, fetch, opener):
    page = _Response(b"<html>" + b"x" * (module.MAX_BYTES * 2), "text/html; charset=utf-8")
    fake = opener(module, {"https://news.sample-press.net/page": page, "https://news.sample-press.net/pdf": _Response(b"%PDF-", "application/pdf")})
    text = getattr(module, fetch)("https://news.sample-press.net/page")
    assert text is not None and len(text) == module.MAX_BYTES
    assert page.reads == [module.MAX_BYTES]
    assert getattr(module, fetch)("https://news.sample-press.net/pdf") is None
    assert fake.requested == ["https://news.sample-press.net/page", "https://news.sample-press.net/pdf"]


@pytest.mark.allow_page_fetch
@pytest.mark.parametrize("module,fetch", [(page_dates, "fetch_html"), (patent_applicants, "fetch_head")])
def test_a_relative_redirect_is_followed_to_the_resolved_public_address(module, fetch, opener):
    fake = opener(module, {"https://news.sample-press.net/old": _redirect(301, "/new"),
                           "https://news.sample-press.net/new": _Response(b"<html>moved</html>")})
    assert getattr(module, fetch)("https://news.sample-press.net/old") == "<html>moved</html>"
    assert fake.requested == ["https://news.sample-press.net/old", "https://news.sample-press.net/new"]


@pytest.mark.allow_page_fetch
@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
def test_every_redirect_status_is_followed_and_the_others_are_not(code, opener):
    fake = opener(page_dates, {"https://news.sample-press.net/old": _redirect(code, "https://news.sample-press.net/new"),
                               "https://news.sample-press.net/new": _Response(b"<html>ok</html>")})
    assert page_dates.fetch_html("https://news.sample-press.net/old") == "<html>ok</html>"
    assert fake.requested[-1] == "https://news.sample-press.net/new"


@pytest.mark.allow_page_fetch
def test_a_redirect_without_a_location_and_an_error_status_both_end_the_fetch(opener):
    fake = opener(page_dates, {"https://news.sample-press.net/a": _redirect(302, None), "https://news.sample-press.net/b": _redirect(404, "/x"),
                               "https://news.sample-press.net/c": URLError("refused")})
    for url in ("https://news.sample-press.net/a", "https://news.sample-press.net/b", "https://news.sample-press.net/c"):
        assert page_dates.fetch_html(url) is None
    assert fake.requested == ["https://news.sample-press.net/a", "https://news.sample-press.net/b", "https://news.sample-press.net/c"]


@pytest.mark.allow_page_fetch
def test_the_fifth_hop_is_the_last_one_tried(opener):
    fake = opener(page_dates, {"https://news.sample-press.net/a": _redirect(301, "/b"), "https://news.sample-press.net/b": _redirect(301, "/a")})
    assert page_dates.fetch_html("https://news.sample-press.net/a") is None
    assert len(fake.requested) == 5


@pytest.mark.allow_page_fetch
@pytest.mark.parametrize("target", ["http://127.0.0.1/admin", "http://10.0.0.5/x", "file:///etc/passwd",
                                    "http://user:pw@news.sample-press.net/x"])
def test_a_redirect_to_a_non_public_address_is_refused_before_it_is_requested(target, opener):
    fake = opener(page_dates, {"https://news.sample-press.net/a": _redirect(302, target)})
    assert page_dates.fetch_html("https://news.sample-press.net/a") is None
    assert fake.requested == ["https://news.sample-press.net/a"]


@pytest.mark.allow_page_fetch
def test_the_declared_charset_decodes_the_page_and_an_unknown_one_yields_nothing(opener):
    opener(page_dates, {"https://news.sample-press.net/latin": _Response("caf\xe9".encode("latin-1"), "text/html; charset=iso-8859-1"),
                        "https://news.sample-press.net/bogus": _Response(b"<html>", "text/html; charset=x-no-such-charset")})
    assert page_dates.fetch_html("https://news.sample-press.net/latin") == "caf\xe9"
    assert page_dates.fetch_html("https://news.sample-press.net/bogus") is None
