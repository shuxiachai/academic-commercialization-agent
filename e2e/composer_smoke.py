"""Real Chromium composer journey with browser-fulfilled paid-operation stubs.

The server exposes static assets only, never the production paid endpoints.
Every API request is intercepted, every unexpected request fails the audit,
and delayed responses exercise the actual DOM, fetch client and event handlers.
This complements, rather than relaxes, the read-only browser_smoke contract.
"""

from __future__ import annotations

import json
import time
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import Page, Route, expect, sync_playwright

from e2e.browser_smoke import PROJECT_ROOT, _capture_failure, _serve


def _wait_requests(page: Page, requests: list[Route], count: int) -> None:
    deadline = time.monotonic() + 5
    while len(requests) < count and time.monotonic() < deadline:
        page.wait_for_timeout(10)  # Pump intercepted browser events until the condition holds.
    assert len(requests) == count, f"Expected {count} requests, observed {len(requests)}"


def _json(route: Route, value: dict, *, status: int = 200, code: str | None = None) -> None:
    route.fulfill(status=status, content_type="application/json", body=json.dumps(value),
                  headers={"X-Error-Code": code} if code else {})


def main() -> None:
    app = FastAPI()
    reached_server: list[str] = []

    @app.middleware("http")
    async def static_only(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"} or request.url.path.startswith("/api/"):
            reached_server.append(f"{request.method} {request.url.path}")
            return JSONResponse({"detail": "No API exists in the composer fixture"}, status_code=500)
        return await call_next(request)

    app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "web/static"), name="static")

    @app.get("/")
    def index():
        return FileResponse(PROJECT_ROOT / "web/index.html")

    requests: list[Route] = []
    unexpected: list[str] = []
    page_errors: list[str] = []
    run_id = "20260906T000000Z-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    progress = {"run_id": run_id, "topic": "Accepted fixture assessment", "state": "completed",
                "stage": "Done", "steps": [], "artifacts": [], "elapsed_seconds": 0}

    with _serve(app) as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()

        def route_request(route: Route) -> None:
            request = route.request
            url = urlsplit(request.url)
            if url.netloc != urlsplit(base).netloc:
                unexpected.append(f"External request: {request.method} {request.url}")
                route.abort()
            elif request.method == "POST" and url.path in {"/api/papers", "/api/runs"}:
                requests.append(route)  # Never continue to an ASGI paid endpoint.
            elif request.method != "GET":
                unexpected.append(f"Unexpected method: {request.method} {url.path}")
                route.abort()
            elif url.path == "/api/access/check":
                _json(route, {"ok": True})
            elif url.path == "/api/runs":
                _json(route, {"runs": []})
            elif url.path == f"/api/runs/{run_id}/progress":
                _json(route, progress)
            elif url.path == "/health":
                _json(route, {"active_runs": 0, "active_paid_operations": 0,
                              "max_concurrent": 5, "retention_days": 30})
            elif url.path == "/" or url.path.startswith("/static/"):
                route.continue_()
            else:
                unexpected.append(f"Unexpected path: {url.path}")
                route.abort()

        context.route("**/*", route_request)
        page = context.new_page()
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        try:
            page.goto(base)
            topic = page.locator("#topic")
            run = page.locator("#run-btn")
            expect(page.locator(".compose__sub")).to_contain_text("evidence gaps")
            expect(page.locator(".compose__sub")).not_to_contain_text("Every claim")
            topic.fill("Existing paper assessment topic")
            pdf = {"name": "first.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-fixture"}
            page.locator("#pdf-input").set_input_files(pdf)
            _wait_requests(page, requests, 1)
            expect(run).to_be_disabled()
            expect(page.locator("#attach-btn")).to_be_disabled()
            # Native drop/change and form events can arrive despite a disabled
            # button. Assert their network effect, not only its CSS/attribute.
            page.locator("#pdf-input").set_input_files({**pdf, "name": "overlapping.pdf"})
            page.locator("#compose-form").evaluate("form => form.requestSubmit()")
            page.wait_for_timeout(30)
            assert len(requests) == 1
            _json(requests[0], {"paper_id": "selected-paper", "title": "Selected paper",
                                "commercialization_topic": "Do not replace the existing topic"})
            expect(run).to_be_enabled()
            expect(topic).to_have_value("Existing paper assessment topic")
            expect(page.locator("#attachment")).to_contain_text("Selected paper")
            run.click()
            _wait_requests(page, requests, 2)
            assert requests[1].request.post_data_json["paper_id"] == "selected-paper"
            assert requests[1].request.post_data_json["topic"] == "Existing paper assessment topic"
            expect(topic).to_be_disabled()
            # Simulate already queued events, including the original input
            # event that used to overwrite the in-flight disabled state.
            topic.evaluate("el => { el.value = 'Queued input'; el.dispatchEvent(new Event('input')); }")
            page.locator("#compose-form").evaluate("form => form.requestSubmit()")
            run.evaluate("button => button.click()")
            page.wait_for_timeout(30)
            assert len(requests) == 2
            _json(requests[1], {"detail": "Daily fixture limit"}, status=429, code="daily_quota_exceeded")
            expect(page.locator("#toasts .toast").last).to_contain_text("00:00 UTC")
            expect(run).to_be_enabled()
            run.click()
            _wait_requests(page, requests, 3)
            _json(requests[2], {"run_id": run_id, "topic": progress["topic"], "state": "running"}, status=202)
            expect(page.locator("#run-title")).to_have_text(progress["topic"])
            expect(page.locator("#run-pill")).to_have_text("completed")
            assert requests[2].request.post_data_json["paper_id"] == "selected-paper"

            # A fresh compose document covers auto-fill, extraction failure,
            # translated copy, and correct operation-specific error feedback.
            page.goto(base)
            page.locator("#ui-lang").select_option("Simplified Chinese")
            expect(page.locator(".compose__sub")).to_contain_text("证据缺口")
            expect(page.locator(".compose__sub")).not_to_contain_text("每条结论")
            page.locator("#pdf-input").set_input_files(pdf)
            _wait_requests(page, requests, 4)
            _json(requests[3], {"paper_id": "autofilled", "title": "Auto-filled paper",
                                "commercialization_topic": "Auto-filled topic"})
            expect(topic).to_have_value("Auto-filled topic")
            expect(run).to_be_enabled()
            page.locator("#attach-btn").click()
            page.locator("#pdf-input").set_input_files(pdf)
            _wait_requests(page, requests, 5)
            _json(requests[4], {"detail": "Daily fixture limit"}, status=429, code="daily_quota_exceeded")
            expect(page.locator("#toasts .toast").last).to_contain_text("每日付费操作额度")
            expect(page.locator("#attachment")).to_be_hidden()
            expect(run).to_be_enabled()
            for code, expected in [("concurrency_limit", "并发已满"), ("rate_limited", "请求过于频繁")]:
                count = len(requests)
                run.click()
                _wait_requests(page, requests, count + 1)
                _json(requests[-1], {"detail": "Fixture limit"}, status=429, code=code)
                expect(page.locator("#toasts .toast").last).to_contain_text(expected)
                expect(run).to_be_enabled()
            assert not unexpected, unexpected
            assert not reached_server, reached_server
            assert not page_errors, page_errors
        except Exception:  # noqa: BLE001 - preserve diagnostic artifact, then propagate the real assertion
            _capture_failure(page)
            raise
        finally:
            context.close()
            browser.close()
    print(json.dumps({"status": "passed", "browser": "chromium", "stubbed_posts": len(requests),
                      "api_requests_reaching_server": len(reached_server), "unexpected_requests": len(unexpected),
                      "paid_provider_requests": 0, "page_errors": len(page_errors)}))


if __name__ == "__main__":
    main()
