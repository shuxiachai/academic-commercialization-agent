"""A transport retry gets a fresh connection, and a streamed call gets more of them.

The first production run on streamed crew calls (2026-11-09, 343 s) had five
failed attempts in eleven, in one pattern: the stream went silent for 60 s and
was cut, the retry two seconds later failed with a connection error in 15-18
s, and the third attempt returned. The writer and the reviewer each used all
three attempts; one more failure on either would have failed the run.

Two things follow. A retry that reuses the connection pool of the attempt that
just died is a retry on the connection that just died: the SDK client is
rebuilt before a transport retry, so the resend opens a new connection. And a
streamed attempt that fails costs at most its per-chunk bound, about a minute,
where a plain attempt cost its whole window; a streamed call can therefore
afford more attempts before the run gives up on it.

The stubs here implement what the CrewAI 1.14.7 OpenAI provider exposes:
``_client`` (an ``openai.OpenAI``) and ``_build_sync_client()``, which builds
a new one from the provider's current fields. One class uses the real provider
and SDK, with no network, to pin the fact the rebuild rests on: the SDK's
``with_options`` copies the client but shares its HTTP pool.
"""

from __future__ import annotations

import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from academic_agent.llm_config import (
    _MAX_ATTEMPTS,
    _STREAM_MAX_ATTEMPTS,
    RunDeadlineExceeded,
    _max_attempts_for,
    _set_transport_timeout,
    _wrap_with_retry,
    configure_llm_deadline,
    set_attempt_observer,
)


class _Client:
    """What the wrapper touches on an openai.OpenAI client."""

    def __init__(self, timeout):
        self.timeout = timeout
        self.closed = False

    def with_options(self, *, timeout):
        return _Client(timeout)

    def close(self):
        self.closed = True


class _Provider:
    """The CrewAI provider's surface: fields, a client, and the method that rebuilds it."""

    def __init__(self, side_effect=None, return_value="answer", *, stream=False):
        self.base_url, self.model = "https://example.test/v1", "model-x"
        self.timeout = 60.0 if stream else 150.0
        self.stream = stream
        self._client = _Client(self.timeout)
        self.additional_params = {}
        self.response_format = None
        self.temperature = 0.0
        self.builds = 0
        # _wrap_with_retry replaces .call with the wrapper; `inner` keeps the
        # provider-level mock so its call count can still be read.
        self.inner = self.call = MagicMock(side_effect=side_effect, return_value=return_value)

    def _build_sync_client(self):
        self.builds += 1
        return _Client(self.timeout)


def _fail_then_answer(failures: list[BaseException]):
    """A call that raises each listed error in turn, then answers."""
    queue = list(failures)

    def call(*args, **kwargs):
        if queue:
            raise queue.pop(0)
        return "answer"

    return call


