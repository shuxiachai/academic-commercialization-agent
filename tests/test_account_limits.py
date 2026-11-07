"""What one account may do at once, and in a day.

An account pays for its own tokens, so the deployment's budget never applied
to it, and nothing else did either: one account could hold every concurrent
slot, and a script behind one could run all day. Two caps of the account's
own now apply, counted the way the code caps are counted. These tests drive
them over HTTP with a worker that never exits until told to.
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import access, runs
from api.main import app

PASSWORD = "a sufficiently long password"
BYOK = {"llm_provider": "deepseek", "llm_api_key": "k", "llm_model": "deepseek-chat", "tavily_api_key": "t"}
_ROOT = Path(__file__).resolve().parents[1]


class _Worker:
    """A subprocess that runs until the test ends it."""

    exited: set[int] = set()
    created = 0

    def __init__(self, *args, **kwargs):
        _Worker.created += 1
        self.number = _Worker.created

    def poll(self):
        return 0 if self.number in _Worker.exited else None

    def terminate(self):
        _Worker.exited.add(self.number)

    def kill(self):
        _Worker.exited.add(self.number)

    def wait(self, timeout=None):
        return 0


class _Limits(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        root = Path(self._tmp.name)
        self._env = patch.dict("os.environ", {"ACCOUNTS_DB": str(root / "accounts.sqlite3")})
        self._env.start()
        for name in ("ACCOUNTS_SIGNUP", "ACCOUNTS_ADMIN_EMAILS"):
            os.environ.pop(name, None)
        runs._registry.clear()
        _Worker.exited, _Worker.created = set(), 0
        self._patches = [
            patch.object(runs, "DEFAULT_OUTPUT_ROOT", root / "outputs"),
            patch.object(runs, "MAX_CONCURRENT", 5), patch.object(runs, "BYOK_MAX_CONCURRENT", None),
            patch.object(runs, "DAILY_CAP", 0), patch.object(runs, "_daily_counts", {}), patch.object(runs, "_daily_date", None),
            patch.object(runs, "_inline_paid_operations", {}), patch.object(runs, "_inline_owners", {}),
            patch.object(runs, "_stop_claims", {}),
            patch.object(runs, "ACCOUNT_MAX_CONCURRENT", 1), patch.object(runs, "ACCOUNT_DAILY_CAP", 3),
            patch.object(access, "ACCESS_CODE", None), patch.object(access, "ACCESS_CODES", None),
            patch("api.runs.subprocess.Popen", _Worker),
        ]
        for item in self._patches:
            item.start()
        (root / "outputs").mkdir()
        self.client = TestClient(app)
        self.tokens = {}
        for email in ("alice@example.com", "bob@example.com"):
            response = self.client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
            self.assertEqual(response.status_code, 201, response.text)
            self.tokens[email] = response.json()["token"]

    def tearDown(self):
        self.client.close()
        for handle in list(runs._registry.values()):
            if handle.log_file is not None:
                handle.log_file.close()
        runs._registry.clear()
        for item in reversed(self._patches):
            item.stop()
        self._env.stop()
        self._tmp.cleanup()

    def _as(self, email):
        return {"Authorization": f"Bearer {self.tokens[email]}"}

    def _start(self, email="alice@example.com", **extra):
        return self.client.post("/api/runs", json={"topic": "a valid research topic", **BYOK}, headers=self._as(email), **extra)

    def _quota(self, email="alice@example.com"):
        return self.client.get("/api/quota", headers=self._as(email)).json()

    @staticmethod
    def _finish_every_worker():
        _Worker.exited.update(range(1, _Worker.created + 1))


class OneAtATimeTests(_Limits):
    def test_an_account_may_have_one_assessment_going_and_another_account_is_not_affected(self):
        first = self._start()
        self.assertEqual(first.status_code, 202, first.text)
        second = self._start()
        self.assertEqual((second.status_code, second.headers["X-Error-Code"]), (429, "account_busy"))
        self.assertIn("1 at a time", second.json()["detail"])
        self.assertIn("Wait for it to finish, or cancel it", second.json()["detail"])
        # The global capacity was not the reason: another account starts at once.
        self.assertEqual(self._start("bob@example.com").status_code, 202)
        # Once the first run ends, the account may start again.
        self._finish_every_worker()
        self.assertEqual(self._start().status_code, 202)

    def test_cancelling_the_running_assessment_frees_the_account(self):
        run_id = self._start().json()["run_id"]
        self.assertEqual(self._start().status_code, 429)
        cancelled = self.client.delete(f"/api/runs/{run_id}?intent=cancel", headers=self._as("alice@example.com"))
        self.assertIn(cancelled.status_code, (200, 202, 204), cancelled.text)
        self.assertEqual(self._start().status_code, 202)

    def test_a_pdf_extraction_counts_as_the_accounts_one_operation(self):
        alice = runs.accounts.owner_tag(1)
        with runs.reserve_inline_paid_operation(owner=alice, byok=True):
            refused = self._start()
            self.assertEqual((refused.status_code, refused.headers["X-Error-Code"]), (429, "account_busy"))
            # Bob's extraction is Bob's.
            self.assertEqual(self._start("bob@example.com").status_code, 202)
        self.assertEqual(self._start().status_code, 202)
        self.assertEqual(self._quota()["used"], 2, "the extraction and the run each used one")

    def test_the_cap_is_a_setting_and_zero_turns_it_off(self):
        with patch.object(runs, "ACCOUNT_MAX_CONCURRENT", 2):
            self.assertEqual(self._start().status_code, 202)
            self.assertEqual(self._start().status_code, 202)
            self.assertEqual(self._start().status_code, 429)
        self._finish_every_worker()
        with patch.object(runs, "ACCOUNT_MAX_CONCURRENT", 0), patch.object(runs, "ACCOUNT_DAILY_CAP", 0):
            for _ in range(4):
                self.assertEqual(self._start().status_code, 202)
            # The host's own cap still stands.
            fifth = self._start()
            self.assertEqual((fifth.status_code, fifth.headers["X-Error-Code"]), (429, "concurrency_limit"))

    def test_an_admin_account_is_not_exempt(self):
        with patch.dict("os.environ", {"ACCOUNTS_ADMIN_EMAILS": "alice@example.com"}):
            self.assertEqual(self._start().status_code, 202)
            self.assertEqual(self._start().headers.get("X-Error-Code"), "account_busy")

    def test_a_visitor_on_their_own_keys_without_an_account_is_not_an_account(self):
        # Where a deployment admits them (no codes, no accounts), there is no
        # identity to count against: only the host's BYOK share applies.
        held = []
        try:
            for _ in range(4):
                reservation = runs.reserve_inline_paid_operation(owner=None, byok=True)
                reservation.__enter__()
                held.append(reservation)
            with self.assertRaises(runs.ConcurrencyLimitReached) as refused:
                with runs.reserve_inline_paid_operation(owner=None, byok=True):
                    pass
            self.assertNotIsInstance(refused.exception, runs.AccountBusy)
        finally:
            for reservation in held:
                reservation.__exit__(None, None, None)
        self.assertIsNone(runs.daily_quota(None))
        self.assertEqual(runs.daily_cap_for(None), 0)


class PerDayTests(_Limits):
    def test_an_account_has_its_own_allowance_shown_before_and_counted_after(self):
        self.assertEqual({k: self._quota()[k] for k in ("limit", "used", "remaining")}, {"limit": 3, "used": 0, "remaining": 3})
        for used in (1, 2, 3):
            self.assertEqual(self._start().status_code, 202)
            self._finish_every_worker()
            self.assertEqual((self._quota()["used"], self._quota()["remaining"]), (used, 3 - used))
        refused = self._start()
        self.assertEqual((refused.status_code, refused.headers["X-Error-Code"]), (429, "account_daily_quota_exceeded"))
        self.assertIn("resets at 00:00 UTC", refused.json()["detail"])
        # Bob's day is Bob's.
        self.assertEqual(self._quota("bob@example.com")["used"], 0)
        self.assertEqual(self._start("bob@example.com").status_code, 202)

    def test_the_count_survives_a_restart_because_it_is_in_the_ledger(self):
        self.assertEqual(self._start().status_code, 202)
        ledger = json.loads((runs.DEFAULT_OUTPUT_ROOT / ".paid-operation-ledger.json").read_text(encoding="utf-8"))
        self.assertIn(runs.accounts.owner_tag(1), json.dumps(ledger))
        # A new process reads the file, not its memory.
        with patch.object(runs, "_daily_counts", {}), patch.object(runs, "_daily_date", None):
            self.assertEqual(self._quota()["used"], 1)

    def test_a_launch_that_fails_before_the_worker_exists_is_refunded(self):
        with patch("api.runs.subprocess.Popen", side_effect=OSError("no interpreter")):
            failed = self._start()
        self.assertGreaterEqual(failed.status_code, 500)
        self.assertEqual(self._quota()["used"], 0)
        self.assertEqual(self._start().status_code, 202, "and the account is not left busy")

    def test_the_operator_budget_and_the_account_allowance_are_separate_numbers(self):
        with patch.object(runs, "DAILY_CAP", 7), patch.object(access, "ACCESS_CODE", "code-1"):
            by_code = self.client.get("/api/quota", headers={"X-Access-Code": "code-1"}).json()
            self.assertEqual(by_code["limit"], 7)
            self.assertEqual(self._quota()["limit"], 3)
            # Neither cap is told about the other's operations.
            self.assertEqual(self._start().status_code, 202)
            self.assertEqual(self.client.get("/api/quota", headers={"X-Access-Code": "code-1"}).json()["used"], 0)
        with patch.object(runs, "ACCOUNT_DAILY_CAP", 0):
            self.assertIsNone(self._quota())


class ThePageTests(unittest.TestCase):
    def test_the_sign_in_answer_carries_the_flag_and_the_page_asks_for_the_allowance(self):
        app_js = (_ROOT / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("quotaEnabled = authConfig?.daily_quota === true;", app_js)
        self.assertIn("if (!quotaEnabled || (byokMode && !accountMode)) {", app_js)
        for code in ("account_busy", "account_daily_quota_exceeded"):
            self.assertIn(f"{code}: \"msg_", app_js)
        strings = (_ROOT / "web" / "static" / "js" / "i18n.js").read_text(encoding="utf-8")
        for key in ("msg_account_busy", "msg_account_daily_quota"):
            self.assertEqual(strings.count(f"    {key}: "), 2, key)


if __name__ == "__main__":
    unittest.main()
