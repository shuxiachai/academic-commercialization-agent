"""The browser smoke waits for the page to come to rest, and the wait has to mean it.

The sample-contents journey presses Tab into the contents and Enter on a
section's link. Between keys it waited for the page to stop scrolling by
comparing window.scrollY with the value its previous look had left on the
page. That value survived from one key press to the next, so the first look
after a new key found the page where the last key had left it and called that
stillness: measured on 2026-11-13, the wait returned in 1.6 ms, before the
browser had begun to scroll the newly focused link into view. Enter then raced
that scroll, and now and then the page ended at the link instead of at the
heading, with the URL already naming the section. In CI that was 4 failures in
41 runs after the scorecard was put above the report (#376) and the scroll to
the contents grew longer; none in the 151 runs before.

The wait is now one script in e2e/scroll_wait.py that keeps nothing between
calls and counts frames as well as time. It runs here in Node on a scripted
clock; what a real Chromium does with it is the smoke's own business.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from e2e.scroll_wait import COMES_TO_REST

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = Path(__file__).with_name("js") / "scroll_wait_contract.mjs"
_SMOKE = (_ROOT / "e2e" / "browser_smoke.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("scenario", [
    "waits_for_a_scroll_that_has_not_begun",
    "nothing_from_an_earlier_wait_is_used",
    "a_still_page_costs_six_frames_and_a_tenth_of_a_second",
    "a_stalled_page_is_not_a_still_one",
    "a_pause_in_the_middle_starts_the_count_again",
    "a_page_that_never_rests_is_an_error_that_says_so",
    "a_heading_is_waited_for_until_it_rests_near_the_top",
    "a_heading_that_rests_elsewhere_fails_and_says_where",
    "a_heading_still_on_its_way_is_not_judged_early",
    "a_heading_that_is_not_there_yet_is_waited_for",
])
def test_the_wait_on_a_scripted_clock(scenario):
    node = shutil.which("node")
    assert node, "Node is required; missing execution is not a passing seam"
    with TemporaryDirectory() as tmp:
        source = Path(tmp) / "wait.js"
        source.write_text(COMES_TO_REST, encoding="utf-8")
        result = subprocess.run([node, str(_SCRIPT), str(source), scenario], capture_output=True,
                                text=True, encoding="utf-8", timeout=60, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {scenario}" in result.stdout


def test_every_scenario_in_the_script_is_run():
    declared = re.findall(r"^  async (\w+)\(\) \{$", _SCRIPT.read_text(encoding="utf-8"), re.M)
    run = test_the_wait_on_a_scripted_clock.pytestmark[0].args[1]
    assert declared and sorted(declared) == sorted(run)


def test_the_wait_keeps_nothing_on_the_page():
    # A sample left on window is what let one key's stillness answer for the next key.
    assert "window.__" not in COMES_TO_REST
    assert not re.search(r"\bwindow\.\w+\s*=[^=]", COMES_TO_REST), "the wait assigns nothing to the page"
    assert "requestAnimationFrame" in COMES_TO_REST, "looks are frames, so a stalled page is not a still one"


def test_the_suite_can_import_the_wait_without_playwright():
    source = (_ROOT / "e2e" / "scroll_wait.py").read_text(encoding="utf-8")
    assert re.search(r"^\s*(import|from) playwright", source, re.M) is None, "the pytest jobs do not install it"


def _body(name: str) -> str:
    """The source of one helper nested in _exercise_sample_contents."""
    found = re.search(rf"^    def {name}\(.*?(?=^    def |^    page\.on\()", _SMOKE, re.M | re.S)
    assert found, name
    return found.group(0)


def test_the_smoke_uses_the_wait_after_each_key_and_at_each_arrival():
    assert "from e2e.scroll_wait import COMES_TO_REST" in _SMOKE
    tab = _body("focus_in_contents")
    assert re.search(r'page\.keyboard\.press\("Tab"\)\n\s+page\.evaluate\(COMES_TO_REST, None\)', tab), (
        "the page is watched after every Tab, before the next key")
    assert "page.evaluate(COMES_TO_REST, section)" in _body("settle_at"), "a heading is watched by its id"
    # Enter on a contents link follows a Tab's wait directly, in both layouts.
    journey = _SMOKE[_SMOKE.index("def _exercise_sample_contents"):_SMOKE.index("def _exercise_browser")]
    for target in ('arrive(slug, "section-3", before)', 'arrive(slugs[0], "section-1", before)'):
        before = journey[:journey.index(target)]
        lines = before[:before.rindex('page.keyboard.press("Enter")')].rstrip().splitlines()
        assert lines.pop().strip() == "before = len(reads)", target
        assert "focus_in_contents(" in lines[-1], f"{target}: the key before Enter is {lines[-1].strip()!r}"


def test_the_smoke_has_no_wait_that_remembers_a_previous_look():
    for name in ("__smokeScrollY", "__smokeTop"):
        assert name not in _SMOKE, name
    journey = _SMOKE[_SMOKE.index("def _exercise_sample_contents"):_SMOKE.index("def _exercise_browser")]
    assert "const still = window." not in journey
    # The one thing the journey does keep on the page is the article node it compares against.
    assert set(re.findall(r"window\.(__\w+)", _SMOKE)) == {"__smokeArticle"}
