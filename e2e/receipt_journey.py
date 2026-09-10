"""Refresh-to-receipt journeys through shipped DOM and HTTP client.

The parent smoke supplies a static-only loopback server. Intercepted POSTs
never reach an API or provider; the lost reply is deliberately not retried.
"""

from urllib.parse import urlsplit

from playwright.sync_api import expect

from e2e.browser_smoke import PROJECT_ROOT


def receipt_journey(browser, base, operation, fulfill):
    context = browser.new_context()
    context.add_init_script("localStorage.setItem('access-code','receipt-fixture-code')")
    page = context.new_page()
    faults, posts, lookups = [], [], []
    parent = "20260910T000000Z-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    child = "20260910T000001Z-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    paper_id = "paper-cccccccccccccccccccccccccccccccc"
    accepted = ({"paper_id": paper_id, "title": "Recovered fixture paper", "commercialization_topic": "Recovered paper topic"}
                if operation == "paper" else {"run_id": child, "topic": "Recovered fixture assessment"})

    def intercept(route):
        request = route.request
        url = urlsplit(request.url)
        if url.netloc != urlsplit(base).netloc:
            faults.append("External request")
            route.abort()
        elif request.method == "POST" and url.path in {"/api/runs", "/api/papers", f"/api/runs/{parent}/resume"}:
            posts.append(route)
        elif request.method != "GET":
            faults.append(f"Unexpected method: {request.method}")
            route.abort()
        elif url.path == "/api/receipts":
            lookups.append(route)
            assert request.headers["idempotency-key"] == posts[0].request.headers["idempotency-key"]
            assert request.headers["x-access-code"] == "receipt-fixture-code"
            assert not url.query
            fulfill(route, {"operation": operation, "state": "accepted", "response": accepted,
                "resource_id": paper_id if operation == "paper" else child,
                "status_code": 200 if operation == "paper" else 202})
        elif url.path == "/api/access/check":
            fulfill(route, {"ok": request.headers.get("x-access-code") == "receipt-fixture-code"})
        elif url.path == "/api/runs":
            fulfill(route, {"runs": []})
        elif url.path == "/health":
            fulfill(route, {"active_runs": 0, "max_concurrent": 5})
        elif url.path in {f"/api/runs/{parent}/progress", f"/api/runs/{child}/progress"}:
            is_parent = url.path.endswith(f"{parent}/progress")
            fulfill(route, {"run_id": parent if is_parent else child, "topic": "Receipt fixture",
                "state": "failed" if is_parent else "completed", "stage": "Done", "steps": [],
                "artifacts": [], "elapsed_seconds": 0,
                "checkpointing": {"committed_nodes": ["retrieval"]} if is_parent else None})
        elif url.path.startswith("/run/"):
            route.fulfill(path=str(PROJECT_ROOT / "web/index.html"), content_type="text/html")
        elif url.path == "/" or url.path.startswith("/static/"):
            route.continue_()
        else:
            faults.append(url.path)
            route.abort()

    context.route("**/*", intercept)
    page.on("pageerror", lambda error: faults.append(str(error)))
    page.on("dialog", lambda dialog: dialog.accept())
    try:
        page.goto(f"{base}/run/{parent}" if operation == "resume" else base)
        expect(page.locator("#code-badge")).to_be_visible()
        with page.expect_request(lambda request: request.method == "POST"):
            if operation == "resume":
                page.locator("[data-resume-run]").click()
            elif operation == "paper":
                page.locator("#pdf-input").set_input_files({"name": "receipt.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-offline"})
            else:
                page.locator("#topic").fill("Offline receipt recovery")
                page.locator("#run-btn").click()
        expect(page.locator("#paid-receipt-lookup")).to_be_visible()
        assert len(posts) == 1
        saved = page.evaluate("JSON.parse(sessionStorage.getItem('paid-receipt-keys-v1'))")
        assert saved == [{"key": posts[0].request.headers["idempotency-key"], "operation": operation}]
        page.reload()
        posts[0].abort()
        expect(page.locator("#paid-receipt-message")).to_contain_text("unconfirmed outcome")
        page.locator("#paid-receipt-lookup").click()
        open_result = page.locator("#paid-receipt-results button")
        expect(open_result).to_have_count(1)
        open_result.click()
        if operation == "paper":
            expect(page.locator("#attachment")).to_contain_text("Recovered fixture paper")
        else:
            expect(page).to_have_url(f"{base}/run/{child}")
        expect(page.locator("#paid-receipt-lookup")).to_be_hidden()
        assert page.evaluate("sessionStorage.getItem('paid-receipt-keys-v1')") is None
        assert len(posts) == len(lookups) == 1, "Receipt recovery must never repeat paid intent"
        assert not faults, faults
        return len(posts)
    finally:
        context.close()
