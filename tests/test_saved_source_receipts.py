"""Separate intent journal: offline corruption, expiry and private-byte checks."""

import hashlib
import json
import secrets
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from academic_agent.report_evidence_snapshot import content_hash
from api import saved_source_receipts as receipts

RUN_ID = "20260919T123456Z-0123456789abcdef0123456789abcdef"
OWNER = "0123456789abcdef"


def key(issued=None):
    return f"v1.{int(time.time()) if issued is None else issued}.{secrets.token_hex(32)}"


def claim(journal, receipt_key, **kwargs):
    return journal.claim(receipt_key, kwargs.get("owner", OWNER), kwargs.get("run_id", RUN_ID),
                         kwargs.get("question", "PRIVATE exact question \r\n"), kwargs.get("identity", "scripted-v1"))


def binding():
    return receipts.Binding(snapshot_hash="1" * 64, catalog_hash="2" * 64)


def test_concurrent_claims_reserve_once_and_store_no_private_bytes(tmp_path):
    """SQLite must resolve duplicate claim races before any callback can start."""
    journal = receipts.Journal(tmp_path)
    receipt_key = key()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: claim(journal, receipt_key), range(8)))
    assert sum(ticket is not None for ticket, _ in results) == 1
    record = journal.lookup(receipt_key, OWNER)
    assert record.state == "pending"
    assert record.key_hash == hashlib.sha256(receipt_key.encode()).hexdigest()
    assert record.admission == "not_admitted"
    raw = (tmp_path / receipts.FILENAME).read_bytes()
    for private in (receipt_key, "PRIVATE exact question", "scripted-v1"):
        assert private.encode() not in raw


@pytest.mark.parametrize("change", [
    {"question": "PRIVATE exact question\r\n"}, {"identity": "scripted-v2"},
    {"run_id": "20260919T123456Z-1123456789abcdef0123456789abcdef"},
])
def test_hmac_binds_exact_question_run_and_selector_identity(tmp_path, change):
    """Whitespace/config changes are new intents, not silently replayed work."""
    journal = receipts.Journal(tmp_path)
    receipt_key = key()
    claim(journal, receipt_key)
    with pytest.raises(receipts.ReceiptError) as exc:
        claim(journal, receipt_key, **change)
    assert exc.value.code == "receipt_conflict"


def test_owner_is_not_a_client_selectable_payer(tmp_path):
    journal = receipts.Journal(tmp_path)
    receipt_key = key()
    claim(journal, receipt_key)
    other = "fedcba9876543210"
    for operation in (lambda: claim(journal, receipt_key, owner=other), lambda: journal.lookup(receipt_key, other)):
        with pytest.raises(receipts.ReceiptError) as exc:
            operation()
        assert exc.value.code == "receipt_not_found"
    assert journal.lookup(receipt_key, other, admin=True).owner == OWNER


def test_binding_and_terminal_transition_are_write_once(tmp_path):
    """Neither snapshot identity nor a final outcome can be overwritten."""
    journal = receipts.Journal(tmp_path)
    receipt_key = key()
    ticket, _ = claim(journal, receipt_key)
    ticket.bind(binding())
    with pytest.raises(receipts.ReceiptError):
        ticket.bind(binding())
    ticket.admitting()
    ticket.admitted()
    with pytest.raises(receipts.ReceiptError):
        ticket.fail("execution_unavailable", admission="not_admitted")
    ticket.fail("execution_unavailable", admission="admitted")
    for action in (ticket.admitting, lambda: ticket.fail("access_denied", admission="admitted")):
        with pytest.raises(receipts.ReceiptError):
            action()
    replay_ticket, record = claim(journal, receipt_key)
    assert replay_ticket is None
    assert (record.state, record.admission, record.error_code) == ("failed", "admitted", "execution_unavailable")


@pytest.mark.parametrize("bad_key", [None, [], "", "v1.0.a", "v1.1000000000." + "Z" * 64])
def test_malformed_key_never_creates_a_journal(tmp_path, bad_key):
    with pytest.raises(receipts.ReceiptError) as exc:
        claim(receipts.Journal(tmp_path), bad_key)
    assert exc.value.code == "invalid_receipt_key"
    assert not (tmp_path / receipts.FILENAME).exists()


