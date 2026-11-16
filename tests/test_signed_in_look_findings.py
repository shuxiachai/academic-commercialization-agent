"""Seven small things seen in an ordinary account on the live site, 2026-11-16.

None of them stopped anyone. Each was a place where the page said something
slightly untrue, or was harder to use than it had to be:

1. the key form's way out read "Add keys later" to an account whose keys
   were already saved;
2. a run's state in the history list was a coloured dot and nothing else;
3. a source whose title ran to 662 characters was drawn as a link 504 px
   tall on a phone;
4. on a phone the run button was 36 px and the menu button 30 px, where the
   other controls a thumb presses are 44;
5. the Chinese line of provider links ended its two lists with ASCII stops;
6. the saved model's field (2026-11-16) was too narrow for the name in it;
7. keys saved in the form that opens after sign-in left the composer saying
   keys were needed, until a reload (found while taking this change's
   pictures; composer_contract.mjs `needed_gate`).

An eighth was reported and is not here. The landing's own language select
read "English" while the interface was Chinese, seen in the hidden landing
of a signed-in page. Measured before changing anything: the landing is only
ever drawn at page load, signing out reloads the page, and on the landing
its own select is the only language control. No visitor could have seen it
wrong, so nothing was changed.

The behaviour is in the Node contracts (composer_contract.mjs `dismiss`,
sidebar_history_contract.mjs `states`); this file
holds the markup, the styles and the words.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
JS = WEB / "static" / "js"
CSS_DIR = WEB / "static" / "css"
INDEX = (WEB / "index.html").read_text(encoding="utf-8")
WORKBENCH = (CSS_DIR / "workbench.css").read_text(encoding="utf-8")
RESULT = (CSS_DIR / "result.css").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def strings():
    text = (JS / "i18n.js").read_text(encoding="utf-8")
    english, chinese = text.split('"Simplified Chinese": {', 1)

    def entry(table, key):
        found = re.search(rf'^\s+{key}: "((?:[^"\\]|\\.)*)"', table, re.M)
        assert found, key
        return found[1]

    return (lambda key: entry(english, key)), (lambda key: entry(chinese, key))


def coarse_rules(sheet: str) -> str:
    """Everything the sheet says inside `@media (pointer: coarse)`."""
    return "\n".join(re.findall(r"@media \(pointer: coarse\) \{(.*?)\n\}", sheet, re.S))


def test_the_key_forms_way_out_has_words_for_an_account_that_has_keys(strings):
    english, chinese = strings
    assert english("byok_close") == "Close" and chinese("byok_close") == "关闭"
    assert english("byok_skip") == "Add keys later" and chinese("byok_skip") == "稍后再添加"
    app = (JS / "app.js").read_text(encoding="utf-8")
    # One place decides the word, from the one fact that decides it, and the
    # language switch finds the same key on the element.
    assert 'const key = accountHasKeys() ? "byok_close" : "byok_skip";' in app
    assert "button.dataset.i18n = key;" in app


def test_a_runs_state_has_a_word_in_both_languages(strings):
    english, chinese = strings
    words = {"running": ("Running", "运行中"), "completed": ("Completed", "已完成"), "failed": ("Failed", "失败"),
             "cancelled": ("Cancelled", "已取消"), "timeout": ("Timed out", "已超时")}
    for state, (en, zh) in words.items():
        assert (english(f"run_state_{state}"), chinese(f"run_state_{state}")) == (en, zh), state
    # The same words the run page's own state pill uses in Chinese.
    run = (JS / "run.js").read_text(encoding="utf-8")
    for _en, zh in words.values():
        assert f'"{zh}"' in run, zh
    # Every state the list colours has a word; "unknown" keeps its own sentence.
    coloured = set(re.findall(r'\.runitem__state\[data-state="(\w+)"\]', WORKBENCH))
    assert coloured == set(words), coloured
    sidebar = (JS / "sidebar.js").read_text(encoding="utf-8")
    assert "visually-hidden" in sidebar and "run_state_" in sidebar
    assert re.search(r"^\.visually-hidden \{", (CSS_DIR / "base.css").read_text(encoding="utf-8"), re.M)


def test_a_source_title_is_drawn_in_at_most_six_lines_and_is_whole_in_the_page():
    """Cut for the eye only: the text stays in the page for a screen reader,
    for search and for the tests that read it, and a long one is also the
    link's tooltip."""
    rule = re.search(r"^\.source__link \{([^}]*)\}", RESULT, re.M)[1]
    for said in ("display: -webkit-box;", "-webkit-box-orient: vertical;", "-webkit-line-clamp: 6;", "line-clamp: 6;",
                 "overflow: hidden;", "overflow-wrap: anywhere;"):
        assert said in rule, said
    result = (JS / "result.js").read_text(encoding="utf-8")
    assert "if (shown.length > LONG_SOURCE_TITLE) title.title = shown;" in result
    assert re.search(r"^const LONG_SOURCE_TITLE = (\d+);", result, re.M)[1] == "160"
    assert "textContent.slice(" not in result[result.index("function renderSavedSource"):][:900], "The text itself is never cut"


def test_the_run_button_and_the_menu_button_are_thumb_sized_on_touch():
    rules = coarse_rules(WORKBENCH)
    for selector in (r"\.send-btn", r"#mobile-menu"):
        rule = re.search(rf"{selector} \{{([^}}]*)\}}", rules)
        assert rule, selector
        assert re.search(r"width: 44px; height: 44px;", rule[1]), selector
    # For a pointer they stay as they were.
    assert re.search(r"^\.send-btn \{\s*width: 36px; height: 36px;", WORKBENCH, re.M)
    assert re.search(r"^\.icon-btn \{\s*width: 30px; height: 30px;", WORKBENCH, re.M)


def test_the_provider_links_line_stops_as_its_language_does():
    fields = (JS / "byok_fields.js").read_text(encoding="utf-8")
    english, chinese = fields.split('"Simplified Chinese": {', 1)
    assert '    byok_keys_stop: ".",' in english and '    byok_keys_stop: "。",' in chinese
    line = re.search(r'<p class="gate__hint" id="byok-links">.*?</p>', INDEX, re.S)[0]
    assert line.count('<span data-byok-i18n="byok_keys_stop">.</span>') == 2
    assert not re.search(r"</a>\s*\.", line), "No stop left in the markup, where no language can change it"
    # The Chinese sentence after them ends with its own stop already.
    assert re.search(r'byok_keys_json: "[^"]*。",', chinese)


def test_the_saved_models_field_has_room_for_a_name():
    """Beside its button it had 185 px on a desktop and 155 on a phone, and
    cut a 22-character name. With a basis the row cannot give it beside the
    button, the button goes below and the field takes the row."""
    rule = re.search(r"\.gate__saved-model \.gate__input \{([^}]*)\}", WORKBENCH)[1]
    basis = int(re.search(r"flex: 1 1 (\d+)px;", rule)[1])
    assert basis >= 260, basis
    assert "min-width: 0" in rule
    assert "flex-wrap: wrap" in re.search(r"\.gate__saved-model \{([^}]*)\}", WORKBENCH)[1]
