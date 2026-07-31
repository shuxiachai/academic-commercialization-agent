"""Tests for the FastAPI layer.

No worker subprocess is ever started: subprocess.Popen is patched and run
directories are built by hand, so these tests consume no API credits and
need no network.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api import runs
from api.main import app


def _run_id(suffix: str = "abcdef0123") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{suffix}"


class _ApiTestCase(unittest.TestCase):
    """Redirects the output root to a temp dir and clears the run registry."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self._patcher = patch.object(runs, "DEFAULT_OUTPUT_ROOT", self.tmp)
        self._patcher.start()
        runs._registry.clear()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self._patcher.stop()
        runs._registry.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_run(
        self,
        run_id: str | None = None,
        *,
        status: dict | None = None,
        report: str | None = None,
        scores: dict | None = None,
        cancelled: bool = False,
        error_log: str | None = None,
    ) -> str:
        """Create a run directory that looks like a finished worker left it."""
        run_id = run_id or _run_id()
        d = self.tmp / run_id
        d.mkdir(parents=True, exist_ok=True)
        if status is not None:
            (d / "status.json").write_text(json.dumps(status), encoding="utf-8")
        if report is not None:
            (d / "commercialization_report.md").write_text(report, encoding="utf-8")
        if scores is not None:
            (d / "commercialization_scores.json").write_text(json.dumps(scores), encoding="utf-8")
        if cancelled:
            (d / "cancelled.marker").write_text("now", encoding="utf-8")
        if error_log is not None:
            (d / "error.log").write_text(error_log, encoding="utf-8")
        return run_id

    def _live_proc(self) -> MagicMock:
        proc = MagicMock()
        proc.poll.return_value = None      # still running
        return proc


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

class HealthTests(_ApiTestCase):

    def test_returns_ok(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_reports_capacity(self):
        body = self.client.get("/health").json()
        self.assertEqual(body["active_runs"], 0)
        self.assertEqual(body["max_concurrent"], runs.MAX_CONCURRENT)

    @patch("academic_agent.llm_config._detect_provider", return_value="deepseek")
    def test_reports_resolved_provider(self, _mock):
        self.assertEqual(self.client.get("/health").json()["llm_provider"], "deepseek")

    @patch(
        "academic_agent.llm_config._detect_provider",
        side_effect=RuntimeError("No LLM API key found."),
    )
    def test_missing_key_reports_null_provider_not_500(self, _mock):
        """An unconfigured server must still answer /health so it can say why."""
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["llm_provider"])

    @patch("api.runs.subprocess.Popen")
    def test_active_run_counted(self, mock_popen):
        mock_popen.return_value = self._live_proc()
        self.client.post("/api/runs", json={"topic": "counted topic"})
        self.assertEqual(self.client.get("/health").json()["active_runs"], 1)


# ---------------------------------------------------------------------------
# POST /api/runs
# ---------------------------------------------------------------------------

class SubmitRunTests(_ApiTestCase):

    @patch("api.runs.subprocess.Popen")
    def test_accepted_returns_202_and_run_id(self, mock_popen):
        mock_popen.return_value = self._live_proc()
        r = self.client.post("/api/runs", json={"topic": "solid state batteries"})
        self.assertEqual(r.status_code, 202)
        self.assertTrue(r.json()["run_id"])
        self.assertEqual(r.json()["state"], "running")

    @patch("api.runs.subprocess.Popen")
    def test_worker_invoked_with_topic(self, mock_popen):
        mock_popen.return_value = self._live_proc()
        self.client.post("/api/runs", json={"topic": "perovskite solar cells"})
        cmd = mock_popen.call_args[0][0]
        self.assertIn("academic_agent.pipeline_worker", cmd)
        self.assertIn("perovskite solar cells", cmd)

    @patch("api.runs.subprocess.Popen")
    def test_language_flag_forwarded(self, mock_popen):
        mock_popen.return_value = self._live_proc()
        self.client.post(
            "/api/runs",
            json={"topic": "cultivated meat", "language": "Simplified Chinese"},
        )
        cmd = mock_popen.call_args[0][0]
        self.assertIn("--language", cmd)
        self.assertIn("Simplified Chinese", cmd)

    @patch("api.runs.subprocess.Popen")
    def test_weight_profile_flag_forwarded(self, mock_popen):
        mock_popen.return_value = self._live_proc()
        self.client.post(
            "/api/runs",
            json={"topic": "CAR-T therapy", "weight_profile": "biomedical"},
        )
        cmd = mock_popen.call_args[0][0]
        self.assertIn("--weight-profile", cmd)
        self.assertIn("biomedical", cmd)

    @patch("api.runs.subprocess.Popen")
    def test_omitted_flags_are_not_passed(self, mock_popen):
        mock_popen.return_value = self._live_proc()
        self.client.post("/api/runs", json={"topic": "green hydrogen"})
        cmd = mock_popen.call_args[0][0]
        self.assertNotIn("--language", cmd)
        self.assertNotIn("--weight-profile", cmd)

    def test_short_topic_rejected(self):
        r = self.client.post("/api/runs", json={"topic": "ab"})
        self.assertEqual(r.status_code, 422)

    def test_missing_topic_rejected(self):
        self.assertEqual(self.client.post("/api/runs", json={}).status_code, 422)

    @patch("api.runs.subprocess.Popen")
    def test_concurrency_limit_returns_429(self, mock_popen):
        mock_popen.return_value = self._live_proc()
        for _ in range(runs.MAX_CONCURRENT):
            self.assertEqual(
                self.client.post("/api/runs", json={"topic": "some topic"}).status_code, 202
            )
        r = self.client.post("/api/runs", json={"topic": "one too many"})
        self.assertEqual(r.status_code, 429)

    @patch("api.runs.subprocess.Popen")
    def test_finished_run_frees_a_slot(self, mock_popen):
        done = MagicMock()
        done.poll.return_value = 0          # already exited
        mock_popen.return_value = done
        for _ in range(runs.MAX_CONCURRENT + 2):
            r = self.client.post("/api/runs", json={"topic": "topic"})
            self.assertEqual(r.status_code, 202)

    @patch("api.runs.subprocess.Popen", side_effect=OSError("cannot spawn"))
    def test_spawn_failure_returns_500(self, _mock_popen):
        r = self.client.post("/api/runs", json={"topic": "valid topic here"})
        self.assertEqual(r.status_code, 500)


