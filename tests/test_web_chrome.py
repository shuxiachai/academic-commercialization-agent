"""Static contracts for the workbench chrome: phone menu and the two themes."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "web/index.html").read_text(encoding="utf-8")
TOKENS = (ROOT / "web/static/css/tokens.css").read_text(encoding="utf-8")


def _declared(block: str) -> dict[str, str]:
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block))


def test_phone_menu_controls_the_sidebar_and_loads_after_app_js():
    """Below 860px the sidebar's own toggle is off-screen; this button is the way in."""
    assert re.search(r'<button[^>]*id="mobile-menu"[^>]*aria-controls="sidebar"', INDEX, re.S)
    assert 'id="sidebar-scrim" hidden' in INDEX
    scripts = re.findall(r'<script type="module" src="/static/js/(\w+)\.js"></script>', INDEX)
    assert scripts.index("chrome") > scripts.index("app")


def test_phone_menu_labels_exist_in_both_interface_languages():
    source = (ROOT / "web/static/js/chrome.js").read_text(encoding="utf-8")
    english, chinese = source.split('"Simplified Chinese":', 1)
    keys = set(re.findall(r"(\w+):", english.split("English:", 1)[1].split("}", 1)[0]))
    assert keys == {"open", "close"}
    assert keys == set(re.findall(r"(\w+):", chinese.split("}", 1)[0]))
    # app.js's browser contracts strip and inject its imports; the chrome is
    # loaded beside it, never through it.
    assert "chrome.js" not in (ROOT / "web/static/js/app.js").read_text(encoding="utf-8")


def test_keyboard_focus_fixes_load_beside_app_js():
    """#237: the gate's inert workbench and a file input that is not a Tab stop.

    e2e/keyboard_smoke.py checks the behaviour in Chromium; this keeps the
    wiring it depends on in place in every pytest cell.
    """
    scripts = re.findall(r'<script type="module" src="/static/js/(\w+)\.js"></script>', INDEX)
    assert scripts.index("gate_focus") > scripts.index("app")
    assert "gate_focus.js" not in (ROOT / "web/static/js/app.js").read_text(encoding="utf-8")
    # #attach-btn opens the file picker; the input itself is visually hidden.
    assert re.search(r'<input type="file" id="pdf-input"[^>]*class="visually-hidden"[^>]*tabindex="-1"', INDEX)
    assert '<button type="button" class="chip-btn" id="attach-btn"' in INDEX


def test_starter_topics_have_a_chinese_entry_for_every_button():
    """A Chinese reader got English starters, and so English reports under "auto"."""
    buttons = re.findall(r'<button type="button" class="starter" data-topic="([^"]+)">', INDEX)
    source = (ROOT / "web/static/js/starters.js").read_text(encoding="utf-8")
    table = source.split('"Simplified Chinese":', 1)[1].split("}", 1)[0]
    chinese = re.findall(r'\["([^"]+)", "([^"]+)"\]', table)
    assert len(buttons) == len(chinese) == 3
    for text, topic in chinese:
        assert re.search(r"[一-鿿]", text) and re.search(r"[一-鿿]", topic)
    scripts = re.findall(r'<script type="module" src="/static/js/(\w+)\.js"></script>', INDEX)
    assert scripts.index("starters") > scripts.index("app")
    app = (ROOT / "web/static/js/app.js").read_text(encoding="utf-8")
    # Rewriting data-topic is enough only while app.js reads it at click time.
    assert "topic.value = btn.dataset.topic;" in app
    assert "starters.js" not in app


def _block(selector: str) -> str:
    """The declarations of the one rule whose selector is exactly `selector`."""
    return re.search(re.escape(selector) + r" \{\n(.*?)\n\s*\}", TOKENS, re.S).group(1)


# The dark palette applies on a dark system unless the reader chose light, and
# whenever the reader chose dark (theme.js sets data-theme on the root).
SYSTEM_DARK = ':root:not([data-theme="light"])'
CHOSEN_DARK = ':root[data-theme="dark"]'


