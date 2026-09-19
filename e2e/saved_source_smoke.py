"""Real isolated factory -> bounded fixture loader -> Chromium, never a provider.

Unlike the older composer journey, successful POSTs are not browser-fulfilled.
Only this new operation and its exact static assets can leave the browser. The
Python process also blocks non-loopback sockets; no production app is imported.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
import threading
import time
from unittest.mock import patch
from urllib.parse import urlsplit

import uvicorn
from playwright.sync_api import Page, Route, expect, sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT = PROJECT_ROOT / "output/playwright/saved-source-smoke.png"
RUN_ID = "20260919T000000Z-" + "a" * 32
EMPTY_ID = "20260919T000000Z-" + "b" * 32
MISSING_ID = "20260919T000000Z-" + "c" * 32
CORRUPT_ID = "20260919T000000Z-" + "d" * 32
QUESTION = " \n定位这份虚构实验的设置 🙂\t "
TEXT_PREFIX = '  保存的虚构实验记录 🙂 e\u0301\t\r\n<img src="https://external.invalid/leak" onerror="window.executed=true">\n**不是 Markdown**\n'
TEXT_SUFFIX = "\nEXACT_UNICODE_TAIL 前🙂  \t\n"
EXACT_TEXT = TEXT_PREFIX + "字" * (1500 - len(TEXT_PREFIX) - len(TEXT_SUFFIX)) + TEXT_SUFFIX
BLANK_TEXT = " \t\r\n\u0085\u001c\u3000"
TITLE = '<img src="https://external.invalid/title" onerror="window.executed=true"> 虚构实验标题'


def _write_registry(root: Path) -> None:
    """Write only fresh fictional saved JSON; do not load live Source validators."""
    def row(index, text):
        return {
            "source_id": f"A{index}", "title": TITLE if index == 1 else f"Fictional source {index}",
            "publisher": "虚构研究室 <script>window.executed=true</script>", "source_type": "academic",
            "url": "javascript:alert('inert')", "doi": None, "published_date": "1899-01-02",
            "accessed_date": "2026-09-19", "evidence_summary": text, "summary_source": "abstract",
        }

    fixtures = {
        RUN_ID: {"academic_sources": [row(1, EXACT_TEXT), row(2, None), row(3, BLANK_TEXT), row(4, "x" * 1501)],
                 "patent_sources": [], "market_sources": []},
        EMPTY_ID: {"academic_sources": [], "patent_sources": [], "market_sources": []},
    }
    for run_id, registry in fixtures.items():
        target = root / run_id
        target.mkdir()
        (target / "validated_sources.json").write_text(json.dumps(registry, ensure_ascii=True), encoding="utf-8")
    corrupt = root / CORRUPT_ID
    corrupt.mkdir()
    (corrupt / "validated_sources.json").write_text("{not-json", encoding="utf-8")


class ScriptedSelector:
    """Trusted deterministic callback; event gates control the stale-reply seam."""

    def __init__(self):
        self.questions: list[str] = []
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self, request, /):
        question = request["messages"][1]["content"]
        self.questions.append(question)
        if question == "hold":
            self.entered.set()
            if not self.release.wait(20):
                raise RuntimeError("Scripted hold was not released")
        if question == "decline":
            return {"role": "assistant", "content": '{"action":"decline"}'}
        if question == "refuse":
            return {"role": "assistant", "content": None, "refusal": "Scripted refusal"}
        if question == "contract_error":
            return {"role": "assistant", "content": "PRIVATE_SCRIPT_ERROR_DO_NOT_ECHO"}
        selected = {"missing": "A2", "blank": "A3", "out_of_scope": "A4"}.get(question, "A1")
        return {"role": "assistant", "content": None, "tool_calls": [{
            "id": "fictional-script", "type": "function",
            "function": {"name": "read_source", "arguments": json.dumps({"source_id": selected})},
        }]}


@contextmanager
def _block_external_connections(faults):
    """Python providers cannot escape even if a later accidental import is added.

    Loopback sockets remain available for the ASGI listener and Windows event
    loop self-pipes. Browser requests have a separate exact URL/method allowlist.
    """
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_lookup = socket.getaddrinfo

    def check(host):
        if host not in {"127.0.0.1", "::1", "localhost", None}:
            faults.append("Blocked external Python connection")
            raise AssertionError("External network forbidden in saved-source smoke")

    def connect(sock, address):
        check(address[0] if isinstance(address, tuple) else address)
        return original_connect(sock, address)

    def connect_ex(sock, address):
        check(address[0] if isinstance(address, tuple) else address)
        return original_connect_ex(sock, address)

    def lookup(host, *args, **kwargs):
        check(host)
        return original_lookup(host, *args, **kwargs)

    with patch.object(socket.socket, "connect", connect), patch.object(socket.socket, "connect_ex", connect_ex), patch.object(socket, "getaddrinfo", lookup):
        yield


@contextmanager
def _serve(app):
    """Pre-bind one loopback socket; this never imports the old smoke harness."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="on"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    try:
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not server.started:
            raise RuntimeError("Isolated saved-source server did not start")
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()
        if thread.is_alive():
            raise RuntimeError("Isolated saved-source server did not stop")


