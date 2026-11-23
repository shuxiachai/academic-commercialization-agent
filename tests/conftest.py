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

import json
import os
import sys
from pathlib import Path

import pytest

# CrewAI reports anonymous usage to telemetry.crewai.com. Its Telemetry object
# starts a background thread that posts what it has gathered every few
# seconds, and keeps retrying a post that failed. Nothing in the test process
# had turned that off, so on CI a test that built a crew left that thread
# posting during the tests that followed. It was found by an offline suite
# whose fixture fails on any connection (tests/test_report_evidence_claim_
# contrast.py): two CI runs on 2026-11-15 failed there, in two different
# tests, with CrewAI's own logger naming itself in the captured log. Whether
# it hit depended on which files shared a part and on timing, which is why
# it appeared when the parts were reshuffled by new tests and not before.
#
# Set before anything imports CrewAI: the Telemetry object reads the variable
# when it is first built and stays as it was built. The fixture below holds
# the other half, a test that clears the environment and builds one anyway.
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"

_EXPERIMENT_LIST = Path(__file__).with_name("experiment_tests.txt")

_LLM_ENVIRONMENT = (
    "LLM_PROVIDER",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_API_BASE",
    "DEEPSEEK_MODEL",
    "DASHSCOPE_API_KEY",
    "QWEN_API_BASE",
    "QWEN_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_API_BASE",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "OPENAI_MODEL_NAME",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_API_BASE",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
)


@pytest.fixture(autouse=True)
def no_real_llm_configuration(monkeypatch):
    """Keep the developer's paid-provider configuration out of every test.

    api.main deliberately loads .env, while many provider tests extend rather
    than replace os.environ so HOME and other process settings survive. Once a
    real Qwen provider is configured, that combination could make unrelated
    DeepSeek/OpenAI tests resolve Qwen depending on collection order. Deleting
    every provider selector and credential gives tests a neutral baseline; a
    test still opts into exactly the provider values it needs.
    """

    for name in _LLM_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)


def stop_crewai_telemetry(modules) -> bool:
    """Whether CrewAI's Telemetry was ready to send; it is switched off if so.

    Read from the modules already imported, never by importing: most tests
    load no CrewAI, and this runs after every one of them. ``ready`` is what
    CrewAI itself checks before it records anything.
    """
    module = modules.get("crewai.telemetry.telemetry")
    instance = getattr(getattr(module, "Telemetry", None), "_instance", None)
    if not getattr(instance, "ready", False):
        return False
    instance.ready = False
    return True


@pytest.fixture(autouse=True)
def no_crewai_telemetry(monkeypatch):
    """No test may leave CrewAI's telemetry running, and one that does is named.

    The variable is restored for every test, in case one before it removed
    it. Afterwards, if CrewAI's Telemetry object exists and is ready to send,
    this test built it with the variable cleared (``patch.dict(os.environ,
    ..., clear=True)`` does that): it is switched off again, so the tests
    after this one are not blamed for it, and this test fails.
    """
    monkeypatch.setenv("CREWAI_DISABLE_TELEMETRY", "true")
    yield
    if stop_crewai_telemetry(sys.modules):
        pytest.fail("This test built CrewAI's Telemetry with CREWAI_DISABLE_TELEMETRY cleared; "
                    "its background thread would post to telemetry.crewai.com during later tests. "
                    "Keep the variable in the environment the test builds.")


@pytest.fixture(autouse=True)
def no_real_arxiv_lookup(monkeypatch):
    """Keep the uploaded-paper title lookup off the network in every test.

    extract_paper_contribution asks arXiv for the title whenever the text
    carries no identifier, which is what most test PDFs look like, and a
    lookup that cannot run degrades to "unavailable" rather than failing. So
    an unpatched test would pass offline, and online would send a real
    request per extraction. Refusing at the single fetch seam makes that
    path deterministic; a test of the lookup itself patches the seam or
    passes title_lookup.
    """
    from academic_agent import pdf_extractor

    def refuse(query, *, timeout):
        raise OSError("tests do not reach arXiv; patch _fetch_arxiv_feed or pass title_lookup")

    monkeypatch.setattr(pdf_extractor, "_fetch_arxiv_feed", refuse)


@pytest.fixture(autouse=True)
def no_real_runtime_limits(monkeypatch):
    """Do not let import-time .env caps decide which isolated tests get 429.

    The complete suite imported runs before dotenv by accident; a focused
    provider/PDF run reversed that order and inherited the real daily cap.
    Tests of admission override these values explicitly after this fixture.
    """
    from api import runs

    monkeypatch.setattr(runs, "DAILY_CAP", 0)
    monkeypatch.setattr(runs, "MAX_CONCURRENT", 2)
    monkeypatch.setattr(runs, "BYOK_MAX_CONCURRENT", None)
    monkeypatch.setattr(runs, "RUN_RETENTION_DAYS", 0)


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


