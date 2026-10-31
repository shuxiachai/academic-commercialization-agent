"""Email-and-password accounts for a public deployment.

The access gate (api/access.py) was built for a handful of invited people:
the operator mints codes and hands them out. A product needs the other shape:
anyone can create an account, and what they run is billed to keys they bring
themselves. This module is the account half of that. Keys are not kept here:
an account identifies a person and scopes their history; their LLM and search
keys travel with each request, exactly as the existing bring-your-own-key
path sends them, and are never written to disk by this server.

Off by default. Setting ACCOUNTS_DB to a file path turns accounts on; a
deployment that leaves it unset sees no change at all, like the access gate.
ACCOUNTS_SIGNUP is open (anyone), invite (anyone who knows
ACCOUNTS_INVITE_CODE) or closed (nobody; existing accounts keep working).
ACCOUNTS_ADMIN_EMAILS names the accounts that see every owner's history,
read at request time so it can change without touching the table. Because
registration verifies no email, an address on that list can be registered
only with the invite code: otherwise whoever typed the operator's address
first would be the operator.

Passwords are hashed with scrypt from the standard library (no new
dependency), with a per-password salt and parameters recorded beside the
hash so they can be raised later without invalidating old rows. Session
tokens are random, sent back once, and stored only as their SHA-256; a
stolen table cannot be replayed. Repeated failed logins lock the pair
of email and source address for a while, so a guesser is stopped without a
stranger being able to lock a user out by guessing at their address; a
looser cap on the email alone still stops a guesser who rotates addresses.
Both are independent of the per-client rate limiter in api/main.py.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

SESSION_SECONDS = 30 * 86400
PASSWORD_MIN = 10
PASSWORD_MAX = 200
EMAIL_MAX = 254
LOCKOUT_FAILURES = 8            # per email and source address
LOCKOUT_EMAIL_FAILURES = 50     # per email across every source
LOCKOUT_SECONDS = 15 * 60
SIGNUP_MODES = ("open", "invite", "closed")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_OWNER_PREFIX = "user:"
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 14, 8, 1
# scrypt needs 128*r*N bytes; hashlib caps at 32 MiB unless told otherwise.
_SCRYPT_MAXMEM = 2 ** 26
_SCHEMA_LOCK = Lock()
_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    disabled INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS login_throttle (
    key TEXT PRIMARY KEY,
    failures INTEGER NOT NULL,
    locked_until INTEGER NOT NULL
);
"""


