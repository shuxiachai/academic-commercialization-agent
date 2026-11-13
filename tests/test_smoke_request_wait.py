"""The browser smoke counts intercepted requests only once they can have arrived.

A route handler fills a Python list, and it runs only while playwright is
pumping the browser's events. The step that opens a run with its first
progress response held clicked the run, made three checks of the page and then
asserted that exactly one request was in the list, with no wait. Measured on
2026-11-13 over 13 runs of the real journey, the request reached the handler
between 0 and 31 ms before that assertion. Once, on a machine also running the
full suite, it reached it afterwards: the smoke failed with "The first
progress request was not held." while its own failure picture showed the page
waiting on exactly that request. It could not be made to happen again in 173
tries, with and without the processor kept busy, and has not been seen in CI.

The wait is e2e/request_wait.py, kept apart from playwright so it can be run
here against a page that is only a counter.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from e2e import request_wait
from e2e.request_wait import wait_for_count

_ROOT = Path(__file__).resolve().parents[1]
_SMOKE = (_ROOT / "e2e" / "browser_smoke.py").read_text(encoding="utf-8")


class _Page:
    """A page whose only behaviour is to let time pass and events arrive."""

    def __init__(self, clock, items, arrivals=()):
        self.clock, self.items, self.arrivals, self.pumps = clock, items, dict(arrivals), []

    def wait_for_timeout(self, milliseconds):
        self.pumps.append(milliseconds)
        self.clock.now += milliseconds / 1000
        for _ in range(self.arrivals.pop(len(self.pumps), 0)):
            self.items.append(object())


class _Clock:
    def __init__(self):
        self.now = 100.0

    def monotonic(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = _Clock()
    monkeypatch.setattr(request_wait.time, "monotonic", fake.monotonic)
    return fake


def test_a_request_already_in_hand_costs_no_wait(clock):
    items = [object()]
    page = _Page(clock, items)
    wait_for_count(page, items, 1, "progress requests held")
    assert page.pumps == []


def test_a_request_that_arrives_late_is_waited_for(clock):
    # What failed once: nothing in the list when it was first looked at.
    items = []
    page = _Page(clock, items, arrivals={7: 1})
    wait_for_count(page, items, 1, "progress requests held")
    assert len(items) == 1
    assert len(page.pumps) == 7, "it stops as soon as the request is there"
    assert set(page.pumps) == {10}, "events are pumped in short turns, not slept through"


def test_a_request_that_never_arrives_fails_after_the_limit_and_says_what_was_missing(clock):
    items = []
    page = _Page(clock, items)
    started = clock.now
    with pytest.raises(AssertionError) as failure:
        wait_for_count(page, items, 1, "progress requests held")
    assert 5.0 <= clock.now - started < 5.1
    assert str(failure.value) == "Expected 1 progress requests held, observed 0 after 5 s."


def test_the_limit_can_be_set(clock):
    items = []
    page = _Page(clock, items, arrivals={150: 1})
    with pytest.raises(AssertionError, match="observed 0 after 1 s"):
        wait_for_count(page, items, 1, "requests", seconds=1)
    wait_for_count(page, items, 1, "requests", seconds=2)


def test_more_than_were_expected_is_a_failure_at_once(clock):
    # A second request while the first is unanswered is the defect the count guards against.
    items = [object(), object()]
    page = _Page(clock, items)
    with pytest.raises(AssertionError, match="Expected 1 progress requests held, observed 2"):
        wait_for_count(page, items, 1, "progress requests held")
    assert page.pumps == []
    both = []
    page = _Page(clock, both, arrivals={3: 2})
    with pytest.raises(AssertionError, match="observed 2"):
        wait_for_count(page, both, 1, "progress requests held")


def test_several_can_be_waited_for_and_none_can_be_expected(clock):
    items = []
    page = _Page(clock, items, arrivals={2: 1, 5: 1})
    wait_for_count(page, items, 2, "requests")
    assert len(page.pumps) == 5
    wait_for_count(_Page(clock, []), [], 0, "requests")


def test_the_suite_can_import_the_wait_without_playwright():
    source = (_ROOT / "e2e" / "request_wait.py").read_text(encoding="utf-8")
    assert re.search(r"^\s*(import|from) playwright", source, re.M) is None, "the pytest jobs do not install it"


def test_the_smoke_has_the_held_request_in_hand_before_it_judges_the_page():
    assert "from e2e.request_wait import wait_for_count" in _SMOKE
    step = _SMOKE[_SMOKE.index('faults["hold_progress"] = True'):_SMOKE.index('faults["hold_progress"] = False')]
    lines = [line.strip() for line in step.splitlines() if line.strip() and not line.strip().startswith("#")]
    assert lines[1] == "run_item.click()"
    assert lines[2] == 'wait_for_count(page, held_progress, 1, "progress requests held")', (
        "the wait follows the click, so the page is judged while its answer is held")
    checks = lines[3:]
    assert sum(line.startswith("expect(") for line in checks) == 3, checks
    # Still exactly one after the page was looked at: a second ask is a defect of its own.
    assert checks[-1].startswith("assert len(held_progress) == 1"), checks[-1]
