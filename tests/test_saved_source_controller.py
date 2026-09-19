"""Actual shared admission/journal with scripted selectors; no provider calls."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
import json
import secrets
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from unittest.mock import Mock

import pytest

from academic_agent import report_evidence_source_locator as locator
from academic_agent.saved_source_loader import SavedSourceLoader
from api import access, runs
from api import saved_source_controller as controller
from api import saved_source_receipts as receipts

RUN_ID = "20260919T123456Z-0123456789abcdef0123456789abcdef"
CODE = "synthetic-owner-code"
TEXT = "  SYNTHETIC private \u6d4b\u8bd5\U0001f642e\u0301\r\n<script>inert</script>\t "
QUESTION = "  private question \r\n"


def key():
    return f"v1.{int(time.time())}.{secrets.token_hex(32)}"


def select(_request):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": "selection", "type": "function", "function": {
            "name": "read_source", "arguments": '{"source_id":"A1"}',
        },
    }]}


def saved_registry(text=TEXT):
    return {"academic_sources": [{
        "source_id": "A1", "title": "SYNTHETIC private title", "publisher": " original publisher ",
        "source_type": "academic_paper", "url": "https://example.invalid/private-locator",
        "doi": " exact old DOI ", "published_date": "historical date", "accessed_date": " exact date ",
        "evidence_summary": text, "summary_source": "abstract",
    }], "patent_sources": [], "market_sources": []}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """Use the real global paid pool with synthetic owner files and isolated disk."""
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(runs, "_registry", {})
    monkeypatch.setattr(runs, "_stop_claims", {})
    monkeypatch.setattr(runs, "_inline_paid_operations", {})
    monkeypatch.setattr(runs, "_daily_counts", {})
    monkeypatch.setattr(runs, "_daily_date", None)
    monkeypatch.setattr(runs, "MAX_CONCURRENT", 1)
    monkeypatch.setattr(runs, "DAILY_CAP", 50)
    monkeypatch.setattr(access, "ACCESS_CODE", CODE)
    monkeypatch.setattr(access, "ACCESS_CODES", "synthetic-other-code")
    monkeypatch.setattr(access, "ADMIN_CODE", "synthetic-admin-code")
    monkeypatch.setattr(socket, "create_connection", Mock(side_effect=AssertionError("No provider/network access")))
    root = tmp_path / RUN_ID
    root.mkdir()
    # The existing owner-marker name, not a mock of owner_of, is the boundary.
    (root / ".owner").write_text(access.owner_id(CODE), encoding="utf-8")
    path = root / "validated_sources.json"
    path.write_text(json.dumps(saved_registry(), ensure_ascii=False), encoding="utf-8")
    created = []

    def make(selector=select, load=None, identity="scripted-v1"):
        value = controller.SavedSourceController(load or SavedSourceLoader(tmp_path), tmp_path,
                                                selector=selector, selector_identity=identity)
        created.append(value)
        return value

    yield make, path, tmp_path
    for value in created:
        asyncio.run(value.close())
    assert runs.active_paid_operation_count() == 0


def count():
    return runs._daily_counts.get(access.owner_id(CODE), 0)


def run(value, receipt_key=None, question=QUESTION, code=CODE):
    return asyncio.run(value.execute(receipt_key or key(), RUN_ID, question, code))


async def observed(event):
    assert await asyncio.to_thread(event.wait, 5), "Worker did not reach the scripted event"


def test_real_load_projection_and_replay_preserve_all_frozen_fields(setup, monkeypatch):
    """Fresh disk data must reconstruct the full result, never a fake callback."""
    make, _, root = setup
    calls = Mock(side_effect=select)
    value = make(calls)
    receipt_key = key()
    first = run(value, receipt_key)
    expected = json.loads(locator.render_locator_result(locator.locate_saved_source(
        SavedSourceLoader(root)(RUN_ID), QUESTION, selector=select)))
    assert first["state"] == "completed"
    assert first["delivery"] == "available"
    assert first["result"] == expected
    assert first["provider_cost"] == first["provider_usage"] == "not_observed"
    assert first["admission_state"] == "admitted"
    assert count() == calls.call_count == 1
    monkeypatch.setattr(controller, "locate_saved_source", Mock(side_effect=AssertionError("Replay cannot run locator")))
    second = run(value, receipt_key)
    third = asyncio.run(value.lookup(receipt_key, CODE))
    for replay in (second, third):
        assert replay["result"] == expected
        assert replay["delivery_snapshot_reads"] == replay["delivery_source_reads"] == 1
        assert replay["result"]["read_attempts"] == expected["read_attempts"]
    assert count() == calls.call_count == 1
    raw = (root / receipts.FILENAME).read_bytes()
    for private in (receipt_key, CODE, QUESTION, TEXT, "SYNTHETIC private title", "https://example.invalid/private-locator"):
        assert private.encode("utf-8") not in raw
    with sqlite3.connect(root / receipts.FILENAME) as db:
        projection = db.execute("SELECT projection FROM receipts").fetchone()[0]
    assert len(projection.encode()) <= 4096
    assert set(json.loads(projection)) == set(receipts.Projection.model_fields)


@pytest.mark.parametrize("text,response,reason", [
    (TEXT, None, "saved_text"), (None, None, "saved_text_missing"), ("", None, "saved_text_missing"),
    (" \t\r\n", None, "saved_text_blank"), ("x" * 1501, None, "selected_text_too_long"),
    (TEXT, {"role": "assistant", "content": '{"action":"decline"}'}, "selector_declined"),
    (TEXT, {"role": "assistant", "refusal": "PRIVATE refusal", "content": None}, "selector_refused"),
    (TEXT, {"invalid": "PRIVATE invalid"}, "invalid_assistant_message"),
])
def test_domain_results_replay_exactly_without_claiming_semantic_success(setup, text, response, reason):
    make, path, _ = setup
    path.write_text(json.dumps(saved_registry(text)), encoding="utf-8")
    calls = Mock(side_effect=select if response is None else lambda _: response)
    value = make(calls)
    receipt_key = key()
    initial = run(value, receipt_key)
    replay = asyncio.run(value.lookup(receipt_key, CODE))
    assert replay["state"] == initial["state"] == "completed"
    assert replay["result"] == initial["result"]
    assert replay["result"]["reason"] == reason
    assert replay["result"]["semantic_support"] == "not_assessed"
    assert count() == calls.call_count == 1


@pytest.mark.parametrize("error_site,reason", [("selector", "selector_error"), ("read", "read_error"),
                                             ("malformed_read", "invalid_read_result")])
def test_unavailable_and_failed_historical_read_counters_are_not_reexecuted(setup, monkeypatch, error_site, reason):
    make, _, _ = setup
    callback = Mock(side_effect=RuntimeError("PRIVATE callback error") if error_site == "selector" else select)
    if error_site != "selector":
        monkeypatch.setattr(locator, "read_source", Mock(side_effect=RuntimeError("PRIVATE read") if error_site == "read" else None,
                                                       return_value={"bad": "PRIVATE read"}))
    value = make(callback)
    receipt_key = key()
    first = run(value, receipt_key)
    monkeypatch.setattr(controller, "read_source", Mock(side_effect=AssertionError("Do not manufacture old reads")))
    replay = asyncio.run(value.lookup(receipt_key, CODE))
    assert replay["result"] == first["result"]
    assert replay["result"]["reason"] == reason
    assert replay["result"]["read_completed"] == int(error_site == "malformed_read")
    assert "PRIVATE" not in json.dumps(replay)
    assert count() == callback.call_count == 1


@pytest.mark.parametrize("case", ["empty", "budget"])
def test_no_callback_outcomes_never_charge_and_replay(setup, case):
    make, path, _ = setup
    if case == "empty":
        path.write_text(json.dumps({"academic_sources": [], "patent_sources": [], "market_sources": []}), encoding="utf-8")
    callback = Mock(side_effect=select)
    value = make(callback)
    receipt_key = key()
    question = "\U0001f642" * 4096 if case == "budget" else QUESTION
    first = run(value, receipt_key, question)
    replay = asyncio.run(value.lookup(receipt_key, CODE))
    assert replay["result"] == first["result"]
    assert replay["result"]["reason"] == ("empty_snapshot" if case == "empty" else "callback_budget_exceeded")
    assert replay["admission_state"] == "not_admitted"
    assert count() == callback.call_count == 0


def test_default_disabled_before_journal_load_but_rollback_lookup_works(setup):
    make, _, root = setup
    loader = Mock(side_effect=AssertionError("Disabled execute must not load"))
    disabled = make(None, loader)
    with pytest.raises(receipts.ReceiptError) as exc:
        run(disabled)
    assert exc.value.code == "selector_disabled"
    assert not (root / receipts.FILENAME).exists()
    receipt_key = key()
    original = run(make(), receipt_key)
    rolled_back = make(None)
    assert asyncio.run(rolled_back.lookup(receipt_key, CODE))["result"] == original["result"]
    assert loader.call_count == 0


@pytest.mark.parametrize("code", [None, "wrong", "synthetic-other-code", "synthetic-admin-code", "\u975eASCII\u4ee3\u7801"])
def test_invalid_or_cross_owner_execute_never_creates_journal(setup, code):
    make, _, root = setup
    with pytest.raises(receipts.ReceiptError) as exc:
        run(make(), code=code)
    assert exc.value.code == "access_denied"
    assert not (root / receipts.FILENAME).exists()
    assert count() == 0


def test_invalid_utf8_owner_marker_is_safe_denial_before_claim(setup):
    """A damaged owner file must not leak UnicodeDecodeError or authorize work."""
    make, path, root = setup
    (path.parent / ".owner").write_bytes(b"\xff")
    callback = Mock(side_effect=select)
    loader = Mock(side_effect=AssertionError("Denied ownership must not load sources"))
    value = make(callback, loader)
    with pytest.raises(receipts.ReceiptError) as exc:
        run(value)
    assert exc.value.code == "access_denied"
    assert str(exc.value) == "Saved-source receipt request could not be completed."
    assert exc.value.__suppress_context__ is True
    assert not (root / receipts.FILENAME).exists()
    assert callback.call_count == loader.call_count == count() == 0
    assert not value._threads


def test_gate_unset_ownerless_and_revoked_codes_do_not_select_operator_funding(setup, monkeypatch):
    make, path, _ = setup
    value = make()
    receipt_key = key()
    first = run(value, receipt_key)
    assert asyncio.run(value.lookup(receipt_key, "synthetic-admin-code"))["result"] == first["result"]
    with pytest.raises(receipts.ReceiptError):
        asyncio.run(value.lookup(receipt_key, "synthetic-other-code"))
    monkeypatch.setattr(access, "ACCESS_CODE", None)
    monkeypatch.setattr(access, "ACCESS_CODES", None)
    monkeypatch.setattr(access, "ADMIN_CODE", None)
    for operation in (lambda: run(value, receipt_key), lambda: asyncio.run(value.lookup(receipt_key, CODE))):
        with pytest.raises(receipts.ReceiptError) as exc:
            operation()
        assert exc.value.code == "access_denied"
    monkeypatch.setattr(access, "ACCESS_CODE", CODE)
    (path.parent / ".owner").unlink()
    with pytest.raises(receipts.ReceiptError) as exc:
        run(value)
    assert exc.value.code == "access_denied"
    assert count() == 1


@pytest.mark.parametrize("stage", ["loader", "selector"])
def test_cancellation_before_admission_is_free_after_entry_keeps_ownership(setup, stage):
    """Cancelled preprocessing never dispatches; admitted work still finalizes."""
    make, _, root = setup
    entered, release = threading.Event(), threading.Event()
    callback = Mock(side_effect=select)
    def load(run_id):
        if stage == "loader":
            entered.set()
            assert release.wait(5)
        return SavedSourceLoader(root)(run_id)
    def selected(request):
        if stage == "selector":
            entered.set()
            assert release.wait(5)
        return callback(request)
    value = make(selected, load)
    receipt_key = key()
    async def scenario():
        task = asyncio.create_task(value.execute(receipt_key, RUN_ID, QUESTION, CODE))
        await observed(entered)
        try:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert runs.active_paid_operation_count() == int(stage == "selector")
            assert (await value.lookup(receipt_key, CODE))["state"] == "pending"
            with pytest.raises(receipts.ReceiptError) as exc:
                await value.execute(key(), RUN_ID, QUESTION, CODE)
            assert exc.value.code == "locator_busy"
        finally:
            release.set()
        await value.close()
        return await value.lookup(receipt_key, CODE)
    reply = asyncio.run(scenario())
    assert count() == callback.call_count == int(stage == "selector")
    assert reply["state"] == ("completed" if stage == "selector" else "failed")
    assert reply["error_code"] == (None if stage == "selector" else "request_abandoned")
    assert reply["provider_cost"] == "not_observed"


def test_cancelled_queued_startup_never_creates_intent_or_loader_thread(setup):
    """Shielding a queued to_thread must not turn cancellation into later billing."""
    make, _, root = setup
    entered, release = threading.Event(), threading.Event()
    queued = threading.Event()
    callback = Mock(side_effect=select)
    value = make(callback)
    class ObservedPool(ThreadPoolExecutor):
        def submit(self, fn, *args, **kwargs):
            result = super().submit(fn, *args, **kwargs)
            if entered.is_set():
                queued.set()
            return result
    async def scenario():
        pool = ObservedPool(max_workers=1)
        asyncio.get_running_loop().set_default_executor(pool)
        def occupy():
            entered.set()
            assert release.wait(5)
        occupied = asyncio.get_running_loop().run_in_executor(None, occupy)
        while not entered.is_set():
            await asyncio.sleep(0)
        task = asyncio.create_task(value.execute(key(), RUN_ID, QUESTION, CODE))
        try:
            while not queued.is_set():
                await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()
        await occupied
        # This barrier runs after the abandoned begin in the single executor.
        await asyncio.to_thread(lambda: None)
    asyncio.run(asyncio.wait_for(scenario(), 8))
    assert not (root / receipts.FILENAME).exists()
    assert callback.call_count == count() == 0
    assert not value._threads


def test_revocation_while_loader_blocked_prevents_paid_entry(setup, monkeypatch):
    make, _, root = setup
    entered, release = threading.Event(), threading.Event()
    callback = Mock(side_effect=select)
    def load(run_id):
        entered.set()
        assert release.wait(5)
        return SavedSourceLoader(root)(run_id)
    value = make(callback, load)
    async def scenario():
        task = asyncio.create_task(value.execute(key(), RUN_ID, QUESTION, CODE))
        await observed(entered)
        monkeypatch.setattr(access, "ACCESS_CODE", None)
        release.set()
        return await task
    reply = asyncio.run(scenario())
    assert (reply["state"], reply["error_code"], reply["admission_state"]) == ("failed", "access_denied", "not_admitted")
    assert callback.call_count == count() == 0


@pytest.mark.parametrize("failure", ["loader", "start", "finalization", "admitted_write"])
def test_start_load_and_durable_finalization_failures_never_redispatch(setup, monkeypatch, failure):
    """Lost finalization is unknown; pre-entry failures do not consume quota."""
    make, _, _ = setup
    callback = Mock(side_effect=select)
    load = Mock(side_effect=RuntimeError("PRIVATE loader path")) if failure == "loader" else None
    value = make(callback, load)
    receipt_key = key()
    if failure == "start":
        original = threading.Thread.start
        def failed_start(thread):
            if thread.name == "saved-source-controller":
                raise RuntimeError("PRIVATE startup")
            return original(thread)
        monkeypatch.setattr(threading.Thread, "start", failed_start)
    if failure in {"finalization", "admitted_write"}:
        monkeypatch.setattr(receipts.Ticket, "complete" if failure == "finalization" else "admitted",
                            Mock(side_effect=receipts.ReceiptError("receipt_unavailable")))
        with pytest.raises(receipts.ReceiptError) as exc:
            run(value, receipt_key)
        assert exc.value.code == "receipt_unavailable"
    else:
        first = run(value, receipt_key)
        assert first["state"] == "failed"
        assert first["error_code"] == ("saved_source_unavailable" if failure == "loader" else "execution_unavailable")
    asyncio.run(value.close())
    replay = asyncio.run(value.lookup(receipt_key, CODE))
    assert replay["state"] == ("unknown" if failure in {"finalization", "admitted_write"} else "failed")
    assert replay["provider_cost"] == "not_observed"
    assert callback.call_count == int(failure == "finalization")
    assert count() == int(failure in {"finalization", "admitted_write"})
    # A new controller cannot reset an unresolved journal reservation.
    other = make(callback)
    assert run(other, receipt_key)["state"] == replay["state"]
    assert callback.call_count == int(failure == "finalization")


def test_physical_post_target_exit_retains_shared_and_local_ownership_and_drains(setup, monkeypatch):
    """A returned target is not physical exit, even after durable completion."""
    make, _, _ = setup
    exited_target, release = threading.Event(), threading.Event()
    original = threading.Thread
    class DelayedExit(original):
        def run(self):
            super().run()
            if self.name == "saved-source-controller":
                exited_target.set()
                assert release.wait(8)
    monkeypatch.setattr(threading, "Thread", DelayedExit)
    value = make()
    async def scenario():
        reply = await value.execute(key(), RUN_ID, QUESTION, CODE)
        await observed(exited_target)
        closer = None
        try:
            assert reply["state"] == "completed"
            assert runs.active_paid_operation_count() == 1
            with pytest.raises(receipts.ReceiptError) as exc:
                await value.execute(key(), RUN_ID, QUESTION, CODE)
            assert exc.value.code == "locator_busy"
            with pytest.raises(runs.ConcurrencyLimitReached), runs.reserve_inline_paid_operation(owner=access.owner_id(CODE), byok=False):
                pytest.fail("Physical exit still owns shared capacity")
            closer = asyncio.create_task(value.close())
            while not value._closed:
                await asyncio.sleep(0)
            assert not closer.done()
            closer.cancel()
            # Cancellation cannot retract close's physical drain. This
            # scheduled turn also proves the event loop is not blocked by join.
            await asyncio.sleep(0)
            assert not closer.done()
            with pytest.raises(receipts.ReceiptError) as exc:
                await value.execute(key(), RUN_ID, QUESTION, CODE)
            assert exc.value.code == "controller_closed"
        finally:
            release.set()
            if closer is not None:
                with suppress(asyncio.CancelledError):
                    await closer
        assert runs.active_paid_operation_count() == 0
        with runs.reserve_inline_paid_operation(owner=access.owner_id(CODE), byok=False):
            assert runs.active_paid_operation_count() == 1
    asyncio.run(asyncio.wait_for(scenario(), 10))


def test_new_process_reads_completed_and_orphan_pending_without_selector(setup):
    """Restart observation does not invent a local task or redispatch the intent."""
    make, _, root = setup
    value = make()
    completed_key, pending_key = key(), key()
    first = run(value, completed_key)
    receipts.Journal(root).claim(pending_key, access.owner_id(CODE), RUN_ID, QUESTION, "scripted-v1")
    script = '''import asyncio, json, sys
from academic_agent.saved_source_loader import SavedSourceLoader
from api import access
from api.saved_source_controller import SavedSourceController
data = json.load(sys.stdin)
access.ACCESS_CODE = data['code']
access.ACCESS_CODES = access.ADMIN_CODE = None
value = SavedSourceController(SavedSourceLoader(data['root']), data['root'])
async def check():
    results = [await value.lookup(key, data['code']) for key in data['keys']]
    await value.close()
    return results
print(json.dumps(asyncio.run(check())))
'''
    result = subprocess.run([sys.executable, "-X", "utf8", "-c", script], input=json.dumps({
        "root": str(root), "code": CODE, "keys": [completed_key, pending_key],
    }), text=True, encoding="utf-8", capture_output=True, timeout=15, check=True)
    completed, pending = json.loads(result.stdout)
    assert completed["result"] == first["result"]
    assert completed["delivery_snapshot_reads"] == 1
    assert (pending["state"], pending["admission_state"]) == ("unknown", "not_admitted")
    assert pending["provider_cost"] == "not_observed"
    assert count() == 1


def test_thread_lease_byok_share_and_existing_inline_behavior(setup, monkeypatch):
    """New tokens share existing BYOK/global limits; inline lifetime is unchanged."""
    monkeypatch.setattr(runs, "MAX_CONCURRENT", 2)
    monkeypatch.setattr(runs, "BYOK_MAX_CONCURRENT", 1)
    entered, release = threading.Event(), threading.Event()
    def worker():
        runs.reserve_thread_paid_operation(owner=None, byok=True)
        entered.set()
        assert release.wait(5)
    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert entered.wait(5)
        with pytest.raises(runs.ConcurrencyLimitReached), runs.reserve_inline_paid_operation(owner=None, byok=True):
            pytest.fail("BYOK share must count dedicated thread")
        with runs.reserve_inline_paid_operation(owner=access.owner_id(CODE), byok=False):
            assert runs.active_paid_operation_count() == 2
        assert runs.active_paid_operation_count() == 1
    finally:
        release.set()
        thread.join()
    assert runs.active_paid_operation_count() == 0
    assert count() == 1


def test_fingerprint_conflicts_and_client_control_fields_rejected(setup):
    make, _, _ = setup
    receipt_key = key()
    value = make()
    run(value, receipt_key)
    for candidate, question in ((value, QUESTION.strip()), (make(identity="scripted-v2"), QUESTION)):
        with pytest.raises(receipts.ReceiptError) as exc:
            run(candidate, receipt_key, question)
        assert exc.value.code == "receipt_conflict"
    for field in ("owner", "model", "endpoint", "byok"):
        with pytest.raises(TypeError):
            asyncio.run(value.execute(key(), RUN_ID, QUESTION, CODE, **{field: "untrusted"}))
    assert count() == 1


@pytest.mark.parametrize("damage,delivery", [("delete", "expired"), ("text", "changed"), ("title", "changed"),
                                            ("unreadable", "unavailable"), ("hash", "unavailable"),
                                            ("read", "unavailable"), ("read_error", "unavailable"),
                                            ("render", "unavailable")])
def test_current_bytes_and_projection_digest_gate_every_replay(setup, monkeypatch, damage, delivery):
    """A valid-shaped record is insufficient: compare actual new data and digest."""
    make, path, root = setup
    callback = Mock(side_effect=select)
    value = make(callback)
    receipt_key = key()
    run(value, receipt_key)
    if damage == "delete":
        path.unlink()
    elif damage in {"text", "title"}:
        changed = saved_registry("CHANGED private text" if damage == "text" else TEXT)
        if damage == "title":
            changed["academic_sources"][0]["title"] = "CHANGED title"
        path.write_text(json.dumps(changed), encoding="utf-8")
    elif damage == "unreadable":
        path.write_bytes(b"malformed PRIVATE JSON")
    elif damage == "read_error":
        monkeypatch.setattr(controller, "read_source", Mock(side_effect=OSError("PRIVATE reader details")))
    elif damage == "render":
        monkeypatch.setattr(controller, "render_locator_result", Mock(side_effect=ValueError("PRIVATE result details")))
    elif damage == "read":
        real_read = controller.read_source
        def forged(*args):
            result = real_read(*args)
            result["text"] = "different actual delivery"
            return result
        monkeypatch.setattr(controller, "read_source", forged)
    else:
        with sqlite3.connect(root / receipts.FILENAME) as db:
            projection = json.loads(db.execute("SELECT projection FROM receipts").fetchone()[0])
            projection["result_digest"] = "0" * 64
            db.execute("UPDATE receipts SET projection=?", (receipts.canonical(projection),))
    observed_read = Mock(wraps=controller.read_source)
    monkeypatch.setattr(controller, "read_source", observed_read)
    replay = asyncio.run(value.lookup(receipt_key, CODE))
    assert (replay["state"], replay["delivery"], replay["result"]) == ("completed", delivery, None)
    assert replay["delivery_source_reads"] == observed_read.call_count == int(
        damage in {"read", "hash", "read_error", "render"})
    assert "PRIVATE" not in json.dumps(replay)
    assert count() == callback.call_count == 1


def test_duplicate_race_one_callback_charge_and_bounded_loader_threads(setup):
    make, _, root = setup
    entered, release = threading.Event(), threading.Event()
    callback = Mock(side_effect=select)
    def load(run_id):
        entered.set()
        assert release.wait(5)
        return SavedSourceLoader(root)(run_id)
    value = make(callback, load)
    receipt_key = key()
    async def scenario():
        first = asyncio.create_task(value.execute(receipt_key, RUN_ID, QUESTION, CODE))
        await observed(entered)
        try:
            replies = await asyncio.gather(*(value.execute(receipt_key, RUN_ID, QUESTION, CODE) for _ in range(8)))
            assert all(reply["state"] == "pending" for reply in replies)
            assert len(value._threads) == 1
            with pytest.raises(receipts.ReceiptError) as exc:
                await value.execute(key(), RUN_ID, QUESTION, CODE)
            assert exc.value.code == "locator_busy"
            assert count() == callback.call_count == 0
        finally:
            release.set()
        assert (await first)["state"] == "completed"
    asyncio.run(scenario())
    assert count() == callback.call_count == 1


@pytest.mark.parametrize("kind", ["pdf", "run", "daily"])
def test_actual_shared_pool_and_daily_admission_errors_survive_locator_catch(setup, monkeypatch, kind):
    make, _, _ = setup
    callback = Mock(side_effect=select)
    value = make(callback)
    receipt_key = key()
    if kind == "daily":
        monkeypatch.setattr(runs, "DAILY_CAP", 1)
        with runs.reserve_inline_paid_operation(owner=access.owner_id(CODE), byok=False):
            pass
        reply = run(value, receipt_key)
    elif kind == "pdf":
        with runs.reserve_inline_paid_operation(owner=access.owner_id(CODE), byok=False):
            reply = run(value, receipt_key)
    else:
        runs._registry["synthetic-running"] = Mock(alive=lambda: True, byok=False)
        try:
            reply = run(value, receipt_key)
        finally:
            runs._registry.clear()
    assert (reply["state"], reply["admission_state"]) == ("failed", "not_admitted")
    assert reply["error_code"] == ("daily_quota_exceeded" if kind == "daily" else "concurrency_limit")
    assert callback.call_count == 0
    assert count() == int(kind != "run")
    assert run(value, receipt_key) == reply


def test_admitted_selector_blocks_actual_pdf_and_run_admission(setup):
    make, _, _ = setup
    entered, release = threading.Event(), threading.Event()
    def callback(request):
        entered.set()
        assert release.wait(5)
        return select(request)
    value = make(callback)
    async def scenario():
        first = asyncio.create_task(value.execute(key(), RUN_ID, QUESTION, CODE))
        await observed(entered)
        try:
            assert runs.capacity_counts() == (0, 1)
            with pytest.raises(runs.ConcurrencyLimitReached), runs.reserve_inline_paid_operation(owner=access.owner_id(CODE), byok=False):
                pytest.fail("PDF must not enter")
            with runs._registry_lock, pytest.raises(runs.ConcurrencyLimitReached):
                runs._admit_paid_operation_locked(owner=access.owner_id(CODE), byok=False)
        finally:
            release.set()
        await first
    asyncio.run(scenario())
    assert count() == 1
