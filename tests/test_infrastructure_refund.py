"""A run that failed because the provider could not be reached gives its day back.

Until now a daily paid operation was refunded only when the worker never
started: once it ran, "an exception cannot prove that the provider was never
reached", so the attempt stayed charged. That rule protects the operator's
bill and it is kept for every failure a requester can cause or fix. It was
the wrong answer on 2026-11-09 and 2026-11-10, when the path from the host to
the model provider stalled on the report writer's request: eight connections
in a row in one run, and from the host's own probe a 100 KB upload that did
not finish in 30 seconds twice in six tries while the sibling endpoint in the
host's region answered in 40 milliseconds. A visitor who met that lost one of
the day's runs to a failure nothing in their request caused and nothing they
could do would fix.

So one cause is refunded after the worker has run: the provider could not be
reached. It is bounded, three a day for each owner, because a refunded run
still spent what its earlier stages cost, and an unbounded refund would turn
the cap off exactly when the path is worst.
"""

from __future__ import annotations

import json
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from academic_agent import pipeline_worker
from academic_agent.run_terminal import TerminalRecord, UsageAccounting, commit_terminal_record
from api import runs

OWNER, OTHER = "code-owner-a", "code-owner-b"
UNREACHABLE = "Connection error."


class _Exited:
    """A worker process that has already ended."""

    def poll(self):
        return 1

    def terminate(self):
        pass

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 1


