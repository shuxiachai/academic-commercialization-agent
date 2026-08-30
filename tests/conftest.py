"""Shared test fixtures and global safety nets.

The autouse fixture below is a guard, not a convenience. ``collect_source_collection``
calls ``plan_topic_search`` unconditionally. Its malformed-response fallback can
also call ``translate_to_english`` for non-English input. Both paths reach the
*paid* LLM endpoint but deliberately fall back to deterministic text on failure,
so a test that triggers either path looks
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


_LLM_ENVIRONMENT = (
    "LLM_PROVIDER",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_API_BASE",
    "DEEPSEEK_MODEL",
    "MOONSHOT_API_KEY",
    "KIMI_API_BASE",
    "KIMI_MODEL",
    "KIMI_REASONING_EFFORT",
    "OPENAI_API_KEY",
    "OPENAI_API_BASE",
    "OPENAI_MODEL",
    "OPENAI_MODEL_NAME",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_API_BASE",
    "ANTHROPIC_MODEL",
)


@pytest.fixture(autouse=True)
def no_real_llm_configuration(monkeypatch):
    """Keep the developer's paid-provider configuration out of every test.

    api.main deliberately loads .env, while many provider unit tests extend
    rather than replace os.environ so HOME and other process settings survive.
    Once a real Kimi provider was configured, that combination made unrelated
    DeepSeek/OpenAI tests resolve Kimi and fail depending on collection order.
    Deleting every provider selector and credential here gives tests a neutral
    baseline; a test still opts into exactly the provider values it needs.
    """

    for name in _LLM_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)


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
