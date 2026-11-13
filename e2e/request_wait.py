"""Wait until a route handler has collected the requests a journey expects,
kept apart from playwright so the unit tests can run it
(tests/test_smoke_request_wait.py does, against a page that is only a counter).

A route handler appends to a Python list, and it runs only while playwright
is pumping the browser's events. A journey that looks at the list straight
after the action that causes the request is racing the browser: the request
has been made, but word of it may not have arrived.

The browser smoke's step that opens a run with its first progress response
held did that. Measured on 2026-11-13 over 13 runs of the real journey, the
request reached the handler between 0 and 31 ms before the assertion that it
had. Once, on a machine also running the full suite, it reached it
afterwards, and the smoke failed with "The first progress request was not
held." while its own failure picture showed the page waiting on exactly that
request. It did not happen again in 173 tries, with or without the processor
kept busy, and has not been seen in CI.

e2e/composer_smoke.py has had the same wait of its own (`_wait_requests`)
since it was written; this is that wait where the other smokes can use it.
"""
from __future__ import annotations

import time

PUMP_MS = 10


def wait_for_count(page, items, count: int, what: str, seconds: float = 5) -> None:
    """Pump the page's events until `items` holds `count` entries, then hold it to exactly that.

    `page` is a playwright Page, or anything with wait_for_timeout(ms). More
    entries than expected fail at once: a request that should not have been
    made is not cured by waiting. Fewer fail after `seconds`.
    """
    deadline = time.monotonic() + seconds
    while len(items) < count and time.monotonic() < deadline:
        page.wait_for_timeout(PUMP_MS)  # the handler runs inside this call
    assert len(items) == count, f"Expected {count} {what}, observed {len(items)} after {seconds:g} s."
