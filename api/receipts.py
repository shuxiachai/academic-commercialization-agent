"""Opt-in, durable paid-intent receipts; never a provider exactly-once claim.

A committed reservation precedes dispatch. Lost completion writes remain
unknown and cannot dispatch again. Keys carry creation time plus 256 random
bits; expired keys are rejected even after pruning, so cleanup cannot turn an
old retry into fresh paid work. SQLite transactions protect receipt claims,
not the application's separately single-process capacity/ownership model.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import hmac
import json
import math
from pathlib import Path
import re
import sqlite3
from threading import Lock
import time
from uuid import uuid4

RETENTION_SECONDS = 86400
MAX_RECEIPTS = 5000
_EPOCH = uuid4().hex
_SCHEMA_LOCK = Lock()
_KEY = re.compile(r"v1\.([0-9]{10})\.[0-9a-f]{64}")
_CURRENT: ContextVar[Ticket | None] = ContextVar("paid_receipt", default=None)
_SCHEMA = """CREATE TABLE receipts (
 key_hash TEXT PRIMARY KEY, owner TEXT, kind TEXT NOT NULL,
 fingerprint TEXT NOT NULL, expires REAL NOT NULL, epoch TEXT NOT NULL,
 state TEXT NOT NULL, resource_id TEXT, status INTEGER, response TEXT
)"""


class ReceiptError(Exception):
    """Only static, credential/content-free messages cross HTTP/log boundaries."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code = status, code


def _unavailable():
    return ReceiptError(503, "receipt_unavailable", "Paid receipt storage is unavailable; do not resubmit with a new key.")


def _identity(key: str) -> tuple[str, float]:
    match = _KEY.fullmatch(key)
    if match is None:
        raise ReceiptError(400, "invalid_receipt_key", "Idempotency-Key must be v1.<UTC epoch seconds>.<64 random hex characters>.")
    issued = int(match[1])
    now = time.time()
    if issued > now + 300:
        raise ReceiptError(400, "invalid_receipt_key", "Receipt key time is in the future; check the client clock.")
    if now >= issued + RETENTION_SECONDS:
        raise ReceiptError(410, "receipt_expired", "This receipt key has expired and cannot start another paid operation.")
    return hashlib.sha256(key.encode()).hexdigest(), issued + RETENTION_SECONDS


@contextmanager
def _database(root: Path, *, create: bool = False):
    path = root / ".paid-receipts.sqlite3"
    connection = None
    try:
        if path.is_symlink():
            raise _unavailable()
        if create:
            root.mkdir(parents=True, exist_ok=True)
        elif not path.exists():
            raise ReceiptError(404, "receipt_not_found", "No receipt is available; this does not establish that the request was free.")
        # Only the exclusive creator may initialize a schema. An existing
        # empty/missing-table database is damaged, not permission to silently
        # discard previous reservations. The lock covers first-file setup in
        # this single API process; SQLite still serializes individual claims.
        with _SCHEMA_LOCK:
            initialize = False
            if create:
                try:
                    with path.open("xb"):
                        initialize = True
                except FileExistsError:
                    pass
            connection = sqlite3.connect(str(path), timeout=2)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA secure_delete=ON")
            if initialize:
                with connection:
                    connection.execute(_SCHEMA)
                    connection.execute("PRAGMA user_version=1")
            if connection.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise _unavailable()
            connection.execute("SELECT key_hash, owner, kind, fingerprint, expires, epoch, state, resource_id, status, response FROM receipts LIMIT 0")
        yield connection
    except (sqlite3.Error, OSError) as exc:
        raise _unavailable() from exc
    finally:
        if connection is not None:
            connection.close()


def _record(row) -> dict:
    """Bad saved shapes are unavailable, not permission for a new dispatch."""
    try:
        record = dict(row)
        if (record["kind"] not in {"run", "resume", "paper"}
                or record["state"] not in {"pending", "accepted", "failed"}
                or not isinstance(record["expires"], (float, int))
                or not math.isfinite(record["expires"])
                or not isinstance(record["epoch"], str)
                or not isinstance(record["fingerprint"], str)
                or re.fullmatch(r"[0-9a-f]{64}", record["fingerprint"]) is None
                or (record["owner"] is not None and not isinstance(record["owner"], str))):
            raise ValueError("Invalid receipt")
        if record["resource_id"] is not None:
            pattern = r"paper-[0-9a-f]{32}" if record["kind"] == "paper" else r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}"
            if not isinstance(record["resource_id"], str) or re.fullmatch(pattern, record["resource_id"]) is None:
                raise ValueError("Invalid resource identity")
        if record["response"] is not None and (not isinstance(record["response"], str) or len(record["response"].encode()) > 16384):
            raise ValueError("Invalid response size")
        record["response"] = json.loads(record["response"]) if record["response"] is not None else None
        if record["state"] == "pending" and (record["response"] is not None or record["status"] is not None):
            raise ValueError("Pending receipt has a final result")
        if record["state"] != "pending" and (
                not isinstance(record["response"], dict) or type(record["status"]) is not int):
            raise ValueError("Invalid receipt result")
        return record
    except (TypeError, ValueError, KeyError) as exc:
        raise _unavailable() from exc


def _authorize(record: dict, owner: str | None, admin: bool = False):
    # Ownerless BYOK has no second server-side identity: the high-entropy
    # receipt key is a read capability just like its resulting run/paper id.
    # A configured code's receipt additionally requires that same valid code.
    if record["owner"] is not None and not admin and record["owner"] != owner:
        raise ReceiptError(404, "receipt_not_found", "No receipt is available for this identity.")


