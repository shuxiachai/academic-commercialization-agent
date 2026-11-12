"""The console's funnel: of the accounts created lately, how many got how far.

Sign-up has been open since 2026-11-07 and a first assessment can now be the
deployment's to pay for. Whether either does anything was not readable
anywhere: the console listed accounts and counted their runs, and to learn
how many newcomers proved their address, started a run or finished one, the
operator would have had to count rows by eye.

The funnel is counts and nothing else. No address leaves the server in it,
administrators are not newcomers and are counted apart, and what the volume
no longer holds is said rather than guessed: a run its owner deleted, or
one that retention removed, is not in any number here.
"""
from __future__ import annotations

import json
import os
import sqlite3
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import access, accounts, admin, runs
from api.main import app

ADMIN = "ops@example.com"
PASSWORD = "a sufficiently long password"
INVITE = "an-invite-code"
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
_ROOT = Path(__file__).resolve().parents[1]


class _Case(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._env = patch.dict("os.environ", {
            "ACCOUNTS_DB": str(self.root / "accounts.sqlite3"), "ACCOUNTS_ADMIN_EMAILS": ADMIN,
            "ACCOUNTS_SIGNUP": "open", "ACCOUNTS_INVITE_CODE": INVITE, "ACCOUNTS_SIGNUPS_PER_HOUR": "0"})
        self._env.start()
        for name in ("MAIL_OUTBOX", "MAIL_RESEND_API_KEY", "ACCOUNTS_TRIAL_RUNS"):
            os.environ.pop(name, None)
        self.outputs = self.root / "outputs"
        self.outputs.mkdir()
        self._patches = [patch.object(runs, "DEFAULT_OUTPUT_ROOT", self.outputs), patch.object(runs, "_registry", {}),
                         patch.object(access, "ACCESS_CODE", None), patch.object(access, "ACCESS_CODES", None)]
        for item in self._patches:
            item.start()
        self._serial = 0
        self.ids = {}

    def tearDown(self):
        for item in self._patches:
            item.stop()
        self._env.stop()
        self._tmp.cleanup()

    def _sql(self, statement, *values):
        db = sqlite3.connect(os.environ["ACCOUNTS_DB"])
        try:
            db.execute(statement, values)
            db.commit()
        finally:
            db.close()

    def _account(self, name, *, days_ago=1.0, verified=True, admin=False):
        """An account created `days_ago` before NOW, its address proven or not."""
        email = ADMIN if admin else f"{name}@example.com"
        user = accounts.register(email, PASSWORD, invite=INVITE if admin else None)
        created = int((NOW - timedelta(days=days_ago)).timestamp())
        self._sql("UPDATE users SET created_at = ?, verified_at = ? WHERE id = ?",
                  created, created + 60 if verified else None, user.id)
        self.ids[name] = user.id
        return user

    def _run(self, owner, *, days_ago=0.5, status=None, cancelled=False, trial=None):
        """A run directory started `days_ago` before NOW, ended as `status` says."""
        self._serial += 1
        started = NOW - timedelta(days=days_ago)
        run_dir = self.outputs / f"{started:%Y%m%dT%H%M%SZ}-{self._serial:032x}"
        run_dir.mkdir()
        if owner is not None:
            tag = accounts.owner_tag(self.ids[owner]) if owner in self.ids else owner
            (run_dir / ".owner").write_text(tag, encoding="utf-8")
        (run_dir / "status.json").write_text(json.dumps(status if status is not None else {"done": True}), encoding="utf-8")
        if cancelled:
            (run_dir / runs._CANCEL_MARKER).write_text("", encoding="utf-8")
        if trial is not None:
            (run_dir / ".trial").write_text(json.dumps({"user_id": 1, "day": "2026-11-11", "released": trial}), encoding="utf-8")
        return run_dir

    def _funnel(self, days=30):
        return admin.funnel(days, now=NOW.timestamp())


FAILED_UNREACHABLE = {"done": True, "error": "Connection error."}
FAILED_QUALITY = {"done": True, "error": "Guardrail failed: blocking validation errors"}


class CohortTests(_Case):
    def test_each_step_counts_the_accounts_that_got_that_far(self):
        self._account("ops", admin=True)
        self._account("ann")                       # proven, ran, finished one
        self._account("bea")                       # proven, ran, none finished
        self._account("cal")                       # proven, never ran
        self._account("dee", verified=False)       # never proved the address
        self._run("ann", status=FAILED_QUALITY)
        self._run("ann")
        self._run("bea", status=FAILED_UNREACHABLE)
        self._run("ops")
        found = self._funnel()
        self.assertEqual((found.accounts_created, found.accounts_verified, found.accounts_ran, found.accounts_completed),
                         (4, 3, 2, 1))

    def test_an_administrator_is_not_a_newcomer(self):
        self._account("ops", admin=True)
        self._run("ops")
        self._run("ops", status=FAILED_QUALITY)
        found = self._funnel()
        self.assertEqual((found.accounts_created, found.accounts_ran, found.accounts_completed), (0, 0, 0))
        self.assertEqual(found.admin_runs, 2)
        self.assertEqual(found.runs["started"], 0, "their runs are counted apart, not among the visitors'")

    def test_the_window_is_when_the_account_was_created(self):
        self._account("old", days_ago=40)
        self._account("new", days_ago=3)
        self._run("old", days_ago=1)          # an old account's recent run
        self._run("new", days_ago=1)
        month, week, quarter = self._funnel(30), self._funnel(2), self._funnel(90)
        self.assertEqual((month.accounts_created, month.accounts_completed), (1, 1))
        self.assertEqual(week.accounts_created, 0)
        self.assertEqual((quarter.accounts_created, quarter.accounts_completed), (2, 2))
        self.assertEqual(month.window_days, 30)
        self.assertEqual(month.since, int((NOW - timedelta(days=30)).timestamp()))

    def test_an_account_counts_once_however_many_runs_it_has(self):
        self._account("ann")
        for _ in range(4):
            self._run("ann")
        found = self._funnel()
        self.assertEqual((found.accounts_ran, found.accounts_completed), (1, 1))


class RunOutcomeTests(_Case):
    def test_runs_started_in_the_window_by_how_they_ended(self):
        self._account("ann")
        self._run("ann")
        self._run("ann")
        self._run("ann", status=FAILED_UNREACHABLE)
        self._run("ann", status=FAILED_UNREACHABLE)
        self._run("ann", status=FAILED_QUALITY)
        self._run("ann", status={"done": False}, cancelled=True)
        self._run("ann", days_ago=45)                       # before the window
        self._run("code:abc")                               # an access code's run
        self._run(None, status=FAILED_QUALITY)              # nobody's: a visitor on their own keys
        found = self._funnel()
        self.assertEqual(found.runs, {"started": 8, "completed": 3, "failed": 4, "cancelled": 1, "timeout": 0,
                                      "running": 0, "unknown": 0})
        self.assertEqual(found.failures, [("provider_unreachable", 2), ("quality_checks", 2)],
                         "a tie reads in the same order every time: by the code's name")

    def test_failure_reasons_are_the_public_codes_most_frequent_first(self):
        self._account("ann")
        for status in (FAILED_UNREACHABLE, FAILED_UNREACHABLE, FAILED_UNREACHABLE, FAILED_QUALITY,
                       {"done": True, "error": "ValueError: nobody has seen this"}):
            self._run("ann", status=status)
        found = self._funnel()
        self.assertEqual(found.failures, [("provider_unreachable", 3), ("quality_checks", 1), ("unknown", 1)])
        self.assertNotIn("nobody has seen", json.dumps(found.failures))

    def test_trial_assessments_are_counted_by_their_marker(self):
        self._account("ann")
        self._run("ann", trial=False)
        self._run("ann", trial=False, status=FAILED_QUALITY)
        self._run("ann", trial=True, status=FAILED_UNREACHABLE)     # given back
        self._run("ann")                                            # on the account's own keys
        found = self._funnel()
        self.assertEqual((found.trial_started, found.trial_completed, found.trial_given_back), (3, 1, 1))


class WhatIsNotThereTests(_Case):
    def test_the_oldest_run_still_kept_is_said(self):
        self.assertIsNone(self._funnel().runs_kept_since)
        self._account("ann")
        self._run("ann", days_ago=2)
        oldest = self._run("ann", days_ago=20)
        found = self._funnel(7)
        self.assertEqual(found.runs_kept_since, int((NOW - timedelta(days=20)).timestamp()),
                         "of everything kept, not only of the window: it says how far back any number can reach")
        self.assertTrue(oldest.name.startswith(f"{NOW - timedelta(days=20):%Y%m%d}"))

    def test_a_run_that_cannot_be_read_is_counted_as_that_and_nothing_else(self):
        self._account("ann")
        self._run("ann")
        with patch.object(runs, "get_state", side_effect=[runs.RunNotFound("gone"), {"state": "completed"}]):
            self._run("ann")
            found = self._funnel()
        self.assertEqual(found.unreadable, 1)
        self.assertEqual(found.runs["started"], 1)

    def test_an_owner_marker_that_cannot_be_read_belongs_to_nobody_here(self):
        self._account("ann")
        run_dir = self._run("ann")
        with patch.object(runs, "owner_of", side_effect=runs.OwnerMarkerUnreadable(run_dir.name)):
            found = self._funnel()
        self.assertEqual((found.accounts_ran, found.unreadable), (0, 1))

    def test_no_accounts_and_no_runs_is_zeros_not_an_error(self):
        found = self._funnel()
        self.assertEqual((found.accounts_created, found.runs["started"], found.failures, found.trial_started),
                         (0, 0, [], 0))


class EndpointTests(_Case):
    def setUp(self):
        super().setUp()
        self.client = TestClient(app)
        self._account("ops", admin=True)
        self._account("ann")
        self._run("ann", status=FAILED_UNREACHABLE)
        self.tokens = {name: self.client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).json()["token"]
                       for name, email in (("ops", ADMIN), ("ann", "ann@example.com"))}

    def tearDown(self):
        self.client.close()
        super().tearDown()

    def _as(self, name):
        return {"Authorization": f"Bearer {self.tokens[name]}"}

    def test_only_an_admin_account_gets_anything_but_404(self):
        self.assertEqual(self.client.get("/api/admin/funnel").status_code, 401)
        self.assertEqual(self.client.get("/api/admin/funnel", headers=self._as("ann")).status_code, 404)
        with patch.object(access, "ACCESS_CODE", "a-code"), patch.object(access, "ADMIN_CODE", "the-admin-code"):
            self.assertEqual(self.client.get("/api/admin/funnel", headers={"X-Access-Code": "the-admin-code"}).status_code, 404)
        self.assertEqual(self.client.get("/api/admin/funnel", headers=self._as("ops")).status_code, 200)

    def test_the_answer_is_counts_and_no_address(self):
        answer = self.client.get("/api/admin/funnel?days=7", headers=self._as("ops"))
        self.assertEqual(answer.status_code, 200, answer.text)
        body = answer.json()
        self.assertEqual(body["window_days"], 7)
        self.assertEqual(body["accounts"], {"created": 1, "verified": 1, "ran": 1, "completed": 0})
        self.assertEqual(body["runs"]["failed"], 1)
        self.assertEqual(body["failures"], [{"code": "provider_unreachable", "runs": 1}])
        self.assertEqual(body["trial"], {"started": 0, "completed": 0, "given_back": 0})
        self.assertNotIn("@", answer.text)

    def test_thirty_days_unless_asked_and_only_a_sensible_window(self):
        self.assertEqual(self.client.get("/api/admin/funnel", headers=self._as("ops")).json()["window_days"], 30)
        for bad in ("0", "-1", "366", "soon"):
            with self.subTest(days=bad):
                self.assertEqual(self.client.get(f"/api/admin/funnel?days={bad}", headers=self._as("ops")).status_code, 422)

    def test_the_account_list_says_who_used_a_trial(self):
        self._sql("UPDATE users SET trial_used = 1 WHERE id = ?", self.ids["ann"])
        rows = {row["email"]: row for row in self.client.get("/api/admin/accounts", headers=self._as("ops")).json()["accounts"]}
        self.assertEqual((rows["ann@example.com"]["trial_used"], rows[ADMIN]["trial_used"]), (1, 0))


class PageTests(unittest.TestCase):
    def test_the_console_shows_the_funnel(self):
        page = (_ROOT / "web" / "admin.html").read_text(encoding="utf-8")
        for needle in ('id="funnel-rows"', 'id="funnel-days"', 'id="funnel-note"'):
            self.assertIn(needle, page)
        script = (_ROOT / "web" / "static" / "js" / "admin.js").read_text(encoding="utf-8")
        self.assertIn("api.adminFunnel(", script)
        self.assertIn("function paintFunnel()", script)
        client = (_ROOT / "web" / "static" / "js" / "api.js").read_text(encoding="utf-8")
        self.assertIn("export const adminFunnel = (days) =>", client)

    def test_the_guide_says_what_the_numbers_are_and_are_not(self):
        guide = (_ROOT / "docs" / "operating-guide.md").read_text(encoding="utf-8")
        self.assertIn("/api/admin/funnel", guide)
        self.assertIn("administrators are counted apart", guide)


if __name__ == "__main__":
    unittest.main()
