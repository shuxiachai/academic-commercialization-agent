"""Actual Chromium/native-intercept/controller/store/HTTP accounting delivery.

Only native HTTP is synthetic; POST executes the real operation before its
acknowledgement is lost. GET fault variants never redispatch that operation.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlsplit

import httpx
from playwright.sync_api import expect, sync_playwright

from e2e.saved_source_receipt_smoke import BrowserFixture, CODE, QUESTION, _fixture
from e2e.saved_source_smoke import EXACT_TEXT, RUN_ID, _block_external_connections, _serve

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT = ROOT / "output/playwright/saved-source-usage-smoke.png"
STORAGE = "saved-source-usage:v1"
POST = f"/api/runs/{RUN_ID}/saved-source-usage"
GET = "/api/saved-source-usage-receipts"
FAKE_KEY = "sk-accounting-browser-offline-only"


class UsageBrowser(BrowserFixture):
    """Reuse the existing browser guards and explicit upstream-held signals."""

    def route(self, route):
        request = route.request
        url = urlsplit(request.url)
        same = (url.scheme, url.netloc) == ("http", urlsplit(self.base).netloc) and not url.query
        static = {"/", "/usage-static/app.js", "/usage-static/accounting.js", "/usage-static/app.css",
                  "/receipt-static/app.js", "/receipt-static/result.js", "/receipt-static/app.css"}
        if same and request.method == "GET" and url.path in static:
            route.continue_()
            return
        post = request.method == "POST" and url.path == POST
        get = request.method == "GET" and url.path == GET
        if not same or not (post or get):
            self.faults.append(f"Unexpected usage browser request: {request.method} {url.path}")
            route.abort()
            return
        assert "cookie" not in request.headers and "authorization" not in request.headers
        assert request.headers["x-access-code"] in {CODE, "wrong-fixture-code", "newer-fixture-code"}
        key = request.headers["idempotency-key"]
        if post:
            assert request.post_data_json == {"question": QUESTION}
            assert json.loads(self.page.evaluate("key => sessionStorage.getItem(key)", STORAGE)) == {
                "version": 1, "receipt_key": key,
            }
        else:
            assert request.post_data is None
        # No upstream redirect may escape the independently guarded browser.
        upstream = route.fetch(max_redirects=0)
        payload = upstream.json()
        (self.posts if post else self.gets).append((request, upstream.status, deepcopy(payload)))
        if post and self.mode == "lost_post":
            assert upstream.status == 200 and payload["receipt"]["result"]["saved_text"]["text"] == EXACT_TEXT
            assert payload["accounting"]["cost"]["estimated_usd"] == "0.000126100"
            route.abort()
        elif get and self.mode == "held_get":
            self.held.append((route, upstream))
            self.page.locator("#locator-form").evaluate("el => el.setAttribute('data-test-upstream-held', 'true')")
        elif get and self.mode in {"numeric_fraction", "numeric_exponent"}:
            # Preserve raw lexical spelling: parsing/stringifying first would
            # erase 1e0 and miss the boundary that originally hid valid text.
            assert upstream.status == 200
            literal = "0.0001261" if self.mode == "numeric_fraction" else "1e0"
            raw = upstream.text().replace('"estimated_usd":"0.000126100"', f'"estimated_usd":{literal}')
            assert f'"estimated_usd":{literal}' in raw
            route.fulfill(status=200, content_type="application/json", body=raw)
        elif get and self.mode in {"bad_accounting", "missing_accounting", "bad_receipt", "pending", "unknown"}:
            assert upstream.status == 200
            if self.mode == "bad_accounting":
                payload["accounting"]["cost"]["estimated_usd"] = "not-money <img src=x>"
            elif self.mode == "missing_accounting":
                payload["accounting"] = None
            elif self.mode == "bad_receipt":
                payload["receipt"]["receipt_key_sha256"] = "0" * 64
            else:
                from academic_agent.saved_source_usage import unavailable_usage
                receipt = payload["receipt"]
                receipt.update(state=self.mode, result=None, delivery="not_ready",
                               delivery_snapshot_reads=0, delivery_source_reads=0)
                payload["accounting"] = unavailable_usage(receipt["receipt_key_sha256"], receipt["run_id"], receipt["expires_at"])
            route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))
        else:
            route.fulfill(response=upstream)

    def empty(self):
        super().empty()
        expect(self.page.locator("#accounting")).to_be_hidden()
        assert self.page.locator("#accounting-facts").text_content() == ""

    def excerpt(self):
        expect(self.page.locator("#result")).to_be_visible()
        assert self.page.locator("#saved-text").text_content() == EXACT_TEXT
        expect(self.page.locator("#saved-text *")).to_have_count(0)
        expect(self.page.locator("#source-metadata img")).to_have_count(0)


def _recovery(browser, base, faults, requests, charge):
    h = UsageBrowser(browser, base, faults)
    cases = 0
    try:
        h.inputs()
        h.mode = "lost_post"
        h.page.locator("#locate").click()
        expect(h.page.locator("#request-status")).to_contain_text("服务端可能已经执行")
        h.wait_settled()
        h.empty()
        h.blocked()
        assert len(h.posts) == len(requests) == charge() == 1
        first = h.posts[0][2]
        assert set(first) == {"contract", "receipt", "accounting"}
        assert len(first["receipt"]) == 14
        cases += 1

        h.mode = "normal"
        h.page.reload(wait_until="networkidle")
        assert len(h.posts) == 1 and len(h.gets) == 0
        expect(h.page.locator("#access-code")).to_have_value("")
        h.blocked()
        h.page.locator("#access-code").fill(CODE)
        h.get()
        expect(h.page.locator("#accounting-cost")).to_have_text("estimated · USD 0.000126100")
        h.wait_settled()
        h.excerpt()
        assert json.loads(h.page.locator("#accounting-facts").text_content()) == first["accounting"]
        assert h.gets[-1][2]["accounting"] == first["accounting"]
        assert h.gets[-1][2]["receipt"]["result"] == first["receipt"]["result"]
        cases += 1

        for mode in ("bad_accounting", "missing_accounting", "numeric_fraction", "numeric_exponent"):
            h.mode = mode
            h.get()
            expect(h.page.locator("#accounting-cost")).to_contain_text("不可用")
            h.wait_settled()
            h.excerpt()
            expect(h.page.locator("#accounting-usage")).to_contain_text("未知")
            assert "USD 0" not in h.page.locator("#accounting-cost").text_content()
            h.blocked()
            cases += 1

        h.mode = "bad_receipt"
        h.get()
        expect(h.page.locator("#request-status")).to_contain_text("服务端可能已经执行")
        h.wait_settled()
        h.empty()
        h.blocked()
        cases += 1
        for mode in ("pending", "unknown"):
            h.mode = mode
            h.get()
            expect(h.page.locator("#request-status")).to_contain_text("pending/unknown")
            h.wait_settled()
            expect(h.page.locator("#result")).to_be_hidden()
            expect(h.page.locator("#accounting-usage")).to_contain_text("未知")
            h.page.locator("#risk").check()
            expect(h.page.locator("#acknowledge")).to_be_disabled()
            h.blocked()
            cases += 1

        h.mode = "held_get"
        h.get()
        h.wait_held()
        h.page.locator("#access-code").fill("newer-fixture-code")
        h.empty()
        route, upstream = h.held.pop()
        route.fulfill(response=upstream)
        expect(h.page.locator("#request-status")).to_contain_text("响应已丢弃")
        h.wait_settled()
        h.empty()
        h.blocked()
        cases += 1

        h.mode = "normal"
        h.page.locator("#access-code").fill(CODE)
        h.get()
        expect(h.page.locator("#accounting-cost")).to_have_text("estimated · USD 0.000126100")
        h.wait_settled()
        h.excerpt()
        assert len(h.posts) == len(requests) == charge() == 1
        SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
        h.page.screenshot(path=str(SCREENSHOT), full_page=True)
        return cases, len(h.posts), len(h.gets)
    finally:
        h.close()


def main():
    faults, requests = [], []
    assert "api.main" not in sys.modules
    # The old strict guards are reused unchanged. No credentials or .env are
    # discovered; this explicitly fake key reaches only MockTransport below.
    with _block_external_connections(faults), patch("dotenv.load_dotenv", side_effect=AssertionError("No dotenv")), TemporaryDirectory(prefix="usage-smoke-", dir=ROOT / "outputs") as temporary:
        from academic_agent.saved_source_accounted_qwen import AccountedQwenSelector
        from academic_agent.saved_source_loader import SavedSourceLoader
        from api.saved_source_usage_app import create_saved_source_usage_app

        def dispatch(request):
            requests.append(request)
            assert request.headers["authorization"] == "Bearer " + FAKE_KEY
            wire = json.loads(request.content)
            assert wire["messages"][1]["content"] == QUESTION
            assert EXACT_TEXT not in request.content.decode()
            assert CODE not in request.content.decode()
            return httpx.Response(200, stream=httpx.ByteStream(json.dumps({
                "model": "qwen3.5-plus", "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
                "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                    "role": "assistant", "content": None, "tool_calls": [{"id": "fake-usage-browser", "type": "function",
                    "function": {"name": "read_source", "arguments": '{"source_id":"A1"}'}}],
                }}],
            }).encode()))

        def transport(**kwargs):
            assert kwargs == {"retries": 0, "verify": True, "trust_env": False}
            return httpx.MockTransport(dispatch)

        root = Path(temporary)
        with _fixture(root) as charge, patch.object(httpx, "AsyncHTTPTransport", transport), sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                loader = SavedSourceLoader(root)
                with _serve(create_saved_source_usage_app(load_snapshot=loader, journal_root=root)) as base:
                    h = UsageBrowser(browser, base, faults)
                    try:
                        h.inputs()
                        h.page.locator("#locate").click()
                        expect(h.page.locator("#request-status")).to_contain_text("selector_disabled")
                        h.wait_settled()
                        h.blocked()
                        h.get()
                        expect(h.page.locator("#request-status")).to_contain_text("receipt_not_found")
                        h.wait_settled()
                        h.empty()
                        h.blocked()
                        assert len(h.posts) == len(h.gets) == 1 and len(requests) == charge() == 0
                    finally:
                        h.close()
                    broken = UsageBrowser(browser, base, faults, storage_script="Object.defineProperty(window, 'sessionStorage', {get(){throw Error('denied');}});")
                    try:
                        broken.inputs()
                        broken.blocked()
                        assert not broken.posts and not broken.gets
                    finally:
                        broken.close()
                selector = AccountedQwenSelector(FAKE_KEY, snapshot=loader(RUN_ID), question=QUESTION, ledger_dir=root / "fresh-native")
                app = create_saved_source_usage_app(load_snapshot=loader, journal_root=root, accounted_selector=selector,
                                                    selector_identity="synthetic-native-usage-browser-v1")
                with _serve(app) as base:
                    cases, posts, gets = _recovery(browser, base, faults, requests, charge)
            finally:
                browser.close()
    assert not faults, faults
    assert "api.main" not in sys.modules
    print(f"Saved-source usage smoke passed: {cases + 3} cases; 1 disabled + {posts} actual POST; {gets + 1} GET; "
          "native HTTP intercepted=1, external provider calls=0, daily admissions=1.")
    print(f"Screenshot: {SCREENSHOT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
