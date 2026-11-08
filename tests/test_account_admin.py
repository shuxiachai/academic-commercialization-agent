"""The operator's password reset.

Until there is an email service, a person who forgets their password has
two ways back, both through the operator: this command in the deployment's
shell, or the admin console (tests/test_admin_console.py). These tests pin
what the command must and must not do: the old password stops working
everywhere, the new one works at once, the only HTTP path to a reset is the
console's and answers to an admin's own password, and the command never
creates or half-touches a database by mistake.
"""
from __future__ import annotations

import contextlib
import io
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from api import account_admin, accounts
from api.main import app

OLD = "the original password"
EMAIL = "alice@example.com"


def _run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = account_admin.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def _printed_password(stdout: str) -> str:
    lines = [line for line in stdout.splitlines() if line.startswith("New password (shown once): ")]
    assert len(lines) == 1, stdout
    return lines[0].split(": ", 1)[1]


class ResetPasswordTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.database = Path(self._tmp.name) / "accounts.sqlite3"
        self._env = patch.dict("os.environ", {"ACCOUNTS_DB": str(self.database)})
        self._env.start()
        for name in ("ACCOUNTS_SIGNUP", "ACCOUNTS_ADMIN_EMAILS"):
            os.environ.pop(name, None)
        self.user = accounts.register(EMAIL, OLD)

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def test_the_old_password_stops_working_and_the_new_one_works_at_once(self):
        first, _ = accounts.login(EMAIL, OLD)
        second, _ = accounts.login(EMAIL, OLD)
        code, out, err = _run("reset-password", "  ALICE@example.com ")
        self.assertEqual((code, err), (0, ""))
        self.assertIn(f"Password reset for {EMAIL}.", out)
        self.assertIn("Sessions ended: 2.", out)
        new = _printed_password(out)
        self.assertGreaterEqual(len(new), 20)
        self.assertEqual(out.count(new), 1, "The password is printed exactly once")
        # Every session ends: the reason for a reset may be a stolen password.
        self.assertIsNone(accounts.session_user(first))
        self.assertIsNone(accounts.session_user(second))
        with self.assertRaises(accounts.AccountError) as refused:
            accounts.login(EMAIL, OLD)
        self.assertEqual(refused.exception.code, "invalid_credentials")
        token, user = accounts.login(EMAIL, new)
        self.assertEqual(user.email, EMAIL)
        self.assertIsNotNone(accounts.session_user(token))

    def test_each_reset_generates_a_different_password(self):
        passwords = {_printed_password(_run("reset-password", EMAIL)[1]) for _ in range(3)}
        self.assertEqual(len(passwords), 3)

    def test_a_locked_out_person_can_sign_in_with_the_new_password_immediately(self):
        for _ in range(accounts.LOCKOUT_FAILURES):
            with self.assertRaises(accounts.AccountError):
                accounts.login(EMAIL, "a wrong guess 123", client="203.0.113.9")
        with self.assertRaises(accounts.AccountError) as locked:
            accounts.login(EMAIL, OLD, client="203.0.113.9")
        self.assertEqual(locked.exception.code, "locked")
        new = _printed_password(_run("reset-password", EMAIL)[1])
        token, _ = accounts.login(EMAIL, new, client="203.0.113.9")
        self.assertIsNotNone(accounts.session_user(token))

    def test_another_accounts_password_sessions_and_lockout_are_untouched(self):
        accounts.register("bob@example.com", OLD)
        bob, _ = accounts.login("bob@example.com", OLD)
        with self.assertRaises(accounts.AccountError):
            accounts.login("bob@example.com", "a wrong guess 123", client="203.0.113.9")
        self.assertEqual(_run("reset-password", EMAIL)[0], 0)
        self.assertIsNotNone(accounts.session_user(bob))
        accounts.login("bob@example.com", OLD)
        with accounts._database() as db:
            rows = db.execute("SELECT key FROM login_throttle").fetchall()
        self.assertTrue(rows and all("bob@example.com" in row["key"] for row in rows))

    def test_a_disabled_account_stays_disabled(self):
        accounts.set_disabled(EMAIL, True)
        new = _printed_password(_run("reset-password", EMAIL)[1])
        with self.assertRaises(accounts.AccountError) as refused:
            accounts.login(EMAIL, new)
        self.assertEqual(refused.exception.code, "disabled")

    def test_an_unknown_address_changes_nothing_and_prints_no_password(self):
        code, out, err = _run("reset-password", "nobody@example.com")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("No account has this email address.", err)
        accounts.login(EMAIL, OLD)

    def test_without_a_database_it_creates_none(self):
        missing = Path(self._tmp.name) / "elsewhere" / "accounts.sqlite3"
        with patch.dict("os.environ", {"ACCOUNTS_DB": str(missing)}):
            code, out, err = _run("reset-password", EMAIL)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("No account database at", err)
        self.assertFalse(missing.exists())
        self.assertFalse(missing.parent.exists())
        os.environ.pop("ACCOUNTS_DB")
        code, out, err = _run("reset-password", EMAIL)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("ACCOUNTS_DB is not set", err)

    def test_the_library_function_applies_the_password_policy(self):
        for weak in ("short", EMAIL, "x" * (accounts.PASSWORD_MAX + 1), None):
            with self.subTest(weak=str(weak)[:12]), self.assertRaises(accounts.AccountError) as refused:
                accounts.reset_password(EMAIL, weak)
            self.assertEqual(refused.exception.code, "weak_password")
        accounts.login(EMAIL, OLD)

    def test_the_only_http_paths_to_a_reset_hold_a_secret_of_their_own(self):
        # A reset a visitor could trigger would need a secret of its own. The
        # console's is an admin account, and it re-asks that admin's password
        # (api/admin.py); the visitor's is the one-time token from a link sent
        # to the address (tests/test_password_reset.py). Nothing else in the
        # API may reach the library call that needs neither.
        paths = sorted({route.path for route in app.routes if hasattr(route, "path")})
        self.assertEqual([path for path in paths if "reset" in path.lower()],
                         ["/api/admin/accounts/{user_id}/password-reset", "/api/auth/password/reset", "/reset"])
        source = Path(accounts.__file__).with_name("main.py").read_text(encoding="utf-8")
        self.assertNotIn("accounts.reset_password", source)
        self.assertNotIn("account_admin", source)
        self.assertEqual(source.count("admin.reset_password("), 1)

    def test_usage_errors_do_not_touch_the_database(self):
        before = self.database.read_bytes()
        for argv in ((), ("reset-password",), ("delete-everything", EMAIL)):
            with self.subTest(argv=argv), self.assertRaises(SystemExit) as stopped:
                _run(*argv)
            self.assertEqual(stopped.exception.code, 2)
        self.assertEqual(self.database.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