def test_dark_theme_redefines_every_colour_token():
    """A colour left out of the dark block would show a paper value on charcoal."""
    light_block = TOKENS.split("@media (prefers-color-scheme: dark)", 1)[0]
    light = _declared(light_block)
    colours = {name for name, value in light.items()
               if re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", value)}
    assert colours, "no colour tokens found"
    for selector in (SYSTEM_DARK, CHOSEN_DARK):
        dark = _declared(_block(selector))
        assert colours <= set(dark), (selector, sorted(colours - set(dark)))


def test_chosen_dark_matches_the_system_dark_palette():
    """CSS cannot share one block between a media query and an attribute selector,
    so the reader's dark choice and a dark system must not drift apart."""
    assert _declared(_block(SYSTEM_DARK)) == _declared(_block(CHOSEN_DARK))
    assert "@media (prefers-color-scheme: dark) {\n  " + SYSTEM_DARK in TOKENS


def test_choosing_light_beats_a_dark_system():
    """Without this, a reader on a dark system could never pick light."""
    assert ":root[data-theme=\"light\"]" in TOKENS
    assert "color-scheme: light" in _block(':root[data-theme="light"]')
    assert "color-scheme: dark" in _block(SYSTEM_DARK) and "color-scheme: dark" in _block(CHOSEN_DARK)


def test_theme_toggle_sits_in_the_sidebar_and_loads_after_app_js():
    """#234: the toggle is a sidebar-footer button handled by its own module."""
    foot = INDEX.split('class="sidebar__foot"', 1)[1].split("</aside>", 1)[0]
    assert re.search(r'<button type="button" class="icon-btn" id="theme-toggle"[^>]*aria-label="[^"]+"', foot)
    scripts = re.findall(r'<script type="module" src="/static/js/(\w+)\.js"></script>', INDEX)
    assert scripts.index("theme") > scripts.index("app")
    assert "theme.js" not in (ROOT / "web/static/js/app.js").read_text(encoding="utf-8")


def test_every_page_with_the_palette_applies_the_saved_theme():
    """#234: a choice made in the workbench must also reach the pages that share
    tokens.css, or they would show the system theme instead."""
    pages = [path for path in sorted((ROOT / "web").glob("*.html"))
             if "/static/css/tokens.css" in path.read_text(encoding="utf-8")]
    assert {path.name for path in pages} >= {"index.html", "samples.html", "privacy.html", "admin.html"}
    for path in pages:
        assert '<script type="module" src="/static/js/theme.js"></script>' in path.read_text(encoding="utf-8"), path.name


def test_theme_toggle_labels_exist_in_both_interface_languages():
    source = (ROOT / "web/static/js/theme.js").read_text(encoding="utf-8")
    english, chinese = source.split('"Simplified Chinese":', 1)
    keys = set(re.findall(r"(\w+):", english.split("English:", 1)[1].split("}", 1)[0]))
    assert keys == {"toDark", "toLight"}
    assert keys == set(re.findall(r"(\w+):", chinese.split("}", 1)[0]))
    assert re.search(r"[一-鿿]", chinese.split("}", 1)[0])


def test_theme_choice_is_stored_defensively_and_only_on_a_press():
    """Blocked site data must not break the page, and nothing is stored (so the page
    keeps following the system) until the reader presses the toggle."""
    source = (ROOT / "web/static/js/theme.js").read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    assert re.search(r"try \{\s*const value = localStorage\.getItem\(KEY\)", code)
    assert re.search(r"try \{\s*localStorage\.setItem\(KEY, theme\)", code)
    assert code.count("localStorage.setItem") == 1
    # The only caller of remember() is the click handler.
    assert code.count("remember(") == 2  # its definition and that one call
    handler = code.split('button?.addEventListener("click"', 1)[1].split("});", 1)[0]
    assert "remember(next)" in handler


def test_both_pages_declare_both_colour_schemes():
    for page in ("web/index.html", "web/samples.html"):
        html = (ROOT / page).read_text(encoding="utf-8")
        assert '<meta name="color-scheme" content="light dark">' in html, page


def test_component_styles_take_colours_from_tokens():
    """Hard-coded colours outside tokens.css would ignore the theme."""
    for name in ("base", "workbench", "result", "samples", "landing"):
        css = (ROOT / f"web/static/css/{name}.css").read_text(encoding="utf-8")
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        css = re.sub(r'url\("data:image/svg\+xml[^"]*"\)', "", css)
        assert not re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", css), name


def test_toasts_never_take_a_click():
    """Text-only toasts stacked over a phone's short report must not block it."""
    css = (ROOT / "web/static/css/workbench.css").read_text(encoding="utf-8")
    rule = re.search(r"\n\.toast \{(.*?)\n\}", css, re.S).group(1)
    assert "pointer-events: none;" in rule
    assert "<button" not in (ROOT / "web/static/js/app.js").read_text(encoding="utf-8").split(
        "function toast(", 1)[1].split("\n}\n", 1)[0]
