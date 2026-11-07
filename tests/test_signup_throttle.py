"""How many accounts one address, and the deployment, may create.

With sign-up open and no email verified, these two caps are what stands
between a script and a table full of addresses. They count accounts created,
not attempts, so a person correcting a typo pays nothing for it, and they
come after the sign-up rules, so a closed deployment is reported as closed.
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import accounts
from api.main import app

PASSWORD = "a sufficiently long password"
_ROOT = Path(__file__).resolve().parents[1]


class _SignUps(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._env = patch.dict("os.environ", {"ACCOUNTS_DB": str(Path(self._tmp.name) / "accounts.sqlite3"),
                                              "ACCOUNTS_SIGNUP": "open"})
        self._env.start()
        for name in ("ACCOUNTS_ADMIN_EMAILS", "ACCOUNTS_INVITE_CODE"):
            os.environ.pop(name, None)
        self._caps = [patch.object(accounts, "SIGNUPS_PER_HOUR_PER_CLIENT", 3), patch.object(accounts, "SIGNUPS_PER_DAY", 5),
                      patch.object(accounts, "_signups_by_client", {}), patch.object(accounts, "_signups_today", [])]
        for cap in self._caps:
            cap.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        for cap in reversed(self._caps):
            cap.stop()
        self._env.stop()
        self._tmp.cleanup()

    def _register(self, email, password=PASSWORD):
        return self.client.post("/api/auth/register", json={"email": email, "password": password})


class PerAddressTests(_SignUps):
    def test_an_address_may_create_a_few_accounts_an_hour_and_is_then_told_to_wait(self):
        for n in range(3):
            self.assertEqual(self._register(f"person{n}@example.com").status_code, 201)
        refused = self._register("person3@example.com")
        self.assertEqual((refused.status_code, refused.headers["X-Error-Code"]), (429, "signup_throttled"))
        self.assertEqual(refused.headers["Retry-After"], "3600")
        self.assertIn("Try again in an hour", refused.json()["detail"])
        # Nothing was created for the refused one, and signing in still works.
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "person3@example.com", "password": PASSWORD}).status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "person0@example.com", "password": PASSWORD}).status_code, 200)

    def test_only_accounts_created_are_counted_not_attempts(self):
        self.assertEqual(self._register("first@example.com").status_code, 201)
        # Typos, a taken address and a weak password: refusals, not sign-ups.
        self.assertEqual(self._register("not an address").status_code, 422)
        self.assertEqual(self._register("first@example.com").status_code, 409)
        self.assertEqual(self._register("second@example.com", "short").status_code, 422)
        self.assertEqual(self._register("second@example.com").status_code, 201)
        self.assertEqual(self._register("third@example.com").status_code, 201)
        self.assertEqual(self._register("fourth@example.com").status_code, 429)

    def test_the_hour_passes_and_another_address_is_another_address(self):
        base = 1_793_000_000
        self.enterContext(patch.object(accounts, "SIGNUPS_PER_DAY", 0))   # the per-address cap alone
        for n in range(3):
            accounts.register(f"a{n}@example.com", PASSWORD, client="10.0.0.1", now=base + n)
        with self.assertRaises(accounts.AccountError) as refused:
            accounts.register("a3@example.com", PASSWORD, client="10.0.0.1", now=base + 10)
        self.assertEqual(refused.exception.code, "signup_throttled")
        self.assertEqual(accounts.register("b0@example.com", PASSWORD, client="10.0.0.2", now=base + 10).email, "b0@example.com")
        self.assertEqual(accounts.register("a3@example.com", PASSWORD, client="10.0.0.1", now=base + 3601).email, "a3@example.com")
        # With no address known, only the deployment's cap applies.
        self.assertEqual(accounts.register("c0@example.com", PASSWORD, client=None, now=base + 3602).email, "c0@example.com")

    def test_the_rules_come_before_the_caps(self):
        # The address has used its cap. A closed deployment still says closed,
        # and a missing invite code still says so: the cap is not what they hit.
        for n in range(3):
            self.assertEqual(self._register(f"earlier{n}@example.com").status_code, 201)
        self.assertEqual(self._register("one-more@example.com").status_code, 429)
        with patch.dict("os.environ", {"ACCOUNTS_SIGNUP": "closed"}):
            refused = self._register("anyone@example.com")
            self.assertEqual((refused.status_code, refused.headers["X-Error-Code"]), (403, "signup_closed"))
        with patch.dict("os.environ", {"ACCOUNTS_SIGNUP": "invite", "ACCOUNTS_INVITE_CODE": "the-code"}):
            refused = self._register("anyone@example.com")
            self.assertEqual((refused.status_code, refused.headers["X-Error-Code"]), (403, "invite_required"))
        # Open mode: an admin address still needs the invite code, and the caps do not hide that.
        with patch.dict("os.environ", {"ACCOUNTS_ADMIN_EMAILS": "ops@example.com", "ACCOUNTS_INVITE_CODE": "the-code"}):
            refused = self._register("ops@example.com")
            self.assertEqual((refused.status_code, refused.headers["X-Error-Code"]), (403, "invite_required"))
            # With the right code the admin address meets the cap like anyone else.
            with_code = self.client.post("/api/auth/register", json={
                "email": "ops@example.com", "password": PASSWORD, "invite": "the-code"})
            self.assertEqual((with_code.status_code, with_code.headers["X-Error-Code"]), (429, "signup_throttled"))


class PerDayTests(_SignUps):
    def test_the_deployment_has_a_day_limit_across_every_address(self):
        base = 1_793_000_000
        for n in range(5):
            accounts.register(f"p{n}@example.com", PASSWORD, client=f"10.0.{n}.1", now=base + n)
        with self.assertRaises(accounts.AccountError) as refused:
            accounts.register("p5@example.com", PASSWORD, client="10.0.9.9", now=base + 10)
        self.assertEqual(refused.exception.code, "signup_throttled")
        self.assertIn("today's limit", refused.exception.message)
        self.assertEqual(accounts.register("p5@example.com", PASSWORD, client="10.0.9.9", now=base + 86401).email, "p5@example.com")

    def test_zero_turns_a_cap_off(self):
        with patch.object(accounts, "SIGNUPS_PER_HOUR_PER_CLIENT", 0), patch.object(accounts, "SIGNUPS_PER_DAY", 0):
            for n in range(8):
                self.assertEqual(self._register(f"many{n}@example.com").status_code, 201)

    def test_the_page_words_the_refusal_in_both_languages(self):
        app_js = (_ROOT / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('signup_throttled: "account_error_throttled"', app_js)
        strings = (_ROOT / "web" / "static" / "js" / "i18n.js").read_text(encoding="utf-8")
        self.assertEqual(strings.count("    account_error_throttled: "), 2)


if __name__ == "__main__":
    unittest.main()
