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
    "the_account_menu_names_the_account_and_opens_on_request",
    "the_slots_are_an_administrators_and_everyone_else_is_told_only_when_full",
    "opening_the_account_panel_does_not_put_the_cursor_in_a_password_field",
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
    "early_landing_gives_way_to_the_code_card",
    "keys_in_this_tab_never_see_the_landing", "unreadable_keys_never_see_the_landing",
    # A boot whose access check got no answer about the visitor says so
    # (tests/test_boot_failure_notice.py).
    "a_boot_told_to_wait_says_so_and_can_be_tried_again", "a_boot_that_cannot_reach_the_server_says_so",
    "a_boot_the_server_could_not_answer_says_so", "a_signed_in_boot_told_to_wait_keeps_the_session",
    "a_shared_link_whose_boot_was_told_to_wait_says_so",
    "a_boot_that_broke_in_the_page_is_not_blamed_on_the_server",
    # A sample's scorecard, drawn by the page, where a picture of one used to be.
    "preview_that_cannot_be_read_is_a_quiet_line", "a_scorecard_that_arrives_after_the_landing_left_is_not_drawn",
    # The card's sign-in mode, without what only creating an account needs.
    "the_card_in_sign_in_mode_says_only_what_signing_in_needs",
    # The run header's fold for the model, the revision and a plain completion.
    "a_change_of_language_renames_the_tab_and_redraws_the_landing_samples",
    # The screenshot of a finished assessment further down the landing.
    "the_screenshot_is_asked_for_once_the_landing_stays_in_the_theme_and_language_in_use",
    "a_run_that_did_not_finish_offers_what_fits_its_cause",
    "a_run_that_is_going_says_the_page_can_be_closed",
    "the_header_folds_what_only_a_maintainer_reads",
    # Whose run it is: the owner's actions, and a signed-in reader's.
    "the_owners_actions_keep_the_rare_ones_behind_more",
    "a_signed_in_reader_of_someone_elses_run_is_told_so_and_offered_no_owner_action",
    "what_the_server_says_decides_and_a_run_with_no_owner_is_this_tabs_or_not",
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
    # What a finished report looks like, in the card beside the pitch: a place
    # for one sample's scorecard, which app.js draws when the landing shows,
    # and a line for when it cannot. It was a 900 px picture of a dark
    # scorecard until 2026-11-13, and this card still holds no picture. The
    # screenshot further down the page is another figure with its own tests
    # below: one file for each theme, width and language, which is what the
    # single picture lacked.
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


def test_every_repaint_of_a_runs_actions_is_told_whose_run_it_is():
    """The scenarios above call the painter with the answer in hand. What
    gives it the answer on the page is the three places that repaint a run's
    actions, each passing what the status just said (`mayModify`). One of
    them painting without it would offer a reader the owner's buttons until
    the next poll, or for good on a finished run, which is polled once."""
    calls = re.findall(r"^\s+paintActions\(([^;]*)\);$", _APP, re.M)
    assert calls == ['known?.state ?? "unknown", known?.checkpointing, mayModify(known), known ?? null',
                     "progress.state, progress.checkpointing, mayModify(progress), progress",
                     "progress.state, progress.checkpointing, mayModify(progress), progress"], calls
    # The notice is in the page, hidden until a reader's status says to show it.
    assert re.search(r'<p class="run-shared" id="run-shared" hidden>', _INDEX)
    assert re.search(r'<button type="button" class="run-shared__new" id="run-shared-new" data-i18n="shared_new">', _INDEX)
    english, chinese = _STRINGS.split('"Simplified Chinese": {', 1)
    for table, words in ((english, ("shared with you", "only its owner can change it")), (chinese, ("分享给你", "只有它的所有者可以改动"))):
        note = re.search(r'^\s+shared_note: "([^"]+)"', table, re.M)[1]
        for word in words:
            assert word in note, note


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


# ── What was added on 2026-11-18: points, a screenshot, sources, questions ──

_CSS = (_WEB / "static/css/landing.css").read_text(encoding="utf-8")
_PRIVACY = (_WEB / "privacy.html").read_text(encoding="utf-8")
_PRIVACY_EN, _PRIVACY_ZH = _PRIVACY.split('data-lang-block="zh"', 1)
_SHOTS = _WEB / "static" / "landing"
_SHOT_NAMES = sorted(f"brief-scorecard-{size}-{theme}-{language}.png"
                     for size in ("desktop", "phone") for theme in ("light", "dark") for language in ("en", "zh"))


