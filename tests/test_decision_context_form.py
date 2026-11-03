"""The composer's Decision Context: starred fields in view, the rest folded, and
a live line that tells the visitor what the backend gate will decide."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from academic_agent.run_spec import DecisionContext

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web/static/js"
CORE = ("asset_description", "target_application", "decision_owner", "decision_type")
FOLDED = ("jurisdiction", "time_horizon", "constraints", "success_criteria", "success_criteria_authority")

# Field values to judge in both languages of the rule: the browser line and the
# backend gate must agree on every one of them.
CASES = {
    "empty": {},
    "blank": {"asset_description": "   ", "decision_owner": "\n"},
    "folded_only": {"time_horizon": "Q3 2027"},
    "two_core": {"asset_description": "Prototype electrolyte", "decision_owner": "Investor"},
    "three_core_and_folded": {"asset_description": "A", "target_application": "B", "decision_type": "C",
                              "constraints": "No new hires"},
    "all_core": {"asset_description": "A", "target_application": "B", "decision_owner": "C", "decision_type": "D"},
}
_HARNESS = """
import { gateLine } from "./decision_context.js";
const cases = JSON.parse(process.argv[2]);
console.log(JSON.stringify(Object.fromEntries(Object.entries(cases).map(([k, v]) => [k, gateLine(v)]))));
"""


def _index() -> str:
    return (ROOT / "web/index.html").read_text(encoding="utf-8")


class DecisionContextFormTests(unittest.TestCase):
    def test_starred_fields_stay_in_view_and_the_rest_fold_away(self):
        page = _index()
        start = page.index('<details class="decision-context" id="decision-context">')
        more = page.index('<details class="decision-context__more">', start)
        end = page.index("</details>", more)
        for field in CORE:
            self.assertTrue(start < page.index(f'data-context-field="{field}"') < more, field)
        for field in FOLDED:
            self.assertTrue(more < page.index(f'data-context-field="{field}"') < end, field)

    def test_every_pick_fills_an_existing_field_with_a_string_both_languages_define(self):
        page = _index()
        i18n = (WEB / "i18n.js").read_text(encoding="utf-8")
        english, chinese = i18n.split('"Simplified Chinese": {', 1)
        picks = re.findall(r'data-fills="([\w-]+)" data-i18n="(\w+)"', page)
        self.assertEqual({target for target, _ in picks}, {"decision-owner", "decision-type"})
        self.assertGreaterEqual(len(picks), 6)
        for target, key in picks:
            self.assertIn(f'id="{target}"', page)
            self.assertRegex(english, rf"\n\s+{key}: ")
            self.assertRegex(chinese, rf"\n\s+{key}: ")
        for key in ("decision_more", "decision_status_none", "decision_status_partial", "decision_status_ready"):
            self.assertRegex(english, rf"\n\s+{key}: ")
            self.assertRegex(chinese, rf"\n\s+{key}: ")

    def test_the_line_script_loads_after_the_app_it_follows(self):
        page = _index()
        self.assertLess(page.index('src="/static/js/app.js"'), page.index('src="/static/js/decision_context.js"'))

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_the_line_agrees_with_the_backend_gate_on_every_case(self):
        with TemporaryDirectory() as tmp:
            work = Path(tmp)
            for name in ("decision_context.js", "i18n.js"):
                (work / name).write_text((WEB / name).read_text(encoding="utf-8"), encoding="utf-8")
            (work / "run.mjs").write_text(_HARNESS, encoding="utf-8")
            result = subprocess.run([shutil.which("node"), str(work / "run.mjs"), json.dumps(CASES)], cwd=work,
                                    capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr[:500])
        lines = json.loads(result.stdout)
        expected_start = {"orientation": "No context yet", "decision_context_incomplete": None,
                          "decision_support": "All 4 starred fields filled"}
        for name, values in CASES.items():
            mode = DecisionContext(**values).assessment_mode if values else "orientation"
            line = lines[name]
            if mode == "decision_context_incomplete":
                answered = sum(bool(str(values.get(f, "")).strip()) for f in CORE)
                self.assertTrue(line.startswith(f"{answered} of the 4 starred fields filled"), (name, line))
            else:
                self.assertTrue(line.startswith(expected_start[mode]), (name, mode, line))


if __name__ == "__main__":
    unittest.main()
