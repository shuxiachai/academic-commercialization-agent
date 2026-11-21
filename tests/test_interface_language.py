"""The interface language a first visit opens in, and a reader's own choice after it.

Measured on the public site on 2026-11-21 (signed out): a browser whose
navigator.language was "zh-CN", with no language saved, opened the landing in
English, `<html lang="en">`, and the only way to Chinese was the small "EN"
select in the header. i18n.js began every page in English unless a choice was
stored.

The rule now, in i18n.js and nowhere else: a choice the reader made is kept
and wins; without one, the browser's first preferred language decides,
Simplified Chinese for any "zh" tag and English for everything else. The
guess is never written down, so only a choice is remembered and a browser set
to another language later is followed. The landing, the workbench, the sample
reader, the privacy page and the operator's console all read their language
from this one module (the last test below holds them to it).

tests/js/interface_language_contract.mjs runs the shipped i18n.js for each
case; e2e/language_smoke.py opens the real pages in Chromium with each
browser language.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "tests/js/interface_language_contract.mjs"
_ENGLISH_TITLE = "Paper in, cited commercialization triage out."


def _open(case: dict) -> dict:
    node = shutil.which("node")
    assert node, "Node is required for the interface-language seam"
    result = subprocess.run([node, str(_SCRIPT), json.dumps(case)], capture_output=True, text=True,
                            encoding="utf-8", cwd=_ROOT)
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


def _chinese(report: dict) -> bool:
    return (report["language"], report["locale"], report["lang"]) == ("Simplified Chinese", "zh-CN", "zh-CN")


def _english(report: dict) -> bool:
    return (report["language"], report["locale"], report["lang"]) == ("English", "en-GB", "en")


@pytest.mark.parametrize("languages", [["zh-CN", "en-US"], ["zh"], ["zh-TW"], ["zh-Hans-CN"], ["ZH-cn"]])
def test_a_first_visit_from_a_chinese_browser_opens_in_chinese(languages):
    report = _open({"navigator": {"languages": languages, "language": languages[0]}})
    assert _chinese(report), report
    assert report["title"] != _ENGLISH_TITLE
    assert report["writes"] == [], "The guess is not saved: only a reader's choice is"


@pytest.mark.parametrize("languages", [["en-US"], ["en-US", "zh-CN"], ["fr-FR", "zh"], ["ja-JP"], ["zhuyin"]])
def test_a_first_visit_from_any_other_browser_opens_in_english(languages):
    """Only the first preferred language counts: a reader who put English
    first and Chinese second asked for English."""
    report = _open({"navigator": {"languages": languages, "language": languages[0]}})
    assert _english(report), report
    assert report["title"] == _ENGLISH_TITLE
    assert report["writes"] == []


def test_a_browser_that_lists_no_languages_is_read_by_its_one_language():
    assert _chinese(_open({"navigator": {"languages": [], "language": "zh-CN"}}))
    assert _english(_open({"navigator": {"languages": [], "language": "en-AU"}}))


@pytest.mark.parametrize("case", [
    {"navigator": {"throws": True}},
    {"navigator": {}},
    {},
    # A script host without a page: Node has had a navigator of its own since
    # version 21, and it says the machine's locale ("zh-CN" on the machine this
    # was written on, "en-US" on CI). Every test that imports i18n.js would
    # read different strings on the two if the module listened to it.
    {"window": False, "hostNavigator": {"languages": ["zh-CN"], "language": "zh-CN"}},
])
def test_a_browser_language_that_cannot_be_read_means_english(case):
    assert _english(_open(case))


@pytest.mark.parametrize(("stored", "languages", "expected"), [
    ("English", ["zh-CN"], "English"),
    ("Simplified Chinese", ["en-US"], "Simplified Chinese"),
    ("English", ["en-US"], "English"),
    ("Simplified Chinese", ["zh-CN"], "Simplified Chinese"),
])
def test_a_choice_the_reader_made_wins_over_the_browser(stored, languages, expected):
    report = _open({"stored": stored, "navigator": {"languages": languages}})
    assert report["language"] == expected
    assert report["writes"] == []


def test_a_stored_value_that_is_no_language_of_the_interface_is_no_choice():
    """What an older page or another script may have left under the key
    neither breaks the page nor stands in for a choice: the browser decides."""
    assert _chinese(_open({"stored": "Klingon", "navigator": {"languages": ["zh-CN"]}}))
    assert _english(_open({"stored": "", "navigator": {"languages": ["en-US"]}}))


@pytest.mark.parametrize("storage", ["throws", "denies-writes"])
def test_storage_that_cannot_be_used_still_follows_the_browser(storage):
    """A private window or blocked site data: reading or writing may throw,
    and the page still opens in the browser's language and still switches."""
    for languages, chinese in ((["zh-CN"], True), (["en-US"], False)):
        report = _open({"storage": storage, "navigator": {"languages": languages}, "then": "English"})
        assert _chinese(report) if chinese else _english(report), report
        assert report["after_choice"]["language"] == "English"
        assert report["after_choice"]["lang"] == "en"


