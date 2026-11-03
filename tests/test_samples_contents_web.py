"""The sample reader links each report section from a contents list (#285).

A report runs to eight sections and the reader showed it as one long scroll.
The served reader modules run in Node against a minimal DOM built from the
served page and the served samples; result.js is replaced by a renderer that
emits only the <h2> headings, as test_samples_title_web.py explains. Layout,
print and keyboard behaviour need a real browser and are covered by
e2e/browser_smoke.py.

The fragment scenario guards a trap: a contents link changes only the URL's
fragment, and Chromium fires popstate for that, which the reader treated as
Back/Forward and answered by reading and rendering the sample again.
"""

import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

from api.main import app

_SCRIPT = Path(__file__).with_name("js") / "samples_contents_contract.mjs"
_RESULT_STUB = """\
export const renderMarkdown = (md) => [...md.matchAll(/^## (.*)$/gm)].map(([, text]) => `<h2>${text}</h2>`).join("");
export const citationIndex = () => new Map();
export function attachCitations() {}
"""


@pytest.mark.parametrize("scenario", [
    "each_sample", "rebuilt", "fragment", "failed_read", "deep_link", "wide", "narrow", "no_headings",
])
def test_contents_follow_the_open_sample(scenario):
    """Counter ids, one list per render, and fragment links that do not reload the sample."""
    node = shutil.which("node")
    assert node, "Node is required; missing execution is not a passing seam"
    client = TestClient(app)
    page = client.get("/samples")
    listed = client.get("/api/samples")
    assert page.status_code == 200 and listed.status_code == 200
    markdown = {}
    for sample in listed.json():
        served = client.get(f"/api/samples/{sample['slug']}")
        assert served.status_code == 200, sample["slug"]
        markdown[sample["slug"]] = served.text
    with TemporaryDirectory() as tmp:
        work = Path(tmp)
        for name in ("samples.js", "samples_i18n.js", "i18n.js"):
            served = client.get(f"/static/js/{name}")
            assert served.status_code == 200, name
            (work / name).write_text(served.text, encoding="utf-8")
        (work / "result.js").write_text(_RESULT_STUB, encoding="utf-8")
        (work / "input.json").write_text(
            json.dumps({"html": page.text, "samples": listed.json(), "markdown": markdown}, ensure_ascii=False),
            encoding="utf-8")
        result = subprocess.run([node, str(_SCRIPT), str(work), scenario], capture_output=True,
                                text=True, encoding="utf-8", timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {scenario}" in result.stdout
