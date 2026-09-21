"""Fake-key actual HTTP interceptions through the frozen native transport."""

import asyncio
from contextlib import suppress
import hashlib
import json
import os
import sqlite3
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from academic_agent import report_evidence_source_locator as locator
from academic_agent.report_evidence_catalog_followup import build_catalog
from academic_agent.report_evidence_qwen_canary import CanaryStopped, _encoded
from academic_agent.saved_source_accounted_qwen import AccountedQwenSelector
from academic_agent.saved_source_usage import AccountingError
from api import runs, saved_source_accounting as accounting, saved_source_receipts as receipts
from tests.test_saved_source_accounting import (
    RESERVATION, TOKENS, boundary, count, execute,  # noqa: F401 -- pytest registers the shared isolated fixture.
)
from tests.test_saved_source_controller import CODE, QUESTION, RUN_ID, TEXT, key, select

KEY = "sk-fictional-accounted-qwen-no-provider"


@pytest.fixture
def native(boundary, monkeypatch):
    """Keep real HTTP parser, native validation, fsync and all three journals."""
    state = SimpleNamespace(
        requests=[], fences=[], response={"model": "qwen3.5-plus", "usage": dict(TOKENS),
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": select(None)}]},
        exception=None, status=200, before_reply=None,
    )
    real_client = httpx.AsyncClient

    def dispatch(request):
        state.requests.append(request)
        with sqlite3.connect(boundary.root / accounting.FILENAME) as db:
            rows = db.execute("SELECT value FROM accounting").fetchall()
            state.fences.append([json.loads(row[0]) for row in rows])
        if state.before_reply is not None:
            state.before_reply()
        if state.exception is not None:
            raise state.exception
        return httpx.Response(state.status, stream=httpx.ByteStream(_encoded(state.response)))

    def client(**kwargs):
        assert isinstance(kwargs["transport"], httpx.MockTransport)
        assert kwargs["trust_env"] is kwargs["follow_redirects"] is False
        assert kwargs["verify"] is True
        return real_client(**kwargs)

    def transport(**kwargs):
        assert kwargs == {"retries": 0, "verify": True, "trust_env": False}
        return httpx.MockTransport(dispatch)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    state.snapshot = boundary.loader(RUN_ID)
    state.selector = AccountedQwenSelector(KEY, snapshot=state.snapshot, question=QUESTION,
                                           ledger_dir=boundary.root / "new-native-ledger")
    state.controller = boundary.make(state.selector)
    return state


def test_actual_native_http_to_store_and_disabled_replay(native, boundary, monkeypatch):
    """A mocked successful callback cannot prove native reserve/fence/usage delivery."""
    receipt_key = key()
    first = execute(native.controller, receipt_key)
    assert first["result"]["saved_text"]["text"] == TEXT
    assert first["accounting"]["usage"] == {"status": "reported_complete", **TOKENS}
    assert first["accounting"]["cost"]["estimated_usd"] == "0.000126100"
    assert first["accounting"]["cost"]["reservation_usd"] == RESERVATION
    assert len(native.requests) == count() == 1
    request = native.requests[0]
    assert request.headers["authorization"] == "Bearer " + KEY
    fence = native.fences[0][0]
    assert fence["phase"] == "entered" and fence["native"] is None
    assert fence["wire_sha256"] == hashlib.sha256(request.content).hexdigest()
    assert fence["context"]["receipt_key_sha256"] == hashlib.sha256(receipt_key.encode()).hexdigest()
    events = [json.loads(line) for line in (boundary.root / "new-native-ledger/events.jsonl").read_text().splitlines()]
    assert [event["event"] for event in events] == ["request_reserved", "request_finished"]
    assert _encoded(events[0]["request"]) == request.content
    assert events[1]["reported_usage"] == TOKENS
    assert TEXT.encode() not in request.content
    sidecar = (boundary.root / accounting.FILENAME).read_bytes()
    for private in (KEY, TEXT, QUESTION, CODE, receipt_key, "SYNTHETIC private title"):
        assert private.encode() not in sidecar
    monkeypatch.setattr(native.selector, "select", Mock(side_effect=AssertionError("No repeat native entry")))
    for reply in (execute(native.controller, receipt_key), asyncio.run(boundary.make().lookup(receipt_key, CODE))):
        assert reply["accounting"] == first["accounting"] and reply["result"] == first["result"]
    assert len(native.requests) == count() == 1


@pytest.mark.parametrize("fault", ["timeout", "http", "missing", "contradictory", "boolean"])
def test_unknown_native_usage_is_not_free(native, fault):
    """Accepted requests retain reservations when usage is absent or invalid."""
    if fault == "timeout":
        native.exception = httpx.ReadTimeout("PRIVATE " + KEY)
    elif fault == "http":
        native.status = 429
    elif fault == "missing":
        native.response.pop("usage")
    elif fault == "contradictory":
        native.response["usage"]["total_tokens"] = 123
    else:
        native.response["usage"]["prompt_tokens"] = True
    reply = execute(native.controller)
    facts = reply["accounting"]
    assert facts["usage"] == {"status": "unknown", "prompt_tokens": None, "completion_tokens": None,
                              "total_tokens": None}
    assert facts["cost"]["estimated_usd"] is None and facts["cost"]["reservation_usd"] == RESERVATION
    assert facts["native_journal_state"] == "complete"
    assert len(native.requests) == count() == 1
    assert KEY not in json.dumps(reply) and "PRIVATE" not in json.dumps(reply)


def test_bad_assistant_keeps_coherent_usage(native):
    """Native selection rejection does not erase the provider's coherent usage."""
    native.response["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = '{"source_id":"A999"}'
    reply = execute(native.controller)
    assert reply["result"]["state"] == "unavailable"
    assert reply["result"]["read_attempts"] == 0
    assert reply["accounting"]["usage"] == {"status": "reported_complete", **TOKENS}
    assert reply["accounting"]["cost"]["status"] == "estimated"


def test_wrong_model_retains_tokens_but_cannot_price_as_authorized(native):
    """Reported tokens and the authority to apply the frozen model price differ."""
    native.response["model"] = "unexpected-model"
    reply = execute(native.controller)
    facts = reply["accounting"]
    assert facts["usage"] == {"status": "reported_complete", **TOKENS}
    assert facts["cost"]["status"] == "unavailable" and facts["cost"]["estimated_usd"] is None
    assert facts["cost"]["reservation_usd"] == RESERVATION
    assert "model_mismatch" in facts["fault_codes"]


def test_failed_native_finish_fsync_is_partial_not_complete(native, monkeypatch):
    """Readable but un-fsynced finish bytes cannot upgrade native durability."""
    original = native.selector._ledger._append

    def fail_finish(event):
        if event.get("event") == "request_finished":
            # Daily admission fsyncs too; scope the fault to the exact native
            # finish instead of depending on unrelated global I/O ordinals.
            with monkeypatch.context() as scoped:
                scoped.setattr(os, "fsync", Mock(side_effect=OSError("PRIVATE native-finish " + KEY)))
                return original(event)
        return original(event)

    monkeypatch.setattr(native.selector._ledger, "_append", fail_finish)
    reply = execute(native.controller)
    assert len(native.requests) == count() == 1
    assert native.selector._ledger.records[0]["usage_status"] == "complete"
    assert native.selector._ledger.pending == 1
    assert reply["result"]["state"] == "unavailable"
    assert reply["accounting"]["native_journal_state"] == "unresolved"
    assert reply["accounting"]["usage"] == {"status": "reported_partial", **TOKENS}
    assert reply["accounting"]["cost"]["status"] == "partial_estimate"
    assert reply["accounting"]["cost"]["reservation_usd"] == RESERVATION


@pytest.mark.parametrize("stage", ["capture", "seal"])
def test_sidecar_write_fault_preserves_valid_native_saved_result(native, boundary, monkeypatch, stage):
    """Accounting-only failure cannot turn a valid native result into callback failure."""
    monkeypatch.setattr(accounting.OperationObservation, stage, Mock(side_effect=OSError("PRIVATE " + KEY)))
    receipt_key = key()
    reply = execute(native.controller, receipt_key)
    assert reply["state"] == "completed" and reply["result"]["saved_text"]["text"] == TEXT
    assert reply["accounting"]["usage"]["status"] in {"unknown", "unavailable"}
    assert reply["accounting"]["usage"]["prompt_tokens"] is None
    replay = asyncio.run(boundary.make().lookup(receipt_key, CODE))
    assert replay["result"] == reply["result"] and len(native.requests) == count() == 1


def test_failed_receipt_write_does_not_upgrade_unknown_receipt(native, boundary, monkeypatch):
    """Complete accounting is not authority to invent a completed receipt."""
    monkeypatch.setattr(receipts.Ticket, "complete", Mock(side_effect=ReceiptFailure()))
    receipt_key = key()
    with pytest.raises(receipts.ReceiptError) as error:
        execute(native.controller, receipt_key)
    assert error.value.code == "receipt_unavailable"
    reply = asyncio.run(boundary.make().lookup(receipt_key, CODE))
    assert reply["state"] == "unknown" and reply["result"] is None
    assert reply["accounting"]["usage"]["status"] == "reported_complete"
    assert len(native.requests) == count() == 1


class ReceiptFailure(receipts.ReceiptError):
    def __init__(self):
        super().__init__("receipt_unavailable")


def test_sidecar_fence_failure_after_native_reserve_prevents_http(native, monkeypatch):
    """A native reservation alone cannot bypass the required durable sidecar fence."""
    fence = Mock(side_effect=OSError("PRIVATE fence failure"))
    monkeypatch.setattr(accounting.OperationObservation, "before_native_entry", fence)
    reply = execute(native.controller)
    assert fence.call_count == 1 and native.requests == []
    assert reply["result"]["state"] == "unavailable"
    assert reply["accounting"]["usage"]["status"] == "not_dispatched"
    assert reply["accounting"]["cost"]["reservation_usd"] == RESERVATION


def test_same_wrapper_cannot_serve_second_receipt_or_reuse_ledger(native, boundary):
    """Equal question/snapshot never makes another receipt the same operation."""
    first = execute(native.controller, key())
    second = execute(native.controller, key())
    assert first["accounting"]["usage"]["status"] == "reported_complete"
    assert second["accounting"]["usage"]["status"] != "reported_complete"
    assert second["result"]["state"] == "unavailable"
    assert len(native.requests) == 1
    with pytest.raises(CanaryStopped, match="output_creation_failed_or_occupied"):
        AccountedQwenSelector(KEY, snapshot=native.snapshot, question=QUESTION,
                             ledger_dir=boundary.root / "new-native-ledger")


def test_invalid_first_context_consumes_wrapper_without_native_entry(native, boundary):
    """An invalid first operation cannot be repaired into a different receipt."""
    with pytest.raises(AccountingError):
        native.selector.select({}, operation=None, observation=None)
    reply = execute(native.controller)
    assert reply["result"]["state"] == "unavailable" and native.requests == []


def test_native_request_validation_stays_frozen_and_no_retry(native, boundary):
    """The wrapper must not repair a mismatched native request before its validator."""
    # Invoke the actual controller but perturb only the locator's candidate
    # request; the native transport still owns exact snapshot/question matching.
    original = locator._request
    request = original(QUESTION, build_catalog(native.snapshot))
    request["messages"][1]["content"] += " mismatch"
    # A dedicated direct observation keeps this an actual claimed/bound receipt.
    receipt_key = key()
    ticket, claimed = native.controller._journal.claim(receipt_key, "a" * 16, RUN_ID, QUESTION, "scripted")
    observation = boundary.store.begin(claimed)
    snapshot = native.snapshot
    bound = ticket.bind(receipts.Binding(snapshot_hash=snapshot.snapshot_hash,
                                         catalog_hash=locator.content_hash(build_catalog(snapshot))))
    operation = observation.bind(bound, "scripted")
    with pytest.raises(CanaryStopped, match="request_identity_mismatch"):
        native.selector.select(request, operation=operation, observation=observation)
    with pytest.raises(AccountingError):
        native.selector.select(original(QUESTION, build_catalog(snapshot)), operation=operation, observation=observation)
    assert native.requests == []


def test_cancelled_waiter_seals_on_actual_thread_and_keeps_slot(native, boundary, monkeypatch):
    """Cancelling the waiter cannot free the slot or skip native/sidecar completion."""
    entered, release = threading.Event(), threading.Event()
    original = accounting.OperationObservation.seal
    thread_ids = []

    def held_seal(self, facts):
        thread_ids.append(threading.get_ident())
        entered.set()
        assert release.wait(10)
        return original(self, facts)

    monkeypatch.setattr(accounting.OperationObservation, "seal", held_seal)
    receipt_key = key()

    async def scenario():
        task = asyncio.create_task(native.controller.execute(receipt_key, RUN_ID, QUESTION, CODE))
        try:
            assert await asyncio.to_thread(entered.wait, 10)
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            assert runs.active_paid_operation_count() == 1
            assert thread_ids == [native.controller._threads[hashlib.sha256(receipt_key.encode()).hexdigest()].ident]
            failures = []

            def competitor():
                try:
                    runs.reserve_thread_paid_operation(owner="b" * 16, byok=False)
                except runs.ConcurrencyLimitReached as exc:
                    failures.append(exc)

            other = threading.Thread(target=competitor)
            other.start()
            other.join(5)
            assert not other.is_alive() and len(failures) == 1
        finally:
            release.set()
            await native.controller.close()
        replay = await boundary.make().lookup(receipt_key, CODE)
        assert replay["accounting"]["usage"] == {"status": "reported_complete", **TOKENS}
        assert replay["result"]["saved_text"]["text"] == TEXT

    asyncio.run(scenario())
    assert runs.active_paid_operation_count() == 0 and len(native.requests) == count() == 1
