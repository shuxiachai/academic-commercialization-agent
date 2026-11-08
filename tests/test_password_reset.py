"""A forgotten password is reset by a link sent to the account's address.

With mail set up (api/mail.py), the sign-in screen's "forgot" form takes an
address and is answered the same way whether or not an account has it; when
one does, a one-time link reaches that address and nowhere else. Opening the
link sets a new password, ends every session of the account and proves the
address. Without mail the route says so, and the operator's reset remains.
"""
from __future__ import annotations

import json
import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import accounts, mail
from api.main import _is_page_asset, app

PASSWORD = "a sufficiently long password"
NEW_PASSWORD = "another password, long enough"
EMAIL = "alice@example.com"
_ROOT = Path(__file__).resolve().parents[1]
_MAIL_SETTINGS = ("MAIL_RESEND_API_KEY", "MAIL_OUTBOX", "MAIL_FROM", "PUBLIC_URL", "MAIL_PER_DAY")
_RESET_PREFIX = "https://aca.example.com/reset?token="


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

    def _signup(self, email=EMAIL):
        response = self.client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def _login(self, password=PASSWORD, email=EMAIL):
        return self.client.post("/api/auth/login", json={"email": email, "password": password})

    def _forgot(self, email=EMAIL):
        return self.client.post("/api/auth/password/forgot", json={"email": email})

    def _reset(self, token, password=NEW_PASSWORD):
        return self.client.post("/api/auth/password/reset", json={"token": token, "new_password": password})

    @staticmethod
    def _bearer(token):
        return {"Authorization": f"Bearer {token}"}

    def _messages(self) -> list[dict]:
        if not self.outbox.is_dir():
            return []
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(self.outbox.iterdir())]

    @staticmethod
    def _link_token(message: dict, prefix: str = _RESET_PREFIX) -> str:
        start = message["text"].index(prefix) + len(prefix)
        return message["text"][start:].split()[0]

    def _reset_token(self, email=EMAIL) -> str:
        before = len(self._messages())
        self.assertEqual(self._forgot(email).status_code, 202)
        messages = self._messages()
        self.assertEqual(len(messages), before + 1, "one message for the request")
        return self._link_token(messages[-1])