def test_expired_pruned_key_never_becomes_new(tmp_path, monkeypatch):
    """Retention deletion cannot erase the self-contained key expiry check."""
    now = int(time.time())
    monkeypatch.setattr(receipts.time, "time", lambda: now)
    receipt_key = key(now)
    journal = receipts.Journal(tmp_path)
    claim(journal, receipt_key)
    now += receipts.RETENTION_SECONDS
    assert journal.prune() == 1
    for action in (lambda: claim(journal, receipt_key), lambda: journal.lookup(receipt_key, OWNER)):
        with pytest.raises(receipts.ReceiptError) as exc:
            action()
        assert exc.value.code == "receipt_expired"
    assert journal.prune() == 0


@pytest.mark.parametrize("offset,code", [(-301, "receipt_expired"), (301, "invalid_receipt_key")])
def test_unused_key_freshness_is_bounded(tmp_path, monkeypatch, offset, code):
    now = int(time.time())
    monkeypatch.setattr(receipts.time, "time", lambda: now)
    with pytest.raises(receipts.ReceiptError) as exc:
        claim(receipts.Journal(tmp_path), key(now + offset))
    assert exc.value.code == code


def test_old_existing_key_replays_until_24h(tmp_path, monkeypatch):
    now = int(time.time())
    monkeypatch.setattr(receipts.time, "time", lambda: now)
    journal = receipts.Journal(tmp_path)
    receipt_key = key(now)
    claim(journal, receipt_key)
    now += 301
    assert claim(journal, receipt_key)[0] is None


@pytest.mark.parametrize("damage", ["empty", "junk", "version", "schema", "extra_table", "row"])
def test_existing_corruption_fails_closed_without_recreation(tmp_path, damage):
    """An existing empty/wrong-schema ledger is lost history, not first boot."""
    journal = receipts.Journal(tmp_path)
    receipt_key = key()
    path = tmp_path / receipts.FILENAME
    if damage in {"empty", "junk"}:
        path.write_bytes(b"" if damage == "empty" else b"PRIVATE corrupt database")
    else:
        claim(journal, receipt_key)
        with sqlite3.connect(path) as db:
            if damage == "version":
                db.execute("PRAGMA user_version=2")
            elif damage == "schema":
                db.execute("ALTER TABLE receipts ADD COLUMN leaked TEXT")
            elif damage == "extra_table":
                db.execute("CREATE TABLE other (x TEXT)")
            else:
                db.execute("UPDATE receipts SET state='invented'")
    before = path.read_bytes()
    for action in (lambda: claim(journal, key()), lambda: journal.lookup(receipt_key, OWNER), journal.prune):
        with pytest.raises(receipts.ReceiptError) as exc:
            action()
        assert exc.value.code == "receipt_unavailable"
        assert "PRIVATE" not in str(exc.value)
    assert path.read_bytes() == before


def test_full_journal_refuses_new_intent_but_preserves_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(receipts, "MAX_RECEIPTS", 2)
    journal = receipts.Journal(tmp_path)
    first = key()
    claim(journal, first)
    claim(journal, key())
    with pytest.raises(receipts.ReceiptError) as exc:
        claim(journal, key())
    assert exc.value.code == "receipt_capacity"
    assert claim(journal, first)[0] is None


@pytest.mark.parametrize("projection", [
    "x" * 4097, '{"private":"PRIVATE title"}',
    '{"state":"pending","state":"completed"}',
])
def test_malformed_or_oversized_projection_cannot_reach_delivery(tmp_path, projection):
    journal = receipts.Journal(tmp_path)
    receipt_key = key()
    claim(journal, receipt_key)
    with sqlite3.connect(tmp_path / receipts.FILENAME) as db:
        db.execute("UPDATE receipts SET projection=?", (projection,))
    with pytest.raises(receipts.ReceiptError) as exc:
        journal.lookup(receipt_key, OWNER)
    assert exc.value.code == "receipt_unavailable"
    assert "PRIVATE" not in str(exc.value)


def test_binding_canonical_hashes_are_not_private_text(tmp_path):
    journal = receipts.Journal(tmp_path)
    receipt_key = key()
    ticket, _ = claim(journal, receipt_key)
    bound = receipts.Binding(snapshot_hash=content_hash("PRIVATE excerpt"), catalog_hash=content_hash("PRIVATE title"))
    ticket.bind(bound)
    assert journal.lookup(receipt_key, OWNER).binding == bound
    with sqlite3.connect(tmp_path / receipts.FILENAME) as db:
        value = json.loads(db.execute("SELECT binding FROM receipts").fetchone()[0])
    assert set(value) == {"method_id", "snapshot_hash", "catalog_hash"}
    assert b"PRIVATE" not in (tmp_path / receipts.FILENAME).read_bytes()
