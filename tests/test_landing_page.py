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

import html
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
    # Password reset by email (tests/test_password_reset.py): the page a link
    # opens, a refused link, the forgot form, and its absence without mail.
    "reset_link", "reset_link_refused", "forgot_from_sign_in", "forgot_absent_without_mail",
    # The Account panel's run-finished notice switch (tests/test_run_notices.py).
    "notice_switch", "notice_switch_refused", "notice_switch_absent_without_mail",
    # An administrator the deployment funds is not asked for keys (tests/test_admin_funded.py).
    "signed_in_admin_funded",
    # A shared run or comparison is read by whoever holds its link, with a bar
    # that offers the way in; and what the way in says when a first
    # assessment is free.
    "anonymous_deep_link_signup_closed", "anonymous_compare_link", "anonymous_other_path_still_meets_the_card",
    "viewer_signs_in", "trial_said_on_the_way_in",
    # The sample reader's "Create account" and "Sign in" are links to / that
    # name the form; and what the landing's own sample list says of each.
    "create_account_link", "sign_in_link", "create_account_link_when_sign_up_is_closed",
    "another_fragment_opens_nothing",
    # The landing is shown before the access check answers, and corrected by it.
    "landing_before_the_check_answers", "a_button_pressed_before_the_answer_opens_its_form_after_it",
    "the_last_press_before_the_answer_is_the_one_kept", "a_press_before_the_answer_where_sign_up_is_closed",
    "the_link_from_a_sample_waits_for_the_answer_too", "early_landing_gives_way_to_an_open_deployment",
    "early_landing_gives_way_to_the_code_card", "early_landing_gives_way_when_the_check_cannot_be_reached",
    "keys_in_this_tab_never_see_the_landing", "unreadable_keys_never_see_the_landing",
    # A sample's scorecard, drawn by the page, where a picture of one used to be.
    "preview_that_cannot_be_read_is_a_quiet_line", "a_scorecard_that_arrives_after_the_landing_left_is_not_drawn",
    # The card's sign-in mode, without what only creating an account needs.
    "the_card_in_sign_in_mode_says_only_what_signing_in_needs",
    # "Get both keys in 3 steps" where the first assessment is free.
    "the_key_guide_under_the_keys_form_knows_a_free_run_is_left",
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
    # What a finished report looks like: a place for one sample's scorecard,
    # which app.js draws when the landing shows, and a line for when it cannot.
    # It was a 900 px picture of a dark scorecard until 2026-11-13; no picture
    # of one is served any more, so there is nothing to go stale or to shrink.
    figure = landing[landing.index('<figure class="landing__figure">'):landing.index("</figure>")]
    assert re.search(r'<div class="landing__preview" id="landing-preview" data-state="loading"></div>', figure)
    assert re.search(r'<p class="landing__preview-note" id="landing-preview-note" data-i18n="landing_preview_unavailable" hidden>', figure)
    assert "<img" not in figure and "report-preview" not in _INDEX
    assert not (_WEB / "static/brand/report-preview.png").exists()
    assert figure.index('id="landing-preview"') < figure.index("<figcaption")
    assert 'id="landing-retention"' in landing


def _landing_strings(language: str) -> dict[str, str]:
    """key -> text, for one interface language, as i18n.js states them."""
    english, chinese = _STRINGS.split('"Simplified Chinese": {', 1)
    table = english if language == "English" else chinese
    return {key: text.replace('\\"', '"')
            for key, text in re.findall(r'^\s+(landing_\w+): "((?:[^"\\]|\\.)*)",?\s*$', table, re.M)}


# What a report is not, in the words the three places used.
_CAUTION = re.compile(r"not a measure|historical|not current|not replace|makes no model"
                      r"|不代表|历史运行|不是当前|不代替|不会发起")


def test_the_landing_says_what_a_report_is_not_once():
    """Until 2026-11-13 three places on the landing each said it: under the
    picture ("One result, not a measure of accuracy."), over the sample list
    ("…makes no model or search request; they are historical runs, not
    current market advice.") and in the footer. Said three times it reads as
    hedging and none of the three is read. The footer's is the one that is
    about every report, so it stays; the picture's caption keeps its date and
    the sample list keeps what a visitor needs to know, that no account is
    needed. Each sample still carries its own dated notice on the sample page."""
    for language in ("English", "Simplified Chinese"):
        strings = _landing_strings(language)
        assert len(strings) >= 18, language
        assert [key for key, text in strings.items() if _CAUTION.search(text)] == ["landing_disclaimer"], language
    assert _landing_strings("English")["landing_figure_caption"] == (
        "A real run from November 2026, opened in the current interface.")
    assert _landing_strings("English")["landing_sample_body"] == "Finished assessments you can read without an account."
    assert _landing_strings("Simplified Chinese")["landing_figure_caption"] == "2026 年 11 月的一次真实运行，在当前界面中打开。"
    assert _landing_strings("Simplified Chinese")["landing_sample_body"] == "无需账号即可阅读的完整评估。"


