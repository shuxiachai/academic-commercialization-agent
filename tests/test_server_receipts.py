"""Paid acceptance must survive lost replies without a second dispatch."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api import access, main, papers, receipts, runs
from academic_agent.checkpoint_runtime import retrieval_identity
from academic_agent.checkpoints import CheckpointStore
from academic_agent.run_spec import RunSpec

_READ_ONLY_POPEN = subprocess.Popen


def request_key():
    return f"v1.{int(time.time())}.{secrets.token_hex(32)}"


@pytest.fixture
def paid_api(monkeypatch, tmp_path):
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(papers, "PAPERS_ROOT", tmp_path / "_papers")
    monkeypatch.setattr(access, "ACCESS_CODE", "offline-owner-a")
    monkeypatch.setattr(access, "ACCESS_CODES", "offline-owner-b")
    monkeypatch.setattr(access, "ADMIN_CODE", None)
    monkeypatch.setattr(runs, "_registry", {})
    monkeypatch.setattr(runs, "_daily_counts", {})
    monkeypatch.setattr(runs, "_daily_date", None)
    monkeypatch.setattr(runs, "_inline_paid_operations", {})
    monkeypatch.setattr(runs, "DAILY_CAP", 5)
    monkeypatch.setattr(runs, "MAX_CONCURRENT", 5)
    monkeypatch.setattr(main, "_rate_limit_exceeded", lambda _: False)
    process = MagicMock()
    process.poll.return_value = None
    launch = MagicMock(return_value=process)
    monkeypatch.setattr(runs.subprocess, "Popen", launch)
    client = TestClient(main.app)
    yield client, launch, tmp_path
    for handle in runs._registry.values():
        if handle.log_file:
            handle.log_file.close()
    client.close()


def test_lost_run_ack_replays_one_acceptance_and_one_charge(paid_api):
    """Discard the first real HTTP reply, repeat intent, count actual Popen."""
    client, launch, _ = paid_api
    headers = {"X-Access-Code": "offline-owner-a", "Idempotency-Key": request_key()}
    first = client.post("/api/runs", headers=headers, json={"topic": "Offline battery research"})
    second = client.post("/api/runs", headers=headers, json={"topic": "Offline battery research"})
    assert first.status_code == second.status_code == 202
    assert second.json() == first.json()
    assert launch.call_count == 1
    assert sum(runs._daily_counts.values()) == 1


def headers(key=None, code="offline-owner-a"):
    return {"Idempotency-Key": key or request_key(), **({"X-Access-Code": code} if code else {})}


@pytest.mark.parametrize("change", [{"topic": "Another topic"}, {"language": "English"},
                                    {"weight_profile": "clean_tech"}, {"paper_id": "changed-paper"}])
def test_changed_normalized_input_cannot_reuse_key(paid_api, change):
    client, launch, _ = paid_api
    auth = headers()
    client.post("/api/runs", headers=auth, json={"topic": "Original topic"})
    result = client.post("/api/runs", headers=auth, json={"topic": "Original topic", **change})
    assert result.status_code == 409 and result.headers["x-error-code"] == "receipt_conflict"
    assert launch.call_count == 1


@pytest.mark.parametrize("code", [None, "offline-owner-b"])
def test_receipt_lookup_does_not_leak_another_owners_result(paid_api, code, monkeypatch):
    client, launch, _ = paid_api
    key = request_key()
    original = client.post("/api/runs", headers=headers(key), json={"topic": "Private topic"})
    denied = client.get("/api/receipts", headers=headers(key, code))
    assert denied.status_code == 404
    assert "Private topic" not in denied.text and original.json()["run_id"] not in denied.text
    # Turning off the global gate must not erase the recorded owner boundary.
    monkeypatch.setattr(access, "ACCESS_CODE", None)
    monkeypatch.setattr(access, "ACCESS_CODES", None)
    assert client.get("/api/receipts", headers=headers(key, None)).status_code == 404
    assert launch.call_count == 1


def test_byok_fingerprint_has_no_plain_credentials_and_lookup_is_capability_based(paid_api):
    client, launch, root = paid_api
    auth = headers(code=None)
    payload = {"topic": "Private BYOK input", "llm_provider": "qwen",
               "llm_api_key": "offline-llm-secret", "serper_api_key": "offline-search-secret"}
    first = client.post("/api/runs", headers=auth, json=payload)
    assert first.status_code == 202
    assert client.post("/api/runs", headers=auth, json=payload).json() == first.json()
    wrong = client.post("/api/runs", headers=auth, json={**payload, "llm_api_key": "different-key"})
    assert wrong.status_code == 409
    receipt = client.get("/api/receipts", headers=auth)
    assert receipt.status_code == 200 and receipt.json()["response"] == first.json()
    assert receipt.headers["cache-control"] == "no-store"
    raw = (root / ".paid-receipts.sqlite3").read_bytes()
    for secret in [payload["llm_api_key"], payload["serper_api_key"], auth["Idempotency-Key"]]:
        assert secret.encode() not in raw
    assert launch.call_count == 1 and sum(runs._daily_counts.values()) == 0


def test_pending_duplicate_is_rejected_while_first_popen_is_in_flight(paid_api):
    client, launch, _ = paid_api
    started, release = threading.Event(), threading.Event()
    process = launch.return_value
    def blocked(*_args, **_kwargs):
        started.set()
        assert release.wait(5)
        return process
    launch.side_effect = blocked
    auth = headers()
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(client.post, "/api/runs", headers=auth, json={"topic": "Concurrent topic"})
        try:
            assert started.wait(3)
            second = client.post("/api/runs", headers=auth, json={"topic": "Concurrent topic"})
            assert second.status_code == 409
            assert second.headers["x-error-code"] == "paid_receipt_pending"
            pending = client.get("/api/receipts", headers=auth).json()
            assert pending["state"] == "pending" and pending["resource_id"]
        finally:
            release.set()
        accepted = first.result(timeout=5)
    assert accepted.status_code == 202
    assert pending["resource_id"] == accepted.json()["run_id"]
    assert launch.call_count == 1 and sum(runs._daily_counts.values()) == 1


def test_lost_commit_after_launch_keeps_durable_pointer_without_second_worker(paid_api, monkeypatch):
    client, launch, root = paid_api
    auth = headers()
    with monkeypatch.context() as fault:
        fault.setattr(receipts.Ticket, "finish", MagicMock(side_effect=receipts.ReceiptError(503, "receipt_unavailable", "unavailable")))
        assert client.post("/api/runs", headers=auth, json={"topic": "Crash boundary"}).status_code == 503
    # A different Python process reads persisted bytes, not an in-memory cache.
    script = "import json,sys; from pathlib import Path; from api.receipts import lookup,public_record; print(json.dumps(public_record(lookup(Path(sys.argv[1]),sys.argv[2],sys.argv[3]))))"
    with monkeypatch.context() as reader:
        # Restore Popen only for this stdlib-only receipt reader, not for any
        # HTTP worker path. Patching runs.subprocess affects the shared module.
        reader.setattr(subprocess, "Popen", _READ_ONLY_POPEN)
        result = subprocess.run([sys.executable, "-c", script, str(root), auth["Idempotency-Key"], access.owner_id("offline-owner-a")],
                                capture_output=True, text=True, check=True, timeout=10)
    saved = json.loads(result.stdout)
    assert saved["state"] == "unknown" and saved["resource_id"] in runs._registry
    duplicate = client.post("/api/runs", headers=auth, json={"topic": "Crash boundary"})
    assert duplicate.status_code == 409 and launch.call_count == 1


def test_resumed_child_receipt_never_starts_a_second_recovery(paid_api):
    client, launch, root = paid_api
    parent = runs.create_run_id()
    directory = root / parent
    directory.mkdir()
    spec = RunSpec(topic="Offline recovery topic")
    spec.save(directory)
    (directory / "status.json").write_text(json.dumps({"done": True, "error": "offline failure"}))
    (directory / ".owner").write_text(access.owner_id("offline-owner-a"))
    CheckpointStore(directory).commit(retrieval_identity(spec, revision="offline-revision", as_of_date=date(2026, 9, 10)),
                                      json.dumps({"topic": spec.topic}), output_format="json")
    auth = headers()
    first = client.post(f"/api/runs/{parent}/resume", headers=auth, json={})
    duplicate = client.post(f"/api/runs/{parent}/resume", headers=auth, json={})
    assert first.status_code == duplicate.status_code == 202
    assert first.json() == duplicate.json()
    assert first.json()["resumed_from"] == parent
    assert client.get("/api/receipts", headers=auth).json()["operation"] == "resume"
    assert launch.call_count == 1 and sum(runs._daily_counts.values()) == 1


def contribution():
    return main.PaperContribution(title="Offline private paper", core_contribution="x" * 25,
        application_domain="energy storage", delta_from_prior="y" * 15,
        commercialization_topic="Offline private topic", search_keywords=["a", "b", "c"])


def test_paper_replay_and_lookup_preserve_result_without_second_extraction(paid_api, monkeypatch):
    client, launch, root = paid_api
    extractor = MagicMock(return_value=contribution())
    monkeypatch.setattr(main, "extract_paper_contribution", extractor)
    auth = headers()
    files = {"file": ("private.pdf", b"%PDF-offline", "application/pdf")}
    first = client.post("/api/papers", headers=auth, files=files)
    duplicate = client.post("/api/papers", headers=auth, files=files)
    assert first.status_code == duplicate.status_code == 200
    assert first.json() == duplicate.json()
    assert client.get("/api/receipts", headers=auth).json()["response"] == first.json()
    assert not (papers.paper_dir(first.json()["paper_id"]) / "paper.pdf").exists()
    assert b"Offline private paper" not in (root / ".paid-receipts.sqlite3").read_bytes()
    assert extractor.call_count == 1 and launch.call_count == 0
    assert sum(runs._daily_counts.values()) == 1
    changed = client.post("/api/papers", headers=auth, files={"file": ("other.pdf", b"%PDF-other", "application/pdf")})
    assert changed.status_code == 409 and extractor.call_count == 1
    papers.discard(first.json()["paper_id"])
    assert client.get("/api/receipts", headers=auth).status_code == 410
    assert client.post("/api/papers", headers=auth, files=files).status_code == 410
    assert extractor.call_count == 1


@pytest.mark.parametrize("queued", [False, True])
def test_receipted_pdf_cancellation_retains_finished_metadata_but_never_starts_abandoned_queue(paid_api, monkeypatch, queued):
    _, _, root = paid_api
    key = request_key()
    ticket, _ = receipts.claim(root, key, None, "paper", {"pdf_sha256": "offline"})
    paper_id, path = papers.save_upload(b"%PDF-offline")
    started, release = threading.Event(), threading.Event()
    def extract(*_args, **_kwargs):
        started.set()
        assert release.wait(4)
        return contribution()
    monkeypatch.setattr(main, "_extract_paper_with_paid_reservation", extract)
    async def exercise():
        original = asyncio.to_thread
        gate = asyncio.Event()
        async def controlled(fn, *args, **kwargs):
            if queued:
                await gate.wait()
            return await original(fn, *args, **kwargs)
        monkeypatch.setattr(asyncio, "to_thread", controlled)
        with receipts.activate(ticket):
            task = asyncio.create_task(main._process_uploaded_paper(paper_id, str(path)))
        try:
            if queued:
                while not main._paper_jobs:
                    await asyncio.sleep(0)
            else:
                assert await original(started.wait, 3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            gate.set()
            release.set()
        for _ in range(300):
            if not main._paper_jobs:
                break
            await asyncio.sleep(0.01)
        assert not main._paper_jobs
    asyncio.run(exercise())
    saved = receipts.lookup(root, key, None)
    assert started.is_set() is not queued
    assert saved["state"] == ("failed" if queued else "accepted")
    assert not path.exists()
    assert (papers.paper_dir(paper_id) / "extraction.json").exists() is not queued


@pytest.mark.parametrize("failure", ["corrupt_db", "empty_db", "missing_schema", "connect", "capacity"])
def test_receipt_storage_faults_fail_before_admission(paid_api, monkeypatch, failure):
    client, launch, root = paid_api
    if failure == "corrupt_db":
        (root / ".paid-receipts.sqlite3").write_bytes(b"not a database")
    elif failure == "empty_db":
        (root / ".paid-receipts.sqlite3").touch()
    elif failure == "missing_schema":
        with sqlite3.connect(root / ".paid-receipts.sqlite3") as db:
            db.execute("PRAGMA user_version=1")
    elif failure == "connect":
        monkeypatch.setattr(receipts.sqlite3, "connect", MagicMock(side_effect=sqlite3.OperationalError("do-not-log-private-key")))
    else:
        monkeypatch.setattr(receipts, "MAX_RECEIPTS", 0)
    result = client.post("/api/runs", headers=headers(), json={"topic": "No spend"})
    assert result.status_code == 503
    assert "do-not-log-private-key" not in result.text
    assert launch.call_count == 0 and sum(runs._daily_counts.values()) == 0


def test_expiry_and_cleanup_cannot_turn_old_retry_into_new_paid_work(paid_api, monkeypatch):
    client, launch, root = paid_api
    now = time.time()
    auth = headers()
    assert client.post("/api/runs", headers=auth, json={"topic": "Expiry example"}).status_code == 202
    monkeypatch.setattr(receipts.time, "time", lambda: now + 86401)
    assert client.post("/api/runs", headers=auth, json={"topic": "Expiry example"}).status_code == 410
    # A new-key operation prunes old private receipt fields in its transaction.
    fresh = client.post("/api/runs", headers=headers(), json={"topic": "New authorized intent"})
    assert fresh.status_code == 202
    assert client.get("/api/receipts", headers=auth).status_code == 410
    assert client.post("/api/runs", headers=auth, json={"topic": "Expiry example"}).status_code == 410
    assert launch.call_count == 2
    with sqlite3.connect(root / ".paid-receipts.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 1


@pytest.mark.parametrize("key", ["", "../private", "v1.0." + "a" * 64, "a" * 10000])
def test_bad_keys_are_bounded_before_paid_dispatch(paid_api, key):
    client, launch, _ = paid_api
    result = client.post("/api/runs", headers=headers(key=key) if key else {"X-Access-Code": "offline-owner-a", "Idempotency-Key": ""},
                         json={"topic": "Invalid key"})
    assert result.status_code == 400 and launch.call_count == 0


@pytest.mark.parametrize("field,value", [("state", "completed"), ("response", "[]"),
                                        ("response", "{"), ("resource_id", "../../private"),
                                        ("fingerprint", "non-ascii-\u00e9"), ("state", "pending")])
def test_corrupted_receipt_never_replays_or_redispatches(paid_api, field, value):
    client, launch, root = paid_api
    auth = headers()
    client.post("/api/runs", headers=auth, json={"topic": "Receipt integrity"})
    with sqlite3.connect(root / ".paid-receipts.sqlite3") as db:
        db.execute(f"UPDATE receipts SET {field}=?", (value,))
    assert client.get("/api/receipts", headers=auth).status_code == 503
    assert client.post("/api/runs", headers=auth, json={"topic": "Receipt integrity"}).status_code == 503
    assert launch.call_count == 1


def test_restart_replays_accepted_receipt_without_recharging(paid_api, monkeypatch):
    """A new process epoch must not invalidate committed acceptance."""
    client, launch, _ = paid_api
    auth = headers()
    first = client.post("/api/runs", headers=auth, json={"topic": "Restart example"})
    monkeypatch.setattr(receipts, "_EPOCH", "new-process-epoch")
    result = client.get("/api/receipts", headers=auth).json()
    assert result["state"] == "accepted" and result["response"] == first.json()
    assert client.post("/api/runs", headers=auth, json={"topic": "Restart example"}).json() == first.json()
    assert launch.call_count == 1 and sum(runs._daily_counts.values()) == 1


def test_receipt_survives_original_quota_rejection_without_later_dispatch(paid_api, monkeypatch):
    """A later capacity change cannot reinterpret a settled key as new work."""
    client, launch, _ = paid_api
    auth = headers()
    monkeypatch.setattr(runs, "MAX_CONCURRENT", 0)
    first = client.post("/api/runs", headers=auth, json={"topic": "No capacity"})
    assert first.status_code == 429 and first.headers["x-error-code"] == "concurrency_limit"
    monkeypatch.setattr(runs, "MAX_CONCURRENT", 5)
    replay = client.post("/api/runs", headers=auth, json={"topic": "No capacity"})
    assert replay.status_code == 429 and replay.headers["x-error-code"] == "concurrency_limit"
    assert client.get("/api/receipts", headers=auth).json()["state"] == "failed"
    assert launch.call_count == 0 and sum(runs._daily_counts.values()) == 0


def test_cross_operation_key_conflicts_before_pdf_work(paid_api, monkeypatch):
    client, launch, _ = paid_api
    extractor = MagicMock(side_effect=AssertionError("Provider call leaked"))
    monkeypatch.setattr(main, "extract_paper_contribution", extractor)
    auth = headers()
    client.post("/api/runs", headers=auth, json={"topic": "Bound operation"})
    paper = client.post("/api/papers", headers=auth, files={"file": ("x.pdf", b"%PDF-offline", "application/pdf")})
    assert paper.status_code == 409 and paper.headers["x-error-code"] == "receipt_conflict"
    assert launch.call_count == 1 and extractor.call_count == 0
    # A rejected duplicate must release transport capacity as well as avoid
    # paid work: repeated conflicts cannot consume both parser slots.
    for _ in range(3):
        again = client.post("/api/papers", headers=auth, files={"file": ("x.pdf", b"%PDF-offline", "application/pdf")})
        assert again.status_code == 409


def test_binding_failure_cannot_start_worker_or_model(paid_api, monkeypatch):
    client, launch, _ = paid_api
    monkeypatch.setattr(receipts.Ticket, "bind", MagicMock(side_effect=receipts._unavailable()))
    extractor = MagicMock(side_effect=AssertionError("Provider call leaked"))
    monkeypatch.setattr(main, "extract_paper_contribution", extractor)
    assert client.post("/api/runs", headers=headers(), json={"topic": "Binding fault"}).status_code == 503
    assert client.post("/api/papers", headers=headers(), files={"file": ("x.pdf", b"%PDF-offline", "application/pdf")}).status_code == 503
    assert not launch.called and not extractor.called and sum(runs._daily_counts.values()) == 0


def test_missing_receipt_is_not_free_and_does_not_allocate(paid_api):
    client, launch, root = paid_api
    result = client.get("/api/receipts", headers=headers())
    assert result.status_code == 404 and "does not establish" in result.text
    assert not (root / ".paid-receipts.sqlite3").exists()
    assert not launch.called and sum(runs._daily_counts.values()) == 0


def test_all_paid_routes_advertise_opt_in_header_and_read_only_lookup(paid_api):
    client, launch, _ = paid_api
    paths = client.get("/openapi.json").json()["paths"]
    for path in ("/api/runs", "/api/runs/{run_id}/resume", "/api/papers"):
        parameter = next(p for p in paths[path]["post"]["parameters"] if p["name"] == "Idempotency-Key")
        assert parameter["in"] == "header" and parameter["required"] is False
    lookup = paths["/api/receipts"]
    assert set(lookup) == {"get"}
    assert next(p for p in lookup["get"]["parameters"] if p["name"] == "Idempotency-Key")["required"] is True
    assert not launch.called


def test_prune_fault_reaches_health_and_schema_loss_fails_readiness(paid_api, monkeypatch):
    client, launch, root = paid_api
    auth = headers()
    client.post("/api/runs", headers=auth, json={"topic": "Maintenance receipt"})
    with sqlite3.connect(root / ".paid-receipts.sqlite3") as db:
        db.execute("DROP TABLE receipts")
    monkeypatch.setattr(main, "_maintenance_checks", {})
    monkeypatch.setattr(main, "_maintenance_timings", {})
    asyncio.run(main._maintenance_stage("receipts", main._prune_receipts))
    assert client.get("/health").json()["maintenance"]["checks"]["receipts"] == "failed"
    ready = client.get("/health/ready")
    assert ready.status_code == 503 and ready.json()["checks"]["paid_receipts"] != "ok"
    assert client.post("/api/runs", headers=auth, json={"topic": "Maintenance receipt"}).status_code == 503
    assert launch.call_count == 1
