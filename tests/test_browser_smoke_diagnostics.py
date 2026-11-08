"""A browser-smoke failure leaves facts beside its picture.

Twice in CI the smoke failed at the same assertion with identical screenshots
of a page whose scripts had not run, and nothing else to go on. The page now
says whether app.js ran (`data-boot` on the document), the smoke waits for
that before judging the history after a reload, and a failure writes a JSON
of what the page and the journey knew.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from e2e import smoke_report

_ROOT = Path(__file__).resolve().parents[1]


class _Page:
    """The few things _capture_failure asks of a Playwright page."""

    def __init__(self, *, closed=False, evaluate=None):
        self.closed, self._evaluate, self.shots = closed, evaluate, []

    def is_closed(self):
        return self.closed

    def screenshot(self, *, path, full_page):
        self.shots.append((Path(path).name, full_page))
        Path(path).write_bytes(b"png")

    def evaluate(self, script):
        if isinstance(self._evaluate, BaseException):
            raise self._evaluate
        assert "dataset.boot" in script and "getEntriesByType" in script
        return self._evaluate


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name) / "playwright"
        self._patch = patch.object(smoke_report, "ARTIFACT_ROOT", self.root)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def _facts(self):
        return json.loads((self.root / "browser-smoke-failure.json").read_text(encoding="utf-8"))

    def test_the_picture_gets_a_json_of_page_and_journey_facts(self):
        page = _Page(evaluate={"boot": None, "readyState": "complete", "scripts": [], "storage": {"local": [], "session": []}})
        smoke_report.capture_failure(page, {"console_errors": ["Failed to load resource: net::ERR_X"],
                                            "page_errors": [], "http_failures": [("GET", "/api/x", 503)]})
        self.assertEqual(page.shots, [("browser-smoke-failure.png", True)])
        facts = self._facts()
        self.assertIsNone(facts["page"]["boot"], "a page that never ran app.js is told apart from one that did")
        self.assertEqual(facts["console_errors"], ["Failed to load resource: net::ERR_X"])
        self.assertEqual(facts["http_failures"], [["GET", "/api/x", 503]])

    def test_a_page_that_cannot_answer_still_leaves_the_picture_and_a_note(self):
        page = _Page(evaluate=RuntimeError("Target closed"))
        smoke_report.capture_failure(page)
        self.assertEqual(len(page.shots), 1)
        self.assertEqual(self._facts()["page"], {"unavailable": "RuntimeError"})

    def test_a_closed_page_leaves_nothing_and_raises_nothing(self):
        smoke_report.capture_failure(_Page(closed=True), {"console_errors": []})
        smoke_report.capture_failure(None)
        self.assertFalse(self.root.exists())


class ContractTests(unittest.TestCase):
    def test_the_page_marks_its_boot_and_the_smoke_waits_for_it(self):
        app_js = (_ROOT / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('markBoot("scripts");', app_js)
        self.assertIn('markBoot("ready");', app_js)
        self.assertLess(app_js.index('markBoot("scripts")'), app_js.index("const $ = "), "set before anything can fail")
        boot = app_js[app_js.index("\nensureAccess().then("):]
        self.assertIn('markBoot("ready")', boot, "ready means the boot decided who the visitor is")
        smoke = (_ROOT / "e2e" / "browser_smoke.py").read_text(encoding="utf-8")
        # The reload in the BYOK history journey, where the two failures were.
        journey = smoke[smoke.index('faults["history_503"] = True'):]
        reload_block = re.search(r'page\.reload\(wait_until="domcontentloaded"\)\n(.*?)to_have_count\(1\)', journey, re.S)
        self.assertIsNotNone(reload_block)
        self.assertIn('to_have_attribute("data-boot", "ready"', reload_block.group(1))
        self.assertIn("capture_failure(page, {", smoke)
        self.assertIn('f[1].startswith("/static/")', smoke, "a refused page file fails the journey by name")
        for name in ("console_errors", "page_errors", "http_failures", "external_requests", "mutation_attempts"):
            self.assertIn(f'"{name}": {name}', smoke)

    def test_the_suite_can_import_the_capture_without_playwright(self):
        source = (_ROOT / "e2e" / "smoke_report.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"^\s*(import|from) playwright", source, re.M), "the suite's pytest jobs do not install it")
        for name in ("composer_smoke.py", "keyboard_smoke.py", "browser_smoke.py"):
            self.assertIn("from e2e.smoke_report import capture_failure", (_ROOT / "e2e" / name).read_text(encoding="utf-8"), name)

    def test_the_harnesses_document_without_an_element_is_left_alone(self):
        app_js = (_ROOT / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("if (document.documentElement) document.documentElement.dataset.boot = stage", app_js)


if __name__ == "__main__":
    unittest.main()
