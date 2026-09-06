"""Stored audit -> HTTP bytes -> shipped renderer, with no provider requests.

The summary already distinguished abstention. The detail panel did not, and
malformed findings could either look clean or throw. Keep that failure at the
delivery seam; a test of a copied Python formatter would not protect the UI.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api import runs
from api.main import app

ROOT = Path(__file__).resolve().parents[1]
PARTIAL = {
    "schema_version": 1, "status": "partial", "non_blocking": True,
    "findings_count": 0, "findings": [],
    "decision_thresholds": {
        "status": "completed", "candidate_lines": 1, "unqualified": 0, "findings": [],
    },
    "citation_material_scope": {
        "status": "partial", "candidate_segments": 3, "checked": 1,
        "unverifiable": 2, "mismatched": 0, "findings": [],
    },
}


def render_details(payload, root: Path, language="English") -> dict:
    """Read the real artifact route and render exactly its body in actual JS."""
    run_id = "20260906T010203Z-0123456789abcdef0123456789abcdef"
    directory = root / run_id
    directory.mkdir(exist_ok=True)
    (directory / "status.json").write_text(json.dumps({"done": True, "stage": "Done"}), encoding="utf-8")
    (directory / "commercialization_report.md").write_text("# Retained report", encoding="utf-8")
    (directory / "report_audit.json").write_text(json.dumps(payload), encoding="utf-8")
    with patch.object(runs, "DEFAULT_OUTPUT_ROOT", root), TestClient(app) as client:
        response = client.get(f"/api/runs/{run_id}/report-audit")
        assert response.status_code == 200
        assert response.json() == payload  # Do not silently rewrite corrupt storage.
        assert client.get(f"/api/runs/{run_id}/report").text == "# Retained report"
        assert client.get(f"/api/runs/{run_id}").status_code == 200
        assert client.get(f"/api/runs/{run_id}/progress").status_code == 200

    node = shutil.which("node")
    assert node, "Node is required for the browser contract; do not silently skip it."
    script = r"""
      const fs = require('node:fs'), vm = require('node:vm');
      const input = JSON.parse(fs.readFileSync(0, 'utf8'));
      class Element {
        constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.textContent = ''; }
        append(...children) { this.children.push(...children); }
      }
      const context = vm.createContext({
        localStorage: {getItem: () => input.language},
        document: {createElement: tag => new Element(tag)},
      });
      for (const name of ['i18n.js', 'result.js']) {
        const code = fs.readFileSync(input.root + '/web/static/js/' + name, 'utf8')
          .replace(/^import .*;\r?\n/gm, '').replace(/export /g, '');
        vm.runInContext(code, context);
      }
      context.payload = input.payload;
      const tree = vm.runInContext('renderReportAudit(payload)', context);
      function flatten(node) { return [node.textContent, ...node.children.map(flatten)].join(' '); }
      function tags(node) { return [node.tag, ...node.children.flatMap(tags)]; }
      const sections = Object.fromEntries(tree.children.filter(n => n.dataset.check)
        .map(n => [n.dataset.check, flatten(n)]));
      console.log(JSON.stringify({text: flatten(tree), sections, tags: tags(tree)}));
    """
    result = subprocess.run(
        [node, "-e", script], input=json.dumps({"root": str(ROOT), "payload": response.json(), "language": language}),
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("language", ["English", "Simplified Chinese"])
def test_partial_counts_and_abstention_reach_detail_panel(tmp_path, language):
    """Empty warnings do not clear the two uncheckable citation segments."""
    panel = render_details(PARTIAL, tmp_path, language)
    if language == "English":
        assert "Candidates: 3; checked: 1; unverifiable: 2" in panel["text"]
        assert "Only part" in panel["text"]
        assert "No issue was found" not in panel["text"]
    else:
        assert "候选片段：3；已检查：1；无法判断：2" in panel["text"]
        assert "无法判断的片段不算通过" in panel["text"]
        assert "未发现问题" not in panel["text"]


@pytest.mark.parametrize("bad", [None, {}, {"status": "completed", "findings": {}},
    {**PARTIAL, "findings": {}}, {**PARTIAL, "findings": [None], "findings_count": 1},
    {**PARTIAL, "findings_count": "0"}, {**PARTIAL, "schema_version": 2},
    {**PARTIAL, "status": "unknown"}, {**PARTIAL, "findings": [{"check": "other", "excerpt": "x"}], "findings_count": 1},
])
def test_unreadable_artifacts_neither_pass_nor_throw(bad, tmp_path):
    """Malformed detail bytes remain downloadable without crashing the panel."""
    panel = render_details(bad, tmp_path)
    assert "missing or unreadable" in panel["text"]
    assert "No issue was found" not in panel["text"]


@pytest.mark.parametrize("field,value", [
    ("checked", "1"), ("checked", True), ("checked", -1),
    ("unverifiable", 50), ("findings", [None]), ("reason", {}),
    ("status", "completed"),
])
def test_bad_nested_section_keeps_neighbour_but_never_claims_clean(field, value, tmp_path):
    """A readable threshold section must survive damage to citation coverage."""
    payload = deepcopy(PARTIAL)
    payload["status"] = "completed"
    payload["citation_material_scope"][field] = value
    panel = render_details(payload, tmp_path)
    assert "Candidate labels: 1; unqualified: 0" in panel["sections"]["decision_thresholds"]
    assert "unreadable" in panel["sections"]["citation_material_scope"]
    assert "No issue was found" not in panel["text"]


def test_non_english_audit_explains_why_it_cannot_check(tmp_path):
    """Language support is an abstention reason, not a report failure."""
    from academic_agent.report_audit import audit_report
    collection = SimpleNamespace(academic_sources=[], patent_sources=[], market_sources=[])
    payload = audit_report("中文报告", collection=collection,
                           decision_gate={}, output_language="Simplified Chinese")
    panel = render_details(payload, tmp_path)
    assert "English reports only" in panel["text"]
    assert "no pass is claimed" in panel["text"]
    assert "No issue was found" not in panel["text"]


def test_no_candidate_is_not_a_clean_bill(tmp_path):
    """Zero eligible segments means not applicable, not all claims verified."""
    from academic_agent.report_audit import audit_report
    collection = SimpleNamespace(academic_sources=[], patent_sources=[], market_sources=[])
    payload = audit_report("An exploratory discussion.", collection=collection,
                           decision_gate={}, output_language="English")
    panel = render_details(payload, tmp_path)
    assert "No candidate matched" in panel["text"]
    assert "No issue was found" not in panel["text"]


def test_completed_check_and_real_warning_remain_visible(tmp_path):
    """Positive controls prevent a blanket-unavailable implementation passing."""
    payload = deepcopy(PARTIAL)
    payload["status"] = "completed"
    payload["citation_material_scope"].update(status="completed", checked=3, unverifiable=0)
    assert "No issue was found" in render_details(payload, tmp_path)["text"]
    finding = {"check": "decision_threshold_provenance", "excerpt": "Pass Threshold: <img src=x>"}
    payload.update(findings=[finding], findings_count=1)
    payload["decision_thresholds"].update(unqualified=1, findings=[finding])
    panel = render_details(payload, tmp_path)
    assert "Pass Threshold: <img src=x>" in panel["text"]
    assert "img" not in panel["tags"]
    assert "No issue was found" not in panel["text"]
