"""The admin console's boot says why it did not open, not always "sign in".

When /admin opens, admin.js asks who the visitor is (api.me()) and loads
the account list (api.adminAccounts()). Until #471 either request failing
for any reason showed "Sign in to the app with an admin account first, then
come back here." That is right for a 401, but a signed-in admin saw the
same sentence when the server answered 429, when it could not be reached,
or when it answered with a 5xx. The main page has said which of these it
was since #427 (paintBootFailure() in app.js); the console now chooses
the same way, in both interface languages, and an error with no status
— one the page itself threw — is still thrown rather than blamed on
the server.

Which sentence each boot shows is exercised with the shipped admin.js,
api.js and i18n.js in tests/js/admin_boot_contract.mjs, and in Chromium
by e2e/browser_smoke.py. The checks here keep in place what those rely
on: the choice itself, the strings in both languages, and the limiter's
answer the fixtures copy.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "tests/js/admin_boot_contract.mjs"
_SCRIPT_TEXT = _SCRIPT.read_text(encoding="utf-8")
_ADMIN = (_ROOT / "web/static/js/admin.js").read_text(encoding="utf-8")
_STRINGS = (_ROOT / "web/static/js/i18n.js").read_text(encoding="utf-8")
_MAIN = (_ROOT / "api/main.py").read_text(encoding="utf-8")
_SMOKE = (_ROOT / "e2e/keyboard_smoke.py").read_text(encoding="utf-8")

SCENARIOS = (
    "me_401",
    "me_not_admin",
    "me_429",
    "me_unreachable",
    "me_500",
    "accounts_429",
    "accounts_500",
    "admin_opens",
    "page_error_rethrown",
)
LANGUAGES = ("English", "Simplified Chinese")
_SHARED_KEYS = ("boot_failure_rate_limited", "msg_network", "boot_failure_server")


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("language", LANGUAGES)
def test_the_boot_says_why_it_did_not_open(scenario, language):
    node = shutil.which("node")
    assert node, "Node is required for the admin boot seam"
    result = subprocess.run([node, str(_SCRIPT), scenario, language],
                            capture_output=True, text=True, encoding="utf-8", cwd=_ROOT)
    assert result.returncode == 0, result.stderr or result.stdout
    assert f"PASS {scenario} {language}" in result.stdout


def _boot() -> str:
    start = _ADMIN.index("(async () => {")
    return _ADMIN[start:_ADMIN.index("})();", start)]


def test_the_boot_chooses_the_sentence_by_what_ended_it():
    boot = _boot()
    assert 'err.status === 401 ? "denied_signin"' in boot
    assert 'err.status === 429 ? "boot_failure_rate_limited"' in boot
    assert 'err.code === "network_unreachable" ? "msg_network"' in boot
    assert '"boot_failure_server"' in boot
    assert 'denial = "denied_admin"' in boot, "A signed-in non-admin keeps denied_admin"
    assert "err.message" not in boot and "errorText" not in boot, (
        "Never the server's own text, which may be a proxy's page")


def test_only_an_answer_or_its_absence_is_blamed_on_the_server():
    """An error with no status was thrown by the page itself and is still thrown."""
    boot = _boot()
    thrown = boot.index('if (typeof err?.status !== "number") throw err;')
    chosen = boot.index('denial = err.status === 401')
    assert thrown < chosen, "Asked in this order: not the server's doing; the server's doing"


def test_the_failure_sentences_are_the_main_page_s_shared_strings():
    """i18n shows the key itself for a string one language lacks."""
    assert "?? i18n.t(key)" in _ADMIN, "The console's own table falls back to the shared strings"
    for key in _SHARED_KEYS:
        assert _STRINGS.count(f"    {key}: ") == 2, key


def test_the_fixtures_answer_as_the_limiter_does():
    """The limiter's refusal, copied into the page's contract and the smoke."""
    refusal = re.search(
        r'\{"detail": "(Too many requests\. Slow down and retry shortly\.)"\},\s*'
        r'status_code=429,\s*headers=\{"Retry-After": "10", "X-Error-Code": "rate_limited"\},', _MAIN)
    assert refusal, "api/main.py _rate_limit no longer answers as these fixtures do"
    detail = refusal.group(1)
    assert f'TOLD_TO_WAIT = {{ body: {{ detail: "{detail}" }}, status: 429,' in _SCRIPT_TEXT
    assert 'headers: { "Retry-After": "10", "X-Error-Code": "rate_limited" } };' in _SCRIPT_TEXT
    assert f'"detail": "{detail}"' in _SMOKE
    assert '"Retry-After": "10", "X-Error-Code": "rate_limited"' in _SMOKE
