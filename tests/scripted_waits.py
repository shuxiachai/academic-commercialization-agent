"""Upper bounds for scripted waits in concurrency and subprocess tests.

A scripted wait bounds how long a test waits for something it *expects* to
happen: a scripted thread reaching or leaving an event, every party reaching
a barrier, a worker exiting, a future or task finishing, a child process
running to completion. These are hang guards, not performance budgets. On
GitHub's Windows runners the same fsync-heavy steps took 5-10x longer than
locally, and bounds of 1-15 s turned that into intermittent failures. A wait
that is never satisfied still fails, only later.

Left as literals in the tests on purpose: waits asserting that something does
NOT happen (a slower machine cannot make those fail), durations a test
simulates (for example a slow cell racing a deadline), production timeouts a
test injects, and cleanup on a path that has already failed.
"""

STEP = 30.0
"""One scripted step: an event, a barrier, a thread join, one future or task."""

SCENARIO = 120.0
"""A whole scripted scenario, request or child process under one hang guard."""