class AccountError(Exception):
    """A refusal the caller can show: `code` is stable, `message` is prose."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class User:
    id: int
    email: str

    @property
    def owner(self) -> str:
        """The owner tag runs, uploads and receipts are recorded under."""
        return f"{_OWNER_PREFIX}{self.id}"

    @property
    def admin(self) -> bool:
        return self.email in admin_emails()


# ── Configuration ──────────────────────────────────────────────────────────

def database_path() -> Path | None:
    value = (os.getenv("ACCOUNTS_DB") or "").strip()
    return Path(value) if value else None


def enabled() -> bool:
    return database_path() is not None


def signup_mode() -> str:
    """open, invite or closed; an unknown value is closed, never open."""
    value = (os.getenv("ACCOUNTS_SIGNUP") or "open").strip().lower()
    return value if value in SIGNUP_MODES else "closed"


def signup_open() -> bool:
    return signup_mode() != "closed"


def invite_code() -> str | None:
    value = (os.getenv("ACCOUNTS_INVITE_CODE") or "").strip()
    return value or None


def _invited(invite: object) -> bool:
    code = invite_code()
    return code is not None and isinstance(invite, str) and hmac.compare_digest(invite.strip(), code)


def admin_emails() -> frozenset[str]:
    raw = os.getenv("ACCOUNTS_ADMIN_EMAILS") or ""
    return frozenset(e for e in (normalize_email(part) for part in raw.split(",")) if e)


# ── Storage ────────────────────────────────────────────────────────────────

@contextmanager
def _database():
    path = database_path()
    if path is None:
        raise AccountError("accounts_disabled", "Accounts are not enabled on this deployment.")
    with _SCHEMA_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(path), timeout=5)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA secure_delete=ON")
        with connection:
            connection.executescript(_SCHEMA)
        yield connection
    finally:
        connection.close()


# ── Normalisation and hashing ──────────────────────────────────────────────

def normalize_email(value: object) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _check_email(email: str) -> None:
    if not email or len(email) > EMAIL_MAX or not _EMAIL.fullmatch(email):
        raise AccountError("invalid_email", "Enter a valid email address.")


def _check_password(password: object, email: str) -> None:
    if not isinstance(password, str) or len(password) < PASSWORD_MIN:
        raise AccountError("weak_password", f"Use a password of at least {PASSWORD_MIN} characters.")
    if len(password) > PASSWORD_MAX:
        raise AccountError("weak_password", f"Use a password of at most {PASSWORD_MAX} characters.")
    if password.strip().lower() == email:
        raise AccountError("weak_password", "The password must differ from the email address.")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
                            maxmem=_SCRYPT_MAXMEM, dklen=32)
    encode = lambda raw: base64.b64encode(raw).decode("ascii")  # noqa: E731
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${encode(salt)}${encode(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt),
                                n=int(n), r=int(r), p=int(p), maxmem=_SCRYPT_MAXMEM, dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── Accounts ───────────────────────────────────────────────────────────────

def register(email: object, password: object, *, invite: object = None, now: float | None = None) -> User:
    """Create an account, or refuse with a stable code the client can show.

    An email on the admin list needs the invite code whatever the sign-up
    mode; with no invite code configured it cannot be registered at all,
    which is the safe reading of an operator who has not set one up yet.
    """
    email = normalize_email(email)
    _check_email(email)
    _check_password(password, email)
    mode = signup_mode()
    if mode == "closed":
        raise AccountError("signup_closed", "This deployment is not accepting new accounts.")
    if email in admin_emails() and not _invited(invite):
        raise AccountError("invite_required", "This address is reserved. Enter the invite code to register it.")
    if mode == "invite" and not _invited(invite):
        raise AccountError("invite_required", "Registration needs the invite code for this deployment.")
    stamp = int(now if now is not None else time.time())
    with _database() as db:
        try:
            with db:
                cursor = db.execute(
                    "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                    (email, hash_password(password), stamp))
        except sqlite3.IntegrityError:
            raise AccountError("email_taken", "An account with this email already exists.") from None
        return User(id=cursor.lastrowid, email=email)


def _throttle_keys(email: str, client: str | None) -> tuple[tuple[str, int], ...]:
    """(key, threshold) pairs a failure counts against: the email from this
    source, and the email from anywhere."""
    return ((f"source:{email}|{client or 'unknown'}", LOCKOUT_FAILURES),
            (f"email:{email}", LOCKOUT_EMAIL_FAILURES))


def login(email: object, password: object, *, client: str | None = None,
          now: float | None = None) -> tuple[str, User]:
    """Check a password and open a session. Returns the one-time token.

    A wrong email and a wrong password get the same answer, and a password is
    still hashed when the email is unknown, so timing does not tell them apart.
    `client` is the caller's address as the server trusts it; failures lock
    that address out of this email, not the email itself.
    """
    email = normalize_email(email)
    stamp = int(now if now is not None else time.time())
    if not isinstance(password, str):
        password = ""
    keys = _throttle_keys(email, client)
    with _database() as db:
        for key, _ in keys:
            row = db.execute("SELECT locked_until FROM login_throttle WHERE key = ?", (key,)).fetchone()
            if row is not None and row["locked_until"] > stamp:
                raise AccountError("locked", "Too many failed sign-ins. Try again in a few minutes.")
        user = db.execute("SELECT id, email, password_hash, disabled FROM users WHERE email = ?", (email,)).fetchone()
        stored = user["password_hash"] if user is not None else hash_password("placeholder-timing-only")
        if user is None or not verify_password(password, stored):
            _record_failure(db, keys, stamp)
            raise AccountError("invalid_credentials", "That email and password were not accepted.")
        if user["disabled"]:
            raise AccountError("disabled", "This account is disabled.")
        token = secrets.token_urlsafe(32)
        with db:
            db.execute("DELETE FROM login_throttle WHERE key = ?", (keys[0][0],))
            db.execute(
                "INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
                (_token_hash(token), user["id"], stamp, stamp + SESSION_SECONDS, stamp))
            db.execute("DELETE FROM sessions WHERE expires_at <= ?", (stamp,))
        return token, User(id=user["id"], email=user["email"])


def _record_failure(db, keys, stamp: int) -> None:
    with db:
        for key, threshold in keys:
            row = db.execute("SELECT failures, locked_until FROM login_throttle WHERE key = ?", (key,)).fetchone()
            # A count older than the lock window starts over; otherwise a
            # user's occasional typos would add up to a lock over months.
            stale = row is not None and row["locked_until"] and row["locked_until"] + LOCKOUT_SECONDS < stamp
            failures = (0 if row is None or stale else row["failures"]) + 1
            locked_until = stamp + LOCKOUT_SECONDS if failures >= threshold else 0
            if failures >= threshold:
                failures = 0  # the lock itself is the penalty; count afresh after it
            db.execute(
                "INSERT INTO login_throttle (key, failures, locked_until) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET failures = excluded.failures, locked_until = excluded.locked_until",
                (key, failures, locked_until))
        db.execute("DELETE FROM login_throttle WHERE locked_until = 0 AND failures = 0")


def session_user(token: object, *, now: float | None = None) -> User | None:
    """The account a session token belongs to, or None for anything else.

    An expired or unknown token is simply None: the caller treats the
    request as anonymous, the same as a wrong access code. Nothing here
    distinguishes "never existed" from "expired" to the outside.
    """
    if not enabled() or not isinstance(token, str) or not token or len(token) > 128:
        return None
    stamp = int(now if now is not None else time.time())
    with _database() as db:
        row = db.execute(
            "SELECT s.token_hash, s.expires_at, u.id, u.email, u.disabled FROM sessions s "
            "JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?", (_token_hash(token),)).fetchone()
        if row is None or row["disabled"]:
            return None
        if row["expires_at"] <= stamp:
            with db:
                db.execute("DELETE FROM sessions WHERE token_hash = ?", (row["token_hash"],))
            return None
        with db:
            db.execute("UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?", (stamp, row["token_hash"]))
        return User(id=row["id"], email=row["email"])


def logout(token: object) -> bool:
    """End one session. True when a session was actually removed."""
    if not enabled() or not isinstance(token, str) or not token:
        return False
    with _database() as db, db:
        return db.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),)).rowcount > 0


def set_disabled(email: object, disabled: bool) -> bool:
    """Operator switch: a disabled account cannot sign in and its sessions end."""
    email = normalize_email(email)
    with _database() as db, db:
        changed = db.execute("UPDATE users SET disabled = ? WHERE email = ?", (1 if disabled else 0, email)).rowcount > 0
        if changed and disabled:
            db.execute("DELETE FROM sessions WHERE user_id = (SELECT id FROM users WHERE email = ?)", (email,))
        return changed


def is_user_owner(owner: object) -> bool:
    return isinstance(owner, str) and owner.startswith(_OWNER_PREFIX)


def label_for_owner(owner: object) -> str | None:
    """The admin view's answer to "whose run is this" for an account owner tag."""
    if not enabled() or not is_user_owner(owner):
        return None
    try:
        user_id = int(owner[len(_OWNER_PREFIX):])
    except ValueError:
        return None
    with _database() as db:
        row = db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
    return row["email"] if row is not None else None
