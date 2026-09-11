"""Actual stored artifact bytes reach shipped detail renderers without fake passes."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import runs
from api.main import app

ROOT = Path(__file__).resolve().parents[1]
SCORES = {"overall_score": 65, "trl_score": 6, "mrl_score": 6,
          "patent_strength": 3, "market_accessibility": 3, "evidence_confidence": 4}
GROUNDING = {"checked": 2, "ungrounded": 0, "unverifiable": 1, "findings": []}
CONSISTENCY = {"checked": True, "blockers": 0, "warnings": 0, "findings": []}


@pytest.mark.parametrize("field,maximum", [("trl_score", 9), ("mrl_score", 10),
    ("patent_strength", 5), ("market_accessibility", 5), ("evidence_confidence", 5)])
@pytest.mark.parametrize("value", [1, 3.5, "maximum", 0, 0.5, None, True, "3.5", -1, 11])
def test_normalized_dimension_range_reaches_browser(tmp_path, monkeypatch, field, maximum, value):
    """Integer-only rendering hid 64/109 stored reports with normalized fractions."""
    value = maximum if value == "maximum" else value
    text, rows = display({**SCORES, field: value}, "scores", tmp_path, monkeypatch)
    valid = type(value) in (int, float) and 1 <= value <= maximum
    if valid:
        assert f"{value} / {maximum}" in text
        assert "no conclusion" not in text
    else:
        assert any(row["text"] == "—" for row in rows)
        assert "no conclusion" in text
    assert "65.0" in text  # One bad dimension never erases the healthy neighbour.


def display(payload, artifact, tmp_path, monkeypatch, language="English", *, persist_scores=False):
    run_id = "20260908T010203Z-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    directory = tmp_path / run_id
    directory.mkdir(exist_ok=True)
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    (directory / "status.json").write_text('{"done":true,"stage":"Done"}', encoding="utf-8")
    (directory / "commercialization_report.md").write_text("# Healthy neighbour", encoding="utf-8")
    name = {"scores": "commercialization_scores.json", "grounding": "claim_grounding.json", "consistency": "consistency.json"}[artifact]
    if persist_scores:
        # Exercise the same saver used by fresh and restored scorer output,
        # not a fixture which already contains the expected disclosure.
        from academic_agent.run_output import save_scores

        assert artifact == "scores"
        save_scores(json.dumps(payload), run_id, tmp_path)
        delivered = json.loads((directory / name).read_text(encoding="utf-8"))
    else:
        (directory / name).write_text(json.dumps(payload), encoding="utf-8")
        delivered = payload
    client = TestClient(app)
    response = client.get(f"/api/runs/{run_id}/{artifact}")
    assert response.status_code == 200
    assert response.json() == delivered
    assert client.get(f"/api/runs/{run_id}/report").text == "# Healthy neighbour"
    assert client.get(f"/api/runs/{run_id}/progress").json()["done"] is True
    node = shutil.which("node")
    assert node, "Node is required; this boundary cannot be silently skipped"
    script = r'''
const fs=require('node:fs'), vm=require('node:vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
class Element {
 constructor(tag){Object.assign(this,{tag,children:[],dataset:{},style:{},textContent:'',className:''});}
 append(...items){this.children.push(...items);}
 addEventListener(){}
 set innerHTML(value){this.children=[];}
 querySelector(selector){const id=selector.match(/data-view="([^"]+)"/)[1];return this.children.find(n=>n.dataset.view===id);}
}
const context=vm.createContext({localStorage:{getItem:()=>input.language},
 document:{createElement:tag=>new Element(tag)},
 api:{getArtifact:async()=>input.payload}, container:new Element('main'), payload:input.payload});
for(const name of ['i18n.js','result.js']) vm.runInContext(
 fs.readFileSync(input.root+'/web/static/js/'+name,'utf8').replace(/^import .*;\r?\n/gm,'').replace(/export /g,''),context);
vm.runInContext(`render(container,'fixture',{artifacts:['${input.artifact}']})`,context);
setImmediate(()=>{
 function walk(n){return [{text:String(n.textContent||''),cls:n.className,tag:n.tag},...n.children.flatMap(walk)];}
 const rows=walk(context.container); console.log(JSON.stringify(rows));
});
'''
    result = subprocess.run([node, "-e", script], input=json.dumps({"root": str(ROOT), "artifact": artifact,
                            "payload": response.json(), "language": language}), text=True, encoding="utf-8",
                            capture_output=True, timeout=30, check=True)
    rows = json.loads(result.stdout)
    return " | ".join(row["text"] for row in rows), rows


@pytest.mark.parametrize("artifact", ["scores", "grounding", "consistency"])
@pytest.mark.parametrize("payload", [{}, [], None, False, "wrong root"])
@pytest.mark.parametrize("language", ["English", "Simplified Chinese"])
def test_invalid_root_never_becomes_zero_score_or_a_pass(tmp_path, monkeypatch, artifact, payload, language):
    """The previous renderer printed 0.0 / Nascent or agreement for empty objects."""
    text, rows = display(payload, artifact, tmp_path, monkeypatch, language)
    assert ("no conclusion" if language == "English" else "不能据此得出结论") in text
    assert "0.0" not in text
    assert not any(row["cls"] == "consistency__clear" for row in rows)


@pytest.mark.parametrize("value", [None, True, "65", -1, 101, {}, []])
def test_bad_overall_does_not_hide_valid_dimensions(tmp_path, monkeypatch, value):
    text, rows = display({**SCORES, "overall_score": value}, "scores", tmp_path, monkeypatch)
    assert "no conclusion" in text
    assert "6 / 9" in text
    assert any(row["text"] == "—" for row in rows)
    assert "Nascent" not in text


@pytest.mark.parametrize("payload", [{**GROUNDING, "checked": None}, {**GROUNDING, "ungrounded": 3},
    {**GROUNDING, "unverifiable": -1}, {**GROUNDING, "checked": "2"}, {**GROUNDING, "checked": True}])
def test_invalid_coverage_counters_are_not_measurements(tmp_path, monkeypatch, payload):
    text, rows = display(payload, "grounding", tmp_path, monkeypatch)
    assert "no conclusion" in text
    assert not any(row["cls"] == "grounding__stats" for row in rows)


def test_nested_grounding_fault_preserves_healthy_counts_and_row(tmp_path, monkeypatch):
    """A malformed neighbour must neither throw nor suppress real warnings."""
    payload = {**GROUNDING, "ungrounded": 1, "by_domain": {"academic": [], "market": GROUNDING},
               "findings": [None, {"finding_id": "AF1", "status": "ungrounded", "claim": "<img src=x> 26.1%",
                                    "ungrounded_figures": ["26.1%"]}]}
    text, rows = display(payload, "grounding", tmp_path, monkeypatch)
    assert "26.1%" in text and "no conclusion" in text
    assert "2/3" in text
    assert any(row["cls"] == "grounding__stats" for row in rows)
    assert not any(row["tag"] == "img" for row in rows)


@pytest.mark.parametrize("payload", [{**CONSISTENCY, "checked": False}, {**CONSISTENCY, "error": "check failed"}])
def test_skipped_or_failed_consistency_is_not_agreement(tmp_path, monkeypatch, payload):
    text, rows = display(payload, "consistency", tmp_path, monkeypatch)
    assert "not a pass" in text
    assert not any(row["cls"] == "consistency__clear" for row in rows)


@pytest.mark.parametrize("payload", [{**CONSISTENCY, "findings": {}}, {**CONSISTENCY, "warnings": 1},
    {**CONSISTENCY, "checked": "true"}, {**CONSISTENCY, "blockers": -1}])
def test_bad_consistency_shape_or_count_cannot_clear_report(tmp_path, monkeypatch, payload):
    text, rows = display(payload, "consistency", tmp_path, monkeypatch)
    assert "no conclusion" in text
    assert not any(row["cls"] == "consistency__clear" for row in rows)


def test_valid_results_remain_visible_and_zero_coverage_is_not_pass(tmp_path, monkeypatch):
    """Positive controls reject an implementation which hides every detail."""
    text, _ = display(SCORES, "scores", tmp_path, monkeypatch)
    assert "65.0" in text and "6 / 9" in text and "no conclusion" not in text
    text, _ = display(CONSISTENCY, "consistency", tmp_path, monkeypatch)
    assert "recommendation matches the score" in text
    text, rows = display({**GROUNDING, "checked": 0}, "grounding", tmp_path, monkeypatch)
    assert "not a pass" in text
    assert not any(row["cls"].endswith("stat--ok") for row in rows)
