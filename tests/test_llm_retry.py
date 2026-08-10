"""Tests for LLM call retry.

A run makes six LLM calls over about three minutes. One dropped connection
used to discard everything before it — a real run died at 2:16 having already
retrieved and validated 24 sources across seven APIs, because the network
changed underneath it. Source retrieval had backoff from early on; the LLM
calls did not.

The important half of these tests is what does NOT retry. Retrying a rejected
request cannot succeed, and against a billed API it may be charged per attempt.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from academic_agent.llm_config import _MAX_ATTEMPTS, _is_retryable, _wrap_with_retry


class RetryClassificationTests(unittest.TestCase):

    def test_transport_failures_are_retryable(self):
        for exc in [
            ConnectionError("Connection error."),
            TimeoutError("timed out"),
            OSError("[Errno 104] Connection reset by peer"),
            RuntimeError("Failed to connect to OpenAI API: Connection error."),
            RuntimeError("502 Bad Gateway"),
            RuntimeError("503 Service Temporarily Unavailable"),
        ]:
            with self.subTest(exc=type(exc).__name__ + str(exc)[:30]):
                self.assertTrue(_is_retryable(exc))

    def test_rejected_requests_are_not_retryable(self):
        """These cannot succeed on a second attempt, and may be billed."""
        for exc in [
            RuntimeError("401 Unauthorized"),
            RuntimeError("403 Forbidden"),
            RuntimeError("Invalid API key provided"),
            ValueError("400 Bad Request: malformed messages"),
            RuntimeError("authentication failed"),
        ]:
            with self.subTest(exc=str(exc)[:30]):
                self.assertFalse(_is_retryable(exc))

    def test_rate_limits_are_not_retried_here(self):
        """429 means "send less". Answering it with an immediate retry is the
        opposite; the pipeline's concurrency cap is the right control."""
        for exc in [
            RuntimeError("429 Too Many Requests"),
            RuntimeError("rate limit exceeded"),
            RuntimeError("quota exceeded for this month"),
        ]:
            with self.subTest(exc=str(exc)[:30]):
                self.assertFalse(_is_retryable(exc))

    def test_an_unrecognised_error_is_not_retried(self):
        """Unknown failures are treated as permanent — a wrong retry costs
        money and time, a wrong give-up costs one run."""
        self.assertFalse(_is_retryable(ValueError("something unexpected")))


class RetryBehaviourTests(unittest.TestCase):

    def setUp(self):
        # Nothing here should actually wait.
        patcher = patch("academic_agent.llm_config.time.sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def _llm(self, side_effect=None, return_value=None):
        """A stand-in for the provider object the factory returns.

        crewai.LLM is a factory — LLM(...) yields OpenAICompatibleCompletion or
        similar, and isinstance(that, LLM) is False. The retry wraps whatever
        instance it is given, so a stub with a .call is all this needs, and it
        keeps the tests off the network.
        """
        from unittest.mock import MagicMock

        stub = MagicMock()
        inner = MagicMock(side_effect=side_effect, return_value=return_value)
        stub.call = inner
        # Hold the original: _wrap_with_retry replaces stub.call, so reading it
        # afterwards would return the wrapper and lose the call count.
        return _wrap_with_retry(stub), inner

    def test_a_transient_failure_is_retried_and_succeeds(self):
        calls = []

        def flaky(*args, **kwargs):
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionError("Connection error.")
            return "answer"

        llm, _ = self._llm(side_effect=flaky)
        self.assertEqual(llm.call("prompt"), "answer")
        self.assertEqual(len(calls), 3)

    def test_it_gives_up_after_the_attempt_limit(self):
        llm, call = self._llm(side_effect=ConnectionError("down"))
        with self.assertRaises(ConnectionError):
            llm.call("prompt")
        self.assertEqual(call.call_count, _MAX_ATTEMPTS)

    def test_a_rejected_request_is_not_retried(self):
        """The regression that matters for cost: one attempt, not three."""
        llm, call = self._llm(side_effect=RuntimeError("401 Unauthorized"))
        with self.assertRaises(RuntimeError):
            llm.call("prompt")
        self.assertEqual(call.call_count, 1)

    def test_a_successful_call_does_not_sleep(self):
        llm, _ = self._llm(return_value="answer")
        llm.call("prompt")
        self.sleep.assert_not_called()

    def test_backoff_grows_between_attempts(self):
        llm, _ = self._llm(side_effect=ConnectionError("down"))
        with self.assertRaises(ConnectionError):
            llm.call("prompt")

        delays = [c.args[0] for c in self.sleep.call_args_list]
        self.assertEqual(len(delays), _MAX_ATTEMPTS - 1)
        self.assertLess(delays[0], delays[1], f"expected growth, got {delays}")

    def test_arguments_reach_the_underlying_call(self):
        llm, call = self._llm(return_value="answer")
        llm.call("prompt", tools=["t"])
        call.assert_called_once_with("prompt", tools=["t"])

    def test_the_factory_product_is_preserved(self):
        """Subclassing crewai.LLM would bypass its factory and lose the
        provider implementation entirely; wrapping must not."""
        from academic_agent.llm_config import create_llm
        import os

        os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
        llm = create_llm()
        self.assertIn("Completion", type(llm).__name__)


if __name__ == "__main__":
    unittest.main()
