"""Production-only, persistent locator admission and private-journal inventory.

Reservation consumption is conservative, not an invoice or refundable spending.
This store and the existing paid/receipt stores are not a distributed transaction.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import sqlite3
import stat
import threading
import time

from academic_agent.saved_source_usage import OperationContext
from api.saved_source_receipts import ReceiptError, canonical

RESERVATION_NANODOLLARS = 11_149_312
MAX_OPERATIONS = 5000
FILENAME = "control-v1.sqlite3"
_DAY_MS = 86_400_000
_SCHEMAS = {
    "control": "CREATE TABLE control (id INTEGER PRIMARY KEY, last_ms INTEGER NOT NULL, observed_ms INTEGER NOT NULL)",
    "operations": "CREATE TABLE operations (key_hash TEXT PRIMARY KEY, context TEXT NOT NULL, admitted_ms INTEGER NOT NULL, reservation INTEGER NOT NULL)",
}


@dataclass(frozen=True)
class Settings:
    enabled: bool = False
    execution_enabled: bool = False
    daily_request_cap: int = 0
    daily_usd_cap: Decimal = Decimal("0")
    min_interval_seconds: Decimal = Decimal("0")

    @classmethod
    def from_env(cls):
        def integer(name):
            raw = os.environ.get(name, "0")
            return int(raw) if raw.isascii() and raw.isdecimal() and len(raw) <= 7 else 0

        def decimal(name):
            try:
                raw = os.environ.get(name, "0")
                if len(raw) > 24:
                    return Decimal(0)
                value = Decimal(raw)
                return value if value.is_finite() and value >= 0 else Decimal(0)
            except InvalidOperation:
                return Decimal(0)

        return cls(
            enabled=os.environ.get("SOURCE_LOCATOR_ENABLED") in {"1", "true"},
            execution_enabled=os.environ.get("SOURCE_LOCATOR_EXECUTION_ENABLED") in {"1", "true"},
            daily_request_cap=integer("SOURCE_LOCATOR_DAILY_REQUEST_CAP"),
            daily_usd_cap=decimal("SOURCE_LOCATOR_DAILY_USD_CAP"),
            min_interval_seconds=decimal("SOURCE_LOCATOR_MIN_INTERVAL_SECONDS"),
        )

    @property
    def execution_allowed(self):
        return (self.enabled is True and self.execution_enabled is True
                and type(self.daily_request_cap) is int and 0 < self.daily_request_cap <= MAX_OPERATIONS
                and isinstance(self.daily_usd_cap, Decimal) and self.daily_usd_cap.is_finite()
                and Decimal(0) < self.daily_usd_cap <= Decimal("1000000")
                and self.daily_usd_cap * 1_000_000_000 >= RESERVATION_NANODOLLARS
                and isinstance(self.min_interval_seconds, Decimal) and self.min_interval_seconds.is_finite()
                and Decimal(0) < self.min_interval_seconds <= Decimal(86400))


def _fault():
    return ReceiptError("execution_unavailable")


def _plain(path, *, directory):
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400
            or (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)) is False):
        raise _fault()


class ControlStore:
    """One process and one dedicated controller; construction performs no I/O."""

    def __init__(self, root, settings):
        self.root, self.settings = Path(root), settings
        self._lock = threading.RLock()

    @contextmanager
    def database(self, *, readonly=False):
        db = None
        try:
            _plain(self.root, directory=True)
            path = self.root / FILENAME
            _plain(path, directory=False)
            db = sqlite3.connect(path.absolute().as_uri() + ("?mode=ro" if readonly else "?mode=rw"),
                                 uri=True, timeout=2)
            if not readonly:
                db.execute("PRAGMA synchronous=FULL")
            definitions = db.execute("SELECT name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            if (definitions != sorted(_SCHEMAS.items()) or db.execute("PRAGMA user_version").fetchone()[0] != 1
                    or db.execute("PRAGMA quick_check").fetchone()[0] != "ok"):
                raise _fault()
            yield db
        except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError):
            raise _fault() from None
        finally:
            if db is not None:
                db.close()

    def prepare(self):
        # Only an absent entire dedicated root can be initialized. A missing
        # control DB in an occupied root is lost admission history, not reset.
        with self._lock:
            try:
                self.root.parent.mkdir(parents=True, exist_ok=True)
                _plain(self.root.parent, directory=True)
                try:
                    self.root.mkdir()
                except FileExistsError:
                    pass
                else:
                    path = self.root / FILENAME
                    with path.open("xb"):
                        pass
                    db = sqlite3.connect(path.absolute().as_uri() + "?mode=rw", uri=True)
                    try:
                        db.execute("PRAGMA synchronous=FULL")
                        with db:
                            for definition in _SCHEMAS.values():
                                db.execute(definition)
                            db.execute("INSERT INTO control VALUES (1, 0, 0)")
                            db.execute("PRAGMA user_version=1")
                        (self.root / "native").mkdir()
                    finally:
                        db.close()
                with self.database(readonly=True) as db:
                    self._rows(db)
                _plain(self.root / "native", directory=True)
            except (OSError, sqlite3.Error):
                raise _fault() from None

    @staticmethod
    def _rows(db):
        control = db.execute("SELECT id, last_ms, observed_ms FROM control").fetchall()
        if (len(control) != 1 or control[0][0] != 1 or type(control[0][1]) is not int
                or type(control[0][2]) is not int
                or not 0 <= control[0][1] <= control[0][2] <= 9_007_199_254_740_991):
            raise _fault()
        rows = db.execute("SELECT key_hash, context, admitted_ms, reservation FROM operations LIMIT ?", (MAX_OPERATIONS + 1,)).fetchall()
        if len(rows) > MAX_OPERATIONS:
            raise _fault()
        checked = []
        for key, raw, admitted, reservation in rows:
            try:
                if type(raw) is not str or len(raw.encode("ascii")) > 8192:
                    raise ValueError("invalid_control")
                context = OperationContext.model_validate_json(raw, strict=True)
                if (canonical(context.model_dump()) != raw or context.receipt_key_sha256 != key
                        or type(admitted) is not int or admitted <= 0 or admitted > control[0][1]
                        or context.expires_at * 1000 <= admitted
                        or type(reservation) is not int or reservation != RESERVATION_NANODOLLARS):
                    raise ValueError("invalid_control")
                checked.append((context, admitted, reservation))
            except (ValueError, TypeError, UnicodeError):
                raise _fault() from None
        return checked, control[0][1], control[0][2]

    def reserve(self, operation):
        if not self.settings.execution_allowed or type(operation) is not OperationContext:
            raise _fault()
        with self._lock, self.database() as db, db:
            db.execute("BEGIN IMMEDIATE")
            rows, last, observed = self._rows(db)
            now = time.time_ns() // 1_000_000
            # Reject clock rollback. Restart, a fresh key or an uncertain
            # request cannot reset this global interval or its UTC-day sums.
            interval_ms = self.settings.min_interval_seconds * 1000
            today = [row for row in rows if row[1] // _DAY_MS == now // _DAY_MS]
            if (now < observed or operation.expires_at * 1000 <= now or now - last < interval_ms
                    or any(row[0].receipt_key_sha256 == operation.receipt_key_sha256 for row in rows)
                    or len(rows) >= MAX_OPERATIONS or len(today) >= self.settings.daily_request_cap
                    or sum(row[2] for row in today) + RESERVATION_NANODOLLARS > self.settings.daily_usd_cap * 1_000_000_000):
                raise _fault()
            db.execute("INSERT INTO operations VALUES (?,?,?,?)", (
                operation.receipt_key_sha256, canonical(operation.model_dump()), now, RESERVATION_NANODOLLARS))
            db.execute("UPDATE control SET last_ms=?, observed_ms=? WHERE id=1", (now, now))
        return self.root / "native" / operation.receipt_key_sha256

    def prune_native(self):
        """Caller holds the controller gate and has excluded all live threads."""
        with self._lock:
            if not self.root.exists():
                return 0
            with self.database() as db, db:
                db.execute("BEGIN IMMEDIATE")
                rows, _, observed = self._rows(db)
                native = self.root / "native"
                _plain(native, directory=True)
                known = {row[0].receipt_key_sha256 for row in rows}
                directories = list(native.iterdir())
                if len(directories) > MAX_OPERATIONS or any(path.name not in known for path in directories):
                    raise _fault()
                # Check the entire inventory before deleting any private bytes.
                for path in directories:
                    _plain(path, directory=True)
                    children = list(path.iterdir())
                    if len(children) > 2 or any(child.name not in {"manifest.json", "events.jsonl"} for child in children):
                        raise _fault()
                    for child in children:
                        _plain(child, directory=False)
                        if child.stat().st_size > 256 * 1024:
                            raise _fault()
                now = time.time_ns() // 1_000_000
                if now < observed:
                    raise _fault()
                # Deleting expired rows also deletes their clock evidence.
                # Commit this independent floor with the deletion so a later
                # rollback/restart cannot reopen a consumed day. Do not move
                # last_ms: periodic cleanup must not starve the paid interval.
                db.execute("UPDATE control SET observed_ms=? WHERE id=1", (now,))
                removed = 0
                for context, admitted, _ in rows:
                    if context.expires_at * 1000 > now or admitted // _DAY_MS >= now // _DAY_MS:
                        continue
                    path = native / context.receipt_key_sha256
                    if path.exists():
                        # Do not recursively delete arbitrary trees. Only the
                        # two inventoried native files in this exact child exist.
                        if path.resolve().parent != native.resolve():
                            raise _fault()
                        for child in path.iterdir():
                            _plain(child, directory=False)
                            child.unlink()
                        path.rmdir()
                    db.execute("DELETE FROM operations WHERE key_hash=?", (context.receipt_key_sha256,))
                    removed += 1
                return removed
