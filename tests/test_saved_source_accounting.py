"""Strict accounting/store/controller seams; synthetic state and zero providers."""

import asyncio
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import socket
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from academic_agent.saved_source_loader import SavedSourceLoader
from academic_agent.saved_source_usage import (
    AccountingError, ExecutionFactsV1, NativeFactsV1, ReportedUsage, UsageProjectionV1,
    decimal_usd, unavailable_usage,
)
from api import access, runs
from api import saved_source_accounting as accounting
from api.saved_source_controller import SavedSourceController
from api.saved_source_receipts import Binding, Journal, ReceiptError
from tests.test_saved_source_controller import CODE, QUESTION, RUN_ID, TEXT, key, saved_registry, select

WIRE = "a" * 64
RESERVATION = "0.011149312"
TOKENS = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}


def native_facts(**changes):
    return NativeFactsV1(**{
        "wire_sha256": WIRE, "dispatch_state": "response_received", "native_journal_state": "complete",
        "model_matches_authorized": True, "reported_usage": ReportedUsage(**TOKENS),
        "reservation_usd": RESERVATION, "price_policy_id": "locator_qwen_frozen_rates_v1", "fault_codes": [],
        **changes,
    })


class ScriptedSelector:
    """Synthetic collector controls only; native proof lives in HTTP tests."""

    def __init__(self):
        self.contexts = []

    def select(self, request, /, *, operation, observation):
        self.contexts.append(operation)
        observation.before_native_entry(wire_sha256=WIRE, reservation_usd=RESERVATION)
        observation.capture(native_facts())
        return select(request)


@pytest.fixture
def boundary(tmp_path, monkeypatch):
    """Actual admission, owner marker, receipt and source loader are not mocked."""
    for name in ("_registry", "_stop_claims", "_inline_paid_operations", "_daily_counts"):
        monkeypatch.setattr(runs, name, {})
    monkeypatch.setattr(runs, "_daily_date", None)
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(runs, "MAX_CONCURRENT", 1)
    monkeypatch.setattr(runs, "DAILY_CAP", 50)
    monkeypatch.setattr(access, "ACCESS_CODE", CODE)
    monkeypatch.setattr(access, "ACCESS_CODES", "synthetic-other-code")
    monkeypatch.setattr(access, "ADMIN_CODE", "synthetic-admin-code")
    forbidden = Mock(side_effect=AssertionError("No actual network"))
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    root = tmp_path / RUN_ID
    root.mkdir()
    (root / ".owner").write_text(access.owner_id(CODE), encoding="utf-8")
    path = root / "validated_sources.json"
    path.write_text(json.dumps(saved_registry(), ensure_ascii=False), encoding="utf-8")
    loader, store = SavedSourceLoader(tmp_path), accounting.AccountingStore(tmp_path)
    controllers = []

    def make(selector=None, *, legacy=False, store_override=None):
        kwargs = {"selector": selector} if legacy else {
            "accounted_selector": selector, "accounting_store": store if store_override is None else store_override,
        }
        value = SavedSourceController(loader, tmp_path, selector_identity="synthetic-accounted-v1" if selector else None,
                                      **kwargs)
        controllers.append(value)
        return value

    yield SimpleNamespace(root=tmp_path, path=path, loader=loader, store=store, make=make)
    for value in controllers:
        asyncio.run(value.close())
    assert runs.active_paid_operation_count() == 0
    forbidden.assert_not_called()


def execute(value, receipt_key=None):
    return asyncio.run(value.execute(receipt_key or key(), RUN_ID, QUESTION, CODE))


def count():
    return runs._daily_counts.get(access.owner_id(CODE), 0)


def claimed(root):
    journal = Journal(root)
    receipt_key = key()
    ticket, record = journal.claim(receipt_key, access.owner_id(CODE), RUN_ID, QUESTION, "synthetic-accounted-v1")
    return ticket, record


def bound_observation(root):
    ticket, record = claimed(root)
    store = accounting.AccountingStore(root)
    observation = store.begin(record)
    bound = ticket.bind(Binding(snapshot_hash="b" * 64, catalog_hash="c" * 64))
    operation = observation.bind(bound, "synthetic-accounted-v1")
    return store, observation, operation, bound


