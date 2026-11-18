"""A page whose first request got no answer about the visitor says so.

The page boots on one request, /api/access/check. A 200 lets the visitor in
and a 401 shows the landing or the sign-in card. Anything else used to be
thrown past the page: the landing was put away, the workbench was shown to
someone nobody had let in, and nothing was said. Since 2026-11-17 the request
limiter counts what the access gate refuses, so a visitor without an identity
whose address is out of budget is answered 429 at that request and met
exactly that. Reproduced in a browser against the real limiter on 2026-11-18
before this change: `data-boot` stayed at "scripts", the landing was gone,
and the page showed the empty composer.

The page now shows a notice in place of everything else: what happened (told
to wait, nothing answered, or the server failed), and a button that loads
the page again.

Which notice each boot shows is exercised with the shipped app.js and api.js
in tests/js/landing_contract.mjs (run from tests/test_landing_page.py), and
in Chromium by e2e/keyboard_smoke.py. The checks here keep in place what
those rely on: the markup, the strings in both languages, the styles, and
the limiter's answer the fixtures copy.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_WEB = _ROOT / "web"
_INDEX = (_WEB / "index.html").read_text(encoding="utf-8")
_APP = (_WEB / "static/js/app.js").read_text(encoding="utf-8")
_STRINGS = (_WEB / "static/js/i18n.js").read_text(encoding="utf-8")
_STYLES = (_WEB / "static/css/workbench.css").read_text(encoding="utf-8")
_MAIN = (_ROOT / "api/main.py").read_text(encoding="utf-8")
_CONTRACT = (_ROOT / "tests/js/landing_contract.mjs").read_text(encoding="utf-8")
_KEYBOARD_SMOKE = (_ROOT / "e2e/keyboard_smoke.py").read_text(encoding="utf-8")

_KEYS = ("boot_failure_title", "boot_failure_rate_limited", "boot_failure_server", "boot_failure_retry", "msg_network")


def _notice() -> str:
    start = _INDEX.index('<section class="boot-failure"')
    return _INDEX[start:_INDEX.index("</section>", start)]


def test_the_notice_is_in_the_page_hidden_and_outside_what_it_replaces():
    opening = _notice().split(">", 1)[0]
    assert 'id="boot-failure"' in opening
    assert re.search(r"\shidden$", opening), "Shown only by a boot that failed"
    assert 'role="alert"' in opening, "Announced when it appears: nothing else on the page will be"
    # The landing, the workbench and the gate are hidden while it shows, so it
    # cannot be inside any of them.
    at = _INDEX.index('id="boot-failure"')
    for other in ('id="landing"', 'id="workbench"', 'id="gate"'):
        assert at < _INDEX.index(other), other
    assert _INDEX.count('id="boot-failure"') == 1


def test_the_notice_has_a_title_a_reason_and_a_way_to_try_again():
    notice = _notice()
    assert '<h1 class="boot-failure__title" id="boot-failure-title"></h1>' in notice
    assert '<p class="boot-failure__text" id="boot-failure-text"></p>' in notice
    button = re.search(r"<button[^>]*id=\"boot-failure-retry\"[^>]*>([^<]*)</button>", notice)
    assert button, notice
    assert 'type="button"' in button.group(0)
    assert 'data-i18n="boot_failure_retry"' in button.group(0)
    assert button.group(1) == "Try again", "What the markup says before the script runs is the English string"


def test_every_string_of_the_notice_is_in_both_interface_languages():
    """i18n shows the key itself for a string one language lacks."""
    for key in _KEYS:
        assert _STRINGS.count(f"    {key}: ") == 2, key
    english = dict(re.findall(r'^    (boot_failure_\w+): "([^"]*)",$', _STRINGS, re.M)[:4])
    assert english["boot_failure_retry"] == "Try again"
    # What a visitor is told to do must be something that works: the limiter
    # adds five requests a second, so seconds, not minutes.
    assert "Try again in a few seconds" in english["boot_failure_rate_limited"]
    for text in english.values():
        assert "429" not in text and "rate limit" not in text.lower(), "Said in a visitor's words"


def test_the_page_chooses_the_sentence_by_what_ended_the_boot():
    paint = _APP[_APP.index("function paintBootFailure(err) {"):]
    paint = paint[:paint.index("\n}\n")]
    assert 'err.status === 429 ? "boot_failure_rate_limited"' in paint
    assert 'err.code === "network_unreachable" ? "msg_network"' in paint
    assert '"boot_failure_server"' in paint
    assert "err.message" not in paint and "errorText" not in paint, "Never the server's own text, which may be a proxy's page"
    assert "location.reload()" in paint
    assert 'markBoot("failed")' in paint


def test_only_an_answer_or_its_absence_is_said_as_a_failed_boot():
    """An error with no status was thrown by the page itself and is still thrown."""
    decide = _APP[_APP.index("async function decideAccess() {"):]
    decide = decide[:decide.index("\n}\n")]
    refused = decide.index("if (err.status !== 401) {")
    thrown = decide.index('if (typeof err?.status !== "number") throw err;')
    kept = decide.index("bootFailure = err;")
    assert refused < thrown < kept, "Asked in this order: sign in; not the server's doing; the server's doing"
    boot = _APP[_APP.index("\nensureAccess().then("):]
    assert boot.index("if (bootFailure) return;") < boot.index("routeFromLocation();"), (
        "Nothing of the workbench starts behind the notice")


def test_the_notice_is_styled_where_the_page_loads_it_and_can_be_hidden():
    assert re.search(r"^\.boot-failure \{[^}]*display: flex;", _STYLES, re.M)
    # Measured at 375 px wide before this rule: the button was 41 px tall.
    assert ".boot-failure .btn { min-height: 44px; }" in _STYLES, "The page's size for something to press"
    sheets = re.findall(r'<link rel="stylesheet" href="/static/css/(\w+)\.css">', _INDEX)
    assert "workbench" in sheets
    # `display: flex` on the section would show it despite the attribute
    # without this rule, which every page's base sheet carries.
    base = (_WEB / "static/css/base.css").read_text(encoding="utf-8")
    assert "[hidden] { display: none !important; }" in base
    assert sheets.index("base") < sheets.index("workbench")


def test_the_fixtures_answer_as_the_limiter_does():
    """The limiter's refusal, copied into the page's contract and the smoke."""
    refusal = re.search(
        r'JSONResponse\(\s*\{"detail": "(Too many requests\. Slow down and retry shortly\.)"\},\s*'
        r'status_code=429,\s*headers=\{"Retry-After": "10", "X-Error-Code": "rate_limited"\},', _MAIN)
    assert refusal, "api/main.py _rate_limit no longer answers as these fixtures do"
    detail = refusal.group(1)
    assert f'TOLD_TO_WAIT = {{ status: 429, body: {{ detail: "{detail}" }}' in _CONTRACT
    assert 'headers: { "Retry-After": "10", "X-Error-Code": "rate_limited" } };' in _CONTRACT
    assert f'"detail": "{detail}"' in _KEYBOARD_SMOKE
    assert '"Retry-After": "10", "X-Error-Code": "rate_limited"' in _KEYBOARD_SMOKE


def test_the_keyboard_smoke_meets_the_notice_in_a_browser():
    journey = _KEYBOARD_SMOKE[_KEYBOARD_SMOKE.index("def _told_to_wait_journey("):]
    journey = journey[:journey.index("\ndef main(")]
    for needed in ('expect(page.locator("#boot-failure")).to_be_visible()',
                   'expect(page.locator("#workbench")).to_be_hidden()',
                   'expect(page.locator("#landing")).to_be_hidden()',
                   'to_have_attribute("data-boot", "failed")',
                   'expect(page.locator("#boot-failure-retry")).to_be_focused()',
                   'keys.press("Enter")',
                   'expect(page.locator("#gate-input")).to_be_focused()'):
        assert needed in journey, needed
    main = _KEYBOARD_SMOKE[_KEYBOARD_SMOKE.index("\ndef main("):]
    assert "_told_to_wait_journey(browser, scratch, base, scheme, log)" in main
