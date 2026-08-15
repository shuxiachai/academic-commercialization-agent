"""Tests for the run's progress state machine.

This drives the live agent log — the panel added in difficulty 15 so the
middle three agents stopped being a black box. It lived as a closure inside
main(), holding a lock, reachable only by running a real six-agent crew, so
the ordering it encodes had never been checked against anything.

What makes it worth pinning is that both ends of the sequence are special and
neither is obvious from reading one branch: the first two parallel
completions announce no successor, and the last sequential one has none to
announce.
"""

from __future__ import annotations

import threading
import unittest

from academic_agent.pipeline_worker import (
    _PARALLEL_COUNT,
    _PARALLEL_STAGE,
    _SEQUENTIAL_STAGES,
    ProgressTracker,
)


def _tracker() -> ProgressTracker:
    return ProgressTracker(_PARALLEL_COUNT, _SEQUENTIAL_STAGES, _PARALLEL_STAGE)


class SequenceTests(unittest.TestCase):

    def _run_all(self) -> list[tuple[int, str, int | None]]:
        tracker = _tracker()
        return [tracker.on_complete() for _ in range(tracker.total_agents)]

    def test_every_agent_is_reported_finished_exactly_once_in_order(self):
        """A repeated or skipped index leaves the log showing an agent that
        never ran, or none for one that did."""
        self.assertEqual([r[0] for r in self._run_all()], [0, 1, 2, 3, 4, 5])

    def test_the_first_two_parallel_completions_announce_no_successor(self):
        """The other two evidence agents are already running. Marking one as
        starting would show the same agent twice in the log."""
        results = self._run_all()
        self.assertIsNone(results[0][2])
        self.assertIsNone(results[1][2])

    def test_the_last_parallel_completion_starts_the_report_writer(self):
        """This is the one moment in the parallel phase where something
        genuinely begins."""
        finished, stage, next_idx = self._run_all()[2]
        self.assertEqual(finished, 2)
        self.assertEqual(next_idx, _PARALLEL_COUNT)
        self.assertEqual(stage, _SEQUENTIAL_STAGES[0])

    def test_the_parallel_phase_reports_its_own_stage_until_it_ends(self):
        results = self._run_all()
        self.assertEqual(results[0][1], _PARALLEL_STAGE)
        self.assertEqual(results[1][1], _PARALLEL_STAGE)

    def test_each_sequential_agent_announces_the_next(self):
        results = self._run_all()
        self.assertEqual(results[3][2], 4)
        self.assertEqual(results[4][2], 5)

    def test_the_final_agent_announces_nobody(self):
        """next_idx == total would write a step for an agent index the client
        has no row for."""
        self.assertIsNone(self._run_all()[5][2])

    def test_stage_names_advance_and_never_run_past_the_list(self):
        """The last completion computes a sequential index one past the end;
        it clamps rather than raising, because a run that finished must not
        fail while reporting that it finished."""
        stages = [r[1] for r in self._run_all()]
        self.assertEqual(stages[2:], [_SEQUENTIAL_STAGES[0], _SEQUENTIAL_STAGES[1],
                                      _SEQUENTIAL_STAGES[2], _SEQUENTIAL_STAGES[2]])

    def test_completions_past_the_end_do_not_raise(self):
        """CrewAI has fired this callback more times than there are tasks
        before — difficulty 15's AgentExecutionStartedEvent fired three times
        for one agent. A progress tracker must not be the thing that kills a
        finished run."""
        tracker = _tracker()
        for _ in range(tracker.total_agents + 3):
            finished, stage, next_idx = tracker.on_complete()
        self.assertEqual(stage, _SEQUENTIAL_STAGES[-1])
        self.assertIsNone(next_idx)


class ConcurrencyTests(unittest.TestCase):
    """The three evidence agents run in parallel and complete on their own
    threads. Unsynchronised counters give two of them the same index, and the
    log then shows one agent twice and another never."""

    def test_on_complete_holds_the_lock(self):
        """The deterministic half. Three threads each incrementing once collide
        too rarely under the GIL for a stress test to prove the lock matters —
        removing it entirely leaves the test below passing. This asserts the
        mechanism instead: whatever the scheduler does, the critical section is
        entered under the lock."""
        tracker = _tracker()
        acquisitions = []
        real = tracker._lock

        class _Watched:
            def __enter__(self):
                acquisitions.append(1)
                return real.__enter__()

            def __exit__(self, *exc):
                return real.__exit__(*exc)

        tracker._lock = _Watched()
        tracker.on_complete()
        self.assertGreaterEqual(tracker.completed, 1)   # the reader path too
        self.assertEqual(len(acquisitions), 2)

    def test_parallel_completions_get_distinct_indices(self):
        """The probabilistic half, run wide enough to be worth something: 64
        threads released together, each taking one index. Two threads reading
        the same counter before either writes would produce a duplicate."""
        width = 64
        tracker = ProgressTracker(width, _SEQUENTIAL_STAGES, _PARALLEL_STAGE)
        seen: list[int] = []
        lock = threading.Lock()
        barrier = threading.Barrier(width)

        def complete():
            barrier.wait()          # release them all at once
            finished, _stage, _next = tracker.on_complete()
            with lock:
                seen.append(finished)

        threads = [threading.Thread(target=complete) for _ in range(width)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(sorted(seen), list(range(width)))

    def test_completed_count_is_readable_while_others_are_completing(self):
        """The tool-usage handlers read this as a fallback agent index from
        the same threads that are advancing it."""
        tracker = _tracker()
        errors: list[BaseException] = []

        def reader():
            try:
                for _ in range(200):
                    self.assertGreaterEqual(tracker.completed, 0)
            except BaseException as exc:      # noqa: BLE001 - re-raised below
                errors.append(exc)

        def writer():
            for _ in range(tracker.total_agents):
                tracker.on_complete()

        threads = [threading.Thread(target=reader), threading.Thread(target=writer)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(tracker.completed, tracker.total_agents)


class ShapeTests(unittest.TestCase):

    def test_total_agents_matches_the_configured_pipeline(self):
        self.assertEqual(_tracker().total_agents,
                         _PARALLEL_COUNT + len(_SEQUENTIAL_STAGES))

    def test_it_does_not_assume_three_and_three(self):
        """The counts are constructor arguments so that adding a seventh agent
        is a config change, not an arithmetic edit in a closure."""
        tracker = ProgressTracker(2, ["A", "B", "C"], "parallel")
        self.assertEqual(tracker.total_agents, 5)
        self.assertEqual([tracker.on_complete()[0] for _ in range(5)], [0, 1, 2, 3, 4])