class RequestTests(_Case):
    def test_an_account_is_sent_one_link_and_nothing_about_itself(self):
        self._signup()
        self.assertEqual(len(self._messages()), 1)             # the verification link
        response = self._forgot()
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        messages = self._messages()
        self.assertEqual(len(messages), 2)
        message = messages[-1]
        self.assertEqual((message["from"], message["to"]), ("ACA <noreply@example.com>", [EMAIL]))
        token = self._link_token(message)
        self.assertGreaterEqual(len(token), 32)
        self.assertIn(f"{_RESET_PREFIX}{token}", message["html"])
        self.assertIn("aca.example.com", message["subject"])
        for word in ("重置密码", "Reset your password", "60"):
            self.assertIn(word, message["text"])
        # Nothing about the person beyond the address it is sent to.
        self.assertNotIn(PASSWORD, message["text"] + message["html"])
        self.assertNotIn("alice", message["text"] + message["html"] + message["subject"])

    def test_an_unknown_address_gets_the_same_answer_and_no_message(self):
        self._signup()
        known = self._forgot(EMAIL)
        unknown = self._forgot("nobody@example.com")
        for response in (known, unknown):
            self.assertEqual(response.status_code, 202)
        self.assertEqual(known.content, unknown.content)
        self.assertEqual(dict(known.headers), dict(unknown.headers) | {"content-length": known.headers.get("content-length")})
        self.assertEqual(len(self._messages()), 2, "the verification link and one reset link")

    def test_the_address_is_matched_like_a_sign_in_and_nonsense_is_silent(self):
        self._signup()
        self.assertEqual(self._forgot("  ALICE@Example.com ").status_code, 202)
        self.assertEqual(len(self._messages()), 2)
        self.assertEqual(self._forgot("not an address").status_code, 202)
        self.assertEqual(self._forgot("").status_code, 202)
        self.assertEqual(len(self._messages()), 2)

    def test_a_second_request_within_a_minute_sends_nothing_more(self):
        self._signup()
        self.assertEqual(self._forgot().status_code, 202)
        self.assertEqual(self._forgot().status_code, 202)
        self.assertEqual(len(self._messages()), 2)
        # In module terms: a token is issued again only after the cooldown,
        # and the newer one retires the older.
        later = int(time.time()) + 3_600          # past the token the request above made
        first = accounts.issue_password_reset(EMAIL, now=later)
        self.assertIsNotNone(first)
        self.assertIsNone(accounts.issue_password_reset(EMAIL, now=later + accounts.RESET_REQUEST_SECONDS - 1))
        second = accounts.issue_password_reset(EMAIL, now=later + accounts.RESET_REQUEST_SECONDS)
        self.assertIsNotNone(second)
        with self.assertRaises(accounts.AccountError) as refused:
            accounts.redeem_reset_link(first[1], NEW_PASSWORD, now=later + 100)
        self.assertEqual(refused.exception.code, "reset_invalid")
        self.assertEqual(accounts.redeem_reset_link(second[1], NEW_PASSWORD, now=later + 100).email, EMAIL)

    def test_a_disabled_account_is_sent_nothing(self):
        self._signup()
        self.assertTrue(accounts.set_disabled(EMAIL, True))
        self.assertEqual(self._forgot().status_code, 202)
        self.assertEqual(len(self._messages()), 1)
        self.assertIsNone(accounts.issue_password_reset(EMAIL))

    def test_a_delivery_failure_is_logged_by_id_and_still_answered_202(self):
        session = self._signup()
        user_id = accounts.session_user(session["token"]).id
        with patch.object(mail, "send", side_effect=mail.MailError("HTTP 500 (internal)")), \
                self.assertLogs("api.main", level="WARNING") as logged:
            self.assertEqual(self._forgot().status_code, 202)
        self.assertEqual(len(logged.output), 1)
        self.assertIn(f"account {user_id} ", logged.output[0])
        self.assertNotIn("alice", logged.output[0])
        self.assertEqual(len(self._messages()), 1)

    def test_the_sign_in_configuration_offers_it_only_with_mail(self):
        self.assertTrue(self.client.get("/api/auth/config").json()["password_reset"])
        # The boot's refusal carries the same configuration, so the gate knows
        # whether to offer the button without a second request.
        refused = self.client.get("/api/access/check")
        self.assertEqual(refused.status_code, 401)
        self.assertTrue(refused.json()["accounts"]["password_reset"])


class WithoutMailTests(_Case):
    mail_env = {}

    def test_the_route_says_so_and_the_screen_does_not_offer_it(self):
        self._signup()
        response = self._forgot()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers.get("X-Error-Code"), "mail_unavailable")
        self.assertNotIn("alice", response.text)
        self.assertFalse(self.client.get("/api/auth/config").json()["password_reset"])
        # A token made by hand still works: the setting gates the sending, not the link.
        user, token = accounts.issue_password_reset(EMAIL)
        self.assertEqual(self._reset(token).status_code, 200)
        self.assertEqual(self._login(NEW_PASSWORD).status_code, 200)


