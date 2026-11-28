"""A run of a model that cannot turn thinking off gets 40 minutes, decided at launch.

Measured 2026-11-28 on production (docs/results-2026-11-28-thinking-model-
time-limit.md): of six qwen3.8-2.4t-a95b runs that reached the writer, one
delivered a reviewed and scored report inside 30 minutes. Two had scoring
refused with about 200 seconds left, one skipped its review, one timed out in
its review. The limit is fixed when the API launches the worker, so the API
has to know then; it learns it from the model's own refusal of non-thinking
mode, seen by this process (a topic preview) or by an earlier run's worker,
which marks its status.json. No model list.

Popen is patched: no worker starts and no provider is called.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from academic_agent import llm_parameter_fallback as fallback
from api import access, runs
from api.main import app

THINKING_ONLY = "qwen-thinking-only-test"
QWEN_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_OPERATOR_QWEN = {
    "LLM_PROVIDER": "qwen",
    "DASHSCOPE_API_KEY": "operator-test-key",
    "QWEN_MODEL": THINKING_ONLY,
}


def _earlier_run(root: Path, suffix: str, status: dict) -> Path:
    run_dir = root / f"20261101T000000Z-{suffix}"
    run_dir.mkdir(parents=True)
    (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    return run_dir


class ThinkingTimeLimitTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        patches = (
            patch.object(runs, "DEFAULT_OUTPUT_ROOT", self.tmp),
            patch.object(access, "ACCESS_CODE", None),
            patch.object(access, "ACCESS_CODES", None),
            patch.object(runs, "DAILY_CAP", 0),
            patch.object(runs, "_daily_counts", {}),
            patch.object(runs, "_daily_date", None),
            patch.object(runs, "_inline_paid_operations", {}),
            patch.dict(os.environ, _OPERATOR_QWEN),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        runs._registry.clear()
        self.addCleanup(runs._registry.clear)
        fallback.reset()
        self.addCleanup(fallback.reset)
        runs._thinking_models.clear()
        self.addCleanup(runs._thinking_models.clear)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.client = TestClient(app)

    def _launch(self) -> tuple[str, list[str], float]:
        proc = MagicMock()
        proc.poll.return_value = None
        with patch("api.runs.subprocess.Popen", return_value=proc) as popen:
            before = time.time()
            response = self.client.post("/api/runs", json={"topic": "phase change cold chain boxes"})
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()["run_id"], popen.call_args.args[0], before

    @staticmethod
    def _flag(command: list[str], name: str) -> str:
        return command[command.index(name) + 1]

    def test_a_model_an_earlier_worker_marked_gets_forty_minutes_end_to_end(self):
        """The mark reaches the worker's argv, the watchdog's handle and the run read."""
        _earlier_run(self.tmp, "aaaaaaaaaa", {"llm_model": THINKING_ONLY, "thinking_required": True})

        run_id, command, launched_at = self._launch()

        self.assertEqual(self._flag(command, "--hard-timeout-seconds"), "2400")
        deadline = float(self._flag(command, "--hard-deadline-epoch"))
        self.assertAlmostEqual(deadline - launched_at, 2400, delta=5)
        self.assertEqual(runs._registry[run_id].hard_timeout_seconds, 2400)
        budget = self.client.get(f"/api/runs/{run_id}").json()["runtime_budget"]
        self.assertEqual(budget["hard_timeout_seconds"], 2400)
        self.assertGreater(budget["remaining_seconds"], runs.TIMEOUT_SECONDS)

    def test_what_this_process_learned_from_a_preview_counts_without_any_record(self):
        """The first run after a deploy has no marked record; its topic preview has asked the model."""
        fallback.learn(QWEN_BASE, THINKING_ONLY, "enable_thinking", True)

        _run_id, command, _ = self._launch()

        self.assertEqual(self._flag(command, "--hard-timeout-seconds"), "2400")

    def test_other_models_and_other_refusals_keep_thirty_minutes(self):
        cases = {
            "nothing known": lambda root: None,
            "another model marked": lambda root: _earlier_run(
                root, "bbbbbbbbbb", {"llm_model": "another-model", "thinking_required": True}),
            "this model, unmarked": lambda root: _earlier_run(
                root, "cccccccccc", {"llm_model": THINKING_ONLY}),
            "a mark that is not true": lambda root: _earlier_run(
                root, "dddddddddd", {"llm_model": THINKING_ONLY, "thinking_required": "yes"}),
            "this model refused response_format": lambda root: fallback.learn(
                QWEN_BASE, THINKING_ONLY, "response_format", fallback.OMIT),
            "this model asked for thinking off": lambda root: fallback.learn(
                QWEN_BASE, THINKING_ONLY, "enable_thinking", False),
            "another model learned thinking": lambda root: fallback.learn(
                QWEN_BASE, "another-model", "enable_thinking", True),
        }
        for index, (name, arrange) in enumerate(cases.items()):
            with self.subTest(name):
                # A fresh output root per case: the launched run's log stays open.
                root = self.tmp / f"case{index}"
                fallback.reset()
                runs._registry.clear()
                with patch.object(runs, "DEFAULT_OUTPUT_ROOT", root),                         patch.object(runs, "_daily_counts", {}), patch.object(runs, "_daily_date", None):
                    root.mkdir()
                    arrange(root)
                    _run_id, command, _ = self._launch()
                self.assertEqual(self._flag(command, "--hard-timeout-seconds"), str(runs.TIMEOUT_SECONDS))

    def test_an_unreadable_record_is_skipped_and_the_next_one_still_counts(self):
        broken = self.tmp / "20261102T000000Z-eeeeeeeeee"
        broken.mkdir()
        (broken / "status.json").write_text("{not json", encoding="utf-8")
        _earlier_run(self.tmp, "ffffffffff", {"llm_model": THINKING_ONLY, "thinking_required": True})

        _run_id, command, _ = self._launch()

        self.assertEqual(self._flag(command, "--hard-timeout-seconds"), "2400")

    def test_a_byok_model_is_judged_by_the_model_the_visitor_named(self):
        """Not the deployment's: the run is billed to and runs on the visitor's model."""
        _earlier_run(self.tmp, "1111111111", {"llm_model": "visitor-thinking-only", "thinking_required": True})
        byok = runs.BYOKCredentials("qwen", "visitor-key", llm_model="visitor-thinking-only",
                                    tavily_api_key="visitor-tavily")
        proc = MagicMock()
        proc.poll.return_value = None
        with patch("api.runs.subprocess.Popen", return_value=proc) as popen:
            runs.start_run("phase change cold chain boxes", byok=byok)
        command = popen.call_args.args[0]
        self.assertEqual(self._flag(command, "--hard-timeout-seconds"), "2400")

        # The operator's model is the thinking-only one; the visitor's is not.
        fallback.learn(QWEN_BASE, THINKING_ONLY, "enable_thinking", True)
        plain = runs.BYOKCredentials("qwen", "visitor-key", llm_model="visitor-plain",
                                     tavily_api_key="visitor-tavily")
        runs._registry.clear()
        with patch("api.runs.subprocess.Popen", return_value=proc) as popen:
            runs.start_run("phase change cold chain boxes", byok=plain)
        self.assertEqual(self._flag(popen.call_args.args[0], "--hard-timeout-seconds"),
                         str(runs.TIMEOUT_SECONDS))

    def test_the_watchdog_kills_a_forty_minute_run_at_forty_not_thirty(self):
        _earlier_run(self.tmp, "2222222222", {"llm_model": THINKING_ONLY, "thinking_required": True})
        run_id, _command, _ = self._launch()
        handle = runs._registry[run_id]

        handle.started -= runs.TIMEOUT_SECONDS + 1
        self.assertEqual(runs.reap_timeouts(), [])
        self.assertEqual(self.client.get(f"/api/runs/{run_id}").json()["state"], "running")

        handle.started -= runs.THINKING_TIMEOUT_SECONDS - runs.TIMEOUT_SECONDS
        self.assertEqual(runs.reap_timeouts(), [run_id])
        status = self.client.get(f"/api/runs/{run_id}").json()
        self.assertEqual(status["state"], "timeout")
        self.assertEqual(status["terminal"]["timeout_seconds"], runs.THINKING_TIMEOUT_SECONDS)
        error_log = (runs.run_dir_for(run_id) / "error.log").read_text(encoding="utf-8")
        self.assertIn("40 minutes", error_log)

    def test_without_a_resolvable_model_the_run_keeps_thirty_minutes(self):
        with patch.dict(os.environ, {"QWEN_MODEL": ""}):
            _run_id, command, _ = self._launch()
        self.assertEqual(self._flag(command, "--hard-timeout-seconds"), str(runs.TIMEOUT_SECONDS))


class RequiresThinkingTests(unittest.TestCase):

    def setUp(self) -> None:
        fallback.reset()
        self.addCleanup(fallback.reset)

    def test_by_model_name_at_any_endpoint(self):
        fallback.learn("https://one.example/v1", "m", "enable_thinking", True)
        self.assertTrue(fallback.requires_thinking("m"))
        self.assertFalse(fallback.requires_thinking("m2"))

    def test_only_a_refusal_that_asked_for_thinking_on(self):
        fallback.learn("https://one.example/v1", "a", "enable_thinking", False)
        fallback.learn("https://one.example/v1", "b", "enable_thinking", fallback.OMIT)
        fallback.learn("https://one.example/v1", "c", "temperature", fallback.OMIT)
        for model in ("a", "b", "c"):
            with self.subTest(model=model):
                self.assertFalse(fallback.requires_thinking(model))


if __name__ == "__main__":
    unittest.main()

