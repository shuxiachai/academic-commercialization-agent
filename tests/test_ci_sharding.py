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

On 2026-11-23 the parts moved from being balanced by number of tests to
being balanced by each file's measured CI time (tests/ci_test_durations.json):
on the coverage cell a closed-experiment canary test takes about 0.25 s and
most others under 0.01 s, so equal counts were far from equal time. The
table only moves files between parts; the tests below hold that it can never
make a file run twice or not at all, and that the committed table is one the
split can read.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import duration_table, parse_shard, parse_times, shard_assignment, shard_weights

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


class TestWeights:
    def test_a_timed_file_weighs_its_seconds_not_its_tests(self):
        """The case the table is for: one file of few slow tests against files of many fast ones."""
        counts = {"tests/test_slow.py": 10, "tests/test_a.py": 100, "tests/test_b.py": 100, "tests/test_c.py": 100}
        table = {"tests/test_slow.py": 60.0, "tests/test_a.py": 20.0, "tests/test_b.py": 20.0, "tests/test_c.py": 20.0}

        def seconds(assigned):
            return sorted(sum(table[name] for name in counts if assigned[name] == part) for part in (1, 2))

        assert seconds(shard_assignment(counts, 2)) == [40.0, 80.0], "by count, the slow file joins a full part"
        assert seconds(shard_assignment(shard_weights(counts, table), 2)) == [60.0, 60.0]

    def test_a_file_the_table_does_not_list_is_estimated_from_its_tests(self):
        counts = {"tests/test_a.py": 10, "tests/test_b.py": 30, "tests/test_new.py": 20}
        table = {"tests/test_a.py": 1.0, "tests/test_b.py": 7.0, "tests/test_gone.py": 99.0}
        # 8 s over the 40 listed tests collected here is 0.2 s a test, so 20 new tests weigh 4 s;
        # a file the table lists but this collection lacks counts for nothing.
        assert shard_weights(counts, table) == {"tests/test_a.py": 1000, "tests/test_b.py": 7000, "tests/test_new.py": 4000}

    def test_without_a_timed_file_the_weight_is_the_number_of_tests(self):
        counts = {"tests/test_a.py": 3, "tests/test_b.py": 9}
        assert shard_weights(counts, {}) == counts
        assert shard_weights(counts, {"tests/test_gone.py": 5.0}) == counts

    def test_no_weight_is_zero_so_no_part_is_left_empty(self):
        counts = {f"tests/test_{i}.py": 1 for i in range(5)}
        weights = shard_weights(counts, {name: 0.0 for name in counts})
        assert min(weights.values()) >= 1
        assert set(shard_assignment(weights, 5).values()) == {1, 2, 3, 4, 5}

    def test_whatever_the_table_says_the_parts_stay_a_partition(self):
        """A wrong or stale table may make the parts uneven, never lose or double a file."""
        counts = {f"tests/test_{i:03d}.py": (i * 37) % 91 + 1 for i in range(120)}
        tables = ({}, {name: 0.0 for name in counts}, {name: float(i % 7) for i, name in enumerate(counts)},
                  {"tests/test_000.py": 1e6}, {"tests/test_elsewhere.py": 3.0})
        for table in tables:
            for parts in (1, 3, 5):
                assigned = shard_assignment(shard_weights(counts, table), parts)
                assert set(assigned) == set(counts)
                assert set(assigned.values()) == set(range(1, parts + 1))


class TestTheHook:
    """The collection hook itself, on made-up items and a made-up table."""

    _FILES = (("tests/test_slow.py", 10), ("tests/test_a.py", 100), ("tests/test_b.py", 100), ("tests/test_c.py", 100))
    _TIMES = {"tests/test_slow.py": 60.0, "tests/test_a.py": 20.0, "tests/test_b.py": 20.0, "tests/test_c.py": 20.0}

    def _split(self, monkeypatch, part, times):
        import conftest

        monkeypatch.setattr(conftest, "duration_table", lambda system: dict(self._TIMES) if system == "linux" else {})
        items = [SimpleNamespace(nodeid=f"{name}::test_{index}") for name, count in self._FILES for index in range(count)]
        deselected = []
        config = SimpleNamespace(hook=SimpleNamespace(pytest_deselected=lambda items: deselected.extend(items)))
        sharding = conftest._Sharding((part, 2), times)
        kept = list(items)
        sharding.pytest_collection_modifyitems(config, kept)
        assert sorted(item.nodeid for item in kept + deselected) == sorted(item.nodeid for item in items)
        return {item.nodeid.split("::")[0] for item in kept}, sharding.summary

    def test_the_split_follows_the_times_not_the_counts(self, monkeypatch):
        files, summary = self._split(monkeypatch, 1, "linux")
        assert files == {"tests/test_slow.py"}, "60 s against three files of 20 s"
        assert "about 60 s by the linux times" in summary
        files, _summary = self._split(monkeypatch, 2, "linux")
        assert files == {"tests/test_a.py", "tests/test_b.py", "tests/test_c.py"}

    def test_without_times_the_split_counts_tests_and_says_so(self, monkeypatch):
        files, summary = self._split(monkeypatch, 1, "windows")
        assert files == {"tests/test_a.py", "tests/test_c.py"}
        assert "balanced by number of tests" in summary