def test_the_pitch_has_three_points_under_its_buttons():
    """Measured at 1440 px on 2026-11-18: the pitch ended at its buttons, 419
    px down, and the card beside it at 782. Three points fill the column.
    Each repeats what the page's steps or the privacy page already say."""
    landing = _landing_markup()
    pitch = landing[landing.index('<div class="landing__pitch">'):landing.index('<aside class="landing__card landing__sample"')]
    assert pitch.index('class="landing__actions"') < pitch.index('<ul class="landing__points">')
    points = re.findall(r"<li>\s*<strong data-i18n=\"(landing_point\d_title)\">[^<]+</strong>\s*"
                        r"<span data-i18n=\"(landing_point\d_body)\">[^<]+</span>\s*</li>", pitch)
    assert points == [(f"landing_point{n}_title", f"landing_point{n}_body") for n in (1, 2, 3)]
    assert re.search(r"\.landing__points \{[^}]*list-style: none", _CSS)
    english, chinese = _landing_strings("English"), _landing_strings("Simplified Chinese")
    # The first two are the second step's own facts, and the third is the privacy page's.
    assert "before any agent writes" in english["landing_point1_body"] and "then freezes them" in english["landing_step2_body"]
    assert "computed by code, not by the model" in english["landing_point2_body"]
    assert "computed by code, not by the model" in english["landing_step2_body"]
    assert "where it is weakest" in english["landing_point3_body"]
    assert "the automated checks shown with each report say where it is weakest" in _PRIVACY_EN
    assert "由代码计算，不由模型给出" in chinese["landing_point2_body"] and "由代码计算，不由模型给出" in chinese["landing_step2_body"]


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR", path.name
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def test_the_screenshot_of_a_finished_assessment_is_one_file_for_each_theme_width_and_language():
    """The landing showed a scorecard's verdict and bars and nothing of the
    brief. It now shows a screenshot of one sample's page. The single picture
    this page had until 2026-11-13 was dark in the light theme and a few
    pixels a letter on a phone, so there is a file for each case, and the
    page tells the browser each file's real size before it loads."""
    assert sorted(path.name for path in _SHOTS.iterdir()) == _SHOT_NAMES, "eight files, and nothing else beside them"
    declared = re.search(r"const LANDING_SHOT_SIZES = \{\s*en: \{ desktop: \[(\d+), (\d+)\], phone: \[(\d+), (\d+)\] \},"
                         r"\s*zh: \{ desktop: \[(\d+), (\d+)\], phone: \[(\d+), (\d+)\] \},\s*\};", _APP)
    assert declared, "the sizes the page gives the picture"
    numbers = [int(value) for value in declared.groups()]
    sizes = {("en", "desktop"): tuple(numbers[0:2]), ("en", "phone"): tuple(numbers[2:4]),
             ("zh", "desktop"): tuple(numbers[4:6]), ("zh", "phone"): tuple(numbers[6:8])}
    for name in _SHOT_NAMES:
        _, _, size, theme, language = name.removesuffix(".png").split("-")
        path = _SHOTS / name
        assert _png_size(path) == sizes[(language, size)], name
        assert path.stat().st_size < 200_000, f"{name}: a picture a phone has to fetch"
    # A phone's file is a phone's capture (two device pixels a CSS pixel), not a desk's made small.
    assert sizes[("en", "phone")][0] < 800 < sizes[("en", "desktop")][0]
    assert "/static/landing/brief-scorecard-${size}-${theme}-${language}.png" in _APP
    # The markup names no file: a page that never shows the landing asks for none.
    landing = _landing_markup()
    figure = landing[landing.index('<figure class="landing__shot-figure">'):]
    figure = figure[:figure.index("</figure>")]
    picture = re.search(r"<img id=\"landing-shot\"([^>]*)>", figure)[1]
    source = re.search(r"<source id=\"landing-shot-phone\"([^>]*)>", figure)[1]
    assert " src=" not in picture and "srcset=" not in source and "/static/landing/" not in _INDEX
    assert 'loading="lazy"' in picture and re.search(r'alt="[^"]{40,}"', picture)
    assert f'width="{sizes[("en", "desktop")][0]}" height="{sizes[("en", "desktop")][1]}"' in picture
    assert f'width="{sizes[("en", "phone")][0]}" height="{sizes[("en", "phone")][1]}"' in source
    assert 'media="(max-width: 640px)"' in source
    # It is asked for once the access check has said the landing stays, never before.
    shown = _APP[_APP.index("async function showLanding()"):]
    assert "paintLandingShot();" in shown[:shown.index("await new Promise")]
    early = _APP[_APP.index("function paintLanding() {"):_APP.index("function themeInUse()")]
    assert "paintLandingShot()" not in early.split("\n}\n", 1)[0]


