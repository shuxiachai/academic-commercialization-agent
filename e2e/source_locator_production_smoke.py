"""Main-app Chromium -> native interception -> durable recovery, never paid.

The browser loses an acknowledgement only AFTER the real main route has
executed. A second page recovers that receipt with execution closed. Synthetic
keys and a transport/socket allowlist keep this separate from any live grant.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlsplit

import httpx
from playwright.sync_api import expect, sync_playwright

from e2e.saved_source_receipt_smoke import BrowserFixture, CODE, QUESTION, _fixture
from e2e.saved_source_smoke import EXACT_TEXT, RUN_ID, TITLE, _block_external_connections, _serve

ROOT = Path(__file__).resolve().parents[1]
STORAGE = "source-locator:v1"
POST = f"/api/runs/{RUN_ID}/source-locator"
GET = "/api/source-locator/receipts"
FAKE_KEY = "sk-production-locator-offline-only"
PUBLIC_ORIGIN = "https://locator.invalid"


def _assert_wire(wire):
    """Inspect decoded metadata, including the JSON catalog inside a message.

    Searching raw JSON for multiline Unicode text misses its escaped spelling.
    Exact synthetic metadata forbids extra private fields or excerpts hidden
    inside a title, and decoded string traversal also covers other messages.
    """
    assert set(wire) == {"messages", "tools", "tool_choice", "model", "stream", "enable_thinking",
                         "parallel_tool_calls", "temperature", "max_tokens"}
    assert wire["model"] == "qwen3.5-plus"
    messages = wire["messages"]
    assert len(messages) == 3
    assert all(set(message) == {"role", "content"} for message in messages)
    assert [message["role"] for message in messages] == ["system", "user", "user"]
    assert messages[1]["content"] == QUESTION
    assert json.loads(messages[2]["content"]) == {
        "method_id": "report_evidence_catalog_v1", "total_count": 4, "returned_count": 4,
        "omitted_count": 0, "coverage": "complete", "title_truncation_count": 0,
        "entries": [{"source_id": f"A{index}", "title": TITLE if index == 1 else f"Fictional source {index}",
                     "title_truncated": False} for index in range(1, 5)],
    }, "Only the exact synthetic ID/title catalog may leave the saved report"

    def strings(value):
        if isinstance(value, dict):
            for key, child in value.items():
                yield key
                yield from strings(child)
        elif isinstance(value, list):
            for child in value:
                yield from strings(child)
        elif isinstance(value, str):
            yield value
    assert all(EXACT_TEXT not in text and CODE not in text for text in strings(wire))


def _wire_negative_controls(wire):
    """The same observer must reject escaped excerpt leaks, not just bad syntax."""
    for location in ("catalog_field", "catalog_title", "system_message"):
        bad = deepcopy(wire)
        if location == "system_message":
            bad["messages"][0]["content"] += EXACT_TEXT
        else:
            catalog = json.loads(bad["messages"][2]["content"])
            catalog["entries"][0]["evidence_summary" if location == "catalog_field" else "title"] = EXACT_TEXT
            bad["messages"][2]["content"] = json.dumps(catalog, ensure_ascii=True)
        # Re-encode/decode exactly as HTTP does: this is the escaped form that
        # made the previous raw-substring negative assertion ineffective.
        bad = json.loads(json.dumps(bad, ensure_ascii=True))
        try:
            _assert_wire(bad)
        except AssertionError:
            continue
        raise AssertionError(f"Wire privacy observer admitted {location}")


class ProductionBrowser(BrowserFixture):
    """Retain existing persistence/network guards but admit only new routes."""

    def same_origin(self, url):
        return (url.scheme, url.netloc) == ("http", urlsplit(self.base).netloc) and not url.query

    def fetch(self, route):
        return route.fetch(max_redirects=0)

    def asset(self, route):
        route.continue_()

    def route(self, route):
        request = route.request
        url = urlsplit(request.url)
        same = self.same_origin(url)
        assets = {"/source-locator", "/source-locator/", *(f"/source-locator-static/{name}" for name in (
            "entry.js", "receipt.js", "result.js", "accounting.js", "app.css", "receipt.css"))}
        if same and request.method == "GET" and url.path in assets:
            self.asset(route)
            return
        post = request.method == "POST" and url.path == POST
        get = request.method == "GET" and url.path == GET
        if not same or not (post or get):
            self.faults.append(f"Unexpected main locator request: {request.method} {url.path}")
            route.abort()
            return
        assert not {"cookie", "authorization"}.intersection(request.headers)
        assert request.headers["x-access-code"] == CODE
        if post:
            assert request.headers["x-source-locator-consent"] == "question-catalog-v1"
            assert request.post_data_json == {"question": QUESTION}
            assert json.loads(self.page.evaluate("key => sessionStorage.getItem(key)", STORAGE)) == {
                "version": 1, "receipt_key": request.headers["idempotency-key"],
            }
        else:
            assert "x-source-locator-consent" not in request.headers
            assert request.post_data is None
        upstream = self.fetch(route)
        payload = upstream.json()
        (self.posts if post else self.gets).append((request, upstream.status, payload))
        if post and self.mode == "lost_post":
            assert upstream.status == 200
            assert payload["receipt"]["result"]["saved_text"]["text"] == EXACT_TEXT
            assert payload["accounting"]["usage"]["total_tokens"] == 120
            route.abort()
        else:
            route.fulfill(response=upstream)


class ProxyProductionBrowser(ProductionBrowser):
    """Real browser HTTPS origin, intercepted into an HTTP-only loopback upstream.

    Every permitted browser request is fetched from the fixed loopback server;
    no request to locator.invalid reaches DNS/network. Preserve Chromium's real
    Origin bytes and bind only the upstream Host. This models TLS termination,
    not TLS certificate verification or Railway's particular forwarded headers.
    """

    def __init__(self, browser, base, faults):
        assert urlsplit(base).scheme == "http" and urlsplit(base).hostname == "127.0.0.1"
        self.upstream = base
        self.slash_checks = 0
        super().__init__(browser, PUBLIC_ORIGIN + "/source-locator", faults)
        assert self.page.url == PUBLIC_ORIGIN + "/source-locator"
        # Chromium/Playwright only intercepts the first hop of this synthetic
        # redirect chain. Observe the actual 307 without following it into DNS;
        # the canonical document and all paid/recovery requests still traverse
        # the real HTTP upstream. This is not a TLS/redirect-following audit.
        result = self.page.evaluate("async () => (await fetch('/source-locator/', {redirect: 'manual'})).type")
        assert result == "opaqueredirect" and self.slash_checks == 1

    def same_origin(self, url):
        return (url.scheme, url.netloc) == ("https", "locator.invalid") and not url.query

    def fetch(self, route):
        request = route.request
        headers = request.all_headers()
        assert not any(name == "forwarded" or name.startswith("x-forwarded-") for name in headers)
        if request.method == "POST":
            assert headers["origin"] == PUBLIC_ORIGIN, "Observe the browser's Origin; do not synthesize it"
        headers["host"] = "locator.invalid"
        return route.fetch(url=self.upstream + urlsplit(request.url).path, headers=headers, max_redirects=0)

    def asset(self, route):
        upstream = self.fetch(route)
        if urlsplit(route.request.url).path == "/source-locator/":
            assert upstream.status == 307 and upstream.headers["location"] == "/source-locator"
            self.slash_checks += 1
        else:
            assert upstream.status == 200
        route.fulfill(response=upstream)


def main(*, proxy=False):
    assert "api.main" not in sys.modules, "Run this isolated smoke as a fresh module"
    faults, native, ingress = [], [], []
    # Explicitly retain only process/tool infrastructure, never ambient provider
    # credentials. dotenv is disabled before any production dependency import.
    environment = {key: os.environ[key] for key in (
        "PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
    ) if key in os.environ}
    environment.update({
        "PYTHON_DOTENV_DISABLED": "1", "CREWAI_TELEMETRY_DISABLED": "true", "OTEL_SDK_DISABLED": "true",
        "AGENT_OBSERVABILITY_ENABLED": "false", "SOURCE_LOCATOR_ENABLED": "true",
        "SOURCE_LOCATOR_EXECUTION_ENABLED": "true", "SOURCE_LOCATOR_DAILY_REQUEST_CAP": "2",
        "SOURCE_LOCATOR_DAILY_USD_CAP": "0.03", "SOURCE_LOCATOR_MIN_INTERVAL_SECONDS": "1",
        "SOURCE_LOCATOR_PUBLIC_ORIGIN": PUBLIC_ORIGIN if proxy else "",
        "DASHSCOPE_API_KEY": FAKE_KEY, "LLM_PROVIDER": "qwen", "QWEN_MODEL": "qwen3.5-plus",
        "TAVILY_API_KEY": "offline-readiness-no-search",
    })

    def dispatch(request):
        native.append(request)
        assert str(request.url) == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer " + FAKE_KEY
        wire = json.loads(request.content)
        _assert_wire(wire)
        _wire_negative_controls(wire)
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps({
            "model": "qwen3.5-plus", "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None, "tool_calls": [{"id": "offline-main-locator", "type": "function",
                "function": {"name": "read_source", "arguments": '{"source_id":"A1"}'}}],
            }}],
        }).encode()))

    def transport(**kwargs):
        assert kwargs == {"retries": 0, "verify": True, "trust_env": False}
        return httpx.MockTransport(dispatch)

    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, environment, clear=True))
        stack.enter_context(patch("dotenv.load_dotenv", return_value=False))
        stack.enter_context(_block_external_connections(faults))
        root = Path(stack.enter_context(TemporaryDirectory(prefix="locator-production-smoke-", dir=ROOT / "outputs")))
        charge = stack.enter_context(_fixture(root))
        from api import main as production

        # CrewAI subclasses the real transport while importing. Replace the
        # constructor only after that definition; sockets remain blocked during
        # imports, so this does not open a provider or telemetry escape window.
        stack.enter_context(patch.object(httpx, "AsyncHTTPTransport", transport))

        async def observed_app(scope, receive, send):
            if scope["type"] == "http" and scope["path"] in {POST, GET, "/source-locator", "/source-locator/"}:
                ingress.append((scope["method"], scope["path"], scope["scheme"],
                                [value for name, value in scope["headers"] if name == b"host"],
                                [value for name, value in scope["headers"] if name == b"origin"]))
            await production.app(scope, receive, send)

        with _serve(observed_app if proxy else production.app) as base, sync_playwright() as playwright:
            with httpx.Client(trust_env=False) as client:
                home = client.get(base + "/")
                assert home.status_code == 200 and 'href="/source-locator' in home.text
                # Enabled feature diagnostics must survive the main response
                # model too; working locator routes cannot hide broken health.
                health = client.get(base + "/health")
                assert health.status_code == 200 and health.json()["status"] == "ok"
                readiness = client.get(base + "/health/ready")
                assert readiness.status_code == 200 and readiness.json()["ready"] is True
            # Proxy-mode URLs are virtual. Even an accidentally un-intercepted
            # redirect must not resolve or connect to a public host.
            browser = playwright.chromium.launch(args=["--host-resolver-rules=MAP * ~NOTFOUND"] if proxy else [])
            try:
                h = (ProxyProductionBrowser(browser, base, faults) if proxy
                     else ProductionBrowser(browser, base + "/source-locator", faults))
                try:
                    h.inputs()
                    h.page.locator("#locate").click()
                    expect(h.page.locator("#request-status")).to_contain_text("请先确认")
                    assert h.page.evaluate("key => sessionStorage.getItem(key)", STORAGE) is None
                    assert not h.posts and len(native) == charge() == 0
                    h.page.locator("#locator-consent").check()
                    h.page.locator("#question").fill(QUESTION + "change")
                    expect(h.page.locator("#locator-consent")).not_to_be_checked()
                    h.page.locator("#question").fill(QUESTION)
                    h.page.locator("#locator-consent").check()
                    h.mode = "lost_post"
                    h.page.locator("#locate").click()
                    expect(h.page.locator("#request-status")).to_contain_text("服务端可能已经执行")
                    h.wait_settled()
                    h.blocked()
                    assert len(h.posts) == len(native) == charge() == 1
                    before = h.posts[0][2]
                    # A real rollback closes new admission, not the authorized
                    # observation route. No new provider identity is constructed.
                    production.app.state.source_locator.stop_accepting()
                    h.mode = "normal"
                    h.page.reload(wait_until="networkidle")
                    expect(h.page.locator("#execution-status")).to_contain_text("已关闭")
                    assert len(h.posts) == 1 and not h.gets
                    expect(h.page.locator("#access-code")).to_have_value("")
                    expect(h.page.locator("#locator-consent")).not_to_be_checked()
                    h.page.locator("#access-code").fill(CODE)
                    h.get()
                    expect(h.page.locator("#result")).to_be_visible()
                    h.wait_settled()
                    assert h.page.locator("#saved-text").text_content() == EXACT_TEXT
                    expect(h.page.locator("#saved-text *")).to_have_count(0)
                    expect(h.page.locator("#accounting-cost")).to_have_text("estimated · USD 0.000126100")
                    assert h.gets[-1][2]["receipt"]["result"] == before["receipt"]["result"]
                    assert h.gets[-1][2]["accounting"] == before["accounting"]
                    assert len(h.posts) == len(h.gets) == len(native) == charge() == 1
                    if proxy:
                        assert h.page.evaluate("location.origin") == PUBLIC_ORIGIN
                        assert all(scheme == "http" and hosts == [b"locator.invalid"]
                                   for _, _, scheme, hosts, _ in ingress)
                        posts = [row for row in ingress if row[0] == "POST"]
                        gets = [row for row in ingress if row[1] == GET]
                        assert len(posts) == len(gets) == 1
                        assert posts[0][4] == [PUBLIC_ORIGIN.encode()]
                    suffix = "-proxy" if proxy else ""
                    output = ROOT / f"output/playwright/source-locator-production{suffix}-smoke.png"
                    output.parent.mkdir(parents=True, exist_ok=True)
                    h.page.screenshot(path=str(output), full_page=True)
                finally:
                    h.close()
            finally:
                browser.close()
    assert not faults, faults
    print(f"Main locator Chromium {'public-HTTPS/backend-HTTP' if proxy else 'direct same-origin'} passed: "
          "consent precedes intent; one native interception and daily admission; "
          "lost acknowledgement recovered by one GET after execution closed; zero external provider requests.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proxy", action="store_true", help="Intercept a public HTTPS browser origin into loopback HTTP")
    main(proxy=parser.parse_args().proxy)