def test_controller_old13_exact_and_opt_in_full_projection_replay(boundary):
    """New opt-in fields cannot relax or accidentally expand the old receipt wire."""
    old = execute(boundary.make(select, legacy=True))
    scripted = ScriptedSelector()
    value, receipt_key = boundary.make(scripted), key()
    first = execute(value, receipt_key)
    assert len(old) == 13 and set(first) == set(old) | {"accounting"}
    assert first["result"] == old["result"]
    assert first["provider_usage"] == first["provider_cost"] == "not_observed"
    expected = first["accounting"]
    assert expected["usage"] == {"status": "reported_complete", **TOKENS}
    assert expected["cost"] == {
        "currency": "USD", "status": "estimated", "estimated_usd": "0.000126100",
        "reservation_usd": RESERVATION, "price_policy_id": "locator_qwen_frozen_rates_v1",
        "invoice_status": "not_observed",
    }
    assert UsageProjectionV1.model_validate(expected).model_dump() == expected
    for reply in (execute(value, receipt_key), asyncio.run(boundary.make().lookup(receipt_key, CODE))):
        assert reply["accounting"] == expected
        assert reply["result"] == first["result"]
    assert len(scripted.contexts) == 1 and count() == 2
    with pytest.raises(ReceiptError) as error:
        execute(boundary.make())
    assert error.value.code == "selector_disabled"


def test_real_claim_context_distinguishes_two_keys_with_same_question(boundary):
    """Question equality cannot replace receipt-key/fingerprint identity."""
    scripted, keys = ScriptedSelector(), [key(), key()]
    value = boundary.make(scripted)
    replies = [execute(value, item) for item in keys]
    assert len(scripted.contexts) == count() == 2
    left, right = scripted.contexts
    assert left.receipt_key_sha256 != right.receipt_key_sha256
    assert left.intent_fingerprint != right.intent_fingerprint
    for context, receipt_key, reply in zip(scripted.contexts, keys, replies, strict=True):
        record = value._journal.lookup(receipt_key, access.owner_id(CODE))
        assert context.receipt_key_sha256 == record.key_hash == reply["accounting"]["receipt_key_sha256"]
        assert context.owner_id == record.owner and context.intent_fingerprint == record.fingerprint
        assert context.snapshot_hash == record.binding.snapshot_hash
        assert context.catalog_hash == record.binding.catalog_hash
        assert context.run_id == record.run_id and context.expires_at == record.expires
        assert context.selector_identity_sha256 == hashlib.sha256(b"synthetic-accounted-v1").hexdigest()
    raw = (boundary.root / accounting.FILENAME).read_bytes()
    for secret in (*keys, CODE, QUESTION, TEXT, "SYNTHETIC private title"):
        assert secret.encode("utf-8") not in raw


@pytest.mark.parametrize("fault", ["missing", "corrupt", "wrong_binding"])
def test_sidecar_fault_keeps_saved_text_and_read_only_lookup(boundary, fault):
    """Missing/corrupt/unrelated accounting cannot erase saved text or mean free."""
    value, receipt_key = boundary.make(ScriptedSelector()), key()
    first = execute(value, receipt_key)
    path = boundary.root / accounting.FILENAME
    if fault == "missing":
        path.unlink()
    elif fault == "corrupt":
        path.write_bytes(b"broken sidecar")
    else:
        with sqlite3.connect(path) as db:
            row = db.execute("SELECT key_hash,value FROM accounting").fetchone()
            payload = json.loads(row[1])
            payload["context"]["snapshot_hash"] = "f" * 64
            db.execute("UPDATE accounting SET value=? WHERE key_hash=?", (accounting.canonical(payload), row[0]))
    before = path.read_bytes() if path.exists() else None
    reply = asyncio.run(boundary.make().lookup(receipt_key, CODE))
    assert reply["result"] == first["result"] and reply["delivery"] == "available"
    assert reply["accounting"]["usage"]["status"] == "unavailable"
    assert reply["accounting"]["dispatch_state"] == "unknown"
    assert reply["accounting"]["cost"]["estimated_usd"] is None
    assert (path.read_bytes() if path.exists() else None) == before
    assert count() == 1