class ResetTests(_Case):
    def test_the_link_sets_the_password_ends_every_session_and_proves_the_address(self):
        first = self._signup()
        second = self._login().json()
        self.assertFalse(first["verified"])
        token = self._reset_token()
        response = self._reset(token)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"email": EMAIL})
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        for session in (first, second):
            self.assertEqual(self.client.get("/api/auth/me", headers=self._bearer(session["token"])).status_code, 401)
        self.assertEqual(self._login(PASSWORD).status_code, 401)
        signed_in = self._login(NEW_PASSWORD)
        self.assertEqual(signed_in.status_code, 200, signed_in.text)
        self.assertTrue(signed_in.json()["verified"], "the link reached the address")
        # Spent: the same link does nothing twice.
        again = self._reset(token, "yet another long password")
        self.assertEqual(again.status_code, 400)
        self.assertEqual(again.headers.get("X-Error-Code"), "reset_invalid")
        self.assertEqual(self._login(NEW_PASSWORD).status_code, 200)

    def test_an_expired_link_says_so_once_and_is_then_unknown(self):
        self._signup()
        _, token = accounts.issue_password_reset(EMAIL, now=1_000)
        with self.assertRaises(accounts.AccountError) as expired:
            accounts.redeem_reset_link(token, NEW_PASSWORD, now=1_000 + accounts.RESET_SECONDS)
        self.assertEqual(expired.exception.code, "reset_expired")
        with self.assertRaises(accounts.AccountError) as unknown:
            accounts.redeem_reset_link(token, NEW_PASSWORD, now=1_000 + accounts.RESET_SECONDS)
        self.assertEqual(unknown.exception.code, "reset_invalid")
        # One second earlier it would have worked.
        _, token = accounts.issue_password_reset(EMAIL, now=5_000)
        self.assertEqual(accounts.redeem_reset_link(token, NEW_PASSWORD, now=5_000 + accounts.RESET_SECONDS - 1).email, EMAIL)

    def test_the_statuses_tell_expired_from_unknown(self):
        self._signup()
        _, token = accounts.issue_password_reset(EMAIL, now=1_000)
        with patch.object(accounts.time, "time", return_value=1_000 + accounts.RESET_SECONDS + 1):
            response = self._reset(token)
        self.assertEqual((response.status_code, response.headers.get("X-Error-Code")), (410, "reset_expired"))
        response = self._reset("not-a-token-this-deployment-made")
        self.assertEqual((response.status_code, response.headers.get("X-Error-Code")), (400, "reset_invalid"))
        self.assertEqual(self._reset("").status_code, 422)
        self.assertEqual(self._reset("x" * 129).status_code, 422)

    def test_a_refused_password_does_not_spend_the_link(self):
        self._signup()
        token = self._reset_token()
        for bad in ("short", EMAIL):
            response = self._reset(token, bad)
            self.assertEqual(response.status_code, 422, bad)
            self.assertEqual(response.headers.get("X-Error-Code"), "weak_password")
        self.assertEqual(self._login(PASSWORD).status_code, 200, "nothing changed yet")
        self.assertEqual(self._reset(token).status_code, 200)
        self.assertEqual(self._login(NEW_PASSWORD).status_code, 200)

    def test_a_locked_out_address_may_sign_in_with_the_new_password(self):
        self._signup()
        for _ in range(accounts.LOCKOUT_FAILURES):
            self.assertEqual(self._login("wrong password, long enough").status_code, 401)
        self.assertEqual(self._login(PASSWORD).status_code, 429, "locked out")
        self.assertEqual(self._reset(self._reset_token()).status_code, 200)
        self.assertEqual(self._login(NEW_PASSWORD).status_code, 200)

    def test_a_disabled_account_is_refused_and_keeps_the_link(self):
        self._signup()
        token = self._reset_token()
        self.assertTrue(accounts.set_disabled(EMAIL, True))
        response = self._reset(token)
        self.assertEqual((response.status_code, response.headers.get("X-Error-Code")), (403, "disabled"))
        self.assertTrue(accounts.set_disabled(EMAIL, False))
        self.assertEqual(self._reset(token).status_code, 200)
        self.assertEqual(self._login(NEW_PASSWORD).status_code, 200)

    def test_a_verification_link_is_not_a_reset_link_and_the_reverse(self):
        self._signup()
        verify_token = self._link_token(self._messages()[0], "https://aca.example.com/verify?token=")
        reset_token = self._reset_token()
        self.assertEqual(self._reset(verify_token).headers.get("X-Error-Code"), "reset_invalid")
        verify = self.client.post("/api/auth/verify", json={"token": reset_token})
        self.assertEqual(verify.headers.get("X-Error-Code"), "verification_invalid")
        # Both still work for what they are for; the reset spends the verification link too.
        self.assertEqual(self._reset(reset_token).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/verify", json={"token": verify_token}).status_code, 400)

    def test_the_page_and_both_routes_are_open_to_a_visitor_without_a_session(self):
        page = self.client.get("/reset?token=abc")
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="reset-form"', page.text)
        self.assertTrue(_is_page_asset("/reset"))
        self.assertEqual(self._forgot("nobody@example.com").status_code, 202)
        self.assertEqual(self._reset("abc").status_code, 400)
        self.assertEqual(self.client.get("/api/runs").status_code, 401, "the rest is still gated")


class MessageTests(_Case):
    def test_the_message_is_the_card_in_both_languages_with_the_link_twice(self):
        subject, text, body = mail.reset_message(f"{_RESET_PREFIX}t-1", minutes=60)
        self.assertEqual(subject, "重置密码 / Reset your password · aca.example.com")
        self.assertEqual(text.count(f"{_RESET_PREFIX}t-1"), 2, "once under each language")
        for part in (text, body):
            for words in ("重置密码", "Reset your password", "60", "密码不会改变", "stays as it is", "aca.example.com"):
                self.assertIn(words, part)
        self.assertEqual(body.count(f'href="{_RESET_PREFIX}t-1"'), 2)
        self.assertIn(f">{_RESET_PREFIX}t-1</a>", body)
        self.assertIn("Set a new password", body)
        self.assertIn('<meta name="color-scheme" content="light">', body)
        self.assertIn("#0f6b66", body)
        self.assertIn('src="https://aca.example.com/static/brand/aca-mark.png"', body)
        self.assertIn("Academic Commercialization Assessment", text)

    def test_the_verification_message_is_unchanged_by_sharing_the_card(self):
        subject, text, body = mail.verification_message("https://aca.example.com/verify?token=t-1")
        self.assertEqual(subject, "验证邮箱 / Verify your email · aca.example.com")
        self.assertIn('>验证你的邮箱<br><span', body)
        self.assertIn("You created an account at <strong style=\"color:#1d1b18;font-weight:600;\">aca.example.com</strong>. "
                      "Open the link to verify this address and start assessments; it works once, for 24 hours.", body)
        self.assertIn("验证邮箱 · Verify email</a>", body)
        self.assertEqual(body.count('href="https://aca.example.com/verify?token=t-1"'), 2)

    def test_the_host_is_escaped_and_the_mark_needs_a_public_url(self):
        with patch.dict("os.environ", {"PUBLIC_URL": "https://a<b.example"}):
            mail.reset()
            body = mail.reset_message("https://a<b.example/reset?token=t")[2]
        mail.reset()
        self.assertIn("a&lt;b.example", body)
        self.assertNotIn("a<b.example<", body)
        with patch.dict("os.environ", {"PUBLIC_URL": ""}):
            mail.reset()
            self.assertNotIn("<img", mail.reset_message("https://x.example/reset?token=t")[2])
        mail.reset()


class PageTests(unittest.TestCase):
    def test_the_page_has_the_forms_and_the_words_in_both_languages(self):
        index = (_ROOT / "web" / "index.html").read_text(encoding="utf-8")
        for marker in ('id="account-forgot"', 'id="forgot-form"', 'id="forgot-email"', 'id="forgot-sent"',
                       'id="reset-form"', 'id="reset-password"', 'autocomplete="new-password"'):
            self.assertIn(marker, index)
        app_js = (_ROOT / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('location.pathname === "/reset"', app_js)
        self.assertIn("!authConfig?.password_reset", app_js)
        self.assertIn("api.setSessionToken(null)", app_js)
        api_js = (_ROOT / "web" / "static" / "js" / "api.js").read_text(encoding="utf-8")
        self.assertIn('"/api/auth/password/forgot"', api_js)
        self.assertIn('"/api/auth/password/reset"', api_js)
        strings = (_ROOT / "web" / "static" / "js" / "i18n.js").read_text(encoding="utf-8")
        for key in ("account_forgot", "forgot_title", "forgot_sub", "forgot_submit", "forgot_sent", "forgot_back",
                    "forgot_unavailable", "reset_title", "reset_sub", "reset_submit", "reset_done", "reset_invalid",
                    "reset_expired", "reset_disabled"):
            self.assertEqual(strings.count(f"    {key}: "), 2, key)

    def test_the_guide_the_readmes_and_the_privacy_page_say_so(self):
        guide = (_ROOT / "docs" / "operating-guide.md").read_text(encoding="utf-8")
        self.assertIn("### Password reset by email", guide)
        self.assertIn("/reset?token=", guide)
        self.assertNotIn("There is no self-service password reset", guide)
        readme = (_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("forgotten password is reset by a link", readme.replace("\n", " "))
        self.assertNotIn("no self-service password reset yet", readme)
        zh = (_ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        self.assertIn("自助重置", zh)
        self.assertNotIn("目前还没有自助找回密码", zh)
        privacy = (_ROOT / "web" / "privacy.html").read_text(encoding="utf-8")
        self.assertIn("Forgot your password?", privacy)
        self.assertNotIn("There is no password reset yet", privacy)


if __name__ == "__main__":
    unittest.main()
