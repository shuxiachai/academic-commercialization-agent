"""Actual native HTTP/controller seams, exclusively with synthetic intercepted data."""

import asyncio
from contextlib import suppress
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import socket
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
import httpx
import pytest

from academic_agent import report_evidence_qwen_canary as base
from academic_agent import report_evidence_source_locator as locator
from academic_agent import saved_source_receipt_qwen_adapter as adapter
from academic_agent.report_evidence_catalog_followup import build_catalog
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource
from academic_agent.saved_source_loader import SavedSourceLoader
from api import access, runs
from api.saved_source_controller import SavedSourceController
from api.saved_source_receipt_app import create_saved_source_receipt_app

KEY = "sk-fictional-rq-offline-no-real-credential"
CODE = "synthetic-rq-owner-code"
USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
FIXTURE = Path(__file__).parent / "fixtures/saved_source_receipt_qwen_canary.json"
FIXTURE_SHA = "b82f67446853685195d03b8e6e9f0a99c5aa11705f10752420ca558907f06216"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def request(binding):
    return locator._request(binding.question, build_catalog(binding.snapshot))


def response(case_id="RQ01"):
    message = {"role": "assistant", "content": '{"action":"decline"}'}
    if case_id == "RQ01":
        message = {"role": "assistant", "content": None, "tool_calls": [{
            "id": "fictional-rq-call", "type": "function", "function": {
                "name": "read_source", "arguments": '{"source_id":"A12"}'}}]}
    return {"model": base.MODEL, "usage": dict(USAGE), "choices": [{
        "index": 0, "message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}]}


def events(batch):
    return [json.loads(path.read_bytes()) for path in sorted(batch.output_dir.glob("event-*.json"))]


def facts(state, index=0):
    """Gate unit inputs are not claimed to be actual Chromium observations."""
    binding = state.bindings[index]
    return {
        "run_id": binding.run_id, "receipt_key_sha256": state.key_hashes[index],
        "snapshot_sha256_before": binding.snapshot.snapshot_hash,
        "snapshot_sha256_after": binding.snapshot.snapshot_hash,
        "post_requests": 1, "get_requests": 1, "callback_entries": 1, "daily_admissions": 1,
        "active_paid_operations_after_drain": 0, "physical_threads_after_drain": 0,
        "http_contract_passed": True, "reference_passed": True, "replay_passed": True,
        "browser_delivery_passed": True, "refresh_no_redispatch_passed": True, "source_identity_passed": True}


@pytest.fixture
def native(tmp_path, monkeypatch):
    """Keep the original HTTP primitive and real fsync; intercept only transport I/O."""
    raw = FIXTURE.read_bytes()
    assert digest(raw) == FIXTURE_SHA
    bindings = [adapter.CaseBinding(
        row["case_id"], row["run_id"],
        ReportEvidenceSnapshot(report_ref=row["run_id"], sources=tuple(SnapshotSource(**s) for s in row["sources"])),
        row["question"], adapter.ADAPTER_IDENTITY) for row in json.loads(raw)["cases"]]
    manifest = {"schema_version": 1, "fixture_sha256": FIXTURE_SHA,
                "source_identity_sha256": "e" * 64, "cases": [b.manifest_entry() for b in bindings]}
    batch = adapter.BatchGate(tmp_path / "batch", manifest)
    state = SimpleNamespace(
        batch=batch, bindings=bindings, manifest=manifest,
        ledgers=[adapter.LocatorQwenLedger(batch.output_dir / b.case_id) for b in bindings],
        key_hashes=[digest(f"fictional-receipt-{i}".encode()) for i in range(2)],
        requests=[], at_dispatch=[], response=response(), status=200, headers={},
        exception=None, raw=None, blocker=None, fsyncs=0, transport_options=[], client_options=[])
    real_client, real_fsync = httpx.AsyncClient, adapter.os.fsync
    denied = Mock(side_effect=AssertionError("Unintercepted provider/network access"))
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", denied)

    def dispatch(wire):
        state.requests.append(wire)
        state.at_dispatch.append((events(batch), state.fsyncs))
        if state.blocker:
            state.blocker()
        if state.exception is not None:
            raise state.exception
        return httpx.Response(state.status, headers=state.headers,
                              stream=httpx.ByteStream(base._encoded(state.response) if state.raw is None else state.raw))

    def transport(**kwargs):
        state.transport_options.append(kwargs)
        return httpx.MockTransport(dispatch)

    def client(**kwargs):
        state.client_options.append(kwargs)
        assert isinstance(kwargs["transport"], httpx.MockTransport)
        return real_client(**kwargs)

    def fsync(fd):
        real_fsync(fd)
        state.fsyncs += 1

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setattr(adapter.os, "fsync", fsync)
    state.bind = lambda i=0: batch.bind_http_intent(bindings[i].case_id, state.key_hashes[i], access.owner_id(CODE))
    state.selector = lambda i=0, check=None: adapter.BoundCaseSelector(
        KEY, bindings[i], batch, state.ledgers[i], check_identity=check or (lambda: None))
    yield state
    denied.assert_not_called()


def test_exact_http_metadata_only_fsynced_both_gates_and_two_ordered_cases(native):
    """Full native bytes match both journals; actual reads never reach provider input."""
    for index, binding in enumerate(native.bindings):
        native.bind(index)
        native.response = response(binding.case_id)
        checks = []
        selector = native.selector(index, lambda checks=checks: checks.append("checked"))
        result = locator.locate_saved_source(binding.snapshot, binding.question, selector=selector)
        wire = native.requests[index]
        assert wire.content == base._encoded(adapter._body(request(binding)))
        assert digest(wire.content) == binding.manifest_entry()["wire_sha256"]
        assert wire.url == base.ENDPOINT and wire.method == "POST"
        assert wire.headers["authorization"] == "Bearer " + KEY and wire.headers["accept-encoding"] == "identity"
        assert all(source.summary not in wire.content.decode("ascii") for source in binding.snapshot.sources)
        assert b"RQ01_LOCAL_ONLY" not in wire.content
        journal = [json.loads(line) for line in (native.ledgers[index].output_dir / "events.jsonl").read_bytes().splitlines()]
        assert [item["event"] for item in journal] == ["request_reserved", "request_finished"]
        assert base._encoded(journal[0]["request"]) == wire.content
        at_post, fsyncs = native.at_dispatch[index]
        assert fsyncs > 0
        assert [item["event"] for item in at_post][-3:] == [
            "aggregate_reserved", "native_transport_entry", "native_http_entry"]
        assert checks == ["checked", "checked"]
        assert selector.audit()["native_http_entries"] == selector.native_transport_entries == 1
        assert selector.audit()["selection"] == {
            "kind": "read_source" if index == 0 else "decline", "source_id": "A12" if index == 0 else None}
        assert result.state == ("excerpt" if index == 0 else "declined")
        assert result.read_attempts == result.read_completed == (1 if index == 0 else 0)
        before = events(native.batch)
        native.batch.observe_native(binding.case_id, native.ledgers[index])
        assert events(native.batch) == before
        native.batch.complete_case(binding.case_id, facts(native, index))
    summary = native.batch.summary()
    assert summary["attempts_consumed"] == summary["native_transport_entries"] == summary["native_http_entries"] == 2
    assert summary["native_reserved_requests"] == summary["provider_responses_received"] == 2
    assert summary["unknown_usage_requests"] == 0 and summary["stop_reason"] is None
    assert summary["case_gates"] == {"RQ01": True, "RQ02": True}
    assert Decimal(summary["budget_consumed_usd"]) == Decimal("0.022298624")
    assert native.transport_options == [{"retries": 0, "verify": True, "trust_env": False}] * 2
    assert all(o["timeout"].connect == 10 and o["timeout"].read == 60 and o["verify"] is True
               and o["follow_redirects"] is o["trust_env"] is False for o in native.client_options)


@pytest.mark.parametrize("part", ["question", "schema", "extra", "keyword", "arity", "non_dict"])
def test_request_bind_rejects_before_native_entry_and_consumes_attempt(native, part):
    """A shared failure stops fresh wrappers, not just the originally called object."""
    native.bind()
    selector, peer = native.selector(), native.selector()
    value = request(native.bindings[0])
    args, kwargs = (value,), {}
    if part == "question":
        value["messages"][1]["content"] += " changed"
    elif part == "schema":
        value["tools"][0]["function"]["parameters"]["additionalProperties"] = 0
    elif part == "extra":
        value["extra"] = KEY
    elif part == "keyword":
        args, kwargs = (), {"request": value}
    elif part == "arity":
        args = (value, value)
    else:
        args = (None,)
    with pytest.raises(base.CanaryStopped, match="^request_identity_mismatch$"):
        selector(*args, **kwargs)
    assert native.batch.summary()["attempts_consumed"] == 1 and selector.native_transport_entries == 0
    assert native.batch.summary()["budget_consumed_usd"] == "0"
    with pytest.raises(base.CanaryStopped, match="^batch_already_stopped$"):
        peer(request(native.bindings[0]))
    assert native.requests == []
    assert KEY not in "".join(path.read_text() for path in native.batch.output_dir.glob("*.json"))


def test_once_guard_lives_in_shared_batch_not_wrapper(native):
    """Removing the aggregate once guard fails even without calling the old transport."""
    native.bind()
    binding = native.bindings[0]
    entry = binding.manifest_entry()
    native.batch.reserve(binding, entry["callback_sha256"], entry["wire_sha256"])
    with pytest.raises(base.CanaryStopped, match="^attempt_consumed$"):
        native.batch.reserve(binding, entry["callback_sha256"], entry["wire_sha256"])
    assert native.batch.summary()["attempts_consumed"] == 1 and native.requests == []


def test_repeated_instances_cannot_dispatch_twice(native):
    """Two wrappers prepared before execution still share one consumed attempt."""
    native.bind()
    first, peer = native.selector(), native.selector()
    first(request(native.bindings[0]))
    with pytest.raises(base.CanaryStopped, match="^attempt_consumed$"):
        peer(request(native.bindings[0]))
    assert len(native.requests) == 1 and peer.native_transport_entries == 0


def test_aggregate_budget_blocks_before_old_ledger_or_http(native, monkeypatch):
    """A budget-guard bypass must dispatch intercepted HTTP and turn this test red."""
    native.bind()
    monkeypatch.setattr(adapter, "USD_LIMIT", Decimal("0.01"))
    with pytest.raises(base.CanaryStopped, match="^budget_limit$"):
        native.selector()(request(native.bindings[0]))
    assert native.requests == [] and native.ledgers[0].records == []
    assert native.batch.summary()["attempts_consumed"] == 1


@pytest.mark.parametrize("after_first", [False, True])
def test_next_case_requires_completion_not_just_native_success(native, after_first):
    """A native response is insufficient to admit the next HTTP intent."""
    if after_first:
        native.bind()
        native.selector()(request(native.bindings[0]))
    with pytest.raises(base.CanaryStopped, match="^case_order$"):
        native.bind(1)
    assert len(native.requests) == int(after_first)


@pytest.mark.parametrize("phase", ["aggregate", "old_reservation", "http_edge", "native_finish", "observation"])
def test_persistence_faults_never_refund_or_cross_dispatch_boundary(native, monkeypatch, phase):
    """Pre-dispatch faults yield zero HTTP; post-dispatch faults retain known usage."""
    native.bind()
    original = adapter.atomic_write_once
    def publish(path, value):
        target = {"aggregate": "aggregate_reserved", "http_edge": "native_http_entry",
                  "observation": "native_observed"}.get(phase)
        if target is not None and value.get("event") == target:
            raise OSError("PRIVATE_PATH_" + KEY)
        return original(path, value)
    monkeypatch.setattr(adapter, "atomic_write_once", publish)
    ledger = native.ledgers[0]
    append = ledger._append
    def old_append(event):
        if event["event"] == {"old_reservation": "request_reserved",
                             "native_finish": "request_finished"}.get(phase):
            raise OSError("PRIVATE_PATH_" + KEY)
        return append(event)
    monkeypatch.setattr(ledger, "_append", old_append)
    with pytest.raises(base.CanaryStopped) as caught:
        native.selector()(request(native.bindings[0]))
    assert KEY not in str(caught.value) and caught.value.__suppress_context__
    dispatched = phase in {"native_finish", "observation"}
    assert len(native.requests) == int(dispatched)
    summary = native.batch.summary()
    assert Decimal(summary["budget_consumed_usd"]) >= base.RESERVATION_USD
    if dispatched:
        assert Decimal(summary["known_usage_estimated_usd"]) > 0
    with pytest.raises(base.CanaryStopped):
        native.bind(1)


@pytest.mark.parametrize("fault", ["usage", "timeout", "protocol", "model", "redirect", "encoding", "oversize", "tokens"])
def test_native_failure_stops_next_case_preserves_known_usage(native, fault):
    """The provider's known usage survives invalid model/selection/token acceptance."""
    native.bind()
    if fault == "usage":
        native.response["usage"]["total_tokens"] += 1
    elif fault == "timeout":
        native.exception = httpx.ReadTimeout("PRIVATE " + KEY)
    elif fault == "protocol":
        native.response["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = '{"source_id":"A999"}'
    elif fault == "model":
        native.response["model"] = "other-model"
    elif fault == "redirect":
        native.status, native.headers = 302, {"location": "https://example.invalid/"}
    elif fault == "encoding":
        native.headers = {"content-encoding": "gzip"}
    elif fault == "oversize":
        native.raw = b"x" * (64 * 1024 + 1)
    else:
        native.response["usage"] = {"prompt_tokens": 1_000_000, "completion_tokens": 20, "total_tokens": 1_000_020}
    with pytest.raises(base.CanaryStopped):
        native.selector()(request(native.bindings[0]))
    summary = native.batch.summary()
    assert len(native.requests) == summary["native_http_entries"] == 1 and summary["stop_reason"] is not None
    if fault in {"protocol", "model", "tokens"}:
        assert summary["unknown_usage_requests"] == 0 and Decimal(summary["known_usage_estimated_usd"]) > 0
    else:
        assert summary["unknown_usage_requests"] == 1
    if fault == "tokens":
        assert Decimal(summary["budget_consumed_usd"]) > Decimal("0.05")
    with pytest.raises(base.CanaryStopped):
        native.bind(1)


@pytest.mark.parametrize("when", ["before", "after"])
def test_identity_drift_before_and_after_native_never_releases_next_case(native, when):
    """Post-dispatch identity failures retain usage rather than claim a free failure."""
    native.bind()
    calls = []
    def check():
        calls.append(True)
        if len(calls) == (1 if when == "before" else 2):
            raise RuntimeError(KEY)
    with pytest.raises(base.CanaryStopped, match="^source_identity_mismatch$"):
        native.selector(check=check)(request(native.bindings[0]))
    assert len(native.requests) == int(when == "after")
    if when == "after":
        assert native.batch.summary()["unknown_usage_requests"] == 0
    with pytest.raises(base.CanaryStopped):
        native.bind(1)


@pytest.mark.parametrize("field,value", [
    ("reference_passed", False), ("http_contract_passed", 1), ("replay_passed", False),
    ("browser_delivery_passed", False), ("refresh_no_redispatch_passed", False),
    ("source_identity_passed", False), ("get_requests", 0), ("post_requests", True),
    ("daily_admissions", 2), ("callback_entries", 2), ("active_paid_operations_after_drain", 1),
    ("physical_threads_after_drain", 1), ("receipt_key_sha256", "0" * 64),
    ("snapshot_sha256_after", "0" * 64), ("run_id", "invalid")])
def test_case_gate_requires_exact_independent_facts(native, field, value):
    """Native success cannot replace failed, malformed or stale browser facts."""
    native.bind()
    native.selector()(request(native.bindings[0]))
    supplied = facts(native)
    supplied[field] = value
    with pytest.raises(base.CanaryStopped, match="^case_gate_failed$"):
        native.batch.complete_case("RQ01", supplied)
    assert not native.batch.summary()["case_gates"]["RQ01"]


def test_snapshot_detached_and_report_reference_bound(native):
    """Object-level model mutation cannot alter a previously copied binding."""
    binding = native.bindings[0]
    clone = adapter.CaseBinding(binding.case_id, binding.run_id, binding.snapshot, binding.question, binding.selector_identity)
    expected = clone.manifest_entry()
    object.__setattr__(binding.snapshot.sources[0], "title", "changed")
    assert clone.manifest_entry() == expected
    with pytest.raises(base.CanaryStopped, match="^invalid_binding$"):
        adapter.CaseBinding(binding.case_id, native.bindings[1].run_id, clone.snapshot, binding.question, binding.selector_identity)


def test_atomic_publication_complete_no_replace_and_occupied_batch(native, tmp_path, monkeypatch):
    """A destination never exposes partial JSON and an occupied batch never resumes."""
    path = tmp_path / "complete.json"
    original = adapter.os.link
    observed = []
    def link(source, destination):
        observed.append(json.loads(Path(source).read_bytes()))
        assert not Path(destination).exists()
        return original(source, destination)
    monkeypatch.setattr(adapter.os, "link", link)
    adapter.atomic_write_once(path, {"complete": True})
    assert observed == [{"complete": True}]
    monkeypatch.setattr(adapter.os, "link", original)
    with pytest.raises(base.CanaryStopped, match="^persistence_failed$"):
        adapter.atomic_write_once(path, {"overwrite": True})
    assert json.loads(path.read_bytes()) == {"complete": True}
    with pytest.raises(base.CanaryStopped):
        adapter.BatchGate(native.batch.output_dir, native.manifest)


def test_actual_fsync_failure_before_attempt_publication_means_zero_http(native, monkeypatch):
    """A real publication-path flush failure must stop before either HTTP primitive."""
    native.bind()
    selector, peer = native.selector(), native.selector()
    def failed_fsync(_fd):
        raise OSError(KEY)
    monkeypatch.setattr(adapter.os, "fsync", failed_fsync)
    with pytest.raises(base.CanaryStopped, match="^persistence_failed$"):
        selector(request(native.bindings[0]))
    with pytest.raises(base.CanaryStopped, match="^batch_already_stopped$"):
        peer(request(native.bindings[0]))
    assert native.requests == [] and native.ledgers[0].records == []
    assert native.batch.summary()["attempts_consumed"] == 1


@pytest.mark.parametrize("change", ["extra", "missing", "boolean_version", "bad_hash", "order"])
def test_manifest_is_exact_hash_only_identity_without_arbitrary_fields(native, tmp_path, change):
    """Free-form manifest diagnostics or malformed identities never reach disk."""
    manifest = json.loads(json.dumps(native.manifest))
    if change == "extra":
        manifest["private"] = KEY
    elif change == "missing":
        del manifest["fixture_sha256"]
    elif change == "boolean_version":
        manifest["schema_version"] = True
    elif change == "bad_hash":
        manifest["cases"][0]["wire_sha256"] = KEY
    else:
        manifest["cases"].reverse()
    path = tmp_path / "invalid-batch"
    with pytest.raises(base.CanaryStopped, match="^invalid_manifest$"):
        adapter.BatchGate(path, manifest)
    assert not path.exists()


def test_native_journal_change_before_completion_cannot_admit_next_case(native):
    """Completion rechecks native observations instead of trusting an old success flag."""
    native.bind()
    native.selector()(request(native.bindings[0]))
    native.ledgers[0].pending = 1
    with pytest.raises(base.CanaryStopped, match="^native_observation_changed$"):
        native.batch.complete_case("RQ01", facts(native))
    assert not native.batch.summary()["case_gates"]["RQ01"]


@pytest.mark.parametrize("malformed", ["extra", "missing"])
def test_case_facts_cannot_default_fill_or_save_arbitrary_fields(native, malformed):
    """The checked facts contract is exact, not a bucket for caller diagnostics."""
    native.bind()
    native.selector()(request(native.bindings[0]))
    supplied = facts(native)
    if malformed == "extra":
        supplied["private"] = KEY
    else:
        del supplied["physical_threads_after_drain"]
    with pytest.raises(base.CanaryStopped, match="^case_gate_failed$"):
        native.batch.complete_case("RQ01", supplied)


@pytest.fixture
def receipt(native, tmp_path, monkeypatch):
    """Real loader/owner files, authorization, admission, journal and factory."""
    root = tmp_path / "synthetic"
    root.mkdir()
    for name in ("_registry", "_stop_claims", "_inline_paid_operations", "_daily_counts"):
        monkeypatch.setattr(runs, name, {})
    monkeypatch.setattr(runs, "_daily_date", None)
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", root)
    monkeypatch.setattr(runs, "MAX_CONCURRENT", 1)
    monkeypatch.setattr(runs, "DAILY_CAP", 20)
    monkeypatch.setattr(access, "ACCESS_CODE", CODE)
    monkeypatch.setattr(access, "ACCESS_CODES", "")
    monkeypatch.setattr(access, "ADMIN_CODE", "")
    for binding in native.bindings:
        directory = root / binding.run_id
        directory.mkdir()
        (directory / ".owner").write_text(access.owner_id(CODE), encoding="utf-8")
        registry = {group + "_sources": [] for group in ("academic", "patent", "market")}
        for saved in binding.snapshot.sources:
            row = saved.model_dump(exclude={"group", "summary", "origin"})
            row.update(evidence_summary=saved.summary, summary_source=saved.origin)
            registry[saved.group + "_sources"].append(row)
        (directory / "validated_sources.json").write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    native.receipt_keys = [f"v1.{int(time.time())}." + str(i + 1) * 64 for i in range(2)]
    native.key_hashes = [digest(key.encode("ascii")) for key in native.receipt_keys]
    yield root
    assert runs.active_paid_operation_count() == 0


def test_real_http_controller_native_and_get_replay_keep_all_fourteen_fields(native, receipt):
    """Actual POST/GET preserve exact delivery, one native call and original billing fields."""
    binding = native.bindings[0]
    native.bind()
    selector = native.selector()
    app = create_saved_source_receipt_app(load_snapshot=SavedSourceLoader(receipt), journal_root=receipt,
                                         selector=selector, selector_identity=binding.selector_identity)
    headers = {"X-Access-Code": CODE, "Idempotency-Key": native.receipt_keys[0]}
    with TestClient(app) as client:
        posted = client.post(f"/api/runs/{binding.run_id}/saved-source-location",
                             headers=headers, json={"question": binding.question})
        recovered = client.get("/api/saved-source-receipts", headers=headers)
    assert posted.status_code == recovered.status_code == 200
    first, replay = posted.json(), recovered.json()
    assert set(first) == set(replay) == {
        "schema_version", "operation", "state", "run_id", "expires_at", "admission_state",
        "provider_usage", "provider_cost", "error_code", "delivery", "delivery_snapshot_reads",
        "delivery_source_reads", "result", "receipt_key_sha256"}
    assert first["result"] == replay["result"]
    assert first["result"]["saved_text"]["text"] == binding.snapshot.sources[1].summary
    assert first["delivery_snapshot_reads"] == first["delivery_source_reads"] == 0
    assert replay["delivery_snapshot_reads"] == replay["delivery_source_reads"] == 1
    assert first["receipt_key_sha256"] == replay["receipt_key_sha256"] == native.key_hashes[0]
    assert all(reply[key] == "not_observed" for reply in (first, replay) for key in ("provider_usage", "provider_cost"))
    assert len(native.requests) == runs._daily_counts[access.owner_id(CODE)] == selector.audit()["callback_entries"] == 1


def test_cancelled_controller_retains_real_native_thread_and_validated_receipt(native, receipt):
    """A cancelled waiter cannot free the paid lease of an actual blocked native thread."""
    native.bind()
    entered, release = threading.Event(), threading.Event()
    def block():
        entered.set()
        assert release.wait(10), "Intercepted HTTP was never released"
    native.blocker = block
    binding = native.bindings[0]
    selector = native.selector()
    controller = SavedSourceController(SavedSourceLoader(receipt), receipt, selector, binding.selector_identity)
    async def scenario():
        task = asyncio.create_task(controller.execute(native.receipt_keys[0], binding.run_id, binding.question, CODE))
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert runs.active_paid_operation_count() == 1
            assert (await controller.lookup(native.receipt_keys[0], CODE))["state"] == "pending"
            assert native.batch.summary()["native_reserved_requests"] == len(native.requests) == 1
        finally:
            release.set()
            with suppress(asyncio.CancelledError):
                await task
            await controller.close()
        replay = await controller.lookup(native.receipt_keys[0], CODE)
        assert replay["state"] == "completed" and replay["delivery"] == "available"
        assert replay["result"]["saved_text"]["text"] == binding.snapshot.sources[1].summary
        assert runs.active_paid_operation_count() == 0
    asyncio.run(scenario())
    assert len(native.requests) == selector.audit()["native_http_entries"] == runs._daily_counts[access.owner_id(CODE)] == 1