@pytest.mark.parametrize("stage", ["begin", "bind"])
def test_store_begin_and_bind_fail_before_selector_or_charge(boundary, monkeypatch, stage):
    """Failed durable intent cannot become an unaccounted provider execution."""
    scripted = ScriptedSelector()
    target = boundary.store if stage == "begin" else accounting.OperationObservation
    monkeypatch.setattr(target, stage, Mock(side_effect=OSError("private path")))
    reply = execute(boundary.make(scripted))
    assert reply["state"] == "failed" and reply["error_code"] == "execution_unavailable"
    assert reply["accounting"]["usage"]["status"] == ("unavailable" if stage == "begin" else "not_dispatched")
    assert scripted.contexts == [] and count() == 0


def test_store_identity_mismatch_and_duplicate_begin_cannot_reset(tmp_path):
    """A sidecar cannot be reused under another claim or silently recreated."""
    ticket, record = claimed(tmp_path)
    store = accounting.AccountingStore(tmp_path)
    observation = store.begin(record)
    with pytest.raises(AccountingError):
        store.begin(record)
    other_ticket, _ = claimed(tmp_path)
    wrong = other_ticket.bind(Binding(snapshot_hash="b" * 64, catalog_hash="c" * 64))
    with pytest.raises(AccountingError):
        observation.bind(wrong, "synthetic-accounted-v1")
    right = ticket.bind(Binding(snapshot_hash="b" * 64, catalog_hash="c" * 64))
    with pytest.raises(AccountingError):
        observation.bind(right, "synthetic-accounted-v1")


def test_native_fence_is_one_shot_and_unknown_keeps_reservation(tmp_path):
    """A pending accepted entry is unknown spending, never reported zero."""
    store, observation, _, record = bound_observation(tmp_path)
    observation.before_native_entry(wire_sha256=WIRE, reservation_usd=RESERVATION)
    result = store.observe(record)
    assert result["usage"]["status"] == "unknown" and result["cost"]["estimated_usd"] is None
    assert result["cost"]["reservation_usd"] == RESERVATION
    with pytest.raises(AccountingError):
        observation.before_native_entry(wire_sha256=WIRE, reservation_usd=RESERVATION)
    assert store.observe(record) == result


def test_partial_requires_durable_coherent_capture(tmp_path):
    """Only committed current-operation usage can produce a partial estimate."""
    store, observation, _, record = bound_observation(tmp_path)
    observation.before_native_entry(wire_sha256=WIRE, reservation_usd=RESERVATION)
    observation.capture(native_facts(native_journal_state="unresolved", fault_codes=["native_journal_unresolved"]))
    observation.seal(ExecutionFactsV1(receipt_state="unresolved", admission_state="admitted",
                                     accounted_selector_entries=1, result_digest=None))
    result = accounting.AccountingStore(tmp_path).observe(record)
    assert result["usage"] == {"status": "reported_partial", **TOKENS}
    assert result["cost"]["status"] == "partial_estimate"
    assert result["cost"]["estimated_usd"] == "0.000126100"


@pytest.mark.parametrize("kwargs", [
    {"selector": select, "accounted_selector": ScriptedSelector(), "accounting_store": object()},
    {"accounted_selector": ScriptedSelector()},
    {"accounted_selector": ScriptedSelector(), "accounting_store": object()},
])
def test_invalid_opt_in_configuration_rejected_before_io(tmp_path, kwargs):
    """An accounted callback without a real observation boundary is disabled."""
    with pytest.raises(ValueError):
        SavedSourceController(lambda _: None, tmp_path, **kwargs)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("bad", [True, 1.0, -1, 1_000_000_001, "100"])
def test_token_values_strict_not_coerced(bad):
    """Booleans/floats cannot become truthful integer token observations."""
    with pytest.raises(ValueError):
        ReportedUsage(**{**TOKENS, "prompt_tokens": bad})


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", "-1", "0.0000000001", "1000000000"])
def test_finite_decimal_and_fixed_nine_places(bad):
    """Nonfinite/negative/overprecise/oversized amounts must fail before JSON."""
    with pytest.raises(ValueError):
        decimal_usd(Decimal(bad))


@pytest.mark.parametrize("bad", [True, 1.5, 9_007_199_254_740_992, "123"])
def test_public_expiry_is_strict_javascript_safe_integer(bad):
    """A valid Python integer is not automatically a lossless browser identity."""
    value = unavailable_usage("a" * 64, RUN_ID, 123)
    value["expires_at"] = bad
    with pytest.raises(ValueError):
        UsageProjectionV1.model_validate(value)


