"""Actual isolated ASGI/admission/journal -> Chromium with synthetic callbacks.

The lost POST is genuinely executed via route.fetch(), then its reply is aborted.
Only GET observations are fault-injected; no paid success response is invented.
The unchanged old lab supplies loopback/socket guards, not production fixtures.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

from e2e.saved_source_smoke import (
    EXACT_TEXT, RUN_ID, ScriptedSelector, TITLE, _block_external_connections, _serve, _write_registry,
)

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT = ROOT / "output/playwright/saved-source-receipt-smoke.png"
CODE = "synthetic-receipt-smoke-code"
STORAGE = "saved-source-receipts:v1"
QUESTION = " \n定位保存的虚构实验 🙂\t "
GUARDS = """
    globalThis.__receiptForbidden = [];
    for (const name of ['localStorage', 'indexedDB']) {
        Object.defineProperty(window, name, {get() {
            __receiptForbidden.push(name); throw new Error('Forbidden persistence');
        }});
    }
    navigator.sendBeacon = () => { __receiptForbidden.push('beacon'); throw new Error('Forbidden telemetry'); };
"""


@contextmanager
def _fixture(root):
    """Patch only this process to fresh disk/shared-ledger state and fake codes."""
    from api import access, runs

    with ExitStack() as stack:
        for name, value in {"DEFAULT_OUTPUT_ROOT": root, "_registry": {}, "_stop_claims": {},
                            "_inline_paid_operations": {}, "_daily_counts": {}, "_daily_date": None,
                            "MAX_CONCURRENT": 1, "DAILY_CAP": 20}.items():
            stack.enter_context(patch.object(runs, name, value))
        for name, value in {"ACCESS_CODE": CODE, "ACCESS_CODES": None, "ADMIN_CODE": None}.items():
            stack.enter_context(patch.object(access, name, value))
        _write_registry(root)
        for folder in root.iterdir():
            if folder.is_dir():
                (folder / ".owner").write_text(access.owner_id(CODE), encoding="utf-8")
        yield lambda: runs._daily_counts.get(access.owner_id(CODE), 0)
        assert runs.active_paid_operation_count() == 0


class BrowserFixture:
    """Exact request allowlist with observed actual upstream replies."""

    def __init__(self, browser, base, faults, *, storage_script=""):
        self.context = browser.new_context(service_workers="block", viewport={"width": 1040, "height": 1100})
        self.context.add_init_script(GUARDS + storage_script)
        self.page = self.context.new_page()
        self.base = base
        self.faults = faults
        self.posts = []
        self.gets = []
        self.held = []
        self.mode = "normal"
        self.page.on("pageerror", lambda error: faults.append(str(error)))
        self.context.route("**/*", self.route)
        self.context.route_web_socket("**/*", self.websocket)
        self.page.goto(base, wait_until="networkidle")
        assert not self.posts and not self.gets, "Boot must not request a receipt or POST"

    def websocket(self, websocket):
        self.faults.append("Unexpected browser WebSocket")
        websocket.close()

    def route(self, route):
        request = route.request
        url = urlsplit(request.url)
        same_origin = (url.scheme, url.netloc) == ("http", urlsplit(self.base).netloc) and not url.query
        static = {"/", "/receipt-static/app.js", "/receipt-static/result.js", "/receipt-static/app.css"}
        if same_origin and request.method == "GET" and url.path in static:
            route.continue_()
            return
        is_post = request.method == "POST" and url.path == f"/api/runs/{RUN_ID}/saved-source-location"
        is_get = request.method == "GET" and url.path == "/api/saved-source-receipts"
        if not same_origin or not (is_post or is_get):
            self.faults.append(f"Unexpected browser request: {request.method} {url.path}")
            route.abort()
            return
        assert "cookie" not in request.headers and "authorization" not in request.headers
        key = request.headers["idempotency-key"]
        assert request.headers["x-access-code"] in {CODE, "wrong-fixture-code", "newer-fixture-code"}
        if is_post:
            assert request.post_data_json == {"question": QUESTION}
            persisted = self.page.evaluate("key => sessionStorage.getItem(key)", STORAGE)
            assert json.loads(persisted) == {"version": 1, "receipt_key": key}, "Persist before actual POST"
        else:
            assert request.post_data is None
        # This reaches the actual factory/controller/shared ledger even when
        # the browser later loses or rejects the returned acknowledgement.
        upstream = route.fetch(max_redirects=0)
        payload = upstream.json() if upstream.status == 200 or upstream.headers.get("content-type", "").startswith("application/json") else None
        (self.posts if is_post else self.gets).append((request, upstream.status, payload))
        if is_post and self.mode == "lost_post":
            assert upstream.status == 200 and payload["state"] == "completed"
            assert payload["result"]["saved_text"]["text"] == EXACT_TEXT
            route.abort()
        elif is_get and self.mode in {"held_get", "timeout_get"}:
            self.held.append((route, upstream))
            # Client busy precedes HTTP completion. Signal actual upstream
            # observation, not elapsed time or merely the start of fetch.
            self.page.locator("#locator-form").evaluate("element => element.setAttribute('data-test-upstream-held', 'true')")
        elif is_get and self.mode == "malformed_get":
            assert upstream.status == 200
            payload["receipt_key_sha256"] = "0" * 64
            route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))
        else:
            route.fulfill(response=upstream)

    def inputs(self, code=CODE):
        self.page.locator("#access-code").fill(code)
        self.page.locator("#run-id").fill(RUN_ID)
        self.page.locator("#question").fill(QUESTION)

    def empty(self):
        expect(self.page.locator("#result")).to_be_hidden()
        assert self.page.locator("#saved-text").text_content() == ""
        expect(self.page.locator("#source-metadata dd")).to_have_count(0)

    def blocked(self):
        count = len(self.posts)
        expect(self.page.locator("#locate")).to_be_disabled()
        self.page.locator("#locator-form").dispatch_event("submit")
        assert len(self.posts) == count

    def get(self):
        self.page.locator("#locator-form").evaluate("element => element.setAttribute('data-test-upstream-held', 'false')")
        self.page.locator("#recover").click()

    def wait_held(self):
        expect(self.page.locator("#locator-form")).to_have_attribute("data-test-upstream-held", "true")
        assert len(self.held) == 1

    def wait_settled(self):
        expect(self.page.locator("#locator-form")).to_have_attribute("aria-busy", "false")

    def close(self):
        for route, _ in self.held:
            route.abort()
        assert self.page.evaluate("__receiptForbidden") == []
        self.context.close()


def _disabled(browser, base, faults, charge):
    h = BrowserFixture(browser, base, faults)
    try:
        h.inputs()
        h.page.locator("#locate").click()
        expect(h.page.locator("#request-status")).to_contain_text("selector_disabled")
        h.wait_settled()
        assert h.posts[0][1] == 503 and charge() == 0
        h.empty()
        h.blocked()
        h.get()
        expect(h.page.locator("#request-status")).to_contain_text("receipt_not_found")
        h.wait_settled()
        h.page.locator("#risk").check()
        expect(h.page.locator("#acknowledge")).to_be_disabled()
        h.page.locator("#reset").click()
        h.blocked()
        assert len(h.posts) == len(h.gets) == 1 and charge() == 0
        return 2, 1, 1
    finally:
        h.close()


def _recovery(browser, base, faults, selector, charge, redirect_probe):
    h = BrowserFixture(browser, base, faults)
    cases = 0
    try:
        h.mode = "lost_post"
        h.inputs()
        h.page.locator("#locate").click()
        expect(h.page.locator("#request-status")).to_contain_text("服务端可能已经执行")
        h.wait_settled()
        h.empty()
        h.blocked()
        assert charge() == len(selector.questions) == len(h.posts) == 1
        key = h.posts[0][0].headers["idempotency-key"]
        assert selector.questions == [QUESTION]
        cases += 1

        h.mode = "normal"
        h.page.reload(wait_until="networkidle")
        expect(h.page.locator("#access-code")).to_have_value("")
        expect(h.page.locator("#run-id")).to_have_value("")
        expect(h.page.locator("#question")).to_have_value("")
        expect(h.page.locator("#recover")).to_be_disabled()
        h.blocked()
        assert len(h.posts) == 1 and len(h.gets) == 0
        h.page.locator("#access-code").fill("wrong-fixture-code")
        h.get()
        expect(h.page.locator("#request-status")).to_contain_text("access_denied")
        h.wait_settled()
        h.empty()
        h.blocked()
        assert h.gets[-1][1] == 401
        cases += 1

        # Hold a real 401, change the selected code, then deliver the stale reply.
        h.mode = "held_get"
        h.get()
        h.wait_held()
        h.page.locator("#access-code").fill("newer-fixture-code")
        h.blocked()
        route, upstream = h.held.pop()
        assert upstream.status == 401
        route.fulfill(response=upstream)
        expect(h.page.locator("#request-status")).to_contain_text("旧请求已结束")
        expect(h.page.locator("#access-code")).to_have_value("newer-fixture-code")
        h.empty()
        cases += 1

        h.mode = "normal"
        h.page.locator("#access-code").fill(CODE)
        h.get()
        expect(h.page.locator("#result")).to_be_visible()
        h.wait_settled()
        assert h.page.locator("#saved-text").text_content() == EXACT_TEXT
        expect(h.page.locator("#result img, #result script, #result a")).to_have_count(0)
        assert h.page.evaluate("window.executed === undefined")
        assert TITLE in h.page.locator("#source-metadata").text_content()
        assert "javascript:alert('inert')" in h.page.locator("#source-metadata").text_content()
        expect(h.page.locator("#receipt-context")).to_contain_text(RUN_ID)
        expect(h.page.locator("#receipt-context")).to_contain_text("原始问题未保存")
        expect(h.page.locator("#receipt-facts")).to_contain_text('"provider_cost": "not_observed"')
        expect(h.page.locator("#semantic-status")).to_contain_text("semantic_support: not_assessed")
        assert h.gets[-1][2]["delivery_snapshot_reads"] == h.gets[-1][2]["delivery_source_reads"] == 1
        assert charge() == len(selector.questions) == len(h.posts) == 1
        cases += 1

        h.mode = "malformed_get"
        h.get()
        expect(h.page.locator("#request-status")).to_contain_text("校验不可用")
        h.wait_settled()
        h.empty()
        h.page.locator("#risk").check()
        expect(h.page.locator("#acknowledge")).to_be_disabled()
        h.blocked()
        cases += 1

        # A real terminal GET is still stale after reset; it cannot authorize
        # acknowledgement or release the occupied request until it settles.
        h.mode = "held_get"
        h.get()
        h.wait_held()
        h.page.locator("#reset").click()
        h.page.locator("#access-code").fill(CODE)
        h.blocked()
        route, upstream = h.held.pop()
        route.fulfill(response=upstream)
        expect(h.page.locator("#request-status")).to_contain_text("旧请求已结束")
        h.empty()
        h.page.locator("#risk").check()
        expect(h.page.locator("#acknowledge")).to_be_disabled()
        h.blocked()
        cases += 1

        h.mode = "timeout_get"
        h.get()
        h.wait_held()
        expect(h.page.locator("#request-status")).to_contain_text("校验不可用", timeout=16000)
        h.wait_settled()
        h.empty()
        assert len(h.held) == 1
        route, _ = h.held.pop()
        route.abort()
        h.blocked()
        cases += 1

        # The actual local ASGI wrapper returns a redirect, without consulting
        # any external host. Neither route.fetch nor the shipped fetch may
        # follow it; otherwise this target counter or the browser guard fails.
        h.mode = "normal"
        redirect_probe.redirect_next = True
        h.get()
        expect(h.page.locator("#request-status")).to_contain_text("校验不可用")
        h.wait_settled()
        h.empty()
        h.blocked()
        assert redirect_probe.redirects == 1 and redirect_probe.target_requests == 0
        assert h.gets[-1][1] == 307
        cases += 1

        h.mode = "normal"
        h.get()
        expect(h.page.locator("#result")).to_be_visible()
        h.wait_settled()
        assert h.page.locator("#saved-text").text_content() == EXACT_TEXT
        assert all(request.headers["idempotency-key"] == key for request, _, _ in h.gets)
        assert h.page.evaluate("Object.keys(sessionStorage)") == [STORAGE]
        assert h.page.evaluate("key => JSON.parse(sessionStorage.getItem(key))", STORAGE) == {"version": 1, "receipt_key": key}
        SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
        h.page.screenshot(path=str(SCREENSHOT), full_page=True)
        h.page.locator("#risk").check()
        h.page.locator("#acknowledge").click()
        expect(h.page.locator("#locate")).to_be_enabled()
        assert h.page.evaluate("key => sessionStorage.getItem(key)", STORAGE) is None
        assert charge() == len(selector.questions) == len(h.posts) == 1
        cases += 1
        return cases, len(h.posts), len(h.gets)
    finally:
        h.close()


def _storage(browser, base, faults):
    scenarios = [
        "Object.defineProperty(window, 'sessionStorage', {get() {throw new Error('Denied');}});",
        f"sessionStorage.setItem('{STORAGE}', '{{broken');",
        f"const originalSet = Storage.prototype.setItem; Storage.prototype.setItem = function(k,v) {{if(k !== '{STORAGE}') originalSet.call(this,k,v);}};",
    ]
    for script in scenarios:
        h = BrowserFixture(browser, base, faults, storage_script=script)
        try:
            h.inputs()
            h.page.locator("#locator-form").dispatch_event("submit")
            expect(h.page.locator("#storage-status")).to_contain_text("持续阻止新提交")
            h.blocked()
            h.page.locator("#reset").click()
            h.inputs()
            h.blocked()
            assert not h.posts and not h.gets
        finally:
            h.close()
    return len(scenarios)


class LocalRedirectProbe:
    """One explicitly armed same-origin GET redirect, outside the real factory."""

    def __init__(self, app):
        self.app = app
        self.redirect_next = False
        self.redirects = 0
        self.target_requests = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/redirect-probe-target":
            self.target_requests += 1
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b"{}"})
            return
        if (scope["type"] == "http" and scope["method"] == "GET"
                and scope["path"] == "/api/saved-source-receipts" and self.redirect_next):
            self.redirect_next = False
            self.redirects += 1
            await send({"type": "http.response.start", "status": 307,
                        "headers": [(b"location", b"/redirect-probe-target"), (b"cache-control", b"no-store")]})
            await send({"type": "http.response.body", "body": b""})
            return
        await self.app(scope, receive, send)


def main():
    faults = []
    assert "api.main" not in sys.modules, "Never import production in this journey"
    # Fail instead of reading any .env, including during guarded factory imports.
    with _block_external_connections(faults), patch("dotenv.load_dotenv", side_effect=AssertionError("No dotenv")), TemporaryDirectory(prefix="saved-source-receipt-") as temporary:
        from academic_agent.saved_source_loader import SavedSourceLoader
        from api.saved_source_receipt_app import create_saved_source_receipt_app

        root = Path(temporary)
        with _fixture(root) as charge, sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                with _serve(create_saved_source_receipt_app(load_snapshot=SavedSourceLoader(root), journal_root=root)) as base:
                    disabled_cases, disabled_posts, disabled_gets = _disabled(browser, base, faults, charge)
                selector = ScriptedSelector()
                probe = LocalRedirectProbe(create_saved_source_receipt_app(load_snapshot=SavedSourceLoader(root), journal_root=root,
                                                                          selector=selector, selector_identity="synthetic-receipt-smoke-v1"))
                with _serve(probe) as base:
                    recovery_cases, posts, gets = _recovery(browser, base, faults, selector, charge, probe)
                    storage_cases = _storage(browser, base, faults)
                    assert len(selector.questions) == charge() == 1
            finally:
                browser.close()
    assert not faults, faults
    assert "api.main" not in sys.modules
    print(f"Saved-source receipt smoke passed: {disabled_cases + recovery_cases + storage_cases} cases; "
          f"{disabled_posts} disabled + {posts} executed real POSTs; {disabled_gets + gets} real GETs; "
          "selector calls=1, daily charges=1, provider calls=0.")
    print(f"Screenshot: {SCREENSHOT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
