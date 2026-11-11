"""A verified account's first assessment may run on the deployment's own keys.

Since 2026-11-07 anyone may sign up, and an account pays with its own keys:
before its first run a newcomer has to obtain a model key and a search key
from two other services. The sample reports show what a run produces; they
do not show it on the visitor's own question. This is the measure that
bridges that step: an operator who chooses to (ACCOUNTS_TRIAL_RUNS, off by
default) lets each verified account start a set number of assessments
without keys, on the path an administrator's runs already take (#359).

What the tests hold onto is the bill. The deployment pays, so every way to
spend a trial is counted and bounded: once per account, a deployment-wide
number a day, a full assessment only (not a resume, not a PDF upload), an
address that has been proven, and nothing at all unless the deployment has
keys to pay with. A trial that never started, or that failed because the
provider could not be reached, is given back.
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

from academic_agent.language import TopicSearchPlan
from academic_agent.run_terminal import TerminalRecord, UsageAccounting, commit_terminal_record
from api import access, accounts, main, plan_preview, runs
from api.main import app

PASSWORD = "a sufficiently long password"
ADMIN, ALICE, BOB = "admin@example.com", "alice@example.com", "bob@example.com"
INVITE = "invite-for-admins"
BYOK = {"llm_provider": "deepseek", "llm_api_key": "k", "llm_model": "deepseek-chat", "tavily_api_key": "t"}
OPERATOR_KEYS = {"LLM_PROVIDER": "qwen", "DASHSCOPE_API_KEY": "operator-model-key", "QWEN_MODEL": "qwen3.5-plus",
                 "SERPER_API_KEY": "operator-search-key"}
STARTED = ("20260101T000000Z-0123456789", Path("."))
_ROOT = Path(__file__).resolve().parents[1]


class _Case(unittest.TestCase):
    """Accounts on, operator keys set, one trial each unless a test says otherwise."""

    extra_env: dict = {**OPERATOR_KEYS, "ACCOUNTS_TRIAL_RUNS": "1"}

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        env = {"ACCOUNTS_DB": str(self.root / "accounts.sqlite3"), "ACCOUNTS_ADMIN_EMAILS": ADMIN,
               "ACCOUNTS_SIGNUP": "open", "ACCOUNTS_INVITE_CODE": INVITE, **self.extra_env}
        self._env = patch.dict("os.environ", env)
        self._env.start()
        for name in ("ACCOUNTS_ADMIN_FUNDED", "ACCOUNTS_TRIAL_RUNS", "ACCOUNTS_TRIAL_DAILY", "TAVILY_API_KEY",
                     "MAIL_OUTBOX", "MAIL_RESEND_API_KEY"):
            if name not in env:
                os.environ.pop(name, None)
        self.outputs = self.root / "outputs"
        self.outputs.mkdir()
        self._patches = [patch.object(access, "ACCESS_CODE", None), patch.object(access, "ACCESS_CODES", None),
                         patch.object(runs, "DEFAULT_OUTPUT_ROOT", self.outputs)]
        for item in self._patches:
            item.start()
        self.client = TestClient(app)
        self.tokens = {}
        for email, invite in ((ADMIN, INVITE), (ALICE, None), (BOB, None)):
            body = {"email": email, "password": PASSWORD, **({"invite": invite} if invite else {})}
            response = self.client.post("/api/auth/register", json=body)
            self.assertEqual(response.status_code, 201, response.text)
            self.tokens[email] = response.json()["token"]

    def tearDown(self):
        self.client.close()
        for item in self._patches:
            item.stop()
        self._env.stop()
        self._tmp.cleanup()

    def _bearer(self, email):
        return {"Authorization": f"Bearer {self.tokens[email]}"}

    def _run(self, email, headers=None, **extra):
        return self.client.post("/api/runs", json={"topic": "a valid research topic", **extra},
                                headers={**self._bearer(email), **(headers or {})})

    def _left(self, email):
        return self.client.get("/api/access/check", headers=self._bearer(email)).json()["account"]["trial_runs_left"]

    def _user(self, email):
        return accounts.session_user(self.tokens[email])

    def _sql(self, statement, *values):
        # Closed explicitly: sqlite3's own context manager only commits, and an
        # open handle keeps the temporary directory from being removed on Windows.
        db = sqlite3.connect(os.environ["ACCOUNTS_DB"])
        try:
            db.execute(statement, values)
            db.commit()
        finally:
            db.close()


class TrialRunTests(_Case):
    def test_a_verified_account_starts_its_first_assessment_without_keys(self):
        self.assertEqual(self._left(ALICE), 1)
        with patch.object(runs, "start_run", return_value=STARTED) as started:
            response = self._run(ALICE)
        self.assertEqual(response.status_code, 202, response.text)
        kwargs = started.call_args.kwargs
        self.assertIsNone(kwargs["byok"], "no keys of the account's own: the deployment's are used")
        self.assertEqual(kwargs["owner"], self._user(ALICE).owner, "still the account's run")
        self.assertEqual(self._left(ALICE), 0)

    def test_the_second_one_needs_keys_as_every_run_did_before(self):
        with patch.object(runs, "start_run", return_value=STARTED) as started:
            self.assertEqual(self._run(ALICE).status_code, 202)
            refused = self._run(ALICE)
            self.assertEqual((refused.status_code, refused.headers["X-Error-Code"]), (401, "byok_required"))
            self.assertEqual(started.call_count, 1)
            self.assertEqual(self._run(ALICE, **BYOK).status_code, 202, "with keys it is the account's own run")

    def test_a_run_on_the_accounts_own_keys_does_not_spend_the_trial(self):
        with patch.object(runs, "start_run", return_value=STARTED) as started:
            self.assertEqual(self._run(ALICE, **BYOK).status_code, 202)
        self.assertEqual(started.call_args.kwargs["byok"].llm_api_key, "k")
        self.assertEqual(self._left(ALICE), 1)

    def test_an_administrator_the_deployment_funds_spends_none(self):
        with patch.object(runs, "start_run", return_value=STARTED):
            for _ in range(3):
                self.assertEqual(self._run(ADMIN).status_code, 202)
        self.assertEqual(accounts.trial_left(self._user(ADMIN)), 1)

    def test_more_than_one_is_the_operators_number(self):
        with patch.dict("os.environ", {"ACCOUNTS_TRIAL_RUNS": "2"}), patch.object(runs, "start_run", return_value=STARTED):
            self.assertEqual(self._left(ALICE), 2)
            self.assertEqual(self._run(ALICE).status_code, 202)
            self.assertEqual(self._run(ALICE).status_code, 202)
            self.assertEqual(self._run(ALICE).status_code, 401)


class WhatItTakesTests(_Case):
    def test_it_is_off_unless_the_operator_turns_it_on(self):
        os.environ.pop("ACCOUNTS_TRIAL_RUNS")
        self.assertEqual(accounts.trial_runs(), 0)
        self.assertEqual(self._left(ALICE), 0)
        with patch.object(runs, "start_run") as started:
            response = self._run(ALICE)
        self.assertEqual((response.status_code, response.headers["X-Error-Code"]), (401, "byok_required"))
        started.assert_not_called()
        self.assertEqual(self.client.get("/api/auth/config").json()["trial_runs"], 0)

    def test_a_number_that_is_not_one_is_off(self):
        for raw in ("", "many", "-3", "1.5"):
            with self.subTest(raw=raw), patch.dict("os.environ", {"ACCOUNTS_TRIAL_RUNS": raw}):
                self.assertEqual(accounts.trial_runs(), 0)

    def test_the_deployment_must_have_both_keys_to_pay_with(self):
        for missing in ("DASHSCOPE_API_KEY", "SERPER_API_KEY"):
            with self.subTest(missing=missing), patch.dict("os.environ", {}):
                os.environ.pop(missing)
                self.assertEqual(self._left(ALICE), 0)
                with patch.object(runs, "start_run") as started:
                    response = self._run(ALICE)
                self.assertEqual((response.status_code, response.headers["X-Error-Code"]), (401, "byok_required"))
                started.assert_not_called()
                self.assertEqual(self.client.get("/api/auth/config").json()["trial_runs"], 0)
        self.assertEqual(self.client.get("/api/auth/config").json()["trial_runs"], 1)

    def test_an_address_that_has_not_been_proven_waits(self):
        with patch.dict("os.environ", {"MAIL_OUTBOX": str(self.root / "outbox"),
                                       "MAIL_FROM": "ACA <noreply@example.com>", "PUBLIC_URL": "https://aca.example.com"}):
            from api import mail
            mail.reset()
            try:
                created = self.client.post("/api/auth/register", json={"email": "carol@example.com", "password": PASSWORD})
                self.assertEqual(created.status_code, 201, created.text)
                self.assertFalse(created.json()["verified"])
                self.assertEqual(created.json()["trial_runs_left"], 0, "nothing to spend until the address is proven")
                with patch.object(runs, "start_run") as started:
                    response = self.client.post("/api/runs", json={"topic": "a valid research topic"},
                                                headers={"Authorization": f"Bearer {created.json()['token']}"})
                self.assertEqual((response.status_code, response.headers["X-Error-Code"]), (403, "email_unverified"))
                started.assert_not_called()
                accounts.mark_verified("carol@example.com")
                self.assertEqual(accounts.trial_left(accounts.session_user(created.json()["token"])), 1)
            finally:
                mail.reset()

    def test_only_a_full_assessment_not_a_resume_or_an_upload(self):
        owner = self._user(ALICE).owner
        failed = self.outputs / ("20260101T000001Z-" + "c" * 32)
        failed.mkdir()
        (failed / ".owner").write_text(owner, encoding="utf-8")
        (failed / "status.json").write_text(json.dumps({"done": True, "error": "boom"}), encoding="utf-8")
        with patch.object(runs, "resume_run") as resumed:
            response = self.client.post(f"/api/runs/{failed.name}/resume", json={}, headers=self._bearer(ALICE))
        self.assertEqual((response.status_code, response.headers.get("X-Error-Code")), (401, "byok_required"))
        resumed.assert_not_called()
        upload = self.client.post("/api/papers", files={"file": ("p.pdf", b"%PDF-1.4 x", "application/pdf")},
                                  headers=self._bearer(ALICE))
        self.assertEqual((upload.status_code, upload.headers.get("X-Error-Code")), (401, "byok_required"))
        self.assertEqual(self._left(ALICE), 1, "neither spent it")


class BoundTests(_Case):
    def test_the_deployment_gives_a_set_number_a_day_across_all_accounts(self):
        with patch.dict("os.environ", {"ACCOUNTS_TRIAL_DAILY": "1"}), patch.object(runs, "start_run", return_value=STARTED) as started:
            self.assertEqual(self._run(ALICE).status_code, 202)
            refused = self._run(BOB)
            self.assertEqual((refused.status_code, refused.headers["X-Error-Code"]), (429, "trial_daily_exhausted"))
            self.assertEqual(started.call_count, 1)
            self.assertEqual(self._left(BOB), 1, "Bob's is not spent: it waits for tomorrow")

    def test_the_daily_number_starts_again_with_the_utc_day(self):
        with patch.dict("os.environ", {"ACCOUNTS_TRIAL_DAILY": "1"}):
            now = datetime(2026, 11, 11, 23, 0, tzinfo=UTC).timestamp()
            accounts.claim_trial(self._user(ALICE), now=now)
            with self.assertRaises(accounts.AccountError) as refused:
                accounts.claim_trial(self._user(BOB), now=now + 60)
            self.assertEqual(refused.exception.code, "trial_daily_exhausted")
            claim = accounts.claim_trial(self._user(BOB), now=now + 3 * 3600)
            self.assertEqual(claim.day, "2026-11-12")

    def test_twenty_a_day_unless_the_operator_says_otherwise(self):
        self.assertEqual(accounts.trial_daily_cap(), 20)
        with patch.dict("os.environ", {"ACCOUNTS_TRIAL_DAILY": "0"}):
            self.assertEqual(accounts.trial_daily_cap(), 0, "0 turns the daily bound off, as for the other caps")
            accounts.claim_trial(self._user(ALICE))
            accounts.claim_trial(self._user(BOB))
        with patch.dict("os.environ", {"ACCOUNTS_TRIAL_DAILY": "soon"}):
            self.assertEqual(accounts.trial_daily_cap(), 20)

    def test_the_claim_itself_refuses_an_unproven_or_disabled_account(self):
        """The request path checks first; the claim does not rely on it."""
        user = self._user(BOB)
        self._sql("UPDATE users SET verified_at = NULL WHERE id = ?", user.id)
        with self.assertRaises(accounts.AccountError) as refused:
            accounts.claim_trial(user)
        self.assertEqual(refused.exception.code, "email_unverified")
        self.assertEqual(accounts.trial_left(accounts.User(id=user.id, email=BOB, verified=False)), 0)
        self._sql("UPDATE users SET verified_at = 1, disabled = 1 WHERE id = ?", user.id)
        with self.assertRaises(accounts.AccountError) as refused:
            accounts.claim_trial(user)
        self.assertEqual(refused.exception.code, "trial_used")
        self.assertEqual(accounts.trial_left(user), 0)

    def test_a_claim_is_refused_once_the_account_has_had_its_number(self):
        accounts.claim_trial(self._user(ALICE))
        with self.assertRaises(accounts.AccountError) as refused:
            accounts.claim_trial(self._user(ALICE))
        self.assertEqual(refused.exception.code, "trial_used")


class GivenBackTests(_Case):
    def test_a_run_that_never_started_does_not_spend_it(self):
        for failure, status in ((OSError("no interpreter"), 500),
                                (runs.DailyCapReached("Daily limit reached"), 429),
                                (runs.ConcurrencyLimitReached("5 of 5"), 429),
                                (runs.PaidLedgerUnavailable("disk"), 503)):
            with self.subTest(failure=type(failure).__name__), patch.object(runs, "start_run", side_effect=failure):
                self.assertEqual(self._run(ALICE).status_code, status)
                self.assertEqual(self._left(ALICE), 1)
        with patch.dict("os.environ", {"ACCOUNTS_TRIAL_DAILY": "1"}), patch.object(runs, "start_run", return_value=STARTED):
            self.assertEqual(self._run(BOB).status_code, 202, "and the day's number was given back with it")

    def test_releasing_never_goes_below_nothing(self):
        claim = accounts.claim_trial(self._user(ALICE))
        accounts.release_trial(claim)
        accounts.release_trial(claim)
        self.assertEqual(accounts.trial_left(self._user(ALICE)), 1)
        with patch.dict("os.environ", {"ACCOUNTS_TRIAL_DAILY": "1"}):
            accounts.claim_trial(self._user(BOB))
            with self.assertRaises(accounts.AccountError):
                accounts.claim_trial(self._user(ALICE))



class _Process:
    """A worker the test ends when it chooses."""

    ended = False

    def __init__(self, *args, **kwargs):
        pass

    def poll(self):
        return 1 if _Process.ended else None

    def terminate(self):
        _Process.ended = True

    def kill(self):
        _Process.ended = True

    def wait(self, timeout=None):
        return 1


class RealLaunchTests(_Case):
    """Through runs.start_run, with only the subprocess replaced."""

    def setUp(self):
        super().setUp()
        _Process.ended = False
        more = [patch.object(runs, "MAX_CONCURRENT", 5), patch.object(runs, "BYOK_MAX_CONCURRENT", None),
                patch.object(runs, "DAILY_CAP", 0), patch.object(runs, "ACCOUNT_DAILY_CAP", 10),
                patch.object(runs, "ACCOUNT_MAX_CONCURRENT", 1),
                patch.object(runs, "_daily_counts", {}), patch.object(runs, "_daily_date", None),
                patch.object(runs, "_registry", {}), patch.object(runs, "_stop_claims", {}),
                patch.object(runs, "_inline_paid_operations", {}), patch.object(runs, "_inline_owners", {}),
                patch.object(runs, "_unreachable_refunds", {}), patch.object(runs, "_unreachable_refund_date", None),
                patch("api.runs.subprocess.Popen", _Process)]
        for item in more:
            item.start()
        self._patches.extend(more)

    def tearDown(self):
        # A worker still "running" holds its log file open; end it and reap,
        # or the directory cannot be removed on Windows.
        _Process.ended = True
        runs.active_count()
        super().tearDown()

    def _end_as_failed(self, run_id, error):
        run_dir = self.outputs / run_id
        (run_dir / "status.json").write_text(json.dumps({"stage": "Error", "done": True, "error": error}), encoding="utf-8")
        now = datetime.now(UTC)
        commit_terminal_record(run_dir, TerminalRecord(
            state="failed", reason_code="worker_exception", termination_method="worker_exit",
            started_at=now - timedelta(seconds=300), ended_at=now, elapsed_seconds=300, last_stage="Agent 4",
            timeout_seconds=1800, usage=None,
            usage_accounting=UsageAccounting(state="lower_bound", snapshot_at=now, through_stage="Agent 4",
                                             run_complete=False, in_flight_request_may_have_spent=True)))
        _Process.ended = True
        runs.active_count()

    def test_the_run_remembers_that_the_deployment_paid_and_that_it_was_a_trial(self):
        response = self._run(ALICE)
        self.assertEqual(response.status_code, 202, response.text)
        run_dir = self.outputs / response.json()["run_id"]
        self.assertEqual((run_dir / ".funded").read_text(encoding="utf-8"), "deployment")
        trial = json.loads((run_dir / ".trial").read_text(encoding="utf-8"))
        self.assertEqual(trial["user_id"], self._user(ALICE).id)
        self.assertEqual(runs.get_state(run_dir.name)["funded_by"], "deployment",
                         "a failure is worded for the operator, not for keys the visitor never had")

    def test_a_trial_lost_to_an_unreachable_provider_is_given_back(self):
        """2026-11-11: 28 of 61 attempts did not return on the mainland
        endpoint. A newcomer's one assessment must not be what that costs."""
        run_id = self._run(ALICE).json()["run_id"]
        self.assertEqual(self._left(ALICE), 0)
        self._end_as_failed(run_id, "Connection error.")
        self.assertEqual(runs.get_state(run_id)["daily_charge_reason"], "provider_unreachable")
        self.assertEqual(self._left(ALICE), 1)
        # Seen again, it is not given back twice: the account spends it on
        # something else, and the old run's marker must not undo that.
        accounts.claim_trial(self._user(ALICE))
        with runs._registry_lock:
            self.assertFalse(runs._release_trial_locked(self.outputs / run_id))
        self.assertEqual(self._left(ALICE), 0)
        self.assertTrue(json.loads((self.outputs / run_id / ".trial").read_text(encoding="utf-8"))["released"])

    def test_the_same_request_sent_twice_is_answered_as_it_was_and_spends_one(self):
        """The page resends a paid request it got no answer to, with the same
        key. By then the trial is spent; the saved receipt must still answer."""
        key = {"Idempotency-Key": f"v1.{int(datetime.now(UTC).timestamp()):010d}.{'a' * 64}"}
        first = self._run(ALICE, headers=key)
        again = self._run(ALICE, headers=key)
        self.assertEqual((first.status_code, again.status_code), (202, 202), again.text)
        self.assertEqual(again.headers.get("Idempotency-Replayed"), "true")
        self.assertEqual(again.json()["run_id"], first.json()["run_id"])
        self.assertEqual(self._left(ALICE), 0)
        self.assertEqual(len([p for p in self.outputs.iterdir() if (p / ".trial").exists()]), 1)
        # A new request, with a new key, is the second run and needs keys.
        other = {"Idempotency-Key": f"v1.{int(datetime.now(UTC).timestamp()):010d}.{'b' * 64}"}
        refused = self._run(ALICE, headers=other)
        self.assertEqual((refused.status_code, refused.headers["X-Error-Code"]), (401, "byok_required"))
        replayed = self._run(ALICE, headers=other)
        self.assertEqual((replayed.status_code, replayed.headers.get("X-Error-Code")), (401, "byok_required"),
                         "and its refusal replays as a refusal, not as an unreadable receipt")

    def test_a_trial_that_failed_for_any_other_reason_is_spent(self):
        run_id = self._run(ALICE).json()["run_id"]
        self._end_as_failed(run_id, "Guardrail failed: blocking validation errors")
        self.assertEqual(runs.get_state(run_id)["daily_charge"], "charged")
        self.assertEqual(self._left(ALICE), 0)

    def test_a_launch_that_fails_gives_it_back(self):
        with patch("api.runs.subprocess.Popen", side_effect=OSError("cannot spawn")):
            self.assertGreaterEqual(self._run(ALICE).status_code, 500)
        self.assertEqual(self._left(ALICE), 1)