@pytest.fixture(autouse=True)
def no_real_page_fetches(monkeypatch, request):
    """Read no web page for a publication date or a patent applicant unless a test asks to.

    collect_source_collection dates each accepted market source from its own
    page through page_dates.fetch_html, and names each web-search patent's
    applicant through patent_applicants.fetch_head. Stubbing those choke
    points, as stub_llm_calls does for the LLM, means a new collector test
    cannot send real requests by forgetting to inject a lookup. The stubs
    return None, as the real functions do for a page they cannot read.

    Opt out with @pytest.mark.allow_page_fetch when exercising a fetch itself.
    """
    if request.node.get_closest_marker("allow_page_fetch"):
        return
    monkeypatch.setattr("academic_agent.page_dates.fetch_html", lambda _url: None)
    monkeypatch.setattr("academic_agent.patent_applicants.fetch_head", lambda _url: None)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "allow_llm: test exercises language._llm_call itself and bypasses the "
        "offline stub (it must still stub the HTTP transport)",
    )
    config.addinivalue_line(
        "markers",
        "allow_page_fetch: test exercises page_dates.fetch_html or patent_applicants.fetch_head "
        "itself and bypasses the offline stubs (it must still stub the opener)",
    )
    config.addinivalue_line(
        "markers",
        "experiment: test of a closed experiment, audit or probe that neither the app nor "
        "the pipeline imports (listed in tests/experiment_tests.txt; applied automatically)",
    )
    # A pull request's cells are split over several runners; see below. The
    # setting is taken out of the environment as it is read: several tests
    # start a pytest of their own, and a child that inherited it would
    # quietly collect a fraction of what its test expects.
    shard = parse_shard(os.environ.pop(_SHARD_ENV, None))
    times = parse_times(os.environ.pop(_TIMES_ENV, None))
    config.pluginmanager.register(_Sharding(shard, times), "aca-test-sharding")


# ── A cell's tests, split over several runners ─────────────────────────────
#
# Measured 2026-11-11: a pull request waited 11 to 13 minutes, set by the cell
# that runs every test under coverage (630 s of pytest for 8,654 tests) with
# the Windows cells behind it (436 s for 4,738). The slowest single test took
# 5.8 s and installing 13 to 32 s: the time is the number of tests. Running
# them in parallel inside one runner (#228) made about half the runs fail a
# timing-sensitive concurrency test. So a cell is split by test file, and
# each part still runs serially on a runner of its own.
#
# ACA_TEST_SHARD="2/5" keeps the second of five parts and deselects the
# rest. Unset, as it is locally and in the weekly workflow, nothing changes.
#
# The parts were first balanced by number of tests. Measured on CI on
# 2026-11-23, tests are nowhere near equal in time: on the coverage cell the
# closed-experiment canary files take about 0.25 s a test and most files under
# 0.01 s, so the slowest of three parts ran 280 s against 187 s for the
# fastest, and the run waited on it. The parts are now balanced by how long
# each file took on CI, read from ci_test_durations.json (one table per runner
# OS, rewritten by scripts/ci_test_durations.py from a few green runs). A file
# the table does not list yet is estimated from its number of tests at the
# table's average rate. The table decides only which runner runs a file,
# never whether it runs: a missing, stale or unreadable table leaves the parts
# a partition, only a less even one, and the run's header says which basis
# the split used.
#
# The runner's OS picks the table, so the same part differs between Linux and
# Windows. ACA_TEST_SHARD_TIMES=linux (or windows) picks it instead, which is
# how a part of a Linux cell is reproduced on a Windows machine.
_SHARD_ENV = "ACA_TEST_SHARD"
_TIMES_ENV = "ACA_TEST_SHARD_TIMES"
_MAX_SHARDS = 16
_DURATIONS = Path(__file__).with_name("ci_test_durations.json")
_SYSTEMS = ("linux", "windows")


def parse_shard(raw: str | None) -> tuple[int, int] | None:
    """(part, parts) from "part/parts"; None when unset. Anything else is refused.

    A typo must not become "run nothing" or "run everything" under a green
    tick, so there is no lenient reading.
    """
    if raw is None or not raw.strip():
        return None
    pieces = raw.strip().split("/")
    if len(pieces) == 2 and all(piece.isdigit() for piece in pieces):
        part, parts = int(pieces[0]), int(pieces[1])
        if 1 <= part <= parts <= _MAX_SHARDS:
            return part, parts
    raise pytest.UsageError(
        f"{_SHARD_ENV}={raw!r} is not a part of a number: write it as 2/3, "
        f"with the part between 1 and the number and the number at most {_MAX_SHARDS}."
    )


def parse_times(raw: str | None, platform: str = sys.platform) -> str:
    """Whose measured times balance the parts: this machine's OS unless the variable names one.

    Refused, not guessed, when it names anything else: a typo would silently
    give a different split from the one being reproduced.
    """
    if raw is None or not raw.strip():
        return "windows" if platform == "win32" else "linux"
    if raw.strip() in _SYSTEMS:
        return raw.strip()
    raise pytest.UsageError(f"{_TIMES_ENV}={raw!r} names no table: write linux or windows, or leave it unset.")