def test_the_screenshot_is_of_the_sample_it_opens_and_says_when_it_was_taken():
    from api import samples

    slug = re.search(r'const LANDING_PREVIEW_SAMPLE = "([a-z0-9-]+)";', _APP)[1]
    landing = _landing_markup()
    figure = landing[landing.index('<figure class="landing__shot-figure">'):]
    assert f'<a class="landing__shot-link" href="/samples/{slug}">' in figure, "the capture opens the page it is a capture of"
    scores = samples.read_sample_scores(slug)
    english, chinese = _landing_strings("English"), _landing_strings("Simplified Chinese")
    # What the picture's description says is in it is what that sample's page shows.
    assert f'{scores["overall_score"]:.1f} / 100' in english["landing_shot_alt"] and "Strong" in english["landing_shot_alt"]
    assert scores["overall_score"] >= 70, "the grade the description names"
    assert f'{scores["overall_score"]:.1f} / 100' in chinese["landing_shot_alt"] and "较强" in chinese["landing_shot_alt"]
    assert "November 2026" in english["landing_shot_caption"] and "2026 年 11 月" in chinese["landing_shot_caption"]
    assert "continuous glucose monitoring" in english["landing_shot_caption"]
    sample = next(entry for entry in samples.SAMPLES if entry.slug == slug)
    assert sample.title_zh in chinese["landing_shot_caption"]
    assert re.search(r'alt="([^"]+)"', figure)[1] == english["landing_shot_alt"], "served as it is then painted"


def test_the_pictures_are_served_and_revalidated_like_every_page_file():
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as client:
        for name in _SHOT_NAMES:
            reply = client.get(f"/static/landing/{name}")
            assert reply.status_code == 200 and reply.headers["content-type"] == "image/png", name
            assert reply.headers["cache-control"] == "no-cache", name


# The services the landing may name as where evidence comes from: each with
# the thing in the code that asks it.
_SOURCE_CLIENTS = {"OpenAlex": "class OpenAlexClient", "Crossref": "class CrossrefClient", "PubMed": "class PubMedClient",
                   "arXiv": "class ArxivClient", "Semantic Scholar": "class SemanticScholarClient"}


def test_the_landing_names_only_sources_the_pipeline_asks():
    """A line of names is a claim about each. Every service named is one the
    retrieval code has a client for and constructs in the default run, or,
    for patents, the Google Patents pages the pipeline searches and reads;
    and each is in the privacy page's list of who receives a query. Lens is
    in the code but asked only with a key this deployment does not have, so
    it is not named."""
    clients = (_ROOT / "src/academic_agent/source_clients.py").read_text(encoding="utf-8")
    pipeline = (_ROOT / "src/academic_agent/source_pipeline.py").read_text(encoding="utf-8")
    services = re.search(r"<strong>Public literature and patent services</strong> \(([^)]+)\)", _PRIVACY_EN)[1]
    for language in ("English", "Simplified Chinese"):
        line = _landing_strings(language)["landing_sources"]
        named = [name for name in (*_SOURCE_CLIENTS, "Google Patents", "Lens", "Scopus", "Web of Science", "Google Scholar",
                                   "USPTO", "Espacenet", "PatentsView", "Europe PMC") if name in line]
        assert named == [*_SOURCE_CLIENTS, "Google Patents"], (language, named)
        for name in named:
            assert name in services, f"{name} is not in the privacy page's list of who receives a query"
    for name, definition in _SOURCE_CLIENTS.items():
        assert definition in clients, name
        constructor = definition.removeprefix("class ") + "("
        assert constructor in pipeline, f"{name}: the pipeline never builds its client"
    assert "site:patents.google.com/patent" in pipeline
    # Market sources come through the visitor's own search service, which the line says without a name of its own.
    assert "web search service you choose" in _landing_strings("English")["landing_sources"]
    assert "The web search service you choose" in _PRIVACY_EN
    assert 'data-i18n="landing_sources"' in _landing_markup()
    # Nothing on the landing says the raw data is public: the saved runs are not in the repository.
    for language in ("English", "Simplified Chinese"):
        for key, text in _landing_strings(language).items():
            assert not re.search(r"raw data|原始数据", text), key


def _faq() -> list[tuple[str, str]]:
    landing = _landing_markup()
    section = landing[landing.index('<section class="landing__faq" id="landing-faq"'):]
    section = section[:section.index("</section>")]
    return re.findall(r'<details class="landing__question">\s*<summary data-i18n="(landing_faq_q\d)">[^<]+</summary>'
                      r'\s*<div class="landing__answer">.*?<p data-i18n="(landing_faq_a\d)">[^<]+</p>\s*</div>\s*</details>',
                      section, re.S)


