"""An account's API keys, saved with the account and sealed at rest.

An account used to be "an identity and a history scope, nothing more": its
keys lived in the browser and travelled with each request. That made the
keys a property of one browser. A second browser, a signed-out session or a
cleared profile had none, and the person was asked to paste two keys again;
the owner's report, after two attempts to fix it in the browser (#407, #408),
was that the form still came up every time. Settings belong to the account.

What is kept, and how:

- One row per account in the account database: the account's id, when the
  keys were saved, and one sealed token. The provider, the model and both
  keys are inside the token; nothing about them is readable in the file, so
  a copy of the database (its backups are copies) says only that an account
  saved keys.
- The token is sealed with Fernet (AES-128-CBC with an HMAC, from the
  `cryptography` package) under a secret that is not in the database:
  ACCOUNT_KEYS_SECRET where the operator sets one, otherwise a random secret
  written once to a file beside the database. The file is not part of a
  backup. On the same volume it does not protect against whoever holds the
  volume; setting the variable keeps the secret off the volume altogether.
- A secret that is lost or changed does not break anything: keys that
  cannot be opened read as not saved, the account is asked for them once,
  and saving replaces the row.

What uses them: a paid operation from an account whose request brings no
keys runs on the saved ones, exactly as if the request had carried them
(api.main._with_account_keys). A request that brings keys runs on those and
saves nothing. The keys are never sent back to a browser: the page is told
the provider, the model and the last four characters of each key.

There is no switch to turn this off. Wherever there are accounts an account
may save its keys, and each account decides for itself: the key form's box
can be unticked, and saved keys can be removed. One behaviour means the
page and the privacy text can say one thing and be right everywhere.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from cryptography.fernet import Fernet, InvalidToken

from api import accounts

_LOGGER = logging.getLogger(__name__)
SECRET_SUFFIX = ".keys-secret"
_SEARCH = ("tavily", "serper")
_LOCK = Lock()
_secrets: dict[str, bytes] = {}


@dataclass(frozen=True)
class Keys:
    provider: str
    model: str
    llm_api_key: str
    search: str
    search_api_key: str
    updated_at: int

    def request_fields(self) -> dict[str, str]:
        """The fields a request would have carried: what the request models call them."""
        return {"llm_provider": self.provider, "llm_api_key": self.llm_api_key, "llm_model": self.model,
                f"{self.search}_api_key": self.search_api_key}


def hint(key: str) -> str:
    """Enough to tell which key it is, and no more: the last four characters
    of a key long enough that four characters are a small part of it."""
    return "…" + key[-4:] if len(key) >= 12 else "…"


def _forget_secret() -> None:
    """Drop the secret read so far, as a restart does. For tests."""
    with _LOCK:
        _secrets.clear()


def _secret() -> bytes:
    """The Fernet key: from the operator's variable, or a file made once beside the database."""
    configured = os.getenv("ACCOUNT_KEYS_SECRET", "").strip()
    if configured:
        # Any text the operator chose becomes a key of the right size.
        return base64.urlsafe_b64encode(hashlib.sha256(configured.encode("utf-8")).digest())
    path = accounts.database_path()
    if path is None:
        raise accounts.AccountError("accounts_disabled", "Accounts are not enabled on this deployment.")
    location = Path(str(path) + SECRET_SUFFIX)
    with _LOCK:
        cached = _secrets.get(str(location))
        if cached is not None:
            return cached
        try:
            made = location.read_bytes().strip()
        except FileNotFoundError:
            made = Fernet.generate_key()
            location.parent.mkdir(parents=True, exist_ok=True)
            try:
                # Created, never replaced: two processes starting together must agree on one secret.
                descriptor = os.open(location, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                made = location.read_bytes().strip()
            else:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(made + b"\n")
        _secrets[str(location)] = made
        return made


class KeysChanged(Exception):
    """The saved set was replaced, more than once, while its model was being changed."""


def _seal(keys: Keys) -> str:
    plain = json.dumps({"provider": keys.provider, "model": keys.model, "llm_api_key": keys.llm_api_key,
                        "search": keys.search, "search_api_key": keys.search_api_key,
                        "nonce": secrets.token_hex(8)}).encode("utf-8")
    return Fernet(_secret()).encrypt(plain).decode("ascii")


def save(user: accounts.User, *, provider: str, model: str, llm_api_key: str, search: str, search_api_key: str,
         now: float | None = None) -> Keys:
    """Seal and keep `user`'s keys, replacing any saved before."""
    if search not in _SEARCH:
        raise ValueError("search must be tavily or serper")
    stamp = int(time.time() if now is None else now)
    keys = Keys(provider=provider, model=model, llm_api_key=llm_api_key, search=search,
                search_api_key=search_api_key, updated_at=stamp)
    sealed = _seal(keys)
    with accounts._database() as db, db:
        db.execute("INSERT INTO account_keys (user_id, sealed, updated_at) VALUES (?, ?, ?) "
                   "ON CONFLICT(user_id) DO UPDATE SET sealed = excluded.sealed, updated_at = excluded.updated_at",
                   (user.id, sealed, stamp))
    return keys


def _sealed(db, user: accounts.User):
    """`user`'s row as stored: the sealed record and when it was written."""
    return db.execute("SELECT sealed, updated_at FROM account_keys WHERE user_id = ?", (user.id,)).fetchone()


def load(user: accounts.User) -> Keys | None:
    """`user`'s saved keys, or None: none saved, or a row that cannot be opened."""
    with accounts._database() as db:
        row = _sealed(db, user)
    return _opened(user, row)


def _opened(user: accounts.User, row) -> Keys | None:
    if row is None:
        return None
    try:
        opened = json.loads(Fernet(_secret()).decrypt(str(row["sealed"]).encode("ascii")))
        keys = Keys(provider=str(opened["provider"]), model=str(opened["model"]),
                    llm_api_key=str(opened["llm_api_key"]), search=str(opened["search"]),
                    search_api_key=str(opened["search_api_key"]), updated_at=int(row["updated_at"]))
    except (InvalidToken, ValueError, KeyError, TypeError, UnicodeError):
        # A changed secret or a damaged row. Said once per read, with nothing of the row in it.
        _LOGGER.warning("Saved keys of account %d cannot be opened; treated as not saved.", user.id)
        return None
    if keys.search not in _SEARCH or not keys.llm_api_key or not keys.search_api_key:
        return None
    return keys


def saved(user: accounts.User) -> bool:
    """Whether `user` has keys this deployment can use."""
    return load(user) is not None


def change_model(user: accounts.User, model: str, *, now: float | None = None) -> Keys | None:
    """Keep `user`'s saved keys and use them with `model`. None when nothing usable is saved.

    The record is one sealed text, so changing a part of it means opening
    it and writing it back. A whole new set saved between the two (another
    device, another tab) must win: writing back would put the old keys over
    the new. So the write goes through only if the row still holds the text
    that was read, and otherwise the new row is read and the model set on
    that. Twice replaced in the time of one change is not a race worth a
    third try; the caller is told the keys changed.
    """
    for _attempt in range(2):
        with accounts._database() as db:
            row = _sealed(db, user)
        keys = _opened(user, row)
        if keys is None:
            return None
        stamp = int(time.time() if now is None else now)
        changed = Keys(provider=keys.provider, model=model, llm_api_key=keys.llm_api_key, search=keys.search,
                       search_api_key=keys.search_api_key, updated_at=stamp)
        with accounts._database() as db, db:
            written = db.execute("UPDATE account_keys SET sealed = ?, updated_at = ? WHERE user_id = ? AND sealed = ?",
                                 (_seal(changed), stamp, user.id, row["sealed"])).rowcount
        if written:
            return changed
    raise KeysChanged


def remove(user: accounts.User) -> bool:
    """Forget `user`'s saved keys. True if there were any."""
    with accounts._database() as db, db:
        return db.execute("DELETE FROM account_keys WHERE user_id = ?", (user.id,)).rowcount > 0