def test_a_choice_is_remembered_and_the_next_visit_keeps_it():
    """The zh-CN reader who picked English once: English on every later
    visit, although the browser still prefers Chinese. And the other way."""
    report = _open({"navigator": {"languages": ["zh-CN"]}, "then": "English"})
    assert _chinese(report)
    assert report["after_choice"] == {"language": "English", "lang": "en", "writes": [["ui-language", "English"]]}
    assert report["next_visit"] == "English"

    report = _open({"navigator": {"languages": ["en-US"]}, "then": "Simplified Chinese"})
    assert _english(report)
    assert report["after_choice"]["writes"] == [["ui-language", "Simplified Chinese"]]
    assert report["next_visit"] == "Simplified Chinese"


def test_one_rule_for_every_page_and_it_is_i18n_js():
    """The landing, the workbench, the sample reader, the privacy page and
    the operator's console each read the language from i18n.js and decide
    nothing about it themselves: no other script reads the browser's language
    or the saved choice, so the pages cannot disagree."""
    scripts = sorted((_ROOT / "web/static/js").glob("*.js"))
    assert len(scripts) > 10
    for script in scripts:
        if script.name == "i18n.js":
            continue
        source = script.read_text(encoding="utf-8")
        assert not re.search(r"navigator\s*\.\s*languages?\b", source), script.name
        assert "ui-language" not in source, script.name
    for page, module in (("index.html", "app.js"), ("samples.html", "samples.js"),
                         ("privacy.html", "privacy.js"), ("admin.html", "admin.js")):
        html = (_ROOT / "web" / page).read_text(encoding="utf-8")
        assert f'src="/static/js/{module}"' in html, page
        script = (_ROOT / "web/static/js" / module).read_text(encoding="utf-8")
        assert re.search(r'^import \* as i18n from "\./i18n\.js";$', script, re.M), module
    source = (_ROOT / "web/static/js/i18n.js").read_text(encoding="utf-8")
    assert source.count('"ui-language"') == 1, "One key, named once"


# The smokes whose browsers open documents of their own, not the main app's
# pages: none of these documents or their scripts loads i18n.js. The receipt
# smoke's browser fixture also opens the locator page for
# source_locator_production_smoke, whose own context opens the main pages.
_OWN_DOCUMENTS = {
    "saved_source_smoke.py": ("web/saved-source-lab",),
    "saved_source_receipt_smoke.py": ("web/saved-source-receipts", "web/source-locator"),
    "saved_source_receipt_qwen_canary.py": ("web/saved-source-receipts",),
    "saved_source_usage_smoke.py": ("web/saved-source-usage",),
}


def test_every_smoke_that_opens_the_main_pages_says_which_browser_language():
    """A first visit follows the browser's language now, and Chromium under
    Playwright takes the system's unless told: "zh-CN" on the machine this
    was written on, "en-US" on CI. A smoke whose browser names no language
    would read the pages in Chinese on one and English on the other, and
    assert on different words. Every browser context that can reach a page
    built on i18n.js names its locale. The saved-source smokes open their own
    documents, which load no i18n.js, and are left as they are (one of them is
    part of a frozen experiment's identity)."""
    checked = 0
    for path in sorted((_ROOT / "e2e").glob("*.py")):
        calls = [node for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                 and node.func.attr == "new_context"]
        if path.name in _OWN_DOCUMENTS:
            assets = [asset for folder in _OWN_DOCUMENTS[path.name] for asset in (_ROOT / folder).rglob("*")
                      if asset.suffix in {".html", ".js"}]
            assert assets, path.name
            for asset in assets:
                assert "i18n.js" not in asset.read_text(encoding="utf-8"), asset
            continue
        for call in calls:
            assert any(keyword.arg == "locale" for keyword in call.keywords), f"{path.name}:{call.lineno}"
            checked += 1
    assert checked >= 13, checked
