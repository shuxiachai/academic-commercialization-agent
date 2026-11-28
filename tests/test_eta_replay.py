"""The production run of 2026-11-27 on qwen3.8-2.4t-a95b, replayed through api/eta.py.

Its page's time-left line read, at 0:12, 1:37, 4:57, 5:58, 10:23, 10:43,
14:48, 16:08, 16:48 and 25:18: 4-25, 8-24, 8-9, 3-21, 1-16, 11-16, 7-8, 5-6,
1-13 and 3-4 minutes, every one "going by runs on other models". The low end
went from 1 to 11 in twenty seconds; the range closed to one minute four
times and opened again; at 16:08 it said 5-6 minutes when the review alone
then took nine. The model had three earlier runs on record, one completed,
one failed in scoring, one a resume that only scored, and none of them was
asked: only completed whole runs were history, three of one model were
needed, and each range was drawn from whichever runs had stayed in the
current stage at least as long as this one had, which near the end of a
stage was one run.

The fixture (tests/fixtures/eta_replay/run-2026-11-27.json) holds the run's
own stage record, the readable records of the model's earlier runs, and
five stand-in runs of another model fitted so that the code at main 102346f
gives every one of the ten values above from the same inputs. Its notes say
which is which.

Since 2026-11-28 the range is every model's recent runs, whichever model
this run is on (the user asked that a model change not move it). So the
stand-ins, which stand for the other models' runs production then held,
are now half the range: the sequence below shows the method on these
inputs, not what production would have said, which this fixture cannot
know.
"""

from __future__ import annotations

import json
import math
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from academic_agent.run_terminal import TerminalRecord, UsageAccounting, commit_terminal_record
from api import eta, runs

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "eta_replay" / "run-2026-11-27.json")
                     .read_text(encoding="utf-8"))
STAGES = [timing["stage"] for timing in FIXTURE["run"]["stage_timings"]]


