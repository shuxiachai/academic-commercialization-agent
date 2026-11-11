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
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from api import mail

SESSION_SECONDS = 30 * 86400
PASSWORD_MIN = 10
PASSWORD_MAX = 200
EMAIL_MAX = 254
LOCKOUT_FAILURES = 8            # per email and source address
LOCKOUT_EMAIL_FAILURES = 50     # per email across every source
LOCKOUT_SECONDS = 15 * 60
# How many accounts may be created: per source address per hour, and on the
# whole deployment per UTC day. With sign-up open and no email verification,
# these are what stands between a script and a table full of addresses. Both
# count accounts actually created, not attempts, so a person correcting a typo
# is not charged for it; 0 turns a cap off. In memory, like the host caps:
# one replica, and a restart forgets the count, which errs toward admitting.
SIGNUPS_PER_HOUR_PER_CLIENT = int(os.getenv("ACCOUNTS_SIGNUPS_PER_HOUR", "5"))
SIGNUPS_PER_DAY = int(os.getenv("ACCOUNTS_SIGNUPS_PER_DAY", "100"))
# A verification link works this long and once. Asking for another one is
# allowed this often, so a page cannot be used to fill someone's inbox.
VERIFY_SECONDS = 24 * 3600
VERIFY_RESEND_SECONDS = 60
_VERIFY = "verify"
# A password-reset link works this long and once. A second request for the
# same address within RESET_REQUEST_SECONDS sends nothing, so the form cannot
# be used to fill someone's inbox; it is short because the one-hour link that
# most people ask for twice is the one that landed in the spam folder.
RESET_SECONDS = 3600
RESET_REQUEST_SECONDS = 60
_RESET = "reset"
SIGNUP_MODES = ("open", "invite", "closed")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_OWNER_PREFIX = "user:"
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 14, 8, 1
# scrypt needs 128*r*N bytes; hashlib caps at 32 MiB unless told otherwise.
_SCRYPT_MAXMEM = 2 ** 26
_SCHEMA_LOCK = Lock()
_SIGNUP_LOCK = Lock()
_TRIAL_LOCK = Lock()
_signups_by_client: dict[str, list[float]] = {}
_signups_today: list[float] = []
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
CREATE TABLE IF NOT EXISTS email_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS trial_days (
    day TEXT PRIMARY KEY,
    used INTEGER NOT NULL
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
    # The address has been proven: the account opened a link sent to it, or
    # it was created before the deployment could send mail, or by an operator.
    verified: bool = True
    # The account asked to be emailed when one of its runs ends (api/notices.py).
    notify_done: bool = False

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


def admin_funded() -> bool:
    """Whether an administrator's paid operations may run on the deployment's own keys.

    On by default once administrator addresses are named (ACCOUNTS_ADMIN_EMAILS),
    off with ACCOUNTS_ADMIN_FUNDED=0. The server still needs a model key and a
    search key for it to mean anything; api.main checks those at the request.
    Every other account keeps paying with its own keys.
    """
    if not admin_emails():
        return False
    return os.getenv("ACCOUNTS_ADMIN_FUNDED", "1").strip().lower() not in ("0", "false", "no", "off")


def _count_setting(name: str, default: int) -> int:
    """A whole number of zero or more from the environment; anything else is the default."""
    raw = (os.getenv(name) or "").strip()
    return int(raw) if raw.isdigit() else default


def trial_runs() -> int:
    """How many assessments a verified account may start on the deployment's keys.

    Off (0) unless the operator sets ACCOUNTS_TRIAL_RUNS: the deployment
    pays for these, and a deployment that never chose to should never find
    that it did. Since sign-up opened, an account has had to bring a model
    key and a search key from two other services before its first run; a
    number here lets it see one result on its own question first. The
    server still needs keys of its own to pay with; api.main checks those
    at the request, as it does for an administrator's runs.
    """
    return _count_setting("ACCOUNTS_TRIAL_RUNS", 0)


def trial_daily_cap() -> int:
    """Trial assessments the deployment starts in one UTC day, across every account.

    ACCOUNTS_TRIAL_DAILY, 20 unless set; 0 turns the bound off, as for the
    other caps. This, not the number per account, is what bounds the bill:
    an address is cheap to make, and the sign-up caps bound how many.
    """
    return _count_setting("ACCOUNTS_TRIAL_DAILY", 20)


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
            _migrate(connection)
        yield connection
    finally:
        connection.close()


def _migrate(connection) -> None:
    """Bring a database from before email verification up to date.

    `verified_at` arrives with the accounts that exist already marked: they
    were created when there was no way to send them a link, and refusing
    them their runs now would punish them for having been first. The mark is
    made in the same step as the column, so an account created unverified
    afterwards is never swept up by it.
    """
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
    if "verified_at" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN verified_at INTEGER")
        connection.execute("UPDATE users SET verified_at = created_at")
    # Opt-in, so accounts from before the column have it off.
    if "notify_done" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN notify_done INTEGER NOT NULL DEFAULT 0")
    # Nothing spent: an account that was here before trials gets its number too.
    if "trial_used" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN trial_used INTEGER NOT NULL DEFAULT 0")


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


def verification_required() -> bool:
    """A new account must prove its address before it can start paid work.

    True exactly when the deployment can send the link (api/mail.py). With
    no mail set up there is nothing to verify with, and accounts are created
    verified, as they were before there was mail.
    """
    return mail.configured()


# ── Accounts ───────────────────────────────────────────────────────────────

def _signup_window(client: str | None, stamp: float) -> None:
    """Refuse a sign-up that would exceed the per-address or per-day cap.

    Caller holds _SIGNUP_LOCK. Only accounts actually created are counted
    (see `_signup_created`), so the check reads the lists and writes nothing.
    """
    hour, day = stamp - 3600, stamp - 86400
    if client is not None and SIGNUPS_PER_HOUR_PER_CLIENT:
        recent = [t for t in _signups_by_client.get(client, ()) if t > hour]
        _signups_by_client[client] = recent
        if len(recent) >= SIGNUPS_PER_HOUR_PER_CLIENT:
            raise AccountError("signup_throttled", "Too many accounts were created from this address recently. "
                               "Try again in an hour.")
    if SIGNUPS_PER_DAY:
        _signups_today[:] = [t for t in _signups_today if t > day]
        if len(_signups_today) >= SIGNUPS_PER_DAY:
            raise AccountError("signup_throttled", "This deployment has reached today's limit on new accounts. "
                               "Try again tomorrow.")


def _signup_created(client: str | None, stamp: float) -> None:
    """Count one created account; caller holds _SIGNUP_LOCK."""
    if client is not None:
        _signups_by_client.setdefault(client, []).append(stamp)
    _signups_today.append(stamp)


def register(email: object, password: object, *, invite: object = None, client: str | None = None,
             now: float | None = None) -> User:
    """Create an account, or refuse with a stable code the client can show.

    An email on the admin list needs the invite code whatever the sign-up
    mode; with no invite code configured it cannot be registered at all,
    which is the safe reading of an operator who has not set one up yet.

    `client` is the caller's address, for the sign-up caps. The caps are
    checked after the rules above, so a closed deployment or a missing
    invite code is reported as itself and not as a limit.
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
    # One lock across check, insert and count: two requests from one address
    # arriving together must not both pass a cap with one place left.
    verified_at = None if verification_required() else stamp
    with _SIGNUP_LOCK:
        _signup_window(client, stamp)
        with _database() as db:
            try:
                with db:
                    cursor = db.execute(
                        "INSERT INTO users (email, password_hash, created_at, verified_at) VALUES (?, ?, ?, ?)",
                        (email, hash_password(password), stamp, verified_at))
            except sqlite3.IntegrityError:
                raise AccountError("email_taken", "An account with this email already exists.") from None
        _signup_created(client, stamp)
        return User(id=cursor.lastrowid, email=email, verified=verified_at is not None)


# ── Email verification ─────────────────────────────────────────────────────

def issue_verification(user: User, *, now: float | None = None, cooldown: bool = True) -> str:
    """Make the one-time token for a verification link and return it, once.

    Any earlier token of the account stops working: the newest link is the
    one in the newest message, and an old message found later proves
    nothing. With `cooldown`, a token younger than VERIFY_RESEND_SECONDS is
    not replaced (`verification_cooldown`), so "send it again" cannot be
    clicked into a flood. An account that is already verified gets
    `already_verified`: there is nothing to prove.
    """
    stamp = int(now if now is not None else time.time())
    with _database() as db:
        row = db.execute("SELECT verified_at FROM users WHERE id = ?", (user.id,)).fetchone()
        if row is None:
            raise AccountError("unknown_account", "No account has this id.")
        if row["verified_at"] is not None:
            raise AccountError("already_verified", "This address is already verified.")
        if cooldown:
            newest = db.execute("SELECT MAX(created_at) AS at FROM email_tokens WHERE user_id = ? AND purpose = ?",
                                (user.id, _VERIFY)).fetchone()["at"]
            if newest is not None and stamp - newest < VERIFY_RESEND_SECONDS:
                raise AccountError("verification_cooldown",
                                   f"A verification email was sent moments ago. Wait {VERIFY_RESEND_SECONDS} seconds "
                                   "before asking for another.")
        token = secrets.token_urlsafe(32)
        with db:
            db.execute("DELETE FROM email_tokens WHERE user_id = ? AND purpose = ?", (user.id, _VERIFY))
            db.execute("INSERT INTO email_tokens (token_hash, user_id, purpose, created_at, expires_at) "
                       "VALUES (?, ?, ?, ?, ?)", (_token_hash(token), user.id, _VERIFY, stamp, stamp + VERIFY_SECONDS))
            db.execute("DELETE FROM email_tokens WHERE expires_at <= ?", (stamp,))
        return token


def verify_email(token: object, *, now: float | None = None) -> User:
    """Mark the account a verification token belongs to as verified, and spend the token.

    Unknown and expired links get different answers (`verification_invalid`,
    `verification_expired`) because the person holding one needs to know
    whether to ask for another; neither answer names an account. Every
    verification token of the account goes with the one spent.
    """
    if not isinstance(token, str) or not token or len(token) > 128:
        raise AccountError("verification_invalid", "This verification link is not valid.")
    stamp = int(now if now is not None else time.time())
    with _database() as db:
        row = db.execute(
            "SELECT t.token_hash, t.expires_at, u.id, u.email, u.verified_at FROM email_tokens t "
            "JOIN users u ON u.id = t.user_id WHERE t.token_hash = ? AND t.purpose = ?",
            (_token_hash(token), _VERIFY)).fetchone()
        if row is None:
            raise AccountError("verification_invalid", "This verification link is not valid.")
        if row["expires_at"] <= stamp:
            with db:
                db.execute("DELETE FROM email_tokens WHERE token_hash = ?", (row["token_hash"],))
            raise AccountError("verification_expired", "This verification link has expired. Sign in and ask for a new one.")
        with db:
            if row["verified_at"] is None:
                db.execute("UPDATE users SET verified_at = ? WHERE id = ?", (stamp, row["id"]))
            db.execute("DELETE FROM email_tokens WHERE user_id = ? AND purpose = ?", (row["id"], _VERIFY))
        return User(id=row["id"], email=row["email"], verified=True)


def mark_verified(email: object) -> bool:
    """Operator switch: treat the address as proven without a link.

    For the operator who has checked by other means, or whose mail is down.
    True when an account was changed; False when it was already verified.
    """
    email = normalize_email(email)
    with _database() as db, db:
        row = db.execute("SELECT id, verified_at FROM users WHERE email = ?", (email,)).fetchone()
        if row is None:
            raise AccountError("unknown_account", "No account has this email address.")
        if row["verified_at"] is not None:
            return False
        db.execute("UPDATE users SET verified_at = ? WHERE id = ?", (int(time.time()), row["id"]))
        db.execute("DELETE FROM email_tokens WHERE user_id = ? AND purpose = ?", (row["id"], _VERIFY))
        return True


def issue_password_reset(email: object, *, now: float | None = None) -> tuple[User, str] | None:
    """Make the one-time token for a password-reset link, or None when nothing is to be sent.

    None for an address no account has, for a disabled account, for an
    address that was asked about less than RESET_REQUEST_SECONDS ago, and for
    something that is not an address at all; the caller answers the same way
    in every case, because the form is open to anyone and must not be a way
    to learn which addresses have accounts. Any earlier reset token of the
    account stops working, as with verification: the newest link is the one
    in the newest message.
    """
    email = normalize_email(email)
    try:
        _check_email(email)
    except AccountError:
        return None
    stamp = int(now if now is not None else time.time())
    with _database() as db:
        row = db.execute("SELECT id, email, verified_at, disabled FROM users WHERE email = ?", (email,)).fetchone()
        if row is None or row["disabled"]:
            return None
        newest = db.execute("SELECT MAX(created_at) AS at FROM email_tokens WHERE user_id = ? AND purpose = ?",
                            (row["id"], _RESET)).fetchone()["at"]
        if newest is not None and stamp - newest < RESET_REQUEST_SECONDS:
            return None
        token = secrets.token_urlsafe(32)
        with db:
            db.execute("DELETE FROM email_tokens WHERE user_id = ? AND purpose = ?", (row["id"], _RESET))
            db.execute("INSERT INTO email_tokens (token_hash, user_id, purpose, created_at, expires_at) "
                       "VALUES (?, ?, ?, ?, ?)", (_token_hash(token), row["id"], _RESET, stamp, stamp + RESET_SECONDS))
            db.execute("DELETE FROM email_tokens WHERE expires_at <= ?", (stamp,))
        return User(id=row["id"], email=row["email"], verified=row["verified_at"] is not None), token


def redeem_reset_link(token: object, new: object, *, now: float | None = None) -> User:
    """Set a new password for the account a reset token belongs to, and spend the token.

    The password policy is checked before the token is spent, so a password
    the policy refuses does not cost the person their link. Then, as with the
    operator's reset: every session of the account ends and its lockout rows
    go, because the reason for a reset may be that someone else has the old
    password, or that the owner locked themself out guessing it. The link
    reached the address, which is what verification asks, so an unverified
    account comes out verified. A disabled account is refused (`disabled`)
    and the token kept: re-enabling is the operator's decision, and the
    person need not ask twice once it is made. Unknown and expired links get
    different answers (`reset_invalid`, `reset_expired`), neither naming an
    account.
    """
    if not isinstance(token, str) or not token or len(token) > 128:
        raise AccountError("reset_invalid", "This password reset link is not valid.")
    stamp = int(now if now is not None else time.time())
    with _database() as db:
        row = db.execute(
            "SELECT t.token_hash, t.expires_at, u.id, u.email, u.disabled FROM email_tokens t "
            "JOIN users u ON u.id = t.user_id WHERE t.token_hash = ? AND t.purpose = ?",
            (_token_hash(token), _RESET)).fetchone()
        if row is None:
            raise AccountError("reset_invalid", "This password reset link is not valid.")
        if row["expires_at"] <= stamp:
            with db:
                db.execute("DELETE FROM email_tokens WHERE token_hash = ?", (row["token_hash"],))
            raise AccountError("reset_expired", "This password reset link has expired. Ask for a new one.")
        if row["disabled"]:
            raise AccountError("disabled", "This account is disabled.")
        _check_password(new, row["email"])
        with db:
            db.execute("UPDATE users SET password_hash = ?, verified_at = COALESCE(verified_at, ?) WHERE id = ?",
                       (hash_password(new), stamp, row["id"]))
            db.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
            db.execute("DELETE FROM email_tokens WHERE user_id = ? AND purpose IN (?, ?)",
                       (row["id"], _RESET, _VERIFY))
            db.execute("DELETE FROM login_throttle WHERE key = ? OR key LIKE ?",
                       (f"email:{row['email']}", f"source:{row['email']}|%"))
        return User(id=row["id"], email=row["email"], verified=True)


def _refuse_if_locked(db, keys, stamp: int) -> None:
    for key, _ in keys:
        row = db.execute("SELECT locked_until FROM login_throttle WHERE key = ?", (key,)).fetchone()
        if row is not None and row["locked_until"] > stamp:
            raise AccountError("locked", "Too many failed sign-ins. Try again in a few minutes.")


def _confirm_password(db, user: "User", password: object, client: str | None, stamp: int) -> None:
    """Re-check the password of an already signed-in account.

    A session is not enough to change the password or delete the account: a
    borrowed laptop or a stolen token would otherwise be the whole account.
    Wrong guesses count against the same lockout as a sign-in, so a stolen
    session cannot be used to guess the password either.
    """
    keys = _throttle_keys(user.email, client)
    _refuse_if_locked(db, keys, stamp)
    row = db.execute("SELECT password_hash FROM users WHERE id = ?", (user.id,)).fetchone()
    if row is None or not isinstance(password, str) or not verify_password(password, row["password_hash"]):
        _record_failure(db, keys, stamp)
        raise AccountError("invalid_credentials", "The current password was not accepted.")


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
        _refuse_if_locked(db, keys, stamp)
        user = db.execute("SELECT id, email, password_hash, disabled, verified_at, notify_done FROM users WHERE email = ?",
                          (email,)).fetchone()
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
        return token, User(id=user["id"], email=user["email"], verified=user["verified_at"] is not None,
                           notify_done=bool(user["notify_done"]))


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
            "SELECT s.token_hash, s.expires_at, u.id, u.email, u.disabled, u.verified_at, u.notify_done FROM sessions s "
            "JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?", (_token_hash(token),)).fetchone()
        if row is None or row["disabled"]:
            return None
        if row["expires_at"] <= stamp:
            with db:
                db.execute("DELETE FROM sessions WHERE token_hash = ?", (row["token_hash"],))
            return None
        with db:
            db.execute("UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?", (stamp, row["token_hash"]))
        return User(id=row["id"], email=row["email"], verified=row["verified_at"] is not None,
                    notify_done=bool(row["notify_done"]))


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


def reset_password(email: object, new: object) -> int:
    """Operator reset: set a password without knowing the current one.

    Reached only from the operator's shell (api/account_admin.py); no HTTP
    route calls it, because nothing a visitor can send should be able to
    replace a password it cannot prove it knows.

    Every session of the account ends, since the reason for a reset may be
    that someone else has the old password. The lockout rows for the address
    go too: a person who was locked out while guessing their own password
    can sign in with the new one at once. A disabled account stays disabled;
    re-enabling is a separate decision (`set_disabled`). Returns how many
    sessions ended.
    """
    email = normalize_email(email)
    _check_password(new, email)
    with _database() as db, db:
        row = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if row is None:
            raise AccountError("unknown_account", "No account has this email address.")
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new), row["id"]))
        ended = db.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],)).rowcount
        db.execute("DELETE FROM login_throttle WHERE key = ? OR key LIKE ?",
                   (f"email:{email}", f"source:{email}|%"))
        return ended


def change_password(user: User, current: object, new: object, *, keep_token: object = None,
                    client: str | None = None, now: float | None = None) -> int:
    """Set a new password after confirming the current one.

    Every other session of the account ends: whoever changed the password
    wants the old one to stop working everywhere. The session that made the
    change (`keep_token`) stays signed in. Returns how many sessions ended.
    """
    stamp = int(now if now is not None else time.time())
    with _database() as db:
        _confirm_password(db, user, current, client, stamp)
        _check_password(new, user.email)
        if new == current:
            raise AccountError("weak_password", "The new password must differ from the current one.")
        keep = _token_hash(keep_token) if isinstance(keep_token, str) and keep_token else ""
        with db:
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new), user.id))
            return db.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?",
                              (user.id, keep)).rowcount


def delete_account(user: User, password: object, *, client: str | None = None,
                   now: float | None = None) -> None:
    """Remove the account, its sessions and its lockout rows.

    The caller deletes what the account owns (runs, uploads, receipts) first
    and calls this last, so a failure part-way leaves an account that can
    sign in and try again rather than data nobody can reach.
    """
    stamp = int(now if now is not None else time.time())
    with _database() as db:
        _confirm_password(db, user, password, client, stamp)
        with db:
            db.execute("DELETE FROM sessions WHERE user_id = ?", (user.id,))
            db.execute("DELETE FROM users WHERE id = ?", (user.id,))
            db.execute("DELETE FROM login_throttle WHERE key = ? OR key LIKE ?",
                       (f"email:{user.email}", f"source:{user.email}|%"))


def confirm_password(user: User, password: object, *, client: str | None = None,
                     now: float | None = None) -> None:
    """Public form of the re-check, for a caller that must verify before it
    starts deleting things."""
    stamp = int(now if now is not None else time.time())
    with _database() as db:
        _confirm_password(db, user, password, client, stamp)


# ── A first assessment on the deployment's keys ────────────────────────────

@dataclass(frozen=True)
class TrialClaim:
    """One trial taken: whose, and against which UTC day's number. Release it once."""

    user_id: int
    day: str


def trial_left(user: "User") -> int:
    """Trials this account may still start: none when off, or until its address is proven."""
    allowed = trial_runs()
    if not allowed or not enabled() or not user.verified:
        return 0
    with _database() as db:
        row = db.execute("SELECT trial_used, disabled FROM users WHERE id = ?", (user.id,)).fetchone()
    if row is None or row["disabled"]:
        return 0
    return max(0, allowed - row["trial_used"])


def claim_trial(user: "User", *, now: float | None = None) -> TrialClaim:
    """Take one trial for `user`, or say why not.

    The account's own number and the deployment's number for the day are
    checked and counted in one step, so two requests arriving together
    cannot both take the last one. Refusals: `email_unverified`,
    `trial_used` (the account has had its number, or trials are off) and
    `trial_daily_exhausted` (the deployment has started its number today;
    the account's own is untouched and waits for tomorrow).
    """
    stamp = now if now is not None else time.time()
    day = datetime.fromtimestamp(stamp, UTC).date().isoformat()
    allowed, cap = trial_runs(), trial_daily_cap()
    with _TRIAL_LOCK, _database() as db:
        with db:
            row = db.execute("SELECT verified_at, disabled, trial_used FROM users WHERE id = ?",
                             (user.id,)).fetchone()
            if row is None or row["disabled"] or row["trial_used"] >= allowed:
                raise AccountError("trial_used", "This account has no free assessment left.")
            if row["verified_at"] is None:
                raise AccountError("email_unverified", "Verify your email address first.")
            today = db.execute("SELECT used FROM trial_days WHERE day = ?", (day,)).fetchone()
            if cap and today is not None and today["used"] >= cap:
                raise AccountError("trial_daily_exhausted",
                                   "Today's free assessments have all been started. Add your own API "
                                   "keys to run now, or come back after midnight UTC.")
            db.execute("UPDATE users SET trial_used = trial_used + 1 WHERE id = ?", (user.id,))
            db.execute("INSERT INTO trial_days (day, used) VALUES (?, 1) "
                       "ON CONFLICT(day) DO UPDATE SET used = used + 1", (day,))
    return TrialClaim(user_id=user.id, day=day)


def release_trial(claim: TrialClaim) -> None:
    """Give a claimed trial back: the run never started, or the provider could not be reached.

    Neither count goes below zero. Call it once for a claim: nothing here
    remembers that a claim was already released.
    """
    with _TRIAL_LOCK, _database() as db:
        with db:
            db.execute("UPDATE users SET trial_used = MAX(trial_used - 1, 0) WHERE id = ?", (claim.user_id,))
            db.execute("UPDATE trial_days SET used = MAX(used - 1, 0) WHERE day = ?", (claim.day,))


def owner_tag(user_id: int) -> str:
    """The owner tag of an account id, the same one `User.owner` gives."""
    return f"{_OWNER_PREFIX}{user_id}"


def user_by_id(user_id: object) -> User | None:
    if not enabled() or not isinstance(user_id, int) or isinstance(user_id, bool):
        return None
    with _database() as db:
        row = db.execute("SELECT id, email, verified_at, notify_done FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    return User(id=row["id"], email=row["email"], verified=row["verified_at"] is not None,
                notify_done=bool(row["notify_done"]))


def set_notify_done(user: User, enabled: bool) -> None:
    """Whether the account wants an email when one of its runs ends. Off until asked."""
    with _database() as db, db:
        db.execute("UPDATE users SET notify_done = ? WHERE id = ?", (1 if enabled else 0, user.id))


def list_users(*, now: float | None = None) -> list[dict]:
    """Every account, newest first, with its live sessions counted.

    For the admin console. A session past its expiry is not counted and the
    newest `last_seen_at` is of a live one: an expired token is not a
    sign-in, even before the next use of it removes the row.
    """
    stamp = int(now if now is not None else time.time())
    with _database() as db:
        rows = db.execute(
            "SELECT u.id, u.email, u.created_at, u.disabled, u.verified_at, u.trial_used, "
            "COUNT(s.token_hash) AS sessions, MAX(s.last_seen_at) AS last_seen_at "
            "FROM users u LEFT JOIN sessions s ON s.user_id = u.id AND s.expires_at > ? "
            "GROUP BY u.id ORDER BY u.created_at DESC, u.id DESC", (stamp,)).fetchall()
    return [dict(row) for row in rows]


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
