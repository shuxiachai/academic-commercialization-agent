"""One literal project credential; no dotenv expansion or environment fallback.

Admission is RFC 6750 b64token syntax within a local byte bound, not vendor
authentication or a vendor key-length rule. Python memory is not securely erased.
"""

from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MAX_FILE_BYTES = 64 * 1024
VARIABLE = "DASHSCOPE_API_KEY"
TOKEN = re.compile(r"[A-Za-z0-9\-._~+/]+=*", re.ASCII)


class CredentialError(Exception):
    """One fixed disposition, never a credential-bearing diagnostic."""

    def __init__(self):
        super().__init__("credential_preflight_failed")


class SecretKey:
    """In-memory only; ordinary representations cannot expose the value."""

    __slots__ = ("_value",)

    def __init__(self, value: str):
        self._value = value

    def __repr__(self):
        return "SecretKey(<redacted>)"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol):
        raise TypeError("credential_serialization_forbidden")

    def authorization(self) -> str:
        return "Bearer " + self._value

    def appears_in(self, text: str) -> bool:
        return self._value in text


def parse_key(raw: bytes) -> SecretKey:
    """Parse physical LF/CRLF lines; interpret only the exact selected LHS.

    Horizontal spacing before the name/equals and optional literal export are
    syntax, not part of the key. The RHS is never stripped or unescaped. Other
    assignments are ignored without interpreting their quotes or references.
    """
    if not isinstance(raw, bytes) or len(raw) > MAX_FILE_BYTES:
        raise CredentialError()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        raise CredentialError() from None
    if "\ufeff" in text:
        raise CredentialError()
    selected = None
    lines = text.split("\n")
    for index, line in enumerate(lines):
        # Do not use splitlines(): VT, FF, NEL and Unicode separators must not
        # invent a new selected assignment. A lone CR is not a physical newline.
        if index < len(lines) - 1 and line.endswith("\r"):
            line = line[:-1]
        line = line.lstrip(" \t")
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^export[ \t]+", "", line, count=1)
        match = re.match(r"([A-Za-z_][A-Za-z_0-9]*)(.*)\Z", line, re.DOTALL)
        if match is None or match[1] != VARIABLE:
            continue
        if selected is not None or not re.match(r"^[ \t]*=", match[2]):
            raise CredentialError()
        value = match[2].split("=", 1)[1]
        if value[:1] in ("'", '"'):
            if len(value) < 2 or value[-1] != value[0]:
                raise CredentialError()
            value = value[1:-1]
        if (not value.isascii() or not 10 <= len(value) <= 256
                or TOKEN.fullmatch(value) is None or "..." in value):
            raise CredentialError()
        selected = SecretKey(value)
    if selected is None:
        raise CredentialError()
    return selected


def read_key() -> SecretKey:
    """Fixed read-only path, one bounded read; no caller path or env override."""
    try:
        with (ROOT / ".env").open("rb") as file:
            raw = file.read(MAX_FILE_BYTES + 1)
        return parse_key(raw)
    except (OSError, CredentialError):
        raise CredentialError() from None