class TestTable:
    def test_the_committed_table_is_one_the_split_can_read(self):
        """An unreadable table would quietly send the split back to counting tests."""
        raw = json.loads((_ROOT / "tests" / "ci_test_durations.json").read_text(encoding="utf-8"))
        for system in ("linux", "windows"):
            table = duration_table(system)
            assert table, f"the table has no {system} times"
            assert len(table) == len(raw[system]), "every entry is a usable number of seconds"
            assert all(name.startswith("tests/") and name.endswith(".py") for name in table)

    def test_each_os_has_its_own_times(self, tmp_path):
        path = tmp_path / "durations.json"
        path.write_text(json.dumps({"linux": {"tests/test_a.py": 2.5}, "windows": {"tests/test_a.py": 7.0}}),
                        encoding="utf-8")
        assert duration_table("linux", path) == {"tests/test_a.py": 2.5}
        assert duration_table("windows", path) == {"tests/test_a.py": 7.0}

    @pytest.mark.parametrize(("platform", "system"), [("win32", "windows"), ("linux", "linux"), ("darwin", "linux")])
    def test_the_machines_os_picks_the_table_unless_told(self, platform, system):
        assert parse_times(None, platform) == system
        assert parse_times("  ", platform) == system
        # Told, as when a Linux part is reproduced on Windows.
        assert parse_times("linux", "win32") == "linux"
        assert parse_times("windows", "linux") == "windows"

    @pytest.mark.parametrize("raw", ["Linux", "win32", "ubuntu", "linux,windows", "1"])
    def test_a_table_it_does_not_have_is_refused(self, raw):
        with pytest.raises(pytest.UsageError):
            parse_times(raw)

    @pytest.mark.parametrize("text", ["", "not json", "[]", '{"linux": []}', '{"windows": {}}',
                                      '{"linux": {"tests/test_a.py": "slow"}}', '{"linux": {"tests/test_a.py": null}}'])
    def test_an_unreadable_table_is_no_table(self, tmp_path, text):
        path = tmp_path / "durations.json"
        path.write_text(text, encoding="utf-8")
        assert duration_table("linux", path) == {}

    def test_a_missing_table_is_no_table(self, tmp_path):
        assert duration_table("linux", tmp_path / "absent.json") == {}

    def test_an_impossible_time_is_left_out(self, tmp_path):
        path = tmp_path / "durations.json"
        path.write_text('{"linux": {"tests/test_a.py": -1, "tests/test_b.py": NaN, "tests/test_c.py": Infinity, '
                        '"tests/test_d.py": 2}}', encoding="utf-8")
        assert duration_table("linux", path) == {"tests/test_d.py": 2.0}


