"""An administrator's paid operations may run on the deployment's own keys.

Every account pays with its own keys, except an address named in
ACCOUNTS_ADMIN_EMAILS on a deployment that has a model key and a search key
and has not turned this off (ACCOUNTS_ADMIN_FUNDED=0). Such a request without
keys is admitted on the operator's keys, counted against the operator's daily
cap, tagged to the account, and the run remembers that the deployment paid so
a failure is worded for the operator. Everyone else is refused as before.
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from academic_agent.language import TopicSearchPlan
from api import access, accounts, main, plan_preview, runs
from api.main import app

PASSWORD = "a sufficiently long password"
ADMIN, ALICE = "admin@example.com", "alice@example.com"
INVITE = "invite-for-admins"
BYOK = {"llm_provider": "deepseek", "llm_api_key": "k", "llm_model": "deepseek-chat", "tavily_api_key": "t"}
OPERATOR_KEYS = {"LLM_PROVIDER": "qwen", "DASHSCOPE_API_KEY": "operator-model-key", "QWEN_MODEL": "qwen3.5-plus",
                 "SERPER_API_KEY": "operator-search-key"}
_ROOT = Path(__file__).resolve().parents[1]


class _Case(unittest.TestCase):
    """Accounts on, one administrator, and (unless a test says otherwise) operator keys set."""

    extra_env: dict = dict(OPERATOR_KEYS)

    def setUp(self):
        self._tmp = TemporaryDirectory()
        root = Path(self._tmp.name)
        env = {"ACCOUNTS_DB": str(root / "accounts.sqlite3"), "ACCOUNTS_ADMIN_EMAILS": ADMIN,
               "ACCOUNTS_SIGNUP": "open", "ACCOUNTS_INVITE_CODE": INVITE, **self.extra_env}
        self._env = patch.dict("os.environ", env)
        self._env.start()
        for name in ("ACCOUNTS_ADMIN_FUNDED", "TAVILY_API_KEY", "MAIL_OUTBOX", "MAIL_RESEND_API_KEY"):
            if name not in env:
                os.environ.pop(name, None)
        self._patches = [patch.object(access, "ACCESS_CODE", None), patch.object(access, "ACCESS_CODES", None),
                         patch.object(runs, "DEFAULT_OUTPUT_ROOT", root / "outputs")]
        for item in self._patches:
            item.start()
        (root / "outputs").mkdir()
        self.outputs = root / "outputs"
        self.client = TestClient(app)
        self.tokens = {}
        for email, invite in ((ADMIN, INVITE), (ALICE, None)):
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

    def _run(self, email, **extra):
        return self.client.post("/api/runs", json={"topic": "a valid research topic", **extra}, headers=self._bearer(email))


class FundingTests(_Case):
    def test_an_administrator_without_keys_runs_on_the_deployment(self):
        with patch.object(runs, "start_run", return_value=("20260101T000000Z-0123456789", Path("."))) as started:
            response = self._run(ADMIN)
        self.assertEqual(response.status_code, 202, response.text)
        kwargs = started.call_args.kwargs
        self.assertIsNone(kwargs["byok"], "no keys of the account's own: the operator's are used")
        self.assertEqual(kwargs["owner"], accounts.session_user(self.tokens[ADMIN]).owner, "still the account's run")

    def test_an_administrator_with_keys_still_uses_them(self):
        with patch.object(runs, "start_run", return_value=("20260101T000000Z-0123456789", Path("."))) as started:
            response = self._run(ADMIN, **BYOK)
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(started.call_args.kwargs["byok"].llm_api_key, "k")

    def test_everyone_else_still_brings_keys(self):
        with patch.object(runs, "start_run") as started:
            response = self._run(ALICE)
        self.assertEqual((response.status_code, response.headers["X-Error-Code"]), (401, "byok_required"))
        started.assert_not_called()
        self.assertFalse(self.client.get("/api/access/check", headers=self._bearer(ALICE)).json()["account"]["admin"])

    def test_the_switch_and_both_keys_are_all_needed(self):
        cases = (
            ("switch off", {"ACCOUNTS_ADMIN_FUNDED": "0"}, ()),
            ("no model key", {}, ("DASHSCOPE_API_KEY",)),
            ("no search key", {}, ("SERPER_API_KEY",)),
        )
        for name, extra, missing in cases:
            with self.subTest(name=name), patch.dict("os.environ", extra):
                for key in missing:
                    os.environ.pop(key, None)
                with patch.object(runs, "start_run") as started:
                    response = self._run(ADMIN)
                self.assertEqual((response.status_code, response.headers.get("X-Error-Code")), (401, "byok_required"))
                started.assert_not_called()
                self.assertFalse(self.client.get("/api/auth/config").json()["admin_funded"])
        self.assertTrue(self.client.get("/api/auth/config").json()["admin_funded"], "all three present again")
        self.assertTrue(self.client.get("/api/access/check", headers=self._bearer(ADMIN)).json()["accounts"]["admin_funded"])

    def test_the_switch_needs_named_administrators(self):
        with patch.dict("os.environ", {"ACCOUNTS_ADMIN_EMAILS": ""}):
            self.assertFalse(accounts.admin_funded())
            self.assertFalse(main._operator_funds_admins())

    def test_an_unverified_administrator_is_still_asked_to_verify_first(self):
        with patch.dict("os.environ", {"MAIL_OUTBOX": str(Path(self._tmp.name) / "outbox"),
                                       "MAIL_FROM": "ACA <noreply@example.com>", "PUBLIC_URL": "https://aca.example.com"}):
            from api import mail
            mail.reset()
            try:
                # A fresh administrator-named account created with mail on is unverified.
                with patch.dict("os.environ", {"ACCOUNTS_ADMIN_EMAILS": f"{ADMIN},second@example.com"}):
                    created = self.client.post("/api/auth/register", json={"email": "second@example.com", "password": PASSWORD, "invite": INVITE})
                    self.assertEqual(created.status_code, 201, created.text)
                    self.assertFalse(created.json()["verified"])
                    response = self.client.post("/api/runs", json={"topic": "a valid research topic"},
                                                headers={"Authorization": f"Bearer {created.json()['token']}"})
                    self.assertEqual((response.status_code, response.headers["X-Error-Code"]), (403, "email_unverified"))
            finally:
                mail.reset()

    def test_an_administrator_previews_on_the_operator_key_and_members_do_not(self):
        used = []

        def planner(topic, n=2, *, credentials=None):
            used.append(credentials)
            return TopicSearchPlan(search_topic="a valid research topic")

        with patch.object(plan_preview, "DAILY_LIMIT", 5), patch.object(plan_preview, "_counts", {}), \
                patch.object(plan_preview, "plan_topic_search", planner):
            ok = self.client.post("/api/plan", json={"topic": "a valid research topic"}, headers=self._bearer(ADMIN))
            self.assertEqual(ok.status_code, 200, ok.text)
            self.assertEqual(used, [None], "the operator's own planner configuration")
            refused = self.client.post("/api/plan", json={"topic": "a valid research topic"}, headers=self._bearer(ALICE))
            self.assertEqual((refused.status_code, refused.headers["X-Error-Code"]), (401, "byok_required"))
            self.assertEqual(used, [None])


class LedgerTests(_Case):
    def test_an_operator_funded_account_run_spends_the_operator_cap(self):
        owner = accounts.session_user(self.tokens[ADMIN]).owner
        with patch.object(runs, "DAILY_CAP", 1), patch.object(runs, "ACCOUNT_DAILY_CAP", 5), \
                patch.object(runs, "_daily_counts", {}), patch.object(runs, "_daily_date", None), \
                patch.object(runs, "MAX_CONCURRENT", 5), patch.object(runs, "ACCOUNT_MAX_CONCURRENT", 5):
            with runs._registry_lock:
                charged = runs._admit_paid_operation_locked(owner=owner, byok=False)
                self.assertIsNotNone(charged, "charged to the operator's day")
                with self.assertRaises(runs.DailyCapReached):
                    runs._admit_paid_operation_locked(owner=owner, byok=False)
            # The same account on its own keys is not held by the operator's cap.
            with runs._registry_lock:
                self.assertIsNotNone(runs._admit_paid_operation_locked(owner=owner, byok=True))


class FundingRecordTests(_Case):
    def _run_dir(self, name="20260101T000000Z-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"):
        run_dir = self.outputs / name
        run_dir.mkdir()
        return run_dir

    def test_the_marker_is_written_only_for_an_account_run_the_deployment_paid(self):
        cases = (("user:1", None, True), ("user:1", object(), False), ("code:abc", None, False), (None, None, False))
        for index, (owner, byok, expected) in enumerate(cases):
            with self.subTest(owner=owner, byok=byok is not None):
                run_dir = self._run_dir(f"20260101T00000{index}Z-" + "b" * 32)
                runs._record_funding(run_dir, owner=owner, byok=byok)
                self.assertEqual((run_dir / ".funded").exists(), expected)
                if expected:
                    self.assertEqual((run_dir / ".funded").read_text(encoding="utf-8"), "deployment")

    def test_the_wording_follows_the_marker(self):
        run_dir = self._run_dir()
        self.assertIsNone(runs._funded_by(run_dir), "no owner: nothing to say")
        (run_dir / ".owner").write_text("user:1", encoding="utf-8")
        self.assertEqual(runs._funded_by(run_dir), "own_keys", "an account's run, as before")
        runs._record_funding(run_dir, owner="user:1", byok=None)
        self.assertEqual(runs._funded_by(run_dir), "deployment", "...unless the deployment paid")
        (run_dir / ".funded").write_text("something else", encoding="utf-8")
        self.assertEqual(runs._funded_by(run_dir), "own_keys", "an unknown value does not claim the operator paid")
        (run_dir / ".owner").write_text("code:abc", encoding="utf-8")
        self.assertEqual(runs._funded_by(run_dir), "deployment")

    def test_the_launch_records_funding_beside_the_owner(self):
        source = (_ROOT / "api" / "runs.py").read_text(encoding="utf-8")
        launch = source[source.index("def _start_run_from_spec("):source.index("def _spec_from_submission(")]
        owner_line = launch.index("(run_dir / _OWNER_FILE).write_text(owner")
        funding_line = launch.index("_record_funding(run_dir, owner=owner, byok=byok)")
        self.assertLess(owner_line, funding_line, "written right after the owner, before the worker starts")
        self.assertIn(json.dumps(".funded"), json.dumps(runs._FUNDED_FILE))


class PageTests(unittest.TestCase):
    def test_the_page_stops_asking_a_funded_administrator_for_keys(self):
        app_js = (_ROOT / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function operatorPays()", app_js)
        self.assertIn("accountMode && accountAdmin && authConfig?.admin_funded === true", app_js)
        self.assertEqual(app_js.count("!operatorPays()"), 2, "the paid-request guard and the boot's key card")
        self.assertIn("if (api.getByok() || operatorPays() || trialPays()) { finish(); return; }", app_js)
        self.assertIn('t(operatorPays() ? "byok_admin_note" : trialPays() ? "byok_trial_note" : "byok_account_note")', app_js)
        # The first production run on the operator's key skipped the free preview and went
        # straight to a paid start: the preview condition only knew accounts with keys.
        self.assertIn("(accountMode ? (Boolean(api.getByok()) || operatorPays() || trialPays()) : !byokMode)", app_js)
        strings = (_ROOT / "web" / "static" / "js" / "i18n.js").read_text(encoding="utf-8")
        self.assertEqual(strings.count("    byok_admin_note: "), 2)

    def test_the_guide_and_the_example_environment_say_so(self):
        guide = (_ROOT / "docs" / "operating-guide.md").read_text(encoding="utf-8")
        self.assertIn("ACCOUNTS_ADMIN_FUNDED=0", guide)
        self.assertIn("`.funded`", guide)
        env = (_ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("ACCOUNTS_ADMIN_FUNDED", env)


if __name__ == "__main__":
    unittest.main()
