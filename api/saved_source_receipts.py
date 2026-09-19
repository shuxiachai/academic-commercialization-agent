"""Private-content-free, single-process locator intent journal, retained 24h.

This separate store cannot authorize provider execution. It reserves an intent
before admission and preserves unknown outcomes, not provider exactly-once or
disk-loss recovery. IDs/hashes/counters are retained; source prose is not.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Annotated, Literal

from pydantic import Field, model_validator

from academic_agent.report_evidence_snapshot import FrozenModel
from academic_agent.report_evidence_source_locator import LocatorCatalog, LocatorResult, METHOD_ID
from academic_agent.saved_source_loader import valid_run_id

FILENAME = ".saved-source-receipts-v1.sqlite3"
RETENTION_SECONDS = 86400
FRESH_SECONDS = 300
MAX_RECEIPTS = 5000
MAX_PROJECTION_BYTES = 4096
OPERATION = "saved_source_location_v1"
_KEY = re.compile(r"v1\.([0-9]{10})\.[0-9a-f]{64}")
_SCHEMA_LOCK = threading.Lock()
_SCHEMA = """CREATE TABLE receipts (
 key_hash TEXT PRIMARY KEY NOT NULL, owner TEXT NOT NULL,
 run_id TEXT NOT NULL, fingerprint TEXT NOT NULL, expires INTEGER NOT NULL,
 state TEXT NOT NULL, admission TEXT NOT NULL, binding TEXT,
 projection TEXT, error_code TEXT
)"""
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Owner = Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
Admission = Literal["not_admitted", "unknown", "admitted"]
ErrorCode = Literal[
    "saved_source_missing", "saved_source_unavailable", "execution_unavailable",
    "concurrency_limit", "daily_quota_exceeded", "paid_ledger_unavailable",
    "access_denied", "request_abandoned",
]
ResultState = LocatorResult.model_fields["state"].annotation
ResultReason = LocatorResult.model_fields["reason"].annotation


class ReceiptError(Exception):
    """Fixed diagnostics only: no raw exceptions, keys or rejected projections."""

    def __init__(self, code: str):
        super().__init__("Saved-source receipt request could not be completed.")
        self.code = code


def unavailable():
    return ReceiptError("receipt_unavailable")


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Binding(FrozenModel):
    method_id: Literal["report_evidence_source_locator_v1"] = METHOD_ID
    snapshot_hash: Hash
    catalog_hash: Hash


class Projection(FrozenModel):
    """Bounded reconstruction recipe, not a reduced copy of private metadata."""

    state: ResultState
    reason: ResultReason
    catalog: LocatorCatalog
    source_id: Annotated[str, Field(pattern=r"^[APM][1-9][0-9]{0,8}$")] | None
    source_hash: Hash | None
    summary_hash: Hash | None
    callback_entries: int = Field(ge=0, le=1)
    callback_bytes: int | None = Field(ge=1)
    read_attempts: int = Field(ge=0, le=1)
    read_completed: int = Field(ge=0, le=1)
    result_digest: Hash

    @model_validator(mode="after")
    def check_identity(self):
        if (self.source_id is None) != (self.source_hash is None) or (
                (self.source_id is None) != (self.summary_hash is None)):
            raise ValueError("invalid_projection_identity")
        return self


class Record(FrozenModel):
    key_hash: Hash
    owner: Owner
    run_id: str
    fingerprint: Hash
    expires: int = Field(ge=1)
    state: Literal["pending", "completed", "failed"]
    admission: Admission
    binding: Binding | None
    projection: Projection | None
    error_code: ErrorCode | None

    @model_validator(mode="after")
    def check_state(self):
        if not valid_run_id(self.run_id):
            raise ValueError("invalid_run_id")
        if self.state == "completed":
            if self.binding is None or self.projection is None or self.error_code is not None:
                raise ValueError("invalid_completion")
            if self.projection.catalog.catalog_hash != self.binding.catalog_hash:
                raise ValueError("invalid_bound_catalog")
            if self.admission != ("admitted" if self.projection.callback_entries else "not_admitted"):
                raise ValueError("invalid_admission")
        elif self.projection is not None or (self.error_code is not None) != (self.state == "failed"):
            raise ValueError("invalid_terminal_state")
        if self.admission != "not_admitted" and self.binding is None:
            raise ValueError("unbound_admission")
        return self


def identity(key: str) -> tuple[str, int]:
    match = _KEY.fullmatch(key) if type(key) is str else None
    if match is None:
        raise ReceiptError("invalid_receipt_key")
    issued = int(match[1])
    now = time.time()
    if issued > now + FRESH_SECONDS:
        raise ReceiptError("invalid_receipt_key")
    if now >= issued + RETENTION_SECONDS:
        raise ReceiptError("receipt_expired")
    return hashlib.sha256(key.encode("ascii")).hexdigest(), issued + RETENTION_SECONDS


def _record(row) -> Record:
    try:
        value = dict(row)
        for field in ("binding", "projection"):
            raw = value[field]
            if raw is not None:
                if type(raw) is not str or len(raw.encode("utf-8")) > MAX_PROJECTION_BYTES:
                    raise ValueError("invalid_projection")
                value[field] = json.loads(raw)
                # Also reject duplicate members, nonfinite numbers and alternate
                # encodings; the only writer uses this exact canonical form.
                if canonical(value[field]) != raw:
                    raise ValueError("noncanonical_projection")
        return Record.model_validate(value)
    except (TypeError, ValueError, KeyError, RecursionError):
        raise unavailable() from None


@contextmanager
def _database(root: Path, *, create=False):
    path = root / FILENAME
    db = None
    try:
        if path.is_symlink():
            raise unavailable()
        if create:
            root.mkdir(parents=True, exist_ok=True)
        with _SCHEMA_LOCK:
            initialize = False
            if create:
                try:
                    with path.open("xb"):
                        initialize = True
                except FileExistsError:
                    pass
            elif not path.exists():
                raise ReceiptError("receipt_not_found")
            # mode=rw prevents a vanished existing database becoming a new one.
            db = sqlite3.connect(path.absolute().as_uri() + "?mode=rw", uri=True, timeout=2)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA secure_delete=ON")
            if initialize:
                with db:
                    db.execute(_SCHEMA)
                    db.execute("PRAGMA user_version=1")
            definitions = db.execute(
                "SELECT name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            if (db.execute("PRAGMA user_version").fetchone()[0] != 1
                    or [tuple(row) for row in definitions] != [("receipts", _SCHEMA)]
                    or db.execute("PRAGMA quick_check").fetchone()[0] != "ok"):
                raise unavailable()
        yield db
    except (sqlite3.Error, OSError):
        raise unavailable() from None
    finally:
        if db is not None:
            db.close()


def _read(db, key_hash):
    row = db.execute("SELECT * FROM receipts WHERE key_hash=?", (key_hash,)).fetchone()
    if row is None:
        raise ReceiptError("receipt_not_found")
    record = _record(row)
    if time.time() >= record.expires:
        raise ReceiptError("receipt_expired")
    return record


def _authorize(record, owner, admin=False):
    if not admin and record.owner != owner:
        raise ReceiptError("receipt_not_found")


@dataclass(frozen=True)
class Ticket:
    root: Path
    key_hash: str

    def _change(self, transform):
        with _database(self.root) as db, db:
            db.execute("BEGIN IMMEDIATE")
            before = _read(db, self.key_hash)
            if before.state != "pending":
                raise unavailable()
            after = Record.model_validate(transform(before.model_dump()))
            binding = canonical(after.binding.model_dump()) if after.binding is not None else None
            projection = canonical(after.projection.model_dump()) if after.projection is not None else None
            if projection is not None and len(projection.encode("ascii")) > MAX_PROJECTION_BYTES:
                raise unavailable()
            db.execute("UPDATE receipts SET state=?, admission=?, binding=?, projection=?, error_code=? WHERE key_hash=?",
                       (after.state, after.admission, binding, projection, after.error_code, self.key_hash))
        return after

    def bind(self, binding: Binding):
        def change(value):
            if value["binding"] is not None or value["admission"] != "not_admitted":
                raise unavailable()
            return {**value, "binding": binding.model_dump()}
        return self._change(change)

    def admitting(self):
        def change(value):
            if value["binding"] is None or value["admission"] != "not_admitted":
                raise unavailable()
            return {**value, "admission": "unknown"}
        return self._change(change)

    def admitted(self):
        def change(value):
            if value["admission"] != "unknown":
                raise unavailable()
            return {**value, "admission": "admitted"}
        return self._change(change)

    def complete(self, projection: Projection):
        return self._change(lambda value: {**value, "state": "completed", "projection": projection.model_dump()})

    def fail(self, code: ErrorCode, *, admission: Admission):
        def change(value):
            # An already observed admission may never be overwritten as free.
            if value["admission"] == "admitted" and admission != "admitted":
                raise unavailable()
            return {**value, "state": "failed", "error_code": code, "admission": admission}
        return self._change(change)


class Journal:
    def __init__(self, root):
        self.root = Path(root)

    def claim(self, key, owner, run_id, question, selector_identity, *, allow_new=True):
        key_hash, expires = identity(key)
        fingerprint = hmac.new(key.encode("ascii"), canonical([
            OPERATION, owner, run_id, question, selector_identity,
        ]).encode("ascii"), "sha256").hexdigest()
        with _database(self.root, create=True) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM receipts WHERE key_hash=?", (key_hash,)).fetchone()
            if row is not None:
                record = _read(db, key_hash)
                _authorize(record, owner)
                if not hmac.compare_digest(record.fingerprint, fingerprint):
                    raise ReceiptError("receipt_conflict")
                return None, record
            if not allow_new:
                raise ReceiptError("locator_busy")
            if time.time() > expires - RETENTION_SECONDS + FRESH_SECONDS:
                raise ReceiptError("receipt_expired")
            # Validate before pruning so malformed state is not erased and
            # mistaken for fresh capacity. This bounded journal is not a cache.
            for saved in db.execute("SELECT * FROM receipts"):
                _record(saved)
            db.execute("DELETE FROM receipts WHERE expires<=?", (time.time(),))
            if db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] >= MAX_RECEIPTS:
                raise ReceiptError("receipt_capacity")
            record = Record(key_hash=key_hash, owner=owner, run_id=run_id, fingerprint=fingerprint,
                            expires=expires, state="pending", admission="not_admitted",
                            binding=None, projection=None, error_code=None)
            db.execute("INSERT INTO receipts VALUES (?,?,?,?,?,?,?,?,?,?)", tuple(record.model_dump().values()))
        return Ticket(self.root, key_hash), record

    def lookup(self, key, owner, *, admin=False):
        key_hash, _ = identity(key)
        with _database(self.root) as db:
            record = _read(db, key_hash)
            _authorize(record, owner, admin)
            return record

    def prune(self):
        if not (self.root / FILENAME).exists():
            return 0
        with _database(self.root) as db, db:
            db.execute("BEGIN IMMEDIATE")
            for row in db.execute("SELECT * FROM receipts"):
                _record(row)
            return db.execute("DELETE FROM receipts WHERE expires<=?", (time.time(),)).rowcount
