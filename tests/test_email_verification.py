"""An account proves its address before it may start paid work.

With mail set up (api/mail.py), a new account is sent a one-time link and is
refused its runs with `email_unverified` until the link has been opened; it
may still sign in, save keys and preview. With no mail, accounts are created
verified, as they were before there was mail, and accounts from before the
column existed are marked verified when the database is first opened.
"""
from __future__ import annotations

import json
import os
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import account_admin, accounts, admin, mail
from api.main import app

PASSWORD = "a sufficiently long password"
BYOK = {"llm_provider": "deepseek", "llm_api_key": "k", "llm_model": "deepseek-chat", "tavily_api_key": "t"}
_ROOT = Path(__file__).resolve().parents[1]
_MAIL_SETTINGS = ("MAIL_RESEND_API_KEY", "MAIL_OUTBOX", "MAIL_FROM", "PUBLIC_URL", "MAIL_PER_DAY")


class _Resend:
    """Stands where api.resend.com would, and remembers what it was sent."""

    def __init__(self, status: int = 200, body: bytes = b'{"id":"mail-1"}', fault: BaseException | None = None):
        self.status, self.body, self.fault = status, body, fault
        self.connections: list[tuple[str, object]] = []
        self.requests: list[tuple[str, str, dict, dict]] = []
        self.closed = 0

    def __call__(self, host, timeout=None):
        self.connections.append((host, timeout))
        return self

    def request(self, method, url, body=None, headers=None):
        if self.fault is not None:
            raise self.fault
        self.requests.append((method, url, json.loads(body.decode("utf-8")), dict(headers or {})))

    def getresponse(self):
        return self

    def read(self, _limit=None):
        return self.body

    def close(self):
        self.closed += 1


class _Case(unittest.TestCase):
    """Accounts on, mail to an outbox directory, unless a test says otherwise."""

    mail_env: dict = {"MAIL_OUTBOX": "<outbox>", "MAIL_FROM": "ACA <noreply@example.com>",
                      "PUBLIC_URL": "https://aca.example.com"}

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.outbox = Path(self._tmp.name) / "outbox"
        env = {"ACCOUNTS_DB": str(Path(self._tmp.name) / "accounts.sqlite3")}
        env.update({k: (str(self.outbox) if v == "<outbox>" else v) for k, v in self.mail_env.items()})
        self._env = patch.dict("os.environ", env)
        self._env.start()
        for name in ("ACCOUNTS_SIGNUP", "ACCOUNTS_ADMIN_EMAILS", "OPERATOR_CONTACT", *_MAIL_SETTINGS):
            if name not in env:
                os.environ.pop(name, None)
        mail.reset()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self._env.stop()
        self._tmp.cleanup()
        mail.reset()

    def _signup(self, email="alice@example.com"):
        response = self.client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    @staticmethod
    def _bearer(token):
        return {"Authorization": f"Bearer {token}"}

    def _messages(self) -> list[dict]:
        if not self.outbox.is_dir():
            return []
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(self.outbox.iterdir())]

    def _link_token(self, message: dict) -> str:
        prefix = "https://aca.example.com/verify?token="
        start = message["text"].index(prefix) + len(prefix)
        return message["text"][start:].split()[0]