def test_the_landing_text_served_before_the_script_is_the_text_that_replaces_it():
    """The markup carries the English text for the moment before i18n.apply()
    runs, and for a reader without scripts. On 2026-11-13 the caption under
    the picture was served as "A real run from August 2026… A historical
    result, not a current one." and replaced a moment later by a sentence
    about November: the picture and its string had been changed and the
    markup had not."""
    english = _landing_strings("English")
    served = re.findall(r'data-i18n="(landing_\w+)"[^>]*>([^<]+)<', _landing_markup())
    assert len(served) >= 15, served
    for key, text in served:
        assert " ".join(html.unescape(text).split()) == english[key], key


def test_the_scorecard_on_the_landing_is_the_run_its_caption_dates():
    """The caption says "A real run from November 2026". The scorecard above
    it is one named sample's, so the two are held together here: a different
    sample, or that sample replaced by a later run, fails until the caption
    is looked at again."""
    from api import samples

    slug = re.search(r'const LANDING_PREVIEW_SAMPLE = "([a-z0-9-]+)";', _APP)[1]
    sample = next(entry for entry in samples.SAMPLES if entry.slug == slug)
    assert sample.committed.startswith("2026-11-"), sample
    assert "November 2026" in _landing_strings("English")["landing_figure_caption"]
    assert "2026 年 11 月" in _landing_strings("Simplified Chinese")["landing_figure_caption"]
    # The scores it draws are the ones the sample page serves, and they are readable.
    scores = samples.read_sample_scores(slug)
    assert isinstance(scores.get("overall_score"), int | float) and 0 <= scores["overall_score"] <= 100


def test_the_card_is_served_in_its_sign_in_mode():
    """The form is one for both modes and app.js paints the mode. What the
    markup carries before that is the sign-in mode, so nothing that belongs
    to creating an account can show for the moment the script has not run."""
    form = _INDEX[_INDEX.index('<form id="account-form"'):]
    form = form[:form.index("</form>")]
    for element in ("account-sub", "account-sub-trial", "account-legal"):
        assert re.search(rf'<p class="gate__(?:sub|hint)" id="{element}"[^>]*\shidden>', form), element
    assert re.search(r'id="account-password"[^>]*autocomplete="current-password"[^>]*'
                     r'data-i18n-placeholder="account_password_plain" placeholder="Password">', form, re.S)
    english, chinese = _STRINGS.split('"Simplified Chinese": {', 1)
    assert '    account_password_plain: "Password",' in english
    assert '    account_password_plain: "密码",' in chinese
    # The rule is still said where a password is chosen.
    assert '    account_password_placeholder: "Password (at least 10 characters)",' in english


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


def test_the_page_has_what_a_reader_of_a_shared_run_is_shown():
    """The bar a visitor without an identity sees above someone else's report."""
    for control in ('id="viewer-bar"', 'id="viewer-sign-in"', 'id="viewer-create"'):
        assert control in _INDEX, control
    assert re.search(r'<div class="viewer-bar" id="viewer-bar" hidden>', _INDEX), "hidden until the boot decides"
    css = (_WEB / "static/css/workbench.css").read_text(encoding="utf-8")
    assert '[data-viewer="true"] .sidebar' in css, "the rail belongs to an identity; a reader has none"
    for key in ("viewer_note", "viewer_sign_in", "viewer_create"):
        assert _STRINGS.count(f"    {key}: ") == 2, key


def test_the_way_in_says_what_a_run_takes_and_what_a_trial_spares():
    """Measured 2026-11-09 to 2026-11-11: 343 to 833 seconds a run, about
    105,000 tokens. The card said "about 15 minutes" and "about 70,000"; and
    with a first assessment on the deployment's keys it must not still say
    that every run is paid for with keys the newcomer brings. Since
    2026-11-14 the cost is said in money, not tokens (tests/test_run_costs.py)."""
    assert "about 15 minutes" not in _STRINGS and "about 15 minutes" not in _INDEX
    assert "约 15 分钟" not in _STRINGS
    assert _STRINGS.count("6 to 15 minutes") >= 3 and _STRINGS.count("6 到 15 分钟") >= 3
    assert "about 70,000" not in _STRINGS and "model tokens" not in _STRINGS
    assert _STRINGS.count("    landing_pay_cost: ") == 2
    for element in ('id="landing-trial"', 'id="account-sub"', 'id="account-sub-trial"'):
        assert element in _INDEX, element
    for key in ("landing_trial", "account_sub_trial"):
        assert _STRINGS.count(f"    {key}: ") == 2, key
    assert "authConfig?.trial_runs > 0" in _APP
