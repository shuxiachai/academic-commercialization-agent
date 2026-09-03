"""Report-audit persistence, API, and browser wiring tests.

The difficult failure class in this project is not computing the wrong value;
it is computing and storing the right value while a later boundary silently
drops it.  These tests therefore cross disk, both API models, and the browser
artifact name rather than stopping at the audit function.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import runs
from api.main import app
from academic_agent.pipeline_worker import _merge_status_fields


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = {
    "status": "completed",
    "non_blocking": True,
    "findings": 1,
    "unqualified_thresholds": 1,
    "citation_scope_checked": 2,
    "citation_scope_mismatches": 0,
    "citation_scope_unverifiable": 1,
}
ARTIFACT = {
    "schema_version": 1,
    "status": "completed",
    "non_blocking": True,
    "findings_count": 1,
    "findings": [
        {
            "check": "decision_threshold_provenance",
            "excerpt": "Pass Threshold: 90%.",
        }
    ],
}


def test_report_audit_survives_disk_both_api_endpoints_and_artifact_download() -> None:
    run_id = "20260903T010203Z-0123456789abcdef0123456789abcdef"
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        run_directory = root / run_id
        run_directory.mkdir()
        (run_directory / "status.json").write_text(
            json.dumps(
                {
                    "stage": "Done",
                    "done": True,
                    "topic": "solid-state battery",
                    "report_audit": SUMMARY,
                }
            ),
            encoding="utf-8",
        )
        (run_directory / "report_audit.json").write_text(
            json.dumps(ARTIFACT), encoding="utf-8"
        )

        with patch.object(runs, "DEFAULT_OUTPUT_ROOT", root):
            client = TestClient(app)
            status = client.get(f"/api/runs/{run_id}")
            progress = client.get(f"/api/runs/{run_id}/progress")
            artifact = client.get(f"/api/runs/{run_id}/report-audit")

    assert status.status_code == 200
    assert progress.status_code == 200
    assert artifact.status_code == 200
    assert status.json()["report_audit"] == SUMMARY
    assert progress.json()["report_audit"] == SUMMARY
    assert "report-audit" in status.json()["artifacts"]
    assert artifact.json() == ARTIFACT


def test_later_status_writes_cannot_erase_a_completed_report_audit() -> None:
    merged = _merge_status_fields(
        {"report_audit": SUMMARY},
        stage="Done",
        done=True,
        error=None,
        output_language=None,
        source_counts=None,
        topic=None,
    )

    assert merged["report_audit"] == SUMMARY


def test_browser_requests_exactly_the_artifact_name_the_server_serves() -> None:
    source = (ROOT / "web/static/js/result.js").read_text(encoding="utf-8")

    assert runs._ARTIFACTS["report-audit"] == "report_audit.json"
    assert 'artifacts.includes("report-audit")' in source
    assert 'getArtifact(runId, "report-audit")' in source
    assert "renderReportAudit(audit)" in source
