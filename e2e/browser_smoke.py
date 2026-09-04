"""Real-browser smoke test for the public web/API seam, with no paid work.

This deliberately is not a pytest module. The ordinary suite is zero-network
and runs in every OS/Python matrix cell; making it discover this file would
either install Chromium four times or turn a missing browser into a skip. A
single dedicated CI job owns this heavier contract instead.

The fixture is a completed run written directly to an isolated output root.
The browser may only issue GET/HEAD/OPTIONS requests to the loopback server.
That makes the zero-provider claim structural: even a future UI regression
that tries to submit a run is aborted and reported, rather than spending a
credential that happened to be present in the CI or developer environment.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

import uvicorn
from playwright.sync_api import Page, Response, Route, expect, sync_playwright

from academic_agent.run_output import create_run_id
from academic_agent.run_terminal import (
    TerminalRecord,
    UsageAccounting,
    commit_terminal_record,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = PROJECT_ROOT / "output" / "playwright"
ACCESS_CODE = "browser-smoke-code"
FIXTURE_TOPIC = "Browser smoke fixture for evidence-constrained commercialization"
REPORT_SENTINEL = "BROWSER_SMOKE_REPORT_REACHED_CLIENT"


def _configure_isolated_app(output_root: Path):
    """Return the production ASGI app with process-local test boundaries.

    Environment variables are set before importing the API modules because
    CrewAI loads ``.env`` as an import side effect. ``load_dotenv`` does not
    overwrite existing values, so setting the smoke code first prevents a
    developer's real deployment code from becoming part of this test.
    """
    # The current read-only journey never starts run telemetry, but explicitly
    # disable both the project opt-in and the SDK before importing FastAPI. A
    # future trace added to a read endpoint must not turn this loopback smoke
    # into an unnoticed Phoenix export merely because a developer has real
    # collector credentials in the parent environment.
    os.environ["AGENT_OBSERVABILITY_ENABLED"] = "false"
    os.environ["OTEL_SDK_DISABLED"] = "true"
    os.environ["ACCESS_CODE"] = ACCESS_CODE
    os.environ.pop("ACCESS_CODES", None)
    os.environ.pop("ACCESS_CODE_ADMIN", None)

    from api import access, runs

    # Repeat the assignment at the module boundary. This is intentional rather
    # than redundant: another imported module may already have loaded access.py
    # in an interactive developer process before this function is called.
    access.ACCESS_CODE = ACCESS_CODE
    access.ACCESS_CODES = None
    access.ADMIN_CODE = None
    runs.DEFAULT_OUTPUT_ROOT = output_root

    from api.main import app

    return app, access


def _write_completed_run(output_root: Path, owner: str) -> str:
    """Create the smallest real on-disk run contract the browser can read."""
    run_id = create_run_id()
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True)
    (run_dir / ".owner").write_text(owner, encoding="utf-8")
    (run_dir / "status.json").write_text(
        json.dumps(
            {
                "done": True,
                "stage": "Done",
                "topic": FIXTURE_TOPIC,
                "output_language": "English",
                "source_counts": {"academic": 3, "patent": 2, "market": 4},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (run_dir / "commercialization_report.md").write_text(
        "# Browser smoke report\n\n"
        f"{REPORT_SENTINEL}\n\n"
        "This report is a local fixture; no model or search provider produced it.\n",
        encoding="utf-8",
    )
    # A report plus ``done=true`` exercises only the historical fallback path.
    # Commit the current immutable record as well so this browser job covers
    # the complete disk -> FastAPI projection -> JavaScript -> DOM seam that a
    # paid run uses. The explicit zero snapshot means "observed zero calls";
    # None would mean accounting failed and is invalid for a completed run.
    started_at = datetime.now(UTC).replace(microsecond=0)
    ended_at = started_at + timedelta(seconds=7)
    accounting = UsageAccounting(
        state="complete",
        snapshot_at=ended_at,
        through_stage="Done",
        run_complete=True,
        in_flight_request_may_have_spent=False,
    )
    commit_terminal_record(
        run_dir,
        TerminalRecord(
            state="completed",
            reason_code="worker_completed",
            termination_method="worker_exit",
            started_at=started_at,
            ended_at=ended_at,
            elapsed_seconds=7,
            last_stage="Done",
            timeout_seconds=1800,
            usage={
                "total_tokens": 0,
                "cost_usd": 0.0,
                "cost_complete": True,
                "agents": [],
            },
            usage_accounting=accounting,
        ),
    )
    return run_id


@contextmanager
def _serve(app):
    """Serve the real ASGI app on an OS-assigned loopback port.

    Passing a pre-bound socket removes the usual ``find free port, close it,
    bind later`` race. It matters in CI, where unrelated jobs can claim a port
    between those two operations and make a healthy browser contract flaky.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]

    config = uvicorn.Config(app, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [sock]},
        name="browser-smoke-uvicorn",
        daemon=True,
    )
    thread.start()

    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
        raise RuntimeError("The local ASGI server did not start within 10 seconds.")

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        if thread.is_alive():
            raise RuntimeError("The local ASGI server did not stop cleanly.")


def _capture_failure(page: Page | None) -> None:
    """Keep one inspectable browser artifact without dirtying successful runs."""
    if page is None or page.is_closed():
        return
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=ARTIFACT_ROOT / "browser-smoke-failure.png", full_page=True)
    except Exception as exc:  # noqa: BLE001 - diagnostics must not replace the original failure
        print(
            f"[browser-smoke] failure screenshot unavailable: {type(exc).__name__}",
            file=sys.stderr,
        )


