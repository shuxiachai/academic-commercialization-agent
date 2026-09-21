"""Bounded accounting sidecar, separate from the frozen receipt journal.

The caller supplies an already authorized real receipt record. Reads never
create files, reconstruct native ledgers, dispatch work or repair missing data.
This single-process store is not a transaction with the receipt/paid ledgers.
"""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Literal

from academic_agent.report_evidence_snapshot import FrozenModel
from academic_agent.saved_source_usage import (
    AccountingError, ExecutionFactsV1, Hash, Money, NativeFactsV1, OperationContext,
)
from api.saved_source_receipts import Record, canonical

FILENAME = ".saved-source-accounting-v1.sqlite3"
MAX_RECORDS = 5000
MAX_RECORD_BYTES = 8192
_SCHEMA = "CREATE TABLE accounting (key_hash TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)"
_SCHEMA_LOCK = threading.Lock()


class _NotRecorded(AccountingError):
    pass


class _BindingMismatch(AccountingError):
    pass


class _Claim(FrozenModel):
    key_hash: str
    owner: str
    fingerprint: str
    run_id: str
    expires: int

    @classmethod
    def from_record(cls, record):
        if type(record) is not Record:
            raise AccountingError()
        checked = Record.model_validate(record.model_dump(warnings="error"))
        return cls(**checked.model_dump(include=set(cls.model_fields)))


class _Entry(FrozenModel):
    version: Literal[1] = 1
    claim: _Claim
    context: OperationContext | None = None
    phase: Literal["begun", "bound", "entered", "captured", "sealed"] = "begun"
    wire_sha256: Hash | None = None
    reservation_usd: Money | None = None
    native: NativeFactsV1 | None = None
    execution: ExecutionFactsV1 | None = None


@contextmanager
def _database(root, *, create=False, readonly=False):
    path = root / FILENAME
    db = None
    try:
        if path.is_symlink():
            raise AccountingError()
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
            mode = "ro" if readonly else "rw"
            db = sqlite3.connect(path.absolute().as_uri() + "?mode=" + mode, uri=True, timeout=2)
            if not readonly:
                db.execute("PRAGMA synchronous=FULL")
            if initialize:
                with db:
                    db.execute(_SCHEMA)
                    db.execute("PRAGMA user_version=1")
            tables = db.execute(
                "SELECT name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            if (tables != [("accounting", _SCHEMA)] or db.execute("PRAGMA user_version").fetchone()[0] != 1
                    or db.execute("PRAGMA quick_check").fetchone()[0] != "ok"):
                raise AccountingError()
        yield db
    except (sqlite3.Error, OSError):
        raise AccountingError() from None
    finally:
        if db is not None:
            db.close()


def _checked(value):
    try:
        if type(value) is not dict or set(value) != set(_Entry.model_fields) or type(value.get("version")) is not int:
            raise ValueError("invalid_stored_schema")
        entry = _Entry.model_validate(value)
        claim = entry.claim
        context = entry.context
        if context is not None and (
                context.receipt_key_sha256 != claim.key_hash or context.owner_id != claim.owner
                or context.intent_fingerprint != claim.fingerprint or context.run_id != claim.run_id
                or context.expires_at != claim.expires):
            raise ValueError("changed_context")
        if entry.phase != "begun" and entry.phase != "sealed" and context is None:
            raise ValueError("missing_context")
        if (entry.wire_sha256 is None) != (entry.reservation_usd is None):
            raise ValueError("incomplete_reservation")
        if entry.wire_sha256 is not None:
            if context is None or entry.phase not in {"entered", "captured", "sealed"}:
                raise ValueError("unbound_entry")
        if entry.phase == "entered" and entry.wire_sha256 is None:
            raise ValueError("missing_entry")
        if entry.native is not None and (
                (entry.wire_sha256 is not None and (entry.wire_sha256 != entry.native.wire_sha256
                  or entry.reservation_usd != entry.native.reservation_usd))
                or entry.phase not in {"captured", "sealed"}):
            raise ValueError("changed_native_identity")
        if entry.native is not None and entry.wire_sha256 is None and entry.native.dispatch_state != "not_dispatched":
            raise ValueError("missing_native_fence")
        if entry.native is not None and context is None:
            raise ValueError("unbound_native_facts")
        if entry.phase == "captured" and entry.native is None:
            raise ValueError("missing_native")
        if (entry.phase == "sealed") != (entry.execution is not None):
            raise ValueError("invalid_seal")
        if (entry.execution is not None and entry.execution.accounted_selector_entries == 0
                and (entry.wire_sha256 is not None or entry.native is not None)):
            raise ValueError("erased_accounted_entry")
        return entry
    except (TypeError, ValueError, RecursionError):
        raise AccountingError() from None


def _encode(entry):
    raw = canonical(_checked(entry.model_dump(warnings="error")).model_dump())
    if len(raw.encode("ascii")) > MAX_RECORD_BYTES:
        raise AccountingError()
    return raw


def _read(db, claim):
    row = db.execute("SELECT value FROM accounting WHERE key_hash=?", (claim.key_hash,)).fetchone()
    if row is None:
        raise _NotRecorded()
    if type(row[0]) is not str or len(row[0]) > MAX_RECORD_BYTES:
        raise AccountingError()
    try:
        value = json.loads(row[0])
        if canonical(value) != row[0]:
            raise AccountingError()
        entry = _checked(value)
        if entry.claim != claim:
            raise _BindingMismatch()
        if time.time() >= claim.expires:
            raise AccountingError()
        return entry
    except (ValueError, TypeError, RecursionError):
        raise AccountingError() from None