def test_the_landing_answers_five_questions_and_each_answer_is_already_written_down_somewhere():
    """How long data is kept, which languages, what a decision context is,
    whether a paper can be uploaded, how fees are worked out. An answer on a
    landing page is the easiest place for a claim nobody checked, so each is
    held here to the page, the constant or the document it repeats."""
    from api import papers

    assert _faq() == [(f"landing_faq_q{n}", f"landing_faq_a{n}") for n in range(1, 6)]
    assert "<details class=\"landing__question\" open" not in _INDEX, "closed until asked"
    english, chinese = _landing_strings("English"), _landing_strings("Simplified Chinese")

    # 1. Kept how long: the deployment's own period, read from /health into
    # the answer's first line, then what the privacy page says can be deleted.
    landing = _landing_markup()
    first = landing[landing.index('data-i18n="landing_faq_q1"'):landing.index('data-i18n="landing_faq_q2"')]
    assert first.index('id="landing-retention"') < first.index('data-i18n="landing_faq_a1"')
    assert landing.count('id="landing-retention"') == 1
    assert not re.search(r"\d+ days|\d+ 天", english["landing_faq_a1"] + chinese["landing_faq_a1"]), (
        "the period is the deployment's, never written into the page")
    assert "You can delete any assessment from its page at any time." in _PRIVACY_EN
    assert "Delete your account from the Account panel." in _PRIVACY_EN
    assert "The original file is deleted as soon as extraction succeeds." in _PRIVACY_EN
    assert "You can remove them at any time" in _PRIVACY_EN
    for said in ("delete any assessment from its page", "your whole account", "deleted as soon as", "until you remove them"):
        assert said in english["landing_faq_a1"], said

    # 2. Languages: the two the interface has, and every language the composer offers for a report.
    select = _INDEX[_INDEX.index('<select class="chip-select" id="language"'):]
    select = select[:select.index("</select>")]
    offered = re.findall(r'<option value="(\w+)">', select)
    assert len(offered) == 11
    for name in offered:
        assert name in english["landing_faq_a2"], name
    assert len(re.findall(r"[^；。，、或]+语|中文", chinese["landing_faq_a2"].split("报告可以用", 1)[1].split("撰写", 1)[0])) == 11
    interface = _INDEX[_INDEX.index('<select class="bare-select" id="ui-lang"'):]
    assert re.findall(r'<option value="([^"]+)">', interface[:interface.index("</select>")]) == ["English", "Simplified Chinese"]
    assert "English and Simplified Chinese" in english["landing_faq_a2"]
    automatic = re.search(r'auto_lang: "([^"]+)"', _STRINGS)[1]
    assert f"“{automatic}”" in english["landing_faq_a2"], "the option's own name"

    # 3. Decision context: the four starred fields, and what the form's own line says of them.
    labels = [re.search(rf'    {key}: "([^"*]+) \*"', _STRINGS)[1].lower()
              for key in ("decision_asset", "decision_application", "decision_owner", "decision_type")]
    for label in labels:
        assert label.split(" or ")[0] in english["landing_faq_a3"].lower(), label
    ready = re.search(r'    decision_status_ready: "([^"]+)"', _STRINGS)[1]
    assert "the report may give a GO / NO-GO for this decision, bounded by its evidence" in ready
    assert "may give a GO / NO-GO for that decision, bounded by its evidence" in english["landing_faq_a3"]
    assert "orientation brief" in english["landing_faq_a3"] and "optional" in english["landing_faq_a3"].lower()
    # The form's title and the question call it by one name in Chinese.
    title = re.findall(r'    decision_context_title: "([^"]+)"', _STRINGS)[1]
    assert "决策场景" in title and "决策场景" in chinese["landing_faq_q3"] and "决策上下文" not in _STRINGS

    # 4. Papers: the size the upload route enforces, and the two deletions the privacy page states.
    megabytes = papers.MAX_UPLOAD_BYTES // 1024 // 1024
    assert f"up to {megabytes} MB" in english["landing_faq_a4"] and f"不超过 {megabytes} MB" in chinese["landing_faq_a4"]
    assert "within 24 hours" in english["landing_faq_a4"] and "24 小时内" in chinese["landing_faq_a4"]
    assert "if no assessment uses it, it is deleted within 24 hours" in _PRIVACY_EN
    assert "Upload only papers you are allowed to send to the model provider you chose." in _PRIVACY_EN
    assert "Upload only papers you are allowed to send to that provider" in english["landing_faq_a4"]
    assert 'accept=".pdf,application/pdf"' in _INDEX and "PDF" in english["landing_faq_a4"]

    # 5. Fees: the privacy page's term, and no sum of its own (the table has them).
    assert "This service does not charge you and cannot refund them." in _PRIVACY_EN
    assert "charges nothing and cannot refund" in english["landing_faq_a5"]
    assert "不收费" in chinese["landing_faq_a5"]
    faq_at, table_at = landing.index('id="landing-faq"'), landing.index('id="landing-costs"')
    assert table_at < faq_at and "table above" in english["landing_faq_a5"] and "上面的表格" in chinese["landing_faq_a5"]
    # Each question is a control a finger can press.
    assert re.search(r"\.landing__question > summary \{[^}]*min-height: 48px", _CSS)