def test_public_schema_all_fields_required_extra_forbidden_and_faults_bounded():
    """A missing field cannot be quietly filled by defaults on the wire seam."""
    original = unavailable_usage("a" * 64, RUN_ID, 123)
    for path in ((), ("usage",), ("cost",)):
        source = original[path[0]] if path else original
        for name in source:
            value = deepcopy(original)
            target = value[path[0]] if path else value
            del target[name]
            with pytest.raises(ValueError):
                UsageProjectionV1.model_validate(value)
        value = deepcopy(original)
        target = value[path[0]] if path else value
        target["private_question"] = QUESTION
        with pytest.raises(ValueError):
            UsageProjectionV1.model_validate(value)
    assert len(json.dumps(original).encode()) < 4096


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-0.000000000", "1e-9", "00.000000000",
                                   "0.1", "0.0000000000", "1000000000.000000000", 0.0, True])
def test_money_wire_is_bounded_canonical_fixed_nine(bad):
    """Noncanonical/float amounts cannot cross the public accounting contract."""
    value = unavailable_usage("a" * 64, RUN_ID, 123)
    value["cost"]["reservation_usd"] = bad
    with pytest.raises(ValueError):
        UsageProjectionV1.model_validate(value)


@pytest.mark.parametrize("faults", [["unknown_private_error"], ["not_recorded", "not_recorded"],
                                    ["not_recorded", "accounting_unavailable"], []])
def test_fault_codes_are_safe_sorted_unique_and_explain_unavailable(faults):
    """Private errors and an unexplained absence cannot masquerade as valid usage."""
    value = unavailable_usage("a" * 64, RUN_ID, 123)
    value["fault_codes"] = faults
    with pytest.raises(ValueError):
        UsageProjectionV1.model_validate(value)


def test_missing_stored_context_cannot_bypass_binding(boundary):
    """Dropping a context field must not turn hash validation into an optional check."""
    value, receipt_key = boundary.make(ScriptedSelector()), key()
    first = execute(value, receipt_key)
    with sqlite3.connect(boundary.root / accounting.FILENAME) as db:
        row = db.execute("SELECT key_hash,value FROM accounting").fetchone()
        payload = json.loads(row[1])
        del payload["context"]
        db.execute("UPDATE accounting SET value=? WHERE key_hash=?", (accounting.canonical(payload), row[0]))
    second = asyncio.run(value.lookup(receipt_key, CODE))
    assert second["accounting"]["usage"]["status"] == "unavailable"
    assert second["result"] == first["result"]


def test_unauthorized_lookup_does_not_read_accounting(boundary, monkeypatch):
    """Accounting receives only a receipt already authorized for the current code."""
    value, receipt_key = boundary.make(ScriptedSelector()), key()
    execute(value, receipt_key)
    observe = Mock(side_effect=AssertionError("Unauthorized accounting lookup"))
    monkeypatch.setattr(boundary.store, "observe", observe)
    with pytest.raises(ReceiptError):
        asyncio.run(value.lookup(receipt_key, "synthetic-other-code"))
    observe.assert_not_called()


def test_no_catalog_proves_no_accounted_entry_without_admission(boundary):
    """The controlled no-callback path is no dispatch, not a provider zero report."""
    boundary.path.write_text(json.dumps({"academic_sources": [], "patent_sources": [], "market_sources": []}))
    scripted = ScriptedSelector()
    reply = execute(boundary.make(scripted))
    assert scripted.contexts == [] and count() == 0
    assert reply["accounting"]["usage"]["status"] == "not_dispatched"
    assert reply["accounting"]["usage"]["prompt_tokens"] is None
    assert reply["accounting"]["cost"]["status"] == "not_applicable"


def test_admission_rejection_is_not_an_accounted_selector_entry(boundary, monkeypatch):
    """Locator callback counts must not invent a provider entry before paid admission."""
    monkeypatch.setattr(runs, "reserve_thread_paid_operation", Mock(side_effect=runs.DailyCapReached()))
    scripted = ScriptedSelector()
    reply = execute(boundary.make(scripted))
    assert reply["state"] == "failed" and reply["error_code"] == "daily_quota_exceeded"
    assert scripted.contexts == [] and count() == 0
    assert reply["accounting"]["usage"]["status"] == "not_dispatched"
