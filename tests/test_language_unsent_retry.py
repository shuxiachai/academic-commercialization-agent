"""The language helper resends a request that never finished sending, and nothing else."""

from __future__ import annotations

import io
import json
import ssl
from contextlib import contextmanager
from http.client import RemoteDisconnected
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

from academic_agent import auxiliary_usage as aux
from academic_agent import language, llm_config
from academic_agent import llm_parameter_fallback as fallback

TOPIC = "perovskite solar cells for building-integrated photovoltaics"
PLAN = ("SEARCH_TOPIC: perovskite solar cells for building-integrated photovoltaics\n"
        "ALIAS: building-integrated perovskite solar cells\n"
        "ALIAS: perovskite photovoltaics for building integration")
USAGE = {"prompt_tokens": 399, "completion_tokens": 981, "total_tokens": 1380}
# qwen3.7-max-preview's answer to enable_thinking=false, as DashScope sent it on 2026-10-23.
THINKING_ONLY = {"error": {"message": "<400> InternalError.Algo.InvalidParameter: The value of the "
                                      "enable_thinking parameter is restricted to True.",
                           "type": "invalid_request_error", "code": "invalid_parameter_error"}}


def http_error(code: int, body: dict) -> HTTPError:
    return HTTPError("https://provider.invalid/v1/chat/completions", code, "error", {},
                     io.BytesIO(json.dumps(body).encode()))


# What urllib raised for two of three planner calls from a local machine on 2026-10-23.
def reset() -> URLError:
    return URLError(ConnectionResetError(10054, "PRIVATE socket detail"))


def tls_cut() -> URLError:
    return URLError(ssl.SSLEOFError(8, "EOF occurred in violation of protocol"))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """A thinking-only Qwen deployment and a clock that does not wait."""
    fallback.reset()
    monkeypatch.setattr(llm_config, "resolve_provider_config", lambda: llm_config.ProviderConfig(
        "qwen", "qwen3.7-max-preview", "https://provider.invalid/v1", "offline-key"))
    slept: list[float] = []
    monkeypatch.setattr(language.time, "sleep", slept.append)
    yield slept
    fallback.reset()


def transport(monkeypatch, *outcomes):
    """Answer each request with the next outcome: an exception to raise, or reply text."""
    sent: list[dict] = []
    queue = list(outcomes)

    @contextmanager
    def urlopen(request, *, timeout):
        sent.append(json.loads(request.data))
        outcome = queue.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        yield SimpleNamespace(read=lambda: json.dumps(
            {"usage": USAGE, "choices": [{"message": {"content": outcome}}]}).encode())

    monkeypatch.setattr(language, "urlopen", urlopen)
    return sent


@pytest.mark.allow_llm
def test_a_reset_before_the_thinking_refusal_no_longer_costs_the_plan(monkeypatch, offline, tmp_path, capsys):
    """The production failure of 2026-10-23.

    The first request died while connecting. The helper made one attempt, so
    the parameter adaptation for the thinking-only model never ran. The run
    searched the typed topic with no alias query, and the plan preview showed
    that echo as the planner's reading.
    """
    sent = transport(monkeypatch, reset(), http_error(400, THINKING_ONLY), PLAN)
    collector = aux.Collector(tmp_path / aux.FILE_NAME)
    with aux.bind(collector):
        plan = language.plan_topic_search(TOPIC)
    collector.finish()

    assert plan.aliases == ("building-integrated perovskite solar cells",
                            "perovskite photovoltaics for building integration")
    assert [body["enable_thinking"] for body in sent] == [False, False, True]
    assert offline == [1.0]
    # Every attempt is in the ledger, failed ones included; none is hidden as a retry.
    summary = collector.summary()
    assert [call["outcome"] for call in summary["calls"]] == ["call_failed", "call_failed", "returned"]
    assert summary["provider_attempt_count"] == 3
    out = capsys.readouterr().out
    assert "[llm] search_planning: ConnectionResetError before the request was sent (attempt 1/3)" in out
    assert "PRIVATE" not in out and "offline-key" not in out


@pytest.mark.allow_llm
def test_a_connection_that_never_opens_is_tried_three_times_then_falls_back_visibly(monkeypatch, offline):
    sent = transport(monkeypatch, reset(), tls_cut(), reset())
    with pytest.warns(UserWarning, match=r"language\._llm_call failed \(URLError\)"):
        plan = language.plan_topic_search(TOPIC)
    assert len(sent) == 3
    assert offline == [1.0, 2.0]
    assert plan.search_topic == TOPIC and plan.aliases == ()


@pytest.mark.allow_llm
@pytest.mark.parametrize("failure", [
    TimeoutError("The read operation timed out"),
    RemoteDisconnected("Remote end closed connection without response"),
    ConnectionResetError(10054, "reset while reading the reply"),
    http_error(500, {"error": {"message": "internal error"}}),
    http_error(429, {"error": {"message": "rate limit"}}),
], ids=["read-timeout", "reply-dropped", "reset-while-reading", "http-500", "http-429"])
def test_a_request_that_was_sent_is_not_sent_again(monkeypatch, offline, failure):
    """After the request has left, the model may be working on it: a resend could bill it twice."""
    sent = transport(monkeypatch, failure, PLAN)
    with pytest.warns(UserWarning, match="falling back to original text"):
        assert language._llm_call("plan this", system="s", stage="search_planning") == ""
    assert len(sent) == 1
    assert offline == []
