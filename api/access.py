"""Shared-secret gate for the API.

No user table, no signup — an operator mints one or more codes and hands
them to specific people (interviewers). Every request under /api/ must
carry a valid one in the X-Access-Code header, or it is rejected before
touching anything that spends money (LLM calls, search API calls).

Multiple codes exist so different holders don't share one identity: each
code's runs are tagged with owner_id(code) and the run list (api/runs.py)
filters by it, so code A's history never appears for code B. A run created
without any code (BYOK) gets no owner tag and so never appears in anyone's
list — see api/main.py's submit_run. ADMIN_CODE is the one exception: it
authorizes runs like any other code (its own runs tagged and rate-limited
the same way) but is exempted from the list filter, so whoever holds it
sees every code's history — see is_admin() and api/main.py's middleware.

Leaving ACCESS_CODE, ACCESS_CODES and ACCESS_CODE_ADMIN all unset disables
the gate entirely: local development and anyone self-hosting without
configuring any of them see no difference from before this existed.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sys

# Single code, kept for backward compatibility with existing deployments.
ACCESS_CODE = (os.getenv("ACCESS_CODE") or "").strip() or None

# Comma-separated codes, for handing out a distinct one per person so their
# run histories stay separate. Both variables are honored if set — read
# fresh on every call (not cached at import) so tests can patch either.
ACCESS_CODES = os.getenv("ACCESS_CODES")

# One further code, if set, that authorizes runs exactly like any other but
# additionally sees every code's history when listing — the one exception
# to per-code isolation, for the operator to check who has actually used
# their code without asking each person individually.
ADMIN_CODE = (os.getenv("ACCESS_CODE_ADMIN") or "").strip() or None


def _valid_codes() -> list[str]:
    codes = []
    if ACCESS_CODE:
        codes.append(ACCESS_CODE)
    if ACCESS_CODES:
        codes.extend(c.strip() for c in ACCESS_CODES.split(",") if c.strip())
    if ADMIN_CODE:
        codes.append(ADMIN_CODE)
    return codes


def is_admin(code: str) -> bool:
    """True if `code` — already a value matching_code() returned, so
    already validated in constant time against the configured set — is the
    admin code specifically."""
    return ADMIN_CODE is not None and code == ADMIN_CODE


def _warn_if_misconfigured() -> None:
    """Catch the copy-paste mistake this exists to prevent: pasting the
    whole `ACCESS_CODES=a,b,c` line — name, equals sign and all — as the
    *value* of a variable, rather than just the values. A code containing
    "=" or starting with "ACCESS_CODE" is not a plausible code anyone would
    intentionally choose, so it is almost certainly this exact mistake.
    A plain print rather than warnings.warn: this needs to show up in a
    platform's deploy logs unconditionally, not depend on however Python's
    warning filters happen to be configured at runtime.
    """
    for code in _valid_codes():
        if "=" in code or code.upper().startswith("ACCESS_CODE"):
            print(
                f"[access] a configured code looks like a mispasted variable "
                f"assignment rather than a real code: {code!r}. Check that "
                f"ACCESS_CODES holds only the comma-separated codes "
                f"themselves, not the 'ACCESS_CODES=' prefix.",
                file=sys.stderr,
            )


_warn_if_misconfigured()


def gate_enabled() -> bool:
    return bool(_valid_codes())


def matching_code(header_value: str | None) -> str | None:
    """The specific configured code the header matches, or None.

    Also None when the gate is disabled (no codes configured) — callers
    that need to distinguish "disabled" from "wrong code" should check
    gate_enabled() separately. Every candidate is compared in constant
    time; which one leaks nothing beyond total elapsed time, an accepted
    trade for a handful of codes.
    """
    if header_value is None:
        return None
    for candidate in _valid_codes():
        if hmac.compare_digest(header_value, candidate):
            return candidate
    return None


def check(header_value: str | None) -> bool:
    """True if the gate is open: either disabled, or the code matches."""
    if not gate_enabled():
        return True
    return matching_code(header_value) is not None


def owner_id(code: str) -> str:
    """Stable identifier for a specific code, used to tag which code a run
    belongs to without keeping the raw secret sitting in run directories on
    disk. Not a security boundary by itself — codes are already secret —
    just avoids writing them out in plaintext a second place."""
    return hashlib.sha256(code.encode()).hexdigest()[:16]


def label_for_owner(owner: str | None) -> str | None:
    """The admin view's answer to "which code ran this": recovers the raw
    code an owner_id() hash came from by testing it against every code
    currently configured, rather than storing the raw code a second place
    on disk. Showing the admin the actual code is not a new disclosure —
    whoever controls ADMIN_CODE already controls every code in .env — it
    just makes the combined history legible instead of an unlabelled merge.

    None if `owner` is None (BYOK, or no code configured) or belongs to a
    code that has since been removed or rotated out of the configuration.
    """
    if owner is None:
        return None
    for code in _valid_codes():
        if owner_id(code) == owner:
            return code
    return None
