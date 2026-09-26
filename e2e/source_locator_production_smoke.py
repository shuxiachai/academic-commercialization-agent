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
FAILED_RUN = "20260926T235959Z-ffffffffffffffffffffffffffffffff"
FAILED_POST = f"/api/runs/{FAILED_RUN}/source-locator"
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
            "entry.js", "outcome.js", "receipt.js", "result.js", "accounting.js", "app.css", "receipt.css"))}
        if same and request.method == "GET" and url.path in assets:
            self.asset(route)
            return
        post = request.method == "POST" and url.path in {POST, FAILED_POST}
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


def _main_spa_navigation(browser, base, faults, *, proxy=False, old_link=False):
    """Serve real SPA modules; only synthetic read data and old-defect bytes vary."""
    run_b = "20260926T121212Z-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    origin = PUBLIC_ORIGIN if proxy else base
    context = browser.new_context(service_workers="block")
    page = context.new_page()
    page.on("pageerror", lambda error: faults.append(f"main SPA: {error}"))
    assets = {"/", f"/run/{RUN_ID}", f"/run/{run_b}", "/source-locator",
              "/static/brand/aca-mark.svg",
              *(f"/static/js/{name}.js" for name in
                ("app", "api", "run", "sidebar", "result", "i18n", "topic", "paid_receipts")),
              *(f"/static/css/{name}.css" for name in ("tokens", "base", "workbench", "result")),
              *(f"/source-locator-static/{name}" for name in
                ("entry.js", "outcome.js", "receipt.js", "result.js", "accounting.js", "app.css", "receipt.css"))}
    progress_reads, injections = [], []

    def reply(route, payload):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    def route_request(route):
        request, url = route.request, urlsplit(route.request.url)
        expected = urlsplit(origin)
        if (url.scheme, url.netloc) != (expected.scheme, expected.netloc) or request.method != "GET":
            faults.append(f"Unexpected SPA request: {request.method} {request.url}")
            route.abort()
        elif not url.query and url.path in assets:
            if proxy or (old_link and url.path == "/static/js/app.js"):
                headers = request.all_headers()
                headers["host"] = urlsplit(origin).netloc
                upstream = route.fetch(url=base + url.path, headers=headers, max_redirects=0)
                assert upstream.status == 200
                if old_link and url.path == "/static/js/app.js":
                    source = upstream.text()
                    hook = "  syncSourceLocatorLink();"
                    assert source.count(hook) == 3
                    injections.append(url.path)
                    route.fulfill(response=upstream, body=source.replace(hook, ""))
                else:
                    route.fulfill(response=upstream)
            else:
                route.continue_()
        elif not url.query and url.path == "/api/access/check":
            reply(route, {"ok": True})
        elif url.path == "/api/runs" and url.query == "limit=50":
            reply(route, {"runs": [{"run_id": RUN_ID, "topic": "Run A", "state": "completed"},
                                   {"run_id": run_b, "topic": "Run B", "state": "completed"}]})
        elif not url.query and url.path == "/health":
            reply(route, {"active_runs": 0, "active_paid_operations": 0, "max_concurrent": 1})
        elif url.path in {f"/api/runs/{RUN_ID}/progress", f"/api/runs/{run_b}/progress"} and url.query == "since=0":
            run_id = RUN_ID if url.path.endswith(RUN_ID + "/progress") else run_b
            progress_reads.append(run_id)
            reply(route, {"run_id": run_id, "topic": "Run A" if run_id == RUN_ID else "Run B", "state": "completed",
                          "stage": "Done", "steps": [], "artifacts": [], "elapsed_seconds": 0})
        else:
            faults.append(f"Unexpected SPA GET: {url.path}?{url.query}")
            route.abort()

    def block_websocket(websocket):
        faults.append("Unexpected SPA WebSocket")
        websocket.close()

    context.route("**/*", route_request)
    context.route_web_socket("**/*", block_websocket)
    try:
        page.goto(origin + f"/run/{RUN_ID}", wait_until="networkidle")
        link = page.locator("#source-locator-link")
        expect(link).to_have_attribute("href", f"/source-locator#{RUN_ID}")
        page.locator(f'.runitem[data-run-id="{run_b}"]').click()
        expect(page.locator("#run-title")).to_have_text("Run B")
        assert run_b in progress_reads
        try:
            expect(link).to_have_attribute("href", f"/source-locator#{run_b}", timeout=1500)
        except AssertionError:
            if not old_link:
                raise
            assert injections == ["/static/js/app.js"]
            assert link.get_attribute("href") == f"/source-locator#{RUN_ID}"
            print("Controlled served old SPA: same A->B href assertion FAILED as required.")
            return
        assert not old_link, "Stale-link negative control escaped the new browser assertion"
        link.click()
        expect(page.locator("#run-id")).to_have_value(run_b)
        assert page.url == origin + "/source-locator#" + run_b
        page.go_back(wait_until="networkidle")
        expect(page.locator("#source-locator-link")).to_have_attribute("href", f"/source-locator#{run_b}")
        page.evaluate("() => { history.pushState({}, '', '/'); dispatchEvent(new PopStateEvent('popstate')); }")
        expect(page.locator("#source-locator-link")).to_have_attribute("href", "/source-locator")
        expect(page.locator("#pane-compose")).to_be_visible()
        page.locator(f'.runitem[data-run-id="{RUN_ID}"]').click()
        expect(page.locator("#run-title")).to_have_text("Run A")
        assert page.url == origin + f"/run/{RUN_ID}"
        page.evaluate("() => { history.pushState = () => { throw Error('test history failure'); }; }")
        page.locator(f'.runitem[data-run-id="{run_b}"]').click()
        expect(page.locator("#run-title")).to_have_text("Run B")
        expect(page.locator("#source-locator-link")).to_have_attribute("href", f"/source-locator#{run_b}")
        assert page.url == origin + f"/run/{RUN_ID}", "Test must retain stale URL A while logical view is B"
        page.locator("#new-run-btn").click()
        expect(page.locator("#pane-compose")).to_be_visible()
        expect(page.locator("#source-locator-link")).to_have_attribute("href", "/source-locator")
        assert page.url == origin + f"/run/{RUN_ID}"
        print("SPA A->B, actual locator prefill, root popstate and failed-history A->B/home passed.")
    finally:
        context.close()