# ---------------------------------------------------------------------------
# GET /api/runs/{run_id} — state derivation
# ---------------------------------------------------------------------------

class RunStateTests(_ApiTestCase):

    def test_unknown_run_returns_404(self):
        self.assertEqual(self.client.get("/api/runs/20260101T000000Z-nope").status_code, 404)

    def test_completed_state(self):
        rid = self._make_run(status={"done": True, "stage": "finished", "topic": "x"})
        body = self.client.get(f"/api/runs/{rid}").json()
        self.assertEqual(body["state"], "completed")

    def test_failed_state_from_status_error(self):
        rid = self._make_run(status={"done": False, "error": "LLM refused"})
        body = self.client.get(f"/api/runs/{rid}").json()
        self.assertEqual(body["state"], "failed")
        self.assertIn("LLM refused", body["error"])

    def test_cancelled_state(self):
        rid = self._make_run(status={"done": False}, cancelled=True)
        self.assertEqual(self.client.get(f"/api/runs/{rid}").json()["state"], "cancelled")

    def test_timeout_state_from_error_log(self):
        rid = self._make_run(
            status={"done": False}, error_log="Analysis timed out after 30 minutes."
        )
        self.assertEqual(self.client.get(f"/api/runs/{rid}").json()["state"], "timeout")

    def test_crashed_worker_reports_failed_with_reason(self):
        rid = self._make_run(status={"done": False}, error_log="Traceback: boom")
        body = self.client.get(f"/api/runs/{rid}").json()
        self.assertEqual(body["state"], "failed")
        self.assertIn("boom", body["error"])

    @patch("api.runs.subprocess.Popen")
    def test_live_run_reports_running_with_elapsed(self, mock_popen):
        mock_popen.return_value = self._live_proc()
        rid = self.client.post("/api/runs", json={"topic": "live topic"}).json()["run_id"]
        body = self.client.get(f"/api/runs/{rid}").json()
        self.assertEqual(body["state"], "running")
        self.assertIsNotNone(body["elapsed_seconds"])

    def test_stage_and_source_counts_exposed(self):
        rid = self._make_run(status={
            "done": False, "stage": "Phase 1", "source_counts": {"academic": 6},
        })
        # No live process and not done → failed, but the status fields still surface.
        body = self.client.get(f"/api/runs/{rid}").json()
        self.assertEqual(body["stage"], "Phase 1")
        self.assertEqual(body["source_counts"], {"academic": 6})

    def test_artifacts_listed(self):
        rid = self._make_run(status={"done": True}, report="# Report", scores={"overall": 70})
        body = self.client.get(f"/api/runs/{rid}").json()
        self.assertIn("report", body["artifacts"])
        self.assertIn("scores", body["artifacts"])

    def test_path_traversal_run_id_rejected(self):
        for evil in ["..", "../etc", "..%2Fetc"]:
            with self.subTest(run_id=evil):
                r = self.client.get(f"/api/runs/{evil}")
                self.assertIn(r.status_code, (404, 422))


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