class _Ledger(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name) / "outputs"
        self.root.mkdir()
        self._patches = [
            patch.object(runs, "DEFAULT_OUTPUT_ROOT", self.root),
            patch.object(runs, "MAX_CONCURRENT", 50), patch.object(runs, "BYOK_MAX_CONCURRENT", None),
            patch.object(runs, "DAILY_CAP", 10), patch.object(runs, "ACCOUNT_DAILY_CAP", 10),
            patch.object(runs, "_daily_counts", {}), patch.object(runs, "_daily_date", None),
            patch.object(runs, "_registry", {}), patch.object(runs, "_settled", []),
            patch.object(runs, "_inline_paid_operations", {}), patch.object(runs, "_inline_owners", {}),
            patch.object(runs, "_stop_claims", {}),
            patch.object(runs, "_unreachable_refunds", {}), patch.object(runs, "_unreachable_refund_date", None),
        ]
        for item in self._patches:
            item.start()
        self._number = 0

    def tearDown(self):
        for item in reversed(self._patches):
            item.stop()
        self._tmp.cleanup()

    def _ended_run(self, *, owner=OWNER, error=UNREACHABLE, state="failed", charged=True):
        """A charged run whose worker has exited, still in the registry to be reaped."""
        self._number += 1
        run_id = f"20261111T{self._number:06d}Z-{'ab' * 16}"
        run_dir = self.root / run_id
        run_dir.mkdir()
        (run_dir / ".owner").write_text(owner, encoding="utf-8")
        charged_on = None
        if charged:
            with runs._registry_lock:
                charged_on = runs._admit_paid_operation_locked(owner=owner, byok=False)
        runs._write_daily_charge(run_dir, charged_on)
        status = {"stage": "Error", "done": True}
        if error is not None:
            status["error"] = error
        (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
        now = datetime.now(UTC)
        complete = state == "completed"
        commit_terminal_record(run_dir, TerminalRecord(
            state=state,
            reason_code={"failed": "worker_exception", "completed": "worker_completed",
                         "cancelled": "user_cancelled", "timeout": "hard_timeout"}[state],
            termination_method="worker_exit" if state in ("failed", "completed") else "kill",
            started_at=now - timedelta(seconds=400), ended_at=now, elapsed_seconds=400,
            last_stage="Agent 4", timeout_seconds=1800, usage={"total_tokens": 1} if complete else None,
            usage_accounting=UsageAccounting(
                state="complete" if complete else "lower_bound", snapshot_at=now, through_stage="Agent 4",
                run_complete=complete, in_flight_request_may_have_spent=not complete),
        ))
        runs._registry[run_id] = runs._Handle(run_id=run_id, topic="t", proc=_Exited(), owner=owner)
        return run_id, run_dir

    def _used(self, owner=OWNER):
        return runs.daily_quota(owner)["used"]

    def _marker(self, run_dir):
        return json.loads((run_dir / ".daily_charge").read_text(encoding="utf-8"))


class UnreachableProviderRefundTests(_Ledger):

    def test_a_run_the_provider_could_not_be_reached_for_gives_the_day_back(self):
        run_id, run_dir = self._ended_run()
        self.assertEqual(self._used(), 1)

        runs.active_count()

        self.assertEqual(self._used(), 0)
        self.assertEqual(runs._read_daily_charge(run_dir), "refunded")
        self.assertEqual(self._marker(run_dir)["refund_reason"], "provider_unreachable")
        state = runs.get_state(run_id)
        self.assertEqual((state["daily_charge"], state["daily_charge_reason"]), ("refunded", "provider_unreachable"))
        # A new process reads the file, not its memory.
        with patch.object(runs, "_daily_counts", {}), patch.object(runs, "_daily_date", None):
            self.assertEqual(self._used(), 0)

    def test_a_request_the_transport_cut_is_the_same_cause(self):
        """What the writer's failed attempts raised on 2026-11-09."""
        for error in (
            "Request timed out.",
            "APITimeoutError: Request timed out.",
            "writer has 5.0s remaining; a bounded provider attempt requires 64.2s "
            "(caused by APITimeoutError: Request timed out.)",
            "writer has 5.0s remaining; a bounded provider attempt requires 64.2s "
            "(caused by APIConnectionError: Connection error.)",
        ):
            with self.subTest(error=error):
                _, run_dir = self._ended_run(error=error)
                runs.active_count()
                self.assertEqual(runs._read_daily_charge(run_dir), "refunded")
                runs._unreachable_refunds.clear()

    def test_every_other_ending_stays_charged(self):
        """The rule that protects the operator's bill is kept for anything a
        requester can cause or fix, and for anything ambiguous."""
        cases = {
            "a rejected key": dict(error="Error code: 401 - invalid api key"),
            "the quality checks": dict(error="Guardrail failed: blocking validation errors"),
            "too little evidence": dict(error="SourceCollectionError: retrieval produced 2 validated sources"),
            "a rate limit": dict(error="Error code: 429 - rate limit exceeded"),
            "something nobody has seen": dict(error="ValueError: unexpected"),
            "the run's own time budget": dict(error="writer has 5.0s remaining; a bounded provider attempt requires 300.0s"),
            "no recorded reason": dict(error=None),
            "a cancellation": dict(state="cancelled"),
            "the watchdog": dict(state="timeout"),
            "a completed run": dict(state="completed", error=None),
        }
        for name, kwargs in cases.items():
            with self.subTest(case=name):
                before = self._used() if runs._daily_counts else 0
                _, run_dir = self._ended_run(**kwargs)
                runs.active_count()
                self.assertEqual(self._used(), before + 1, name)
                self.assertEqual(runs._read_daily_charge(run_dir), "charged")
                self.assertNotIn("refund_reason", {k: v for k, v in self._marker(run_dir).items() if v})

    def test_a_run_that_was_never_charged_has_nothing_to_give_back(self):
        _, run_dir = self._ended_run(charged=False)
        self._ended_run(error="ValueError: unexpected")          # another run holds the owner's one unit
        runs.active_count()
        self.assertEqual(self._used(), 1)
        self.assertEqual(runs._read_daily_charge(run_dir), "not_charged")

    def test_a_charge_from_a_day_that_is_over_is_left_alone(self):
        _, run_dir = self._ended_run()
        yesterday = (datetime.now(UTC).date() - timedelta(days=1))
        runs._write_daily_charge(run_dir, yesterday)
        runs.active_count()
        self.assertEqual(self._used(), 1, "today's count is not paid for yesterday's failure")
        self.assertEqual(runs._read_daily_charge(run_dir), "charged")

    def test_it_is_given_once(self):
        run_id, run_dir = self._ended_run()
        self._ended_run(error="ValueError: unexpected")
        runs.active_count()
        self.assertEqual(self._used(), 1)
        # The same exit seen again, as after a restart that re-registers nothing.
        with runs._registry_lock:
            runs._refund_unreachable_failure_locked(run_id, OWNER)
        self.assertEqual(self._used(), 1)


class RefundBoundTests(_Ledger):

    def test_three_a_day_for_each_owner(self):
        """A refunded run still spent what its earlier stages cost. Without a
        bound, a bad afternoon turns the cap off for anyone who keeps trying."""
        self.assertEqual(runs.UNREACHABLE_REFUNDS_PER_DAY, 3)
        dirs = [self._ended_run()[1] for _ in range(5)]
        runs.active_count()
        self.assertEqual([runs._read_daily_charge(d) for d in dirs],
                         ["refunded", "refunded", "refunded", "charged", "charged"])
        self.assertEqual(self._used(), 2)

        _, other = self._ended_run(owner=OTHER)
        runs.active_count()
        self.assertEqual(runs._read_daily_charge(other), "refunded", "one owner's bad day is not another's")

    def test_the_bound_starts_again_with_the_day(self):
        for _ in range(3):
            self._ended_run()
        runs.active_count()
        tomorrow = datetime.now(UTC) + timedelta(days=1)

        class _Tomorrow(datetime):
            @classmethod
            def now(cls, tz=None):
                return tomorrow if tz is not None else tomorrow.replace(tzinfo=None)

        with patch.object(runs, "datetime", _Tomorrow):
            _, run_dir = self._ended_run()
            runs.active_count()
            self.assertEqual(runs._read_daily_charge(run_dir), "refunded")


class RefundNeverBreaksTheReapTests(_Ledger):

    def test_a_ledger_that_cannot_be_written_keeps_the_charge(self):
        _, run_dir = self._ended_run()
        with patch.object(runs, "_write_daily_ledger_locked", side_effect=runs.PaidLedgerUnavailable("disk")):
            self.assertEqual(runs.active_count(), 0)
        self.assertEqual(runs._read_daily_charge(run_dir), "charged")
        self.assertEqual(runs._daily_counts.get(OWNER), 1)
        self.assertEqual(runs._unreachable_refunds.get(OWNER, 0), 0, "a refund that did not happen is not counted")

    def test_damaged_records_keep_the_charge_and_the_reap_goes_on(self):
        for damage in ("status", "terminal", "marker"):
            with self.subTest(damage=damage):
                run_id, run_dir = self._ended_run()
                name = {"status": "status.json", "terminal": "terminal.json", "marker": ".daily_charge"}[damage]
                (run_dir / name).write_text("{not json", encoding="utf-8")
                before = runs._daily_counts.get(OWNER)
                self.assertEqual(runs.active_count(), 0)
                self.assertEqual(runs._daily_counts.get(OWNER), before)
                self.assertNotIn(run_id, runs._registry)

    def test_an_unexpected_error_in_the_refund_does_not_reach_admission(self):
        self._ended_run()
        with patch.object(runs, "_read_terminal", side_effect=RuntimeError("boom")):
            self.assertEqual(runs.active_count(), 0)
        self.assertEqual(self._used(), 1)


class ChargeMarkerReasonTests(unittest.TestCase):

    def test_the_marker_says_why_a_charge_was_given_back(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            runs._write_daily_charge(run_dir, date(2026, 11, 11), refunded=True, refund_reason="launch_failed")
            self.assertEqual(runs._read_daily_charge(run_dir), "refunded")
            self.assertEqual(runs._read_refund_reason(run_dir), "launch_failed")

    def test_a_marker_from_before_reasons_has_none(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / ".daily_charge").write_text(json.dumps(
                {"schema_version": 1, "charged": True, "charged_on": "2026-10-23", "refunded": True}), encoding="utf-8")
            self.assertEqual(runs._read_daily_charge(run_dir), "refunded")
            self.assertIsNone(runs._read_refund_reason(run_dir))

    def test_only_a_known_reason_on_a_refunded_charge_is_reported(self):
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            for record in (
                {"schema_version": 1, "charged": True, "charged_on": "2026-10-23", "refunded": False,
                 "refund_reason": "provider_unreachable"},
                {"schema_version": 1, "charged": True, "charged_on": "2026-10-23", "refunded": True,
                 "refund_reason": "<script>"},
            ):
                (run_dir / ".daily_charge").write_text(json.dumps(record), encoding="utf-8")
                self.assertIsNone(runs._read_refund_reason(run_dir))
            (run_dir / ".daily_charge").write_text("{not json", encoding="utf-8")
            self.assertIsNone(runs._read_refund_reason(run_dir))


class FailureWordingTests(unittest.TestCase):
    """A request the transport cut was told to "retry with a narrower topic"."""

    def test_a_cut_provider_request_is_unreachable_not_the_time_limit(self):
        for raw in ("Request timed out.", "APITimeoutError: Request timed out.",
                    "openai.APIConnectionError: Connection error.",
                    "writer has 5.0s remaining; a bounded provider attempt requires 64.2s "
                    "(caused by APITimeoutError: Request timed out.)"):
            with self.subTest(raw=raw):
                code, message = runs._public_failure(raw)
                self.assertEqual(code, "provider_unreachable")
                self.assertNotIn("narrower topic", message)

    def test_the_runs_own_time_limit_keeps_its_code(self):
        for raw in ("the run timed out before the report was written", "deadline exceeded while waiting for sources",
                    "hard timeout after 1800 seconds"):
            with self.subTest(raw=raw):
                self.assertEqual(runs._public_failure(raw)[0], "timeout")

    def test_a_retrieval_timeout_is_not_called_an_unreachable_provider(self):
        """A search service that timed out is a different failure with its own
        wording; only what the model SDK raises is read as this one."""
        raw = "SourceCollectionError: retrieval produced 2 validated sources (Tavily: Read timed out.)"
        self.assertNotEqual(runs._public_failure(raw)[0], "provider_unreachable")


class WorkerErrorTextTests(unittest.TestCase):
    """The budget's refusal used to hide the transport failure that led to it."""

    def test_the_cause_is_kept_beside_the_error(self):
        try:
            try:
                raise ConnectionError("Connection error.")
            except ConnectionError as cause:
                raise TimeoutError("writer has 5.0s remaining; a bounded provider attempt requires 64.2s") from cause
        except TimeoutError as exc:
            text = pipeline_worker._error_text(exc)
        self.assertEqual(text, "writer has 5.0s remaining; a bounded provider attempt requires 64.2s "
                               "(caused by ConnectionError: Connection error.)")
        self.assertEqual(runs._public_failure(text)[0], "provider_unreachable")

    def test_an_error_without_a_cause_is_its_own_text(self):
        self.assertEqual(pipeline_worker._error_text(ValueError("bad input")), "bad input")

    def test_the_text_stays_bounded(self):
        try:
            try:
                raise ConnectionError("c" * 900)
            except ConnectionError as cause:
                raise RuntimeError("e" * 900) from cause
        except RuntimeError as exc:
            self.assertEqual(len(pipeline_worker._error_text(exc)), 400)


if __name__ == "__main__":
    unittest.main()
