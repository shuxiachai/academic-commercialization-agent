"""Tests for the concurrency cap and artifact path validation.

The cap was checked and the handle registered as two separate steps, with a
mkdir and a Popen in between and no lock around either. FastAPI runs `def`
endpoints in a thread pool, so submissions genuinely overlap: six concurrent
requests against a cap of two all started. Each run drives a six-agent LLM
pipeline, so the cost of exceeding the cap is billed, not theoretical.

The load test below fails against the unlocked version.
"""

from __future__ import annotations

import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from api import runs


class _FakeProc:
    """A subprocess that never exits."""

    def __init__(self, *args, **kwargs):
        pass

    def poll(self):
        return None

    def terminate(self):
        pass

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


class _ConcurrencyTestBase(unittest.TestCase):

    def setUp(self):
        runs._registry.clear()
        self._tmp = TemporaryDirectory()
        # Order matters: cleanups run last-registered-first, so the log files
        # must be closed before the directory holding them is removed.
        # Windows refuses to unlink a file that still has an open handle, and
        # every started run owns an open process.log.
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self._close_open_logs)
        patcher = patch.object(runs, "DEFAULT_OUTPUT_ROOT", Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _close_open_logs(self):
        for handle in list(runs._registry.values()):
            if handle.log_file is not None:
                try:
                    handle.log_file.close()
                except OSError:
                    pass
        runs._registry.clear()


class ConcurrencyCapTests(_ConcurrencyTestBase):

    def test_parallel_submissions_respect_the_cap(self):
        """The regression this file exists for.

        A barrier maximises overlap so every thread reaches the cap check at
        the same moment — which is exactly the window the old code left open.
        """
        started: list[str] = []
        rejected: list[int] = []
        errors: list[str] = []
        threads = 8
        barrier = threading.Barrier(threads)

        def submit():
            barrier.wait()
            try:
                run_id, _ = runs.start_run("solid-state batteries")
                started.append(run_id)
            except runs.ConcurrencyLimitReached:
                rejected.append(1)
            except Exception as exc:  # noqa: BLE001 - surface, do not swallow
                errors.append(f"{type(exc).__name__}: {exc}")

        with patch("api.runs.subprocess.Popen", _FakeProc):
            workers = [threading.Thread(target=submit) for _ in range(threads)]
            for w in workers:
                w.start()
            for w in workers:
                w.join(timeout=30)

        self.assertEqual(errors, [])
        self.assertLessEqual(
            len(started), runs.MAX_CONCURRENT,
            f"cap is {runs.MAX_CONCURRENT} but {len(started)} runs started",
        )
        self.assertEqual(len(started) + len(rejected), threads)

    def test_serial_submissions_still_reach_the_cap(self):
        """Locking must not make the cap stricter than it is."""
        with patch("api.runs.subprocess.Popen", _FakeProc):
            for _ in range(runs.MAX_CONCURRENT):
                runs.start_run("topic")
            with self.assertRaises(runs.ConcurrencyLimitReached):
                runs.start_run("one too many")

    def test_slot_is_released_when_the_process_fails_to_launch(self):
        """A reservation counts as alive, so a failed launch must remove it."""
        with patch("api.runs.subprocess.Popen", side_effect=OSError("no exec")):
            with self.assertRaises(OSError):
                runs.start_run("topic")

        self.assertEqual(runs.active_count(), 0)
        with patch("api.runs.subprocess.Popen", _FakeProc):
            runs.start_run("topic")          # must not raise
        self.assertEqual(runs.active_count(), 1)

    def test_slot_is_released_when_run_dir_creation_fails(self):
        """A failure before Popen must release the reservation too.

        Regression test: run_dir.mkdir() and the .owner write used to sit
        between the reservation and the try/except that frees it on
        failure, so an unwritable outputs directory (an unwritable Railway
        volume, in production) leaked one slot per failed attempt with no
        way to clear it short of restarting the process.
        """
        with patch("api.runs.Path.mkdir", side_effect=PermissionError("no access")):
            with self.assertRaises(PermissionError):
                runs.start_run("topic")

        self.assertEqual(runs.active_count(), 0)
        with patch("api.runs.subprocess.Popen", _FakeProc):
            runs.start_run("topic")          # must not raise
        self.assertEqual(runs.active_count(), 1)

    def test_cancel_frees_a_slot(self):
        with patch("api.runs.subprocess.Popen", _FakeProc):
            run_id, _ = runs.start_run("topic")
            self.assertEqual(runs.active_count(), 1)
            runs.cancel_run(run_id)
            self.assertEqual(runs.active_count(), 0)

        terminal = json.loads(
            (runs.run_dir_for(run_id) / "terminal.json").read_text(encoding="utf-8")
        )
        self.assertEqual(terminal["state"], "cancelled")
        self.assertEqual(terminal["reason_code"], "user_cancelled")
        self.assertEqual(terminal["usage_accounting"]["state"], "unavailable")
        self.assertTrue(terminal["usage_accounting"]["in_flight_request_may_have_spent"])

    def test_concurrent_cancels_do_not_both_succeed(self):
        """Exactly one caller owns a given run."""
        with patch("api.runs.subprocess.Popen", _FakeProc):
            run_id, _ = runs.start_run("topic")

        outcomes: list[str] = []
        barrier = threading.Barrier(4)

        def cancel():
            barrier.wait()
            try:
                runs.cancel_run(run_id)
                outcomes.append("cancelled")
            except runs.RunNotFound:
                outcomes.append("not_found")

        workers = [threading.Thread(target=cancel) for _ in range(4)]
        for w in workers:
            w.start()
        for w in workers:
            w.join(timeout=30)

        self.assertEqual(outcomes.count("cancelled"), 1, outcomes)

    def test_delete_run_refuses_a_live_run(self):
        with patch("api.runs.subprocess.Popen", _FakeProc):
            run_id, run_dir = runs.start_run("topic")
            with self.assertRaises(runs.RunStillActive):
                runs.delete_run(run_id)
            self.assertTrue(run_dir.exists())  # refused, not partially removed

    def test_delete_run_removes_a_finished_runs_directory(self):
        with patch("api.runs.subprocess.Popen", _FakeProc):
            run_id, run_dir = runs.start_run("topic")
            runs.cancel_run(run_id)  # stops it — no longer tracked as alive
        runs.delete_run(run_id)
        self.assertFalse(run_dir.exists())

    def test_delete_run_rejects_an_unknown_id(self):
        with self.assertRaises(runs.RunNotFound):
            runs.delete_run("20260101T000000Z-nonexistent0")


class ArtifactPathTests(_ConcurrencyTestBase):
    """artifact_path must validate run_id itself, not rely on call order."""

    def test_traversing_run_id_rejected(self):
        for bad in ["../secrets", "..\\secrets", "a/b", "a\\b", ".."]:
            with self.subTest(run_id=bad):
                self.assertIsNone(runs.artifact_path(bad, "report"))

    def test_empty_run_id_rejected(self):
        self.assertIsNone(runs.artifact_path("", "report"))

    def test_unknown_artifact_name_rejected(self):
        self.assertIsNone(runs.artifact_path("20260101T000000Z-abcdef", "passwd"))

    def test_valid_run_id_resolves_an_existing_artifact(self):
        run_id = "20260101T000000Z-abcdef"
        run_dir = Path(self._tmp.name) / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "commercialization_report.md").write_text("# Report", encoding="utf-8")

        path = runs.artifact_path(run_id, "report")
        self.assertIsNotNone(path)
        self.assertEqual(path.read_text(encoding="utf-8"), "# Report")

    def test_missing_artifact_returns_none(self):
        run_id = "20260101T000000Z-abcdef"
        (Path(self._tmp.name) / run_id).mkdir(parents=True)
        self.assertIsNone(runs.artifact_path(run_id, "report"))

