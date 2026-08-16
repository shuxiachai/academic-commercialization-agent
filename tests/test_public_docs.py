"""Contract tests for public documentation that describes live behaviour.

These assertions are deliberately narrow. Prose in general is not executable,
but three statements here are interfaces: the benchmark table is the advertised
evaluation set, run-id entropy is part of the capability-URL security model, and
the list of serving surfaces tells a new contributor which entry points exist.
All three drifted while every runtime test stayed green.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import benchmark
from academic_agent.run_output import _RUN_ID_ENTROPY_BYTES


ROOT = Path(__file__).resolve().parent.parent


class BenchmarkTableContractTests(unittest.TestCase):
    """The English and Chinese README tables must describe benchmark.TOPICS."""

    def test_both_public_tables_match_the_executable_benchmark(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        rows = re.findall(
            r"^\|\s*(\d{2})\s*\|\s*(.*?)\s*\|\s*(\d+)\s*[–-]\s*(\d+)\s*\|\s*(.*?)\s*\|$",
            readme,
            flags=re.MULTILINE,
        )
        expected = [
            (num, topic, str(low), str(high), industry)
            for num, topic, (low, high), industry in benchmark.TOPICS
        ]

        # The README is bilingual. Comparing the complete sequence catches a
        # missing table as well as a stale row; set equality would let one
        # language disappear without changing the distinct values.
        self.assertEqual(rows, expected + expected)


class RunIdDocumentationContractTests(unittest.TestCase):
    """Security prose must derive from the same entropy choice as the code."""

    def test_public_security_claims_match_run_id_entropy(self):
        bits = _RUN_ID_ENTROPY_BYTES * 8
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        api_source = (ROOT / "api" / "main.py").read_text(encoding="utf-8")

        self.assertIn(f"{bits} bits of randomness", readme)
        self.assertIn(f"{bits} 位随机性", readme)
        self.assertNotIn("40 bits of randomness", readme)
        self.assertNotIn("40 位随机性", readme)
        self.assertNotIn("a 40-bit id", api_source)


class ServingSurfaceDocumentationTests(unittest.TestCase):
    """Removed entry points must not remain described as live architecture."""

    def test_current_entry_point_docs_do_not_advertise_gradio(self):
        for relative in ("AGENTS.md", "api/main.py", "api/runs.py", "api/papers.py"):
            with self.subTest(file=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertNotIn("Gradio", text)


if __name__ == "__main__":
    unittest.main()
