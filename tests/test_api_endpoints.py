"""Tests for the endpoints the browser client added.

/progress is polled roughly once a second for the length of a run, and
/report.pdf renders on first request. Both were added with no coverage; the
PDF one was verified by hand exactly once.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import runs
from api.main import app


class _EndpointTestBase(unittest.TestCase):

    def setUp(self):
        runs._registry.clear()
        self.addCleanup(runs._registry.clear)
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        patcher = patch.object(runs, "DEFAULT_OUTPUT_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app)

    def _run_dir(self, run_id="20260809T120000Z-abcdef0123", **status):
        directory = self.root / run_id
        directory.mkdir(parents=True, exist_ok=True)
        payload = {"stage": "Done", "done": True, "error": None,
                   "topic": "solid-state batteries", "output_language": "English"}
        payload.update(status)
        (directory / "status.json").write_text(
            json.dumps(payload), encoding="utf-8")
        return run_id, directory


class ProgressTests(_EndpointTestBase):

    def test_unknown_run_is_404(self):
        r = self.client.get("/api/runs/20260101T000000Z-deadbeef/progress")
        self.assertEqual(r.status_code, 404)

    def test_traversing_run_id_is_404_not_a_read(self):
        r = self.client.get("/api/runs/..%2F..%2Fetc/progress")
        self.assertIn(r.status_code, (404, 400))

    def test_progress_reports_the_topic(self):
        """The client shows a placeholder title until this field arrives.

        It was missing from the model, so a run opened from the sidebar
        displayed "…" for its whole duration.
        """
        run_id, _ = self._run_dir()
        body = self.client.get(f"/api/runs/{run_id}/progress").json()
        self.assertEqual(body["topic"], "solid-state batteries")

    def test_steps_are_returned_incrementally(self):
        """`since` exists so a poll does not re-send the whole log each tick."""
        run_id, directory = self._run_dir()
        lines = [json.dumps({"type": "finish", "agent_idx": i}) for i in range(5)]
        (directory / "steps.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

        first = self.client.get(f"/api/runs/{run_id}/progress?since=0").json()
        self.assertEqual(len(first["steps"]), 5)

        later = self.client.get(f"/api/runs/{run_id}/progress?since=5").json()
        self.assertEqual(later["steps"], [])

    def test_a_half_written_step_line_is_skipped(self):
        """The worker appends while this is being read."""
        run_id, directory = self._run_dir()
        (directory / "steps.jsonl").write_text(
            json.dumps({"type": "finish", "agent_idx": 0}) + "\n"
            + '{"type": "fin',            # mid-write
            encoding="utf-8",
        )
        body = self.client.get(f"/api/runs/{run_id}/progress").json()
        self.assertEqual(len(body["steps"]), 1)

    def test_missing_steps_file_is_not_an_error(self):
        run_id, _ = self._run_dir()
        body = self.client.get(f"/api/runs/{run_id}/progress").json()
        self.assertEqual(body["steps"], [])

    def test_progress_is_not_shadowed_by_the_artifact_route(self):
        """/api/runs/{id}/{artifact} would match "progress" as an artifact.

        Route order is the only thing keeping these apart, and route order is
        easy to disturb when adding an endpoint.
        """
        run_id, _ = self._run_dir()
        body = self.client.get(f"/api/runs/{run_id}/progress").json()
        self.assertIn("steps", body)          # the artifact route returns a file


class ReportPdfTests(_EndpointTestBase):

    def test_unknown_run_is_404(self):
        r = self.client.get("/api/runs/20260101T000000Z-deadbeef/report.pdf")
        self.assertEqual(r.status_code, 404)

    def test_run_without_a_report_is_409(self):
        """409 rather than 404: the run exists, the artifact does not."""
        run_id, _ = self._run_dir()
        r = self.client.get(f"/api/runs/{run_id}/report.pdf")
        self.assertEqual(r.status_code, 409)

    def test_existing_pdf_is_served_without_re_rendering(self):
        run_id, directory = self._run_dir()
        (directory / "commercialization_report.md").write_text("# R", encoding="utf-8")
        (directory / "commercialization_report.pdf").write_bytes(b"%PDF-1.4 cached")

        with patch("ui.pdf_export._generate_pdf") as render:
            r = self.client.get(f"/api/runs/{run_id}/report.pdf")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "application/pdf")
        render.assert_not_called()

    def test_pdf_is_rendered_on_first_request(self):
        run_id, directory = self._run_dir()
        (directory / "commercialization_report.md").write_text("# R", encoding="utf-8")

        def _fake_render(markdown, run_dir, output_language="English"):
            (Path(run_dir) / "commercialization_report.pdf").write_bytes(b"%PDF-1.4 new")

        with patch("ui.pdf_export._generate_pdf", side_effect=_fake_render) as render:
            r = self.client.get(f"/api/runs/{run_id}/report.pdf")

        self.assertEqual(r.status_code, 200)
        render.assert_called_once()

    def test_render_failure_is_reported_not_swallowed(self):
        run_id, directory = self._run_dir()
        (directory / "commercialization_report.md").write_text("# R", encoding="utf-8")

        private = RuntimeError(r"no font at C:\private\fonts token=top-secret")
        with patch(
            "ui.pdf_export._generate_pdf", side_effect=private
        ):
            r = self.client.get(f"/api/runs/{run_id}/report.pdf")

        self.assertEqual(r.status_code, 500)
        self.assertEqual(
            r.json()["detail"],
            "The report PDF could not be rendered. The Markdown report is still available.",
        )
        self.assertNotIn("top-secret", r.text)
        self.assertNotIn("private", r.text)

    def test_silent_render_failure_is_still_an_error(self):
        """A renderer that returns without writing must not yield a 200."""
        run_id, directory = self._run_dir()
        (directory / "commercialization_report.md").write_text("# R", encoding="utf-8")

        with patch("ui.pdf_export._generate_pdf", return_value=None):
            r = self.client.get(f"/api/runs/{run_id}/report.pdf")

        self.assertEqual(r.status_code, 500)


class SpaRoutingTests(_EndpointTestBase):
    """Deep links must return the document; the client reads the path."""

    def test_root_serves_the_page(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers["content-type"])

    def test_run_deep_link_serves_the_same_page(self):
        r = self.client.get("/run/20260101T000000Z-abcdef")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers["content-type"])

    def test_api_routes_are_not_shadowed_by_the_spa(self):
        r = self.client.get("/health")
        self.assertEqual(r.headers["content-type"], "application/json")


if __name__ == "__main__":
    unittest.main()