def _write(root: Path, serial: int, entry: dict) -> None:
    if entry.get("stand_in"):
        started = datetime.fromisoformat(entry["day"] + "T09:00:00+00:00")
        at = started + timedelta(seconds=10)
        timings = []
        for stage, seconds in zip(STAGES, entry["stages"], strict=True):
            timings.append({"stage": stage, "started_at": at.isoformat()})
            at += timedelta(seconds=seconds)
        timings.append({"stage": "Done", "started_at": at.isoformat()})
        ended = at
    else:
        timings = entry["stage_timings"]
        started, ended = (datetime.fromisoformat(entry[key]) for key in ("started_at", "ended_at"))
    run_dir = root / (started.strftime("%Y%m%dT%H%M%SZ-") + f"{serial:032x}")
    run_dir.mkdir()
    status = {"stage": "Done" if entry["state"] == "completed" else "Error", "done": True,
              "llm_model": entry["model"], "stage_timings": timings}
    if entry.get("recovery"):
        status["recovery"] = entry["recovery"]
    (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    commit_terminal_record(run_dir, TerminalRecord(
        state=entry["state"], reason_code="worker_completed" if entry["state"] == "completed" else "worker_exception",
        termination_method="worker_exit", started_at=started, ended_at=ended,
        elapsed_seconds=int((ended - started).total_seconds()), last_stage=status["stage"], timeout_seconds=1800,
        usage=None, recovery=entry.get("recovery"),
        usage_accounting=UsageAccounting(state="unavailable", snapshot_at=ended,
                                         run_complete=entry["state"] == "completed",
                                         in_flight_request_may_have_spent=False),
    ))


def _clock(shown: str) -> int:
    minutes, seconds = shown.split(":")
    return int(minutes) * 60 + int(seconds)


def replay() -> list[dict]:
    """The estimate at each moment the page was read, with where the run was then."""
    root = Path(tempfile.mkdtemp())
    try:
        for serial, entry in enumerate(FIXTURE["history"], 1):
            _write(root, serial, entry)
        run = FIXTURE["run"]
        start = datetime.fromisoformat(run["started_at"])
        began = [(timing["stage"], (datetime.fromisoformat(timing["started_at"]) - start).total_seconds())
                 for timing in run["stage_timings"]]
        points = []
        with patch.object(runs, "DEFAULT_OUTPUT_ROOT", root), patch.object(eta, "_cache", {}):
            for shown, page in FIXTURE["observed"]:
                elapsed = _clock(shown)
                stage, since = [entry for entry in began if entry[1] <= elapsed][-1]
                in_stage = int(elapsed - since)
                timings = [{"stage": stage, "started_at": "", "duration_seconds": in_stage, "active": True}]
                points.append({
                    "shown": shown, "page": page, "elapsed": elapsed, "stage": eta.stage_key(stage),
                    "estimate": eta.estimate(stage, timings),
                })
        return points
    finally:
        shutil.rmtree(root, ignore_errors=True)


def said(estimate: dict) -> str:
    """The range as run.js minutesRange says it: low end down, high end up, never under 1."""
    low = max(1, math.floor(estimate["low_seconds"] / 60))
    high = max(low, math.ceil(estimate["high_seconds"] / 60))
    return f"{low}–{high}"


class ReplayOfTheRunOf20261127(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.points = replay()

    def test_every_reading_goes_by_the_runs_of_every_model_and_names_none(self):
        """Its model's three runs and the five of another model all count, every stage seen at
        least three times, so nothing is widened and no model is named."""
        for point in self.points:
            estimate = point["estimate"]
            self.assertIsNotNone(estimate, point["shown"])
            self.assertEqual((estimate["basis_runs"], estimate["few_sample_stages"]), (8, []), point["shown"])
            self.assertFalse({"model", "same_model", "other_model_stages"} & set(estimate), point["shown"])

    def test_within_a_stage_the_range_only_closes_in_as_time_passes(self):
        """Neither end rises, and neither falls faster than the clock: 1-16 then 11-16 twenty
        seconds later, or 8-24 then 8-9, cannot happen."""
        for before, after in zip(self.points, self.points[1:], strict=False):
            if before["stage"] != after["stage"]:
                continue
            passed = after["elapsed"] - before["elapsed"]
            for end in ("low_seconds", "high_seconds"):
                was, now = before["estimate"][end], after["estimate"][end]
                self.assertLessEqual(now, was, (before["shown"], after["shown"], end))
                self.assertLessEqual(was - now, passed + 1, (before["shown"], after["shown"], end))

    def test_no_reading_is_a_one_minute_range(self):
        for point in self.points:
            low, high = (int(part) for part in said(point["estimate"]).split("–"))
            self.assertGreaterEqual(high - low, 2, (point["shown"], said(point["estimate"])))

    def test_what_the_run_had_left_is_inside_every_range(self):
        """At 16:08 the page said 5-6 minutes; the review then took nine and the scorer, when the
        resume ran it, 3 min 38 s. Had the scorer run here, that is what was left."""
        run = FIXTURE["run"]
        for point in self.points:
            left = run["review_ended_seconds"] + run["resume_scoring_seconds"] - point["elapsed"]
            estimate = point["estimate"]
            self.assertTrue(estimate["low_seconds"] <= left <= estimate["high_seconds"],
                            (point["shown"], left, estimate["low_seconds"], estimate["high_seconds"]))

    def test_the_upper_end_passed_the_time_left_before_the_limit_until_the_review(self):
        """What the run page compares to warn that this run may come close to the limit: until the
        review began, every reading's slowest case needed more than the 30 minutes had left."""
        limit = FIXTURE["run"]["hard_timeout_seconds"]
        warned = [point["estimate"]["high_seconds"] > limit - point["elapsed"] for point in self.points]
        self.assertEqual(warned, [point["stage"] != "review" for point in self.points])

    def test_the_replayed_readings(self):
        """The sequence the change gives on these inputs, beside the one production showed."""
        self.assertEqual([page for _shown, page in FIXTURE["observed"]],
                         ["4–25", "8–24", "8–9", "3–21", "1–16", "11–16", "7–8", "5–6", "1–13", "3–4"])
        # By this model's own runs (#512) it read 18-38, 17-36, 15-32, 15-32, 10-27, 10-27, 8-23,
        # 8-22, 8-16, 2-8: narrower and higher, as long as the model stays the same.
        self.assertEqual([said(point["estimate"]) for point in self.points],
                         ["4–31", "3–29", "3–26", "2–25", "1–21", "1–21", "1–17", "1–15", "1–13", "1–4"])


if __name__ == "__main__":
    unittest.main()