def _failed_receipt_notice(browser, base, faults, native, charge, *, proxy=False, old_entry=False):
    """Observe a real pre-admission receipt, including the old served-entry control."""
    fixture = ProxyProductionBrowser if proxy else ProductionBrowser
    injections = []
    if old_entry:
        class WithoutOutcome(fixture):
            def asset(self, route):
                if urlsplit(route.request.url).path != "/source-locator-static/entry.js":
                    return super().asset(route)
                upstream = self.fetch(route)
                assert upstream.status == 200
                source = upstream.text()
                hook = "renderOutcome(decoded, byId);"
                assert source.count(hook) == 1
                injections.append(hook)
                route.fulfill(response=upstream, body=source.replace(hook, ""))
        fixture = WithoutOutcome
    failed = fixture(browser, base if proxy else base + "/source-locator", faults)
    try:
        failed.inputs()
        failed.page.locator("#run-id").fill(FAILED_RUN)
        failed.page.locator("#locator-consent").check()
        failed.page.locator("#locate").click()
        expect(failed.page.locator("#receipt")).to_be_visible()
        failed.wait_settled()
        assert len(failed.posts) == 1 and failed.posts[0][1] == 200
        receipt = failed.posts[0][2]["receipt"]
        assert receipt["state"] == "failed" and receipt["error_code"] == "saved_source_missing"
        assert receipt["admission_state"] == "not_admitted"
        assert len(native) == charge() == 0
        notice = failed.page.locator("#receipt-outcome")
        try:
            expect(notice).to_be_visible(timeout=1500)
        except AssertionError:
            if not old_entry:
                raise
            assert injections == ["renderOutcome(decoded, byId);"]
            assert notice.text_content() == ""
            print("Controlled served old entry: same failed-receipt visibility assertion FAILED as required.")
            return
        assert not old_entry, "Missing-hook negative control escaped the new browser assertion"
        expect(notice).to_contain_text("定位失败：此报告的已保存来源不可用")
        expect(notice).to_contain_text("不代表免费或可自动重试")
        expect(failed.page.locator("#receipt-outcome *")).to_have_count(0)
        assert "saved_source_missing" not in notice.text_content()
        before = failed.page.evaluate("key => sessionStorage.getItem(key)", STORAGE)
        suffix = "-proxy" if proxy else ""
        output = ROOT / f"output/playwright/source-locator-failed-receipt{suffix}.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        failed.page.screenshot(path=str(output), full_page=True)
        failed.page.locator("#reset").click()
        expect(notice).to_be_hidden()
        assert notice.text_content() == ""
        assert failed.page.evaluate("key => sessionStorage.getItem(key)", STORAGE) == before
        expect(failed.page.locator("#locate")).to_be_disabled()
        assert len(failed.posts) == 1 and not failed.gets and len(native) == charge() == 0
        print("Real failed receipt: Chinese notice visible, reset clears prose but retains blocked receipt.")
    finally:
        failed.close()


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
        # Copy only the fixture's synthetic owner; do not patch authorization.
        missing_sources = root / FAILED_RUN
        missing_sources.mkdir()
        (missing_sources / ".owner").write_bytes((root / RUN_ID / ".owner").read_bytes())
        from api import main as production

        # CrewAI subclasses the real transport while importing. Replace the
        # constructor only after that definition; sockets remain blocked during
        # imports, so this does not open a provider or telemetry escape window.
        stack.enter_context(patch.object(httpx, "AsyncHTTPTransport", transport))

        async def observed_app(scope, receive, send):
            if scope["type"] == "http" and scope["path"] in {POST, FAILED_POST, GET, "/source-locator", "/source-locator/"}:
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
                    # The owned fixture deliberately lacks sources.json, so the
                    # normal owner check precedes a real pre-admission failure.
                    _failed_receipt_notice(browser, base, faults, native, charge, proxy=proxy)
                    _failed_receipt_notice(browser, base, faults, native, charge, proxy=proxy, old_entry=True)
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
                        posts = [row for row in ingress if row[1] == POST]
                        failed_posts = [row for row in ingress if row[1] == FAILED_POST]
                        gets = [row for row in ingress if row[1] == GET]
                        assert len(posts) == len(gets) == 1
                        assert posts[0][4] == [PUBLIC_ORIGIN.encode()]
                        assert len(failed_posts) == 2
                        assert all(row[4] == [PUBLIC_ORIGIN.encode()] for row in failed_posts)
                    suffix = "-proxy" if proxy else ""
                    output = ROOT / f"output/playwright/source-locator-production{suffix}-smoke.png"
                    output.parent.mkdir(parents=True, exist_ok=True)
                    h.page.screenshot(path=str(output), full_page=True)
                finally:
                    h.close()
                _main_spa_navigation(browser, base, faults, proxy=proxy)
                _main_spa_navigation(browser, base, faults, proxy=proxy, old_link=True)
                assert len(native) == charge() == 1, "UI checks must not create another native request"
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
