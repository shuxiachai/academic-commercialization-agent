"""An anonymous visit to "/" lands on a home page, not on an empty workbench.

Production has been accounts-only with open sign-up since 2026-11-07, which
makes "/" the address a stranger arrives at from a link or a search result.
It used to render the workbench with the sign-in card over it: a blurred
tool with nothing in it, and no word on what the tool is for or who pays.
The landing says that first; the card opens from its buttons; the workbench
appears once someone is signed in. A stored session skips the landing, a
deep link still meets the card directly, and a deployment without accounts
(invite-only, by access code) keeps the card it always had.

The behaviour is exercised in tests/js/landing_contract.mjs with the shipped
app.js and api.js; the checks here keep the markup, strings and wiring that
harness relies on in place.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_WEB = _ROOT / "web"
_INDEX = (_WEB / "index.html").read_text(encoding="utf-8")
_APP = (_WEB / "static/js/app.js").read_text(encoding="utf-8")
_STRINGS = (_WEB / "static/js/i18n.js").read_text(encoding="utf-8")
_SCRIPT = Path(__file__).with_name("js") / "landing_contract.mjs"

SCENARIOS = (
    "anonymous_root", "anonymous_root_signup_closed", "anonymous_deep_link", "anonymous_codes_only",
    "signed_in", "ungated", "logout_goes_home", "logout_without_accounts_reloads",
)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_which_view_each_visitor_is_shown(scenario):
    node = shutil.which("node")
    assert node, "Node is required for the landing seam"
    result = subprocess.run([node, str(_SCRIPT), scenario], capture_output=True, text=True,
                            encoding="utf-8", cwd=_ROOT)
    assert result.returncode == 0, result.stderr or result.stdout
    assert f"PASS {scenario}" in result.stdout


def _landing_markup() -> str:
    start = _INDEX.index('id="landing"')
    return _INDEX[start:_INDEX.index('id="workbench"', start)]


def test_the_landing_is_in_the_page_before_the_workbench():
    """The landing is the first thing in the document and hidden until the boot decides."""
    assert re.search(r'<section class="landing" id="landing" hidden>', _INDEX)
    landing = _landing_markup()
    for control in ('id="landing-create"', 'id="landing-sign-in"', 'id="landing-sign-in-top"',
                    'id="landing-lang"', 'id="landing-sample-list"'):
        assert control in landing, control
    # The two things a visitor can do without an account, and the terms they would accept.
    assert landing.count('href="/samples"') >= 2
    assert 'href="/privacy"' in landing
    # The buttons are buttons: the card they open is in this document, not another page.
    assert re.search(r'<button type="button"[^>]*id="landing-create"', landing)
    assert re.search(r'<button type="button"[^>]*id="landing-sign-in"', landing)


def test_the_card_can_be_put_down_again_from_the_landing():
    gate = _INDEX[_INDEX.index('id="gate"'):]
    assert re.search(r'<button type="button"[^>]*id="gate-back"[^>]*hidden>', gate)


def test_every_landing_string_is_in_both_interface_languages():
    """i18n.apply() shows the key itself for a string one language lacks."""
    keys = set(re.findall(r'data-i18n="(landing_\w+)"', _landing_markup())) | {"gate_back"}
    assert len(keys) >= 18, sorted(keys)
    for key in sorted(keys):
        assert _STRINGS.count(f"    {key}: ") == 2, key


def test_the_landing_stylesheet_loads_with_the_page_and_the_focus_fix_covers_it():
    sheets = re.findall(r'<link rel="stylesheet" href="/static/css/(\w+)\.css">', _INDEX)
    assert "landing" in sheets and sheets.index("landing") > sheets.index("workbench")
    # While the card is up the landing is under its scrim, like the workbench:
    # neither may take a Tab stop or a click (gate_focus.js, e2e/keyboard_smoke.py).
    focus = (_WEB / "static/js/gate_focus.js").read_text(encoding="utf-8")
    assert '"#landing"' in focus


def test_the_boot_keeps_the_shape_the_other_harnesses_strip():
    """Several contracts cut the boot block with a regex on this exact call."""
    assert _APP.count("\nensureAccess().then(") == 1
    assert "function showLanding(" in _APP
