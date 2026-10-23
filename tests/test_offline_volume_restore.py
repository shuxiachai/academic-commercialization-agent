"""Synthetic, quiesced volume-copy rehearsal; not a backup/restore service.

All stored execution/admission facts are newly authored scenario data, never
observations of paid work. No selector/transport/worker runs even while seeding.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import socket
import sqlite3
import stat
import subprocess
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock
from urllib.parse import unquote, urlparse
import urllib.request

import dotenv
import httpx
import pytest

from academic_agent import auxiliary_usage as aux, pdf_extractor, report_evidence_source_locator as locator
from academic_agent import saved_source_accounted_qwen as accounted_qwen
from academic_agent import report_evidence_source_locator_qwen_transport as native
from academic_agent.checkpoints import CheckpointIdentity, CheckpointStore, hash_json
from academic_agent.report_evidence_catalog_followup import build_catalog
from academic_agent.report_evidence_snapshot import content_hash, read_source
from academic_agent.run_output import save_report
from academic_agent.run_spec import RunSpec
from academic_agent.run_terminal import (
    TerminalRecord, TerminalRecordUnreadable, UsageAccounting,
    commit_terminal_record, load_terminal_record,
)
from academic_agent.saved_source_loader import SavedSourceLoader
from api import access, papers, receipts, runs
from api import auxiliary_usage as pdf_usage
from api import saved_source_accounting as accounting
from api import saved_source_controller as controller
from api import saved_source_production_policy as policy
from api import saved_source_receipts as locator_receipts
from tests.test_saved_source_controller import CODE, RUN_ID, TEXT, saved_registry

DAY = date(2026, 9, 26)
START = datetime(2026, 9, 26, 12, tzinfo=UTC)
NOW = int(START.timestamp())
PAPER_ID = "paper-" + "2" * 32
CHILD_ID = "20260926T120001Z-" + "3" * 32
QUESTION = "SYNTHETIC offline volume question"
SELECTOR_ID = "synthetic-stored-history-not-executed"
LOCATOR_DIR = ".source-locator-v1"
LEDGER = ".paid-operation-ledger.json"
REPORT = "# SYNTHETIC offline report\n\nFixture only; no research claim.\n"
EXTRACTION = {
    "title": "SYNTHETIC pending paper", "core_contribution": "Offline fixture only",
    "application_domain": "Synthetic fixtures", "commercialization_topic": "Synthetic restoration",
}
SCORES = {"synthetic": True, "score": 3.5, "semantic_support": "not_assessed"}
MAX_ENTRIES, MAX_BYTES = 128, 2 * 1024 * 1024


def _key(index):
    # Deterministic synthetic receipt capabilities, never real keys.
    return f"v1.{NOW}.{index:064x}"


def _json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


class InventoryRejected(ValueError):
    """This bounded fixture copy failed its trusted external inventory."""


@dataclass(frozen=True)
class Entry:
    kind: str
    length: int
    sha256: str | None


def _plain(info):
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise InventoryRejected("link/reparse point")
    if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
        raise InventoryRejected("unsupported entry type")


def _confined(path, sandbox, *, absent=False):
    """Check containment and every ancestor before resolving or copying."""
    path, sandbox = path.absolute(), sandbox.absolute()
    if not path.is_relative_to(sandbox) or ".." in path.parts:
        raise InventoryRejected("outside pytest sandbox")
    current = sandbox
    _plain(current.lstat())
    for part in path.relative_to(sandbox).parts:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if absent and current == path:
                return path
            raise InventoryRejected("missing ancestor") from None
        _plain(info)
    if absent:
        raise InventoryRejected("destination already exists")
    if not path.resolve(strict=True).is_relative_to(sandbox.resolve(strict=True)):
        raise InventoryRejected("resolved outside pytest sandbox")
    return path


def _inventory(root, sandbox):
    """Record dotfiles, directories, types, lengths and hashes; never follow links."""
    root = _confined(root, sandbox)
    if not root.is_dir():
        raise InventoryRejected("volume must be a directory")
    result, total = {}, 0

    def visit(path):
        nonlocal total
        info = path.lstat()
        _plain(info)
        if path.name.endswith(("-wal", "-shm", "-journal", ".tmp")):
            raise InventoryRejected("unquiesced sidecar")
        name = path.relative_to(root).as_posix()
        if len(result) >= MAX_ENTRIES:
            raise InventoryRejected("entry bound")
        if stat.S_ISDIR(info.st_mode):
            result[name] = Entry("directory", 0, None)
            for child in sorted(path.iterdir()):
                visit(child)
        else:
            total += info.st_size
            if total > MAX_BYTES:
                raise InventoryRejected("byte bound")
            raw = path.read_bytes()
            if len(raw) != info.st_size:
                raise InventoryRejected("file changed during inventory")
            result[name] = Entry("file", len(raw), _sha(raw))

    visit(root)
    return result


def _matches(root, sandbox, expected):
    if _inventory(root, sandbox) != expected:
        raise InventoryRejected("inventory mismatch")


def _copy_fresh(source, destination, sandbox, expected):
    """Test-only copy; rejected partial targets are retained, never overwritten."""
    _matches(source, sandbox, expected)
    destination = _confined(destination, sandbox, absent=True)
    if destination.is_relative_to(source.absolute()):
        raise InventoryRejected("destination inside source")
    destination.mkdir()
    for name, entry in expected.items():
        if name == ".":
            continue
        target = destination / name
        if entry.kind == "directory":
            target.mkdir()
        else:
            with target.open("xb") as output:
                output.write((source / name).read_bytes())
    _matches(source, sandbox, expected)
    _matches(destination, sandbox, expected)
    return destination


@pytest.fixture(autouse=True)
def empty_rate_limit_buckets():
    """No HTTP here: avoid conftest's api.main/.env import in this module only.

    Direct readers cannot use HTTP rate buckets. Old fixtures are unchanged;
    all execution/network guards remain active below.
    """
    yield


@pytest.fixture(autouse=True)
def offline_guard(monkeypatch, tmp_path, stub_llm_calls):
    """Caught fail-fast errors still fail teardown through independent counts."""
    forbidden = []

    def block(obj, name):
        guard = Mock(name=name, side_effect=AssertionError(f"Forbidden offline entry: {name}"))
        monkeypatch.setattr(obj, name, guard)
        forbidden.append(guard)

    for obj, names in (
        (dotenv, ("load_dotenv", "find_dotenv")),
        (subprocess, ("Popen",)), (os, ("system",)),
        (socket, ("create_connection", "getaddrinfo")), (socket.socket, ("sendto", "connect_ex")),
        (urllib.request, ("urlopen",)),
        (httpx.Client, ("send",)), (httpx.AsyncClient, ("send",)),
        (httpx.HTTPTransport, ("handle_request",)), (httpx.AsyncHTTPTransport, ("handle_async_request",)),
        (runs, ("start_run", "resume_run", "_start_run_from_spec", "_admit_paid_operation_locked",
                "_charge_daily_ledger_locked", "reserve_inline_paid_operation", "reserve_thread_paid_operation",
                "reap_timeouts", "prune_expired_runs", "shutdown_all")),
        (papers, ("save_upload", "prune_old")),
        (pdf_extractor, ("extract_pdf_text", "extract_paper_contribution", "_call_llm_json")),
        (locator, ("locate_saved_source",)), (controller, ("locate_saved_source",)),
        (controller.SavedSourceController, ("execute", "_begin", "_operate")),
        (accounted_qwen.AccountedQwenSelector, ("__init__", "select")),
        (native.LocatorQwenTransport, ("__init__", "__call__")),
        (native.LocatorQwenLedger, ("__init__", "reserve")),
        (policy.ControlStore, ("reserve", "prune_native")),
    ):
        for name in names:
            block(obj, name)
    block(sys.modules["academic_agent.language"], "_llm_call")
    denied_connect = Mock(side_effect=AssertionError("External socket connection forbidden"))
    forbidden.append(denied_connect)
    real_connect = socket.socket.connect

    def connect(sock, address):
        # Windows asyncio's self-pipe may use socketpair's loopback fallback;
        # arbitrary loopback clients/servers are not exempt from the guard.
        local = isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}
        self_pipe = os.name == "nt" and local and any(
            frame.filename == socket.__file__
            and frame.function in {"socketpair", "_socketpair", "_fallback_socketpair"}
            for frame in inspect.stack(context=0)
        )
        return real_connect(sock, address) if self_pipe else denied_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    connections, real_connect_db = [], sqlite3.connect

    class TrackedConnection(sqlite3.Connection):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.closed_verified = False

        def close(self):
            # SQLite checks thread ownership before closed-state on execute.
            # Verify the real close in its owner thread, without disabling
            # check_same_thread or treating a cross-thread error as closure.
            super().close()
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                super().execute("SELECT 1")
            self.closed_verified = True

    def tracked_connect(database, *args, **kwargs):
        raw = str(database)
        if raw.startswith("file:"):
            raw = unquote(urlparse(raw).path)
            if os.name == "nt":
                raw = raw.removeprefix("/")
        assert Path(raw).absolute().is_relative_to(tmp_path.absolute()), "SQLite outside fresh pytest root"
        assert "factory" not in kwargs and len(args) < 5, "Unexpected SQLite factory override"
        db = real_connect_db(database, *args, factory=TrackedConnection, **kwargs)
        connections.append(db)
        return db

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)

    def quiesced():
        for db in connections:
            assert db.closed_verified, "SQLite connection did not complete a verified real close"
        assert runs._registry == runs._stop_claims == runs._inline_paid_operations == {}
        assert pdf_usage._ACTIVE == {} and aux.current() is None

    yield SimpleNamespace(quiesced=quiesced, block=block)
    try:
        quiesced()
    finally:
        for guard in forbidden:
            guard.assert_not_called()
        assert stub_llm_calls == []


def _roots(monkeypatch, root):
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", root)
    monkeypatch.setattr(papers, "PAPERS_ROOT", root / "_papers")
    for name in ("_registry", "_stop_claims", "_inline_paid_operations", "_daily_counts"):
        monkeypatch.setattr(runs, name, {})
    monkeypatch.setattr(runs, "_daily_date", None)
    monkeypatch.setattr(pdf_usage, "_ACTIVE", {})
    monkeypatch.setattr(pdf_usage, "_FAULTS", {})


@pytest.fixture
def application_readers(monkeypatch, offline_guard):
    """Load real handlers without dotenv reads, lifespan or cached main aliases.

    An isolated module avoids leaking import-time patched aliases into api.main
    in later tests. The unused provider-configuration import is fail-fast stubbed
    before it can initialize CrewAI (whose import itself invokes dotenv). Only
    main's explicit dotenv hook is ignored; network/execution guards stay active.
    These are handler/model observations, not an HTTP or browser rehearsal.
    """
    path = Path(__file__).resolve().parents[1] / "api" / "main.py"
    spec = importlib.util.spec_from_file_location("_offline_volume_readers", path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    monkeypatch.setenv("SOURCE_LOCATOR_ENABLED", "0")
    provider_config = ModuleType("academic_agent.llm_config")
    # Every name main imports from llm_config, each a fail-fast guard: /health
    # resolves the model through resolve_provider_config, and these readers
    # must never reach a credential or an SDK.
    for name in ("_detect_provider", "resolve_provider_config", "validate_llm_configuration"):
        setattr(provider_config, name, None)
        offline_guard.block(provider_config, name)
    ignored_dotenv = Mock(return_value=False)
    with monkeypatch.context() as patch:
        patch.setitem(sys.modules, provider_config.__name__, provider_config)
        patch.setattr(dotenv, "load_dotenv", ignored_dotenv)
        spec.loader.exec_module(module)
    ignored_dotenv.assert_called_once_with(path.parents[1] / ".env")
    assert module._source_locator is None and module._maintenance_task is None
    for name in ("extract_paper_contribution", "_process_uploaded_paper", "_extract_paper_with_paid_reservation",
                 "submit_run", "resume_run", "upload_paper", "get_report_pdf", "_lifespan", "_reaper"):
        offline_guard.block(module, name)
    yield module
    ignored_dotenv.assert_called_once_with(path.parents[1] / ".env")
    assert module._source_locator is None and module._maintenance_task is None


@contextmanager
def _source_unavailable(volume):
    """Temporarily hide only this confined synthetic source, retaining all bytes."""
    source = _confined(volume.source, volume.sandbox)
    hidden = _confined(volume.sandbox / "source-unavailable", volume.sandbox, absent=True)
    boundary = volume.sandbox.resolve(strict=True)
    assert source.resolve(strict=True).is_relative_to(boundary)
    assert hidden.resolve(strict=False).is_relative_to(boundary)
    source.rename(hidden)
    try:
        assert not source.exists()
        yield
    finally:
        _confined(hidden, volume.sandbox)
        _confined(source, volume.sandbox, absent=True)
        assert hidden.resolve(strict=True).is_relative_to(boundary)
        assert source.resolve(strict=False).is_relative_to(boundary)
        hidden.rename(source)


@contextmanager
def _no_observation_writes(monkeypatch):
    """Catch swallowed attempts to repair, settle or recreate auxiliary records."""
    guards = []
    with monkeypatch.context() as patch:
        for obj, names in ((aux.Collector, ("__init__", "_save", "begin", "settle", "finish")),
                           (pdf_usage, ("paper_operation", "prune")),
                           (receipts.Ticket, ("bind", "finish")), (receipts, ("claim",))):
            for name in names:
                guard = Mock(side_effect=AssertionError(f"Read attempted accounting write: {name}"))
                patch.setattr(obj, name, guard)
                guards.append(guard)
        try:
            yield
        finally:
            for guard in guards:
                guard.assert_not_called()
            assert pdf_usage._ACTIVE == pdf_usage._FAULTS == {}


def _stored_locator(snapshot):
    """Synthetic historical facts only; no selector invocation masquerades as a read."""
    catalog = build_catalog(snapshot)
    coverage = locator.LocatorCatalog(
        catalog_hash=content_hash(catalog), catalog_bytes=len(locator._canonical(catalog).encode("ascii")),
        **{name: catalog[name] for name in (
            "total_count", "returned_count", "omitted_count", "coverage", "title_truncation_count")},
    )
    saved = snapshot.sources[0]
    source = locator.LocatorSource(
        **saved.model_dump(exclude={"summary"}), stored_length=saved.stored_length,
        snapshot_hash=snapshot.snapshot_hash, source_hash=snapshot.source_hash(saved),
        summary_hash=content_hash(saved.summary),
    )
    read = read_source(snapshot, saved.source_id, 0, locator.MAX_SAVED_CODEPOINTS)
    result = locator.LocatorResult(
        state="excerpt", reason="saved_text", catalog=coverage, source=source,
        saved_text=locator.LocatorText(**{name: read[name] for name in locator.LocatorText.model_fields}),
        callback_entries=1,
        callback_bytes=len(locator._canonical(locator._request(QUESTION, catalog)).encode("ascii")),
        read_attempts=1, read_completed=1,
    )
    return controller._projection(result)


@pytest.fixture
def volume(tmp_path, monkeypatch, offline_guard):
    sandbox = tmp_path / "synthetic-rehearsal"
    sandbox.mkdir()
    source = sandbox / "source"
    source.mkdir()
    _roots(monkeypatch, source)
    monkeypatch.setattr(access, "ACCESS_CODE", CODE)
    owner = access.owner_id(CODE)
    monkeypatch.setattr(receipts, "_EPOCH", "synthetic-fixture-origin")
    for module in (receipts, locator_receipts, accounting):
        monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: NOW))

    class FixtureDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return START if tz else START.replace(tzinfo=None)

    monkeypatch.setattr(runs, "datetime", FixtureDatetime)
    run = source / RUN_ID
    run.mkdir()
    (run / ".owner").write_text(owner, encoding="utf-8")
    spec = RunSpec(topic="SYNTHETIC volume fixture", language="English", paper_contribution=EXTRACTION)
    spec.save(run)
    save_report(REPORT, RUN_ID, output_root=source)
    _json(run / "validated_sources.json", saved_registry())
    _json(run / "commercialization_scores.json", SCORES)
    _json(run / "status.json", {"topic": spec.topic, "done": True, "stage": "Done"})
    identity = CheckpointIdentity(
        node_id="retrieval", input_sha256=hash_json(spec), evidence_sha256=hash_json(saved_registry()),
        config_sha256=hash_json({"synthetic": True}), pipeline_revision="synthetic-offline-volume-v1", as_of_date=DAY,
    )
    payload = json.dumps({"synthetic": True, "sources": saved_registry()})
    manifest = CheckpointStore(run).commit(identity, payload, output_format="json", completed_at=START)
    # Storage presence/identity only, not worker hydration or executed recovery.
    CheckpointStore(run / ".resume-source").commit(identity, payload, output_format="json", completed_at=START)
    terminal = TerminalRecord(
        state="completed", reason_code="worker_completed", termination_method="worker_exit",
        started_at=START, ended_at=START + timedelta(seconds=17), elapsed_seconds=17, last_stage="Done",
        usage_accounting=UsageAccounting(state="unavailable", snapshot_at=START, run_complete=True,
                                         in_flight_request_may_have_spent=False),
        checkpointing={"state": "partial", "committed_nodes": ["retrieval"]}, recovery={"state": "not_requested"},
    )
    commit_terminal_record(run, terminal)
    paper = source / "_papers" / PAPER_ID
    paper.mkdir(parents=True)
    (paper / ".owner").write_text(owner, encoding="utf-8")
    papers.save_extraction(PAPER_ID, EXTRACTION)
    # Real accounting writers, entirely synthetic observations: no SDK, HTTP
    # helper or extraction is constructed/called to generate these counters.
    with pdf_usage.paper_operation(PAPER_ID) as pdf:
        sequence = pdf.begin("pdf_extraction", "llm_invocation", "qwen3.5-plus")
        pdf.settle(sequence, aux.Tokens(prompt_tokens=113, completion_tokens=29), "returned")
    reference = pdf_usage.paper_reference(PAPER_ID)
    collector = aux.Collector(run / aux.FILE_NAME, pdf_reference=reference)
    sequence = collector.begin("search_planning", "http_attempt", "qwen3.5-plus")
    collector.settle(sequence, aux.Tokens(prompt_tokens=11, completion_tokens=7), "returned")
    collector.begin("translation", "http_attempt", "qwen3.5-plus")
    # A terminal outcome is not auxiliary settlement. The second observation
    # stays pending/unknown even though the immutable run says completed.
    _json(run / "status.json", {"topic": spec.topic, "done": True, "stage": "Done",
                               "auxiliary_usage_snapshot": collector.snapshot()})
    auxiliary, pdf_summary = collector.summary(), pdf_usage.paper_summary(PAPER_ID)
    assert auxiliary["observed_tokens"] == 18 and auxiliary["total_tokens"] is None
    assert auxiliary["calls"][1]["observed_cost_usd"] is None
    assert pdf_summary["observed_tokens"] == 142 and pdf_summary["provider_attempt_count"] is None
    # Real storage writer, synthetic counts; never actual paid admission.
    monkeypatch.setattr(runs, "_daily_counts", {owner: 2})
    with runs._registry_lock:
        runs._write_daily_ledger_locked(DAY)
    for index, kind, resource in ((1, "run", RUN_ID), (2, "paper", PAPER_ID), (3, "resume", CHILD_ID)):
        ticket, previous = receipts.claim(source, _key(index), owner, kind, {"synthetic": True})
        assert ticket is not None and previous is None
        ticket.bind(resource)
        if kind != "resume":
            response = {"paper_id": resource} if kind == "paper" else {"run_id": resource, "topic": spec.topic}
            ticket.finish(response, 200 if kind == "paper" else 202)
    feature = source / LOCATOR_DIR
    control = policy.ControlStore(feature, policy.Settings())
    control.prepare()
    snapshot = SavedSourceLoader(source)(RUN_ID)
    journal, store = locator_receipts.Journal(feature), accounting.AccountingStore(feature)
    ticket, claimed = journal.claim(_key(4), owner, RUN_ID, QUESTION, SELECTOR_ID)
    observation = store.begin(claimed)
    bound = ticket.bind(controller._binding(snapshot))
    operation = observation.bind(bound, SELECTOR_ID)
    projection, expected_result = _stored_locator(snapshot)
    ticket.admitting()
    ticket.admitted()
    ticket.complete(projection)
    # Accounting remains unfinished/unknown. No invented provider finish/tokens.
    journal.claim(_key(5), owner, RUN_ID, "SYNTHETIC unresolved intent", SELECTOR_ID)
    # The control writer is admission, so keep it guarded. Seed a synthetic row
    # in the real schema; readonly _rows must validate the restored identity.
    with control.database() as db, db:
        db.execute("INSERT INTO operations VALUES (?,?,?,?)", (
            operation.receipt_key_sha256, locator_receipts.canonical(operation.model_dump()),
            NOW * 1000, policy.RESERVATION_NANODOLLARS))
        db.execute("UPDATE control SET last_ms=?, observed_ms=? WHERE id=1", (NOW * 1000, NOW * 1000))
    native_dir = feature / "native" / operation.receipt_key_sha256
    native_dir.mkdir()
    _json(native_dir / "manifest.json", {"synthetic": True, "native_execution": "not_run"})
    (native_dir / "events.jsonl").write_bytes(b'{"synthetic":true,"event":"inventory_only_not_a_paid_record"}\n')
    offline_guard.quiesced()
    frozen = _inventory(source, sandbox)
    return SimpleNamespace(
        source=source, sandbox=sandbox, frozen=frozen, owner=owner, spec=spec, terminal=terminal,
        identity=identity, checkpoint_payload=payload, checkpoint_file=manifest.output_file,
        result=expected_result, operation=operation, guard=offline_guard,
        auxiliary=auxiliary, pdf_summary=pdf_summary, pdf_reference=reference,
    )


async def _lookup(root, key):
    value = controller.SavedSourceController(
        SavedSourceLoader(root), root / LOCATOR_DIR,
        accounting_store=accounting.AccountingStore(root / LOCATOR_DIR),
    )
    assert value._selector is value._accounted_selector is None
    try:
        return await value.lookup(key, CODE)
    finally:
        await value.close()
        assert value._threads == {}


def _read_auxiliary(volume, root, readers, *, expected_run=None, expected_pdf=None):
    """Observe actual handler/model projections and replay, never imitate them."""
    expected_run = volume.auxiliary if expected_run is None else expected_run
    expected_pdf = volume.pdf_summary if expected_pdf is None else expected_pdf
    assert pdf_usage.paper_path(PAPER_ID) == root / "_auxiliary_usage" / f"{PAPER_ID}.json"
    assert pdf_usage._ACTIVE == pdf_usage._FAULTS == {}
    request = readers.Request({"type": "http", "headers": [
        (b"idempotency-key", _key(2).encode("ascii")), (b"x-access-code", CODE.encode("ascii"))]})
    for _ in range(2):
        for response in (readers.get_run(RUN_ID), readers.get_progress(RUN_ID, since=0)):
            body = response.model_dump(mode="json")
            assert body["auxiliary_usage"] == expected_run
            assert body["state"] == "completed" and body["terminal"]["record_state"] == "committed"
            assert body["usage"] is None and body["usage_accounting"]["state"] == "unavailable"
        assert pdf_usage.paper_summary(PAPER_ID) == expected_pdf
        response = readers.Response()
        receipt = readers.get_paid_receipt(request, response).model_dump(mode="json")
        assert response.headers["Cache-Control"] == "no-store"
        assert receipt["state"] == "accepted" and receipt["resource_id"] == PAPER_ID
        assert receipt["auxiliary_usage"] == receipt["response"]["auxiliary_usage"] == expected_pdf
        assert all(receipt["response"][name] == value for name, value in EXTRACTION.items())
        record = receipts.lookup(root, _key(2), volume.owner)
        replay = readers._replay_receipt(record)
        assert replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
        assert json.loads(replay.body) == receipt["response"]
    assert load_terminal_record(root / RUN_ID) == volume.terminal
    assert _sha((root / RUN_ID / "terminal.json").read_bytes()) == volume.frozen[f"{RUN_ID}/terminal.json"].sha256


def _read_restored(volume, root, monkeypatch, readers):
    """Fresh reader instances/cache reset, not a worker restart or paid replay."""
    _roots(monkeypatch, root)
    monkeypatch.setattr(receipts, "_EPOCH", "synthetic-restarted-observer")
    assert runs._daily_counts == {} and runs._daily_date is None
    state = runs.get_state(RUN_ID)
    assert state["state"] == "completed" and state["terminal"]["record_state"] == "committed"
    assert state["elapsed_seconds"] == 17 and state["usage"] is None
    assert state["usage_accounting"]["state"] == "unavailable"
    for name, filename in (("report", "commercialization_report.md"), ("sources", "validated_sources.json"),
                           ("scores", "commercialization_scores.json"), ("terminal", "terminal.json")):
        path = runs.artifact_path(RUN_ID, name)
        assert path == root / RUN_ID / filename
        assert _sha(path.read_bytes()) == volume.frozen[f"{RUN_ID}/{filename}"].sha256
    assert runs.owner_of(RUN_ID) == volume.owner
    assert RunSpec.load(root / RUN_ID) == volume.spec
    assert load_terminal_record(root / RUN_ID) == volume.terminal
    for run in (root / RUN_ID, root / RUN_ID / ".resume-source"):
        inspected = CheckpointStore(run).inspect(volume.identity)
        assert inspected.state == "reusable" and inspected.text() == volume.checkpoint_payload
    assert papers.load_extraction(PAPER_ID) == EXTRACTION
    assert papers.extraction_path_for_run(PAPER_ID, owner=volume.owner) == root / "_papers" / PAPER_ID / "extraction.json"
    with pytest.raises(papers.PaperNotFound):
        papers.extraction_path_for_run(PAPER_ID, owner="unrelated-synthetic-owner")
    with runs._registry_lock:
        counts = runs._read_daily_ledger_locked(DAY)
        runs._daily_window_locked()
    assert runs._daily_counts == counts == {volume.owner: 2}
    records = [receipts.public_record(receipts.lookup(root, _key(index), volume.owner)) for index in (1, 2, 3)]
    assert [(item["operation"], item["state"], item["resource_id"]) for item in records] == [
        ("run", "accepted", RUN_ID), ("paper", "accepted", PAPER_ID), ("resume", "unknown", CHILD_ID)]
    assert records[1]["response"] == {"paper_id": PAPER_ID} and records[2]["response"] is None
    result = asyncio.run(_lookup(root, _key(4)))
    assert result["state"] == "completed" and result["delivery"] == "available"
    assert result["result"] == volume.result and result["result"]["saved_text"]["text"] == TEXT
    assert (result["delivery_snapshot_reads"], result["delivery_source_reads"]) == (1, 1)
    assert result["provider_usage"] == result["provider_cost"] == "not_observed"
    assert result["accounting"]["usage"]["status"] == "unknown"
    assert result["accounting"]["usage"]["total_tokens"] is None
    assert result["accounting"]["cost"]["estimated_usd"] is None
    feature = root / LOCATOR_DIR
    record = locator_receipts.Journal(feature).lookup(_key(4), volume.owner)
    assert accounting.AccountingStore(feature).observe(record) == result["accounting"]
    pending = asyncio.run(_lookup(root, _key(5)))
    assert pending["state"] == "unknown" and pending["delivery"] == "not_ready" and pending["result"] is None
    control = policy.ControlStore(feature, policy.Settings())
    with control.database(readonly=True) as db:
        rows, last, observed = control._rows(db)
    assert rows == [(volume.operation, NOW * 1000, policy.RESERVATION_NANODOLLARS)]
    assert last == observed == NOW * 1000
    native_dir = feature / "native" / volume.operation.receipt_key_sha256
    assert set(path.name for path in native_dir.iterdir()) == {"manifest.json", "events.jsonl"}
    for path in native_dir.iterdir():
        assert _sha(path.read_bytes()) == volume.frozen[path.relative_to(root).as_posix()].sha256
    with _no_observation_writes(monkeypatch):
        _read_auxiliary(volume, root, readers)
    # Current helper observations exclude the historical invocation; duplicate
    # status/sidecar snapshots also reconcile rather than accumulate.
    auxiliary = state["auxiliary_usage"]
    assert auxiliary["call_count"] == auxiliary["provider_attempt_count"] == 2
    assert auxiliary["observed_tokens"] == 18 and auxiliary["total_tokens"] is None
    assert auxiliary["coverage"] == "pending" and not auxiliary["cost_complete"]
    assert auxiliary["calls"][1]["tokens"] is auxiliary["calls"][1]["observed_cost_usd"] is None
    assert auxiliary["observed_cost_usd"] == auxiliary["calls"][0]["observed_cost_usd"] > 0
    assert auxiliary["pdf_reference"] == {"relation": "reference_only", "observation": volume.pdf_summary}
    assert auxiliary["pdf_reference"]["observation"]["observed_tokens"] == 142
    assert not auxiliary["end_to_end_cost_complete"]
    assert aux.run_reference(root / RUN_ID) == volume.pdf_reference
    volume.guard.quiesced()


def test_quiesced_copy_real_readers_preserve_every_byte(volume, monkeypatch, application_readers):
    """Visible-only copies can conceal lost hidden admission and ownership state."""
    assert {
        ".", LEDGER, ".paid-receipts.sqlite3", f"{RUN_ID}/.owner", f"{RUN_ID}/.run-spec.json",
        f"{RUN_ID}/.resume-source", f"_papers/{PAPER_ID}/.owner",
        f"{LOCATOR_DIR}/{locator_receipts.FILENAME}", f"{LOCATOR_DIR}/{accounting.FILENAME}",
        f"{LOCATOR_DIR}/{policy.FILENAME}",
        f"{RUN_ID}/{aux.FILE_NAME}", "_auxiliary_usage", f"_auxiliary_usage/{PAPER_ID}.json",
    } <= volume.frozen.keys()
    restored = _copy_fresh(volume.source, volume.sandbox / "restored", volume.sandbox, volume.frozen)
    with _source_unavailable(volume):
        _read_restored(volume, restored, monkeypatch, application_readers)
    # Legacy receipts may open SQLite RW. Assert byte invariance, not OS readonly
    # enforcement, immutable mounts, or absence of transient filesystem I/O.
    _matches(restored, volume.sandbox, volume.frozen)
    _matches(volume.source, volume.sandbox, volume.frozen)


@pytest.mark.parametrize("damage", ["omitted_dotfile", "mixed", "truncated"])
def test_reinjected_copy_damage_is_rejected(volume, monkeypatch, damage):
    """Reinject actual omitted-dotfile/corrupt-copy faults into an accepted copy."""
    restored = _copy_fresh(volume.source, volume.sandbox / "damaged", volume.sandbox, volume.frozen)
    if damage == "omitted_dotfile":
        (restored / LEDGER).unlink()
        _roots(monkeypatch, restored)
        with runs._registry_lock:
            assert runs._read_daily_ledger_locked(DAY) == {}  # First boot, NOT safe restoration.
        assert not (restored / LEDGER).exists()
    elif damage == "mixed":
        _json(restored / RUN_ID / "commercialization_scores.json", {**SCORES, "score": 4.5})
    else:
        target = restored / ".paid-receipts.sqlite3"
        target.write_bytes(target.read_bytes()[:37])
    with pytest.raises(InventoryRejected, match="inventory mismatch"):
        _matches(restored, volume.sandbox, volume.frozen)
    _matches(volume.source, volume.sandbox, volume.frozen)


@pytest.mark.parametrize("damage", ["terminal", "checkpoint"])
def test_real_reader_corruption_is_not_repaired_or_hidden(volume, monkeypatch, damage):
    """An old done flag or matching identity cannot override corrupt terminal/payload bytes."""
    restored = _copy_fresh(volume.source, volume.sandbox / "damaged", volume.sandbox, volume.frozen)
    _roots(monkeypatch, restored)
    run = restored / RUN_ID
    target = run / "terminal.json" if damage == "terminal" else run / "checkpoints" / "retrieval" / volume.checkpoint_file
    target.write_bytes(b"{truncated")
    with pytest.raises(InventoryRejected):
        _matches(restored, volume.sandbox, volume.frozen)
    damaged = _inventory(restored, volume.sandbox)
    if damage == "terminal":
        with pytest.raises(TerminalRecordUnreadable):
            load_terminal_record(run)
        state = runs.get_state(RUN_ID)
        assert state["state"] == "unknown" and state["terminal"]["record_state"] == "unreadable"
        assert state["usage"] is None and state["usage_accounting"]["state"] == "unavailable"
    else:
        inspected = CheckpointStore(run).inspect(volume.identity)
        assert inspected.state == "corrupt" and {"output_bytes", "output_sha256"} <= set(inspected.reasons)
    _matches(restored, volume.sandbox, damaged)
    _matches(volume.source, volume.sandbox, volume.frozen)


@pytest.mark.parametrize("damage,delivery", [("source_missing", "expired"), ("source_changed", "changed"),
                                           ("accounting_corrupt", "available")])
def test_locator_damage_never_redispatches_or_claims_zero_cost(volume, monkeypatch, damage, delivery):
    """Completed receipt cannot recreate missing text or turn unreadable accounting into free work."""
    restored = _copy_fresh(volume.source, volume.sandbox / "damaged", volume.sandbox, volume.frozen)
    _roots(monkeypatch, restored)
    sources = restored / RUN_ID / "validated_sources.json"
    if damage == "source_missing":
        sources.unlink()
    elif damage == "source_changed":
        _json(sources, saved_registry(TEXT + "changed"))
    else:
        (restored / LOCATOR_DIR / accounting.FILENAME).write_bytes(b"synthetic corrupt accounting")
    with pytest.raises(InventoryRejected):
        _matches(restored, volume.sandbox, volume.frozen)
    damaged = _inventory(restored, volume.sandbox)
    result = asyncio.run(_lookup(restored, _key(4)))
    assert result["state"] == "completed" and result["delivery"] == delivery
    assert result["provider_usage"] == result["provider_cost"] == "not_observed"
    if damage == "accounting_corrupt":
        assert result["result"] == volume.result
        assert result["accounting"]["usage"]["status"] == "unavailable"
        assert result["accounting"]["dispatch_state"] == "unknown"
        assert result["accounting"]["usage"]["total_tokens"] is None
        assert result["accounting"]["cost"]["estimated_usd"] is None
    else:
        assert result["result"] is None and result["delivery_source_reads"] == 0
    volume.guard.quiesced()
    _matches(restored, volume.sandbox, damaged)
    _matches(volume.source, volume.sandbox, volume.frozen)


def test_auxiliary_copy_loss_preserves_uncertainty_and_terminal(volume, monkeypatch, application_readers):
    """Lost sidecars cannot become free work, erase a fallback or reprice a PDF reference."""
    for index, (kind, damage, fallback) in enumerate((
        ("run", "missing", True), ("run", "corrupt", True),
        ("run", "missing", False), ("run", "corrupt", False),
        ("pdf", "missing", False), ("pdf", "corrupt", False),
    )):
        restored = _copy_fresh(volume.source, volume.sandbox / f"aux-damage-{index}", volume.sandbox, volume.frozen)
        _roots(monkeypatch, restored)
        target = restored / RUN_ID / aux.FILE_NAME if kind == "run" else pdf_usage.paper_path(PAPER_ID)
        if damage == "missing":
            _confined(target, volume.sandbox)
            assert target.resolve(strict=True).is_relative_to(volume.sandbox.resolve(strict=True))
            target.unlink()
        else:
            target.write_bytes(b"{synthetic truncated auxiliary observation")
        if kind == "run" and not fallback:
            status_path = restored / RUN_ID / "status.json"
            status = json.loads(status_path.read_text(encoding="utf-8"))
            del status["auxiliary_usage_snapshot"]
            _json(status_path, status)
        with pytest.raises(InventoryRejected, match="inventory mismatch"):
            _matches(restored, volume.sandbox, volume.frozen)
        damaged = _inventory(restored, volume.sandbox)
        missing = aux.unavailable("not_recorded" if damage == "missing" else "unreadable")
        expected_run, expected_pdf = volume.auxiliary, volume.pdf_summary
        if kind == "run":
            expected_run = {**volume.auxiliary, "record_state": "write_failed"} if fallback else missing
        else:
            expected_pdf = missing
        with _source_unavailable(volume), _no_observation_writes(monkeypatch):
            _read_auxiliary(volume, restored, application_readers,
                            expected_run=expected_run, expected_pdf=expected_pdf)
            observed = runs.get_state(RUN_ID)["auxiliary_usage"] if kind == "run" else pdf_usage.paper_summary(PAPER_ID)
            assert observed["total_tokens"] is None and not observed["cost_complete"]
            if kind == "run" and fallback:
                assert observed["observed_tokens"] == 18 and observed["observed_cost_usd"] > 0
                assert observed["calls"][1]["total_tokens"] is observed["calls"][1]["observed_cost_usd"] is None
            else:
                assert observed["call_count"] is observed["observed_tokens"] is observed["observed_cost_usd"] is None
            if kind == "pdf":
                # The private source ledger can disappear without changing the
                # already-frozen association or adding its old cost to this run.
                assert aux.run_reference(restored / RUN_ID) == volume.pdf_reference
                assert runs.get_state(RUN_ID)["auxiliary_usage"]["observed_tokens"] == 18
        volume.guard.quiesced()
        _matches(restored, volume.sandbox, damaged)
        _matches(volume.source, volume.sandbox, volume.frozen)


def test_failed_auxiliary_publication_restores_status_lower_bound(volume, monkeypatch, application_readers):
    """A copied pending sidecar must reconcile the newer failed-write status, not sum it."""
    run = volume.source / RUN_ID
    collector = aux.Collector(run / aux.FILE_NAME)
    pending_bytes = collector.path.read_bytes()
    real_open = Path.open

    def fail_publication(path, *args, **kwargs):
        if path == collector.path.with_suffix(".json.tmp"):
            raise OSError("Synthetic auxiliary publication failure before temporary creation")
        return real_open(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", fail_publication)
        collector.settle(1, None, "call_failed")
        collector.finish()
    assert collector.path.read_bytes() == pending_bytes
    status_path = run / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status.update(auxiliary_usage_snapshot=collector.snapshot(), auxiliary_usage_storage_failed=True)
    _json(status_path, status)
    volume.auxiliary = collector.summary()
    assert volume.auxiliary["record_state"] == "write_failed" and volume.auxiliary["coverage"] == "partial"
    # Freeze this scenario before copying, including its independent fallback.
    volume.guard.quiesced()
    volume.frozen = _inventory(volume.source, volume.sandbox)
    restored = _copy_fresh(volume.source, volume.sandbox / "failed-publication", volume.sandbox, volume.frozen)
    _roots(monkeypatch, restored)
    with _source_unavailable(volume), _no_observation_writes(monkeypatch):
        _read_auxiliary(volume, restored, application_readers)
        disk = aux.read_ledger(restored / RUN_ID / aux.FILE_NAME)
        assert disk.calls[1].state == "pending" and not disk.operation_complete
        observed = runs.get_state(RUN_ID)["auxiliary_usage"]
        assert observed["calls"][1]["state"] == "settled" and observed["calls"][1]["outcome"] == "call_failed"
        assert observed["call_count"] == 2 and observed["observed_tokens"] == 18
        assert observed["total_tokens"] is observed["calls"][1]["observed_cost_usd"] is None
        assert not observed["cost_complete"] and not observed["end_to_end_cost_complete"]
        assert observed["observed_cost_usd"] == observed["calls"][0]["observed_cost_usd"] > 0
        assert observed["pdf_reference"]["observation"]["observed_tokens"] == 142
    volume.guard.quiesced()
    _matches(restored, volume.sandbox, volume.frozen)
    _matches(volume.source, volume.sandbox, volume.frozen)


def test_intact_old_snapshot_is_not_freshness_or_paid_resume_authority(volume, monkeypatch, application_readers):
    """Old bytes remain intact/readable while later consumption is absent from them."""
    restored = _copy_fresh(volume.source, volume.sandbox / "old-snapshot", volume.sandbox, volume.frozen)
    _roots(monkeypatch, volume.source)
    monkeypatch.setattr(runs, "_daily_counts", {volume.owner: 3})
    with runs._registry_lock:
        runs._write_daily_ledger_locked(DAY)
    ticket, _ = receipts.claim(volume.source, _key(6), volume.owner, "run", {"synthetic_later": True})
    ticket.bind(CHILD_ID)
    # Later synthetic settlement is absent from the intact older copy too.
    collector = aux.Collector(volume.source / RUN_ID / aux.FILE_NAME)
    collector.settle(1, aux.Tokens(prompt_tokens=5, completion_tokens=3), "returned")
    collector.finish()
    later = _inventory(volume.source, volume.sandbox)
    assert later != volume.frozen
    # Its OWN trusted earlier manifest passes: integrity is not freshness.
    _matches(restored, volume.sandbox, volume.frozen)
    with _source_unavailable(volume):
        _read_restored(volume, restored, monkeypatch, application_readers)
    with pytest.raises(receipts.ReceiptError) as missing:
        receipts.lookup(restored, _key(6), volume.owner)
    assert missing.value.code == "receipt_not_found"
    _roots(monkeypatch, volume.source)
    with runs._registry_lock:
        assert runs._read_daily_ledger_locked(DAY)[volume.owner] == 3
    assert receipts.lookup(volume.source, _key(6), volume.owner)["resource_id"] == CHILD_ID
    current = runs.get_state(RUN_ID)["auxiliary_usage"]
    assert current["observed_tokens"] == current["total_tokens"] == 26 and current["coverage"] == "complete"
    assert aux.read_summary(restored / RUN_ID / aux.FILE_NAME)["observed_tokens"] == 18
    _matches(restored, volume.sandbox, volume.frozen)
    _matches(volume.source, volume.sandbox, later)


def test_copy_refuses_unquiesced_or_occupied_or_outside_paths(volume, tmp_path):
    """No WAL/journal merging, online overwrite, in-place copy or outside destination."""
    target = volume.sandbox / "restored"
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = volume.source / (".paid-receipts.sqlite3" + suffix)
        sidecar.write_bytes(b"synthetic leftover")
        with pytest.raises(InventoryRejected, match="unquiesced"):
            _copy_fresh(volume.source, target, volume.sandbox, volume.frozen)
        assert not target.exists()
        sidecar.unlink()
    target.mkdir()
    sentinel = target / ".keep"
    sentinel.write_bytes(b"synthetic keep")
    for destination in (target, sentinel, volume.source, volume.source / "nested", tmp_path / "outside"):
        with pytest.raises(InventoryRejected):
            _copy_fresh(volume.source, destination, volume.sandbox, volume.frozen)
    assert sentinel.read_bytes() == b"synthetic keep"
    assert not (volume.source / "nested").exists() and not (tmp_path / "outside").exists()
    _matches(volume.source, volume.sandbox, volume.frozen)


def test_reparse_and_symlink_are_rejected_before_external_traversal(volume, tmp_path, monkeypatch):
    """Reject reparse/symlink metadata without requiring Windows link privileges.

    Windows observations are injected metadata, not real links or junctions.
    POSIX additionally exercises a real directory symlink without skipping.
    """
    real_lstat = Path.lstat
    for kind in ("reparse", "symlink"):
        for target in (volume.source / LEDGER, volume.source / LOCATOR_DIR, volume.source):
            def linked(path, *args, _target=target, _kind=kind, **kwargs):
                result = real_lstat(path, *args, **kwargs)
                if path == _target:
                    return SimpleNamespace(
                        st_mode=stat.S_IFLNK if _kind == "symlink" else result.st_mode,
                        st_file_attributes=0x400 if _kind == "reparse" else 0,
                    )
                return result

            with monkeypatch.context() as patch:
                patch.setattr(Path, "lstat", linked)
                with pytest.raises(InventoryRejected, match="link/reparse"):
                    _inventory(volume.source, volume.sandbox)
    _matches(volume.source, volume.sandbox, volume.frozen)
    if os.name != "nt":
        external = tmp_path / "external-synthetic"
        external.mkdir()
        (external / "keep").write_bytes(b"untouched")
        link = volume.source / ".escape"
        link.symlink_to(external, target_is_directory=True)
        try:
            with pytest.raises(InventoryRejected, match="link/reparse"):
                _inventory(volume.source, volume.sandbox)
            assert (external / "keep").read_bytes() == b"untouched"
        finally:
            link.unlink()
