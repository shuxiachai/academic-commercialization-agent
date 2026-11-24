"""The privacy and terms page says what the code does, and stays that way.

A privacy page that drifts from the behaviour it describes is worse than
none. These tests tie the periods, provider names and storage claims on the
page to the constants and modules they come from, so a change to the
behaviour that the page does not follow fails here.
"""
from __future__ import annotations

import os
import re
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import access, accounts, mail, papers, receipts, runs
from api.main import app
from api.models import BYOK_PROVIDERS

_ROOT = Path(__file__).resolve().parent.parent
_PAGE = (_ROOT / "web" / "privacy.html").read_text(encoding="utf-8")
_SCRIPT = (_ROOT / "web" / "static" / "js" / "privacy.js").read_text(encoding="utf-8")


class PageIsPublicTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict("os.environ")
        environment.start()
        self.addCleanup(environment.stop)
        for name in ("ACCOUNTS_DB", "OPERATOR_CONTACT"):
            os.environ.pop(name, None)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_the_page_and_its_facts_are_readable_without_credentials(self):
        with patch.object(access, "ACCESS_CODE", "code-1"), \
                patch.dict("os.environ", {"ACCOUNTS_DB": str(_ROOT / "unused-accounts.sqlite3")}):
            page = self.client.get("/privacy")
            self.assertEqual(page.status_code, 200)
            self.assertIn("text/html", page.headers["content-type"])
            self.assertEqual(self.client.get("/api/site").status_code, 200)
            # ...while the rest of the API still turns an anonymous visitor away.
            self.assertEqual(self.client.get("/api/runs").status_code, 401)

    def test_site_facts_come_from_the_deployment(self):
        with patch.object(runs, "RUN_RETENTION_DAYS", 30), \
                patch.dict("os.environ", {"OPERATOR_CONTACT": "  ops@example.org  "}):
            self.assertEqual(self.client.get("/api/site").json(),
                             {"retention_days": 30, "contact": "ops@example.org", "accounts": False,
                              "signup_open": False, "account_backup_days": None, "mail": False})
        with patch.object(runs, "RUN_RETENTION_DAYS", 0), patch.dict("os.environ", {}):
            os.environ.pop("OPERATOR_CONTACT", None)
            self.assertEqual(self.client.get("/api/site").json(),
                             {"retention_days": None, "contact": None, "accounts": False,
                              "signup_open": False, "account_backup_days": None, "mail": False})

    def test_the_site_facts_say_whether_new_accounts_are_taken(self):
        """The sample reader's link onward reads it here. It sends no credential,
        so the access check, which says the same, would refuse it."""
        with TemporaryDirectory() as folder:
            for mode, takes in (("open", True), ("invite", True), ("closed", False)):
                settings = {"ACCOUNTS_DB": str(Path(folder) / "accounts.sqlite3"), "ACCOUNTS_SIGNUP": mode,
                            "ACCOUNTS_INVITE_CODE": "an-invite-code"}
                with self.subTest(mode=mode), patch.dict("os.environ", settings):
                    facts = self.client.get("/api/site").json()
                    self.assertIs(facts["accounts"], True)
                    self.assertIs(facts["signup_open"], takes)
                    self.assertIs(facts["signup_open"], accounts.signup_open())
        # Without accounts there is nothing to sign up for, whatever the mode says.
        with patch.dict("os.environ", {"ACCOUNTS_SIGNUP": "open"}):
            self.assertIs(self.client.get("/api/site").json()["signup_open"], False)

    def test_the_site_facts_say_whether_this_deployment_sends_email(self):
        # Only a deployment that hands messages to the delivery service: an outbox
        # directory, the development setting, sends nothing to anyone.
        for mode, sends in (("resend", True), ("outbox", False), ("off", False), ("misconfigured", False)):
            with self.subTest(mode=mode), patch.object(mail, "mode", return_value=mode):
                self.assertIs(self.client.get("/api/site").json()["mail"], sends)

    def test_an_overlong_contact_line_is_cut_not_served_whole(self):
        with patch.dict("os.environ", {"OPERATOR_CONTACT": "x" * 5000}):
            self.assertEqual(len(self.client.get("/api/site").json()["contact"]), 300)

    def test_the_gate_links_to_the_page(self):
        index = (_ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertGreaterEqual(index.count('href="/privacy"'), 2)   # the gate footer and the account form


class PageMatchesTheCodeTests(unittest.TestCase):
    def test_both_languages_are_in_the_markup(self):
        self.assertEqual(len(re.findall(r'data-lang-block="en"', _PAGE)), 1)
        self.assertEqual(len(re.findall(r'data-lang-block="zh"', _PAGE)), 1)
        english, chinese = _PAGE.split('data-lang-block="zh"')
        # The same sections on both sides, so one language cannot quietly say less.
        self.assertEqual(english.count("<h2>"), chinese.count("<h2>"))
        self.assertEqual(english.count("<li>"), chinese.count("<li>"))

    def test_the_retention_period_is_never_written_into_the_page(self):
        """It is the deployment's number. The page shows it from /api/site."""
        self.assertEqual(_PAGE.count("data-retention="), 4)          # two per language
        self.assertEqual(_PAGE.count("data-retention-auto"), 2)
        self.assertEqual(len(re.findall(r"<span data-retention-auto hidden>", _PAGE)), 2)
        self.assertIsNone(re.search(r"\b(30|60|90|180|365) (days|天)", _PAGE))
        self.assertIn('fetch("/api/site")', _SCRIPT)
        self.assertIn("site.retention_days === null", _SCRIPT)

    def test_privacy_js_retention_wording_in_both_languages(self):
        """Run privacy.js in Node across loading, error, missing, malformed, integer and null."""
        import json
        import shutil
        import subprocess

        node = shutil.which("node")
        assert node, "Node is required; missing execution is not a passing seam"
        contract = Path(__file__).with_name("js") / "privacy_retention_contract.mjs"
        i18n_js = (_ROOT / "web" / "static" / "js" / "i18n.js").read_text(encoding="utf-8")
        for scenario in ("loading", "http_503", "missing", "malformed", "days", "null_forever"):
            with self.subTest(scenario=scenario), TemporaryDirectory() as tmp:
                work = Path(tmp)
                (work / "privacy.js").write_text(_SCRIPT, encoding="utf-8")
                (work / "i18n.js").write_text(i18n_js, encoding="utf-8")
                (work / "input.json").write_text(
                    json.dumps({"html": _PAGE}, ensure_ascii=False), encoding="utf-8"
                )
                result = subprocess.run(
                    [node, str(contract), str(work), scenario],
                    capture_output=True, text=True, encoding="utf-8", timeout=30, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f"PASS {scenario}", result.stdout)

    def test_the_24_hour_claims_match_the_constants(self):
        self.assertEqual(papers._MAX_AGE_SECONDS, 24 * 3600)         # unused extractions
        self.assertEqual(receipts.RETENTION_SECONDS, 24 * 3600)      # receipts
        self.assertEqual(accounts.VERIFY_SECONDS, 24 * 3600)         # a verification link
        self.assertEqual(_PAGE.count("24 hours"), 3)
        self.assertEqual(_PAGE.count("24 小时"), 3)

    def test_every_model_provider_a_visitor_can_choose_is_named(self):
        names = {"deepseek": "DeepSeek", "qwen": "Alibaba Model Studio", "openai": "OpenAI", "anthropic": "Anthropic"}
        self.assertEqual(set(names), set(BYOK_PROVIDERS), "a new provider must be added to the privacy page")
        for name in names.values():
            self.assertIn(name, _PAGE)
        self.assertIn("阿里云百炼", _PAGE)

    def test_the_account_claims_match_the_account_store(self):
        self.assertTrue(accounts.hash_password("a sufficiently long password").startswith("scrypt$"))
        self.assertGreaterEqual(_PAGE.count("scrypt"), 2)

    def test_no_cookies_and_nothing_from_another_site(self):
        for path in list((_ROOT / "api").glob("*.py")) + list((_ROOT / "web" / "static" / "js").glob("*.js")):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("set_cookie", text, path.name)
            self.assertNotIn("document.cookie", text, path.name)
        self.assertNotIn("<script src=\"http", _PAGE)
        # Every <link> that makes the browser fetch something fetches it from
        # this site. The canonical link is the one that fetches nothing: it
        # states the page's own public address for a search engine, and is
        # held to that address by tests/test_search_indexing.py.
        self.assertEqual(re.findall(r'<link(?! rel="canonical" href="https://academic-agent\.cc/privacy">)[^>]+href="(?!/static/)', _PAGE), [])
        self.assertEqual(_PAGE.count('<link rel="canonical"'), 1)

    def test_the_contact_line_is_written_as_text_not_markup(self):
        self.assertIn("node.textContent = site.contact.trim()", _SCRIPT)
        self.assertNotIn("innerHTML", _SCRIPT)


def _between(text: str, start: str, end: str) -> str:
    """The part of `text` from `start` up to the next `end`."""
    begin = text.index(start)
    return text[begin:text.index(end, begin + len(start))]


class EmailAndAccountClaimsTests(unittest.TestCase):
    """Until 2026-11-13 the page said the address "is not verified and no email
    is ever sent to it", and that an account was an email, a hash and "nothing
    else". It was written on 5 November. Verification, password reset and the
    finish notice arrived on the 7th and 8th, each with its own tests, and the
    one test here that should have noticed looked for `smtplib` in the account
    store, which sends through an HTTPS API. So the page went on saying it for
    a week on a deployment that was sending all three."""

    def setUp(self):
        self.english, self.chinese = _PAGE.split('data-lang-block="zh"')
        self.email_en = _between(self.english, "<h3>Email sent to you</h3>", "<h3>")
        self.email_zh = _between(self.chinese, "<h3>发给你的邮件</h3>", "<h3>")

    def test_the_page_no_longer_says_what_stopped_being_true(self):
        for phrase in ("no email is ever sent", "The email is not verified", "Nothing else about you is collected",
                       "不会向它发送任何邮件", "邮箱不做验证", "不收集关于你的其他信息"):
            self.assertNotIn(phrase, _PAGE)

    def test_every_kind_of_message_the_code_can_send_is_described(self):
        builders = sorted(name for name in vars(mail) if name.endswith("_message") and not name.startswith("_"))
        self.assertEqual(builders, ["reset_message", "run_notice_message", "verification_message"],
                         "a new kind of email must be described on the privacy page")
        senders = {path.name for path in (_ROOT / "api").glob("*.py")
                   if path.name != "mail.py" and "mail.send(" in path.read_text(encoding="utf-8")}
        self.assertEqual(senders, {"main.py", "notices.py"}, "a new place that sends email must be described too")
        self.assertIn("three kinds of message and no others", self.email_en)
        for words in ("verify the address", "choose a new password", "completes or fails"):
            self.assertIn(words, self.email_en)
        self.assertIn("只发三类邮件", self.email_zh)
        for words in ("验证邮箱", "设置新密码", "完成或失败"):
            self.assertIn(words, self.email_zh)

    def test_the_link_lifetimes_are_the_codes(self):
        self.assertEqual(accounts.VERIFY_SECONDS, 24 * 3600)
        self.assertEqual(accounts.RESET_SECONDS, 60 * 60)
        self.assertIn("24 hours", self.email_en)
        self.assertIn("60 minutes", self.email_en)
        self.assertIn("24 小时", self.email_zh)
        self.assertIn("60 分钟", self.email_zh)

    def test_the_finish_notice_carries_what_the_page_says_and_is_off_until_asked_for(self):
        subject, text, html_body = mail.run_notice_message("https://example.org/run/abc", topic="perovskite cells",
                                                           state="completed")
        for part in (text, html_body):
            self.assertIn("perovskite cells", part)
            self.assertIn("https://example.org/run/abc", part)
        self.assertNotIn("perovskite", subject, "the topic is in the message, not in its subject line")
        self.assertIs(accounts.User(id=1, email="a@example.org").notify_done, False)
        self.assertIn("its topic and its link", self.email_en)
        self.assertIn("only if you turn it on", self.email_en)
        self.assertIn("主题和链接", self.email_zh)
        self.assertIn("只有在你打开", self.email_zh)

    def test_the_other_two_messages_carry_a_link_and_nothing_about_the_person(self):
        for build in (mail.verification_message, mail.reset_message):
            subject, text, html_body = build("https://example.org/verify?token=abc")
            self.assertIn("https://example.org/verify?token=abc", text)
            self.assertNotIn("@", subject + text.replace("https://example.org/verify?token=abc", ""))

    def test_the_delivery_service_is_named_among_those_who_see_content(self):
        self.assertEqual(mail.RESEND_HOST, "api.resend.com", "another delivery service must be named on the privacy page")
        for block, heading, words in (
            (self.english, "<h2>Who else sees your content</h2>", ("Resend", "your email address", "topic", "opens the report")),
            (self.chinese, "<h2>还有谁会看到你的内容</h2>", ("Resend", "你的邮箱地址", "主题", "可以打开报告")),
        ):
            who = _between(block, heading, "<h2>")
            for word in words:
                self.assertIn(word, who)

    def test_links_are_kept_as_hashes_as_the_page_says(self):
        self.assertIn("token_hash TEXT PRIMARY KEY", accounts._SCHEMA)
        self.assertNotRegex(accounts._SCHEMA, r"\btoken TEXT")
        self.assertIn("only as hashes", self.email_en)
        self.assertIn("只保存哈希", self.email_zh)

    def test_what_the_account_store_keeps_is_what_the_page_lists(self):
        with TemporaryDirectory() as folder, patch.dict("os.environ", {"ACCOUNTS_DB": str(Path(folder) / "a.sqlite3")}):
            with accounts._database():
                pass
            with sqlite3.connect(Path(folder) / "a.sqlite3") as db:
                tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                          if not row[0].startswith("sqlite_")}
                columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
            db.close()
        self.assertEqual(tables, {"users", "sessions", "login_throttle", "email_tokens", "trial_days", "account_keys"},
                         "a new table in the account store must be described on the privacy page")
        self.assertEqual(columns, {"id", "email", "password_hash", "created_at", "disabled", "verified_at", "notify_done",
                                   "trial_used"},
                         "a new fact kept about an account must be described on the privacy page")
        account_en = _between(self.english, "<h3>Your account</h3>", "<h3>")
        for words in ("when the account was created", "when its address was verified", "finish notice",
                      "free trial assessments it has used", "disabled the account"):
            self.assertIn(words, account_en)
        account_zh = _between(self.chinese, "<h3>你的账号</h3>", "<h3>")
        for words in ("账号的创建时间", "邮箱通过验证的时间", "结束通知", "免费试用评估", "停用"):
            self.assertIn(words, account_zh)

    def test_saved_api_keys_are_described_as_what_they_are(self):
        """The page said "Your API keys are never stored on this server" until
        2026-11-15. They are now saved with the account, sealed; what the page
        says about that is held to what the store keeps."""
        with TemporaryDirectory() as folder, patch.dict("os.environ", {"ACCOUNTS_DB": str(Path(folder) / "a.sqlite3")}):
            with accounts._database():
                pass
            db = sqlite3.connect(Path(folder) / "a.sqlite3")
            try:
                columns = [row[1] for row in db.execute("PRAGMA table_info(account_keys)")]
            finally:
                db.close()
        self.assertEqual(columns, ["user_id", "sealed", "updated_at"],
                         "anything kept about saved keys beyond one sealed record must be described on the page")
        keys_en = _between(self.english, "<h3>Your API keys</h3>", "<h3>")
        for words in ("saved with your account unless you untick", "one encrypted record",
                      "nothing about them can be read in the account store",
                      "kept apart from the account store and is not part of its recovery copies",
                      "never sent back to your browser", "the last four characters of each key",
                      "replace or remove them", "deleting your account removes them",
                      "restored from a recovery copy, saved keys are cleared"):
            self.assertIn(words, keys_en)
        keys_zh = _between(self.chinese, "<h3>你的 API Key</h3>", "<h3>")
        for words in ("除非你取消勾选", "一条加密记录", "账号库里读不出其中任何内容", "与账号库分开存放",
                      "不会再发回你的浏览器", "最后四位", "更换或删除", "注销账号会一并删除", "保存的密钥会被清除"):
            self.assertIn(words, keys_zh)
        # Nothing on the page still says keys are never stored, or that the browser keeps a copy.
        for stale in ("never stored on this server", "不会保存在本服务器上", "or any database", "或任何数据库",
                      "Remember these keys on this device", "在这台设备上记住这些密钥", "kept in local storage, unencrypted"):
            self.assertNotIn(stale, _PAGE, stale)
        self.assertIn("Your API keys in readable form", _between(self.english, "<h2>What is never stored</h2>", "<h2>"))
        self.assertIn("可读形式的 API Key", _between(self.chinese, "<h2>从不保存什么</h2>", "<h2>"))
        # The page's name for the box is the box's.
        strings = (Path(__file__).resolve().parents[1] / "web/static/js/i18n.js").read_text(encoding="utf-8")
        self.assertIn('byok_to_account: "Save these keys to my account"', strings)
        self.assertIn('byok_to_account: "把这些密钥保存到我的账号"', strings)
        self.assertEqual(_PAGE.count("Save these keys to my account"), 2)
        self.assertEqual(_PAGE.count("把这些密钥保存到我的账号"), 2)

    def test_wrong_passwords_are_counted_against_the_network_address_and_the_page_says_so(self):
        keys = [key for key, _ in accounts._throttle_keys("a@example.org", "203.0.113.9")]
        self.assertTrue(any("203.0.113.9" in key for key in keys))
        self.assertTrue(all("a@example.org" in key for key in keys))
        self.assertIn("counted against the email address tried and the network address they came from",
                      _between(self.english, "<h3>Your account</h3>", "<h3>"))
        self.assertIn("按所尝试的邮箱和请求来源的网络地址计数", _between(self.chinese, "<h3>你的账号</h3>", "<h3>"))

    def test_the_page_says_which_case_this_deployment_is_only_from_its_facts(self):
        for value in ("on", "off"):
            spans = re.findall(rf'<span data-mail="{value}"( hidden)?>', _PAGE)
            self.assertEqual(spans, [" hidden", " hidden"], f"one per language, hidden until /api/site answers ({value})")
        self.assertIn("site.mail", _SCRIPT)
        self.assertIn("node.dataset.mail", _SCRIPT)

    def test_both_languages_carry_the_same_date(self):
        english = re.search(r"Last updated (\d+) (\w+) (\d{4})\.", self.english)
        chinese = re.search(r"最近更新：(\d{4}) 年 (\d+) 月 (\d+) 日。", self.chinese)
        self.assertIsNotNone(english)
        self.assertIsNotNone(chinese)
        months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                  "November", "December"]
        self.assertEqual((int(english[3]), months.index(english[2]) + 1, int(english[1])),
                         (int(chinese[1]), int(chinese[2]), int(chinese[3])))
        self.assertGreaterEqual((int(english[3]), months.index(english[2]) + 1, int(english[1])), (2026, 11, 13))


if __name__ == "__main__":
    unittest.main()
