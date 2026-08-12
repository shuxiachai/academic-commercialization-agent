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

The second autouse fixture guards a subtler leak: api/access.py reads
ACCESS_CODE/ACCESS_CODES/ACCESS_CODE_ADMIN from os.environ at *import* time,
and api/main.py's load_dotenv() call is what actually puts .env's real
values into os.environ before that happens — but only if api.main gets
imported before api.access does. Python caches modules, so whichever test
file's import statements happen to touch api.access first for a given
pytest process permanently decides whether the real deployment's access
codes leak into every other test in that run. That is exactly how
test_api.py went from "always passes" to "fails in isolation, passes only
when collected after test_access_gate.py" the moment .env picked up a real
ACCESS_CODE for Railway testing — collection order was doing the isolating,
by accident, not any test's own setup.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def no_real_access_codes(monkeypatch):
    """Pin every access-code global to None before each test.

    Importing api.access here guarantees it is already in sys.modules by
    the time any test file's own imports run, so no test's outcome depends
    on import order. A test that wants a real gate still patches these
    itself, same as always — this only fixes the *default*.
    """
    from api import access

    monkeypatch.setattr(access, "ACCESS_CODE", None)
    monkeypatch.setattr(access, "ACCESS_CODES", None)
    monkeypatch.setattr(access, "ADMIN_CODE", None)


@pytest.fixture(autouse=True)
def empty_rate_limit_buckets():
    """Give every test a fresh request budget.

    The limiter is process-global and keyed by client, and TestClient presents
    the same client for the whole session — so without this the suite spends
    one shared budget across every HTTP test it runs. It fits today, which is
    the problem: the margin shrinks silently with each test added, and the
    failure it eventually produces is a 429 in whichever test happens to run
    last, nowhere near the change that caused it.

    The limiter's own behaviour is covered deliberately in test_api.py rather
    than left to accumulate here.
    """
    from api import main

    main._rate_buckets.clear()
    yield
    main._rate_buckets.clear()


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