@dataclass(frozen=True)
class Ticket:
    root: Path
    key_hash: str
    kind: str

    def bind(self, resource_id: str):
        # Called before Popen/provider dispatch. If the later receipt write is
        # lost, status lookup can still point to the intended resource without
        # claiming that launch happened or repeating it.
        with _database(self.root) as db, db:
            changed = db.execute("UPDATE receipts SET resource_id=? WHERE key_hash=? AND state='pending' AND resource_id IS NULL",
                                 (resource_id, self.key_hash)).rowcount
            if changed != 1:
                raise _unavailable()

    def finish(self, response: dict, status: int, *, failed: bool = False):
        # Keep PDF excerpts in their existing expiring paper store, not a
        # second receipt copy with potentially different retention semantics.
        if self.kind == "paper" and not failed:
            response = {"paper_id": response["paper_id"]}
        raw = json.dumps(response, ensure_ascii=False, allow_nan=False)
        if len(raw.encode()) > 16384:
            raise _unavailable()
        with _database(self.root) as db, db:
            changed = db.execute("UPDATE receipts SET state=?, status=?, response=? WHERE key_hash=? AND state='pending'",
                       ("failed" if failed else "accepted", status, raw, self.key_hash))
            if changed.rowcount != 1:
                # The PDF thread already commits its result before the waiter
                # returns. A duplicate finalizer may observe that same result,
                # but a vanished row must never be presented as durable success.
                row = db.execute("SELECT * FROM receipts WHERE key_hash=?", (self.key_hash,)).fetchone()
                record = _record(row)
                if record["state"] != ("failed" if failed else "accepted") or record["response"] != response or record["status"] != status:
                    raise _unavailable()


def claim(root: Path, key: str, owner: str | None, kind: str, payload: dict) -> tuple[Ticket | None, dict | None]:
    key_hash, expires = _identity(key)
    # Keyed fingerprint binds BYOK credentials and all normalized inputs,
    # including PDF byte digest/parent id, without saving those inputs or
    # enabling offline guesses using a public unkeyed hash. Raw key is not
    # stored in SQLite and must never appear in a URL, log or traceback text.
    fingerprint = hmac.new(key.encode(), json.dumps([kind, owner, payload], sort_keys=True,
                         ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode(), "sha256").hexdigest()
    with _database(root, create=True) as db, db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM receipts WHERE key_hash=?", (key_hash,)).fetchone()
        if row is not None:
            record = _record(row)
            _authorize(record, owner)
            if not hmac.compare_digest(record["fingerprint"], fingerprint):
                raise ReceiptError(409, "receipt_conflict", "This key belongs to different input or credentials; no new operation was started.")
            return None, record
        if time.time() > expires - RETENTION_SECONDS + 300:
            raise ReceiptError(410, "receipt_expired", "An unused old key cannot start paid work. Check its receipt instead of retrying.")
        db.execute("DELETE FROM receipts WHERE expires<=?", (time.time(),))
        if db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] >= MAX_RECEIPTS:
            raise ReceiptError(503, "receipt_capacity", "Paid receipt capacity is full; no new operation was started.")
        db.execute("INSERT INTO receipts VALUES (?,?,?,?,?,?,'pending',NULL,NULL,NULL)",
                   (key_hash, owner, kind, fingerprint, expires, _EPOCH))
    return Ticket(root, key_hash, kind), None


def lookup(root: Path, key: str, owner: str | None, *, admin: bool = False) -> dict:
    key_hash, _ = _identity(key)
    with _database(root) as db:
        row = db.execute("SELECT * FROM receipts WHERE key_hash=?", (key_hash,)).fetchone()
        if row is None:
            raise ReceiptError(404, "receipt_not_found", "No receipt is available; this does not establish that the request was free.")
        record = _record(row)
        _authorize(record, owner, admin)
        return record


def public_record(record: dict) -> dict:
    state = record["state"]
    if state == "pending" and record["epoch"] != _EPOCH:
        state = "unknown"
    return {"operation": record["kind"], "state": state,
            "resource_id": record["resource_id"], "status_code": record["status"],
            "response": record["response"], "expires_at": record["expires"]}


@contextmanager
def activate(ticket: Ticket | None):
    token = _CURRENT.set(ticket)
    try:
        yield
    finally:
        _CURRENT.reset(token)


def current() -> Ticket | None:
    return _CURRENT.get()


def bind_resource(resource_id: str):
    ticket = current()
    if ticket is not None:
        ticket.bind(resource_id)


def validate(root: Path):
    """Readiness is not allowed to recreate a broken existing receipt ledger."""
    if not (root / ".paid-receipts.sqlite3").exists():
        return
    with _database(root) as db:
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise _unavailable()
        db.execute("SELECT key_hash, state FROM receipts LIMIT 1")


def prune(root: Path) -> int:
    """Independent maintenance; deletion never re-enables an expired key.

    This removes receipt rows, not runs or extracted papers. SQLite secure
    deletion is enabled, but filesystem snapshots/backups are outside this
    local retention contract. A failed transaction remains an observed fault.
    """
    if not (root / ".paid-receipts.sqlite3").exists():
        return 0
    with _database(root) as db, db:
        return db.execute("DELETE FROM receipts WHERE expires<=?", (time.time(),)).rowcount
