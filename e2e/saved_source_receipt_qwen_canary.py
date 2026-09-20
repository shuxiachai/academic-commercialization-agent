"""Actual RQ Chromium journey; this CLI ONLY runs intercepted offline rehearsal.

The parent-only runner calls browser_batch(live=True) after its separate gates.
Importing this module neither imports Playwright/app globals nor opens sockets.
The old zero-provider smoke guards and all shipped app assets remain unchanged.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack, contextmanager
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
from tempfile import TemporaryDirectory
import threading
from time import monotonic, sleep
from unittest.mock import patch
from urllib.parse import urlsplit

from academic_agent import saved_source_receipt_qwen_canary as runner
from academic_agent.report_evidence_qwen_canary import ENDPOINT, CanaryStopped, _encoded

STORAGE = "saved-source-receipts:v1"
HOST = "dashscope.aliyuncs.com"
FAKE_KEY = "sk-rq-offline-fake-never-live"
GUARDS = """
    globalThis.__rqForbidden = [];
    for (const name of ['localStorage', 'indexedDB']) {
      Object.defineProperty(window, name, {get() {
        __rqForbidden.push(name); throw Error('Forbidden persistence');
      }});
    }
    navigator.sendBeacon = () => { __rqForbidden.push('beacon'); throw Error('Forbidden telemetry'); };
