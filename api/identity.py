"""Who is asking: an access code, a signed-in account, or nobody.

Two credential systems share the API. The access code (api/access.py) is a
shared secret the operator hands to invited people and bills to the
deployment; an account (api/accounts.py) is a person who signed up and pays
with their own keys. Every handler that scopes history, tags a paid
operation or authorizes a mutation used to ask the access module directly.
They now ask this one, so the two systems cannot drift apart on what a
request is allowed to see or spend.

Precedence: a valid access code wins over a session token. A code holder who
also signed in is treated as the code holder, because the code is the only
one of the two that can spend the deployment's money, and that choice should
never be made by accident.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import Request

from api import access, accounts

Kind = Literal["code", "user", "none"]


@dataclass(frozen=True)
class Identity:
    kind: Kind
    #: Owner tag that this identity's runs, uploads and receipts are recorded
    #: under; None only for an anonymous request.
    tag: str | None
    #: Owner to scope history reads by; None for an admin (sees everything)
    #: and for an anonymous request (nothing to scope by).
    owner: str | None
    is_admin: bool
    user: accounts.User | None = None

    @property
    def anonymous(self) -> bool:
        return self.kind == "none"


ANONYMOUS = Identity(kind="none", tag=None, owner=None, is_admin=False)


def required() -> bool:
    """Whether an anonymous request is turned away from gated paths."""
    return access.gate_enabled() or accounts.enabled()


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def resolve(request: Request) -> Identity:
    """Identify the request from its headers; never raises for bad input.

    A malformed code or token is anonymous, not an error: the caller decides
    what anonymity means on its path (a 401, or nothing at all when neither
    system is configured).
    """
    try:
        matched = access.matching_code(request.headers.get("x-access-code"))
    except (TypeError, ValueError):
        matched = None
    if matched is not None:
        tag = access.owner_id(matched)
        admin = access.is_admin(matched)
        return Identity(kind="code", tag=tag, owner=None if admin else tag, is_admin=admin)
    token = _bearer(request)
    if token is None:
        return ANONYMOUS
    try:
        user = accounts.session_user(token)
    except accounts.AccountError:
        user = None
    if user is None:
        return ANONYMOUS
    admin = user.admin
    return Identity(kind="user", tag=user.owner, owner=None if admin else user.owner,
                    is_admin=admin, user=user)


def label_for_owner(owner: str | None) -> str | None:
    """What the admin history view shows beside a run: the code, or the email."""
    if owner is None:
        return None
    return access.label_for_owner(owner) or accounts.label_for_owner(owner)
