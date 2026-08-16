"""Contract tests for public documentation that describes live behaviour.

These assertions are deliberately narrow. Prose in general is not executable,
but four statements here are interfaces: the benchmark table and measured
results are the advertised evaluation contract, run-id entropy is part of the
capability-URL security model, and the list of serving surfaces tells a new
contributor which entry points exist. All four have drifted while every runtime
test stayed green.
"""

from __future__ import annotations

import csv
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


class BenchmarkResultsDocumentationContractTests(unittest.TestCase):
    """Public performance claims must be computed from the shipped CSV."""

    def test_bilingual_measured_results_match_the_frozen_baseline(self):
        with (ROOT / "outputs" / "benchmark" / "benchmark_summary.csv").open(
            encoding="utf-8-sig", newline="",
        ) as handle:
            rows = list(csv.DictReader(handle))

        total = len(rows)
        completed = sum(row["status"] == "success" for row in rows)
        calibrated = sum(row["trl_calibration"] == "pass" for row in rows)
        formulas = sum(row["formula_correct"].lower() == "true" for row in rows)
        complete_reports = sum(row["sections_complete"].lower() == "true" for row in rows)
        unsupported_numeric = sum(int(row["numeric_uncited_lines"] or 0) for row in rows)
        topic_count = len({row["case_num"] for row in rows})
        repetitions = {sum(candidate["case_num"] == case for candidate in rows)
                       for case in {row["case_num"] for row in rows}}

        # A mixed fixture/live CSV cannot support a single public number: the
        # evidence conditions differ. Likewise, "three repetitions" is a real
        # stability claim only when every topic has three, not when 30 rows
        # happen to divide evenly by ten.
        self.assertEqual({row["evidence_mode"] for row in rows}, {"live"})
        self.assertEqual(repetitions, {3})

        claims = (
            "### Measured results",
            f"**{topic_count} topics × {repetitions.pop()} live repetitions**",
            f"| End-to-end completion | **{completed}/{total}** |",
            f"| TRL calibration | **{calibrated}/{total}** |",
            f"| Weighted formula correctness | **{formulas}/{total}** |",
            f"| Complete report structure | **{complete_reports}/{total}** |",
            f"| Unsupported numeric lines | **{unsupported_numeric} across {total} reports** |",
            "### 实测结果",
            f"**{topic_count} 个主题 × 每个主题 {total // topic_count} 次实时检索运行**",
            f"| 端到端完成 | **{completed}/{total}** |",
            f"| TRL 校准 | **{calibrated}/{total}** |",
            f"| 加权公式正确 | **{formulas}/{total}** |",
            f"| 报告结构完整 | **{complete_reports}/{total}** |",
            f"| 无引用数值行 | **{total} 份报告中 {unsupported_numeric} 行** |",
        )
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for claim in claims:
            with self.subTest(claim=claim):
                self.assertIn(claim, readme)


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
