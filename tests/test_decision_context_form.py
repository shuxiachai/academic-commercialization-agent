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


# The form's own behaviour, with a document that holds only what the module
# asks of it: the fields, the picks beside two of them, and the fold. Each
# field reports the height its text needs (`needs`), as a browser's
# scrollHeight does, and a one-pixel border on each side.
_FORM_HARNESS = """
const listeners = (node) => (node.listeners ??= {});
const element = (extra = {}) => ({
  value: "", textContent: "", dataset: {}, style: {}, attributes: {}, needs: 0, focused: 0,
  get scrollHeight() { return this.needs; },
  get clientHeight() { return this.needs ? 60 : 0; },
  get offsetHeight() { return this.needs ? 62 : 0; },
  addEventListener(type, handler) { (listeners(this)[type] ??= []).push(handler); },
  dispatchEvent(event) { for (const handler of listeners(this)[event.type] ?? []) handler(event); },
  setAttribute(name, value) { this.attributes[name] = String(value); },
  focus() { this.focused += 1; },
  ...extra,
});
const field = (tagName, name) => element({ tagName, dataset: { contextField: name } });
const fields = {
  "decision-asset": field("TEXTAREA", "asset_description"),
  "decision-owner": field("INPUT", "decision_owner"),
  "decision-type": field("INPUT", "decision_type"),
};
const pick = (fills, text) => element({ textContent: text, dataset: { fills } });
const picks = [pick("decision-owner", "Investor"), pick("decision-owner", " Technology transfer office "),
  pick("decision-type", "License the technology")];
const line = element();
const fold = element();
const language = element();
globalThis.window = element();
globalThis.Event = class { constructor(type) { this.type = type; } };
globalThis.document = {
  querySelector: (selector) => ({ "#decision-context-status": line, "#ui-lang": language }[selector] ?? null),
  querySelectorAll: (selector) => (selector === "[data-context-field]" ? Object.values(fields)
    : selector === "[data-fills]" ? picks : selector.includes("details") || selector.includes("decision-context") ? [fold] : []),
  getElementById: (id) => fields[id] ?? null,
};
const { fitHeight, pickChosen } = await import("./decision_context.js");
const pressed = () => picks.map((p) => p.attributes["aria-pressed"]);
const out = { atStart: pressed() };

picks[1].dispatchEvent(new Event("click"));
out.afterPick = { value: fields["decision-owner"].value, pressed: pressed(), focused: fields["decision-owner"].focused };
picks[0].dispatchEvent(new Event("click"));
out.afterOtherPick = { value: fields["decision-owner"].value, pressed: pressed() };
fields["decision-owner"].value = "Investor and board";
fields["decision-owner"].dispatchEvent(new Event("input"));
out.afterTyping = pressed();
fields["decision-owner"].value = "  Investor ";
fields["decision-owner"].dispatchEvent(new Event("input"));
out.typedTheSameWords = pressed();
// The interface language changes: the pick now reads otherwise, the field keeps what it put there.
// And an answer typed in the other language is the pick's words once the pick is named in it.
fields["decision-type"].value = "许可该技术";
fields["decision-type"].dispatchEvent(new Event("input"));
out.typedInTheOtherLanguage = pressed();
picks[0].textContent = "投资人";
picks[2].textContent = "许可该技术";
language.dispatchEvent(new Event("change"));
out.afterLanguage = pressed();

const asset = fields["decision-asset"];
asset.value = "long text";
asset.needs = 140;
asset.dispatchEvent(new Event("input"));
out.grown = asset.style.height;
asset.needs = 44;
asset.dispatchEvent(new Event("input"));
out.shrunk = asset.style.height;
// Folded away, a field measures nothing: its height is left to its rows.
asset.needs = 0;
asset.dispatchEvent(new Event("input"));
out.folded = asset.style.height;
// Opened again, and the window made narrower: measured again each time.
asset.needs = 96;
fold.dispatchEvent(new Event("toggle"));
out.opened = asset.style.height;
asset.needs = 180;
window.dispatchEvent(new Event("resize"));
out.resized = asset.style.height;
// A one-line field is never given a height.
out.input = fields["decision-owner"].style.height ?? null;
out.pure = [pickChosen("Investor", "Investor"), pickChosen("Investor", ""), pickChosen("Investor", "investor")];
out.fit = [fitHeight({ style: {}, scrollHeight: 0 }), fitHeight(null)];
console.log(JSON.stringify(out));
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

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_a_pick_shows_as_chosen_and_a_long_answer_is_shown_whole(self):
        """Seen on 2026-11-18: a description of four lines in "Asset or
        research output" showed its last three with no sign of the first, and
        a pressed pick looked like the three beside it once the pointer left.
        A pick is now marked while its field holds what it put there, and a
        multi-line field is as tall as its text."""
        with TemporaryDirectory() as tmp:
            work = Path(tmp)
            for name in ("decision_context.js", "i18n.js"):
                (work / name).write_text((WEB / name).read_text(encoding="utf-8"), encoding="utf-8")
            (work / "run.mjs").write_text(_FORM_HARNESS, encoding="utf-8")
            result = subprocess.run([shutil.which("node"), str(work / "run.mjs")], cwd=work,
                                    capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr[:800])
        seen = json.loads(result.stdout)
        self.assertEqual(seen["atStart"], ["false", "false", "false"], "nothing is chosen in an empty form")
        self.assertEqual(seen["afterPick"], {"value": "Technology transfer office", "focused": 1,
                                             "pressed": ["false", "true", "false"]})
        self.assertEqual(seen["afterOtherPick"], {"value": "Investor", "pressed": ["true", "false", "false"]},
                         "one field holds one answer, so one pick of its group is marked")
        self.assertEqual(seen["afterTyping"], ["false", "false", "false"], "an edited answer is the visitor's own")
        self.assertEqual(seen["typedTheSameWords"], ["true", "false", "false"],
                         "the words decide, however they got there and whatever surrounds them")
        self.assertEqual(seen["typedInTheOtherLanguage"], ["true", "false", "false"])
        self.assertEqual(seen["afterLanguage"], ["true", "false", "true"],
                         "the field still holds what the first pick put there, under the pick's new name; "
                         "and the picks are looked at again when their names change")
        # The height is what the text needs plus the field's two borders.
        self.assertEqual([seen["grown"], seen["shrunk"]], ["142px", "46px"])
        self.assertEqual(seen["folded"], "auto", "a field that measures nothing keeps the height its rows give it")
        self.assertEqual([seen["opened"], seen["resized"]], ["98px", "182px"])
        self.assertIsNone(seen["input"])
        self.assertEqual(seen["pure"], [True, False, False])
        self.assertEqual(seen["fit"], [None, None])

    def test_the_form_styles_a_chosen_pick_and_lets_a_field_grow(self):
        css = (ROOT / "web/static/css/workbench.css").read_text(encoding="utf-8")
        self.assertRegex(css, r'\.decision-pick\[aria-pressed="true"\]\s*\{[^}]*var\(--accent')
        grow = re.search(r"\.decision-context__grid textarea\s*\{([^}]*)\}", css)
        self.assertIsNotNone(grow)
        # The script sets the height; a drag handle would fight it, and a
        # ceiling keeps a pasted page from pushing the run button off screen.
        self.assertIn("resize: none", grow[1])
        self.assertRegex(grow[1], r"max-height:\s*[^;]+;")
        self.assertIn("overflow-y: auto", grow[1])
        # A short answer beside a long one keeps its own height, under its label.
        self.assertIn("align-content: start", re.search(r"\.decision-context__grid label\s*\{([^}]*)\}", css)[1])
        # Every pick is a toggle to assistive technology from the first paint.
        picks = re.findall(r'<button type="button" class="chip-btn decision-pick"([^>]*)>', _index())
        self.assertGreaterEqual(len(picks), 8)
        for attributes in picks:
            self.assertIn('aria-pressed="false"', attributes)


if __name__ == "__main__":
    unittest.main()
