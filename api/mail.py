"""Outbound email: the one way the service reaches a person who is not on the page.

The service sends email for exactly one reason so far: to prove that whoever
created an account can read the address they typed. Nothing else is sent, and
nothing is sent to anyone who did not just ask for it.

Delivery goes through Resend's HTTPS API (https://resend.com/docs/api-reference/emails/send-email)
with the standard library's connection, for the same reason the alert robots
do: the key is a secret, and a client that logs each request's details would
write it into the service log. The API key travels in one header and is
never part of any message this module produces.

Two settings choose where mail goes; set exactly one of them:

- `MAIL_RESEND_API_KEY`: a Resend sending key for the domain `MAIL_FROM` is
  on. Production.
- `MAIL_OUTBOX`: a directory. Each message is written there as a JSON file
  instead of being sent. Development, where the link in the message is
  opened by hand.

Both need `MAIL_FROM` (the sender, `Name <address>` or a bare address) and
`PUBLIC_URL` (where this deployment is reached, for the links in messages;
read from configuration and never from a request's Host header, since the
link in an email must not be something a request can choose). With neither
setting, mail is `off`: accounts are created verified, as before there was
mail. With a setting that cannot be used, mail is `misconfigured`, which
`/health` shows and which behaves as `off` for accounts.

`MAIL_PER_DAY` (default 100, Resend's free allowance) caps what the
deployment sends in a UTC day, counted in memory like the sign-up caps:
one replica, and a restart forgets, which errs toward sending.
"""
from __future__ import annotations

import html
import http.client
import json
import logging
import os
import re
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from threading import Lock

_LOGGER = logging.getLogger(__name__)

RESEND_HOST = "api.resend.com"
_TIMEOUT_SECONDS = 10.0
_REPLY_LIMIT = 4096
_ADDRESS = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")
_SENDER = re.compile(r"^(?:(?P<name>[^<>]{1,80})\s*)?<(?P<address>[^<>\s]+)>$")
_SETTINGS = "MAIL_RESEND_API_KEY or MAIL_OUTBOX"

_LOCK = Lock()
_sent_today: list[float] = []
_last_sent_at: float | None = None
_last_failed_at: float | None = None


class MailError(Exception):
    """A message that was not delivered. Its text never names the key or the address."""


# ── Configuration ──────────────────────────────────────────────────────────

def _setting(name: str) -> str:
    return (os.getenv(name) or "").strip()


def sender() -> str | None:
    """`MAIL_FROM` as given, when it is an address or `Name <address>`; otherwise None."""
    value = " ".join(_setting("MAIL_FROM").split())
    if _ADDRESS.fullmatch(value):
        return value
    match = _SENDER.fullmatch(value)
    if match and _ADDRESS.fullmatch(match["address"]):
        return value
    return None


def public_url() -> str | None:
    """`PUBLIC_URL` without its trailing slash, when it is an http(s) origin; otherwise None."""
    value = _setting("PUBLIC_URL").rstrip("/")
    if re.fullmatch(r"https?://[A-Za-z0-9.-]+(?::\d{1,5})?", value):
        return value
    return None


def per_day() -> int:
    try:
        value = int(_setting("MAIL_PER_DAY") or 100)
    except ValueError:
        return 100
    return max(value, 0)


def mode() -> str:
    """off, resend, outbox or misconfigured."""
    key, outbox = _setting("MAIL_RESEND_API_KEY"), _setting("MAIL_OUTBOX")
    if not key and not outbox:
        return "off"
    if (key and outbox) or sender() is None or public_url() is None:
        return "misconfigured"
    return "resend" if key else "outbox"


def configured() -> bool:
    """Mail can be sent: accounts then start unverified and are sent a link."""
    return mode() in ("resend", "outbox")


def reset() -> None:
    """Forget the day's count and the last outcome; tests."""
    global _last_sent_at, _last_failed_at
    with _LOCK:
        _sent_today.clear()
        _last_sent_at = _last_failed_at = None


# ── Messages ───────────────────────────────────────────────────────────────

def _service_host() -> str:
    url = public_url() or ""
    return url.split("://", 1)[-1]


def verification_message(link: str, *, hours: int = 24) -> tuple[str, str, str]:
    """(subject, text, html) of the email that proves an address, in both languages.

    The link is the whole content: no name, no greeting, nothing that would
    make a forwarded copy say anything about the person. The two languages
    are both there because the service does not know which one the reader
    uses before they have signed in.
    """
    host = _service_host()
    subject = f"验证邮箱 / Verify your email · {host}" if host else "验证邮箱 / Verify your email"
    text = (
        f"你在 {host} 创建了账号。点击下面的链接验证这个邮箱；链接 {hours} 小时内有效，只能使用一次。\n"
        f"{link}\n\n"
        f"如果不是你创建的，忽略这封邮件即可，不会有任何事情发生。\n\n"
        f"You created an account at {host}. Open the link to verify this address; "
        f"it works once, for {hours} hours.\n"
        f"{link}\n\n"
        f"If this was not you, ignore this message and nothing will happen.\n"
    )
    safe_link, safe_host = html.escape(link, quote=True), html.escape(host)
    body = (
        "<!doctype html><html><body style=\"font-family:system-ui,sans-serif;line-height:1.5;"
        "color:#1f2328;max-width:36em;margin:2em auto;padding:0 1em\">"
        f"<p>你在 {safe_host} 创建了账号。点击下面的按钮验证这个邮箱；链接 {hours} 小时内有效，只能使用一次。</p>"
        f"<p>You created an account at {safe_host}. Open the link to verify this address; "
        f"it works once, for {hours} hours.</p>"
        f"<p><a href=\"{safe_link}\" style=\"display:inline-block;padding:.6em 1.2em;background:#1f6feb;"
        "color:#fff;text-decoration:none;border-radius:6px\">验证邮箱 / Verify email</a></p>"
        f"<p style=\"font-size:.85em;color:#57606a\">或复制这个地址到浏览器 / Or paste this address into your browser:<br>"
        f"<a href=\"{safe_link}\">{safe_link}</a></p>"
        "<p style=\"font-size:.85em;color:#57606a\">如果不是你创建的，忽略这封邮件即可。"
        "If this was not you, ignore this message.</p>"
        "</body></html>"
    )
    return subject, text, body


