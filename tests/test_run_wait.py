"""What a code holder sees while waiting: runs left today and time left."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from academic_agent.run_terminal import TerminalRecord, UsageAccounting, commit_terminal_record
from api import access, eta, runs
from api.main import app

STAGES = (
    "Source Collection & Validation",
    "Phase 1 — Evidence Collection (Academic · Patent · Market)",
    "Agent 4 — Report Writing",
    "Agent 5 — Quality Review & Citation Check",
    "Agent 6 — Commercialization Scoring",
)


class _Root(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        for patcher in (
            patch.object(runs, "DEFAULT_OUTPUT_ROOT", self.root),
            patch.object(runs, "_daily_counts", {}),
            patch.object(runs, "_daily_date", None),
            patch.object(eta, "_cache", {}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.serial = 0

    def _finished(self, durations: tuple[int, ...] | None, *, state: str = "completed", total: int | None = None):
        """A finished run whose stages took `durations` seconds (None: no stage times)."""
        self.serial += 1
        run_dir = self.root / f"20261021T{self.serial:06d}Z-ab"
        run_dir.mkdir()
        start = datetime(2026, 10, 21, 9, tzinfo=UTC)
        elapsed = total if total is not None else sum(durations or ())
        status: dict = {"stage": "Done", "done": True}
        if durations is not None:
            offsets, at = [], start
            for stage, seconds in zip(STAGES, durations, strict=True):
                offsets.append({"stage": stage, "started_at": at.isoformat()})
                at += timedelta(seconds=seconds)
            status["stage_timings"] = [*offsets, {"stage": "Done", "started_at": at.isoformat()}]
        (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
        end = start + timedelta(seconds=elapsed)
        commit_terminal_record(run_dir, TerminalRecord(
            state=state, reason_code="worker_completed" if state == "completed" else "worker_exception",
            termination_method="worker_exit", started_at=start, ended_at=end, elapsed_seconds=elapsed,
            last_stage="Done", timeout_seconds=1800, usage=None,
            usage_accounting=UsageAccounting(state="unavailable", snapshot_at=end, run_complete=True,
                                             in_flight_request_may_have_spent=False),
        ))
        return run_dir


class EtaTests(_Root):
    def _estimate(self, stage: str, in_stage: int, elapsed: int):
        timings = [{"stage": stage, "started_at": "", "duration_seconds": in_stage, "active": True}]
        return eta.estimate(stage, elapsed, timings)

    def test_per_stage_medians_count_down_from_the_current_stage(self):
        for durations in ((60, 300, 120, 90, 30), (80, 320, 140, 100, 40), (70, 310, 130, 95, 35)):
            self._finished(durations)
        estimate = self._estimate(STAGES[2], in_stage=30, elapsed=450)
        # report median 130 - 30 in it, then review 95 and scoring 35.
        self.assertEqual(estimate, {"remaining_seconds": 230, "basis_runs": 3, "basis": "stages"})

    def test_without_stage_times_the_median_total_is_used(self):
        for total in (600, 900, 700):
            self._finished(None, total=total)
        self.assertEqual(self._estimate(STAGES[1], in_stage=10, elapsed=100),
                         {"remaining_seconds": 600, "basis_runs": 3, "basis": "total"})

    def test_a_slow_run_goes_negative_instead_of_stopping_at_zero(self):
        for total in (600, 600, 600):
            self._finished(None, total=total)
        self.assertEqual(self._estimate(STAGES[4], in_stage=10, elapsed=700)["remaining_seconds"], -100)

    def test_failed_runs_are_not_history(self):
        self._finished(None, total=600)
        self._finished(None, total=600)
        self._finished(None, total=60, state="failed")
        self.assertIsNone(self._estimate(STAGES[0], in_stage=5, elapsed=5))

    def test_a_finished_run_reports_no_eta(self):
        for total in (600, 600, 600):
            run_dir = self._finished(None, total=total)
        self.assertIsNone(runs.get_state(run_dir.name)["eta"])


class QuotaTests(_Root):
    def setUp(self):
        super().setUp()
        for patcher in (
            patch.object(runs, "DAILY_CAP", 3),
            patch.object(access, "ACCESS_CODE", None),
            patch.object(access, "ACCESS_CODES", "for-alice,for-bob"),
            patch.object(access, "ADMIN_CODE", "for-admin"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(app)

    def _charge(self, code: str) -> None:
        with runs.reserve_inline_paid_operation(owner=access.owner_id(code), byok=False):
            pass

    def _quota(self, code: str):
        r = self.client.get("/api/quota", headers={"X-Access-Code": code})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_counts_this_codes_operations_today(self):
        self._charge("for-alice")
        quota = self._quota("for-alice")
        self.assertEqual((quota["limit"], quota["used"], quota["remaining"]), (3, 1, 2))
        tomorrow = datetime.now(UTC).date() + timedelta(days=1)
        self.assertEqual(datetime.fromisoformat(quota["resets_at"]),
                         datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=UTC))
        self.assertEqual(self._quota("for-bob")["used"], 0)

    def test_the_admin_code_sees_its_own_count(self):
        self._charge("for-admin")
        self.assertEqual(self._quota("for-admin")["used"], 1)

    def test_remaining_never_goes_below_zero(self):
        for _ in range(3):
            self._charge("for-alice")
        self.assertEqual(self._quota("for-alice")["remaining"], 0)

    def test_an_uncapped_deployment_says_null_and_advertises_nothing(self):
        with patch.object(runs, "DAILY_CAP", 0):
            self.assertIsNone(self._quota("for-alice"))
            r = self.client.get("/api/access/check", headers={"X-Access-Code": "for-alice"})
            self.assertFalse(r.json()["daily_quota"])
        r = self.client.get("/api/access/check", headers={"X-Access-Code": "for-alice"})
        self.assertTrue(r.json()["daily_quota"])

    def test_needs_an_access_code(self):
        self.assertEqual(self.client.get("/api/quota").status_code, 401)

    def test_an_unreadable_ledger_is_503_not_a_guess(self):
        (self.root / ".paid-operation-ledger.json").write_text("{broken", encoding="utf-8")
        r = self.client.get("/api/quota", headers={"X-Access-Code": "for-alice"})
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main()
