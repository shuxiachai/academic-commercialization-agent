"""The privacy and terms page says what the code does, and stays that way.

A privacy page that drifts from the behaviour it describes is worse than
none. These tests tie the periods, provider names and storage claims on the
page to the constants and modules they come from, so a change to the
behaviour that the page does not follow fails here.
"""
from __future__ import annotations

import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import access, accounts, papers, receipts, runs
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
                             {"retention_days": 30, "contact": "ops@example.org", "accounts": False})
        with patch.object(runs, "RUN_RETENTION_DAYS", 0), patch.dict("os.environ", {}):
            os.environ.pop("OPERATOR_CONTACT", None)
            self.assertEqual(self.client.get("/api/site").json(),
                             {"retention_days": None, "contact": None, "accounts": False})

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
        self.assertIsNone(re.search(r"\b(30|60|90|180|365) (days|天)", _PAGE))
        self.assertIn('fetch("/api/site")', _SCRIPT)

    def test_the_24_hour_claims_match_the_constants(self):
        self.assertEqual(papers._MAX_AGE_SECONDS, 24 * 3600)         # unused extractions
        self.assertEqual(receipts.RETENTION_SECONDS, 24 * 3600)      # receipts
        self.assertEqual(_PAGE.count("24 hours"), 2)
        self.assertEqual(_PAGE.count("24 小时"), 2)

    def test_every_model_provider_a_visitor_can_choose_is_named(self):
        names = {"deepseek": "DeepSeek", "qwen": "Alibaba Model Studio", "openai": "OpenAI", "anthropic": "Anthropic"}
        self.assertEqual(set(names), set(BYOK_PROVIDERS), "a new provider must be added to the privacy page")
        for name in names.values():
            self.assertIn(name, _PAGE)
        self.assertIn("阿里云百炼", _PAGE)

    def test_the_account_claims_match_the_account_store(self):
        self.assertTrue(accounts.hash_password("a sufficiently long password").startswith("scrypt$"))
        self.assertGreaterEqual(_PAGE.count("scrypt"), 2)
        # "No email is ever sent": the store has no way to send one.
        source = (_ROOT / "api" / "accounts.py").read_text(encoding="utf-8")
        self.assertNotIn("smtplib", source)

    def test_no_cookies_and_nothing_from_another_site(self):
        for path in list((_ROOT / "api").glob("*.py")) + list((_ROOT / "web" / "static" / "js").glob("*.js")):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("set_cookie", text, path.name)
            self.assertNotIn("document.cookie", text, path.name)
        self.assertNotIn("<script src=\"http", _PAGE)
        self.assertEqual(re.findall(r'<link[^>]+href="(?!/static/)', _PAGE), [])

    def test_the_contact_line_is_written_as_text_not_markup(self):
        self.assertIn("node.textContent = site.contact.trim()", _SCRIPT)
        self.assertNotIn("innerHTML", _SCRIPT)


if __name__ == "__main__":
    unittest.main()
