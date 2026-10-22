"""A failing retrieval lane in production opens an issue; recovery closes it."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "retrieval-health.yml"
SCRIPT = ROOT / "scripts" / "retrieval_health_alert.py"

_spec = importlib.util.spec_from_file_location("retrieval_health_alert", SCRIPT)
alert = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(alert)


def health(failing=(), mostly_empty=(), lanes=None):
    lanes = lanes if lanes is not None else [
        {"lane": "OA-Cited", "observed_runs": 12, "empty_runs": 12, "failed_runs": 12},
        {"lane": "S2", "observed_runs": 5, "empty_runs": 4, "failed_runs": 1},
    ]
    return {"window": 20, "runs_examined": 12, "lanes": lanes,
            "failing": list(failing), "mostly_empty": list(mostly_empty)}


def test_a_failing_lane_alerts_with_counts_and_what_to_check():
    decision, body = alert.decide(health(failing=["OA-Cited"], mostly_empty=["S2"]))
    assert decision == "alert"
    assert "| OA-Cited | 12 | 12 | 12 |" in body
    assert "- **OA-Cited**: check OpenAlex: OPENALEX_API_KEY and its daily budget." in body
    assert "Mostly empty, not alerted: S2." in body


def test_mostly_empty_lanes_alone_do_not_alert():
    decision, body = alert.decide(health(mostly_empty=["S2"]))
    assert decision == "ok"
    assert "No lane is failing." in body


def test_no_runs_yet_is_not_an_alert():
    assert alert.decide(health(lanes=[]))[0] == "ok"


def test_every_lane_label_gets_a_hint():
    for lane in ("OA-Recent", "S2", "PubMed", "arXiv", "Lens.org", "market web search", "patent web search"):
        assert alert.hint(lane) != "the lane's client", lane


def test_the_script_prints_its_decision_and_writes_the_body(tmp_path):
    source = tmp_path / "health.json"
    source.write_text(json.dumps(health(failing=["S2"])), encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), str(source), str(tmp_path / "body.md")],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "alert"
    assert "SEMANTIC_SCHOLAR_API_KEY" in (tmp_path / "body.md").read_text(encoding="utf-8")


def test_the_workflow_runs_daily_and_keeps_one_issue_in_step():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # YAML 1.1 reads the bare key `on` as True.
    assert workflow[True]["schedule"] and "workflow_dispatch" in workflow[True]
    assert workflow["permissions"] == {"contents": "read", "issues": "write"}
    job = workflow["jobs"]["production"]
    assert job["env"]["HEALTH_CODE"] == "${{ secrets.PRODUCTION_ADMIN_CODE }}"
    script = job["steps"][-1]["run"]
    assert 'if [ -z "${HEALTH_CODE:-}" ]' in script
    assert "/api/health/retrieval?window=20" in script
    for command in ("gh issue create", "gh issue comment", "gh issue close"):
        assert command in script
    assert "exit 1" in script
    # The code goes only into the request header, never into the log.
    assert script.count("$HEALTH_CODE") == 1 and "echo \"$HEALTH_CODE" not in script
