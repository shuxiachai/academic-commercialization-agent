"""Tests for the CLI entry point registered in pyproject.toml.

This path had no test at all, and drifted a full generation behind the worker
because of it: no evidence artifacts, no token accounting, no citation screen,
no per-domain degradation, and a report selected by negative index long after
the worker had abandoned that as unsafe. Nothing failed, because nothing ran.

So these assert the property that keeps it from drifting again — that the CLI
starts the same worker every other entry point does — rather than re-testing
the pipeline through a second door.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from unittest import TestCase, mock

from academic_agent import main as cli


def _args(**over) -> argparse.Namespace:
    base = {"topic": "solid-state batteries", "language": "",
            "weight_profile": "", "paper_json": ""}
    base.update(over)
    return argparse.Namespace(**base)


class ModuleExecutionTests(TestCase):
    def test_python_module_execution_reaches_the_parser(self):
        """The documented module command used to exit zero without running.

        Python module execution runs top-level code rather than the console
        script registered in pyproject.toml. Exercising --help proves the
        module seam reaches run() without starting a paid worker.
        """
        completed = subprocess.run(
            [sys.executable, "-m", "academic_agent.main", "--help"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertIn("--topic", completed.stdout)


class CommandConstructionTests(TestCase):

    def test_it_launches_the_worker_module(self):
        """The whole point of the rewrite: one implementation of a run."""
        cmd = cli.build_command("20260101T000000Z-abc", _args())
        self.assertEqual(cmd[0], sys.executable)
        self.assertEqual(cmd[1:3], ["-m", "academic_agent.pipeline_worker"])

    def test_run_id_and_topic_are_positional_in_that_order(self):
        cmd = cli.build_command("20260101T000000Z-abc", _args())
        self.assertEqual(cmd[3], "20260101T000000Z-abc")
        self.assertEqual(cmd[4], "solid-state batteries")

    def test_topic_is_stripped(self):
        """An unstripped topic reaches the retrieval layer as a different
        string and quietly changes what is searched for."""
        cmd = cli.build_command("r", _args(topic="  perovskite  "))
        self.assertEqual(cmd[4], "perovskite")

    def test_optional_flags_are_omitted_when_unset(self):
        """Passing --language '' would force an empty language rather than
        leaving detection to the worker."""
        cmd = cli.build_command("r", _args())
        for flag in ("--language", "--weight-profile", "--paper-json"):
            with self.subTest(flag=flag):
                self.assertNotIn(flag, cmd)

    def test_optional_flags_are_forwarded_when_set(self):
        cmd = cli.build_command("r", _args(
            language="Chinese", weight_profile="biomedical",
            paper_json="/tmp/paper.json"))
        for flag, value in (("--language", "Chinese"),
                            ("--weight-profile", "biomedical"),
                            ("--paper-json", "/tmp/paper.json")):
            with self.subTest(flag=flag):
                self.assertEqual(cmd[cmd.index(flag) + 1], value)

    def test_the_worker_accepts_every_flag_the_cli_forwards(self):
        """Guards the seam rather than the spelling: a flag renamed in the
        worker makes the CLI fail at runtime, on a paid run, and only for
        whoever used that flag."""
        import academic_agent.pipeline_worker as worker

        source = __import__("inspect").getsource(worker.main)
        for flag in ("--language", "--weight-profile", "--paper-json"):
            with self.subTest(flag=flag):
                self.assertIn(flag, source)


class ExitBehaviourTests(TestCase):

    def _run_cli(self, returncode: int):
        completed = subprocess.CompletedProcess(args=[], returncode=returncode)
        with mock.patch.object(cli.subprocess, "run", return_value=completed) as spawn, \
             mock.patch.object(sys, "argv", ["academic_agent", "--topic", "x y z"]), \
             self.assertRaises(SystemExit) as exit_ctx:
            cli.run()
        return exit_ctx.exception.code, spawn

    def test_the_worker_exit_code_is_propagated(self):
        """A CLI that exits 0 on a failed run breaks every script wrapping it,
        and the worker is the only thing that knows whether the run worked."""
        self.assertEqual(self._run_cli(1)[0], 1)
        self.assertEqual(self._run_cli(0)[0], 0)

    def test_output_is_inherited_not_captured(self):
        """The worker's stage log is the only progress a terminal user sees;
        capturing it would make a three-minute run look like a hang."""
        _code, spawn = self._run_cli(0)
        kwargs = spawn.call_args.kwargs
        self.assertNotIn("capture_output", kwargs)
        self.assertNotIn("stdout", kwargs)

    def test_a_failure_is_not_rewrapped_in_another_exception(self):
        """It used to raise RuntimeError(...) from exc, which buried the
        worker's own diagnosis under a second traceback."""
        code, _spawn = self._run_cli(1)
        self.assertEqual(code, 1)


class NoSecondPipelineTests(TestCase):
    """The drift this file exists to prevent was possible because the CLI had
    its own copy of the run. It should now have none."""

    def test_the_cli_does_not_drive_the_crew_itself(self):
        import inspect

        source = inspect.getsource(cli)
        for symbol in ("AcademicAgent", "kickoff", "collect_source_collection",
                       "tasks_output"):
            with self.subTest(symbol=symbol):
                self.assertNotIn(f"{symbol}(", source)

    def test_only_one_module_starts_a_worker_besides_the_api(self):
        """If a third caller ever grows its own pipeline, this is where it
        shows up."""
        import inspect
        from pathlib import Path

        repo = Path(inspect.getfile(cli)).resolve().parents[2]
        starters = []
        for path in list((repo / "src").rglob("*.py")) + list((repo / "api").rglob("*.py")):
            if path.name == "pipeline_worker.py":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if "academic_agent.pipeline_worker" in text and "subprocess" in text:
                starters.append(path.name)
        self.assertEqual(sorted(starters), ["main.py", "runs.py"])
