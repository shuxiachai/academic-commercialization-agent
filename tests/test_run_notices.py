"""An account that asked is emailed when one of its runs ends.

Opt-in from the Account panel, only where mail is set up (api/notices.py).
The maintenance loop sweeps the newest run directories; each is decided once
and marked, so a restart repeats nothing and turning the notice on later does
not announce older runs. Completed and failed runs are announced; cancelled
and timed-out ones, ownerless ones, and ones that ended long ago are not.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from academic_agent.run_terminal import TerminalRecord, UsageAccounting, commit_terminal_record
from api import accounts, mail, main, notices, runs
from api.main import app

PASSWORD = "a sufficiently long password"
EMAIL = "alice@example.com"
_ROOT = Path(__file__).resolve().parents[1]
_MAIL_SETTINGS = ("MAIL_RESEND_API_KEY", "MAIL_OUTBOX", "MAIL_FROM", "PUBLIC_URL", "MAIL_PER_DAY")


class _Case(unittest.TestCase):
    """Accounts on, mail to an outbox directory, runs under a temporary root."""

    mail_env: dict = {"MAIL_OUTBOX": "<outbox>", "MAIL_FROM": "ACA <noreply@example.com>",
                      "PUBLIC_URL": "https://aca.example.com"}

    def setUp(self):
        self._tmp = TemporaryDirectory()
        root = Path(self._tmp.name)
        self.outbox = root / "outbox"
        self.outputs = root / "outputs"
        env = {"ACCOUNTS_DB": str(root / "accounts.sqlite3")}
        env.update({k: (str(self.outbox) if v == "<outbox>" else v) for k, v in self.mail_env.items()})
        self._env = patch.dict("os.environ", env)
        self._env.start()
        for name in ("ACCOUNTS_SIGNUP", "ACCOUNTS_ADMIN_EMAILS", "OPERATOR_CONTACT", *_MAIL_SETTINGS):
            if name not in env:
                os.environ.pop(name, None)
        self._outputs = patch.object(runs, "DEFAULT_OUTPUT_ROOT", self.outputs)
        self._outputs.start()
        mail.reset()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self._outputs.stop()
        self._env.stop()
        self._tmp.cleanup()
        mail.reset()

    def _signup(self, email=EMAIL, *, notify=True) -> tuple[str, str]:
        """Create an account; return (session token, owner tag)."""
        response = self.client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
        self.assertEqual(response.status_code, 201, response.text)
        token = response.json()["token"]
        if notify:
            self.assertEqual(self.client.post("/api/auth/notify", json={"enabled": True},
                                              headers=self._bearer(token)).status_code, 204)
        return token, accounts.session_user(token).owner

    @staticmethod
    def _bearer(token):
        return {"Authorization": f"Bearer {token}"}

    def _messages(self) -> list[dict]:
        if not self.outbox.is_dir():
            return []
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(self.outbox.iterdir())]

    def _notices(self) -> list[dict]:
        """Messages other than the verification links sign-up sends."""
        return [m for m in self._messages() if "verify?token" not in m["text"]]

    def _run(self, owner, *, state="completed", topic="Hyperloop", started=None, ended=None, terminal=True) -> str:
        now = datetime.now(UTC)
        started = started or now - timedelta(minutes=15)
        ended = ended or now - timedelta(minutes=1)
        run_id = f"{started:%Y%m%dT%H%M%SZ}-{secrets.token_hex(16)}"
        run_dir = self.outputs / run_id
        run_dir.mkdir(parents=True)
        if owner is not None:
            (run_dir / ".owner").write_text(owner, encoding="utf-8")
        (run_dir / "status.json").write_text(json.dumps({"topic": topic, "state": state}), encoding="utf-8")
        if terminal:
            self._end(run_id, state=state, started=started, ended=ended)
        return run_id

    def _end(self, run_id, *, state="completed", started=None, ended=None) -> None:
        now = datetime.now(UTC)
        started = started or now - timedelta(minutes=15)
        ended = ended or now - timedelta(minutes=1)
        commit_terminal_record(self.outputs / run_id, TerminalRecord(
            state=state, reason_code=state, termination_method="worker_exit", started_at=started, ended_at=ended,
            elapsed_seconds=int((ended - started).total_seconds()),
            usage_accounting=UsageAccounting(state="unavailable", snapshot_at=ended, run_complete=state == "completed",
                                             in_flight_request_may_have_spent=False)))

    def _marker(self, run_id) -> dict | None:
        path = self.outputs / run_id / ".notice"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


class SweepTests(_Case):
    def test_an_account_that_asked_is_told_once_about_a_finished_run(self):
        _, owner = self._signup()
        run_id = self._run(owner, topic="Perovskite solar cells")
        self.assertEqual(notices.sweep(), [run_id])
        (message,) = self._notices()
        self.assertEqual(message["to"], [EMAIL])
        self.assertIn("Assessment finished", message["subject"])
        self.assertIn("aca.example.com", message["subject"])
        link = f"https://aca.example.com/run/{run_id}"
        self.assertEqual(message["text"].count(link), 2)
        self.assertEqual(message["html"].count(f'href="{link}"'), 2)
        for words in ("Perovskite solar cells", "评估完成", "14 分钟", "about 14 minutes", "Account panel"):
            self.assertIn(words, message["text"])
        self.assertNotIn("alice", message["text"] + message["html"] + message["subject"])
        self.assertEqual(self._marker(run_id)["outcome"], "sent")
        # Decided once: the next sweep has nothing to say about it.
        self.assertEqual(notices.sweep(), [])
        self.assertEqual(len(self._notices()), 1)

    def test_a_failed_run_is_told_as_such_and_other_endings_are_not_told(self):
        _, owner = self._signup()
        failed = self._run(owner, state="failed", topic="Hyperloop")
        cancelled = self._run(owner, state="cancelled")
        timed_out = self._run(owner, state="timeout")
        self.assertEqual(notices.sweep(), [failed])
        (message,) = self._notices()
        self.assertIn("did not finish", message["subject"])
        for words in ("未能完成", "checkpoint", "Open the run"):
            self.assertIn(words, message["text"] + message["html"])
        self.assertEqual(self._marker(cancelled)["outcome"], "skipped")
        self.assertEqual(self._marker(timed_out)["outcome"], "skipped")

    def test_an_account_that_did_not_ask_is_not_told_even_after_it_asks(self):
        token, owner = self._signup(notify=False)
        run_id = self._run(owner)
        self.assertEqual(notices.sweep(), [])
        self.assertEqual(self._marker(run_id)["outcome"], "declined")
        self.assertEqual(self.client.post("/api/auth/notify", json={"enabled": True},
                                          headers=self._bearer(token)).status_code, 204)
        # The decision stands: the switch is for what ends from now on.
        self.assertEqual(notices.sweep(), [])
        later = self._run(owner)
        self.assertEqual(notices.sweep(), [later])

    def test_a_running_run_is_left_alone_until_it_ends(self):
        _, owner = self._signup()
        run_id = self._run(owner, terminal=False)
        self.assertEqual(notices.sweep(), [])
        self.assertIsNone(self._marker(run_id), "no decision yet: nothing to decide")
        self._end(run_id)
        self.assertEqual(notices.sweep(), [run_id])

    def test_a_run_that_ended_long_ago_is_marked_without_a_message(self):
        _, owner = self._signup()
        now = datetime.now(UTC)
        stale = self._run(owner, started=now - timedelta(hours=30), ended=now - timedelta(hours=29))
        ancient = self._run(owner, started=now - timedelta(days=5), ended=now - timedelta(days=5, hours=-1))
        fresh = self._run(owner)
        self.assertEqual(notices.sweep(), [fresh])
        self.assertEqual(self._marker(stale)["outcome"], "stale")
        self.assertIsNone(self._marker(ancient), "older than the lookback: not even opened")
        self.assertEqual(len(self._notices()), 1)

    def test_runs_without_an_account_owner_are_nobody_s_news(self):
        self._signup()
        byok = self._run(None)
        code = self._run("code:abc")
        self.assertEqual(notices.sweep(), [])
        self.assertIsNone(self._marker(byok))
        self.assertIsNone(self._marker(code))
        self.assertEqual(self._notices(), [])

    def test_a_message_that_cannot_be_sent_is_logged_by_id_and_not_retried(self):
        token, owner = self._signup()
        user_id = accounts.session_user(token).id
        run_id = self._run(owner)
        with patch.object(mail, "send", side_effect=mail.MailError("HTTP 500 (internal)")), \
                self.assertLogs("api.notices", level="WARNING") as logged:
            self.assertEqual(notices.sweep(), [])
        self.assertEqual(len(logged.output), 1)
        self.assertIn(f"account {user_id} ", logged.output[0])
        self.assertNotIn("alice", logged.output[0])
        self.assertEqual(self._marker(run_id)["outcome"], "failed")
        self.assertEqual(notices.sweep(), [])
        self.assertEqual(self._notices(), [])

    def test_the_loop_calls_the_sweep_and_survives_its_failure(self):
        with patch.object(notices, "sweep", return_value=[]) as sweep:
            asyncio.run(main._send_notices())
        sweep.assert_called_once_with()
        with patch.object(notices, "sweep", side_effect=RuntimeError("disk")), \
                self.assertLogs("api.main", level="ERROR") as logged:
            asyncio.run(main._send_notices())
        self.assertIn("Run notice sweep failed", logged.output[0])


class SwitchTests(_Case):
    def test_the_switch_is_off_until_asked_and_shows_everywhere_the_account_does(self):
        token, _ = self._signup(notify=False)
        me = self.client.get("/api/auth/me", headers=self._bearer(token)).json()
        self.assertEqual(me, {"email": EMAIL, "admin": False, "verified": False, "notify_done": False,
                          "trial_runs_left": 0})
        self.assertTrue(self.client.get("/api/auth/config").json()["notices"])
        self.assertEqual(self.client.post("/api/auth/notify", json={"enabled": True},
                                          headers=self._bearer(token)).status_code, 204)
        self.assertTrue(self.client.get("/api/auth/me", headers=self._bearer(token)).json()["notify_done"])
        self.assertTrue(self.client.get("/api/access/check", headers=self._bearer(token)).json()["account"]["notify_done"])
        self.assertEqual(self.client.post("/api/auth/notify", json={"enabled": False},
                                          headers=self._bearer(token)).status_code, 204)
        self.assertFalse(self.client.get("/api/auth/me", headers=self._bearer(token)).json()["notify_done"])
        # A session is needed; the body is a boolean.
        self.assertEqual(self.client.post("/api/auth/notify", json={"enabled": True}).status_code, 401)
        self.assertEqual(self.client.post("/api/auth/notify", json={"enabled": "yes please"},
                                          headers=self._bearer(token)).status_code, 422)

    def test_accounts_from_before_the_column_have_it_off(self):
        token, _ = self._signup(notify=False)
        with accounts._database() as db, db:
            db.execute("UPDATE users SET notify_done = 1")
            db.execute("ALTER TABLE users DROP COLUMN notify_done")
        self.assertFalse(accounts.session_user(token).notify_done, "the column is back, and off")


class WithoutMailTests(_Case):
    mail_env = {}

    def test_nothing_is_offered_swept_or_accepted(self):
        token, owner = self._signup(notify=False)
        self.assertFalse(self.client.get("/api/auth/config").json()["notices"])
        response = self.client.post("/api/auth/notify", json={"enabled": True}, headers=self._bearer(token))
        self.assertEqual((response.status_code, response.headers.get("X-Error-Code")), (503, "mail_unavailable"))
        self.assertFalse(notices.enabled())
        run_id = self._run(owner)
        self.assertEqual(notices.sweep(), [])
        self.assertIsNone(self._marker(run_id), "nothing is decided where nothing can be sent")


class MessageTests(_Case):
    def test_the_message_is_the_card_with_the_topic_escaped_and_cut(self):
        link = "https://aca.example.com/run/r-1"
        subject, text, body = mail.run_notice_message(link, topic="  Solid  <b>state</b> batteries ", state="completed", minutes=12)
        self.assertEqual(subject, "评估完成 / Assessment finished · aca.example.com")
        self.assertIn("Solid <b>state</b> batteries", text)
        self.assertIn("Solid &lt;b&gt;state&lt;/b&gt; batteries", body)
        self.assertNotIn("<b>state</b>", body)
        self.assertEqual(body.count(f'href="{link}"'), 2)
        self.assertIn("about 12 minutes", body)
        self.assertIn('<meta name="color-scheme" content="light">', body)
        long = "x" * 300
        self.assertIn("x" * 119 + "…", mail.run_notice_message(link, topic=long, state="failed")[1])
        self.assertNotIn("x" * 121, mail.run_notice_message(link, topic=long, state="failed")[1])
        no_time = mail.run_notice_message(link, topic="", state="completed", minutes=0)[1]
        self.assertNotIn("minutes", no_time)
        self.assertIn("「—」", no_time)


class PageTests(unittest.TestCase):
    def test_the_panel_the_client_and_the_words_are_there_in_both_languages(self):
        index = (_ROOT / "web" / "index.html").read_text(encoding="utf-8")
        for marker in ('id="settings-notify-row"', 'id="settings-notify"', 'id="settings-notify-hint"', 'data-i18n="account_notify"'):
            self.assertIn(marker, index)
        app_js = (_ROOT / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("api.setNotify(wanted)", app_js)
        self.assertIn("notifyRow.hidden = !authConfig?.notices", app_js)
        self.assertIn("me.notify_done === true", app_js)
        api_js = (_ROOT / "web" / "static" / "js" / "api.js").read_text(encoding="utf-8")
        self.assertIn('"/api/auth/notify"', api_js)
        strings = (_ROOT / "web" / "static" / "js" / "i18n.js").read_text(encoding="utf-8")
        for key in ("account_notify", "account_notify_hint", "account_notify_on", "account_notify_off", "account_notify_failed"):
            self.assertEqual(strings.count(f"    {key}: "), 2, key)
        css = (_ROOT / "web" / "static" / "css" / "workbench.css").read_text(encoding="utf-8")
        self.assertIn(".gate__choice", css)

    def test_the_guide_the_readmes_and_the_privacy_page_say_so(self):
        guide = (_ROOT / "docs" / "operating-guide.md").read_text(encoding="utf-8")
        self.assertIn("### Email when a run ends", guide)
        self.assertIn("/api/auth/notify", guide)
        self.assertIn(".notice", guide)
        readme = (_ROOT / "README.md").read_text(encoding="utf-8").replace("\n", " ")
        self.assertIn("emailed when an assessment", readme)
        zh = (_ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        self.assertIn("评估结束时收到邮件通知", zh)
        privacy = (_ROOT / "web" / "privacy.html").read_text(encoding="utf-8")
        self.assertIn("Email me when an assessment finishes", privacy)
        self.assertIn("评估结束后发邮件给我", privacy)
        self.assertNotIn("目前还没有找回密码功能", privacy, "the Chinese side kept the old claim after #353")


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.WARNING)
    unittest.main()