class PreviewTests(_Case):
    def test_an_account_with_a_trial_left_previews_on_the_deployments_key(self):
        used = []

        def planner(topic, n=2, *, credentials=None):
            used.append(credentials)
            return TopicSearchPlan(search_topic="a valid research topic")

        with patch.object(plan_preview, "DAILY_LIMIT", 5), patch.object(plan_preview, "_counts", {}), \
                patch.object(plan_preview, "plan_topic_search", planner):
            ok = self.client.post("/api/plan", json={"topic": "a valid research topic"}, headers=self._bearer(ALICE))
            self.assertEqual(ok.status_code, 200, ok.text)
            self.assertEqual(used, [None])
            accounts.claim_trial(self._user(ALICE))
            refused = self.client.post("/api/plan", json={"topic": "a valid research topic"}, headers=self._bearer(ALICE))
            self.assertEqual((refused.status_code, refused.headers["X-Error-Code"]), (401, "byok_required"))


class WhatThePageIsToldTests(_Case):
    def test_every_answer_that_describes_the_account_says_how_many_are_left(self):
        login = self.client.post("/api/auth/login", json={"email": ALICE, "password": PASSWORD})
        self.assertEqual(login.json()["trial_runs_left"], 1)
        self.assertEqual(self.client.get("/api/auth/me", headers=self._bearer(ALICE)).json()["trial_runs_left"], 1)
        self.assertEqual(self._left(ALICE), 1)
        check = self.client.get("/api/access/check", headers=self._bearer(ALICE)).json()
        self.assertEqual(check["accounts"]["trial_runs"], 1)
        self.assertEqual(self.client.get("/api/auth/config").json()["trial_runs"], 1)
        self.assertEqual(self._left(ADMIN), 0, "an administrator the deployment funds has nothing to count down")
        accounts.claim_trial(self._user(ALICE))
        self.assertEqual(self.client.get("/api/auth/me", headers=self._bearer(ALICE)).json()["trial_runs_left"], 0)


