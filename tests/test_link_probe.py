"""The provider-link probe: what the production host can say about its own path.

2026-11-09: a production run on streamed calls had the writer's request fail
on eight fresh connections in a row, each silent for 60 seconds, while the
same 22,000-token request from the maintainer's machine, outside the host's
network, got its first chunk in 6.9 seconds. The three evidence agents' smaller requests mostly got
through. Everything pointed at the path from the host (Railway, Singapore) to
dashscope.aliyuncs.com, and nothing could be measured from there: the shell
is not reachable from here and the worker's attempt rows say only "no chunk
in 60 seconds".

The probe measures from the host. It posts a 1 KB and a 100 KB chat request
with no key to the configured endpoint and, for Bailian, to its sibling on
the other side of the border; both servers read the whole body before they
answer 401, so the time to that answer is the time the path takes to carry a
writer-sized request. Nothing is billed, no key is sent, no host comes from
the caller.
"""

from __future__ import annotations

import json
import threading
import unittest
from unittest.mock import patch

import httpx

from api import link_probe

_BEIJING = {"DASHSCOPE_API_KEY": "sk-test", "QWEN_MODEL": "m",
            "QWEN_API_BASE": "https://dashscope.aliyuncs.com/compatible-mode/v1"}
_CLEAR = {name: "" for name in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY",
                                "DASHSCOPE_API_KEY", "LLM_PROVIDER", "OPENAI_API_BASE", "OPENAI_MODEL_NAME")}


def _env(**values):
    return patch.dict("os.environ", {**_CLEAR, **values})


