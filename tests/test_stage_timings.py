"""Stage start times: written by the worker, measured by the API."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from academic_agent.pipeline_worker import _merge_status_fields
from api import access, runs
from api.main import app

T0 = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]


def _at(seconds: int) -> str:
    return (T0 + timedelta(seconds=seconds)).isoformat()


class WorkerStageTimingTests(unittest.TestCase):
    def _merge(self, existing: dict, stage: str, now: str | None) -> dict:
        return _merge_status_fields(
            existing, stage=stage, done=False, error=None, output_language=None,
            source_counts=None, topic=None, now=now,
        )

    def test_a_new_stage_records_when_it_began(self):
        data = self._merge({}, "Source Collection & Validation", _at(0))
        data = self._merge(data, "Phase 1 — Evidence Collection", _at(40))
        self.assertEqual(data["stage_timings"], [
            {"stage": "Source Collection & Validation", "started_at": _at(0)},
            {"stage": "Phase 1 — Evidence Collection", "started_at": _at(40)},
        ])

    def test_repeating_the_current_stage_does_not_restart_its_clock(self):
        data = self._merge({}, "Phase 1", _at(0))
        data = self._merge(data, "Phase 1", _at(30))
        self.assertEqual(data["stage_timings"], [{"stage": "Phase 1", "started_at": _at(0)}])

    def test_a_write_without_a_clock_keeps_the_record(self):
        data = self._merge({}, "Phase 1", _at(0))
        data = self._merge(data, "Agent 4", None)
        self.assertEqual(data["stage_timings"], [{"stage": "Phase 1", "started_at": _at(0)}])
        self.assertNotIn("stage_timings", self._merge({}, "Phase 1", None))


class ProjectionTests(unittest.TestCase):
    RAW = [
        {"stage": "Source Collection & Validation", "started_at": _at(0)},
        {"stage": "Phase 1", "started_at": _at(40)},
        {"stage": "Agent 4", "started_at": _at(100)},
    ]

    def _durations(self, raw, **kwargs) -> list[tuple[str, int | None, bool]]:
        kwargs.setdefault("running", False)
        kwargs.setdefault("ended_at", None)
        return [(t["stage"], t["duration_seconds"], t["active"]) for t in runs._stage_timings(raw, **kwargs)]

    def test_a_stage_lasts_until_the_next_one_and_the_last_until_the_run_ended(self):
        self.assertEqual(self._durations(self.RAW, ended_at=T0 + timedelta(seconds=130)), [
            ("Source Collection & Validation", 40, False),
            ("Phase 1", 60, False),
            ("Agent 4", 30, False),
        ])

    def test_end_markers_close_the_last_stage_and_are_not_listed(self):
        raw = [*self.RAW, {"stage": "Error", "started_at": _at(110)}]
        self.assertEqual(self._durations(raw)[-1], ("Agent 4", 10, False))
        self.assertEqual(len(self._durations(raw)), 3)

    def test_the_current_stage_of_a_running_run_is_active(self):
        with patch("api.runs.datetime") as clock:
            clock.now.return_value = T0 + timedelta(seconds=125)
            clock.fromisoformat = datetime.fromisoformat
            self.assertEqual(self._durations(self.RAW, running=True)[-1], ("Agent 4", 25, True))

    def test_an_unknown_end_is_none_not_zero(self):
        self.assertEqual(self._durations(self.RAW)[-1], ("Agent 4", None, False))

    def test_malformed_entries_are_skipped(self):
        raw = [
            "Phase 1", {"stage": "", "started_at": _at(0)}, {"stage": "A", "started_at": "yesterday"},
            {"stage": "B", "started_at": "2026-10-21T09:00:00"},  # no time zone
            {"stage": "Agent 4", "started_at": _at(0)},
        ]
        self.assertEqual(self._durations(raw, ended_at=T0 + timedelta(seconds=5)), [("Agent 4", 5, False)])
        self.assertEqual(runs._stage_timings({"not": "a list"}, running=False, ended_at=None), [])


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        for patcher in (
            patch.object(runs, "DEFAULT_OUTPUT_ROOT", root),
            patch.object(access, "ACCESS_CODE", None),
            patch.object(access, "ACCESS_CODES", None),
            patch.object(access, "ADMIN_CODE", None),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.run_id = "20261021T090000Z-ab"
        run_dir = root / self.run_id
        run_dir.mkdir()
        (run_dir / "status.json").write_text(json.dumps({
            "stage": "Error", "done": True, "error": "boom",
            "stage_timings": [*ProjectionTests.RAW, {"stage": "Error", "started_at": _at(110)}],
        }), encoding="utf-8")
        self.client = TestClient(app)

    def test_status_and_progress_both_carry_the_timings(self):
        for path in (f"/api/runs/{self.run_id}", f"/api/runs/{self.run_id}/progress"):
            timings = self.client.get(path).json()["stage_timings"]
            self.assertEqual([t["duration_seconds"] for t in timings], [40, 60, 10], path)


_BROWSER_CHECK = r"""
import assert from "node:assert/strict";
const storage = { getItem: () => null, setItem() {}, removeItem() {} };
Object.assign(globalThis, {
  localStorage: storage, sessionStorage: storage,
  document: { querySelectorAll: () => [], documentElement: {} },
  fetch: () => { throw new Error("no network"); },
});
const root = process.env.APP_ROOT_URL;
const run = await import(root + "web/static/js/run.js");
const i18n = await import(root + "web/static/js/i18n.js");
const timings = [
  { stage: "Source Collection & Validation", duration_seconds: 40, active: false },
  { stage: "Phase 1 — Evidence Collection (Academic · Patent · Market)", duration_seconds: 75, active: false },
  { stage: "Agent 4 — Report Writing", duration_seconds: 12, active: true },
];
const rows = run.stageStates("Agent 4 — Report Writing", "running", timings);
assert.deepEqual(rows.map((row) => [row.state, row.seconds]),
  [["done", 40], ["done", 75], ["active", 12], ["pending", null], ["pending", null]]);
assert.ok(run.stageStates("Done", "unknown", timings).every((row) => row.seconds === null));
assert.ok(run.stageStates("Agent 4 — Report Writing", "running").every((row) => row.seconds === null));
assert.equal(run.timingSummary(timings), "Sources 0:40 · Evidence 1:15 · Report 0:12…");
assert.equal(run.timingSummary(undefined), "");
i18n.setLanguage("Simplified Chinese");
assert.equal(run.timingSummary(timings), "来源 0:40 · 证据分析 1:15 · 报告撰写 0:12…");
console.log("PASS stage timing view");
"""


def test_stage_list_and_header_summary_show_the_durations():
    node = shutil.which("node")
    assert node, "Node must execute the shipped run.js; skipping loses the seam"
    result = subprocess.run(
        [node, "--input-type=module", "-e", _BROWSER_CHECK],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
        env={**os.environ, "APP_ROOT_URL": ROOT.as_uri() + "/"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS stage timing view" in result.stdout
