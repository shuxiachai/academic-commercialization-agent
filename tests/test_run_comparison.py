"""Two runs side by side: the view exists, the server serves its address, and
the module draws the difference from what each run already publishes.

The comparison is drawn in the page from the reads the run page makes, so
there is no comparison endpoint to test. What is tested is the module's
arithmetic and its honesty about what is missing, the route, and that both
languages name everything the view says.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = Path(__file__).with_name("js") / "compare_contract.mjs"
_INDEX = (_ROOT / "web" / "index.html").read_text(encoding="utf-8")
_STRINGS = (_ROOT / "web" / "static" / "js" / "i18n.js").read_text(encoding="utf-8")
_APP = (_ROOT / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
_COMPARE = (_ROOT / "web" / "static" / "js" / "compare.js").read_text(encoding="utf-8")
_CSS = (_ROOT / "web" / "static" / "css" / "result.css").read_text(encoding="utf-8")


@pytest.mark.parametrize("scenario", ["rows", "unfinished", "nothing_to_compare", "drawn",
                                      "decision_rows", "next_step_expand", "loads_the_decision_only_when_asked",
                                      "topics", "picker_order"])
def test_the_module_compares_what_is_there_and_shows_what_is_not(scenario):
    node = shutil.which("node")
    assert node, "Node is required for the comparison seam"
    result = subprocess.run([node, str(_SCRIPT), scenario], capture_output=True, text=True,
                            encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {scenario}" in result.stdout


def test_the_server_serves_the_address_as_the_page():
    with TestClient(app) as client:
        page = client.get("/compare/20261021T022241Z-aaaa/20261105T090000Z-bbbb")
        assert page.status_code == 200
        assert "text/html" in page.headers["content-type"]
        assert 'id="pane-compare"' in page.text
        assert page.headers["cache-control"] in ("no-cache", "no-store")
        # Anything else under /compare is not a page.
        assert client.get("/compare/only-one").status_code == 404


def test_both_languages_name_everything_the_view_says():
    keys = set(re.findall(r't\("(compare_[a-z_]+|compare)"\)', _COMPARE + _APP))
    keys |= set(re.findall(r'data-i18n="(compare_[a-z_]+)"', _INDEX))
    assert {"compare", "compare_title", "compare_delta", "compare_same_run", "compare_not_finished"} <= keys
    for key in sorted(keys):
        assert _STRINGS.count(f"    {key}: ") == 2, key


def test_the_page_reaches_it_only_from_a_run_and_never_sends_the_pair():
    assert 'compare.id = "run-compare"' in _APP
    assert "/^\\/compare\\/([^/]+)\\/([^/]+)$/" in _APP
    assert 'id="compare-dialog"' in _INDEX and 'id="compare-choices"' in _INDEX
    # The comparison is reads only: the same reads the run page makes, nothing new.
    for call in re.findall(r"api\.(\w+)\(", _COMPARE):
        assert call in {"getRun", "getArtifact", "getReport", "getDecision"}, call
    assert "fetch(" not in _COMPARE and "POST" not in _COMPARE
    # Values become text, never markup.
    assert "innerHTML =" not in _COMPARE.replace('innerHTML = ""', "")


def _rule(selector: str, css: str = "") -> str:
    """The declarations of the first rule for `selector`, outside any media query."""
    found = re.search(rf"(?m)^{re.escape(selector)}\s*\{{([^}}]*)\}}", css or _CSS)
    assert found, selector
    return found[1]


def test_the_cards_the_table_and_the_rows_under_it_share_one_set_of_columns():
    """Until 2026-11-18 the two run cards were laid out on three columns and
    the table under them on four, so a card stood over no column of its own
    and nothing on a card said whether it was A or B. They now take their
    widths from the same four values, and each card carries its letter."""
    columns = "var(--compare-label) var(--compare-run) var(--compare-run) var(--compare-delta)"
    for selector in (".compare__heads", ".compare__brief-row"):
        assert f"grid-template-columns: {columns}" in _rule(selector), selector
    for name, width in (("label", "--compare-label"), ("run", "--compare-run"), ("delta", "--compare-delta")):
        assert f"width: var({width})" in _rule(f".compare__col--{name}"), name
    assert "table-layout: fixed" in _rule(".compare__table")
    shares = dict(re.findall(r"(--compare-(?:label|run|delta)):\s*([\d.]+)%", _rule(".compare")))
    assert set(shares) == {"--compare-label", "--compare-run", "--compare-delta"}, shares
    total = float(shares["--compare-label"]) + 2 * float(shares["--compare-run"]) + float(shares["--compare-delta"])
    assert total == 100, shares
    # Equal height: a card with a three-line topic no longer stands beside a shorter one.
    assert "align-items: stretch" in _rule(".compare__heads")
    # The text of a card, a table cell and a row under the table starts at one edge.
    inset = re.search(r"padding(?:-inline)?:[^;]*var\(--compare-inset\)", _rule(".compare__run"))
    assert inset and "var(--compare-inset)" in _rule(".compare__table th, .compare__table td")
    assert "var(--compare-inset)" in _rule(".compare__brief-cell")
    assert 'container.append(el("div", "compare")' not in _COMPARE, "the wrapper is the pane body's own class"
    assert 'id="compare-body"' in _INDEX and re.search(r'<div class="pane__body compare" id="compare-body">', _INDEX)


def test_the_picker_opens_in_the_middle_and_puts_the_same_topic_first():
    """A <dialog> is centred by the margins the browser gives it, and the
    page's reset takes every margin away (base.css), so the picker opened in
    the top left corner of the window. Found 2026-11-18 while taking pictures."""
    assert "margin: auto" in _rule(".picker")
    assert re.search(r"(?m)^\*, \*::before, \*::after \{[^}]*margin: 0", (_ROOT / "web/static/css/base.css").read_text(encoding="utf-8"))
    # The order is the module's, the list is the rail's own request, and the
    # run's own topic comes from that list or, failing that, from its title.
    assert "compareView.pickerOrder(runs, runId, " in _APP
    assert 'choose.dataset.sameTopic = "true"' in _APP
    for key in ("compare_pick_same", "compare_different_topics", "compare_pick_intro"):
        assert _STRINGS.count(f"    {key}: ") == 2, key
    english, chinese = _STRINGS.split('"Simplified Chinese": {', 1)
    assert "same topic" in re.search(r'compare_pick_intro: "([^"]+)"', english)[1]
    assert "同课题" in re.search(r'compare_pick_intro: "([^"]+)"', chinese)[1]
    assert re.search(r'compare_different_topics: "这两次评估的课题不同，分数差值仅供参考。"', chinese)
