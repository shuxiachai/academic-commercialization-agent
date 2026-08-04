"""Shared test fixtures and global safety nets.

The autouse fixture below is a guard, not a convenience. ``collect_source_collection``
calls ``generate_synonyms`` unconditionally and ``translate_to_english`` for any
non-English topic, both of which reach the *paid* LLM endpoint. They swallow
failures and fall back to the original text, so a test that triggers them looks
like it passes either way — but on a machine with network and a valid key it
really does spend credit, and in CI it just adds latency and flakiness.

Stubbing the single choke point (`_llm_call`) means a newly added test cannot
reintroduce the leak by forgetting to patch anything.

The stub returns "" rather than raising, because that is exactly what the real
function returns when the endpoint is unreachable. Every caller already has a
documented fallback for that case, so tests exercise the same degraded path
they would hit in an offline environment — which is worth covering anyway.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def stub_llm_calls(monkeypatch, request):
    """Replace language._llm_call with an offline stub for every test.

    Yields a list that records (prompt, system) for each attempted call, so a
    test can assert on whether translation was requested:

        def test_x(stub_llm_calls):
            ...
            assert len(stub_llm_calls) == 1

    Opt out with @pytest.mark.allow_llm when exercising _llm_call itself.
    """
    calls: list[tuple[str, str]] = []

    if request.node.get_closest_marker("allow_llm"):
        yield calls
        return

    def _offline(prompt: str, *, system: str = "", **_kwargs) -> str:
        calls.append((prompt, system))
        return ""       # same as the real function when the endpoint is down

    monkeypatch.setattr("academic_agent.language._llm_call", _offline)
    yield calls


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "allow_llm: test exercises language._llm_call itself and bypasses the "
        "offline stub (it must still stub the HTTP transport)",
    )