# ── Delivery ────────────────────────────────────────────────────────────────

# Replaced in tests. Nothing else may choose where a message goes.
_connect: Callable[..., http.client.HTTPConnection] = http.client.HTTPSConnection


def _allow(now: float) -> None:
    """Take one place in the day's allowance or refuse; caller holds _LOCK."""
    cap = per_day()
    if not cap:
        return
    _sent_today[:] = [t for t in _sent_today if t > now - 86400]
    if len(_sent_today) >= cap:
        raise MailError("This deployment has reached today's limit on outgoing email.")
    _sent_today.append(now)


def send(to: str, subject: str, text: str, html_body: str | None = None, *, now: float | None = None) -> None:
    """Deliver one message, or raise MailError. Never logs or names the address or the key."""
    global _last_sent_at, _last_failed_at
    stamp = time.time() if now is None else now
    current = mode()
    if current not in ("resend", "outbox"):
        raise MailError(f"Email is not set up: set exactly one of {_SETTINGS}, with MAIL_FROM and PUBLIC_URL."
                        if current == "misconfigured" else f"Email is not set up: set {_SETTINGS}.")
    message = {"from": sender(), "to": [to], "subject": subject, "text": text}
    if html_body:
        message["html"] = html_body
    with _LOCK:
        try:
            _allow(stamp)
            if current == "outbox":
                _write_to_outbox(message, stamp)
            else:
                _post_to_resend(message)
        except MailError:
            _last_failed_at = stamp
            raise
        _last_sent_at = stamp


def _write_to_outbox(message: dict, stamp: float) -> None:
    directory = _setting("MAIL_OUTBOX")
    try:
        os.makedirs(directory, exist_ok=True)
        name = f"{int(stamp * 1000)}-{len(os.listdir(directory)) + 1:04d}.json"
        with open(os.path.join(directory, name), "w", encoding="utf-8") as handle:
            json.dump(message, handle, ensure_ascii=False, indent=2)
    except OSError as exc:
        raise MailError(f"The outbox directory could not be written ({type(exc).__name__}).") from None


def _post_to_resend(message: dict) -> None:
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    connection = _connect(RESEND_HOST, timeout=_TIMEOUT_SECONDS)
    try:
        connection.request("POST", "/emails", body=body, headers={
            "Authorization": f"Bearer {_setting('MAIL_RESEND_API_KEY')}",
            "Content-Type": "application/json; charset=utf-8",
        })
        reply = connection.getresponse()
        status, raw = reply.status, reply.read(_REPLY_LIMIT)
    except (OSError, http.client.HTTPException) as exc:
        # The type and nothing more: an exception's text is not ours to vouch for.
        raise MailError(f"The email service could not be reached ({type(exc).__name__}).") from None
    finally:
        connection.close()
    if status == 200:
        return
    try:
        name = json.loads(raw.decode("utf-8")).get("name")
    except (ValueError, AttributeError):
        name = None
    # Resend names its refusals (validation_error, missing_api_key, daily_quota_exceeded,
    # rate_limit_exceeded ...). The name is a token from a fixed list; the message beside
    # it is the vendor's text and can quote what was sent, so it is not repeated.
    detail = f" ({name})" if isinstance(name, str) and re.fullmatch(r"[a-z_]{1,40}", name) else ""
    raise MailError(f"The email service answered HTTP {status}{detail}.")


# ── Reporting ──────────────────────────────────────────────────────────────

def _when(stamp: float | None) -> datetime | None:
    return datetime.fromtimestamp(stamp, tz=UTC) if stamp is not None else None


def status() -> dict:
    """For /health: whether a message could be sent, not whether one was needed."""
    current = mode()
    if current == "off":
        state = "off"
    elif current == "misconfigured":
        state = "misconfigured"
    elif _last_failed_at is not None and (_last_sent_at is None or _last_failed_at > _last_sent_at):
        state = "failing"
    else:
        state = "ready"
    return {"state": state, "channel": current if current in ("resend", "outbox") else None,
            "last_sent_at": _when(_last_sent_at), "last_failed_at": _when(_last_failed_at)}


def _test(argv: list[str]) -> int:
    """`python -m api.mail test someone@example.com`: send one message and report."""
    if len(argv) != 2 or argv[0] != "test" or not _ADDRESS.fullmatch(argv[1]):
        print("Usage: python -m api.mail test <address>", file=sys.stderr)
        return 2
    subject, text, body = verification_message(f"{public_url() or 'https://example.invalid'}/verify?token=test-only")
    try:
        send(argv[1], f"[test] {subject}", text, body)
    except MailError as exc:
        print(f"Not sent: {exc}")
        return 1
    print(f"Sent through {mode()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_test(sys.argv[1:]))