class TargetTests(unittest.TestCase):

    def test_bailian_mainland_is_probed_beside_its_international_sibling(self):
        with _env(**_BEIJING):
            found = link_probe.targets()
        self.assertEqual([(t.name, t.url) for t in found], [
            ("configured", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"),
            ("intl", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"),
        ])
        self.assertEqual([t.host for t in found], ["dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com"])

    def test_bailian_international_is_probed_beside_the_mainland_host(self):
        with _env(**{**_BEIJING, "QWEN_API_BASE": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"}):
            names = [(t.name, t.host) for t in link_probe.targets()]
        self.assertEqual(names, [("configured", "dashscope-intl.aliyuncs.com"), ("mainland", "dashscope.aliyuncs.com")])

    def test_another_provider_has_only_its_own_endpoint(self):
        with _env(OPENAI_API_KEY="sk-o", OPENAI_MODEL="gpt-x", LLM_PROVIDER="openai"):
            found = link_probe.targets()
        self.assertEqual([(t.name, t.url) for t in found], [("configured", "https://api.openai.com/v1/chat/completions")])

    def test_anthropic_is_asked_on_its_messages_path(self):
        with _env(ANTHROPIC_API_KEY="sk-a", ANTHROPIC_MODEL="claude-x", LLM_PROVIDER="anthropic"):
            found = link_probe.targets()
        self.assertEqual(found[0].url, "https://api.anthropic.com/v1/messages")

    def test_without_a_configured_provider_there_is_nothing_to_probe(self):
        with _env():
            with self.assertRaises(link_probe.NoEndpoint):
                link_probe.targets()

    def test_targets_never_carry_the_key(self):
        with _env(**_BEIJING):
            for target in link_probe.targets():
                self.assertNotIn("sk-test", target.url)
                self.assertNotIn("sk-test", repr(target))


class ReadingTests(unittest.TestCase):
    """Timings are milliseconds since the request started, as a timeline."""

    def test_each_mark_is_read_from_the_transport_trace(self):
        events = {
            "connection.connect_tcp.complete": 100.8,
            "connection.start_tls.complete": 101.1,
            "http11.send_request_body.complete": 101.9,
            "http11.receive_response_headers.complete": 102.2,
        }
        reading = link_probe.reading_from(events, started=100.0, finished=102.25, status=401, error=None, body_bytes=100_000)
        self.assertEqual(
            (reading.connect_ms, reading.tls_ms, reading.upload_ms, reading.first_byte_ms, reading.total_ms),
            (800, 1100, 1900, 2200, 2250),
        )
        self.assertEqual((reading.status, reading.error, reading.body_bytes), (401, None, 100_000))

    def test_a_mark_the_request_never_reached_is_null_not_zero(self):
        events = {"connection.connect_tcp.complete": 100.5, "connection.start_tls.complete": 100.7}
        reading = link_probe.reading_from(events, started=100.0, finished=130.7, status=None, error="WriteTimeout", body_bytes=100_000)
        self.assertEqual((reading.connect_ms, reading.tls_ms), (500, 700))
        self.assertIsNone(reading.upload_ms)
        self.assertIsNone(reading.first_byte_ms)
        self.assertEqual((reading.total_ms, reading.status, reading.error), (30700, None, "WriteTimeout"))


class ProbeOnceTests(unittest.TestCase):

    def setUp(self):
        self.requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return httpx.Response(401, json={"error": {"message": "You didn't provide an API key."}})

        self.transport = httpx.MockTransport(handler)
        self.target = link_probe.Target("configured", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")

    def test_the_request_is_a_chat_completion_of_the_asked_size_with_no_key(self):
        reading = link_probe.probe_once(self.target, 100_000, transport=self.transport)

        self.assertEqual(len(self.requests), 1)
        request = self.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertNotIn("authorization", {k.lower() for k in request.headers})
        self.assertEqual(request.headers["content-type"], "application/json")
        self.assertEqual(len(request.content), 100_000)
        body = json.loads(request.content)
        self.assertEqual(body["messages"][0]["role"], "user")
        self.assertEqual((reading.status, reading.error, reading.body_bytes), (401, None, 100_000))
        self.assertGreaterEqual(reading.total_ms, 0)

    def test_the_small_request_is_the_small_size(self):
        link_probe.probe_once(self.target, link_probe.SMALL_BYTES, transport=self.transport)
        self.assertEqual(len(self.requests[0].content), link_probe.SMALL_BYTES)

    def test_a_transport_failure_is_a_reading_not_an_exception(self):
        def dying(request):
            raise httpx.ReadTimeout("timed out", request=request)

        reading = link_probe.probe_once(self.target, 1_000, transport=httpx.MockTransport(dying))
        self.assertEqual((reading.status, reading.error), (None, "ReadTimeout"))

    def test_the_timeout_matches_the_bound_given(self):
        seen = {}

        def handler(request):
            seen["timeout"] = request.extensions.get("timeout")
            return httpx.Response(401)

        link_probe.probe_once(self.target, 1_000, timeout=7, transport=httpx.MockTransport(handler))
        self.assertEqual(seen["timeout"], {"connect": 7.0, "read": 7.0, "write": 7.0, "pool": 7.0})


class RunTests(unittest.TestCase):

    def test_a_run_reads_both_sizes_on_every_target_small_first(self):
        calls = []

        def fake_probe(target, size, *, timeout, transport=None):
            calls.append((target.name, size))
            return link_probe.Reading(body_bytes=size, total_ms=1, status=401)

        with _env(**_BEIJING), patch.object(link_probe, "probe_once", fake_probe):
            answer = link_probe.run()

        self.assertEqual(sorted({name for name, _ in calls}), ["configured", "intl"])
        for name in ("configured", "intl"):
            sizes = [size for n, size in calls if n == name]
            self.assertEqual(sizes, [1_000, 10_000, 30_000, 100_000, 100_000],
                             "the small body, the two steps between, then the writer-sized one twice")
        self.assertEqual([t["name"] for t in answer["targets"]], ["configured", "intl"])
        self.assertEqual(answer["targets"][0]["host"], "dashscope.aliyuncs.com")
        self.assertEqual(len(answer["targets"][0]["readings"]), 5)
        self.assertEqual(answer["sizes"], [1_000, 10_000, 30_000, 100_000])
        self.assertEqual(answer["timeout_seconds"], link_probe.TIMEOUT_SECONDS)
        self.assertEqual((answer["small_bytes"], answer["large_bytes"]), (link_probe.SMALL_BYTES, link_probe.LARGE_BYTES))
        self.assertRegex(answer["taken_at"], r"^\d{4}-\d{2}-\d{2}T")
        self.assertEqual(answer["targets"][0]["readings"][0]["status"], 401)

    def test_the_writer_sized_body_is_the_size_of_the_writer_request(self):
        """2026-11-09: 22,010 prompt tokens, about 100 KB on the wire."""
        self.assertEqual(link_probe.LARGE_BYTES, 100_000)
        self.assertEqual(link_probe.SMALL_BYTES, 1_000)

    def test_two_steps_between_find_where_the_path_starts_to_choke(self):
        """From the production host on 2026-11-09 09:08 UTC: 1 KB in 0.75 s, 100 KB
        uploaded in 25.7 s and then not at all. Whether a smaller writer request
        would pass needs readings in between, the evidence agents' size (about
        30 KB, which mostly passed that afternoon) among them."""
        self.assertEqual(link_probe.SIZES, (1_000, 10_000, 30_000, 100_000))
        self.assertEqual(link_probe._READINGS, ((1_000, 1), (10_000, 1), (30_000, 1), (100_000, 2)))

    def test_the_bound_is_half_the_per_chunk_bound_a_production_attempt_gets(self):
        """A 100 KB upload that needs more than 30 s has already failed the
        writer, whose first chunk must arrive within 60; the console answer
        stays under three minutes with every size on both hosts."""
        self.assertEqual(link_probe.TIMEOUT_SECONDS, 30)

    def test_one_probe_at_a_time(self):
        with _env(**_BEIJING), link_probe._running:
            with self.assertRaises(link_probe.Busy):
                link_probe.run()

    def test_the_targets_are_probed_in_parallel(self):
        """Serial, two hosts with a dead path would take four minutes."""
        active, peak, lock = [0], [0], threading.Lock()
        release = threading.Event()

        def fake_probe(target, size, *, timeout, transport=None):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            release.wait(2.0)
            with lock:
                active[0] -= 1
            return link_probe.Reading(body_bytes=size, total_ms=1, status=401)

        with _env(**_BEIJING), patch.object(link_probe, "probe_once", fake_probe):
            timer = threading.Timer(0.3, release.set)
            timer.start()
            link_probe.run()
            timer.cancel()
        self.assertEqual(peak[0], 2)


if __name__ == "__main__":
    unittest.main()
