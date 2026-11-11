"""A pull request's test cells are split over several runners; nothing may fall between them.

Measured on 2026-11-11: a pull request waited 11 to 13 minutes, set by the
one cell that runs all 8,654 tests under coverage (630 seconds of pytest),
with the two Windows cells behind it at 436 seconds for the 4,738 tests they
run. No single test is slow (the slowest took 5.8 seconds) and installing
takes 13 to 32 seconds, so neither trimming tests nor caching helps: the
time is the number of tests. Running them in parallel inside one runner was
tried (#228) and about half the runs then failed a timing-sensitive
concurrency test.

So each cell is split by test file over several runners, and each part still
runs serially on a machine of its own. That only works if the parts are
exactly a partition: every test in one part, none in two, the same answer on
every runner that computes it. These tests hold that, for the function and
for a real collection.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import parse_shard, shard_assignment

_ROOT = Path(__file__).resolve().parents[1]


class TestAssignment:
    def test_every_file_goes_to_exactly_one_part(self):
        counts = {f"tests/test_{i:03d}.py": (i * 37) % 91 + 1 for i in range(120)}
        for parts in (1, 2, 3, 5):
            assigned = shard_assignment(counts, parts)
            assert set(assigned) == set(counts)
            assert set(assigned.values()) <= set(range(1, parts + 1))
            assert len(set(assigned.values())) == parts, "no part is left empty when there are files enough"

    def test_the_parts_carry_about_the_same_number_of_tests(self):
        """Balanced by tests, not by files: one file here has 400 tests and many have 3."""
        counts = {"tests/test_big.py": 400, **{f"tests/test_{i:03d}.py": 3 + i % 40 for i in range(200)}}
        assigned = shard_assignment(counts, 3)
        loads = [sum(n for name, n in counts.items() if assigned[name] == part) for part in (1, 2, 3)]
        assert max(loads) - min(loads) <= max(counts.values()) // 10, loads

    def test_the_answer_does_not_depend_on_the_order_files_were_met_in(self):
        counts = {f"tests/test_{i:03d}.py": (i * 13) % 50 + 1 for i in range(60)}
        shuffled = dict(sorted(counts.items(), key=lambda item: item[0][::-1]))
        assert shard_assignment(counts, 3) == shard_assignment(shuffled, 3)

    def test_a_tie_is_broken_by_name_so_every_runner_agrees(self):
        counts = {name: 5 for name in ("tests/test_b.py", "tests/test_a.py", "tests/test_c.py")}
        assert shard_assignment(counts, 3) == {"tests/test_a.py": 1, "tests/test_b.py": 2, "tests/test_c.py": 3}

    def test_one_part_is_everything(self):
        counts = {"tests/test_a.py": 2, "tests/test_b.py": 9}
        assert set(shard_assignment(counts, 1).values()) == {1}


class TestSetting:
    def test_unset_means_the_whole_suite(self):
        assert parse_shard(None) is None
        assert parse_shard("") is None
        assert parse_shard("  ") is None

    def test_a_part_of_a_number(self):
        assert parse_shard("2/3") == (2, 3)
        assert parse_shard(" 1/1 ") == (1, 1)

    @pytest.mark.parametrize("raw", ["0/3", "4/3", "3", "a/b", "1/0", "-1/3", "1/3/5", "1.5/3", "2/17", "/3"])
    def test_anything_else_is_refused_not_guessed(self, raw):
        """A typo must not become "run nothing" or "run everything" with a green tick."""
        with pytest.raises(pytest.UsageError):
            parse_shard(raw)


def _collected(shard: str | None, *args: str) -> list[str]:
    env = {key: value for key, value in os.environ.items() if key != "ACA_TEST_SHARD"}
    if shard is not None:
        env["ACA_TEST_SHARD"] = shard
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *args],
        cwd=_ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )
    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]
    return sorted(line for line in result.stdout.splitlines() if "::" in line)


_SAMPLE = ("tests/test_ci_sharding.py", "tests/test_runtime_budget.py", "tests/test_llm_retry.py",
           "tests/test_link_probe.py", "tests/test_daily_charge_marker.py", "tests/test_failure_reasons.py",
           "tests/test_experiment_suite.py", "tests/test_ablation.py")


class TestARealCollection:
    """Through pytest itself, on a handful of real files, experiment ones among them."""

    def test_the_parts_are_a_partition_of_the_whole(self):
        whole = _collected(None, *_SAMPLE)
        parts = [_collected(f"{index}/3", *_SAMPLE) for index in (1, 2, 3)]
        assert all(parts), "no part is empty"
        assert sorted(node for part in parts for node in part) == whole, "nothing lost, nothing run twice"
        files = [{node.split("::")[0] for node in part} for part in parts]
        assert not (files[0] & files[1] or files[0] & files[2] or files[1] & files[2]), \
            "a file's tests stay together: its fixtures and order are its own"

    def test_the_partition_is_of_what_the_marker_left(self):
        """The cells that skip closed experiments split what remains, evenly."""
        whole = _collected(None, "-m", "not experiment", *_SAMPLE)
        parts = [_collected(f"{index}/2", "-m", "not experiment", *_SAMPLE) for index in (1, 2)]
        assert sorted(parts[0] + parts[1]) == whole
        assert not any("test_ablation.py" in node for node in whole), "an experiment file, deselected before the split"
        assert abs(len(parts[0]) - len(parts[1])) <= len(whole) // 3

    def test_a_malformed_setting_stops_the_run(self):
        env = {**os.environ, "ACA_TEST_SHARD": "4/3"}
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_runtime_budget.py"],
                                cwd=_ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        assert result.returncode != 0
        assert "ACA_TEST_SHARD" in result.stdout + result.stderr

    def test_a_part_with_nothing_to_run_is_an_error_not_a_pass(self):
        """One file split in three leaves two parts empty; an empty part that
        exits green would hide a suite that silently stopped running."""
        env = {**os.environ, "ACA_TEST_SHARD": "3/3"}
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_runtime_budget.py"],
                                cwd=_ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        assert result.returncode != 0
        assert "no tests" in (result.stdout + result.stderr).lower()

    def test_a_pytest_started_by_a_test_does_not_inherit_the_split(self):
        """Several tests start a pytest of their own and count what it
        collects. Inside a split cell they must still see the whole."""
        env = {**os.environ, "ACA_TEST_SHARD": "1/1"}
        node = "tests/test_ci_sharding.py::TestARealCollection::test_the_setting_is_gone_once_it_has_been_read"
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", node],
                                cwd=_ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        assert result.returncode == 0, result.stdout[-800:]
        assert "1 passed" in result.stdout

    def test_the_setting_is_gone_once_it_has_been_read(self):
        """Run directly this holds trivially; the test above runs it under a
        split, where it is what a child process of any test would inherit."""
        assert "ACA_TEST_SHARD" not in os.environ

    def test_the_run_says_which_part_it_is(self):
        env = {**os.environ, "ACA_TEST_SHARD": "1/2"}
        result = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *_SAMPLE[:4]],
                                cwd=_ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        assert "part 1 of 2" in result.stdout
