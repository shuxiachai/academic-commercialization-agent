"""The locator's link is shown only where the locator opens, and a refused visitor gets a page.

Seen on production on 2026-11-15, signed in as an ordinary account at
academic-agent.cc: the sidebar linked to "Saved-source locator", and the link
answered 403 with the raw body
`{"detail":"Saved-source receipt request could not be completed.","error_code":"origin_denied"}`.
The same path answered 200 at the Railway address.

Both halves were working as written. The feature accepts the one origin in
SOURCE_LOCATOR_PUBLIC_ORIGIN (docs/results-2026-09-23-source-locator-public-origin.md),
which on that deployment is the Railway address. The main page, though,
added the link whenever the feature was on, whatever address the page was
being read at; and the refusal was the API's JSON, shown to a person as text.

Nothing about what the locator accepts changes here: the same check decides
both, and a host it would refuse simply is not offered the link. The header
that picks the refusal's form (page or JSON) decides nothing else.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient
import pytest

from api import main
from api import saved_source_production as production
from api.saved_source_production_assets import refusal_page
from tests.test_saved_source_production import (
    SETTINGS, URL, app_for, boundary as boundary, consent, count, native as native, prepared as prepared,
)

PUBLIC = "https://locator.invalid"
PINNED = replace(SETTINGS, public_origin=PUBLIC)
RUN = "20260926T010101Z-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
LINK = 'id="source-locator-link"'
NAVIGATION = {"Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document",
              "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
PLAIN = (main._WEB_ROOT / "index.html").read_text(encoding="utf-8")


def _main_page(monkeypatch, runtime, host, path="/", **headers):
    monkeypatch.setattr(main, "_source_locator", runtime)
    with TestClient(main.app, base_url=f"http://{host}") as client:
        response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text[:200]
    return response


def test_the_link_is_offered_at_the_configured_address_and_nowhere_else(prepared, monkeypatch):
    runtime = prepared.build(PINNED)
    at_home = _main_page(monkeypatch, runtime, "locator.invalid")
    assert at_home.text.count(LINK) == 1 and 'href="/source-locator"' in at_home.text
    deep = _main_page(monkeypatch, runtime, "locator.invalid", f"/run/{RUN}")
    assert f'href="/source-locator#{RUN}"' in deep.text
    # The visitor's address, which the feature would refuse: no link to a page that answers 403.
    for host in ("academic-agent.cc", "www.locator.invalid", "locator.invalid:8443", "locator.invalid.evil.test"):
        elsewhere = _main_page(monkeypatch, runtime, host, f"/run/{RUN}")
        assert LINK not in elsewhere.text and "/source-locator" not in elsewhere.text, host
        assert elsewhere.text == PLAIN, "Otherwise the page is the page as it is without the feature"
    assert prepared.key_reads == prepared.requests == [] and count() == 0, "Deciding this does no locator work"


def test_no_header_but_host_can_make_the_link_appear(prepared, monkeypatch):
    """The feature never takes its public address from forwarding headers
    (AGENTS.md); what shows its link must not either."""
    runtime = prepared.build(PINNED)
    for forged in ({"X-Forwarded-Host": "locator.invalid"}, {"Forwarded": "host=locator.invalid;proto=https"},
                   {"X-Forwarded-Proto": "https", "X-Original-Host": "locator.invalid"},
                   {"Origin": PUBLIC}, {"Referer": PUBLIC + "/"}):
        page = _main_page(monkeypatch, runtime, "academic-agent.cc", **forged)
        assert LINK not in page.text, forged
    # At the right host, an Origin from somewhere else is refused by the feature too, so no link.
    assert LINK not in _main_page(monkeypatch, runtime, "locator.invalid", Origin="https://evil.invalid").text
    assert LINK in _main_page(monkeypatch, runtime, "locator.invalid", Origin=PUBLIC).text


@pytest.mark.parametrize("configured", ["not an origin", "https://a.invalid,https://b.invalid", "https://*.invalid"])
def test_a_configuration_the_feature_refuses_offers_no_link_anywhere(prepared, monkeypatch, configured):
    runtime = prepared.build(replace(SETTINGS, public_origin=configured))
    for host in ("locator.invalid", "a.invalid", "academic-agent.cc"):
        assert LINK not in _main_page(monkeypatch, runtime, host).text


def test_without_a_configured_address_the_link_is_as_it_was(prepared, monkeypatch):
    runtime = prepared.build(SETTINGS)      # no public origin: the feature compares against the request itself
    for host in ("testserver", "academic-agent.cc"):
        assert _main_page(monkeypatch, runtime, host).text.count(LINK) == 1
    # ...and with the feature off there is none.
    monkeypatch.setattr(main, "_source_locator", None)
    with TestClient(main.app) as client:
        assert LINK not in client.get("/").text


def test_a_person_refused_at_the_page_gets_a_page(prepared):
    runtime = prepared.build(PINNED)
    with TestClient(app_for(runtime), base_url="http://academic-agent.cc", follow_redirects=False) as client:
        for path in (production.PAGE_PATH, production.PAGE_PATH + "/"):
            refused = client.get(path, headers=NAVIGATION)
            assert refused.status_code == 403, path
            assert refused.headers["content-type"].startswith("text/html"), path
            assert refused.headers["x-error-code"] == "origin_denied"
            assert refused.headers["cache-control"] == "no-store"
            text = refused.text
            shown = text.split("</style>", 1)[1]
            assert "error_code" not in text and "{" not in shown and '"detail"' not in text, "No JSON is shown to a person"
            assert "The saved-source locator is not available at this address" in text
            assert "这个地址不提供“定位已保存来源”" in text
            assert '<a href="/">' in text, "A way back to the application"
            assert "academic-agent.cc" not in text and "locator.invalid" not in text, \
                "Neither the address asked for nor the configured one is written into the page"
        # A browser too old to say how it is fetching says what it accepts.
        older = client.get(production.PAGE_PATH, headers={"Accept": "text/html,application/xhtml+xml"})
        assert older.status_code == 403 and older.headers["content-type"].startswith("text/html")
    assert prepared.key_reads == prepared.requests == [] and count() == 0


def test_a_program_refused_still_gets_json(prepared):
    runtime = prepared.build(PINNED)
    with TestClient(app_for(runtime), base_url="http://academic-agent.cc", follow_redirects=False) as client:
        def refused_as_json(response):
            assert response.status_code == 403, response.text
            assert response.headers["content-type"].startswith("application/json")
            assert response.json()["error_code"] == "origin_denied"

        # The page's path, asked for by something that is not a person opening it.
        refused_as_json(client.get(production.PAGE_PATH))
        refused_as_json(client.get(production.PAGE_PATH, headers={"Accept": "application/json"}))
        refused_as_json(client.get(production.PAGE_PATH, headers={"Sec-Fetch-Mode": "cors", "Accept": "text/html"}))
        refused_as_json(client.get(production.PAGE_PATH, headers={"Sec-Fetch-Mode": "no-cors", "Sec-Fetch-Dest": "iframe",
                                                                  "Accept": "text/html"}))
        # Scripts and styles are never documents, whatever the request says of itself.
        refused_as_json(client.get("/source-locator-static/entry.js", headers=NAVIGATION))
        # The API, even dressed as a navigation.
        refused_as_json(client.post(URL, headers={**consent(), **NAVIGATION, "Content-Type": "application/json"},
                                    content=b"{}"))
        refused_as_json(client.get(production.GET_PATH, headers={**consent(), **NAVIGATION}))
    assert prepared.key_reads == prepared.requests == [] and count() == 0


def test_at_the_configured_address_nothing_changes(prepared):
    runtime = prepared.build(PINNED)
    with TestClient(app_for(runtime), base_url="http://locator.invalid", follow_redirects=False) as client:
        page = client.get(production.PAGE_PATH, headers=NAVIGATION)
        assert page.status_code == 200 and 'data-execution-allowed="true"' in page.text
        assert "x-error-code" not in page.headers
        slash = client.get(production.PAGE_PATH + "/", headers=NAVIGATION)
        assert slash.status_code == 307 and slash.headers["location"] == production.PAGE_PATH


def test_the_refusal_page_runs_nothing_and_loads_nothing():
    """It is served where the locator's own assets are refused, so it carries
    its few styles itself, and the policy names exactly those bytes."""
    import base64
    import hashlib
    import re

    response = refusal_page("origin_denied")
    text = response.body.decode("utf-8")
    assert "<script" not in text and "src=" not in text and 'rel="stylesheet"' not in text
    assert re.findall(r'href="([^"]*)"', text) == ["/"], "One link, to the application, and it is relative"
    style = re.search(r"<style>(.*?)</style>", text, re.S)[1]
    digest = base64.b64encode(hashlib.sha256(style.encode("utf-8")).digest()).decode("ascii")
    policy = response.headers["content-security-policy"]
    assert f"style-src 'sha256-{digest}'" in policy
    assert "default-src 'none'" in policy and "script-src" not in policy and "unsafe" not in policy
    assert "frame-ancestors 'none'" in policy and "base-uri 'none'" in policy
    for header, value in (("X-Frame-Options", "DENY"), ("X-Content-Type-Options", "nosniff"),
                          ("Referrer-Policy", "no-referrer"), ("Cache-Control", "no-store")):
        assert response.headers[header] == value
    # Any other refusal of the page says the feature is unavailable, not that the address is wrong.
    other = refusal_page("execution_unavailable")
    assert other.status_code == 503 and other.headers["x-error-code"] == "execution_unavailable"
    assert "unavailable at the moment" in other.body.decode("utf-8")
    assert "not available at this address" not in other.body.decode("utf-8")
    # A code this module does not know is not echoed.
    unknown = refusal_page("<script>alert(1)</script>")
    assert "<script" not in unknown.body.decode("utf-8") and "alert" not in unknown.headers["x-error-code"]
