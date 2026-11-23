"""Measure how long each test file takes on CI, for balancing the split cells.

    uv run python scripts/ci_test_durations.py RUN_ID [RUN_ID ...]

Reads the job logs of the given runs of the Tests workflow through the GitHub
CLI (signed in, run from inside the repository) and rewrites
tests/ci_test_durations.json: for each runner OS, the mean number of seconds
each test file took. tests/conftest.py gives each part of a split cell about
the same share of those seconds. The table decides only which runner runs a
file, never whether a file runs, so a stale one costs time and nothing else.
Refresh it when the parts of a cell finish far apart; a few green runs of
current main (five or so) average out the noise of a single runner.

How a file is timed: GitHub stamps every log line with the time the runner
received it, and `pytest -v` prints one line per test as the test ends. A
test's time is the gap since the line before it and a file's time is the sum
over its tests, so a module fixture's setup counts towards its file, which is
where it belongs. Collection and the summary after the last test belong to no
file and are left out.

Which cells: Linux is timed on the Ubuntu/Python 3.12 cell, the one that runs
every file and does so under coverage; the other Linux cell takes about a
third as long, so its balance matters least. Windows is timed on both Windows
cells. Only parts that passed are read: a failed part stops nothing, but its
timings would be those of a run that went wrong.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

TABLE = Path(__file__).resolve().parents[1] / "tests" / "ci_test_durations.json"

_STAMPED = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?Z (.*)$")
# The nodeid, then the outcome `pytest -v` appends once the test has ended.
_RESULT = re.compile(r"^(tests/[^\s:]+\.py)::\S.* (PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_PART = re.compile(r"^pytest \((ubuntu|windows)-latest, py(3\.\d+), part \d+ of \d+\)$")
# Which cells time which runner OS (see the docstring).
_TIMED = {("ubuntu", "3.12"): "linux", ("windows", "3.11"): "windows", ("windows", "3.12"): "windows"}


def _stamp(date: str, fraction: str | None) -> datetime:
    # Seven fractional digits on GitHub; datetime reads at most six.
    return datetime.fromisoformat(date + (fraction or ".0")[:7])


def file_seconds(log: str) -> dict[str, float]:
    """Seconds per test file in one job's log; empty when no test result is in it."""
    seconds: dict[str, float] = defaultdict(float)
    previous = None
    for raw in log.splitlines():
        stamped = _STAMPED.match(raw)
        if not stamped:
            continue
        when = _stamp(stamped.group(1), stamped.group(2))
        result = _RESULT.match(_ANSI.sub("", stamped.group(3)))
        if result and previous is not None:
            seconds[result.group(1)] += (when - previous).total_seconds()
        # Until the first result, the clock follows the log, so the first
        # test is timed from the line before it (the collection summary).
        if result or not seconds:
            previous = when
    return dict(seconds)


def timed_os(job_name: str) -> str | None:
    """"linux" or "windows" for a test part of a timed cell, None for any other job."""
    part = _PART.match(job_name)
    return _TIMED.get((part.group(1), part.group(2))) if part else None


def build_table(observations: dict[str, list[dict[str, float]]], runs: list[int]) -> dict:
    """The JSON document: per OS, each file's mean seconds over the parts that ran it."""
    table: dict = {
        "about": ("Seconds each test file took on CI, per runner OS. tests/conftest.py balances "
                  "the parts of a split cell by it; scripts/ci_test_durations.py rewrites it."),
        "runs": sorted(runs),
    }
    for system in ("linux", "windows"):
        per_file: dict[str, list[float]] = defaultdict(list)
        for timings in observations.get(system, []):
            for name, value in timings.items():
                per_file[name].append(value)
        table[system] = {name: round(statistics.fmean(values), 1) for name, values in sorted(per_file.items())}
    return table


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("runs", nargs="+", type=int, help="IDs of runs of the Tests workflow")
    args = parser.parse_args(argv)
    observations: dict[str, list[dict[str, float]]] = defaultdict(list)
    for run in args.runs:
        jobs = json.loads(_gh("run", "view", str(run), "--json", "jobs"))["jobs"]
        read = 0
        for job in jobs:
            system = timed_os(job["name"])
            if system is None or job["conclusion"] != "success":
                continue
            timings = file_seconds(_gh("api", f"repos/{{owner}}/{{repo}}/actions/jobs/{job['databaseId']}/logs"))
            if timings:
                observations[system].append(timings)
                read += 1
        print(f"run {run}: {read} timed parts", file=sys.stderr)
    if not observations.get("linux") or not observations.get("windows"):
        print("No passing part of a timed Linux or Windows cell was found; the table is unchanged.", file=sys.stderr)
        return 1
    table = build_table(observations, args.runs)
    TABLE.write_text(json.dumps(table, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {TABLE.name}: {len(table['linux'])} Linux and {len(table['windows'])} Windows files", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
