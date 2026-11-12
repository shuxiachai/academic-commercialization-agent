"""The model field's guide: what was measured, and buttons that fill a name in.

A new account reaches a form with a required, empty "Model" box. The
placeholder gave one example and a typed-suggestion list offered two names,
neither saying which had been run through this pipeline or how it did. The
served byok_fields.js and i18n.js run in Node against a minimal DOM built from
the served page's own ids; the rows of the tables come from the module itself,
and tests/test_byok_client.py holds each row to the result document it quotes.
"""

import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

from api.main import app

_SCRIPT = Path(__file__).with_name("js") / "byok_fields_contract.mjs"


def measured_rows(source: str) -> dict[str, list[dict]]:
    """MODEL_MEASURED as written in byok_fields.js."""
    block = re.search(r"MODEL_MEASURED = \{(.*?)\n\};", source, re.S)[1]
    rows: dict[str, list[dict]] = {}
    for provider, body in re.findall(r"(\w+): \[(.*?)\n  \],", block, re.S):
        rows[provider] = [
            {"model": model, "inRange": int(in_range), "runs": int(runs), "date": date}
            for model, in_range, runs, date in re.findall(
                r'\{ model: "([^"]+)", inRange: (\d+), runs: (\d+), date: "([^"]+)" \}', body)
        ]
    return rows


def suggestion_rows(source: str) -> dict[str, list[str]]:
    block = re.search(r"MODEL_SUGGESTIONS = \{(.*?)\};", source, re.S)[1]
    return {provider: re.findall(r'"([^"]+)"', names)
            for provider, names in re.findall(r"(\w+):\s*\[([^\]]*)\]", block)}


@pytest.mark.parametrize("scenario", [
    "measured", "fill", "typed", "unmeasured", "switch", "language", "reset",
])
def test_the_model_guide_follows_the_provider_and_never_fills_the_field_itself(scenario):
    node = shutil.which("node")
    assert node, "Node is required; missing execution is not a passing seam"
    client = TestClient(app)
    page = client.get("/")
    assert page.status_code == 200
    with TemporaryDirectory() as tmp:
        work = Path(tmp)
        sources = {}
        for name in ("byok_fields.js", "i18n.js"):
            served = client.get(f"/static/js/{name}")
            assert served.status_code == 200, name
            sources[name] = served.text
            (work / name).write_text(served.text, encoding="utf-8")
        (work / "input.json").write_text(json.dumps({
            "html": page.text,
            "measured": measured_rows(sources["byok_fields.js"]),
            "suggestions": suggestion_rows(sources["byok_fields.js"]),
        }, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run([node, str(_SCRIPT), str(work), scenario], capture_output=True,
                                text=True, encoding="utf-8", timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {scenario}" in result.stdout


_REPO = Path(__file__).resolve().parents[1]
_SOURCE = _REPO / "web" / "static" / "js" / "byok_fields.js"
# Where each figure is stated, and the words that state it there.
_STATED_IN = {
    "qwen3.8-max": ("results-2026-10-19-heldout-trl-v2.md", "{in_range}/{runs} in range"),
    "qwen3.7-plus": ("results-2026-10-18-heldout-trl-v1.md", "{in_range}/{runs} in range"),
    "deepseek-v4-pro": (
        "results-2026-11-08-heldout-spot-check-deepseek-v4-pro-b.md", "**In range {in_range}/{runs}**"),
    "deepseek-v4.1-flash-1017": (
        "results-2026-11-11-heldout-spot-check-deepseek-v4.1-flash.md", "**TRL in range {in_range}/{runs}.**"),
}


def test_every_measured_figure_is_the_one_its_result_document_states():
    """The page shows a visitor a number about a model. It is a result's
    headline or it is not shown: a row with no document, or a figure the
    document does not state, fails here."""
    rows = measured_rows(_SOURCE.read_text(encoding="utf-8"))
    listed = [row for provider_rows in rows.values() for row in provider_rows]
    assert {row["model"] for row in listed} == set(_STATED_IN)
    for row in listed:
        name, words = _STATED_IN[row["model"]]
        text = (_REPO / "docs" / name).read_text(encoding="utf-8")
        assert f"`{row['model']}`" in text or f"on {row['model']}" in text, row
        assert words.format(in_range=row["inRange"], runs=row["runs"]) in text, row
        assert row["date"] in text, row
        assert 0 < row["inRange"] <= row["runs"], row


def test_measured_models_are_names_the_form_accepts_listed_best_supported_first():
    from academic_agent.llm_config import BYOK_MODEL_PATTERN
    from api.models import BYOK_PROVIDERS

    rows = measured_rows(_SOURCE.read_text(encoding="utf-8"))
    assert rows, "No measured rows were read"
    assert set(rows) <= set(BYOK_PROVIDERS)
    for provider, provider_rows in rows.items():
        assert provider_rows, provider
        names = [row["model"] for row in provider_rows]
        assert len(names) == len(set(names)), provider
        for name in names:
            assert re.fullmatch(BYOK_MODEL_PATTERN.pattern, name), name
        # By share of runs in range, and by more runs where two shares are equal.
        ordered = sorted(provider_rows, key=lambda row: (-row["inRange"] / row["runs"], -row["runs"]))
        assert provider_rows == ordered, provider


def test_the_guide_sits_under_the_model_field_and_both_languages_can_say_it():
    page = (_REPO / "web" / "index.html").read_text(encoding="utf-8")
    form = page[page.index('id="byok-form"'):page.index('id="byok-submit"')]
    order = [form.index(f'id="{name}"') for name in (
        "byok-model", "byok-model-options", "byok-model-note", "byok-model-chips", "byok-search")]
    assert order == sorted(order)
    field = re.search(r'<input[^>]*id="byok-model"[^>]*>', form)[0]
    # The note is the field's description, so a screen reader hears it there.
    assert 'aria-describedby="byok-model-note"' in field
    assert "value=" not in field

    source = _SOURCE.read_text(encoding="utf-8")
    english, chinese = source[source.index("const STRINGS"):].split('"Simplified Chinese": {', 1)
    keys = set(re.findall(r"^\s+(\w+):", english, re.M)) - {"English"}
    assert {"model_measured", "model_unmeasured", "model_chip_measured", "model_chip_plain"} <= keys
    assert keys == set(re.findall(r"^\s{4}(\w+):", chinese, re.M))
