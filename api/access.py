"""Shared-secret gate for the API.

This project's only deployment target is a short-lived public demo link
handed to specific people (interviewers), not a multi-tenant product — so
there is no user table, no signup, just one secret the operator sets before
sharing the link. Every request under /api/ must carry it in the
X-Access-Code header, or it is rejected before touching anything that spends
money (LLM calls, Serper searches).

Leaving ACCESS_CODE unset disables the gate entirely: local development and
anyone self-hosting without configuring it see no difference from before.
"""

from __future__ import annotations

import hmac
import os

ACCESS_CODE = os.getenv("ACCESS_CODE")


def check(header_value: str | None) -> bool:
    """True if the gate is open: either disabled, or the code matches.

    Constant-time comparison — a demo link is exactly the kind of target
    where an early-exit string comparison invites a timing attack for free.
    """
    if ACCESS_CODE is None:
        return True
    return header_value is not None and hmac.compare_digest(header_value, ACCESS_CODE)


def authorizes_run(header_value: str | None, *, byok: bool) -> bool:
    """True if this request may create a new run — the one action that
    always spends someone's money.

    Two ways in: the deployment's own access code (billed to the operator),
    or complete bring-your-own-key credentials (billed to the requester).
    Both are checked here rather than in the path-based gate, because this
    decision needs the parsed request body — whether BYOK fields are present
    — which a middleware would have to parse the body early to see.
    """
    return byok or check(header_value)