class SignUpTests(_Case):
    def test_a_new_account_is_unverified_and_is_sent_one_link(self):
        session = self._signup()
        self.assertFalse(session["verified"])
        self.assertEqual(self.client.get("/api/auth/me", headers=self._bearer(session["token"])).json(),
                         {"email": "alice@example.com", "admin": False, "verified": False})
        self.assertFalse(self.client.get("/api/access/check", headers=self._bearer(session["token"])).json()["account"]["verified"])
        messages = self._messages()
        self.assertEqual(len(messages), 1)
        (message,) = messages
        self.assertEqual((message["from"], message["to"]), ("ACA <noreply@example.com>", ["alice@example.com"]))
        token = self._link_token(message)
        self.assertGreaterEqual(len(token), 32)
        # The same link in the text and the html, and the deployment named, in both languages.
        self.assertIn(f"https://aca.example.com/verify?token={token}", message["html"])
        self.assertIn("aca.example.com", message["subject"])
        for word in ("验证", "Open the link", "24"):
            self.assertIn(word, message["text"])
        # Nothing about the person beyond the address it is sent to.
        self.assertNotIn(PASSWORD, message["text"])
        self.assertNotIn("alice", message["text"] + message["html"] + message["subject"])

    def test_the_message_wears_the_sites_colours_and_mark(self):
        subject, text, body = mail.verification_message("https://aca.example.com/verify?token=t-1")
        # The mark is a PNG on the public URL: mail clients do not all show SVG.
        self.assertIn('src="https://aca.example.com/static/brand/aca-mark.png"', body)
        self.assertTrue((_ROOT / "web" / "static" / "brand" / "aca-mark.png").is_file())
        # The page's light palette, and a request to stay light in a dark inbox.
        for colour in ("#f5f3ee", "#fdfcf9", "#0f6b66", "#1d1b18"):
            self.assertIn(colour, body)
        self.assertIn('<meta name="color-scheme" content="light">', body)
        # Both languages, the wordmark, and the link exactly twice (button and fallback).
        for word in ("Academic Commercialization Assessment", "验证你的邮箱", "Verify your email", "请勿回复", "do not reply"):
            self.assertIn(word, body)
            self.assertIn(word, text)
        self.assertEqual(body.count('href="https://aca.example.com/verify?token=t-1"'), 2)
        # The fallback shows the address itself, for the reader who has to copy it.
        self.assertIn(">https://aca.example.com/verify?token=t-1</a>", body)
        # No mark and no broken image when the deployment has no public URL.
        with patch.dict("os.environ", {"PUBLIC_URL": ""}):
            self.assertNotIn("<img", mail.verification_message("https://x.example/verify?token=t")[2])

    def test_paid_work_is_refused_until_the_link_is_opened_and_previews_are_not(self):
        session = self._signup()
        headers = self._bearer(session["token"])
        # With or without keys: the address comes first, so the page can say one thing.
        for body in ({"topic": "a valid research topic"}, {"topic": "a valid research topic", **BYOK}):
            response = self.client.post("/api/runs", json=body, headers=headers)
            self.assertEqual((response.status_code, response.headers["X-Error-Code"]), (403, "email_unverified"), body)
        # Signed in all the same: history and the account's own settings work.
        self.assertEqual(self.client.get("/api/runs", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/quota", headers=headers).status_code, 200)

    def test_opening_the_link_verifies_once(self):
        session = self._signup()
        headers = self._bearer(session["token"])
        token = self._link_token(self._messages()[0])
        # The link itself is a page, and fetching it proves nothing: a mail
        # client's preview must not be what verifies an address.
        page = self.client.get(f"/verify?token={token}")
        self.assertEqual((page.status_code, page.headers["content-type"].split(";")[0]), (200, "text/html"))
        self.assertFalse(self.client.get("/api/auth/me", headers=headers).json()["verified"])
        # The page posts the token; no session is needed for that.
        verified = self.client.post("/api/auth/verify", json={"token": token})
        self.assertEqual((verified.status_code, verified.json()), (200, {"email": "alice@example.com", "verified": True}))
        self.assertTrue(self.client.get("/api/auth/me", headers=headers).json()["verified"])
        # Spent: a second visit says invalid, not verified again.
        again = self.client.post("/api/auth/verify", json={"token": token})
        self.assertEqual((again.status_code, again.headers["X-Error-Code"]), (400, "verification_invalid"))
        # And the account is past the check: without keys the next refusal is the keys.
        response = self.client.post("/api/runs", json={"topic": "a valid research topic"}, headers=headers)
        self.assertEqual((response.status_code, response.headers["X-Error-Code"]), (401, "byok_required"))

    def test_an_unknown_or_expired_link_says_which(self):
        self._signup()
        for bad in ("", "x" * 129, "not-a-token"):
            with self.subTest(token=bad):
                with self.assertRaises(accounts.AccountError) as refused:
                    accounts.verify_email(bad)
                self.assertEqual(refused.exception.code, "verification_invalid")
        token = self._link_token(self._messages()[0])
        with self.assertRaises(accounts.AccountError) as refused:
            accounts.verify_email(token, now=accounts.VERIFY_SECONDS + 10 ** 10)
        self.assertEqual(refused.exception.code, "verification_expired")
        # Expired is gone: the same link is now unknown.
        with self.assertRaises(accounts.AccountError) as refused:
            accounts.verify_email(token)
        self.assertEqual(refused.exception.code, "verification_invalid")
        response = self.client.post("/api/auth/verify", json={"token": "nope"})
        self.assertEqual((response.status_code, response.headers["X-Error-Code"]), (400, "verification_invalid"))

    def test_a_sign_up_still_succeeds_when_the_message_cannot_leave(self):
        with patch.object(mail, "_write_to_outbox", side_effect=mail.MailError("down")), \
                self.assertLogs("api.main", level="WARNING") as logged:
            session = self._signup()
        self.assertFalse(session["verified"])
        self.assertEqual(self._messages(), [])
        # The log says a message was not sent and for which account id, never the address.
        self.assertEqual(len(logged.output), 1)
        self.assertNotIn("alice", logged.output[0])
        self.assertIn("not sent", logged.output[0])


class ResendTests(_Case):
    def test_send_again_replaces_the_link_and_is_paced(self):
        session = self._signup()
        headers = self._bearer(session["token"])
        first = self._link_token(self._messages()[0])
        with patch.object(accounts, "VERIFY_RESEND_SECONDS", 0):
            response = self.client.post("/api/auth/verify/resend", headers=headers)
        self.assertEqual(response.status_code, 202)
        second = self._link_token(self._messages()[1])
        self.assertNotEqual(first, second)
        refused = self.client.post("/api/auth/verify", json={"token": first})
        self.assertEqual((refused.status_code, refused.headers["X-Error-Code"]), (400, "verification_invalid"))
        # Straight after a message, another is refused with when to retry, and nothing is sent.
        paced = self.client.post("/api/auth/verify/resend", headers=headers)
        self.assertEqual((paced.status_code, paced.headers["X-Error-Code"], paced.headers["Retry-After"]),
                         (429, "verification_cooldown", str(accounts.VERIFY_RESEND_SECONDS)))
        self.assertEqual(len(self._messages()), 2)
        # The newest link still works.
        self.assertEqual(self.client.post("/api/auth/verify", json={"token": second}).status_code, 200)
        done = self.client.post("/api/auth/verify/resend", headers=headers)
        self.assertEqual((done.status_code, done.headers["X-Error-Code"]), (409, "already_verified"))

    def test_the_cooldown_is_measured_from_the_last_message(self):
        user = accounts.register("bob@example.com", PASSWORD, now=1_000)
        accounts.issue_verification(user, now=1_000, cooldown=False)
        with self.assertRaises(accounts.AccountError) as refused:
            accounts.issue_verification(user, now=1_000 + accounts.VERIFY_RESEND_SECONDS - 1)
        self.assertEqual(refused.exception.code, "verification_cooldown")
        self.assertTrue(accounts.issue_verification(user, now=1_000 + accounts.VERIFY_RESEND_SECONDS))

    def test_send_again_needs_a_session_and_working_mail(self):
        session = self._signup()
        self.assertEqual(self.client.post("/api/auth/verify/resend").status_code, 401)
        with patch.object(accounts, "VERIFY_RESEND_SECONDS", 0), \
                patch.object(mail, "_write_to_outbox", side_effect=mail.MailError("down")), \
                self.assertLogs("api.main", level="WARNING"):
            response = self.client.post("/api/auth/verify/resend", headers=self._bearer(session["token"]))
        self.assertEqual((response.status_code, response.headers["X-Error-Code"]), (503, "mail_unavailable"))
        with patch.dict("os.environ", {"MAIL_OUTBOX": ""}):
            response = self.client.post("/api/auth/verify/resend", headers=self._bearer(session["token"]))
        self.assertEqual((response.status_code, response.headers["X-Error-Code"]), (503, "mail_unavailable"))


class WithoutMailTests(_Case):
    mail_env = {}

    def test_accounts_are_created_verified_and_health_says_mail_is_off(self):
        session = self._signup()
        self.assertTrue(session["verified"])
        self.assertEqual(self.client.get("/health").json()["mail"],
                         {"state": "off", "channel": None, "last_sent_at": None, "last_failed_at": None})
        response = self.client.post("/api/runs", json={"topic": "a valid research topic"},
                                    headers=self._bearer(session["token"]))
        self.assertEqual(response.headers["X-Error-Code"], "byok_required")

    def test_an_unusable_setting_is_misconfigured_and_behaves_as_off(self):
        cases = {
            "both": {"MAIL_RESEND_API_KEY": "re_x", "MAIL_OUTBOX": self._tmp.name, "MAIL_FROM": "a@b.co", "PUBLIC_URL": "https://a.b"},
            "no sender": {"MAIL_RESEND_API_KEY": "re_x", "PUBLIC_URL": "https://a.b"},
            "bad sender": {"MAIL_RESEND_API_KEY": "re_x", "MAIL_FROM": "ACA", "PUBLIC_URL": "https://a.b"},
            "no url": {"MAIL_RESEND_API_KEY": "re_x", "MAIL_FROM": "a@b.co"},
            "url with path": {"MAIL_RESEND_API_KEY": "re_x", "MAIL_FROM": "a@b.co", "PUBLIC_URL": "https://a.b/app/"},
        }
        for name, env in cases.items():
            with self.subTest(name), patch.dict("os.environ", env):
                self.assertEqual(mail.mode(), "misconfigured")
                self.assertFalse(accounts.verification_required())
                self.assertEqual(self.client.get("/health").json()["mail"]["state"], "misconfigured")
        with patch.dict("os.environ", {"MAIL_RESEND_API_KEY": "re_x", "MAIL_FROM": "ACA <a@b.co>", "PUBLIC_URL": "https://a.b/"}):
            self.assertEqual((mail.mode(), mail.public_url(), mail.sender()), ("resend", "https://a.b", "ACA <a@b.co>"))
            self.assertTrue(accounts.verification_required())
            self.assertEqual(self.client.get("/health").json()["mail"]["state"], "ready")

    def test_accounts_from_before_the_column_are_marked_verified_once(self):
        path = Path(os.environ["ACCOUNTS_DB"])
        old = sqlite3.connect(str(path))
        with old:
            old.executescript("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE, "
                              "password_hash TEXT NOT NULL, created_at INTEGER NOT NULL, disabled INTEGER NOT NULL DEFAULT 0);")
            old.execute("INSERT INTO users (email, password_hash, created_at) VALUES ('old@example.com', 'x', 1)")
        old.close()
        self.assertTrue(accounts.user_by_id(1).verified)
        with patch.dict("os.environ", {"MAIL_OUTBOX": str(self.outbox), "MAIL_FROM": "a@b.co", "PUBLIC_URL": "https://a.b"}):
            new = accounts.register("new@example.com", PASSWORD)
            self.assertFalse(new.verified)
            # Opening the database again does not sweep the new account up.
            self.assertFalse(accounts.user_by_id(new.id).verified)
            self.assertTrue(accounts.user_by_id(1).verified)


class DeliveryTests(_Case):
    mail_env = {"MAIL_RESEND_API_KEY": "re_secret_key", "MAIL_FROM": "ACA <noreply@example.com>",
                "PUBLIC_URL": "https://aca.example.com"}

    def test_a_message_goes_to_resend_with_the_key_in_one_header(self):
        resend = _Resend()
        with patch.object(mail, "_connect", resend):
            mail.send("to@example.com", "Subject", "Body", "<p>Body</p>")
        self.assertEqual(resend.connections, [(mail.RESEND_HOST, mail._TIMEOUT_SECONDS)])
        ((method, path, body, headers),) = resend.requests
        self.assertEqual((method, path), ("POST", "/emails"))
        self.assertEqual(body, {"from": "ACA <noreply@example.com>", "to": ["to@example.com"], "subject": "Subject",
                                "text": "Body", "html": "<p>Body</p>"})
        self.assertEqual(headers["Authorization"], "Bearer re_secret_key")
        self.assertEqual(resend.closed, 1)
        self.assertEqual(mail.status()["state"], "ready")

    def test_a_refusal_names_resends_code_and_never_the_key_or_the_address(self):
        cases = [
            (_Resend(status=422, body=b'{"statusCode":422,"name":"validation_error","message":"to@example.com is bad"}'),
             "HTTP 422 (validation_error)"),
            (_Resend(status=429, body=b'{"name":"rate_limit_exceeded"}'), "HTTP 429 (rate_limit_exceeded)"),
            (_Resend(status=500, body=b"not json"), "HTTP 500."),
            (_Resend(status=401, body=b'{"name":"<script>"}'), "HTTP 401."),
            (_Resend(fault=OSError("connect to re_secret_key failed")), "(OSError)"),
        ]
        for resend, expected in cases:
            with self.subTest(expected=expected), patch.object(mail, "_connect", resend), \
                    self.assertRaises(mail.MailError) as refused:
                mail.send("to@example.com", "S", "B")
            text = str(refused.exception)
            self.assertIn(expected, text)
            self.assertNotIn("re_secret_key", text)
            self.assertNotIn("to@example.com", text)
            self.assertEqual(resend.closed, 1)
        self.assertEqual(mail.status()["state"], "failing")

    def test_the_day_has_an_allowance(self):
        resend = _Resend()
        with patch.dict("os.environ", {"MAIL_PER_DAY": "2"}), patch.object(mail, "_connect", resend):
            mail.send("a@example.com", "S", "B", now=1_000)
            mail.send("b@example.com", "S", "B", now=1_001)
            with self.assertRaises(mail.MailError) as refused:
                mail.send("c@example.com", "S", "B", now=1_002)
            self.assertIn("limit", str(refused.exception))
            self.assertEqual(len(resend.requests), 2)
            mail.send("c@example.com", "S", "B", now=1_000 + 86401)
        with patch.dict("os.environ", {"MAIL_PER_DAY": "0"}), patch.object(mail, "_connect", resend):
            for n in range(5):
                mail.send(f"{n}@example.com", "S", "B", now=2_000)
        self.assertEqual(len(resend.requests), 8)

    def test_health_reports_the_channel_and_the_last_outcome(self):
        with patch.object(mail, "_connect", _Resend()):
            mail.send("a@example.com", "S", "B")
        reported = self.client.get("/health").json()["mail"]
        self.assertEqual((reported["state"], reported["channel"], reported["last_failed_at"]), ("ready", "resend", None))
        self.assertIsNotNone(reported["last_sent_at"])


class OperatorTests(_Case):
    def test_the_console_and_the_shell_see_and_set_the_mark(self):
        self._signup("alice@example.com")
        (row,) = admin.list_accounts()
        self.assertFalse(row.verified)
        with patch("sys.stdout"), patch("sys.stderr"):
            self.assertEqual(account_admin.main(["verify", "Alice@Example.com"]), 0)
            self.assertEqual(account_admin.main(["verify", "alice@example.com"]), 0)   # already: still fine
            self.assertEqual(account_admin.main(["verify", "nobody@example.com"]), 2)
        (row,) = admin.list_accounts()
        self.assertTrue(row.verified)
        # The spent link is gone with the mark.
        token = self._link_token(self._messages()[0])
        with self.assertRaises(accounts.AccountError):
            accounts.verify_email(token)

    def test_the_page_has_the_notice_and_the_words_in_both_languages(self):
        index = (_ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="verify-notice"', index)
        self.assertIn('id="verify-resend"', index)
        app_js = (_ROOT / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('err.code === "email_unverified"', app_js)
        self.assertIn('location.pathname === "/verify"', app_js)
        self.assertIn("accountMode && !accountVerified", app_js)
        strings = (_ROOT / "web" / "static" / "js" / "i18n.js").read_text(encoding="utf-8")
        for key in ("msg_email_unverified", "verify_notice", "verify_resend", "verify_sent", "verify_cooldown",
                    "verify_failed", "verify_done", "verify_done_sign_in", "verify_invalid", "verify_expired"):
            self.assertEqual(strings.count(f"    {key}: "), 2, key)
        admin_js = (_ROOT / "web" / "static" / "js" / "admin.js").read_text(encoding="utf-8")
        self.assertEqual(admin_js.count("unverified: "), 2)


if __name__ == "__main__":
    unittest.main()