class RunListFilterTests(_ConcurrencyTestBase):
    """Only run directories belong in the run list.

    The filter used to name its exceptions ("benchmark"), so adding
    outputs/_papers for uploaded PDFs immediately put a storage directory in
    the list, rendering as a run with no topic and no status. Matching the
    run_id shape instead means a new internal directory cannot reappear there.
    """

    def _make(self, *names):
        for name in names:
            (Path(self._tmp.name) / name).mkdir(parents=True, exist_ok=True)

    def test_internal_directories_are_not_runs(self):
        self._make("_papers", "benchmark", ".cache", "20260809T005704Z-1fac18d7a9")
        summaries, _total = runs.list_runs()
        self.assertEqual([s["run_id"] for s in summaries], ["20260809T005704Z-1fac18d7a9"])

    def test_real_run_ids_are_accepted(self):
        ids = ["20260809T005704Z-1fac18d7a9", "20260101T000000Z-abcdef0123"]
        self._make(*ids)
        summaries, _total = runs.list_runs()
        self.assertEqual(sorted(s["run_id"] for s in summaries), sorted(ids))

    def test_empty_output_root_is_not_an_error(self):
        summaries, total = runs.list_runs()
        self.assertEqual((summaries, total), ([], 0))

if __name__ == "__main__":
    unittest.main()