class ArtifactTests(_ApiTestCase):

    def test_report_returned_as_markdown(self):
        rid = self._make_run(status={"done": True}, report="# Title\n\nBody text.")
        r = self.client.get(f"/api/runs/{rid}/report")
        self.assertEqual(r.status_code, 200)
        self.assertIn("# Title", r.text)
        self.assertIn("markdown", r.headers["content-type"])

    def test_report_missing_returns_409(self):
        rid = self._make_run(status={"done": True})
        r = self.client.get(f"/api/runs/{rid}/report")
        self.assertEqual(r.status_code, 409)

    def test_report_unknown_run_returns_404(self):
        self.assertEqual(
            self.client.get("/api/runs/20260101T000000Z-nope/report").status_code, 404
        )

    def test_scores_artifact_served_as_json(self):
        rid = self._make_run(status={"done": True}, scores={"overall_score": 65})
        r = self.client.get(f"/api/runs/{rid}/scores")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["overall_score"], 65)

    def test_unknown_artifact_name_returns_404(self):
        rid = self._make_run(status={"done": True})
        r = self.client.get(f"/api/runs/{rid}/not_an_artifact")
        self.assertEqual(r.status_code, 404)
        self.assertIn("Unknown artifact", r.json()["detail"])

    def test_absent_artifact_returns_409_listing_available(self):
        rid = self._make_run(status={"done": True}, report="# R")
        r = self.client.get(f"/api/runs/{rid}/scores")
        self.assertEqual(r.status_code, 409)
        self.assertIn("report", r.json()["detail"])


# ---------------------------------------------------------------------------
# DELETE /api/runs/{run_id}
# ---------------------------------------------------------------------------

class CancelRunTests(_ApiTestCase):

    @patch("api.runs.subprocess.Popen")
    def test_cancel_live_run_marks_cancelled(self, mock_popen):
        proc = self._live_proc()
        mock_popen.return_value = proc
        rid = self.client.post("/api/runs", json={"topic": "cancel me"}).json()["run_id"]

        r = self.client.delete(f"/api/runs/{rid}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["state"], "cancelled")
        proc.terminate.assert_called_once()

    @patch("api.runs.subprocess.Popen")
    def test_cancel_frees_concurrency_slot(self, mock_popen):
        mock_popen.return_value = self._live_proc()
        ids = [
            self.client.post("/api/runs", json={"topic": f"topic number {i}"}).json()["run_id"]
            for i in range(runs.MAX_CONCURRENT)
        ]
        self.assertEqual(self.client.post("/api/runs", json={"topic": "blocked"}).status_code, 429)
        self.client.delete(f"/api/runs/{ids[0]}")
        self.assertEqual(self.client.post("/api/runs", json={"topic": "now ok"}).status_code, 202)

    def test_cancel_finished_run_returns_404(self):
        rid = self._make_run(status={"done": True})
        self.assertEqual(self.client.delete(f"/api/runs/{rid}").status_code, 404)


# ---------------------------------------------------------------------------
# GET /api/runs
# ---------------------------------------------------------------------------

class ListRunsTests(_ApiTestCase):

    def test_empty_list(self):
        body = self.client.get("/api/runs").json()
        self.assertEqual(body["runs"], [])
        self.assertEqual(body["total"], 0)

    def test_lists_runs_newest_first(self):
        self._make_run("20260101T000000Z-aaaaaaaaaa", status={"done": True, "topic": "older"})
        self._make_run("20260601T000000Z-bbbbbbbbbb", status={"done": True, "topic": "newer"})
        body = self.client.get("/api/runs").json()
        self.assertEqual(body["total"], 2)
        self.assertEqual(body["runs"][0]["topic"], "newer")

    def test_benchmark_dir_excluded(self):
        (self.tmp / "benchmark").mkdir()
        self._make_run(status={"done": True, "topic": "real run"})
        body = self.client.get("/api/runs").json()
        self.assertEqual(body["total"], 1)

    def test_limit_respected(self):
        for i in range(5):
            self._make_run(f"2026010{i}T000000Z-cccccccccc", status={"done": True})
        self.assertEqual(len(self.client.get("/api/runs?limit=2").json()["runs"]), 2)

    def test_invalid_limit_rejected(self):
        self.assertEqual(self.client.get("/api/runs?limit=0").status_code, 422)


# ---------------------------------------------------------------------------
# Timeout reaper
# ---------------------------------------------------------------------------

class TimeoutReaperTests(_ApiTestCase):

    @patch("api.runs.subprocess.Popen")
    def test_reaps_run_past_deadline(self, mock_popen):
        proc = self._live_proc()
        mock_popen.return_value = proc
        rid = self.client.post("/api/runs", json={"topic": "slow topic"}).json()["run_id"]

        # Backdate the start so the handle looks overdue.
        runs._registry[rid].started -= runs.TIMEOUT_SECONDS + 1

        killed = runs.reap_timeouts()
        self.assertIn(rid, killed)
        proc.terminate.assert_called_once()
        self.assertEqual(self.client.get(f"/api/runs/{rid}").json()["state"], "timeout")

    @patch("api.runs.subprocess.Popen")
    def test_healthy_run_not_reaped(self, mock_popen):
        mock_popen.return_value = self._live_proc()
        rid = self.client.post("/api/runs", json={"topic": "fresh topic"}).json()["run_id"]
        self.assertEqual(runs.reap_timeouts(), [])
        self.assertEqual(self.client.get(f"/api/runs/{rid}").json()["state"], "running")


if __name__ == "__main__":
    unittest.main()