def _capture(page: Page) -> None:
    SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SCREENSHOT), full_page=True)


def _journey(browser, base: str, selector: ScriptedSelector | None, faults: list[str]) -> int:
    context = browser.new_context(service_workers="block", viewport={"width": 1040, "height": 900})
    context.add_init_script("""
        for (const name of ['localStorage', 'sessionStorage', 'indexedDB']) {
            Object.defineProperty(window, name, {get() { throw new Error('Forbidden persistence'); }});
        }
        navigator.sendBeacon = () => { throw new Error('Forbidden telemetry'); };
    """)
    posts = []
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    allowed_posts = {f"/api/runs/{run_id}/saved-source-location" for run_id in (RUN_ID, EMPTY_ID, MISSING_ID, CORRUPT_ID)}

    def route_request(route: Route):
        request = route.request
        url = urlsplit(request.url)
        same_origin = (url.scheme, url.netloc) == ("http", urlsplit(base).netloc) and not url.query
        if same_origin and request.method == "POST" and url.path in allowed_posts:
            posts.append(request)
            body = request.post_data_json
            assert set(body) == {"question"} and isinstance(body["question"], str)
            assert not {"authorization", "x-access-code", "cookie"}.intersection(request.headers)
            route.continue_()  # Actual loader, locator and complete HTTP response.
        elif same_origin and request.method == "GET" and url.path in {"/", "/lab-static/app.js", "/lab-static/app.css"}:
            route.continue_()
        else:
            faults.append(f"Unexpected browser request: {request.method} {url.path}")
            route.abort()

    def block_websocket(websocket):
        faults.append("Unexpected browser WebSocket")
        websocket.close()

    context.route("**/*", route_request)
    context.route_web_socket("**/*", block_websocket)

    def send(question, run_id=RUN_ID):
        page.locator("#run-id").fill(run_id)
        page.locator("#question").fill(question)
        with page.expect_response(lambda reply: reply.request.method == "POST") as observed:
            page.locator("#locate").click()
        expect(page.locator("#locate")).to_be_enabled()
        return observed.value

    def assert_empty():
        expect(page.locator("#result")).to_be_hidden()
        assert page.locator("#saved-text").text_content() == ""
        expect(page.locator("#source-metadata dd")).to_have_count(0)

    try:
        page.goto(base, wait_until="networkidle")
        assert len(posts) == 0
        expect(page.locator(".notice").first).to_contain_text("billing not implemented")
        expect(page.locator(".notice").first).to_contain_text("not verified support")
        if selector is None:
            response = send(QUESTION)
            assert response.status == 503 and response.json()["error_code"] == "selector_disabled"
            expect(page.locator("#request-status")).to_contain_text("selector_disabled")
            assert_empty()
        else:
            response = send(QUESTION)
            assert response.status == 200
            assert response.headers["cache-control"] == "no-store"
            payload = response.json()
            assert payload["result"]["saved_text"]["text"] == EXACT_TEXT
            assert posts[-1].post_data_json == {"question": QUESTION}
            assert selector.questions == [QUESTION]
            assert page.locator("#saved-text").text_content() == EXACT_TEXT
            assert TITLE in page.locator("#source-metadata").text_content()
            assert "1899-01-02" in page.locator("#source-metadata").text_content()
            assert "javascript:alert('inert')" in page.locator("#source-metadata").text_content()
            expect(page.locator("#result img, #result script, #result a")).to_have_count(0)
            assert page.evaluate("window.executed === undefined")
            expect(page.locator("#catalog-coverage")).to_contain_text("4 / 共 4")
            expect(page.locator("#semantic-status")).to_contain_text("semantic_support: not_assessed")

            for question, state in [("missing", "missing_text"), ("blank", "blank_text"), ("decline", "declined"), ("refuse", "declined"), ("out_of_scope", "out_of_scope")]:
                assert send(question).status == 200
                expect(page.locator("#result-state")).to_contain_text(f"· {state}")
                assert page.locator("#saved-text").text_content() == (BLANK_TEXT if question == "blank" else "")
            callbacks = len(selector.questions)
            assert send("empty", EMPTY_ID).json()["result"]["state"] == "no_sources"
            expect(page.locator("#result-state")).to_contain_text("· no_sources")
            assert len(selector.questions) == callbacks

            for question, run_id, status in [("missing registry", MISSING_ID, 404), ("corrupt registry", CORRUPT_ID, 503), ("contract_error", RUN_ID, 502)]:
                assert send(question, run_id).status == status
                assert_empty()
                assert "PRIVATE_SCRIPT_ERROR" not in page.locator("#request-status").text_content()

            for change in ("input", "reset"):
                selector.entered.clear()
                selector.release.clear()
                page.locator("#run-id").fill(RUN_ID)
                page.locator("#question").fill("hold")
                before = len(posts)
                page.locator("#locate").click()
                assert selector.entered.wait(5), "Real callback did not enter"
                expect(page.locator("#locate")).to_be_disabled()
                # Exercise the handler guard even if a synthetic submit bypasses
                # disabled-button behavior. The server is still genuinely occupied.
                page.locator("#locator-form").dispatch_event("submit")
                if change == "reset":
                    page.locator("#reset").click()
                    expect(page.locator("#run-id")).to_have_value("")
                else:
                    page.locator("#run-id").fill(EMPTY_ID)
                page.locator("#run-id").fill(RUN_ID)
                page.locator("#question").fill("replacement")
                page.locator("#locator-form").dispatch_event("submit")
                assert_empty()
                assert len(posts) == before + 1
                with page.expect_response(lambda reply: reply.request.method == "POST"):
                    selector.release.set()
                expect(page.locator("#locate")).to_be_enabled()
                assert_empty()
                assert len(posts) == before + 1, "No automatic replacement after stale response"
                assert send("missing").status == 200
                expect(page.locator("#result-state")).to_contain_text("· missing_text")

            # Leave a useful final frame, not an empty error panel, for parent QA.
            assert send(QUESTION).status == 200
            assert page.locator("#saved-text").text_content() == EXACT_TEXT
            _capture(page)
        assert not faults, faults
        assert not errors, errors
        return len(posts)
    except BaseException:
        try:
            _capture(page)
        except Exception as exc:  # noqa: BLE001 -- screenshot failure cannot mask the failed assertion.
            print(f"Saved-source failure screenshot unavailable: {type(exc).__name__}", file=sys.stderr)
        raise
    finally:
        if selector is not None:
            selector.release.set()
        context.close()


def main() -> None:
    faults: list[str] = []
    assert "api.main" not in sys.modules, "This journey must not import production"
    with _block_external_connections(faults), TemporaryDirectory(prefix="saved-source-smoke-") as temporary:
        # Guard imports too: accidental future provider setup must not escape.
        from academic_agent.saved_source_loader import SavedSourceLoader
        from api.saved_source_app import create_saved_source_app

        root = Path(temporary)
        _write_registry(root)
        loader = SavedSourceLoader(root)
        selector = ScriptedSelector()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                # Default-off check uses a separate actual factory instance.
                with _serve(create_saved_source_app(load_snapshot=loader)) as base:
                    disabled_posts = _journey(browser, base, None, faults)
                with _serve(create_saved_source_app(load_snapshot=loader, selector=selector)) as base:
                    scripted_posts = _journey(browser, base, selector, faults)
            finally:
                browser.close()
    assert not faults, faults
    assert "api.main" not in sys.modules
    print(f"Saved-source smoke passed: {disabled_posts} disabled + {scripted_posts} real isolated POSTs; zero provider calls.")
    print(f"Screenshot: {SCREENSHOT.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