class ByokShareOfThePoolTests(_ConcurrencyTestBase):
    """A visitor bringing their own key pays for their own tokens, so the
    daily cap does not apply to them. That exemption is what made this a
    problem: anonymous traffic that costs the operator nothing could hold
    every concurrency slot, and a submission with a wrong key holds one while
    it fails. The people the deployment exists for — the ones handed an
    access code — were the ones who got shut out.
    """

    def _byok(self):
        return runs.BYOKCredentials(llm_provider="deepseek",
                                    llm_api_key="sk-test",
                                    serper_api_key="s-test")

    def test_byok_cannot_take_the_last_slot(self):
        with patch.object(runs.subprocess, "Popen", _FakeProc), \
             patch.object(runs, "MAX_CONCURRENT", 3), \
             patch.object(runs, "BYOK_MAX_CONCURRENT", 2):
            for _ in range(2):
                runs.start_run("topic", byok=self._byok())
            with self.assertRaises(runs.ConcurrencyLimitReached):
                runs.start_run("one too many", byok=self._byok())

    def test_a_code_holder_can_still_start_when_byok_is_saturated(self):
        """The whole point. The global cap is not reached, so this must run."""
        with patch.object(runs.subprocess, "Popen", _FakeProc), \
             patch.object(runs, "MAX_CONCURRENT", 3), \
             patch.object(runs, "BYOK_MAX_CONCURRENT", 2):
            for _ in range(2):
                runs.start_run("topic", byok=self._byok())
            runs.start_run("code holder", owner="alice")   # must not raise
            self.assertEqual(runs.active_count(), 3)

    def test_the_global_cap_still_bounds_code_holders(self):
        """The BYOK limit is checked in addition to the global one, not
        instead of it — otherwise this fix would remove the cap it sits
        behind."""
        with patch.object(runs.subprocess, "Popen", _FakeProc), \
             patch.object(runs, "MAX_CONCURRENT", 2), \
             patch.object(runs, "BYOK_MAX_CONCURRENT", 1):
            runs.start_run("a", owner="alice")
            runs.start_run("b", owner="alice")
            with self.assertRaises(runs.ConcurrencyLimitReached):
                runs.start_run("c", owner="alice")

    def test_a_finished_byok_run_releases_its_share(self):
        """Counted from live handles, not from a running total — otherwise the
        limit would be a lifetime quota that never resets."""
        class _Exited(_FakeProc):
            def poll(self):
                return 0

        with patch.object(runs, "MAX_CONCURRENT", 3), \
             patch.object(runs, "BYOK_MAX_CONCURRENT", 1):
            with patch.object(runs.subprocess, "Popen", _Exited):
                runs.start_run("finished", byok=self._byok())
            self.assertEqual(runs.active_byok_count(), 0)
            with patch.object(runs.subprocess, "Popen", _FakeProc):
                runs.start_run("next", byok=self._byok())   # must not raise

    def test_the_message_says_it_is_the_byok_limit(self):
        """A visitor told "the service is busy" while the deployment sits idle
        would report a bug that is not there."""
        with patch.object(runs.subprocess, "Popen", _FakeProc), \
             patch.object(runs, "MAX_CONCURRENT", 5), \
             patch.object(runs, "BYOK_MAX_CONCURRENT", 1):
            runs.start_run("topic", byok=self._byok())
            with self.assertRaises(runs.ConcurrencyLimitReached) as ctx:
                runs.start_run("blocked", byok=self._byok())
        self.assertIn("bring-your-own-key", str(ctx.exception))
        self.assertIn("access-code holders", str(ctx.exception))

    def test_default_leaves_at_least_one_slot_for_code_holders(self):
        """The default has to be safe on a deployment nobody configured."""
        self.assertGreaterEqual(runs.MAX_CONCURRENT - runs.byok_limit(), 1)
        self.assertGreaterEqual(runs.byok_limit(), 1)
