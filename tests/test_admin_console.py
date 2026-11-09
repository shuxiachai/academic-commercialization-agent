"""The operator's console: who may see it, what it shows, and what it may do.

Three things matter more than the rest. Only an admin account gets anything
but 404, an admin access code included. Every action re-asks the admin's own
password. And nothing an account should never see leaves the server: no
hash, no token, no email address in a URL or a log line.
"""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import access, account_backup, accounts, admin, link_probe, runs
from api.main import app

ADMIN, ALICE, BOB = "ops@example.com", "alice@example.com", "bob@example.com"
PASSWORD = {ADMIN: "the operator's own password", ALICE: "alice's long password", BOB: "bob's long password too"}
INVITE = "an-invite-code"
_ROOT = Path(__file__).resolve().parent.parent


class _Console(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._env = patch.dict("os.environ", {
            "ACCOUNTS_DB": str(self.root / "accounts.sqlite3"), "ACCOUNTS_ADMIN_EMAILS": ADMIN,
            "ACCOUNTS_SIGNUP": "invite", "ACCOUNTS_INVITE_CODE": INVITE,
            "ACCOUNTS_BACKUP_DIR": str(self.root / "backups")})
        self._env.start()
        for name in ("ACCOUNTS_BACKUP_HOURS", "ACCOUNTS_BACKUP_KEEP", "OPERATOR_CONTACT"):
            os.environ.pop(name, None)
        self._outputs = patch.object(runs, "DEFAULT_OUTPUT_ROOT", self.root / "outputs")
        self._outputs.start()
        (self.root / "outputs").mkdir()
        self.client = TestClient(app)
        self.tokens = {}
        for email in (ADMIN, ALICE, BOB):
            response = self.client.post("/api/auth/register",
                                        json={"email": email, "password": PASSWORD[email], "invite": INVITE})
            self.assertEqual(response.status_code, 201, response.text)
            self.tokens[email] = response.json()["token"]

    def tearDown(self):
        self.client.close()
        self._outputs.stop()
        self._env.stop()
        self._tmp.cleanup()

    def _as(self, email):
        return {"Authorization": f"Bearer {self.tokens[email]}"}

    def _accounts(self, email=ADMIN):
        response = self.client.get("/api/admin/accounts", headers=self._as(email))
        self.assertEqual(response.status_code, 200, response.text)
        return {row["email"]: row for row in response.json()["accounts"]}

    def _login(self, email, password):
        return self.client.post("/api/auth/login", json={"email": email, "password": password})

    def _run_for(self, email, number):
        run_id = f"20261107T0{number:05d}Z-{'ab' * 16}"[:50]
        directory = self.root / "outputs" / run_id
        directory.mkdir()
        (directory / "status.json").write_text(json.dumps({"done": True, "topic": "t"}), encoding="utf-8")
        (directory / ".owner").write_text(accounts.owner_tag(self._accounts()[email]["id"]), encoding="utf-8")


_PROBE = {
    "taken_at": "2026-11-09T08:00:00+00:00", "timeout_seconds": 30.0, "small_bytes": 1000, "large_bytes": 100000,
    "sizes": [1000, 10000, 30000, 100000],
    "targets": [{"name": "configured", "host": "dashscope.aliyuncs.com", "readings": [
        {"body_bytes": 1000, "connect_ms": 80, "tls_ms": 170, "upload_ms": 171, "first_byte_ms": 400,
         "total_ms": 401, "status": 401, "error": None},
        {"body_bytes": 100000, "connect_ms": 82, "tls_ms": 175, "upload_ms": None, "first_byte_ms": None,
         "total_ms": 30180, "status": None, "error": "WriteTimeout"}]}],
}


class WhoMaySeeItTests(_Console):
    def test_only_an_admin_account_gets_anything_but_404(self):
        for path in ("/api/admin/accounts", "/api/admin/backups"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401, "anonymous: the gate")
                self.assertEqual(self.client.get(path, headers=self._as(ALICE)).status_code, 404)
                with patch.object(access, "ACCESS_CODE", "a-code"), patch.object(access, "ADMIN_CODE", "the-admin-code"):
                    # The admin code reads every run; it is not an admin here.
                    self.assertEqual(self.client.get(path, headers={"X-Access-Code": "the-admin-code"}).status_code, 404)
                self.assertEqual(self.client.get(path, headers=self._as(ADMIN)).status_code, 200)
        for path in (f"/api/admin/accounts/{self._accounts()[ALICE]['id']}/password-reset",
                     f"/api/admin/accounts/{self._accounts()[ALICE]['id']}/disabled"):
            body = {"password": PASSWORD[BOB], "disabled": True}
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, json=body).status_code, 401)
                self.assertEqual(self.client.post(path, json=body, headers=self._as(BOB)).status_code, 404)
        # Nothing happened to Alice.
        self.assertEqual(self._login(ALICE, PASSWORD[ALICE]).status_code, 200)

    def test_the_link_probe_answers_only_an_admin_account_and_posts_to_fixed_targets(self):
        """It makes this server post to the provider; who may ask is the
        same question as for the rest of the console, and where it posts is
        not the caller's to choose."""
        calls = []

        def fake_run():
            calls.append(1)
            return _PROBE

        with patch.object(link_probe, "run", fake_run):
            self.assertEqual(self.client.post("/api/admin/link-probe").status_code, 401)
            self.assertEqual(self.client.post("/api/admin/link-probe", headers=self._as(ALICE)).status_code, 404)
            with patch.object(access, "ACCESS_CODE", "a-code"), patch.object(access, "ADMIN_CODE", "the-admin-code"):
                self.assertEqual(self.client.post("/api/admin/link-probe",
                                                  headers={"X-Access-Code": "the-admin-code"}).status_code, 404)
            self.assertEqual(calls, [], "nobody but an admin account makes this server post anywhere")
            answer = self.client.post("/api/admin/link-probe", headers=self._as(ADMIN),
                                      json={"url": "https://attacker.example/collect"})
        self.assertEqual(answer.status_code, 200, answer.text)
        self.assertEqual(answer.json(), _PROBE)
        self.assertEqual(calls, [1])

    def test_the_link_probe_says_when_it_cannot_run(self):
        with patch.object(link_probe, "run", side_effect=link_probe.Busy("A link probe is already running.")):
            self.assertEqual(self.client.post("/api/admin/link-probe", headers=self._as(ADMIN)).status_code, 409)
        with patch.object(link_probe, "run", side_effect=link_probe.NoEndpoint("No provider endpoint is configured.")):
            self.assertEqual(self.client.post("/api/admin/link-probe", headers=self._as(ADMIN)).status_code, 503)

    def test_the_console_offers_the_probe(self):
        page = (_ROOT / "web" / "admin.html").read_text(encoding="utf-8")
        self.assertIn('id="link-probe"', page)
        self.assertIn('id="link-rows"', page)
        script = (_ROOT / "web" / "static" / "js" / "admin.js").read_text(encoding="utf-8")
        self.assertIn("api.adminLinkProbe()", script)
        client = (_ROOT / "web" / "static" / "js" / "api.js").read_text(encoding="utf-8")
        self.assertIn('request("/api/admin/link-probe", { method: "POST" })', client)

    def test_the_page_is_a_plain_document_that_says_nothing_by_itself(self):
        page = self.client.get("/admin")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.headers["cache-control"], "no-cache")
        self.assertIn("/static/js/admin.js", page.text)
        for secret in (ADMIN, ALICE, "scrypt", INVITE):
            self.assertNotIn(secret, page.text)
        self.assertIn('name="robots" content="noindex"', page.text)

    def test_the_app_offers_the_console_to_admins_only(self):
        index = (_ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<a id="account-console" href="/admin" data-i18n="account_console" hidden>', index)
        script = (_ROOT / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('$("#account-console").hidden = me.admin !== true;', script)
        strings = (_ROOT / "web" / "static" / "js" / "i18n.js").read_text(encoding="utf-8")
        self.assertEqual(strings.count("account_console:"), 2, "both languages")


class WhatItShowsTests(_Console):
    def test_accounts_are_listed_newest_first_with_what_an_operator_asks(self):
        rows = self.client.get("/api/admin/accounts", headers=self._as(ADMIN)).json()["accounts"]
        self.assertEqual([row["email"] for row in rows], [BOB, ALICE, ADMIN])
        self.assertEqual(set(rows[0]), {"id", "email", "created_at", "disabled", "verified", "admin", "sessions", "last_seen_at", "runs"})
        by_email = {row["email"]: row for row in rows}
        self.assertEqual((by_email[ADMIN]["admin"], by_email[ALICE]["admin"]), (True, False))
        self.assertEqual(by_email[ALICE]["sessions"], 1)
        self.assertIsNotNone(by_email[ALICE]["last_seen_at"])
        self.assertFalse(any(row["disabled"] for row in rows))
        # Never a hash, never a token, however the row is spelled.
        self.assertNotIn("scrypt", json.dumps(rows))
        self.assertNotIn(self.tokens[ALICE], json.dumps(rows))

    def test_sign_ins_are_live_ones_and_runs_are_counted_per_account(self):
        self._login(ALICE, PASSWORD[ALICE])
        self._login(ALICE, PASSWORD[ALICE])
        self.assertEqual(self._accounts()[ALICE]["sessions"], 3)
        # An expired token is not a sign-in, even before its row goes.
        with contextlib.closing(sqlite3.connect(os.environ["ACCOUNTS_DB"])) as db, db:
            db.execute("UPDATE sessions SET expires_at = ? WHERE user_id = (SELECT id FROM users WHERE email = ?)",
                       (int(time.time()) - 1, ALICE))
        self.assertEqual(self._accounts()[ALICE]["sessions"], 0)
        self.assertIsNone(self._accounts()[ALICE]["last_seen_at"])
        for number in range(3):
            self._run_for(ALICE, number)
        self._run_for(BOB, 7)
        counts = {email: row["runs"] for email, row in self._accounts().items()}
        self.assertEqual(counts, {ADMIN: 0, ALICE: 3, BOB: 1})

    def test_backups_are_listed_newest_first_and_each_is_verified(self):
        answer = self.client.get("/api/admin/backups", headers=self._as(ADMIN)).json()
        self.assertEqual(answer, {"scheduled": True, "every_hours": 24, "keep": 14, "backups": []})
        moment = 1_793_000_000
        account_backup.run_schedule(moment)
        account_backup.run_schedule(moment + 86400)
        (self.root / "backups" / "accounts-20261101T000000Z.sqlite3").write_bytes(b"not a database")
        rows = self.client.get("/api/admin/backups", headers=self._as(ADMIN)).json()["backups"]
        self.assertEqual([row["name"] for row in rows], sorted((row["name"] for row in rows), reverse=True))
        self.assertEqual(len(rows), 3)
        good = [row for row in rows if row["accounts"] is not None]
        bad = [row for row in rows if row["accounts"] is None]
        self.assertEqual(len(good), 2)
        self.assertEqual({row["accounts"] for row in good}, {3})
        self.assertEqual((good[0]["taken_at"], good[0]["problem"]), (moment + 86400, None))
        self.assertGreater(good[0]["size"], 0)
        self.assertEqual(len(bad), 1)
        self.assertIn("cannot be read as a database", bad[0]["problem"])
        with patch.dict("os.environ", {"ACCOUNTS_BACKUP_HOURS": "0"}):
            answer = self.client.get("/api/admin/backups", headers=self._as(ADMIN)).json()
        self.assertEqual((answer["scheduled"], answer["every_hours"], answer["keep"]), (False, None, None))
        self.assertEqual(len(answer["backups"]), 3, "off for the future does not hide what was taken")


class WhatItMayDoTests(_Console):
    def test_a_reset_needs_the_admins_own_password_and_ends_the_accounts_sign_ins(self):
        alice = self._accounts()[ALICE]["id"]
        self._login(ALICE, PASSWORD[ALICE])
        path = f"/api/admin/accounts/{alice}/password-reset"
        refused = self.client.post(path, json={"password": "not the admin's"}, headers=self._as(ADMIN))
        self.assertEqual((refused.status_code, refused.headers["X-Error-Code"]), (401, "invalid_credentials"))
        self.assertEqual(self._login(ALICE, PASSWORD[ALICE]).status_code, 200, "a refused attempt changes nothing")
        with self.assertLogs("api.admin", level="WARNING") as logged:
            done = self.client.post(path, json={"password": PASSWORD[ADMIN]}, headers=self._as(ADMIN))
        self.assertEqual(done.status_code, 200, done.text)
        body = done.json()
        self.assertEqual(set(body), {"email", "temporary_password", "sessions_ended"})
        self.assertEqual((body["email"], body["sessions_ended"]), (ALICE, 3))
        new = body["temporary_password"]
        self.assertGreaterEqual(len(new), accounts.PASSWORD_MIN)
        # The old password and every old session are gone; the new password works.
        self.assertEqual(self._login(ALICE, PASSWORD[ALICE]).status_code, 401)
        self.assertEqual(self.client.get("/api/auth/me", headers=self._as(ALICE)).status_code, 401)
        self.assertEqual(self._login(ALICE, new).status_code, 200)
        # The admin stays signed in; the log names ids, never addresses or the password.
        self.assertEqual(self.client.get("/api/auth/me", headers=self._as(ADMIN)).status_code, 200)
        line = " ".join(record.getMessage() for record in logged.records)
        self.assertIn(f"reset the password of account {alice}", line)
        for secret in (ALICE, ADMIN, new):
            self.assertNotIn(secret, line)
        # Two resets never agree.
        again = self.client.post(path, json={"password": PASSWORD[ADMIN]}, headers=self._as(ADMIN)).json()
        self.assertNotEqual(again["temporary_password"], new)

    def test_an_admin_cannot_reset_or_disable_themself_here(self):
        me = self._accounts()[ADMIN]["id"]
        for path, body in ((f"/api/admin/accounts/{me}/password-reset", {}),
                           (f"/api/admin/accounts/{me}/disabled", {"disabled": True})):
            with self.subTest(path=path):
                refused = self.client.post(path, json={"password": PASSWORD[ADMIN], **body}, headers=self._as(ADMIN))
                self.assertEqual((refused.status_code, refused.headers["X-Error-Code"]), (409, "own_account"))
        self.assertEqual(self._login(ADMIN, PASSWORD[ADMIN]).status_code, 200)

    def test_an_unknown_or_malformed_account_id_is_refused_without_a_change(self):
        for user_id, status in (("999", 404), ("abc", 422), ("-1", 404)):
            with self.subTest(user_id=user_id):
                refused = self.client.post(f"/api/admin/accounts/{user_id}/password-reset",
                                           json={"password": PASSWORD[ADMIN]}, headers=self._as(ADMIN))
                self.assertEqual(refused.status_code, status)

    def test_disabling_stops_sign_in_and_ends_sessions_and_enabling_restores_it(self):
        bob = self._accounts()[BOB]["id"]
        path = f"/api/admin/accounts/{bob}/disabled"
        with self.assertLogs("api.admin", level="WARNING") as logged:
            self.assertEqual(self.client.post(path, json={"password": PASSWORD[ADMIN], "disabled": True},
                                              headers=self._as(ADMIN)).status_code, 204)
        self.assertIn(f"disabled account {bob}", logged.records[0].getMessage())
        self.assertNotIn(BOB, logged.records[0].getMessage())
        self.assertEqual(self._accounts()[BOB]["disabled"], True)
        self.assertEqual(self.client.get("/api/auth/me", headers=self._as(BOB)).status_code, 401)
        refused = self._login(BOB, PASSWORD[BOB])
        self.assertEqual((refused.status_code, refused.headers["X-Error-Code"]), (403, "disabled"))
        # The wrong admin password enables nothing.
        self.assertEqual(self.client.post(path, json={"password": "wrong", "disabled": False},
                                          headers=self._as(ADMIN)).status_code, 401)
        self.assertEqual(self._accounts()[BOB]["disabled"], True)
        self.assertEqual(self.client.post(path, json={"password": PASSWORD[ADMIN], "disabled": False},
                                          headers=self._as(ADMIN)).status_code, 204)
        self.assertEqual(self._accounts()[BOB]["disabled"], False)
        self.assertEqual(self._login(BOB, PASSWORD[BOB]).status_code, 200, "the same password still works")

    def test_guessing_the_admins_password_here_locks_like_a_sign_in(self):
        alice = self._accounts()[ALICE]["id"]
        path = f"/api/admin/accounts/{alice}/password-reset"
        for _ in range(accounts.LOCKOUT_FAILURES):
            self.assertEqual(self.client.post(path, json={"password": "guess"}, headers=self._as(ADMIN)).status_code, 401)
        locked = self.client.post(path, json={"password": PASSWORD[ADMIN]}, headers=self._as(ADMIN))
        self.assertEqual((locked.status_code, locked.headers["X-Error-Code"]), (429, "locked"))
        self.assertEqual(self._login(ALICE, PASSWORD[ALICE]).status_code, 200, "nothing was reset")

    def test_the_command_and_the_console_make_the_same_kind_of_password(self):
        with patch.object(admin, "generated_password", return_value="made-by-the-shared-generator-x") as made:
            from api import account_admin
            code = account_admin.main(["reset-password", ALICE])
        self.assertEqual(code, 0)
        self.assertEqual(made.call_count, 1)
        self.assertEqual(self._login(ALICE, "made-by-the-shared-generator-x").status_code, 200)


if __name__ == "__main__":
    unittest.main()