class OperationObservation:
    """One operation thread owns each handle and its monotonic transitions."""

    def __init__(self, store, claim):
        self._store, self._claim = store, claim
        self._owner_thread = threading.get_ident()
        self._context = None
        self._failed = False

    @property
    def operation(self):
        if self._context is None or self._failed:
            raise AccountingError()
        return self._context

    def _change(self, allowed, transform):
        try:
            if self._failed or threading.get_ident() != self._owner_thread:
                raise AccountingError()
            with _database(self._store.root) as db, db:
                db.execute("BEGIN IMMEDIATE")
                entry = _read(db, self._claim)
                if entry.phase not in allowed:
                    raise AccountingError()
                after = _checked(transform(entry.model_dump()))
                db.execute("UPDATE accounting SET value=? WHERE key_hash=?", (_encode(after), self._claim.key_hash))
            return after
        except Exception:  # noqa: BLE001 -- failed accounting must stop admission, never expose storage details.
            self._failed = True
            raise AccountingError() from None

    def bind(self, bound_record, selector_identity):
        claim = _Claim.from_record(bound_record)
        if claim != self._claim or bound_record.binding is None or bound_record.state != "pending":
            self._failed = True
            raise AccountingError()
        if type(selector_identity) is not str or not 1 <= len(selector_identity) <= 256 or not selector_identity.strip():
            self._failed = True
            raise AccountingError()
        context = OperationContext(
            receipt_key_sha256=claim.key_hash, owner_id=claim.owner, intent_fingerprint=claim.fingerprint,
            run_id=claim.run_id, expires_at=claim.expires,
            selector_identity_sha256=hashlib.sha256(selector_identity.encode("utf-8")).hexdigest(),
            snapshot_hash=bound_record.binding.snapshot_hash, catalog_hash=bound_record.binding.catalog_hash,
        )
        self._change({"begun"}, lambda value: {**value, "context": context.model_dump(), "phase": "bound"})
        self._context = context
        return context

    def before_native_entry(self, *, wire_sha256, reservation_usd):
        self._change({"bound"}, lambda value: {**value, "phase": "entered",
                     "wire_sha256": wire_sha256, "reservation_usd": reservation_usd})

    def capture(self, native_facts):
        if type(native_facts) is not NativeFactsV1:
            self._failed = True
            raise AccountingError()
        # Request validation can prove no dispatch without ever reaching the
        # native fence. Capture that controlled outcome without a fake entry.
        self._change({"bound", "entered"}, lambda value: {**value, "phase": "captured",
                     "native": native_facts.model_dump(warnings="error")})

    def seal(self, execution_facts):
        if type(execution_facts) is not ExecutionFactsV1:
            self._failed = True
            raise AccountingError()
        self._change({"begun", "bound", "entered", "captured"}, lambda value: {
            **value, "phase": "sealed", "execution": execution_facts.model_dump(warnings="error"),
        })


class AccountingStore:
    """No constructor I/O; only begin can initialize the new bounded sidecar."""

    def __init__(self, root):
        self.root = Path(root)

    def begin(self, claimed_record):
        try:
            claim = _Claim.from_record(claimed_record)
            if (claimed_record.state != "pending" or claimed_record.binding is not None
                    or claimed_record.admission != "not_admitted" or time.time() >= claim.expires):
                raise AccountingError()
            with _database(self.root, create=True) as db, db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT COUNT(*) FROM accounting").fetchone()[0] >= MAX_RECORDS:
                    raise AccountingError()
                # Existing, expired or damaged records cannot be reset to buy a
                # second entry. Retention cleanup is deliberately not GET work.
                db.execute("INSERT INTO accounting VALUES (?,?)", (claim.key_hash, _encode(_Entry(claim=claim))))
            return OperationObservation(self, claim)
        except Exception:  # noqa: BLE001 -- callers get a fixed failure before any native entry.
            raise AccountingError() from None

    def observe(self, authorized_record):
        # Projection import is local so controller/storage never load a provider.
        from academic_agent.saved_source_usage import project_usage, unavailable_usage

        try:
            claim = _Claim.from_record(authorized_record)
            if not (self.root / FILENAME).exists():
                raise _NotRecorded()
            with _database(self.root, readonly=True) as db:
                entry = _read(db, claim)
            if entry.context is not None and (authorized_record.binding is None
                    or entry.context.snapshot_hash != authorized_record.binding.snapshot_hash
                    or entry.context.catalog_hash != authorized_record.binding.catalog_hash):
                raise _BindingMismatch()
            return project_usage(entry)
        except _NotRecorded:
            return unavailable_usage(authorized_record.key_hash, authorized_record.run_id,
                                     authorized_record.expires, "not_recorded")
        except _BindingMismatch:
            return unavailable_usage(authorized_record.key_hash, authorized_record.run_id,
                                     authorized_record.expires, "binding_mismatch")
        except Exception:  # noqa: BLE001 -- absence, corruption and binding faults are unavailable, never free.
            return unavailable_usage(authorized_record.key_hash, authorized_record.run_id, authorized_record.expires)
