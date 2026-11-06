"""The run list past its first fifty entries, and its search box.

The rail showed the newest fifty runs and nothing else: an older run could
only be reached by a link kept somewhere. These tests drive the shipped
sidebar module against a fake history. The search is done in the page on
purpose, so the words typed are never part of a request; one scenario checks
exactly that.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = Path(__file__).with_name("js") / "sidebar_history_contract.mjs"


@pytest.mark.parametrize("scenario", [
    "first_page", "beyond_one_request", "search", "capped", "short_history", "shifting", "reset",
])
def test_the_rail_reads_and_searches_the_whole_history(scenario):
    node = shutil.which("node")
    assert node, "Node is required for the run-history seam"
    result = subprocess.run([node, str(_SCRIPT), scenario], capture_output=True, text=True,
                            encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {scenario}" in result.stdout


def test_the_search_box_is_in_the_page_and_both_languages_name_everything():
    markup = (_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    box = markup.index('id="run-search"')
    assert box < markup.index('id="runlist"'), "The box sits above the list it filters"
    assert 'type="search"' in markup[box - 80:box + 300] and " hidden>" in markup[box:box + 300]
    strings = (_ROOT / "web" / "static" / "js" / "i18n.js").read_text(encoding="utf-8")
    for key in ("runs_search", "runs_no_match", "runs_show_more", "runs_search_capped",
                "run_again", "run_again_title", "copy_link", "msg_link_copied", "msg_link_copy_failed"):
        assert strings.count(f"    {key}: ") == 2, key


def test_the_page_never_puts_search_words_in_a_request():
    api = (_ROOT / "web" / "static" / "js" / "api.js").read_text(encoding="utf-8")
    start = api.index("export const listRuns")
    signature = api[start:api.index(";", start)]
    assert "limit" in signature and "offset" in signature
    assert "q=" not in signature and "query" not in signature and "search" not in signature
