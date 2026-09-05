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
        expected = [
            (num, topic, str(low), str(high), industry)
            for num, topic, (low, high), industry in benchmark.TOPICS
        ]

        # Language entry points now live in separate files. Each must retain
        # the complete ordered contract: joining both documents or comparing
        # sets would let a missing translation hide behind the English rows.
        for relative in ("README.md", "README.zh-CN.md"):
            with self.subTest(file=relative):
                readme = (ROOT / relative).read_text(encoding="utf-8")
                rows = re.findall(
                    r"^\|\s*(\d{2})\s*\|\s*(.*?)\s*\|\s*(\d+)\s*[–-]\s*(\d+)\s*\|\s*(.*?)\s*\|$",
                    readme,
                    flags=re.MULTILINE,
                )
                self.assertEqual(rows, expected)


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

        english_claims = (
            "### Measured results",
            f"**{topic_count} topics × {repetitions.pop()} live repetitions**",
            f"| End-to-end completion | **{completed}/{total}** |",
            f"| TRL calibration | **{calibrated}/{total}** |",
            f"| Weighted formula correctness | **{formulas}/{total}** |",
            f"| Complete report structure | **{complete_reports}/{total}** |",
            f"| Unsupported numeric lines | **{unsupported_numeric} across {total} reports** |",
        )
        chinese_claims = (
            "### 实测结果",
            f"**{topic_count} 个主题 × 每个主题 {total // topic_count} 次实时检索运行**",
            f"| 端到端完成 | **{completed}/{total}** |",
            f"| TRL 校准 | **{calibrated}/{total}** |",
            f"| 加权公式正确 | **{formulas}/{total}** |",
            f"| 报告结构完整 | **{complete_reports}/{total}** |",
            f"| 无引用数值行 | **{total} 份报告中 {unsupported_numeric} 行** |",
        )
        for relative, claims in (
            ("README.md", english_claims),
            ("README.zh-CN.md", chinese_claims),
        ):
            readme = (ROOT / relative).read_text(encoding="utf-8")
            for claim in claims:
                with self.subTest(file=relative, claim=claim):
                    self.assertIn(claim, readme)


class RunIdDocumentationContractTests(unittest.TestCase):
    """Security prose must derive from the same entropy choice as the code."""

    def test_public_security_claims_match_run_id_entropy(self):
        bits = _RUN_ID_ENTROPY_BYTES * 8
        api_source = (ROOT / "api" / "main.py").read_text(encoding="utf-8")

        for relative, phrase in (
            ("README.md", "bits of randomness"),
            ("README.zh-CN.md", "位随机性"),
        ):
            with self.subTest(file=relative):
                readme = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(f"{bits} {phrase}", readme)
                self.assertNotIn("40 bits of randomness", readme)
                self.assertNotIn("40 位随机性", readme)
        self.assertNotIn("a 40-bit id", api_source)


class ServingSurfaceDocumentationTests(unittest.TestCase):
    """Removed entry points must not remain described as live architecture."""

    def test_current_entry_point_docs_do_not_advertise_gradio(self):
        # The contribution guide survived the frontend replacement with the
        # old entry point and sent new contributors to deleted files.
        for relative in (
            "AGENTS.md", "CONTRIBUTING.md", "api/main.py", "api/runs.py", "api/papers.py",
        ):
            with self.subTest(file=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertNotIn("Gradio", text)


class PublicDocumentationNavigationTests(unittest.TestCase):
    """Shorter entry points must keep their local evidence reachable."""

    def test_current_guide_relative_links_resolve(self):
        # This deliberately checks only repository paths, not remote URLs or
        # provider pages. Documentation validation must not create network
        # dependencies or pretend that a reachable citation proves a claim.
        for relative in (
            "README.md", "README.zh-CN.md", "AGENTS.md", "CONTRIBUTING.md",
            "docs/README.md", "docs/evidence-status.md", "docs/operating-guide.md",
            "docs/portfolio-case-study.md", "docs/experiment-index.md",
        ):
            document = ROOT / relative
            for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
                path = target.split("#", maxsplit=1)[0]
                if not path or "://" in path:
                    continue
                with self.subTest(file=relative, target=target):
                    self.assertTrue((document.parent / path).is_file(), target)

    def test_archive_links_every_dated_protocol_result_and_erratum(self):
        # Removing the old chronology is safe only if every underlying dated
        # decision remains discoverable. New studies should extend the index,
        # not recreate an append-only timeline in each language overview.
        archive = (ROOT / "docs" / "experiment-index.md").read_text(encoding="utf-8")
        for path in sorted((ROOT / "docs").glob("*.md")):
            if path.name.startswith(("prereg-", "protocol-", "results-", "errata-")):
                with self.subTest(file=path.name):
                    self.assertIn(f"]({path.name})", archive)


if __name__ == "__main__":
    unittest.main()