"""


@contextmanager
def network_guard(*, live):
    """Narrow DNS/IP/port/TLS guard, not an OS sandbox or binary attestation.

    Offline rehearsal permits only loopback; native mode additionally admits
    the exact pinned host's globally routable DNS answers on port 443. HTTPS
    verification and SNI remain required. No arbitrary proxy/DNS host is allowed.
    """
    faults, addresses = [], set()
    original_lookup = socket.getaddrinfo
    original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex
    original_bio, original_wrap = ssl.SSLContext.wrap_bio, ssl.SSLContext.wrap_socket

    def host_text(host):
        return host.decode("ascii") if isinstance(host, bytes) else host

    def reject():
        faults.append("network_boundary_failed")
        raise CanaryStopped("network_boundary_failed")

    def loopback(host):
        return host in {"127.0.0.1", "::1", "localhost", None}

    def lookup(host, port, *args, **kwargs):
        host = host_text(host)
        if loopback(host):
            return original_lookup(host, port, *args, **kwargs)
        if not live or host != HOST or port != 443:
            reject()
        values = original_lookup(host, port, *args, **kwargs)
        for value in values:
            address = value[4][0]
            if not ipaddress.ip_address(address).is_global:
                reject()
            addresses.add(address)
        return values

    def check(address):
        if not isinstance(address, tuple) or len(address) < 2:
            reject()
        host, port = host_text(address[0]), address[1]
        if loopback(host):
            return
        if not live or host not in addresses or port != 443:
            reject()

    def connect(sock, address):
        check(address)
        return original_connect(sock, address)

    def connect_ex(sock, address):
        check(address)
        return original_connect_ex(sock, address)

    def tls(context, kwargs):
        if (not live or kwargs.get("server_hostname") != HOST or kwargs.get("server_side", False)
                or context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname):
            reject()

    def wrap_bio(context, *args, **kwargs):
        tls(context, kwargs)
        return original_bio(context, *args, **kwargs)

    def wrap_socket(context, *args, **kwargs):
        tls(context, kwargs)
        return original_wrap(context, *args, **kwargs)

    with ExitStack() as stack:
        for target, name, value in ((socket, "getaddrinfo", lookup),
                                    (socket.socket, "connect", connect), (socket.socket, "connect_ex", connect_ex),
                                    (ssl.SSLContext, "wrap_bio", wrap_bio), (ssl.SSLContext, "wrap_socket", wrap_socket)):
            stack.enter_context(patch.object(target, name, value))
        yield faults


@contextmanager
def serve(app):
    """Own the entire current app lifespan; shutdown drains actual controller threads."""
    import uvicorn

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False, lifespan="on"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=False)
    thread.start()
    try:
        deadline = monotonic() + 15
        while not server.started and thread.is_alive() and monotonic() < deadline:
            sleep(0.01)
        runner.require(server.started, "browser_runtime_failed")
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        server.should_exit = True
        # No timeout is interpreted as physical exit. A stuck trusted callback
        # may block shutdown; neither its lease nor accounting may be reset.
        thread.join()
        sock.close()


def journey(browser, base, case, execution, batch, owner):
    from playwright.sync_api import expect

    context = browser.new_context(service_workers="block")
    context.add_init_script(GUARDS)
    page = context.new_page()
    page.set_default_timeout(15000)
    faults, posts, gets = [], [], []
    page.on("pageerror", lambda _error: faults.append("browser_delivery_failed"))
    receipt_key = None
    static = {"/", "/receipt-static/app.js", "/receipt-static/result.js", "/receipt-static/app.css"}

    def routed(route):
        nonlocal receipt_key
        try:
            request, url = route.request, urlsplit(route.request.url)
            runner.require((url.scheme, url.netloc) == ("http", urlsplit(base).netloc)
                           and not url.query and not url.fragment, "network_boundary_failed")
            if request.method == "GET" and url.path in static:
                upstream = route.fetch(max_redirects=0, max_retries=0)
                runner.require(upstream.status == 200, "browser_delivery_failed")
                route.fulfill(response=upstream)
                return
            is_post = request.method == "POST" and url.path == f"/api/runs/{case['run_id']}/saved-source-location"
            is_get = request.method == "GET" and url.path == "/api/saved-source-receipts"
            runner.require(is_post or is_get, "network_boundary_failed")
            headers = request.all_headers()
            runner.require(headers.get("x-access-code") == runner.CODE
                           and not {"authorization", "cookie"}.intersection(headers), "http_contract_failed")
            key = headers["idempotency-key"]
            if is_post:
                runner.require(not posts and not gets and request.post_data_json == {"question": case["question"]},
                               "http_contract_failed")
                saved = page.evaluate("name => sessionStorage.getItem(name)", STORAGE)
                runner.require(json.loads(saved) == {"version": 1, "receipt_key": key}, "http_contract_failed")
                receipt_key = key
                batch.bind_http_intent(case["case_id"], runner.digest(key.encode("ascii")), owner)
            else:
                runner.require(len(posts) == 1 and not gets and key == receipt_key, "replay_failed")
            # This fetch traverses the real loopback HTTP factory/controller.
            # Explicitly disable both redirect following and connection retries.
            upstream = route.fetch(max_redirects=0, max_retries=0, timeout=180000)
            observation = {"status": upstream.status, "raw": upstream.body()}
            (posts if is_post else gets).append(observation)
            if is_post and case["case_id"] == "RQ01":
                route.abort()  # The upstream is done; only its browser acknowledgement is lost.
            else:
                route.fulfill(response=upstream)
        except Exception as exc:  # noqa: BLE001 -- never expose URLs, capabilities, codes or raw Playwright text.
            faults.append(runner.safe_reason(exc, "browser_delivery_failed"))
            route.abort()

    def websocket(ws):
        faults.append("network_boundary_failed")
        ws.close()

    context.route("**/*", routed)
    context.route_web_socket("**/*", websocket)
    try:
        page.goto(base, wait_until="networkidle")
        runner.require(not posts and not gets, "replay_failed")
        page.locator("#access-code").fill(runner.CODE)
        page.locator("#run-id").fill(case["run_id"])
        page.locator("#question").fill(case["question"])
        page.locator("#locate").click(timeout=180000)
        expect(page.locator("#locator-form")).to_have_attribute("aria-busy", "false", timeout=180000)
        runner.require(not faults and len(posts) == 1 and posts[0]["status"] == 200, "http_contract_failed")
        runner.require(batch.stop_reason is None, "native_audit_failed")
        if case["case_id"] == "RQ01":
            expect(page.locator("#request-status")).to_contain_text("服务端可能已经执行")
            expect(page.locator("#result")).to_be_hidden()
        else:
            expect(page.locator("#result")).to_be_visible()
        expect(page.locator("#locate")).to_be_disabled()
        callbacks_before = len(execution.callbacks)
        native_before = batch.summary()
        page.reload(wait_until="networkidle")
        runner.require(len(posts) == 1 and not gets, "replay_failed")
        for element in ("#access-code", "#run-id", "#question"):
            expect(page.locator(element)).to_have_value("")
        expect(page.locator("#recover")).to_be_disabled()
        expect(page.locator("#locate")).to_be_disabled()
        page.locator("#access-code").fill(runner.CODE)
        page.locator("#recover").click()
        expect(page.locator("#locator-form")).to_have_attribute("aria-busy", "false")
        runner.require(not faults and len(gets) == 1 and gets[0]["status"] == 200, "replay_failed")
        expect(page.locator("#result")).to_be_visible()
        expect(page.locator("#result b, #result script, #result img, #result a")).to_have_count(0)
        expect(page.locator("#receipt-context")).to_contain_text(case["run_id"])
        expect(page.locator("#receipt-context")).to_contain_text("原始问题未保存")
        expect(page.locator("#semantic-status")).to_contain_text("semantic_support: not_assessed")
        runner.require(page.evaluate("__rqForbidden") == [] and not faults
                       and len(execution.callbacks) == callbacks_before == 1
                       and batch.summary() == native_before, "replay_failed")
        checked = runner.audit_http(case, execution, posts[0]["raw"], gets[0]["raw"], receipt_key)
        # DOM is compared with both delivered result and frozen synthetic bytes;
        # normalization of CRLF, combining marks or non-BMP text cannot pass.
        delivered = checked["result"]["saved_text"]
        actual = page.locator("#saved-text").text_content()
        runner.require(actual == (delivered["text"] if delivered else ""), "browser_delivery_failed")
        checked.update(browser_delivery_passed=True, refresh_no_redispatch_passed=True,
                       post_requests=len(posts), get_requests=len(gets),
                       dom_text_sha256=runner.digest(actual.encode("utf-8")), dom_codepoints=len(actual))
        return checked
    finally:
        context.close()


def browser_batch(*, cases, bindings, batch, api_key, check_identity, live):
    """Shared native/rehearsal journey; no separate ASGI native pre-run exists."""
    from playwright.sync_api import sync_playwright
    from academic_agent.saved_source_receipt_qwen_adapter import BoundCaseSelector, atomic_write_once

    rows, browser_info = [], None
    failure = None
    started = monotonic()
    try:
        # This outer scope starts before Playwright's Node driver, not merely
        # before Chromium. It restores the parent key only after both drivers
        # and the actual operation threads have drained, including failures.
        with runner.without_provider_environment(), network_guard(live=live) as faults, runner.isolated_runtime(
                batch.output_dir / "synthetic_saved_sources", cases) as (loader, owner, runs):
            from api.saved_source_receipt_app import create_saved_source_receipt_app

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, args=["--disable-background-networking"])
                try:
                    browser_info = {"runtime_version": browser.version,
                                    "executable_path_sha256": runner.digest(playwright.chromium.executable_path.encode("utf-8")),
                                    "installed_package_version": runner.version("playwright"), "binary_attestation": False}
                    atomic_write_once(batch.output_dir / "browser-runtime.json", browser_info)
                    for case, binding in zip(cases, bindings, strict=True):
                        begin = monotonic()
                        outcome = {"case_id": case["case_id"], "status": "failed", "mechanical_passed": False,
                                   "reference_passed": None, "failure": None}
                        execution, checked, facts = None, None, None
                        published = False
                        try:
                            check_identity()
                            ledger = runner.native.LocatorQwenLedger(batch.output_dir / case["case_id"])
                            def case_identity(bound=binding):
                                check_identity()
                                runner.require(loader(bound.run_id) == bound.snapshot, "source_binding_failed")

                            selector = BoundCaseSelector(api_key, binding, batch, ledger, check_identity=case_identity)
                            execution = runner.CaseExecution(binding, selector, loader)
                            app = create_saved_source_receipt_app(
                                load_snapshot=execution.load, journal_root=batch.output_dir / "synthetic_saved_sources",
                                selector=execution.callback, selector_identity=binding.selector_identity)
                            before = loader(binding.run_id).snapshot_hash
                            admissions_before = runs._daily_counts.get(owner, 0)
                            try:
                                with execution.observe_reads(), serve(app) as base:
                                    checked = journey(browser, base, case, execution, batch, owner)
                            finally:
                                execution.drain()
                                # Check failure paths too; native usage is already retained by adapter finally.
                                check_identity()
                            after = loader(binding.run_id).snapshot_hash
                            batch.observe_native(case["case_id"], ledger)
                            checked["native_journal"] = runner.audit_native_journal(binding, ledger)
                            runner.require(not faults, "network_boundary_failed")
                            facts = {"run_id": binding.run_id, "receipt_key_sha256": checked["receipt_key_sha256"],
                                     "snapshot_sha256_before": before, "snapshot_sha256_after": after,
                                     "post_requests": checked["post_requests"], "get_requests": checked["get_requests"],
                                     "callback_entries": len(execution.callbacks),
                                     "daily_admissions": runs._daily_counts.get(owner, 0) - admissions_before,
                                     "active_paid_operations_after_drain": runs.active_paid_operation_count(),
                                     "physical_threads_after_drain": sum(thread.is_alive() for thread in execution.threads),
                                     "http_contract_passed": checked["mechanical_passed"],
                                     "reference_passed": checked["reference_passed"], "replay_passed": checked["replay_passed"],
                                     "browser_delivery_passed": checked["browser_delivery_passed"],
                                     "refresh_no_redispatch_passed": checked["refresh_no_redispatch_passed"],
                                     "source_identity_passed": True}
                            atomic_write_once(batch.output_dir / (case["case_id"] + "-result.json"), {
                                "scope": "private_synthetic_delivery_audit_not_public_summary", **checked, "facts": facts})
                            published = True
                            # Reference disagreement cannot erase successful mechanical
                            # observations. Freeze the safe audit BEFORE stopping.
                            runner.require(checked["reference_passed"], "reference_mismatch")
                            batch.complete_case(case["case_id"], facts)
                            outcome.update(status="passed", mechanical_passed=True, reference_passed=True)
                        except Exception as exc:  # noqa: BLE001 -- retain accounting, never arbitrary provider/UI details.
                            failure = runner.safe_reason(exc)
                            if checked:
                                outcome.update(mechanical_passed=checked["mechanical_passed"],
                                               reference_passed=checked["reference_passed"])
                                if not published:
                                    atomic_write_once(batch.output_dir / (case["case_id"] + "-result.json"), {
                                        "scope": "private_synthetic_delivery_audit_not_public_summary",
                                        **checked, "facts": facts, "later_failure": failure})
                            outcome["failure"] = failure
                            batch.stop(failure)
                        finally:
                            if execution is not None:
                                execution.drain()
                            outcome["elapsed_seconds"] = monotonic() - begin
                            rows.append(outcome)
                        if failure is not None:
                            break
                finally:
                    browser.close()
    except Exception as exc:  # noqa: BLE001 -- browser startup/storage/global-guard failures stop the same batch.
        failure = runner.safe_reason(exc, "browser_runtime_failed")
        batch.stop(failure)
    for case in cases[len(rows):]:
        rows.append({"case_id": case["case_id"], "status": "unrun", "mechanical_passed": None,
                     "reference_passed": None, "failure": None, "elapsed_seconds": None})
    native_summary = batch.summary()
    summary = {"protocol_identity": runner.PROTOCOL_IDENTITY,
               "mode": "native_browser" if live else "offline_intercepted_browser",
               "provider_calls": None if live else 0,
               "batch_passed": failure is None and all(row["status"] == "passed" for row in rows)
               and all(native_summary["case_gates"].values()) and native_summary["stop_reason"] is None
               and native_summary["unknown_usage_requests"] == 0 and not native_summary["pending_cases"],
               "failure": failure, "cases": rows,
               "mechanical_passed_cases": sum(row["mechanical_passed"] is True for row in rows),
               "reference_checks": sum(row["reference_passed"] is not None for row in rows),
               "reference_matches": sum(row["reference_passed"] is True for row in rows),
               "unrun_cases": [row["case_id"] for row in rows if row["status"] == "unrun"],
               "native_audit": native_summary, "browser_runtime": browser_info,
               "elapsed_seconds": monotonic() - started,
               "elapsed_scope": "browser_setup_cases_identity_drains_and_case_publication_not_provider_latency",
               "summary_persisted": True}
    atomic_write_once(batch.output_dir / "summary.json", summary)
    return summary


@contextmanager
def intercepted_native(cases, *, wrong_visible=False):
    """Actual pinned HTTP primitive, fake credential, deterministic response bytes."""
    import httpx

    requests = []

    def dispatch(request):
        runner.require(request.url == ENDPOINT and request.method == "POST"
                       and request.headers["authorization"] == "Bearer " + FAKE_KEY
                       and request.headers["accept-encoding"] == "identity", "native_audit_failed")
        body = json.loads(request.content)
        case = next(row for row in cases if row["question"] == body["messages"][1]["content"])
        requests.append(request)
        source_id = case["reference"]["source_id"]
        if wrong_visible and case["case_id"] == "RQ01":
            source_id = "A11"
        message = {"role": "assistant", "content": '{"action":"decline"}'}
        if source_id:
            message = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "rq-offline-call", "type": "function", "function": {
                    "name": "read_source", "arguments": json.dumps({"source_id": source_id})}}]}
        response = {"model": "qwen3.5-plus", "usage": {
            "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "tool_calls" if source_id else "stop"}]}
        return httpx.Response(200, stream=httpx.ByteStream(_encoded(response)))

    def transport(**kwargs):
        runner.require(kwargs == {"retries": 0, "verify": True, "trust_env": False}, "network_boundary_failed")
        return httpx.MockTransport(dispatch)

    with patch.object(httpx, "AsyncHTTPTransport", transport):
        yield requests


def rehearsal():
    from academic_agent.saved_source_receipt_qwen_adapter import BatchGate

    cases = runner.load_cases()
    bindings = runner.bindings_for(cases)
    with TemporaryDirectory(prefix="rq-browser-rehearsal-", dir=runner.ROOT / "outputs") as directory:
        batch = BatchGate(Path(directory) / "intercepted_batch", runner.batch_manifest(bindings, {
            "scope": "offline_intercepted_rehearsal_not_committed_identity"}))
        with offline_child_environment_probe() as children, intercepted_native(cases) as requests:
            result = browser_batch(cases=cases, bindings=bindings, batch=batch, api_key=FAKE_KEY,
                                   check_identity=lambda: None, live=False)
        runner.require(result["batch_passed"] and len(requests) == 2, "batch_failed")
        success_requests = len(requests)
        # A separate temporary offline control proves fail-stop retains delivery
        # facts. It never opens or retries the fixed native batch directory.
        fault_batch = BatchGate(Path(directory) / "wrong_visible_control", runner.batch_manifest(bindings, {
            "scope": "offline_fault_control_not_committed_identity"}))
        with offline_child_environment_probe() as fault_children, intercepted_native(cases, wrong_visible=True) as wrong_requests:
            wrong = browser_batch(cases=cases, bindings=bindings, batch=fault_batch, api_key=FAKE_KEY,
                                  check_identity=lambda: None, live=False)
        audit = json.loads((fault_batch.output_dir / "RQ01-result.json").read_text(encoding="utf-8"))
        runner.require(not wrong["batch_passed"] and wrong["failure"] == "reference_mismatch"
                       and wrong["unrun_cases"] == ["RQ02"] and len(wrong_requests) == 1
                       and audit["mechanical_passed"] is True and audit["reference_passed"] is False
                       and audit["result"]["source"]["source_id"] == "A11"
                       and audit["local_reads"] == audit["delivery_reads"]
                       and len(audit["local_reads"]) == 1 and audit["browser_delivery_passed"] is True
                       and all(len(audit[field]) == 64 for field in ("post_sha256", "get_sha256", "dom_text_sha256"))
                       and not (fault_batch.output_dir / "RQ02").exists(), "batch_failed")
        return {"marker": "RQ_OFFLINE_BROWSER_PASS", "cases": 2, "browser_posts": 2,
                "browser_gets": 2, "native_http_intercepts": success_requests, "provider_calls": 0,
                "actual_callback_entries": 2, "original_local_reads": 1, "replay_local_reads": 1,
                "key_free_driver_starts": children[0] + fault_children[0],
                "wrong_visible_control": {"cases": 1, "native_http_intercepts": len(wrong_requests),
                                          "retained_mechanical_audit": True, "RQ02": "unrun"},
                "browser_runtime": result["browser_runtime"]}


@contextmanager
def offline_child_environment_probe():
    """Inspect the actual driver spawn env using only a fake parent sentinel."""
    starts = [0]
    original = asyncio.create_subprocess_exec

    async def observed(*args, **kwargs):
        environment = kwargs.get("env", os.environ)
        runner.require("DASHSCOPE_API_KEY" not in environment, "browser_runtime_failed")
        starts[0] += 1
        return await original(*args, **kwargs)

    with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "sk-rq-fake-parent-env-sentinel"}), \
            patch.object(asyncio, "create_subprocess_exec", observed):
        yield starts
        runner.require(starts[0] == 1 and os.environ.get("DASHSCOPE_API_KEY") == "sk-rq-fake-parent-env-sentinel",
                       "browser_runtime_failed")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)  # No paid flag or external output override exists here.
    try:
        print(json.dumps(rehearsal(), ensure_ascii=True, sort_keys=True))
        return 0
    except Exception as exc:  # noqa: BLE001 -- never print provider/Playwright exceptions or credentials.
        print(json.dumps({"marker": "RQ_OFFLINE_BROWSER_FAILED", "provider_calls": 0,
                          "error": runner.safe_reason(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
