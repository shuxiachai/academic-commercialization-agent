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


def test_dark_theme_redefines_every_colour_token():
    """A colour left out of the dark block would show a paper value on charcoal."""
    light_block = TOKENS.split("@media (prefers-color-scheme: dark)", 1)[0]
    dark_block = TOKENS.split("@media (prefers-color-scheme: dark)", 1)[1].split("@media", 1)[0]
    light, dark = _declared(light_block), _declared(dark_block)
    colours = {name for name, value in light.items()
               if re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", value)}
    assert colours, "no colour tokens found"
    assert colours <= set(dark), sorted(colours - set(dark))


def test_both_pages_declare_both_colour_schemes():
    for page in ("web/index.html", "web/samples.html"):
        html = (ROOT / page).read_text(encoding="utf-8")
        assert '<meta name="color-scheme" content="light dark">' in html, page


def test_component_styles_take_colours_from_tokens():
    """Hard-coded colours outside tokens.css would ignore the theme."""
    for name in ("base", "workbench", "result", "samples"):
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
