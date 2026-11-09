"""Every provider attempt leaves a record, and the per-node window is real.

Why these exist. On 2026-11-08 a production run's writer stage took 282
seconds for a 6,487-token answer while the reviewer, on the same model in the
same run, wrote 2,880 tokens in 50 seconds. The arithmetic says one attempt was
killed by the 150-second transport timeout and a second one finished; the
usage record said one request, because CrewAI counts successful requests only,
and the wrapper's "retrying" notice went to stdout, which the API worker sends
to /dev/null. Nothing in the run directory or the API could confirm or deny a
billed, invisible retry. These tests pin the two seams that make it visible
(an attempt observer and a stderr notice) and the one that makes it rarer (the
writer's longer window actually reaching the transport client).
"""

from __future__ import annotations

import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from academic_agent import llm_config
from academic_agent.llm_config import (
    _wrap_with_retry,
    configure_llm_deadline,
    set_attempt_observer,
)


class _Client:
    def __init__(self, timeout):
        self.timeout = timeout

    def with_options(self, *, timeout):
        return _Client(timeout)


class _Provider:
    """The attributes the CrewAI provider builds each request from."""

    def __init__(self, side_effect=None, return_value="answer"):
        self.base_url, self.model = "https://example.test/v1", "model-x"
        self.timeout = 150.0
        self._client = _Client(150.0)
        self.additional_params = {}
        self.response_format = None
        self.temperature = 0.0
        self.call = MagicMock(side_effect=side_effect, return_value=return_value)


class AttemptObserverTests(unittest.TestCase):

    def setUp(self):
        patcher = patch("academic_agent.llm_config.time.sleep")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.records: list[dict] = []
        self.observer = self.records.append
        previous = set_attempt_observer(self.observer)
        self.addCleanup(set_attempt_observer, previous)

    def _wrapped(self, **kwargs):
        provider = _Provider(**kwargs)
        llm = _wrap_with_retry(provider)
        configure_llm_deadline(
            llm, deadline_monotonic=None, stage="Writer", request_timeout_seconds=150.0,
        )
        return llm

    def test_a_successful_call_reports_one_returned_attempt_with_its_duration(self):
        clock = iter([100.0, 212.4])
        llm = self._wrapped()
        with patch("academic_agent.llm_config.time.monotonic", side_effect=lambda: next(clock)):
            self.assertEqual(llm.call("prompt"), "answer")

        self.assertEqual(len(self.records), 1)
        record = self.records[0]
        self.assertEqual(record["stage"], "Writer")
        self.assertEqual(record["attempt"], 1)
        self.assertEqual(record["outcome"], "returned")
        self.assertAlmostEqual(record["duration_seconds"], 112.4)
        self.assertFalse(record["retry"])

    def test_a_timed_out_attempt_is_reported_before_the_retry_that_succeeds(self):
        """The billed attempt that usage never shows is the one that matters."""
        calls = []

        def slow_then_fine(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise TimeoutError("Request timed out.")
            return "answer"

        llm = self._wrapped(side_effect=slow_then_fine)
        self.assertEqual(llm.call("prompt"), "answer")

        self.assertEqual(
            [(r["attempt"], r["outcome"], r["retry"]) for r in self.records],
            [(1, "timeout", True), (2, "returned", False)],
        )
        self.assertEqual(self.records[0]["error_type"], "TimeoutError")

    def test_a_rejected_request_is_reported_as_an_error_without_retry(self):
        llm = self._wrapped(side_effect=RuntimeError("401 Unauthorized"))
        with self.assertRaises(RuntimeError):
            llm.call("prompt")

        self.assertEqual(
            [(r["attempt"], r["outcome"], r["retry"], r["error_type"]) for r in self.records],
            [(1, "error", False, "RuntimeError")],
        )

    def test_a_failing_observer_cannot_break_the_provider_call(self):
        """Diagnostics must never cost a run that the provider answered."""
        def explode(_record):
            raise ValueError("observer bug")

        set_attempt_observer(explode)
        llm = self._wrapped()
        self.assertEqual(llm.call("prompt"), "answer")

    def test_the_observer_is_process_global_and_restorable(self):
        seen = []
        observer = seen.append
        previous = set_attempt_observer(observer)
        try:
            self.assertIs(previous, self.observer)
            self._wrapped().call("prompt")
        finally:
            restored = set_attempt_observer(previous)
        self.assertIs(restored, observer)
        self.assertEqual(len(seen), 1)
        self.assertEqual(self.records, [])


class RetryNoticeDestinationTests(unittest.TestCase):

    def setUp(self):
        patcher = patch("academic_agent.llm_config.time.sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_retry_notice_goes_to_stderr_where_the_api_worker_keeps_it(self):
        """api/runs.py starts the worker with stdout=DEVNULL and stderr into
        process.log. A notice on stdout is a notice nobody can read later."""
        calls = []

        def flaky(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise ConnectionError("Connection error.")
            return "answer"

        llm = _wrap_with_retry(_Provider(side_effect=flaky))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            llm.call("prompt")

        self.assertIn("retrying", err.getvalue())
        self.assertIn("ConnectionError", err.getvalue())
        self.assertEqual(out.getvalue(), "")


class TransportWindowTests(unittest.TestCase):

    def test_a_longer_stage_window_reaches_the_sdk_client(self):
        """A 300-second budget that leaves the client at 150 changes nothing:
        the SDK still cuts the writer at 150 and the retry is billed anyway."""
        provider = _Provider()
        llm = _wrap_with_retry(provider)

        configure_llm_deadline(
            llm, deadline_monotonic=None, stage="Writer", request_timeout_seconds=300.0,
        )

        self.assertEqual((provider.timeout, provider._client.timeout), (300.0, 300.0))
        self.assertEqual(llm._academic_agent_call_budget.request_timeout_seconds, 300.0)

    def test_the_ordinary_window_leaves_the_client_as_built(self):
        provider = _Provider()
        llm = _wrap_with_retry(provider)
        client_before = provider._client

        configure_llm_deadline(
            llm, deadline_monotonic=None, stage="Scorer", request_timeout_seconds=150.0,
        )

        self.assertIs(provider._client, client_before)
        self.assertEqual(provider.timeout, 150.0)

    def test_thinking_time_doubles_the_window_the_stage_was_given(self):
        """The thinking adaptation multiplies whatever the node has, so the
        writer on a thinking-only model gets 600, not 300 and not 150."""
        provider = _Provider()
        llm = _wrap_with_retry(provider)
        configure_llm_deadline(
            llm, deadline_monotonic=None, stage="Writer", request_timeout_seconds=300.0,
        )

        llm_config._give_thinking_time(llm, llm._academic_agent_call_budget)

        self.assertEqual((provider.timeout, provider._client.timeout), (600.0, 600.0))
        self.assertEqual(llm._academic_agent_call_budget.request_timeout_seconds, 600.0)


if __name__ == "__main__":
    unittest.main()
