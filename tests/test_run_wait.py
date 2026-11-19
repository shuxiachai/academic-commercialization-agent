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

    def _finished(self, durations: tuple[int, ...] | None, *, state: str = "completed", total: int | None = None,
                  model: str | None = None, model_in: str = "status", resumed_from: str | None = None):
        """A finished run whose stages took `durations` seconds (None: no stage times).

        `model` is recorded where a worker of today records it (`status`) or
        only in the usage record, as a run from before that field has it.
        """
        self.serial += 1
        run_dir = self.root / f"20261021T{self.serial:06d}Z-ab"
        run_dir.mkdir()
        start = datetime(2026, 10, 21, 9, tzinfo=UTC)
        elapsed = total if total is not None else sum(durations or ())
        status: dict = {"stage": "Done", "done": True}
        if model and model_in == "status":
            status["llm_model"] = model
        if durations is not None:
            offsets, at = [], start
            for stage, seconds in zip(STAGES, durations, strict=True):
                offsets.append({"stage": stage, "started_at": at.isoformat()})
                at += timedelta(seconds=seconds)
            status["stage_timings"] = [*offsets, {"stage": "Done", "started_at": at.isoformat()}]
        (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
        end = start + timedelta(seconds=elapsed)
        usage = None
        if model and model_in == "usage":
            usage = {"total_tokens": 10, "agents": [{"role": "Writer", "model": model, "total_tokens": 10}]}
        recovery = None
        if resumed_from is not None:
            recovery = {"state": "reused", "source_run_id": resumed_from, "reused_nodes": ["retrieval"],
                        "next_node": "academic"}
        commit_terminal_record(run_dir, TerminalRecord(
            state=state, reason_code="worker_completed" if state == "completed" else "worker_exception",
            termination_method="worker_exit", started_at=start, ended_at=end, elapsed_seconds=elapsed,
            last_stage="Done", timeout_seconds=1800, usage=usage,
            usage_accounting=UsageAccounting(state="unavailable" if usage is None else "complete", snapshot_at=end,
                                             run_complete=True, in_flight_request_may_have_spent=False),
            recovery=recovery,
        ))
        return run_dir


class EtaTests(_Root):
    """The range a running run is shown, from what recent runs took (api/eta.py).

    On 2026-11-18 the page said "about 7 min" at the start of a run that took
    24 min 40 s: one median over the last thirty completed runs, whatever
    model they ran on, two days after the deployment moved to a slower one.
    """

    THREE = ((60, 300, 120, 90, 30), (80, 320, 140, 100, 40), (70, 310, 130, 95, 35))

    def _estimate(self, stage: str, in_stage: int, elapsed: int, model: str | None = None):
        timings = [{"stage": stage, "started_at": "", "duration_seconds": in_stage, "active": True}]
        return eta.estimate(stage, elapsed, timings, model=model)

    def test_the_range_is_what_each_run_took_from_this_point_on(self):
        for durations in self.THREE:
            self._finished(durations)
        estimate = self._estimate(STAGES[2], in_stage=30, elapsed=450)
        # Run by run: the rest of the report stage, then its review and scoring:
        # 90 + 90 + 30, 110 + 100 + 40, 100 + 95 + 35.
        self.assertEqual(estimate, {
            "remaining_seconds": 230, "low_seconds": 210, "high_seconds": 250, "basis_runs": 3,
            "basis": "stages", "model": None, "same_model": False, "overdue": False,
        })

    def test_the_range_moves_as_stages_complete(self):
        for durations in self.THREE:
            self._finished(durations)
        at_start = self._estimate(STAGES[0], in_stage=0, elapsed=0)
        self.assertEqual((at_start["low_seconds"], at_start["high_seconds"]), (600, 680))
        scoring = self._estimate(STAGES[4], in_stage=0, elapsed=600)
        self.assertEqual((scoring["low_seconds"], scoring["high_seconds"]), (30, 40))

    def test_a_run_that_had_left_the_stage_by_now_is_not_asked(self):
        """Fifty seconds into scoring, the runs that scored in 30, 35 and 40 say nothing about the rest."""
        for durations in (*self.THREE, (70, 310, 130, 95, 200)):
            self._finished(durations)
        estimate = self._estimate(STAGES[4], in_stage=50, elapsed=650)
        self.assertEqual((estimate["low_seconds"], estimate["high_seconds"], estimate["overdue"]), (150, 150, False))

    def test_slower_than_every_run_at_this_stage_is_said_with_what_the_later_stages_took(self):
        for durations in self.THREE:
            self._finished(durations)
        estimate = self._estimate(STAGES[1], in_stage=900, elapsed=980)
        self.assertTrue(estimate["overdue"])
        # Report, review and scoring alone: 240, 280, 260.
        self.assertEqual((estimate["low_seconds"], estimate["high_seconds"]), (240, 280))
        last = self._estimate(STAGES[4], in_stage=900, elapsed=1500)
        self.assertEqual((last["low_seconds"], last["high_seconds"], last["overdue"]), (0, 0, True))

    def test_runs_of_the_same_model_make_the_range(self):
        for durations in self.THREE:
            self._finished(durations, model="fast-model")
        for durations in ((60, 900, 400, 100, 60), (60, 700, 300, 100, 60), (60, 800, 350, 100, 60)):
            self._finished(durations, model="slow-model")
        slow = self._estimate(STAGES[0], in_stage=0, elapsed=0, model="slow-model")
        self.assertEqual((slow["low_seconds"], slow["high_seconds"]), (1220, 1520))
        self.assertEqual((slow["model"], slow["same_model"], slow["basis_runs"]), ("slow-model", True, 3))
        fast = self._estimate(STAGES[0], in_stage=0, elapsed=0, model="fast-model")
        self.assertEqual((fast["low_seconds"], fast["high_seconds"]), (600, 680))

    def test_too_few_runs_of_the_model_and_other_models_stand_in_and_say_so(self):
        for durations in self.THREE:
            self._finished(durations, model="fast-model")
        self._finished((60, 900, 400, 100, 60), model="new-model")
        self._finished((60, 800, 350, 100, 60), model="new-model")
        estimate = self._estimate(STAGES[0], in_stage=0, elapsed=0, model="new-model")
        self.assertEqual((estimate["model"], estimate["same_model"], estimate["basis_runs"]), (None, False, 5))
        self.assertEqual((estimate["low_seconds"], estimate["high_seconds"]), (600, 1520))
        # A run that names no model is answered the same way.
        self.assertFalse(self._estimate(STAGES[0], in_stage=0, elapsed=0)["same_model"])

    def test_a_model_named_only_by_the_usage_record_is_still_its_model(self):
        for durations in self.THREE:
            self._finished(durations, model="older-run-model", model_in="usage")
        estimate = self._estimate(STAGES[0], in_stage=0, elapsed=0, model="older-run-model")
        self.assertEqual((estimate["model"], estimate["same_model"]), ("older-run-model", True))

    def test_only_the_newest_runs_of_a_model_are_asked(self):
        self._finished((60, 3000, 120, 90, 30), model="m")
        for _ in range(eta.MODEL_RUNS):
            self._finished((60, 300, 120, 90, 30), model="m")
        estimate = self._estimate(STAGES[0], in_stage=0, elapsed=0, model="m")
        self.assertEqual((estimate["low_seconds"], estimate["high_seconds"], estimate["basis_runs"]),
                         (600, 600, eta.MODEL_RUNS))

    def test_a_resumed_run_is_not_history(self):
        """It ran only what its parent had not finished: 3 min 48 s was never a whole run."""
        for durations in self.THREE:
            self._finished(durations)
        self._finished((5, 200, 0, 0, 0), resumed_from="20261021T000001Z-ab")
        estimate = self._estimate(STAGES[0], in_stage=0, elapsed=0)
        self.assertEqual((estimate["low_seconds"], estimate["basis_runs"]), (600, 3))

    def test_without_stage_times_whole_run_times_are_used(self):
        for total in (600, 900, 700):
            self._finished(None, total=total)
        self.assertEqual(self._estimate(STAGES[1], in_stage=10, elapsed=100), {
            "remaining_seconds": 600, "low_seconds": 500, "high_seconds": 800, "basis_runs": 3,
            "basis": "total", "model": None, "same_model": False, "overdue": False,
        })

    def test_a_run_slower_than_every_whole_run_is_overdue_and_never_negative(self):
        for total in (600, 600, 600):
            self._finished(None, total=total)
        estimate = self._estimate(STAGES[4], in_stage=10, elapsed=700)
        self.assertEqual((estimate["remaining_seconds"], estimate["low_seconds"], estimate["high_seconds"],
                          estimate["overdue"]), (0, 0, 0, True))

    def test_failed_runs_are_not_history(self):
        self._finished(None, total=600)
        self._finished(None, total=600)
        self._finished(None, total=60, state="failed")
        self.assertIsNone(self._estimate(STAGES[0], in_stage=5, elapsed=5))

    def test_a_finished_run_reports_no_eta(self):
        for total in (600, 600, 600):
            run_dir = self._finished(None, total=total)
        self.assertIsNone(runs.get_state(run_dir.name)["eta"])

    def test_the_estimate_reaches_both_run_reads_with_the_runs_own_model(self):
        """The seam: the model the worker recorded is the one the range is drawn for, and every
        field of the answer is on both endpoints (a response model drops what it does not declare)."""
        for durations in ((60, 900, 400, 100, 60), (60, 700, 300, 100, 60), (60, 800, 350, 100, 60)):
            self._finished(durations, model="slow-model")
        for durations in self.THREE:
            self._finished(durations, model="fast-model")
        run_id = "20261022T090000Z-" + "c" * 32
        run_dir = self.root / run_id
        run_dir.mkdir()
        now = datetime.now(UTC)
        (run_dir / "status.json").write_text(json.dumps({
            "stage": STAGES[2], "done": False, "llm_model": "slow-model", "topic": "t",
            "stage_timings": [
                {"stage": STAGES[0], "started_at": (now - timedelta(seconds=900)).isoformat()},
                {"stage": STAGES[1], "started_at": (now - timedelta(seconds=840)).isoformat()},
                {"stage": STAGES[2], "started_at": (now - timedelta(seconds=40)).isoformat()},
            ],
        }), encoding="utf-8")

        class _Alive:
            def poll(self):
                return None

        handle = runs._Handle(run_id=run_id, topic="t", proc=_Alive(), log_file=None)
        with patch.object(runs, "_registry", {run_id: handle}), patch.object(access, "ACCESS_CODE", None), \
                patch.object(access, "ACCESS_CODES", None), patch.object(access, "ADMIN_CODE", None):
            client = TestClient(app)
            for path in (f"/api/runs/{run_id}", f"/api/runs/{run_id}/progress"):
                body = client.get(path).json()
                self.assertEqual(body["llm_model"], "slow-model", path)
                estimate = body["eta"]
                self.assertEqual(set(estimate), {"remaining_seconds", "low_seconds", "high_seconds", "basis_runs",
                                                 "basis", "model", "same_model", "overdue"}, path)
                self.assertEqual((estimate["model"], estimate["same_model"], estimate["basis_runs"]),
                                 ("slow-model", True, 3), path)
                # 40 s into a report stage that took 300 to 400, then 160 of review and scoring.
                self.assertTrue(415 <= estimate["low_seconds"] <= 420, estimate)
                self.assertTrue(515 <= estimate["high_seconds"] <= 520, estimate)


class ResumeEstimateTests(_Root):
    """A resume is told nothing until its worker knows which stage it starts in.

    The production resume of 2026-11-18 had only scoring left and was shown
    "about 9 min": an estimate for a whole run, made while its stage still
    read as the first one.
    """

    def _running(self, stage: str, *, resume: bool):
        for durations in EtaTests.THREE:
            self._finished(durations)
        run_id = "20261022T090000Z-" + "d" * 32
        run_dir = self.root / run_id
        run_dir.mkdir()
        if resume:
            (run_dir / runs.RESUME_SNAPSHOT_DIRECTORY / "checkpoints").mkdir(parents=True)
        now = datetime.now(UTC)
        (run_dir / "status.json").write_text(json.dumps({
            "stage": stage, "done": False, "topic": "t",
            "stage_timings": [{"stage": stage, "started_at": (now - timedelta(seconds=2)).isoformat()}],
        }), encoding="utf-8")

        class _Alive:
            def poll(self):
                return None

        handle = runs._Handle(run_id=run_id, topic="t", proc=_Alive(), log_file=None)
        with patch.object(runs, "_registry", {run_id: handle}):
            return runs.get_state(run_id)["eta"]

    def test_a_resume_still_in_its_first_stage_has_no_estimate(self):
        self.assertIsNone(self._running(STAGES[0], resume=True))

    def test_a_resume_in_its_real_stage_is_told_what_is_left_of_that(self):
        estimate = self._running(STAGES[4], resume=True)
        # Scoring alone: 30 to 40 seconds, two of them gone.
        self.assertTrue(26 <= estimate["low_seconds"] <= 28 and 36 <= estimate["high_seconds"] <= 38, estimate)

    def test_a_fresh_run_in_its_first_stage_is_told_the_whole_run(self):
        estimate = self._running(STAGES[0], resume=False)
        self.assertTrue(595 <= estimate["low_seconds"] <= 600 and 675 <= estimate["high_seconds"] <= 680, estimate)


class TypicalMinutesTests(_Root):
    """The figure the public pages state, from this deployment's own newest runs."""

    def test_the_newest_runs_whole_times_in_minutes_rounded_outward(self):
        for total in (301, 899, 1481):
            self._finished(None, total=total)
        self.assertEqual(eta.typical_minutes(), {"low": 5, "high": 25, "runs": 3})

    def test_no_figure_from_fewer_than_three_runs(self):
        self._finished(None, total=600)
        self._finished(None, total=700)
        self.assertIsNone(eta.typical_minutes())

    def test_the_health_reading_carries_it_and_says_nothing_without_history(self):
        """The pages read /health already; the figure rides on it, as two durations and a count."""
        client = TestClient(app)
        self.assertIsNone(client.get("/health").json()["run_minutes"])
        eta._cache.clear()
        for total in (301, 899, 1481):
            self._finished(None, total=total)
        self.assertEqual(client.get("/health").json()["run_minutes"], {"low": 5, "high": 25, "runs": 3})

    def test_the_health_reading_carries_the_operators_contact_only_when_one_is_set(self):
        client = TestClient(app)
        with patch.dict("os.environ", {"OPERATOR_CONTACT": ""}):
            self.assertIsNone(client.get("/health").json()["contact"])
        with patch.dict("os.environ", {"OPERATOR_CONTACT": "  ops@example.test  "}):
            self.assertEqual(client.get("/health").json()["contact"], "ops@example.test")


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
