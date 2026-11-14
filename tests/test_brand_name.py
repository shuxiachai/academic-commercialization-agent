"""One name for the product, on every page.

On 2026-11-13 a visitor met four: the landing header said "Academic
Commercialization Assessment", the browser tab "Commercialization
Assessment", the sidebar and the sample, privacy and console headers
"Assessment", and the Chinese interface "商业化评估" beside a landing that said
"学术成果商业化评估". The link preview added a fifth ("... Assessment Agent").

The name is "Academic Commercialization Assessment", in Chinese
"学术成果商业化评估". Where there is no room for it (the sidebar, a header on a
phone) it is "ACA" in both languages, the letters of the mark beside it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_WEB = Path(__file__).resolve().parents[1] / "web"
_FULL = "Academic Commercialization Assessment"
_FULL_ZH = "学术成果商业化评估"
_SHORT = "ACA"
_PAGES = {"index.html": "", "samples.html": "Sample reports · ", "privacy.html": "Privacy and terms · ",
          "admin.html": "Console · "}


def _read(name: str) -> str:
    return (_WEB / name).read_text(encoding="utf-8")


def _strings(language: str) -> str:
    english, chinese = _read("static/js/i18n.js").split('"Simplified Chinese": {', 1)
    return english if language == "English" else chinese


def test_the_strings_state_the_name_once_in_each_language():
    assert f'    brand_full: "{_FULL}",' in _strings("English")
    assert f'    brand_full: "{_FULL_ZH}",' in _strings("Simplified Chinese")
    for language in ("English", "Simplified Chinese"):
        assert f'    brand: "{_SHORT}",' in _strings(language), language
        assert "landing_brand" not in _strings(language), "the landing has no name of its own"


@pytest.mark.parametrize("page,prefix", _PAGES.items())
def test_the_browser_tab_says_the_name_in_full(page, prefix):
    assert re.search(r"<title>([^<]*)</title>", _read(page))[1] == prefix + _FULL


@pytest.mark.parametrize("page", ["index.html", "samples.html"])
def test_a_link_preview_says_the_name_in_full(page):
    text = _read(page)
    assert re.search(r'<meta property="og:site_name" content="([^"]*)">', text)[1] == _FULL
    title = re.search(r'<meta property="og:title" content="([^"]*)">', text)[1]
    assert title.endswith(_FULL), title


@pytest.mark.parametrize("page", _PAGES)
def test_a_header_says_the_name_in_full_and_the_short_one_where_it_is_narrow(page):
    """Every page header carries both, and the style sheet they all load
    picks one by width; the workbench's sidebar, which is narrow at every
    width, carries the short one alone."""
    text = _read(page)
    names = re.findall(r'<span class="brand__name"[^>]*>(.*?)</span>\s*</a>', text, re.S)
    headers = [name for name in names if "brand__full" in name]
    assert headers, page
    for name in headers:
        assert re.fullmatch(
            rf'<span class="brand__full" data-i18n="brand_full">{_FULL}</span>'
            rf'<span class="brand__short" data-i18n="brand">{_SHORT}</span>', name.strip()), name
    for name in names:
        if "brand__full" not in name:
            assert page == "index.html" and name == _SHORT, (page, name)
    assert text.count('aria-label="' + _FULL + '"') >= len(headers)
    if page == "index.html":
        assert len(names) == 3 and len(headers) == 1, "the landing header, and the sidebar's two"
        assert text.count(f'<span class="brand__name" data-i18n="brand">{_SHORT}</span>') == 2


def test_the_width_at_which_the_short_name_takes_over_is_in_the_shared_style_sheet():
    base = _read("static/css/base.css")
    assert re.search(r"\.brand__short\s*\{\s*display:\s*none;\s*\}", base)
    rule = re.search(r"@media \(max-width: (\d+)px\) \{\s*\.brand__full\s*\{\s*display:\s*none;\s*\}"
                     r"\s*\.brand__short\s*\{\s*display:\s*inline;\s*\}\s*\}", base)
    assert rule and 480 <= int(rule[1]) <= 767, "a phone gets the short name; a tablet has room for the full one"
    for page in _PAGES:
        assert '<link rel="stylesheet" href="/static/css/base.css">' in _read(page), page


def test_no_page_or_script_says_part_of_the_name():
    """A title built in a script (the privacy page, the console, a finished
    run's tab) must use the same name, not a shorter one of its own."""
    files = [*_WEB.glob("*.html"), *(_WEB / "static" / "js").glob("*.js")]
    assert len(files) > 20
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"Commercialization Assessment", text):
            assert text[max(0, match.start() - 9):match.start()] == "Academic ", (path.name, text[match.start() - 40:match.end()])
        for match in re.finditer(r"商业化评估", text):
            assert text[max(0, match.start() - 4):match.start()] == "学术成果", (path.name, text[match.start() - 20:match.end()])
        assert not re.search(r'>Assessment</span>|brand: "Assessment"', text), path.name


def test_the_scripts_that_set_a_title_use_the_shared_name():
    privacy = _read("static/js/privacy.js")
    admin = _read("static/js/admin.js")
    for name, text in (("privacy.js", privacy), ("admin.js", admin)):
        assert 'i18n.t("brand_full")' in text, name
        assert 'node.textContent = i18n.t(node.dataset.i18n)' in text, f"{name} paints its header's name"
