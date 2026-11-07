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


@pytest.mark.parametrize("scenario", ["rows", "unfinished", "nothing_to_compare", "drawn"])
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
        assert call in {"getRun", "getArtifact", "getReport"}, call
    assert "fetch(" not in _COMPARE and "POST" not in _COMPARE
    # Values become text, never markup.
    assert "innerHTML =" not in _COMPARE.replace('innerHTML = ""', "")
