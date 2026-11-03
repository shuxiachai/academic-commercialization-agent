"""Production says which commit it serves, and CI waits for the merged one."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from fastapi.testclient import TestClient

from academic_agent.checkpoint_runtime import pipeline_revision
from api import main
from api.main import app

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "deploy-check.yml"


class HealthRevisionTests(unittest.TestCase):
    def test_health_reports_the_revision_this_process_serves(self):
        body = TestClient(app).get("/health").json()
        self.assertEqual(body["pipeline_revision"], main._PIPELINE_REVISION)
        self.assertEqual(body["pipeline_revision"], pipeline_revision())

    def test_railway_supplies_the_commit(self):
        sha = "0123456789abcdef0123456789abcdef01234567"
        with patch.dict("os.environ", {"RAILWAY_GIT_COMMIT_SHA": sha}):
            self.assertEqual(pipeline_revision(), f"git:{sha}")


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

    def test_it_follows_a_passing_tests_run_on_main(self):
        # YAML 1.1 reads the bare key `on` as True.
        trigger = self.workflow[True]["workflow_run"]
        self.assertEqual(trigger, {"workflows": ["Tests"], "types": ["completed"], "branches": ["main"]})
        condition = self.workflow["jobs"]["production"]["if"]
        self.assertIn("conclusion == 'success'", condition)
        self.assertIn("event == 'push'", condition)

    def test_it_compares_the_health_revision_with_the_merged_commit(self):
        script = self.workflow["jobs"]["production"]["steps"][0]["run"]
        self.assertIn("/health", script)
        self.assertIn(".pipeline_revision", script)
        self.assertEqual(self.workflow["jobs"]["production"]["env"]["TARGET"],
                         "${{ github.event.workflow_run.head_sha }}")


if __name__ == "__main__":
    unittest.main()