class TestMeasuring:
    """scripts/ci_test_durations.py, which writes the table from CI job logs."""

    _LOG = "\n".join([
        "2026-11-23T12:06:00.0000000Z ##[group]Run uv run --python 3.11 pytest tests/ -v",
        "2026-11-23T12:06:20.0000000Z collecting ... collected 6 items / 2 deselected / 4 selected",
        "2026-11-23T12:06:21.5000000Z tests/test_a.py::TestA::test_one PASSED [ 25%]",
        "2026-11-23T12:06:22.0000000Z tests/test_a.py::test_two[case with spaces] PASSED [ 50%]",
        "2026-11-23T12:06:22.0100000Z some warning text printed by a test",
        "2026-11-23T12:06:25.0000000Z tests/sub/test_b.py::test_three \x1b[32mPASSED\x1b[0m [ 75%]",
        "2026-11-23T12:06:25.2500000Z tests/test_a.py::test_four SKIPPED (no Node) [100%]",
        "2026-11-23T12:06:40.0000000Z ============================= slowest 40 durations =============================",
        "2026-11-23T12:06:40.1000000Z 3.00s call     tests/sub/test_b.py::test_three",
        "2026-11-23T12:06:41.0000000Z ==== 3 passed, 1 skipped, 2 deselected in 21.00s ====",
    ])

    def test_a_file_is_the_sum_of_the_gaps_before_its_results(self):
        from scripts.ci_test_durations import file_seconds

        seconds = file_seconds(self._LOG)
        # test_one from the collection line: 1.5 s; test_two 0.5; test_four 0.25. test_three: 3.0,
        # the warning line in between counted to the test it came from. Collection and the
        # summary after the last result belong to no file.
        assert seconds == pytest.approx({"tests/test_a.py": 2.25, "tests/sub/test_b.py": 3.0})

    def test_a_log_without_results_times_nothing(self):
        from scripts.ci_test_durations import file_seconds

        assert file_seconds("2026-11-23T12:06:00.0000000Z ##[group]Run uv sync\n") == {}

    @pytest.mark.parametrize(("name", "system"), [
        ("pytest (ubuntu-latest, py3.12, part 2 of 5)", "linux"),
        ("pytest (windows-latest, py3.11, part 1 of 5)", "windows"),
        ("pytest (windows-latest, py3.12, part 5 of 5)", "windows"),
        # The faster Linux cell is not timed, and the gates run no tests.
        ("pytest (ubuntu-latest, py3.11, part 2 of 5)", None),
        ("pytest (windows-latest, py3.11)", None),
        ("coverage floor (Ubuntu, py3.12)", None),
    ])
    def test_which_jobs_time_which_os(self, name, system):
        from scripts.ci_test_durations import timed_os

        assert timed_os(name) == system

    def test_the_table_is_each_files_mean_per_os(self):
        from scripts.ci_test_durations import build_table

        table = build_table({"linux": [{"tests/test_a.py": 1.0}, {"tests/test_a.py": 2.0, "tests/test_b.py": 0.04}],
                             "windows": [{"tests/test_a.py": 4.0}]}, runs=[7, 3])
        assert table["linux"] == {"tests/test_a.py": 1.5, "tests/test_b.py": 0.0}
        assert table["windows"] == {"tests/test_a.py": 4.0}
        assert table["runs"] == [3, 7]
        assert set(table) == {"about", "runs", "linux", "windows"}


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
    # Each call is a pytest of its own (a few seconds on a Windows runner), so
    # these real collections are kept few; the functions above carry the cases.
    env = {key: value for key, value in os.environ.items() if key not in ("ACA_TEST_SHARD", "ACA_TEST_SHARD_TIMES")}
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
        """The cells that skip closed experiments split what remains.

        Evenly in time, not in tests, since the parts are balanced by measured
        seconds; so this asks only that both parts have work."""
        whole = _collected(None, "-m", "not experiment", *_SAMPLE)
        parts = [_collected(f"{index}/2", "-m", "not experiment", *_SAMPLE) for index in (1, 2)]
        assert sorted(parts[0] + parts[1]) == whole
        assert not any("test_ablation.py" in node for node in whole), "an experiment file, deselected before the split"
        assert parts[0] and parts[1]

    @pytest.mark.parametrize(("name", "value"), [("ACA_TEST_SHARD", "4/3"), ("ACA_TEST_SHARD_TIMES", "ubuntu")])
    def test_a_malformed_setting_stops_the_run(self, name, value):
        env = {**os.environ, "ACA_TEST_SHARD": "1/1", name: value}
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_runtime_budget.py"],
                                cwd=_ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        assert result.returncode != 0
        assert name in result.stdout + result.stderr

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
        env = {**os.environ, "ACA_TEST_SHARD": "1/1", "ACA_TEST_SHARD_TIMES": "linux"}
        node = "tests/test_ci_sharding.py::TestARealCollection::test_the_setting_is_gone_once_it_has_been_read"
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", node],
                                cwd=_ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        assert result.returncode == 0, result.stdout[-800:]
        assert "1 passed" in result.stdout

    def test_the_setting_is_gone_once_it_has_been_read(self):
        """Run directly this holds trivially; the test above runs it under a
        split, where it is what a child process of any test would inherit."""
        assert "ACA_TEST_SHARD" not in os.environ
        assert "ACA_TEST_SHARD_TIMES" not in os.environ

    @pytest.mark.parametrize("system", ["linux", "windows"])
    def test_the_run_says_which_part_it_is(self, system):
        env = {**os.environ, "ACA_TEST_SHARD": "1/2", "ACA_TEST_SHARD_TIMES": system}
        result = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *_SAMPLE[:4]],
                                cwd=_ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        assert "part 1 of 2" in result.stdout
        # And on what it balanced the parts, so a stale table shows in the log.
        assert f"by the {system} times in ci_test_durations.json" in result.stdout