class StorageTests(unittest.TestCase):
    def test_a_database_from_before_trials_gains_the_column_with_nothing_spent(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "accounts.sqlite3"
            db = sqlite3.connect(str(path))
            db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, "
                       "created_at INTEGER NOT NULL, disabled INTEGER NOT NULL DEFAULT 0, verified_at INTEGER, "
                       "notify_done INTEGER NOT NULL DEFAULT 0)")
            db.execute("INSERT INTO users (email, password_hash, created_at, verified_at) VALUES ('old@example.com', 'x', 1, 1)")
            db.commit()
            db.close()
            with patch.dict("os.environ", {"ACCOUNTS_DB": str(path), "ACCOUNTS_TRIAL_RUNS": "1"}):
                user = accounts.User(id=1, email="old@example.com")
                self.assertEqual(accounts.trial_left(user), 1, "an account that was here first gets one too")
                accounts.claim_trial(user)
                self.assertEqual(accounts.trial_left(user), 0)


class PageTests(unittest.TestCase):
    def test_the_page_lets_a_trial_start_without_keys_and_only_a_run(self):
        app_js = (_ROOT / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function trialPays()", app_js)
        self.assertIn("accountMode && accountVerified && accountTrialLeft > 0", app_js)
        self.assertIn('!operatorPays() && !(operation === "run" && trialPays())', app_js)
        self.assertEqual(app_js.count("accountTrialLeft = Number.isInteger(me.trial_runs_left) ? me.trial_runs_left : 0;"), 2,
                         "when the account is applied, and again once its address is proven")
        self.assertIn('trial_daily_exhausted: "msg_trial_daily_exhausted"', app_js)
        strings = (_ROOT / "web" / "static" / "js" / "i18n.js").read_text(encoding="utf-8")
        for key in ("trial_note", "byok_trial_note", "msg_trial_daily_exhausted"):
            self.assertEqual(strings.count(f"    {key}: "), 2, key)
        page = (_ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="trial-note"', page)

    def test_the_guide_and_the_example_environment_say_so(self):
        guide = (_ROOT / "docs" / "operating-guide.md").read_text(encoding="utf-8")
        for name in ("ACCOUNTS_TRIAL_RUNS", "ACCOUNTS_TRIAL_DAILY", "`.trial`"):
            self.assertIn(name, guide)
        env = (_ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("ACCOUNTS_TRIAL_RUNS", env)
        self.assertIn("ACCOUNTS_TRIAL_DAILY", env)


if __name__ == "__main__":
    unittest.main()
