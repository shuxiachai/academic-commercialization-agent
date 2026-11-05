"""Every cause the API can name is worded for every reader, in both places.

api/runs.py holds the English sentences and the codes; web/static/js/run.js
holds the other language, keyed by the same codes. A cause added on one side
only would reach a Chinese reader in English, or not at all, with no test
failing. This file is the only thing holding the two tables together.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from api import runs

_RUN_JS = Path(__file__).resolve().parents[1] / "web" / "static" / "js" / "run.js"


def _page_keys() -> dict[str, str]:
    source = _RUN_JS.read_text(encoding="utf-8")
    table = source[source.index("const FAILURE_STRINGS = {"):source.index("/** The sentence to show for why a run stopped")]
    return {key: value for key, value in re.findall(r'^\s+"?([a-z_]+(?::[a-z_]+)?)"?: "([^"]+)",$', table, re.M)}


def _api_keys() -> set[str]:
    keys = {runs._UNKNOWN_FAILURE[0], "cancelled", "timeout_resumable"}
    for category in runs._PUBLIC_FAILURE_CATEGORIES:
        keys.add(category.code)
        if category.deployment:
            keys.add(f"{category.code}:deployment")
        if category.own_keys:
            keys.add(f"{category.code}:own_keys")
    return keys


class FailureWordingTests(unittest.TestCase):
    def test_the_page_words_exactly_the_causes_the_api_names(self):
        self.assertEqual(set(_page_keys()), _api_keys())

    def test_codes_are_unique_and_every_marker_is_lower_case(self):
        codes = [category.code for category in runs._PUBLIC_FAILURE_CATEGORIES]
        self.assertEqual(len(codes), len(set(codes)))
        for category in runs._PUBLIC_FAILURE_CATEGORIES:
            for marker in category.markers:
                # The raw reason is lower-cased before matching.
                self.assertEqual(marker, marker.lower(), category.code)

    def test_each_reader_is_told_something_they_can_act_on(self):
        for category in runs._PUBLIC_FAILURE_CATEGORIES:
            with self.subTest(code=category.code):
                if category.deployment:
                    # A code holder cannot change the deployment: say so, and who can.
                    self.assertTrue(category.deployment.endswith(runs._OPERATOR_SIDE))
                if category.own_keys:
                    # An account is the only one who can fix its own keys.
                    self.assertNotIn("operator", category.own_keys.lower())
                    self.assertNotIn("deployment", category.own_keys.lower())
                    self.assertRegex(category.own_keys, r"\b[Yy]our?\b")
                # A cause the deployment's reader cannot act on is one an account can.
                self.assertFalse(category.deployment and not category.own_keys, category.code)

    def test_the_same_holds_in_chinese(self):
        page = _page_keys()
        for key, sentence in page.items():
            with self.subTest(key=key):
                self.assertRegex(sentence, r"[\u4e00-\u9fff]")
                self.assertTrue(sentence.endswith("。"))
                if key.endswith(":deployment"):
                    self.assertIn("运营者", sentence)
                if key.endswith(":own_keys"):
                    self.assertIn("你", sentence)
                    self.assertNotIn("运营者", sentence)
                    self.assertNotIn("本站", sentence)

    def test_no_wording_can_carry_what_the_provider_said(self):
        raw = ("AuthenticationError: Error code: 401 - Incorrect API key provided: sk-SECRET-KEY-123 "
               "at C:\\\\Users\\\\someone\\\\project with prompt 'CONFIDENTIAL TOPIC'")
        for funded_by in (None, "deployment", "own_keys"):
            code, sentence = runs._public_failure(raw, funded_by=funded_by)
            self.assertEqual(code, "provider_auth")
            for leaked in ("SECRET", "someone", "CONFIDENTIAL", "401"):
                self.assertNotIn(leaked, sentence)

    def test_the_owner_marker_decides_whose_keys_and_nothing_else(self):
        import tempfile
        with tempfile.TemporaryDirectory() as raw:
            run_dir = Path(raw)
            self.assertIsNone(runs._funded_by(run_dir))
            for owner, expected in (("user:7", "own_keys"), ("code-hash", "deployment"), ("", "deployment")):
                (run_dir / ".owner").write_text(owner, encoding="utf-8")
                self.assertEqual(runs._funded_by(run_dir), expected, owner)


if __name__ == "__main__":
    unittest.main()