def _exercise_browser(base_url: str, run_id: str) -> dict[str, int]:
    external_requests: list[str] = []
    mutation_attempts: list[str] = []
    console_errors: list[str] = []
    unexpected_console_errors: list[str] = []
    http_failures: list[tuple[str, str, int]] = []
    page_errors: list[str] = []
    page: Page | None = None

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()

        def guard_route(route: Route) -> None:
            request = route.request
            parsed = urlsplit(request.url)
            if parsed.hostname not in {"127.0.0.1", "localhost"}:
                external_requests.append(f"{request.method} {request.url}")
                route.abort("blockedbyclient")
                return
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                mutation_attempts.append(f"{request.method} {parsed.path}")
                route.abort("blockedbyclient")
                return
            route.continue_()

        def record_response(response: Response) -> None:
            if response.status >= 400:
                request = response.request
                http_failures.append(
                    (request.method, urlsplit(response.url).path, response.status)
                )

        context.route("**/*", guard_route)
        page = context.new_page()
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.on("response", record_response)
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        try:
            response = page.goto(base_url, wait_until="domcontentloaded")
            assert response is not None and response.ok, "The SPA entry point did not load."
            csp = response.headers.get("content-security-policy", "")
            assert "default-src 'self'" in csp, "The browser response lost its CSP boundary."

            gate = page.locator("#gate")
            expect(gate).to_be_visible()

            page.locator("#gate-input").fill("wrong-browser-smoke-code")
            page.locator("#gate-submit").click()
            expect(page.locator("#gate-error")).to_be_visible()
            expect(gate).to_be_visible()

            page.locator("#gate-input").fill(ACCESS_CODE)
            page.locator("#gate-submit").click()
            expect(gate).to_be_hidden()

            run_item = page.locator(f'button.runitem[data-run-id="{run_id}"]')
            expect(run_item).to_be_visible()
            expect(run_item).to_contain_text(FIXTURE_TOPIC)

            # Exercise local admission UX without submitting. A two-character
            # value must remain disabled; a scoped topic enables the control.
            # The route guard below would still block the POST if a later UI
            # change accidentally submitted during either assertion.
            run_button = page.locator("#run-btn")
            expect(run_button).to_be_disabled()
            page.locator("#topic").fill("ab")
            expect(run_button).to_be_disabled()
            page.locator("#topic").fill(
                "Quantum sensor arrays for industrial predictive maintenance"
            )
            expect(run_button).to_be_enabled()

            run_item.click()
            expect(page).to_have_url(f"{base_url}/run/{run_id}")
            expect(page.locator("#run-title")).to_have_text(FIXTURE_TOPIC)
            expect(page.locator("#run-pill")).to_have_text("completed")
            terminal = page.locator("#run-terminal")
            expect(terminal).to_have_text("· worker completed")
            expect(terminal).to_have_attribute(
                "title",
                "Reason: worker_completed\nTermination: worker_exit",
            )
            expect(page.locator("article.prose")).to_contain_text(REPORT_SENTINEL)

            # A direct route is a separate seam from client-side navigation.
            # Reloading proves the server returns the SPA at /run/{id}, the
            # stored code re-authorizes, and the report reaches the DOM again.
            page.reload(wait_until="domcontentloaded")
            expect(page.locator("#run-terminal")).to_have_text("· worker completed")
            expect(page.locator("article.prose")).to_contain_text(REPORT_SENTINEL)

            assert not external_requests, (
                "The browser attempted non-loopback requests: "
                + ", ".join(external_requests)
            )
            assert not mutation_attempts, (
                "The zero-paid smoke attempted a mutating request: "
                + ", ".join(mutation_attempts)
            )

            # The gate intentionally exercises two rejected requests: the
            # boot-time probe without a code and the explicit wrong-code
            # attempt. Chromium projects each expected 401 into a generic
            # console error, so classify it against the precise HTTP response
            # instead of either treating the healthy gate as broken or
            # suppressing every browser error indiscriminately.
            expected_auth_failures = [
                ("GET", "/api/access/check", 401),
                ("GET", "/api/access/check", 401),
            ]
            assert http_failures == expected_auth_failures, (
                f"Unexpected HTTP failures: {http_failures!r}"
            )
            expected_401_console = (
                "Failed to load resource: the server responded with a status "
                "of 401 (Unauthorized)"
            )
            unexpected_console_errors[:] = [
                message for message in console_errors if message != expected_401_console
            ]
            assert len(console_errors) == len(expected_auth_failures)
            assert not unexpected_console_errors, (
                "Browser console errors: " + "; ".join(unexpected_console_errors)
            )
            assert not page_errors, "Uncaught page errors: " + "; ".join(page_errors)
        except Exception:  # noqa: BLE001 - preserve visual evidence for any browser/assertion failure
            _capture_failure(page)
            raise
        finally:
            context.close()
            browser.close()

    return {
        "external_requests": len(external_requests),
        "mutation_attempts": len(mutation_attempts),
        "expected_unauthorized_responses": len(http_failures),
        "console_errors": len(unexpected_console_errors),
        "page_errors": len(page_errors),
    }


def main() -> None:
    with TemporaryDirectory(prefix=".browser-smoke-", dir=PROJECT_ROOT) as temp_dir:
        output_root = Path(temp_dir) / "outputs"
        app, access = _configure_isolated_app(output_root)
        run_id = _write_completed_run(output_root, access.owner_id(ACCESS_CODE))
        with _serve(app) as base_url:
            audit = _exercise_browser(base_url, run_id)

    print(
        json.dumps(
            {
                "status": "passed",
                "browser": "chromium",
                "paid_provider_requests": 0,
                **audit,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
