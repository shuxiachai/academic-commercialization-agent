"""Where an invite code comes from, and fields a phone does not zoom on.

Two small things a first-time visitor meets before anything else. In invite
mode the sign-up form showed an "Invite code" field and no word on who gives
codes out. And on a phone, tapping a field whose text is under 16px makes
iOS Safari zoom the page and leave it zoomed.
"""
from __future__ import annotations

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app

_WEB = Path(__file__).resolve().parents[1] / "web"


class ContactDeliveryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._env = patch.dict("os.environ", {"ACCOUNTS_DB": str(Path(self._tmp.name) / "accounts.sqlite3"),
                                               "ACCOUNTS_SIGNUP": "invite", "ACCOUNTS_INVITE_CODE": "a-long-invite-code",
                                               "OPERATOR_CONTACT": "  ops@example.org  "})
        self._env.start()
        os.environ.pop("ACCOUNTS_ADMIN_EMAILS", None)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self._env.stop()
        self._tmp.cleanup()

    def test_the_contact_arrives_with_what_the_gate_already_receives(self):
        # No request of its own: the boot's one request, or its refusal, carries it.
        refusal = self.client.get("/api/access/check")
        self.assertEqual(refusal.status_code, 401)
        self.assertEqual(refusal.json()["accounts"]["contact"], "ops@example.org")
        self.assertEqual(self.client.get("/api/auth/config").json()["contact"], "ops@example.org")
        account = self.client.post("/api/auth/register", json={
            "email": "alice@example.com", "password": "an ordinary long password", "invite": "a-long-invite-code"})
        self.assertEqual(account.status_code, 201, account.text)
        signed_in = self.client.get("/api/access/check", headers={"Authorization": f"Bearer {account.json()['token']}"})
        self.assertEqual(signed_in.json()["accounts"]["contact"], "ops@example.org")
        # The same value the privacy page states, read in one place.
        self.assertEqual(self.client.get("/api/site").json()["contact"], "ops@example.org")

    def test_no_contact_is_none_and_a_long_one_is_cut(self):
        for value, expected in (("", None), ("   ", None), ("x" * 500, "x" * 300)):
            with self.subTest(value=value[:5]), patch.dict("os.environ", {"OPERATOR_CONTACT": value}):
                self.assertEqual(self.client.get("/api/auth/config").json()["contact"], expected)
                self.assertEqual(self.client.get("/api/access/check").json()["accounts"]["contact"], expected)

    def test_without_accounts_the_sign_in_configuration_names_nobody(self):
        os.environ.pop("ACCOUNTS_DB")
        self.assertIsNone(self.client.get("/api/auth/config").json()["contact"])


class PageTests(unittest.TestCase):
    def test_the_hint_sits_under_the_invite_field_and_starts_hidden(self):
        markup = (_WEB / "index.html").read_text(encoding="utf-8")
        field = markup.index('id="account-invite"')
        hint = markup.index('<p class="gate__hint" id="account-invite-hint" hidden></p>')
        self.assertLess(field, hint)
        self.assertLess(hint, markup.index('id="account-error"'))

    def test_both_languages_have_both_sentences(self):
        strings = (_WEB / "static/js/i18n.js").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r'^    account_invite_hint: "[^"]*\{contact\}[^"]*",$', strings, re.M)), 2)
        self.assertEqual(len(re.findall(r'^    account_invite_hint_ask: "[^"{]+",$', strings, re.M)), 2)

    def test_the_contact_is_placed_as_text(self):
        source = (_WEB / "static/js/app.js").read_text(encoding="utf-8")
        body = re.search(r"function paintInviteHint\(shown\) \{(.+?)\n\}", source, re.S)[1]
        self.assertIn("who.textContent = contact;", body)
        # The only thing ever assigned as markup is nothing: clearing the line.
        self.assertEqual(re.findall(r'innerHTML *= *([^;]*);', body), ['""'])
        self.assertNotIn("fetch(", body)


class TouchFieldTests(unittest.TestCase):
    """Static: the rule exists and covers every field. The browser check is in the PR."""

    def test_a_field_on_a_touch_device_is_at_least_sixteen_pixels(self):
        tokens = (_WEB / "static/css/tokens.css").read_text(encoding="utf-8")
        size = float(re.search(r"--text-touch:\s*([0-9.]+)px;", tokens)[1])
        self.assertGreaterEqual(size, 16)
        base = (_WEB / "static/css/base.css").read_text(encoding="utf-8")
        rule = re.search(r"@media \(pointer: coarse\) \{(.+?)\n\}", base, re.S)[1]
        self.assertIn("font-size: var(--text-touch);", rule)
        for field in ("input", "textarea", "select"):
            self.assertRegex(rule, rf":root:root {field}\b")
        # Controls with no text to zoom on are left alone.
        for kind in ("checkbox", "radio", "file"):
            self.assertIn(f'[type="{kind}"]', rule)

    def test_every_page_that_has_a_field_loads_that_rule(self):
        for page in ("index.html", "privacy.html", "samples.html"):
            with self.subTest(page=page):
                self.assertIn('href="/static/css/base.css"', (_WEB / page).read_text(encoding="utf-8"))

    def test_the_gates_text_buttons_are_thumb_sized_on_touch(self):
        sheet = (_WEB / "static/css/workbench.css").read_text(encoding="utf-8")
        rule = re.search(r"@media \(pointer: coarse\) \{\s*\.gate__switch \{([^}]+)\}", sheet)[1]
        self.assertGreaterEqual(int(re.search(r"min-height:\s*(\d+)px", rule)[1]), 44)


if __name__ == "__main__":
    unittest.main()
