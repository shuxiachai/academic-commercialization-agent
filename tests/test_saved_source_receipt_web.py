"""Shipped receipt scripts and real frozen fixtures, never provider requests."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource
from academic_agent.report_evidence_source_locator import locate_saved_source, render_locator_result

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "20260919T000000Z-" + "a" * 32
SCENARIOS = ["domain", "malformed", "inputs", "lifecycle", "storage", "recovery", "errors", "bounds", "timeout", "acknowledge"]


def browser_fixtures():
    """Frozen serializer supplies exact Unicode and domain results, not fake JSON."""
    prefix = '  前🙂 e\u0301\t\r\n<img src=x onerror="alert(1)"> **not markdown**\n\x7f'
    suffix = "\nEXACT_TAIL  \t"
    text = prefix + "界" * (1500 - len(prefix) - len(suffix)) + suffix

    def result(summary, *, count=1, reply=None, question="Find the source"):
        snapshot = ReportEvidenceSnapshot(report_ref=RUN_ID, sources=tuple(
            SnapshotSource(
                source_id=f"A{index + 1}", group="academic", title="<script>inert()</script> 保存标题",
                publisher="Publisher\n<img src=x>", source_type="academic", url="javascript:alert(1)",
                doi=None, published_date="1899-01-02", accessed_date="2026-09-19",
                summary=summary, origin="abstract",
            ) for index in range(count)
        ))
        selection = {"role": "assistant", "content": None, "tool_calls": [{
            "id": "scripted-ui", "type": "function", "function": {"name": "read_source", "arguments": '{"source_id":"A1"}'},
        }]}

        def select(_):
            if reply == "error":
                raise ValueError("PRIVATE callback failure")
            return selection if reply is None else reply

        return json.loads(render_locator_result(locate_saved_source(snapshot, question, selector=select)))

    return {
        "run_id": RUN_ID,
        "results": {
            "excerpt": result(text), "missing_text": result(None), "empty_text": result(""),
            "blank_text": result(" \t\r\n\u0085\u001c\u3000"),
            "declined": result("saved", reply={"role": "assistant", "content": '{"action":"decline"}'}),
            "refused": result("saved", reply={"role": "assistant", "content": None, "refusal": "No"}),
            "out_of_scope": result("x" * 1501), "no_sources": result(None, count=0),
            "budget": result("saved", question="🙂" * 4096), "partial": result("saved", count=33),
            "failed": result("saved", reply={"bad": "PRIVATE"}), "unavailable": result("saved", reply="error"),
        },
    }


def run_node(scenario, fixtures):
    node = shutil.which("node")
    assert node, "Node is required; receipt browser contracts must not be skipped"
    completed = subprocess.run(
        [node, str(ROOT / "tests/js/saved_source_receipt_contract.mjs"), scenario],
        input=json.dumps(fixtures, ensure_ascii=True), capture_output=True, text=True,
        encoding="utf-8", cwd=ROOT, timeout=45,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    observed = json.loads(completed.stdout)
    assert observed["scenario"] == scenario and observed["passed"] is True and observed["cases"] > 0
    return observed


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_saved_source_receipt_shipped_contract(scenario):
    """Lost/stale acknowledgements must retain the key and cannot unlock paid intent."""
    run_node(scenario, browser_fixtures())


def test_actual_receipt_http_payload_reaches_browser(tmp_path, monkeypatch):
    """Real ASGI/controller/journal replays reach exact text without another charge."""
    from fastapi.testclient import TestClient

    from academic_agent.saved_source_loader import SavedSourceLoader
    from api import access, runs
    from api.saved_source_receipt_app import create_saved_source_receipt_app

    code = "synthetic-receipt-browser-code"
    for name, value in {"DEFAULT_OUTPUT_ROOT": tmp_path, "_registry": {}, "_stop_claims": {},
                        "_inline_paid_operations": {}, "_daily_counts": {}, "_daily_date": None,
                        "MAX_CONCURRENT": 1, "DAILY_CAP": 10}.items():
        monkeypatch.setattr(runs, name, value)
    monkeypatch.setattr(access, "ACCESS_CODE", code)
    monkeypatch.setattr(access, "ACCESS_CODES", None)
    monkeypatch.setattr(access, "ADMIN_CODE", None)
    fixtures = browser_fixtures()
    text = fixtures["results"]["excerpt"]["saved_text"]["text"]
    folder = tmp_path / RUN_ID
    folder.mkdir()
    (folder / ".owner").write_text(access.owner_id(code), encoding="utf-8")
    (folder / "validated_sources.json").write_text(json.dumps({"academic_sources": [{
        "source_id": "A1", "title": "Synthetic title", "publisher": "Synthetic publisher",
        "source_type": "academic", "url": "javascript:alert(1)", "doi": None,
        "published_date": "1899-01-02", "accessed_date": "2026-09-19",
        "evidence_summary": text, "summary_source": "abstract",
    }], "patent_sources": [], "market_sources": []}), encoding="utf-8")
    calls = []

    def select(request):
        calls.append(request)
        return {"role": "assistant", "content": None, "tool_calls": [{
            "id": "test-only", "type": "function", "function": {"name": "read_source", "arguments": '{"source_id":"A1"}'},
        }]}

    # TestClient is in-process, but Windows asyncio creates loopback self-pipes.
    # Permit only those local sockets; all external/provider paths still fail.
    import socket
    from unittest.mock import Mock

    monkeypatch.setattr(socket, "create_connection", Mock(side_effect=AssertionError("No provider network")))
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_lookup = socket.getaddrinfo

    def check(host):
        assert host in {"127.0.0.1", "::1", "localhost", None}, "No external/provider network"

    def connect(sock, address):
        check(address[0] if isinstance(address, tuple) else address)
        return original_connect(sock, address)

    def connect_ex(sock, address):
        check(address[0] if isinstance(address, tuple) else address)
        return original_connect_ex(sock, address)

    def lookup(host, *args, **kwargs):
        check(host)
        return original_lookup(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", lookup)
    import time

    key = f"v1.{int(time.time())}." + "1" * 64
    headers = {"Idempotency-Key": key, "X-Access-Code": code}
    app = create_saved_source_receipt_app(load_snapshot=SavedSourceLoader(tmp_path), journal_root=tmp_path,
                                          selector=select, selector_identity="scripted-browser-test-v1")
    with TestClient(app) as client:
        first = client.post(f"/api/runs/{RUN_ID}/saved-source-location", json={"question": " original 🙂 "}, headers=headers)
        assert first.status_code == 200
        replay = client.get("/api/saved-source-receipts", headers=headers)
        assert replay.status_code == 200
        payload = replay.json()
        assert payload["result"] == first.json()["result"]
        assert payload["receipt_key_sha256"] == hashlib.sha256(key.encode()).hexdigest()
        assert payload["delivery_snapshot_reads"] == payload["delivery_source_reads"] == 1
        assert payload["result"]["saved_text"]["text"] == text
        assert len(calls) == runs._daily_counts[access.owner_id(code)] == 1
        fixtures["actual_reply"] = payload
        run_node("actual", fixtures)
    assert runs.active_paid_operation_count() == 0


if __name__ == "__main__":
    # Direct Node-first execution avoids pytest's global production-app fixture.
    sys.stdout.write(json.dumps(browser_fixtures(), ensure_ascii=True))
