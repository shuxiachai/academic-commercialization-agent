"""Production-only origin pinning; never infer public authority from proxy headers.

The frozen receipt helper couples ingress validation to the ASGI scheme. Keep
its non-origin checks here explicitly rather than fabricating a Request/scope
to make that helper accept a TLS-terminating deployment. Frozen labs stay exact.
"""

from ipaddress import IPv4Address, IPv6Address
import re

from api.saved_source_receipt_app import (
    MAX_ACCESS_CODE_BYTES, MAX_BODY_BYTES, MAX_CRITICAL_HEADER_BYTES, _CRITICAL, _KEY,
)
from api.saved_source_receipts import ReceiptError

_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.ASCII)


def canonical_origin(value):
    """A deliberately narrow ASCII origin, not a URL parser's repaired URL.

    Scheme/DNS case, IPv6 spelling and default ports are canonicalized. Empty
    delimiters, userinfo, zone IDs, wildcard/list syntax and trailing DNS dots
    are refused, not silently stripped or interpreted as equivalent hosts.
    """
    if (type(value) is not str or not 1 <= len(value) <= 2048
            or any(ord(char) <= 32 or ord(char) >= 127 for char in value)):
        raise ValueError("invalid_origin")
    match = re.fullmatch(r"(https?)://([^/?#]+)", value, flags=re.IGNORECASE | re.ASCII)
    if match is None:
        raise ValueError("invalid_origin")
    scheme, authority = match[1].lower(), match[2]
    if authority.startswith("["):
        address = re.fullmatch(r"\[([0-9a-fA-F:.]+)\](?::([0-9]{1,5}))?", authority)
        if address is None:
            raise ValueError("invalid_origin")
        host, port = str(IPv6Address(address[1])), address[2]
    else:
        address = re.fullmatch(r"([^:]+)(?::([0-9]{1,5}))?", authority)
        if address is None:
            raise ValueError("invalid_origin")
        host, port = address[1].lower(), address[2]
        if len(host) > 253 or any(_LABEL.fullmatch(label) is None for label in host.split(".")):
            raise ValueError("invalid_origin")
        if all(char in "0123456789." for char in host):
            # Refuse abbreviated/leading-zero numeric hosts that browsers can
            # interpret differently from a DNS-name comparison.
            host = str(IPv4Address(host))
    port = int(port) if port is not None else (443 if scheme == "https" else 80)
    if not 1 <= port <= 65535:
        raise ValueError("invalid_origin")
    return scheme, host, port


class OriginPolicy:
    """One configuration snapshot with explicit invalidity; no environment reread."""

    def __init__(self, public_origin=""):
        self.expected = None
        self.valid = True
        if public_origin != "":
            try:
                self.expected = canonical_origin(public_origin)
            except ValueError:
                self.valid = False

    def check(self, request, headers):
        if not self.valid:
            raise ReceiptError("execution_unavailable")
        try:
            if self.expected is not None:
                # Host is required even for origin-less receipt GETs. Its
                # omitted port is interpreted using the PUBLIC scheme, never
                # the backend's HTTP scheme or a forwarded host/proto field.
                actual = canonical_origin(f"{self.expected[0]}://{headers.get(b'host', '')}")
                if actual != self.expected:
                    raise ValueError("different_host")
                expected = self.expected
            elif b"origin" in headers:
                expected = canonical_origin(f"{request.scope['scheme']}://{headers.get(b'host', '')}")
            else:
                return
            if b"origin" in headers and canonical_origin(headers[b"origin"]) != expected:
                raise ValueError("different_origin")
        except ValueError:
            raise ReceiptError("origin_denied") from None

    def check_page(self, request):
        # Pages/assets need no credentials or receipt key. Apply the same raw
        # Host/Origin contract without borrowing the API's body/consent rules.
        self.check(request, _headers(request))


def _headers(request):
    critical = [(name.lower(), value) for name, value in request.scope["headers"] if name.lower() in _CRITICAL]
    if sum(len(name) + len(value) for name, value in critical) > MAX_CRITICAL_HEADER_BYTES:
        raise ReceiptError("headers_too_large")
    headers = {}
    for name, raw in critical:
        if name in headers:
            raise ReceiptError("invalid_request")
        headers[name] = raw.decode("latin-1")
    return headers


def request_headers(request, origin_policy):
    """Mirror frozen ingress rules; change only the production origin authority.

    No header is removed, overwritten or normalized in the original Request.
    The production wrapper separately bounds/requires its explicit consent.
    """
    if request.scope.get("query_string"):
        raise ReceiptError("invalid_request")
    headers = _headers(request)
    code = headers.get(b"x-access-code", "")
    if len(code) > MAX_ACCESS_CODE_BYTES:
        raise ReceiptError("headers_too_large")
    if not code or any(ord(char) < 32 or ord(char) >= 127 for char in code):
        raise ReceiptError("access_denied")
    key = headers.get(b"idempotency-key", "")
    if _KEY.fullmatch(key) is None:
        raise ReceiptError("invalid_receipt_key")
    origin_policy.check(request, headers)
    if b"content-encoding" in headers:
        raise ReceiptError("unsupported_media_type")
    if b"content-length" in headers:
        length = headers[b"content-length"]
        if not length.isascii() or not length.isdecimal() or len(length) > 20:
            raise ReceiptError("invalid_request")
        if b"transfer-encoding" in headers:
            raise ReceiptError("invalid_request")
        if int(length) > MAX_BODY_BYTES:
            raise ReceiptError("body_too_large")
    if request.method == "POST" and headers.get(b"content-type", "").lower() != "application/json":
        raise ReceiptError("unsupported_media_type")
    return key, code
