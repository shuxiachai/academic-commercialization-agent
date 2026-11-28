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
                  model: str | None = None, model_in: str = "status", resumed_from: str | None = None,
                  stages: tuple[tuple[str, int], ...] | None = None, reused: tuple[str, ...] = ("retrieval",),
                  next_node: str = "academic"):
        """A finished run whose stages took `durations` seconds (None: no stage times).

        A run that did not complete stops in the last stage `durations`
        reaches, and its record ends there with "Error", as a worker's does.
        `stages` gives the record's (stage, seconds) entries outright, for a
        resume whose record files its time under another stage's name.
        `model` is recorded where a worker of today records it (`status`) or
        only in the usage record, as a run from before that field has it.
        """
        self.serial += 1
        run_dir = self.root / f"20261021T{self.serial:06d}Z-ab"
        run_dir.mkdir()
        start = datetime(2026, 10, 21, 9, tzinfo=UTC)
        entries = stages
        if entries is None and durations is not None:
            entries = tuple(zip(STAGES[:len(durations)], durations, strict=True))
        elapsed = total if total is not None else sum(seconds for _stage, seconds in entries or ())
        status: dict = {"stage": "Done" if state == "completed" else "Error", "done": True}
        if model and model_in == "status":
            status["llm_model"] = model
        if entries is not None:
            offsets, at = [], start
            for stage, seconds in entries:
                offsets.append({"stage": stage, "started_at": at.isoformat()})
                at += timedelta(seconds=seconds)
            ending = "Done" if state == "completed" else "Error"
            status["stage_timings"] = [*offsets, {"stage": ending, "started_at": at.isoformat()}]
        (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
        end = start + timedelta(seconds=elapsed)
        usage = None
        if model and model_in == "usage":
            usage = {"total_tokens": 10, "agents": [{"role": "Writer", "model": model, "total_tokens": 10}]}
        recovery = None
        if resumed_from is not None:
            recovery = {"state": "reused", "source_run_id": resumed_from, "reused_nodes": list(reused),
                        "next_node": next_node}
        commit_terminal_record(run_dir, TerminalRecord(
            state=state, reason_code="worker_completed" if state == "completed" else "worker_exception",
            termination_method="worker_exit", started_at=start, ended_at=end, elapsed_seconds=elapsed,
            last_stage=status["stage"], timeout_seconds=1800, usage=usage,
            usage_accounting=UsageAccounting(state="unavailable" if usage is None else "complete", snapshot_at=end,
                                             run_complete=True, in_flight_request_may_have_spent=False),
            recovery=recovery,
        ))
        return run_dir


class EtaTests(_Root):
    """The range a running run is shown, from what earlier runs took (api/eta.py).

    On 2026-11-18 the page said "about 7 min" at the start of a run that took
    24 min 40 s: one median over the last thirty completed runs. On 2026-11-27
    a run was told 1-16 minutes, then 11-16 twenty seconds later, then 7-8 and
    5-6 with fourteen minutes still to go (tests/test_eta_replay.py). Each
    stage is now the fastest to the slowest of its recent times, from any run
    that finished the stage, and the range adds them up. Since 2026-11-28 the
    times are every model's: the deployment's model is changed often, and the
    user asked that the estimate not depend on it.
    """

    THREE = ((60, 300, 120, 90, 30), (80, 320, 140, 100, 40), (70, 310, 130, 95, 35))
    FIELDS = {"remaining_seconds", "low_seconds", "high_seconds", "basis_runs", "basis", "overdue",
              "few_sample_stages"}

    def _estimate(self, stage: str, in_stage: int):
        timings = [{"stage": stage, "started_at": "", "duration_seconds": in_stage, "active": True}]
        return eta.estimate(stage, timings)

    def _running(self, model: str | None, *, serial: int = 0, in_stage: int = 40) -> str:
        """A run in its report stage, `in_stage` seconds in, recorded as running on `model`."""
        run_id = f"20261022T09000{serial}Z-" + "c" * 32
        run_dir = self.root / run_id
        run_dir.mkdir()
        now = datetime.now(UTC)
        status = {
            "stage": STAGES[2], "done": False, "topic": "t",
            "stage_timings": [
                {"stage": STAGES[0], "started_at": (now - timedelta(seconds=900)).isoformat()},
                {"stage": STAGES[1], "started_at": (now - timedelta(seconds=840)).isoformat()},
                {"stage": STAGES[2], "started_at": (now - timedelta(seconds=in_stage)).isoformat()},
            ],
        }
        if model is not None:
            status["llm_model"] = model
        (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
        return run_id

    def test_each_stage_is_its_fastest_to_its_slowest_and_the_range_adds_them_up(self):
        for durations in self.THREE:
            self._finished(durations, model="m")
        estimate = self._estimate(STAGES[2], in_stage=30)
        # The rest of the report, 120 - 30 to 140 - 30; review 90 to 100; scoring 30 to 40.
        self.assertEqual(estimate, {
            "remaining_seconds": 230, "low_seconds": 210, "high_seconds": 250, "basis_runs": 3,
            "basis": "stages", "overdue": False, "few_sample_stages": [],
        })
        at_start = self._estimate(STAGES[0], in_stage=0)
        self.assertEqual((at_start["low_seconds"], at_start["high_seconds"]), (600, 680))

    def test_within_a_stage_neither_end_rises_as_the_stage_goes_on(self):
        """The rule it replaces asked only the runs that had stayed in the stage this long:
        fifty seconds into scoring that was one run, and the range read 150 to 150."""
        for durations in (*self.THREE, (70, 310, 130, 95, 200)):
            self._finished(durations, model="m")
        seen = [self._estimate(STAGES[4], in_stage=second) for second in range(0, 260, 10)]
        for before, after in zip(seen, seen[1:], strict=False):
            for end in ("low_seconds", "high_seconds"):
                self.assertLessEqual(after[end], before[end])
                self.assertLessEqual(before[end] - after[end], 10)
        fifty = seen[5]
        self.assertEqual((fifty["low_seconds"], fifty["high_seconds"], fifty["overdue"]), (0, 150, False))

    def test_a_run_that_failed_or_timed_out_lends_the_stages_it_finished(self):
        """Not the stage it stopped in: that one was cut short, not finished."""
        self._finished((60, 300, 120, 90, 30), model="m")
        self._finished((70, 310, 600, 400, 5), state="failed", model="m")
        self._finished((65, 305, 610), state="timeout", model="m")
        in_review = self._estimate(STAGES[3], in_stage=0)
        # Review 90 and 400, widened a quarter for two times: 72 to 500. Scoring 30 alone,
        # widened by half: 20 to 45. The failed run's 5 s of scoring was never finished.
        self.assertEqual((in_review["low_seconds"], in_review["high_seconds"]), (92, 545))
        self.assertEqual((in_review["basis_runs"], in_review["few_sample_stages"]), (2, ["review", "scoring"]))
        writing = self._estimate(STAGES[2], in_stage=0)
        # Report 120 and 600 (the timed-out run's 610 was cut short): 96 to 750.
        self.assertEqual((writing["low_seconds"], writing["high_seconds"]), (96 + 92, 750 + 545))
        sources = self._estimate(STAGES[0], in_stage=0)
        self.assertNotIn("sources", sources["few_sample_stages"])

    def test_a_resume_lends_the_stage_it_ran_not_the_ones_it_took_from_its_parent(self):
        """The production resume of 2026-11-18 scored in 3 min 33 s, and its worker of then filed
        those seconds under the evidence stage; run.js stageSeconds shows them under scoring."""
        for durations in self.THREE:
            self._finished(durations, model="m")
        self._finished(None, model="m", resumed_from="20261021T000001Z-ab",
                       reused=("retrieval", "academic", "patent", "market", "writer", "reviewer"),
                       next_node="scorer", stages=((STAGES[0], 0), (STAGES[1], 213), (STAGES[4], 0)))
        scoring = self._estimate(STAGES[4], in_stage=0)
        self.assertEqual((scoring["low_seconds"], scoring["high_seconds"], scoring["basis_runs"]), (30, 213, 4))
        whole = self._estimate(STAGES[0], in_stage=0)
        # Sources and evidence are the three whole runs' alone: 60 to 80 and 300 to 320.
        self.assertEqual((whole["low_seconds"], whole["high_seconds"]), (600, 680 + 213 - 40))

    def test_a_stage_seen_once_or_twice_is_widened(self):
        """Measured on 106 benchmark runs in 13 batches of one model each: the next run's time lay
        between the fastest and slowest of one earlier run 0% of the time, of two 33%; a half
        either way for one and a quarter for two brought that to 69% and 73%."""
        self._finished((60, 300, 120, 90, 30), model="m")
        once = self._estimate(STAGES[4], in_stage=0)
        self.assertEqual((once["low_seconds"], once["high_seconds"], once["few_sample_stages"]), (20, 45, ["scoring"]))
        self._finished((80, 320, 140, 100, 40), model="m")
        eta._cache.clear()  # what is on record is read again at most every CACHE_SECONDS
        twice = self._estimate(STAGES[4], in_stage=0)
        self.assertEqual((twice["low_seconds"], twice["high_seconds"]), (24, 50))
        self._finished((70, 310, 130, 95, 35), model="m")
        eta._cache.clear()
        thrice = self._estimate(STAGES[4], in_stage=0)
        self.assertEqual((thrice["low_seconds"], thrice["high_seconds"], thrice["few_sample_stages"]), (30, 40, []))

    def test_the_times_of_every_model_make_one_range(self):
        """A slow model's runs and a fast one's are asked alike, newest first."""
        for durations in self.THREE:
            self._finished(durations, model="fast-model")
        for durations in ((60, 900, 400, 100), (70, 800, 350, 90), (65, 850, 380, 95)):
            self._finished(durations, state="failed", model="slow-model")
        estimate = self._estimate(STAGES[2], in_stage=0)
        # Reports 120 to 400 across both; review 90 to 100 (the slow runs' reviews were cut short);
        # scoring 30 to 40.
        self.assertEqual((estimate["low_seconds"], estimate["high_seconds"], estimate["basis_runs"]), (240, 540, 6))
        self.assertEqual(set(estimate), self.FIELDS)

    def test_only_the_newest_times_of_a_stage_are_asked(self):
        self._finished((60, 3000, 120, 90, 30), model="m")
        for _ in range(eta.STAGE_SAMPLES):
            self._finished((60, 300, 120, 90, 30), model="other")
        estimate = self._estimate(STAGES[0], in_stage=0)
        self.assertEqual((estimate["low_seconds"], estimate["high_seconds"], estimate["basis_runs"]),
                         (600, 600, eta.STAGE_SAMPLES))

    def test_slower_than_every_time_at_this_stage_is_said_with_what_the_later_stages_took(self):
        for durations in self.THREE:
            self._finished(durations, model="m")
        estimate = self._estimate(STAGES[1], in_stage=900)
        self.assertTrue(estimate["overdue"])
        # Report, review and scoring alone: 120 + 90 + 30 to 140 + 100 + 40.
        self.assertEqual((estimate["low_seconds"], estimate["high_seconds"]), (240, 280))
        last = self._estimate(STAGES[4], in_stage=900)
        self.assertEqual((last["low_seconds"], last["high_seconds"], last["overdue"]), (0, 0, True))

    def test_a_stage_with_no_time_on_record_gives_no_estimate(self):
        """Runs that all stopped in their first stage, or have no stage times, finished nothing to go by."""
        self._finished((60,), state="failed", model="m")
        for total in (600, 900, 700):
            self._finished(None, total=total, model="m")
        self.assertIsNone(self._estimate(STAGES[0], in_stage=5))

    def test_a_run_whose_worker_has_written_its_end_is_told_nothing(self):
        """Production, 2026-11-28: for the seconds between the worker writing "Done" and the run
        reading as completed, the page said "about 3-33 min left", the whole run's range, with the
        limit warning. An end line is no stage, and nothing is ahead of it."""
        for durations in self.THREE:
            self._finished(durations, model="m")
        for end in ("Done", "Error"):
            self.assertIsNone(self._estimate(end, in_stage=0), end)
        # Before the worker names any stage the whole run is still ahead, as before.
        self.assertEqual(self._estimate("", in_stage=0)["high_seconds"], 680)

    def test_a_finished_run_reports_no_eta(self):
        for durations in self.THREE:
            run_dir = self._finished(durations)
        self.assertIsNone(runs.get_state(run_dir.name)["eta"])

    def test_the_runs_own_model_does_not_change_its_estimate(self):
        """The seam, on both run reads. Before 2026-11-28 a run on the slow model here was told
        what that model's runs took, one on the fast model what the fast one's took, and one on a
        model new here what other models took, said in words. Now all three are told the same,
        and the answer names no model (a response model drops what it does not declare)."""
        for durations in ((60, 900, 400, 100, 60), (60, 700, 300, 100, 60), (60, 800, 350, 100, 60)):
            self._finished(durations, model="slow-model")
        for durations in self.THREE:
            self._finished(durations, model="fast-model")
        on = {model: self._running(model, serial=serial)
              for serial, model in enumerate(("slow-model", "fast-model", "brand-new-model", None))}

        class _Alive:
            def poll(self):
                return None

        registry = {run_id: runs._Handle(run_id=run_id, topic="t", proc=_Alive(), log_file=None)
                    for run_id in on.values()}
        with patch.object(runs, "_registry", registry), patch.object(access, "ACCESS_CODE", None), \
                patch.object(access, "ACCESS_CODES", None), patch.object(access, "ADMIN_CODE", None):
            client = TestClient(app)
            told = {}
            for model, run_id in on.items():
                for path in (f"/api/runs/{run_id}", f"/api/runs/{run_id}/progress"):
                    body = client.get(path).json()
                    self.assertEqual(body["llm_model"], model, path)
                    estimate = body["eta"]
                    self.assertEqual(set(estimate), self.FIELDS, path)
                    told[(model, path.endswith("progress"))] = (estimate["basis_runs"], tuple(estimate["few_sample_stages"]))
                    # 40 s into a report stage that took 120 to 400, then review 90 to 100 and scoring
                    # 30 to 60, from all six runs.
                    self.assertTrue(199 <= estimate["low_seconds"] <= 200, (model, estimate))
                    self.assertTrue(519 <= estimate["high_seconds"] <= 520, (model, estimate))
            self.assertEqual(set(told.values()), {(6, ())})
            self.assertEqual(len(told), 8)


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
