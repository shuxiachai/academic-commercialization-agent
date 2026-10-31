"""Accounts in isolation: hashing, sessions, lockout and the owner tag.

No HTTP here. api.accounts is a small store with a policy; each test pins one
rule a product user would feel if it slipped: a password that verifies when it
should not, a session that outlives its expiry, a lock that never engages.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from api import accounts


class _AccountsCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.db = Path(self._tmp.name) / "nested" / "accounts.sqlite3"
        self._env = patch.dict("os.environ", {"ACCOUNTS_DB": str(self.db)}, clear=False)
        self._env.start()
        # patch.dict restores these on stop, whether popped or not.
        for name in ("ACCOUNTS_SIGNUP", "ACCOUNTS_ADMIN_EMAILS"):
            os.environ.pop(name, None)

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()


class ConfigurationTests(unittest.TestCase):
    def test_disabled_by_default_and_nothing_touches_disk(self):
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("ACCOUNTS_DB", None)
            self.assertFalse(accounts.enabled())
            self.assertIsNone(accounts.session_user("anything"))
            self.assertFalse(accounts.logout("anything"))
            self.assertIsNone(accounts.label_for_owner("user:1"))
            with self.assertRaises(accounts.AccountError) as ctx:
                accounts.register("a@example.com", "long-enough-password")
            self.assertEqual(ctx.exception.code, "accounts_disabled")

    def test_blank_path_is_disabled_too(self):
        with patch.dict("os.environ", {"ACCOUNTS_DB": "   "}, clear=False):
            self.assertFalse(accounts.enabled())


class PasswordTests(unittest.TestCase):
    def test_hash_roundtrip_and_salt(self):
        first, second = accounts.hash_password("correct horse battery"), accounts.hash_password("correct horse battery")
        self.assertNotEqual(first, second)              # fresh salt each time
        self.assertTrue(accounts.verify_password("correct horse battery", first))
        self.assertFalse(accounts.verify_password("correct horse battery ", first))
        self.assertFalse(accounts.verify_password("", first))

    def test_a_damaged_or_foreign_hash_never_verifies(self):
        for stored in ("", "plain", "scrypt$x$8$1$!!$!!", "bcrypt$a$b$c$d$e", "scrypt$32768$8$1$AAAA"):
            self.assertFalse(accounts.verify_password("anything", stored), stored)

    def test_parameters_travel_with_the_hash(self):
        stored = accounts.hash_password("correct horse battery")
        scheme, n, r, p, *_ = stored.split("$")
        self.assertEqual((scheme, n, r, p), ("scrypt", "16384", "8", "1"))


class RegisterTests(_AccountsCase):
    def test_register_normalises_the_email_and_returns_the_owner_tag(self):
        user = accounts.register("  Alice@Example.COM ", "a sufficiently long password")
        self.assertEqual(user.email, "alice@example.com")
        self.assertEqual(user.owner, f"user:{user.id}")
        self.assertTrue(self.db.is_file())              # the parent directory was created

    def test_duplicate_email_is_refused_case_insensitively(self):
        accounts.register("alice@example.com", "a sufficiently long password")
        with self.assertRaises(accounts.AccountError) as ctx:
            accounts.register("ALICE@example.com", "another long password")
        self.assertEqual(ctx.exception.code, "email_taken")

    def test_email_and_password_policy(self):
        for email in ("", "no-at-sign", "a@b", "a b@c.d", "x@" + "y" * 260 + ".com"):
            with self.subTest(email=email), self.assertRaises(accounts.AccountError) as ctx:
                accounts.register(email, "a sufficiently long password")
            self.assertEqual(ctx.exception.code, "invalid_email")
        for password in ("short", "x" * 9, None, 12345, "x" * 201, "ALICE@example.com"):
            with self.subTest(password=password), self.assertRaises(accounts.AccountError) as ctx:
                accounts.register("alice@example.com", password)
            self.assertEqual(ctx.exception.code, "weak_password")

    def test_signup_can_be_closed_without_locking_existing_accounts_out(self):
        accounts.register("alice@example.com", "a sufficiently long password")
        with patch.dict("os.environ", {"ACCOUNTS_SIGNUP": "closed"}):
            self.assertFalse(accounts.signup_open())
            with self.assertRaises(accounts.AccountError) as ctx:
                accounts.register("bob@example.com", "a sufficiently long password")
            self.assertEqual(ctx.exception.code, "signup_closed")
            token, user = accounts.login("alice@example.com", "a sufficiently long password")
            self.assertEqual(user.email, "alice@example.com")
            self.assertTrue(token)


PASSWORD_OK = "a sufficiently long password"


class LoginAndSessionTests(_AccountsCase):
    def setUp(self):
        super().setUp()
        self.user = accounts.register("alice@example.com", PASSWORD_OK)

    def test_login_opens_a_session_that_resolves_until_it_expires(self):
        token, user = accounts.login("Alice@example.com", "a sufficiently long password", now=1_000)
        self.assertEqual(user.id, self.user.id)
        self.assertEqual(accounts.session_user(token, now=1_000 + accounts.SESSION_SECONDS - 1).email, "alice@example.com")
        self.assertIsNone(accounts.session_user(token, now=1_000 + accounts.SESSION_SECONDS))
        # Expiry removed the row; the token does not come back later either.
        self.assertIsNone(accounts.session_user(token, now=1_000))

    def test_tokens_are_stored_hashed_and_are_distinct_per_login(self):
        first, _ = accounts.login("alice@example.com", "a sufficiently long password")
        second, _ = accounts.login("alice@example.com", "a sufficiently long password")
        self.assertNotEqual(first, second)
        with closing(sqlite3.connect(str(self.db))) as connection:
            rows = connection.execute("SELECT token_hash FROM sessions").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertNotIn((first,), rows)
        self.assertNotIn((second,), rows)

    def test_logout_ends_only_that_session(self):
        first, _ = accounts.login("alice@example.com", "a sufficiently long password")
        second, _ = accounts.login("alice@example.com", "a sufficiently long password")
        self.assertTrue(accounts.logout(first))
        self.assertFalse(accounts.logout(first))         # already gone
        self.assertIsNone(accounts.session_user(first))
        self.assertIsNotNone(accounts.session_user(second))

    def test_wrong_password_unknown_email_and_garbage_are_the_same_refusal(self):
        for email, password in (("alice@example.com", "wrong password here"), ("nobody@example.com", "a sufficiently long password"),
                                (None, None), ("alice@example.com", 42)):
            with self.subTest(email=email), self.assertRaises(accounts.AccountError) as ctx:
                accounts.login(email, password)
            self.assertEqual(ctx.exception.code, "invalid_credentials")

    def test_repeated_failures_lock_the_email_for_a_while_then_clear_on_success(self):
        for _ in range(accounts.LOCKOUT_FAILURES):
            with self.assertRaises(accounts.AccountError):
                accounts.login("alice@example.com", "wrong password here", now=5_000)
        with self.assertRaises(accounts.AccountError) as ctx:
            accounts.login("alice@example.com", "a sufficiently long password", now=5_001)
        self.assertEqual(ctx.exception.code, "locked")    # even the right password waits
        token, _ = accounts.login("alice@example.com", "a sufficiently long password",
                                  now=5_000 + accounts.LOCKOUT_SECONDS)
        self.assertTrue(token)
        # A clean sign-in resets the count: one more wrong try does not lock.
        with self.assertRaises(accounts.AccountError) as ctx:
            accounts.login("alice@example.com", "wrong password here", now=6_000 + accounts.LOCKOUT_SECONDS)
        self.assertEqual(ctx.exception.code, "invalid_credentials")

    def test_lockout_is_per_source_so_a_stranger_cannot_lock_a_user_out(self):
        for _ in range(accounts.LOCKOUT_FAILURES):
            with self.assertRaises(accounts.AccountError):
                accounts.login("alice@example.com", "wrong password here", client="203.0.113.9", now=7_000)
        with self.assertRaises(accounts.AccountError) as ctx:
            accounts.login("alice@example.com", PASSWORD_OK, client="203.0.113.9", now=7_001)
        self.assertEqual(ctx.exception.code, "locked")
        # Alice, from her own address, still gets in.
        token, _ = accounts.login("alice@example.com", PASSWORD_OK, client="198.51.100.7", now=7_001)
        self.assertTrue(token)

    def test_enough_failures_from_anywhere_still_lock_the_email(self):
        for i in range(accounts.LOCKOUT_EMAIL_FAILURES):
            with self.assertRaises(accounts.AccountError):
                accounts.login("alice@example.com", "wrong password here", client=f"10.0.0.{i}", now=8_000)
        with self.assertRaises(accounts.AccountError) as ctx:
            accounts.login("alice@example.com", PASSWORD_OK, client="198.51.100.7", now=8_001)
        self.assertEqual(ctx.exception.code, "locked")

    def test_a_reserved_admin_address_needs_the_invite_code_in_every_mode(self):
        with patch.dict("os.environ", {"ACCOUNTS_ADMIN_EMAILS": "ops@example.com"}):
            with self.assertRaises(accounts.AccountError) as ctx:
                accounts.register("ops@example.com", PASSWORD_OK)
            self.assertEqual(ctx.exception.code, "invite_required")
            with patch.dict("os.environ", {"ACCOUNTS_INVITE_CODE": "let-me-in"}):
                with self.assertRaises(accounts.AccountError):
                    accounts.register("ops@example.com", PASSWORD_OK, invite="nope")
                self.assertTrue(accounts.register("ops@example.com", PASSWORD_OK, invite=" let-me-in ").admin)

    def test_invite_mode_and_unknown_modes(self):
        with patch.dict("os.environ", {"ACCOUNTS_SIGNUP": "invite", "ACCOUNTS_INVITE_CODE": "let-me-in"}):
            self.assertEqual(accounts.signup_mode(), "invite")
            with self.assertRaises(accounts.AccountError) as ctx:
                accounts.register("carol@example.com", PASSWORD_OK)
            self.assertEqual(ctx.exception.code, "invite_required")
            accounts.register("carol@example.com", PASSWORD_OK, invite="let-me-in")
        with patch.dict("os.environ", {"ACCOUNTS_SIGNUP": "whatever"}):
            self.assertEqual(accounts.signup_mode(), "closed")     # a typo never opens sign-up
            self.assertFalse(accounts.signup_open())

    def test_unknown_malformed_and_oversized_tokens_resolve_to_nobody(self):
        for token in (None, "", "x" * 129, "not-a-token", 12):
            self.assertIsNone(accounts.session_user(token), token)

    def test_disabling_an_account_ends_its_sessions_and_refuses_sign_in(self):
        token, _ = accounts.login("alice@example.com", "a sufficiently long password")
        self.assertTrue(accounts.set_disabled("ALICE@example.com", True))
        self.assertIsNone(accounts.session_user(token))
        with self.assertRaises(accounts.AccountError) as ctx:
            accounts.login("alice@example.com", "a sufficiently long password")
        self.assertEqual(ctx.exception.code, "disabled")
        self.assertTrue(accounts.set_disabled("alice@example.com", False))
        self.assertFalse(accounts.set_disabled("nobody@example.com", True))

    def test_admin_is_a_deployment_setting_read_at_request_time(self):
        self.assertFalse(self.user.admin)
        with patch.dict("os.environ", {"ACCOUNTS_ADMIN_EMAILS": " Alice@Example.com , ops@example.com"}):
            self.assertTrue(self.user.admin)
            _, user = accounts.login("alice@example.com", "a sufficiently long password")
            self.assertTrue(user.admin)

    def test_owner_tag_labels_back_to_the_email_for_the_admin_view(self):
        self.assertEqual(accounts.label_for_owner(self.user.owner), "alice@example.com")
        self.assertIsNone(accounts.label_for_owner("user:999"))
        self.assertIsNone(accounts.label_for_owner("user:not-a-number"))
        self.assertIsNone(accounts.label_for_owner("0123456789abcdef"))   # an access-code owner
        self.assertTrue(accounts.is_user_owner("user:1"))
        self.assertFalse(accounts.is_user_owner("0123456789abcdef"))


if __name__ == "__main__":
    unittest.main()