def duration_table(system: str, path: Path = _DURATIONS) -> dict[str, float]:
    """Seconds per test file measured on CI on one OS; empty when there is no usable table.

    Every part of a cell runs on the same OS from the same commit, so every
    part reads the same table. A table that cannot be read is not an error
    here (balance is all it affects); tests/test_ci_sharding.py holds that
    the committed one is readable.
    """
    try:
        table = json.loads(path.read_text(encoding="utf-8"))[system]
        return {str(name): float(seconds) for name, seconds in table.items() if 0 <= float(seconds) < float("inf")}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def shard_weights(counts: dict[str, int], table: dict[str, float]) -> dict[str, int]:
    """How long each file is expected to take, in whole milliseconds, by which the parts are balanced.

    A file the table lists weighs its measured seconds; one it does not yet
    list weighs its number of tests at the average rate of the listed files
    in this collection. With no listed file at all, the weight is the number
    of tests, as before the table existed. Every weight is at least 1, so
    each of the first files placed opens a part of its own and no part is
    left empty while there are files enough. Whole numbers, so every runner
    adds them up to exactly the same loads.
    """
    listed = [name for name in counts if name in table]
    listed_tests = sum(counts[name] for name in listed)
    if not listed_tests:
        return dict(counts)
    rate = sum(table[name] for name in listed) / listed_tests
    return {
        name: max(1, round(1000 * (table[name] if name in table else rate * count)))
        for name, count in counts.items()
    }


def shard_assignment(weights: dict[str, int], parts: int) -> dict[str, int]:
    """Which part (1-based) each test file belongs to.

    Whole files, because a file's fixtures and test order are its own.
    Balanced by weight (shard_weights: expected milliseconds, or the number
    of tests without a table). The heaviest file first, each to whichever
    part is lightest so far; ties, in weight or in load, go by name and by
    the lower part, so every runner that collects the same tests computes
    the same answer.
    """
    loads = [0] * parts
    assigned: dict[str, int] = {}
    for name, weight in sorted(weights.items(), key=lambda item: (-item[1], item[0])):
        lightest = min(range(parts), key=lambda index: (loads[index], index))
        loads[lightest] += weight
        assigned[name] = lightest + 1
    return assigned


class _Sharding:
    """Deselects every test outside this runner's part. Inactive unless the variable is set."""

    def __init__(self, shard: tuple[int, int] | None, times: str = "linux") -> None:
        self.shard = shard
        self.times = times
        self.summary: str | None = None

    # After every other hook, the `-m` deselection included: the parts are a
    # partition of what this cell actually runs, not of everything collected.
    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, config, items):
        if self.shard is None:
            return
        part, parts = self.shard
        counts: dict[str, int] = {}
        for item in items:
            counts[item.nodeid.split("::", 1)[0]] = counts.get(item.nodeid.split("::", 1)[0], 0) + 1
        table = duration_table(self.times)
        weights = shard_weights(counts, table)
        assigned = shard_assignment(weights, parts)
        kept = [item for item in items if assigned[item.nodeid.split("::", 1)[0]] == part]
        dropped = [item for item in items if assigned[item.nodeid.split("::", 1)[0]] != part]
        if not kept:
            # An empty part that exits green would hide a suite that stopped running.
            raise pytest.UsageError(
                f"{_SHARD_ENV}={part}/{parts} leaves no tests to run: "
                f"{len(items)} test(s) in {len(counts)} file(s) cannot fill {parts} parts."
            )
        files = sum(1 for name in assigned.values() if name == part)
        timed = sum(1 for name in counts if name in table)
        if timed:
            # The estimate is what the split aimed at; the run's own time says how close it came.
            estimate = sum(weight for name, weight in weights.items() if assigned[name] == part) / 1000
            basis = (f"about {estimate:.0f} s by the {self.times} times in {_DURATIONS.name}, "
                     f"{timed} of {len(counts)} files timed")
        else:
            basis = f"balanced by number of tests: no file is timed for {self.times} in {_DURATIONS.name}"
        self.summary = (f"part {part} of {parts}: {len(kept)} of {len(items)} tests, "
                        f"{files} of {len(counts)} files; {basis} ({_SHARD_ENV})")
        if dropped:
            config.hook.pytest_deselected(items=dropped)
            items[:] = kept

    def pytest_report_collectionfinish(self, config):
        return self.summary


def experiment_test_files() -> set[str]:
    """File names listed in tests/experiment_tests.txt."""
    lines = _EXPERIMENT_LIST.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")}


def pytest_collection_modifyitems(config, items):
    # Mark by file so pull-request CI can run `-m "not experiment"` on the
    # Windows and Python 3.11 cells while the coverage cell runs everything.
    listed = experiment_test_files()
    for item in items:
        if item.path.name in listed:
            item.add_marker(pytest.mark.experiment)


@pytest.fixture(autouse=True)
def fresh_signup_counts(monkeypatch):
    """Each test starts with no accounts created from anywhere.

    The sign-up caps count accounts created per source address and per day,
    in memory. The test client is always one address, and a whole run of the
    suite creates far more than five accounts an hour from it; without this
    the sixth test to register anyone would be told to come back later.
    """
    from api import accounts

    monkeypatch.setattr(accounts, "_signups_by_client", {})
    monkeypatch.setattr(accounts, "_signups_today", [])