class ReconnectBeforeRetryTests(unittest.TestCase):

    def setUp(self):
        patcher = patch("academic_agent.llm_config.time.sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_transport_failure_is_retried_on_a_new_client_and_the_old_one_is_closed(self):
        """The retry two seconds after a cut stream failed in 15-18 s with a
        connection error, three times in one run: the pool it reused held the
        connection that had just died."""
        provider = _Provider(side_effect=_fail_then_answer([TimeoutError("Request timed out.")]))
        first_client = provider._client
        llm = _wrap_with_retry(provider)

        self.assertEqual(llm.call("prompt"), "answer")

        self.assertEqual(provider.builds, 1)
        self.assertIsNot(provider._client, first_client)
        self.assertTrue(first_client.closed, "the dead pool must be released, not kept open")
        self.assertEqual(provider.inner.call_count, 2)

    def test_every_transport_retry_gets_its_own_client(self):
        provider = _Provider(side_effect=_fail_then_answer([
            TimeoutError("Request timed out."),
            ConnectionError("Connection error."),
        ]))
        llm = _wrap_with_retry(provider)

        self.assertEqual(llm.call("prompt"), "answer")
        self.assertEqual(provider.builds, 2)

    def test_the_rebuilt_client_keeps_the_window_the_stage_was_given(self):
        """configure_llm_deadline widened the writer's window to 300 s; a
        rebuild from the provider's fields must not fall back to the default."""
        provider = _Provider(side_effect=_fail_then_answer([ConnectionError("Connection error.")]))
        llm = _wrap_with_retry(provider)
        configure_llm_deadline(llm, deadline_monotonic=None, stage="writer", request_timeout_seconds=300)

        llm.call("prompt")

        self.assertEqual((provider.timeout, provider._client.timeout), (300.0, 300.0))

    def test_a_rejected_request_is_not_retried_and_keeps_its_client(self):
        """401 is not a connection problem; nothing is rebuilt, nothing is closed."""
        provider = _Provider(side_effect=RuntimeError("401 Unauthorized"))
        first_client = provider._client
        llm = _wrap_with_retry(provider)

        with self.assertRaises(RuntimeError):
            llm.call("prompt")

        self.assertEqual(provider.builds, 0)
        self.assertIs(provider._client, first_client)
        self.assertFalse(first_client.closed)

    def test_a_refused_parameter_is_resent_on_the_same_client(self):
        """The provider answered and billed nothing: the connection is fine,
        and the adapted resend is not a transport retry."""
        provider = _Provider(side_effect=_fail_then_answer([
            RuntimeError("400 Bad Request: parameter.enable_thinking must be set to false"),
        ]))
        first_client = provider._client
        with patch("academic_agent.llm_config.parameter_fallback.learned", return_value={}), \
                patch("academic_agent.llm_config.parameter_fallback.learn"), \
                patch("academic_agent.llm_config.parameter_fallback.adjustment",
                      return_value=("enable_thinking", False)):
            llm = _wrap_with_retry(provider)
            self.assertEqual(llm.call("prompt"), "answer")

        self.assertEqual(provider.builds, 0)
        self.assertIs(provider._client, first_client)

    def test_a_provider_that_cannot_rebuild_still_retries(self):
        """The wrapper also wraps stand-ins and other providers; a missing
        _build_sync_client is not a reason to drop the retry."""
        stub = MagicMock(spec=["call", "base_url", "model"])
        stub.base_url, stub.model = "https://example.test/v1", "model-x"
        inner = stub.call = MagicMock(side_effect=_fail_then_answer([ConnectionError("Connection error.")]))
        llm = _wrap_with_retry(stub)

        self.assertEqual(llm.call("prompt"), "answer")
        self.assertEqual(inner.call_count, 2)

    def test_a_rebuild_that_fails_is_noted_on_stderr_and_the_retry_goes_ahead_on_the_old_client(self):
        provider = _Provider(side_effect=_fail_then_answer([ConnectionError("Connection error.")]))
        first_client = provider._client
        provider._build_sync_client = MagicMock(side_effect=ValueError("OPENAI_API_KEY is required"))
        llm = _wrap_with_retry(provider)

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(llm.call("prompt"), "answer")

        self.assertIs(provider._client, first_client)
        self.assertFalse(first_client.closed)
        self.assertIn("ValueError", err.getvalue())
        self.assertIn("kept", err.getvalue())

    def test_the_notice_says_the_retry_opens_a_new_connection(self):
        provider = _Provider(side_effect=_fail_then_answer([ConnectionError("Connection error.")]))
        llm = _wrap_with_retry(provider)

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            llm.call("prompt")

        self.assertIn("new connection", err.getvalue())


class RealProviderRebuildTests(unittest.TestCase):
    """Against the vendored CrewAI provider and OpenAI SDK, no network."""

    def _llm(self):
        from crewai import LLM

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            return LLM(provider="openai", api_key="sk-test", model="model-x",
                       base_url="https://example.test/v1", stream=True,
                       timeout=60.0, max_retries=0)

    def test_with_options_shares_the_http_pool_and_a_rebuild_does_not(self):
        """The reason the wrapper rebuilds instead of copying."""
        llm = self._llm()
        original = llm._client

        copied = original.with_options(timeout=300.0)
        self.assertIs(copied._client, original._client, "with_options shares the httpx client")

        rebuilt = llm._build_sync_client()
        self.addCleanup(rebuilt.close)
        self.assertIsNot(rebuilt._client, original._client, "a rebuild opens a new pool")

    def test_a_rebuild_carries_the_window_and_the_no_retry_setting(self):
        llm = self._llm()
        _set_transport_timeout(llm, 300.0)

        rebuilt = llm._build_sync_client()
        self.addCleanup(rebuilt.close)

        self.assertEqual((rebuilt.timeout, rebuilt.max_retries), (300.0, 0))
        self.assertEqual(str(rebuilt.base_url).rstrip("/"), "https://example.test/v1")

    def test_a_streaming_provider_gets_the_streamed_attempt_cap(self):
        self.assertEqual(_max_attempts_for(self._llm()), _STREAM_MAX_ATTEMPTS)


class StreamedAttemptCapTests(unittest.TestCase):

    def setUp(self):
        patcher = patch("academic_agent.llm_config.time.sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)
        self.records = []
        self.addCleanup(set_attempt_observer, set_attempt_observer(self.records.append))

    def test_the_streamed_cap_is_higher_than_the_plain_one(self):
        """A failed streamed attempt costs its per-chunk bound, a plain one
        its whole window; the streamed call can afford more of them."""
        self.assertGreater(_STREAM_MAX_ATTEMPTS, _MAX_ATTEMPTS)
        self.assertEqual(_STREAM_MAX_ATTEMPTS, 5)

    def test_a_streamed_node_gets_the_higher_cap_and_a_plain_node_the_old_one(self):
        self.assertEqual(_max_attempts_for(_Provider(stream=True)), _STREAM_MAX_ATTEMPTS)
        self.assertEqual(_max_attempts_for(_Provider(stream=False)), _MAX_ATTEMPTS)
        self.assertEqual(_max_attempts_for(MagicMock(spec=["call"])), _MAX_ATTEMPTS)

    def test_a_streamed_node_survives_four_cut_streams(self):
        """2026-11-09: writer and reviewer each used all three attempts."""
        provider = _Provider(stream=True, side_effect=_fail_then_answer(
            [TimeoutError("Request timed out.")] * 4))
        llm = _wrap_with_retry(provider)

        self.assertEqual(llm.call("prompt"), "answer")

        self.assertEqual(provider.inner.call_count, 5)
        self.assertEqual([r["attempt"] for r in self.records], [1, 2, 3, 4, 5])
        self.assertEqual(self.records[-1]["outcome"], "returned")

    def test_a_streamed_node_gives_up_after_its_cap(self):
        provider = _Provider(stream=True, side_effect=TimeoutError("Request timed out."))
        llm = _wrap_with_retry(provider)

        with self.assertRaises(TimeoutError):
            llm.call("prompt")

        self.assertEqual(provider.inner.call_count, _STREAM_MAX_ATTEMPTS)
        self.assertEqual([r["retry"] for r in self.records], [True, True, True, True, False])

    def test_a_plain_node_still_gives_up_after_three(self):
        provider = _Provider(stream=False, side_effect=TimeoutError("Request timed out."))
        llm = _wrap_with_retry(provider)

        with self.assertRaises(TimeoutError):
            llm.call("prompt")

        self.assertEqual(provider.inner.call_count, _MAX_ATTEMPTS)

    def test_backoff_keeps_growing_through_the_extra_attempts(self):
        provider = _Provider(stream=True, side_effect=ConnectionError("Connection error."))
        llm = _wrap_with_retry(provider)

        with self.assertRaises(ConnectionError):
            llm.call("prompt")

        delays = [c.args[0] for c in self.sleep.call_args_list]
        self.assertEqual(len(delays), _STREAM_MAX_ATTEMPTS - 1)
        self.assertEqual(delays, sorted(delays))
        self.assertLess(delays[-1], 25.0, "the longest backoff before the fifth attempt stays under half a minute")

    def test_the_notice_names_the_streamed_cap(self):
        provider = _Provider(stream=True, side_effect=_fail_then_answer([ConnectionError("Connection error.")]))
        llm = _wrap_with_retry(provider)

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            llm.call("prompt")

        self.assertIn(f"attempt 1/{_STREAM_MAX_ATTEMPTS}", err.getvalue())

    @patch("academic_agent.llm_config.time.monotonic")
    def test_the_extra_attempts_still_need_a_full_window_each(self, monotonic):
        """More attempts never add time back: the fourth is refused when the
        stage's remaining window no longer holds backoff plus one attempt."""
        clock = [0.0]
        monotonic.side_effect = lambda: clock[0]

        def failing(*args, **kwargs):
            clock[0] += 55.0
            raise ConnectionError("Connection error.")

        provider = _Provider(stream=True, side_effect=failing)
        llm = _wrap_with_retry(provider)
        # Three attempts of 55 s fit before 230 s; after the third failure the
        # backoff (8 s plus jitter) and a 60-s window no longer do.
        configure_llm_deadline(llm, deadline_monotonic=230.0, stage="writer", request_timeout_seconds=60)

        with self.assertRaises(RunDeadlineExceeded):
            llm.call("prompt")

        self.assertEqual(provider.inner.call_count, 3)
        self.assertEqual(self.records[-1]["retry"], False)


if __name__ == "__main__":
    unittest.main()
