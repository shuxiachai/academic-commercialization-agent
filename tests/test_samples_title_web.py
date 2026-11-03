"""The sample reader names the browser tab after the open sample (#284).

Every /samples/<slug> page used to keep the static "Sample reports" title, so
tabs, bookmarks and history entries for different samples looked identical.
The served reader modules run in Node against a minimal DOM built from the
served page (its <title> and element ids) and the served sample list. Only
result.js is replaced: its renderer has its own test in test_samples.py, and
it imports the credentialed api.js, which this page must never load.
"""

import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

from api.main import app

_SCRIPT = Path(__file__).with_name("js") / "samples_title_contract.mjs"
_RESULT_STUB = """\
export const renderMarkdown = (md) => md;
export const citationIndex = () => new Map();
export function attachCitations() {}
"""


@pytest.mark.parametrize("scenario", [
    "index", "each_sample", "history", "language", "unknown_slug",
    "stale_response", "list_failed", "empty_list",
])
def test_tab_title_follows_the_open_sample(scenario):
    """Deep links, Back/Forward and a language switch keep the title on the visible report."""
    node = shutil.which("node")
    assert node, "Node is required; missing execution is not a passing seam"
    client = TestClient(app)
    page = client.get("/samples")
    listed = client.get("/api/samples")
    assert page.status_code == 200 and listed.status_code == 200
    with TemporaryDirectory() as tmp:
        work = Path(tmp)
        for name in ("samples.js", "samples_i18n.js", "i18n.js"):
            served = client.get(f"/static/js/{name}")
            assert served.status_code == 200, name
            (work / name).write_text(served.text, encoding="utf-8")
        (work / "result.js").write_text(_RESULT_STUB, encoding="utf-8")
        (work / "input.json").write_text(
            json.dumps({"html": page.text, "samples": listed.json()}, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run([node, str(_SCRIPT), str(work), scenario], capture_output=True,
                                text=True, encoding="utf-8", timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {scenario}" in result.stdout
